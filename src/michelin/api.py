"""HTTP API + static hosting for the built frontend (web/dist). One process, deployable as-is.

    uv run uvicorn michelin.api:app --reload      # API on :8000, serves web/dist if it exists
    MICHELIN_MOCK=1 ...                           # /api/plan answers from data/fixtures

During frontend development run `npm run dev` in web/ instead; Vite proxies /api here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from michelin.explain import explain
from michelin.meal import PeopleAction, apply_people_action
from michelin.model import ExtractionRequest, ExtractionResponse
from michelin.plan.budget import subtotal_cap, totals
from michelin.plan.edibility import assessment, edible_by, open_questions
from michelin.plan.optimizer import solve
from michelin.plan.portions import required_range, total_units
from michelin.plan.score import variety_score
from michelin.plan.validation import validate_order
from michelin.profiles import ProfileStore
from michelin.schemas import (
    Check,
    Conflict,
    DinerProfile,
    Menu,
    Plan,
    PlanItem,
    TableRequest,
    validate_money,
)

ROOT = Path(__file__).resolve().parents[2]
MENU_DIR = Path(os.environ.get("MICHELIN_MENU_DIR", ROOT / "data/menus"))
PROFILE_DIR = Path(os.environ.get("MICHELIN_PROFILE_DIR", ROOT / "data/profiles"))
PROFILE_DB = Path(os.environ.get("MICHELIN_PROFILE_DB", ROOT / "data/local/profiles.sqlite3"))
WEB_DIST = Path(os.environ.get("MICHELIN_WEB_DIST", ROOT / "web/dist"))
FIXTURE_DIR = ROOT / "data/fixtures"
MOCK = os.environ.get("MICHELIN_MOCK", "") not in ("", "0", "false")

app = FastAPI(title="Michelin", version="0.1.0")


@app.post("/api/meal/people")
def meal_people(request: PeopleAction):
    try:
        diners = apply_people_action(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"diners": diners, "recommendation_invalidated": True}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the frontend may be hosted separately
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Data access (files on disk; swap for a DB later without touching the routes)
# ---------------------------------------------------------------------------


def load_menus() -> dict[str, Menu]:
    return {
        p.stem: Menu.model_validate_json(p.read_text()) for p in sorted(MENU_DIR.glob("*.json"))
    }


def load_profiles() -> dict[str, DinerProfile]:
    out: dict[str, DinerProfile] = {}
    for p in sorted(PROFILE_DIR.glob("*.json")):
        for row in json.loads(p.read_text()):
            profile = DinerProfile.model_validate(row)
            out[profile.id] = profile
    return out


# ---------------------------------------------------------------------------
# Wire types
# ---------------------------------------------------------------------------


class MenuSummary(BaseModel):
    slug: str
    restaurant_name: str
    cuisine: str
    verified: bool
    n_dishes: int


class PlanRequest(BaseModel):
    menu_id: str
    diner_ids: list[str] = Field(default_factory=list)  # saved profiles, by id
    diners: list[DinerProfile] = Field(default_factory=list)  # edited or ad-hoc, sent inline
    budget_per_person: float = Field(gt=0, allow_inf_nan=False)
    budget_total: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    _budget_cents = field_validator("budget_per_person", "budget_total")(validate_money)
    tax_rate: float = Field(default=0.08875, ge=0, le=0.3)
    tip_rate: float = Field(default=0.18, ge=0, le=0.4)
    min_dishes_per_person: int = Field(default=2, ge=1, le=40, strict=True)
    locked_dish_ids: list[str] = Field(default_factory=list)
    excluded_dish_ids: list[str] = Field(default_factory=list)
    menu_override: Menu | None = None
    dish_count_target: int | None = Field(default=None, ge=1, le=20)
    style_preference: str = Field(default="balanced", pattern="^(balanced|lighter|favorites)$")
    explain: bool = False  # ask the LLM stage for one-line reasons

    @model_validator(mode="after")
    def _someone_is_eating(self) -> PlanRequest:
        if not self.diner_ids and not self.diners:
            raise ValueError("diner_ids or diners must name at least one diner")
        if len({p.id for p in self.diners}) != len(self.diners):
            raise ValueError("Inline diner IDs must be unique")
        if len(set(self.diner_ids) | {p.id for p in self.diners}) > 6:
            raise ValueError("At most six diners are supported")
        return self


class PlanResponse(BaseModel):
    kind: str  # "plan" | "conflict"
    plan: Plan | None = None
    conflict: Conflict | None = None
    subtotal_cap: float


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mock": MOCK}


@app.get("/api/menus", response_model=list[MenuSummary])
def list_menus() -> list[MenuSummary]:
    return [
        MenuSummary(
            slug=slug,
            restaurant_name=m.restaurant_name,
            cuisine=m.cuisine,
            verified=m.verified,
            n_dishes=len(m.dishes),
        )
        for slug, m in load_menus().items()
    ]


@app.get("/api/menus/{slug}", response_model=Menu)
def get_menu(slug: str) -> Menu:
    menus = load_menus()
    if slug not in menus:
        raise HTTPException(404, f"unknown menu {slug!r}")
    return menus[slug]


@app.get("/api/profiles", response_model=list[DinerProfile])
def list_profiles(x_profile_scope: str | None = Header(default=None)) -> list[DinerProfile]:
    return list(_profiles(x_profile_scope).values())


def _scope(scope):
    import re

    if not scope or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", scope):
        raise HTTPException(422, "Supply X-Profile-Scope (1–100 letters, digits, _ or -).")
    return scope


def _profiles(scope):
    return load_profiles() if scope is None else ProfileStore(PROFILE_DB).list(_scope(scope))


class ProfileWrite(BaseModel):
    profile: DinerProfile
    expected_revision: int = Field(ge=0, strict=True)


@app.post("/api/profiles", status_code=201)
def create_profile(profile: DinerProfile, x_profile_scope: str | None = Header(default=None)):
    return _save_profile(profile, 0, x_profile_scope)


def _save_profile(profile, revision, scope):
    try:
        revision = ProfileStore(PROFILE_DB).save(_scope(scope), profile, revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"profile": profile, "revision": revision}


@app.get("/api/profiles/{person_id}/history")
def profile_history(person_id: str, x_profile_scope: str | None = Header(default=None)):
    rows = ProfileStore(PROFILE_DB).history(_scope(x_profile_scope), person_id)
    if not rows:
        raise HTTPException(404, "Unknown person in this scope")
    return rows


@app.get("/api/profiles/{person_id}")
def get_profile(person_id: str, x_profile_scope: str | None = Header(default=None)):
    return profile_history(person_id, x_profile_scope)[-1]


@app.put("/api/profiles/{person_id}")
def update_profile(
    person_id: str, body: ProfileWrite, x_profile_scope: str | None = Header(default=None)
):
    if person_id != body.profile.id or body.expected_revision < 1:
        raise HTTPException(422, "Keep the person ID stable and supply the current revision.")
    return _save_profile(body.profile, body.expected_revision, x_profile_scope)


@app.delete("/api/profiles/{person_id}")
def delete_profile(person_id: str, x_profile_scope: str | None = Header(default=None)):
    if not ProfileStore(PROFILE_DB).delete(_scope(x_profile_scope), person_id):
        raise HTTPException(404, "Unknown person in this scope")
    return {"deleted": True}


def _resolve_diners(req: PlanRequest, scope: str | None = None) -> list[DinerProfile]:
    """Inline diners win over saved profiles with the same id; order follows the request."""
    profiles = _profiles(scope)
    inline = {d.id: d for d in req.diners}
    missing = [d for d in req.diner_ids if d not in profiles and d not in inline]
    if missing:
        raise HTTPException(404, f"unknown diners {missing}")
    seen: set[str] = set()
    out: list[DinerProfile] = []
    for d in list(req.diners) + [profiles[i] for i in req.diner_ids if i not in inline]:
        if d.id not in seen:
            seen.add(d.id)
            if scope is not None and d.id in inline and d.id in profiles:
                saved = profiles[d.id]
                d = d.model_copy(
                    update={
                        key: getattr(saved, key)
                        for key in ("likes", "dislikes", "max_spice")
                        if key not in d.model_fields_set
                    }
                )
            out.append(d)
    return out


@app.post("/api/plan", response_model=PlanResponse)
def plan(req: PlanRequest, x_profile_scope: str | None = Header(default=None)) -> PlanResponse:
    menus = load_menus()
    if req.menu_override is None and req.menu_id not in menus:
        raise HTTPException(404, f"unknown menu {req.menu_id!r}")
    menu = req.menu_override or menus[req.menu_id]
    if menu.currency != "USD":
        raise HTTPException(422, "Only USD menus are supported.")
    if not menu.verified:
        raise HTTPException(422, "Review and verify the menu before planning.")
    if len(menu.dishes) > 40 or len({d.id for d in menu.dishes}) != len(menu.dishes):
        raise HTTPException(422, "Use up to 40 dishes with unique IDs.")
    if any(d.price is None or d.price < 0 for d in menu.dishes):
        raise HTTPException(422, "Every dish needs a valid price before planning.")
    known = {d.id for d in menu.dishes}
    for dish_id in req.locked_dish_ids + req.excluded_dish_ids:
        if dish_id not in known:
            raise HTTPException(404, f"unknown dish {dish_id!r}")

    request = TableRequest(
        menu_id=req.menu_id,
        diners=_resolve_diners(req, x_profile_scope),
        budget_per_person=req.budget_per_person,
        budget_total=req.budget_total,
        tax_rate=req.tax_rate,
        tip_rate=req.tip_rate,
        min_dishes_per_person=req.min_dishes_per_person,
        locked_dish_ids=req.locked_dish_ids,
        excluded_dish_ids=req.excluded_dish_ids,
        dish_count_target=req.dish_count_target,
        style_preference=req.style_preference,
    )
    cap = subtotal_cap(request.all_in_budget, 1, req.tax_rate, req.tip_rate)

    if MOCK:
        result = _mock_solve(menu, request)
    else:
        try:
            result = solve(menu, request)
        except TimeoutError as e:
            raise HTTPException(503, str(e)) from e

    if isinstance(result, Conflict):
        return PlanResponse(kind="conflict", conflict=result, subtotal_cap=cap)
    try:
        result = Plan.model_validate(result)
    except (ValueError, TypeError) as exc:
        raise HTTPException(502, "Planner returned malformed output.") from exc
    before = result.model_dump(exclude={"items"})
    original_items = [i.model_dump(exclude={"reason"}) for i in result.items]
    if req.explain:
        try:
            result = explain(result, menu, request)
        except NotImplementedError as e:
            raise HTTPException(501, f"explain not implemented: {e}") from e
        except Exception as e:
            raise HTTPException(502, "Explanation failed; no order returned.") from e
    try:
        result = Plan.model_validate(result)
        if before != result.model_dump(exclude={"items"}) or original_items != [
            i.model_dump(exclude={"reason"}) for i in result.items
        ]:
            raise ValueError("Explanation altered the order")
        report = validate_order(menu, request, result.items)
        if not report["valid"]:
            return PlanResponse(
                kind="conflict",
                subtotal_cap=cap,
                conflict=Conflict(
                    code="order_validation_failed",
                    message="Order failed independent validation: "
                    + "; ".join(r["detail"] for r in report["reasons"]),
                ),
            )
        if any(getattr(result, k) != v for k, v in report["totals"].items()):
            raise ValueError("Incorrect totals")
        if any(
            i.edible_by != edible_by(menu.dish(i.dish_id), request.diners) for i in result.items
        ):
            raise ValueError("Incorrect diner eligibility")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(502, "Planner or explanation returned invalid output.") from exc
    return PlanResponse(kind="plan", plan=result, subtotal_cap=cap)


@app.get("/api/model/prepared")
def prepared_inputs():
    """Known local inputs, not an extraction service or an OCR catalogue."""
    from michelin.model import prepared_catalog

    return [
        {
            key: row[key]
            for key in (
                "menu_id",
                "input_text",
                "input_sha256",
                "source_url",
                "retrieved_at",
                "preparation",
            )
        }
        for row in prepared_catalog()
    ]


@app.post("/api/menu/extract")
def extract_menu(req: ExtractionRequest) -> ExtractionResponse:
    from michelin.model import UnpreparedInput, extract, get_extraction_provider

    try:
        return extract(req, get_extraction_provider())
    except UnpreparedInput as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            502, "Extraction provider failed or returned malformed output; no menu accepted."
        ) from exc


class ParseRequest(BaseModel):
    text: str = Field(default="", max_length=100000)
    image_base64: str | None = Field(default=None, max_length=12000000)


@app.post("/api/menu/parse")
def parse_menu(req: ParseRequest) -> dict:
    import base64
    import binascii
    import shutil
    import subprocess
    import tempfile

    from michelin.parse import parse_text

    text = req.text
    if req.image_base64:
        binary = shutil.which("tesseract")
        if not binary:
            raise HTTPException(
                503,
                "Image reading is unavailable on this server. Paste menu text or add dishes manually.",
            )
        try:
            image = base64.b64decode(req.image_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "The image could not be read.")
        if not (
            image.startswith((b"\x89PNG", b"\xff\xd8\xff"))
            or (image.startswith(b"RIFF") and image[8:12] == b"WEBP")
        ):
            raise HTTPException(422, "Use a PNG, JPEG, or WebP menu image.")
        try:
            with tempfile.NamedTemporaryFile(suffix=".img") as source:
                source.write(image)
                source.flush()
                result = subprocess.run(
                    [binary, source.name, "stdout", "-l", "eng"],
                    capture_output=True,
                    text=True,
                    timeout=25,
                    check=False,
                )
            if result.returncode:
                raise HTTPException(
                    422, "The image could not be read. Try a clearer photo or paste the text."
                )
            text = result.stdout
        except subprocess.TimeoutExpired:
            raise HTTPException(
                503, "Image reading took too long. Try a smaller photo or paste the text."
            )
    if not text.strip():
        raise HTTPException(422, "Paste menu text or choose an image first.")
    return {
        "dishes": [d.model_dump() for d in parse_text(text)],
        "text": text,
        "mode": "local_ocr" if req.image_base64 else "local_text",
        "notice": "Local deterministic extraction; no model API called. Review all rows.",
    }


class EvaluateRequest(BaseModel):
    menu: Menu
    diners: list[DinerProfile]


@app.post("/api/menu/evaluate")
def evaluate_menu(req: EvaluateRequest) -> dict:
    return {
        d.id: {
            "edible_by": edible_by(d, req.diners),
            "blocked_for": {
                p.id: assessment(d, p)["reasons"]
                for p in req.diners
                if p.id not in edible_by(d, [p])
            },
            "assessments": {p.id: assessment(d, p) for p in req.diners},
            "questions": open_questions(d, req.diners),
        }
        for d in req.menu.dishes
    }


class OrderValidationRequest(BaseModel):
    menu: Menu
    request: TableRequest
    items: list[PlanItem] = Field(max_length=40)


@app.post("/api/order/validate")
def order_validation(body: OrderValidationRequest):
    return validate_order(body.menu, body.request, body.items)


# ---------------------------------------------------------------------------
# Mock: fixed dish selection from data/fixtures, everything derived is computed for real,
# so the frontend sees realistic edible_by / totals / checks while the optimizer is pending.
# ---------------------------------------------------------------------------


def _mock_solve(menu: Menu, request: TableRequest) -> Plan | Conflict:
    if request.budget_per_person < 20:
        return Conflict.model_validate_json((FIXTURE_DIR / "conflict_sample.json").read_text())

    fixture = Plan.model_validate_json((FIXTURE_DIR / "plan_sample.json").read_text())
    reasons: dict[str, str] = {}
    chosen: list[str] = [
        i.dish_id for i in fixture.items if i.dish_id not in request.excluded_dish_ids
    ]
    for dish_id in request.locked_dish_ids:
        if dish_id not in chosen:
            chosen.append(dish_id)
    chosen = [d for d in chosen if d in {x.id for x in menu.dishes}]

    n = request.n_diners
    items: list[PlanItem] = []
    subtotal = 0.0
    for dish_id in chosen:
        dish = menu.dish(dish_id)
        qty = n if dish.category.value == "staple" and dish.id == "steamed_rice" else 1
        subtotal += (dish.price or 0.0) * qty
        items.append(
            PlanItem(
                dish_id=dish_id,
                quantity=qty,
                edible_by=edible_by(dish, request.diners),
                reason=reasons.get(dish_id),
            )
        )

    dishes = [menu.dish(i.dish_id) for i in items]
    non_staple = [d for d in dishes if d.category.value != "staple"]
    t = totals(subtotal, n, request.tax_rate, request.tip_rate)
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    lo, hi = required_range(n)
    units = total_units(dishes)

    short = [
        p.name
        for p in request.diners
        if sum(1 for d in non_staple if p.id in edible_by(d, [p])) < request.min_dishes_per_person
    ]
    checks = [
        Check(
            name="allergies",
            passed=True,
            detail="Dishes are marked per diner; see who can eat what.",
        ),
        Check(
            name="diets", passed=True, detail="Diet flags applied per diner; null counts as unsafe."
        ),
        Check(
            name="coverage",
            passed=not short,
            detail=(
                f"Everyone can eat at least {request.min_dishes_per_person} dishes."
                if not short
                else f"Not enough for: {', '.join(short)}."
            ),
        ),
        Check(
            name="budget",
            passed=subtotal <= cap + 1e-6,
            detail=f"Menu subtotal ${subtotal:.2f} against a cap of ${cap:.2f}; total ${t.total:.2f}.",
        ),
        Check(
            name="portions",
            passed=lo <= units <= hi,
            detail=f"{units:.1f} portion units for {n} people (target {lo:.1f} to {hi:.1f}).",
        ),
    ]
    questions: list[str] = []
    for d in dishes:
        for q in open_questions(d, request.diners):
            if q not in questions:
                questions.append(q)

    return explain(
        Plan(
            items=items,
            subtotal=t.subtotal,
            tax=t.tax,
            tip=t.tip,
            total=t.total,
            per_person=t.per_person,
            variety_score=variety_score(dishes),
            checks=checks,
            confirm_with_staff=questions,
        ),
        menu,
        request,
    )


# ---------------------------------------------------------------------------
# Frontend: the Vite build output. Mounted last so /api/* wins.
# ---------------------------------------------------------------------------

if (WEB_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
else:

    @app.get("/", response_class=HTMLResponse)
    def frontend_not_built() -> str:
        return (
            "<p>Frontend not built. Run <code>npm run build</code> in <code>web/</code>, "
            "or <code>npm run dev</code> there for development (it proxies /api to this server).</p>"
        )
