"""The LLM chooses the dishes; deterministic code decides whether the order is allowed.

There is no rules-optimizer fallback: recommendations come only from the model
(OpenRouter first, then the free Gemini key; see michelin.llm).

The model sees a compact brief: each shareable dish with its price, category, portion
units, spice, allergen flags and hidden-ingredient knowledge, and which diners the server's
rules already allow to eat it; the diners' allergies, diets, heat limits, likes and
dislikes; the menu-price cap left after tax, tip and rice; the portion range; kept dishes.
It answers in a JSON schema with dish ids, a reason per dish, who each dish is for,
questions for the server, and, when nothing can fit, why and one change to make.

Every order goes through `validate_order` (ids on the menu, kept and removed dishes,
budget with tax and tip, portions, coverage for every diner) plus a check that each "for"
diner is actually allowed to eat the dish. Violations are sent back for at most
MAX_RETRIES more tries. If it still fails, or no model answers, the result is a conflict
that says why; it is never replaced by another planner.

Valid answers are cached by request (memory and data/local/llm_plans.json), so repeating
a request does not spend quota.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from michelin import gemini, llm
from michelin.explain import explain
from michelin.plan.budget import cents, subtotal_cap, totals
from michelin.plan.edibility import assessment, edible_by, open_questions
from michelin.plan.portions import required_range, units
from michelin.plan.score import variety_score
from michelin.plan.validation import validate_order
from michelin.schemas import Check, Conflict, Menu, Plan, PlanItem, Relaxation, TableRequest

log = logging.getLogger("michelin")
# Same idea as the web app's heat note: names that usually mean a hot dish.
HOT_NAME = re.compile(
    r"chil(i|li)|spicy|hot (?!and sour)|sichuan|szechuan|kung ?pao|ma ?po|dan ?dan|ma ?la|"
    r"numbing|麻辣|辣|水煮|宫保|麻婆|担担",
    re.IGNORECASE,
)
MAX_RETRIES = 3
CACHE_PATH = Path(__file__).resolve().parents[3] / "data/local/llm_plans.json"
_cache_lock = threading.Lock()
_memory: dict[str, dict] = {}

SYSTEM = """You plan a shared, family-style order at a Chinese restaurant for a table.

Choose dishes only from the list you are given, by id. Hard rules:
- Every diner must be able to eat at least the required number of chosen dishes. A dish \
counts for a diner only if that diner is in the dish's "ok_for" list; never list anyone \
else in "for". "ok_for" already applies allergies and diets; do not overrule it.
- Kept dishes must be in the order.
- The sum of the chosen dishes' prices must not exceed "menu_price_cap" (tax, tip and \
rice are already taken out of the budget).
- The chosen dishes' portion units must add up to within "portion_units" [min, max].
Then, softly: aim for "target_dishes" dishes, vary the main ingredients and cooking \
methods, respect heat limits ("max_spice" 0 means no heat; do not recommend a hot dish to \
that diner in "for" or in the reason), avoid dislikes, include likes.
For each dish give one short, specific reason (under 20 words) naming who it suits, and \
list a few short questions the table should ask the server about hidden ingredients or \
allergens in the chosen dishes. Do not invent ingredients that are not in the brief.

If no order can meet the hard rules (for example the cap is too low for enough dishes \
that everyone can eat), return an empty "dishes" list and fill "no_fit": a one-sentence \
reason and one change that would make an order possible. For a budget problem use change \
"budget" and put in "dish_ids" the cheapest order that meets every rule except the cap; \
the server prices it with tax, tip and rice. Otherwise use "coverage" with a smaller \
number of dishes per diner in "new_value"."""


@dataclass
class Outcome:
    plan: Plan | None
    conflict: Conflict | None
    note: str
    attempts: int = 0
    violations: list[list[str]] = field(default_factory=list)
    cached: bool = False


def enabled() -> bool:
    """Recommendations need a model: OpenRouter or Gemini."""
    return llm.provider() is not None


def _unavailable(message: str, attempts: int = 0, history=None) -> Outcome:
    return Outcome(
        None,
        Conflict(code="ai_unavailable", message=message),
        message,
        attempts,
        history or [],
    )


def _staples(menu: Menu, request: TableRequest):
    excluded, locked = set(request.excluded_dish_ids), set(request.locked_dish_ids)
    staples = [
        d
        for d in menu.dishes
        if d.category.value == "staple" and d.id not in excluded and d.price is not None
    ]
    kept = [d for d in staples if d.id in locked]
    if kept:
        return kept
    if not request.include_staple:
        return []
    everyone = [d for d in staples if len(edible_by(d, request.diners)) == request.n_diners]
    return [min(everyone, key=lambda d: d.price)] if everyone else []


def brief(menu: Menu, request: TableRequest) -> dict:
    n = request.n_diners
    staples = _staples(menu, request)
    staple_cost = sum(cents(d.price) * n for d in staples) / 100
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    excluded = set(request.excluded_dish_ids)
    dishes = []
    for d in menu.dishes:
        if d.id in excluded or d.category.value == "staple" or d.price is None:
            continue
        ok = edible_by(d, request.diners)
        if not ok:
            continue
        row = {
            "id": d.id,
            "name": d.name_en or d.name_zh,
            "price": d.price,
            "category": d.category.value,
            "units": units(d),
            "ok_for": ok,
        }
        if d.name_zh:
            row["zh"] = d.name_zh
        if d.spice_level is not None:
            row["spice"] = d.spice_level
        elif HOT_NAME.search(f"{d.name_en or ''} {d.name_zh or ''} {d.description_raw or ''}"):
            row["spice"] = "unknown, name suggests hot"
        if d.cooking_method:
            row["method"] = d.cooking_method
        main = [i.name for i in d.main_ingredients if i.tier.value == "menu"]
        hidden = [i.name for i in d.main_ingredients if i.tier.value != "menu"]
        if main:
            row["ingredients"] = main[:6]
        if hidden:
            row["may_contain"] = hidden[:6]
        if d.allergens:
            row["allergens"] = sorted({f"{f.allergen.value} ({f.tier.value})" for f in d.allergens})
        if d.confirm_with_staff:
            row["ask"] = d.confirm_with_staff[:2]
        dishes.append(row)
    lo, hi = required_range(n)
    diners = []
    for p in request.diners:
        row = {"id": p.id, "name": p.name}
        for key in ("allergies", "diets", "dislikes", "likes"):
            if getattr(p, key):
                row[key] = [getattr(x, "value", x) for x in getattr(p, key)]
        if p.max_spice is not None:
            row["max_spice"] = p.max_spice
        diners.append(row)
    target = request.dish_count_target or n + len(staples)
    return {
        "diners": diners,
        "dishes": dishes,
        "budget_per_person": request.budget_per_person,
        "tax_rate": request.tax_rate,
        "tip_rate": request.tip_rate,
        "menu_price_cap": round(cap - staple_cost, 2),
        "rice_added": [f"{d.name_en or d.id} x{n}" for d in staples],
        "portion_units": [lo, hi],
        "min_dishes_per_diner": request.min_dishes_per_person,
        "target_dishes": max(1, target - len(staples)),
        "kept": [i for i in request.locked_dish_ids if i not in {d.id for d in staples}],
        "style": request.style_preference,
    }


def _schema(ids: list[str], diner_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "dishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dish_id": {"type": "string", "enum": ids},
                        "reason": {"type": "string"},
                        "for": {"type": "array", "items": {"type": "string", "enum": diner_ids}},
                    },
                    "required": ["dish_id", "reason", "for"],
                },
            },
            "server_questions": {"type": "array", "items": {"type": "string"}},
            "no_fit": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "change": {"type": "string", "enum": ["budget", "coverage"]},
                    "dish_ids": {"type": "array", "items": {"type": "string", "enum": ids}},
                    "new_value": {"type": "number"},
                },
                "required": ["reason", "change"],
            },
        },
        "required": ["dishes", "server_questions"],
    }


def check(menu: Menu, request: TableRequest, answer: dict, staples) -> tuple[list[str], list]:
    """(violations, items). Items include the server-added rice."""
    known = {d.id: d for d in menu.dishes}
    allowed = {d.id for d in menu.dishes if d.category.value != "staple"}
    names = {p.id: p.name for p in request.diners}
    problems, items, seen = [], [], set()
    rows = answer.get("dishes") if isinstance(answer, dict) else None
    if not isinstance(rows, list) or not rows:
        return ["The answer had no dishes."], []
    for row in rows:
        dish_id = row.get("dish_id") if isinstance(row, dict) else None
        if dish_id not in known:
            problems.append(f"{dish_id!r} is not a dish id on this menu.")
            continue
        if dish_id not in allowed:
            problems.append(f"{dish_id} is rice/staple; it is added automatically, leave it out.")
            continue
        if dish_id in seen:
            problems.append(f"{dish_id} is listed twice.")
            continue
        seen.add(dish_id)
        ok = set(edible_by(known[dish_id], request.diners))
        for pid in row.get("for") or []:
            if pid in names and pid not in ok:
                problems.append(
                    f"{dish_id} is not safe for {names[pid]} ({pid}) under their allergies or "
                    "diets; do not count it for them."
                )
        items.append(PlanItem(dish_id=dish_id, quantity=1))
    items += [PlanItem(dish_id=d.id, quantity=request.n_diners) for d in staples]
    report = validate_order(menu, request, items)
    for reason in report["reasons"]:
        detail = reason["detail"]
        if reason["code"] == "insufficient_coverage":
            pid = detail.split(":")[0]
            detail = (
                f"{names.get(pid, pid)} ({pid}) can eat only {detail.split(': ')[1].split()[0]} "
                f"chosen dishes; needs {request.min_dishes_per_person}."
            )
        elif reason["code"] == "over_budget":
            subtotal = sum(cents(known[i.dish_id].price) * i.quantity for i in items) / 100
            cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
            detail = f"Menu prices add up to ${subtotal:.2f} including rice; the cap is ${cap:.2f}."
        elif reason["code"] == "missing_locked_dish":
            missing = set(request.locked_dish_ids) - {i.dish_id for i in items}
            detail = f"Kept dishes missing: {', '.join(sorted(missing))}."
        problems.append(detail)
    return list(dict.fromkeys(problems)), items


def _key(payload: dict, model_id: str) -> str:
    raw = json.dumps({"model": model_id, "brief": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str, path: Path) -> dict | None:
    with _cache_lock:
        if key in _memory:
            return _memory[key]
        if path.exists():
            try:
                stored = json.loads(path.read_text(encoding="utf-8")).get(key)
            except (OSError, ValueError):
                stored = None
            if stored:
                _memory[key] = stored
                return stored
    return None


def _cache_put(key: str, answer: dict, path: Path) -> None:
    with _cache_lock:
        _memory[key] = answer
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            data[key] = answer
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        except (OSError, ValueError):
            log.warning("Could not store the AI plan cache at %s", path)


def _to_plan(menu: Menu, request: TableRequest, answer: dict, items: list) -> Plan:
    known = {d.id: d for d in menu.dishes}
    selected = [(known[i.dish_id], i.quantity) for i in items]
    t = totals(
        sum(cents(d.price) * q for d, q in selected) / 100,
        request.n_diners,
        request.tax_rate,
        request.tip_rate,
    )
    reasons = {r["dish_id"]: str(r.get("reason") or "").strip()[:200] for r in answer["dishes"]}
    base = explain(
        Plan(
            items=[
                PlanItem(dish_id=d.id, quantity=q, edible_by=edible_by(d, request.diners))
                for d, q in selected
            ],
            subtotal=t.subtotal,
            tax=t.tax,
            tip=t.tip,
            total=t.total,
            per_person=t.per_person,
            variety_score=variety_score([d for d, _ in selected]),
        ),
        menu,
        request,
    )
    items = [
        i.model_copy(update={"reason": reasons.get(i.dish_id) or i.reason}) for i in base.items
    ]
    questions = list(
        dict.fromkeys(q for d, _ in selected for q in open_questions(d, request.diners))
    )
    extra = [str(q).strip()[:200] for q in answer.get("server_questions") or [] if str(q).strip()]
    checks = [
        Check(name="ai", passed=True, detail="Dishes chosen by the AI, then checked by the rules."),
        Check(
            name="coverage",
            passed=True,
            detail=f"Each diner has at least {request.min_dishes_per_person} non-staple dishes "
            "under recorded requirements.",
        ),
        Check(name="budget", passed=True, detail="The total includes tax and tip and fits."),
        Check(name="portions", passed=True, detail="Shared portions meet the estimated range."),
        Check(name="diets", passed=True, detail="Allergies and diets were checked per diner."),
    ]
    return base.model_copy(
        update={
            "items": items,
            "checks": checks,
            "confirm_with_staff": list(dict.fromkeys(questions + extra[:5])),
        }
    )


def _budget_for(menu: Menu, request: TableRequest, dish_ids) -> float | None:
    """Per-person all-in budget (next 50 cents) at which the model's suggested order passes
    every check. None when there is no suggested order or it fails anything but the budget."""
    if not isinstance(dish_ids, list) or not dish_ids:
        return None
    known = {d.id: d for d in menu.dishes}
    if any(i not in known for i in dish_ids) or len(set(dish_ids)) != len(dish_ids):
        return None
    staples = _staples(menu, request)
    items = [PlanItem(dish_id=i, quantity=1) for i in dish_ids]
    items += [PlanItem(dish_id=d.id, quantity=request.n_diners) for d in staples]
    subtotal = sum(cents(known[i.dish_id].price) * i.quantity for i in items) / 100
    t = totals(subtotal, request.n_diners, request.tax_rate, request.tip_rate)
    price = math.ceil(t.total / request.n_diners * 2 - 1e-9) / 2  # up to 50 cents a person
    raised = request.model_copy(update={"budget_per_person": price, "budget_total": None})
    return price if validate_order(menu, raised, items)["valid"] else None


def _unresolved(menu: Menu, request: TableRequest) -> bool:
    """Some dish is out only because its evidence is unresolved (ask staff), not a conflict."""
    return any(
        not (a := assessment(d, p))["eligible"] and a["status"] == "requires_confirmation"
        for d in menu.dishes
        for p in request.diners
    )


def _no_fit(
    menu: Menu, request: TableRequest, answer: dict, problems: list[str]
) -> Conflict | None:
    """The model's own "nothing fits" answer, with its suggested change if it is sane."""
    info = answer.get("no_fit") if isinstance(answer, dict) else None
    if not isinstance(info, dict) or answer.get("dishes"):
        return None
    reason = str(info.get("reason") or "").strip()[:300] or "No order meets every rule."
    relaxations = []
    value = info.get("new_value")
    if info.get("change") == "budget":
        price = _budget_for(menu, request, info.get("dish_ids"))
        if price is None and isinstance(value, int | float):
            price = round(float(value) * 2 + 0.4999) / 2  # the model's own figure
        if price is not None and request.budget_per_person < price <= 500:
            relaxations.append(
                Relaxation(
                    kind="budget",
                    new_value=price,
                    description=f"Set the all-in budget to {price:.2f} per person.",
                )
            )
    elif info.get("change") == "coverage" and isinstance(value, int | float):
        n = int(value)
        if 1 <= n < request.min_dishes_per_person:
            relaxations.append(
                Relaxation(
                    kind="coverage",
                    new_value=n,
                    description=f"Allow at least {n} non-staple dishes per diner.",
                )
            )
    message = (
        f"{reason} No order meets the current budget, portions, dietary coverage, and kept dishes."
    )
    if problems:
        message += " Last attempt: " + "; ".join(problems[:3])
    return Conflict(code="no_solution", message=message, relaxations=relaxations)


def _ask(turns: list, schema: dict, menu: Menu, request: TableRequest, client):
    """One model call -> (JSON text, model used). Tests replace this with a fake."""
    return llm.generate_json("plan", system=SYSTEM, turns=turns, schema=schema, client=client)


def plan(menu: Menu, request: TableRequest, client=None, cache_path: Path | None = None) -> Outcome:
    """A model-chosen order that passed every check, or a conflict that says why not."""
    cache_path = cache_path or CACHE_PATH
    if not enabled() and client is None:
        return _unavailable(
            "Recommendations need an AI model, and none is configured on this server. "
            "Set OPENROUTER_API_KEY or GEMINI_API_KEY (see the README)."
        )
    payload = brief(menu, request)
    if not payload["dishes"]:
        return Outcome(
            None,
            Conflict(
                code="missing_information" if _unresolved(menu, request) else "no_solution",
                message="No dish on this menu fits anyone's recorded allergies and diets; "
                "unresolved items need confirmation with staff. Review the menu or the "
                "diners' settings.",
            ),
            "No dish fits anyone.",
        )
    staples = _staples(menu, request)
    model_id = llm.model("plan")
    key = _key(payload, model_id)
    stored = _cache_get(key, cache_path)
    if stored:
        problems, items = check(menu, request, stored["answer"], staples)
        if not problems:
            return Outcome(
                _to_plan(menu, request, stored["answer"], items),
                None,
                f"AI plan by {llm.label(stored['model'])}, checked by the rules (cached).",
                cached=True,
            )
    ids = [d["id"] for d in payload["dishes"]]
    schema = _schema(ids, [p.id for p in request.diners])
    turns = [llm.Turn("user", "Brief:\n" + json.dumps(payload, ensure_ascii=False))]
    history: list[list[str]] = []
    answer: dict = {}
    for attempt in range(1 + MAX_RETRIES):
        try:
            text, used = _ask(turns, schema, menu, request, client)
        except gemini.RateLimited as exc:
            if "OpenRouter credit" in str(exc):
                message = f"{exc} No order was made."
            elif exc.daily:
                message = (
                    "Today's free Gemini quota is used up (it resets daily), so no order was "
                    "made. Set OPENROUTER_API_KEY to use a paid model."
                )
            else:
                message = "The AI model is rate limited right now, so no order was made. "
                message += "Try again in a minute."
            return _unavailable(message, attempt, history)
        except llm.Unavailable as exc:
            return _unavailable(str(exc), attempt, history)
        except Exception as exc:  # noqa: BLE001 - network, timeout, provider errors
            log.warning("AI planner failed: %s: %s", type(exc).__name__, str(exc)[:300])
            return _unavailable(
                "The AI model did not answer, so no order was made. Try again in a moment.",
                attempt,
                history,
            )
        try:
            answer = json.loads(text or "")
        except ValueError:
            answer = {"dishes": []}
        no_fit = _no_fit(menu, request, answer, history[-1] if history else [])
        if no_fit is not None:
            history.append([])
            return Outcome(None, no_fit, "The AI found no order that fits.", attempt + 1, history)
        problems, items = check(menu, request, answer, staples)
        history.append(problems)
        if not problems:
            _cache_put(key, {"model": used, "answer": answer}, cache_path)
            retried = f" after {attempt} correction{'s' * (attempt > 1)}" if attempt else ""
            return Outcome(
                _to_plan(menu, request, answer, items),
                None,
                f"AI plan by {llm.label(used)}, checked by the rules{retried}.",
                attempt + 1,
                history,
            )
        turns += [
            llm.Turn("model", text or ""),
            llm.Turn(
                "user",
                "That order breaks these rules:\n- "
                + "\n- ".join(problems)
                + "\nReturn a corrected order in the same format. If no order can meet the "
                "rules, return no dishes and fill no_fit with the reason and one change.",
            ),
        ]
    last = history[-1] if history else []
    return Outcome(
        None,
        Conflict(
            code="ai_no_valid_order",
            message=f"The AI could not find an order that passes the checks after "
            f"{1 + MAX_RETRIES} tries. Still wrong: " + "; ".join(last[:4]),
        ),
        "The AI's orders did not pass the checks.",
        1 + MAX_RETRIES,
        history,
    )
