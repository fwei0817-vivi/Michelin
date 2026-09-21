"""HTTP API + static hosting for the web/ frontend. One process, deployable as-is.

    uv run uvicorn michelin.api:app --reload
    open http://localhost:8000
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from michelin.explain import explain
from michelin.plan.budget import subtotal_cap
from michelin.plan.optimizer import solve
from michelin.schemas import Conflict, DinerProfile, Menu, Plan, TableRequest

ROOT = Path(__file__).resolve().parents[2]
MENU_DIR = Path(os.environ.get("MICHELIN_MENU_DIR", ROOT / "data/menus"))
PROFILE_DIR = Path(os.environ.get("MICHELIN_PROFILE_DIR", ROOT / "data/profiles"))
WEB_DIR = Path(os.environ.get("MICHELIN_WEB_DIR", ROOT / "web"))
FIXTURE_DIR = ROOT / "data/fixtures"
MOCK = os.environ.get("MICHELIN_MOCK", "") not in ("", "0", "false")

app = FastAPI(title="Michelin", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the frontend may be hosted separately (GitHub Pages etc.)
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Data access (files on disk; swap for a DB later without touching the routes)
# ---------------------------------------------------------------------------


def load_menus() -> dict[str, Menu]:
    return {p.stem: Menu.model_validate_json(p.read_text()) for p in sorted(MENU_DIR.glob("*.json"))}


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
    diner_ids: list[str] = Field(min_length=1)
    budget_per_person: float = Field(gt=0)
    tax_rate: float = 0.08875
    tip_rate: float = 0.18
    min_dishes_per_person: int = Field(default=2, ge=1)
    explain: bool = False  # ask Claude for one-line reasons (needs ANTHROPIC_API_KEY)


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
    return {"ok": True}


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
def list_profiles() -> list[DinerProfile]:
    return list(load_profiles().values())


@app.post("/api/plan", response_model=PlanResponse)
def plan(req: PlanRequest) -> PlanResponse:
    menus = load_menus()
    if req.menu_id not in menus:
        raise HTTPException(404, f"unknown menu {req.menu_id!r}")
    profiles = load_profiles()
    missing = [d for d in req.diner_ids if d not in profiles]
    if missing:
        raise HTTPException(404, f"unknown diners {missing}")

    menu = menus[req.menu_id]
    request = TableRequest(
        menu_id=req.menu_id,
        diners=[profiles[d] for d in req.diner_ids],
        budget_per_person=req.budget_per_person,
        tax_rate=req.tax_rate,
        tip_rate=req.tip_rate,
        min_dishes_per_person=req.min_dishes_per_person,
    )
    cap = subtotal_cap(req.budget_per_person, request.n_diners, req.tax_rate, req.tip_rate)

    if MOCK:  # frontend development before the optimizer exists
        if req.budget_per_person < 20:
            conflict = Conflict.model_validate_json((FIXTURE_DIR / "conflict_sample.json").read_text())
            return PlanResponse(kind="conflict", conflict=conflict, subtotal_cap=cap)
        fixture = Plan.model_validate_json((FIXTURE_DIR / "plan_sample.json").read_text())
        return PlanResponse(kind="plan", plan=fixture, subtotal_cap=cap)

    try:
        result = solve(menu, request)
    except NotImplementedError as e:
        raise HTTPException(501, f"optimizer not implemented: {e}") from e

    if isinstance(result, Conflict):
        return PlanResponse(kind="conflict", conflict=result, subtotal_cap=cap)
    if req.explain:
        try:
            result = explain(result, menu, request)
        except NotImplementedError as e:
            raise HTTPException(501, f"explain not implemented: {e}") from e
    return PlanResponse(kind="plan", plan=result, subtotal_cap=cap)


# Static frontend last, so /api/* wins. html=True serves index.html at "/".
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
