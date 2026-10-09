"""The LLM chooses the dishes; deterministic code decides whether the order is allowed.

There is no rules-optimizer fallback: recommendations come only from the model
(OpenRouter first, then the free Gemini key; see michelin.llm).

The model sees a compact brief: each shareable dish with its price, category, spice,
the AI's own likely-ingredient and allergen facts (plan/dish_facts.py) and rule-flagged
risks, and which diners the server's rules already allow to eat it; the diners' allergies,
diets and free-text taste notes; the menu-price cap left after tax, tip and rice; kept dishes. The model
decides how many dishes to order (guideline: about one per person, plus rice). It answers
in a JSON schema with dish ids, a reason and a server question per dish, who each dish is
for, a one-line summary, and, when nothing can fit, why.

Every order goes through `validate_order` (ids on the menu, kept and removed dishes,
allergies and diets, budget with tax and tip, every diner able to eat at least one dish)
plus a check that each "for" diner is actually allowed to eat the dish. There is no
portion or dish-count rule. Violations are sent back for at most
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
from michelin.plan import hints as rules_hints
from michelin.plan import refine
from michelin.plan.budget import cents, subtotal_cap, totals
from michelin.plan.edibility import (
    ask_server,
    assessment,
    edible_by,
    risks,
)
from michelin.plan.score import variety_score
from michelin.plan.validation import family_repeats, validate_order
from michelin.schemas import (
    PREFERENCE_TEXT,
    Check,
    Conflict,
    Menu,
    Plan,
    PlanItem,
    Relaxation,
    TableRequest,
)

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
- Every diner must be able to eat at least one chosen dish. A dish counts for a diner \
only if that diner is in the dish's "ok_for" list; never list anyone else in "for". \
"ok_for" already applies allergies and diets; do not overrule it.
- Kept dishes must be in the order.
- The sum of the chosen dishes' prices must not exceed "menu_price_cap" (tax, tip and \
rice are already taken out of the budget).
You decide how many dishes to order. A good guideline is about one dish per person (rice \
is added for everyone), more if dishes are small and the budget allows, fewer if they are \
large or money is tight; make sure each diner has a fair share they can eat. Then, softly: \
vary the main ingredients and cooking methods, and follow each diner's "notes" (their tastes \
in their own words, e.g. "no spicy food, loves tofu": do not recommend a hot dish to someone \
who avoids heat, in "for" or in the reason). Notes may start with quick taste picks: \
"no spicy food" or "mild heat at most" means choose dishes with spice 0-1 for them and \
avoid spice 2-3 unless nothing else fits; "loves spicy food" means include a hot dish they \
can eat; "likes seafood" or "likes meat dishes" means include one they can eat; "prefers \
light..." (清淡) favours steamed, cold, soup and simple stir-fried dishes over deep-fried, \
heavy braised or oily ones; "no offal" means avoid tripe, intestine, liver, kidney, blood. \
These are tastes, not rules: never let them leave a diner with nothing to eat.
Dishes with the same "family" are one menu line in different versions (e.g. Kung Pao \
with chicken, beef, shrimp or tofu, each with its own price and "ok_for"): choose the \
version that suits the table. Order a second version of the same family only if each \
version feeds someone the other cannot; never three.
For each dish give one short, specific reason (under 20 words) naming who it suits.
For each chosen dish that has "risks", write "server_question": ONE plain sentence (under \
25 words) that a diner would actually say to the server: name the dish, ask about every \
listed risk, and say who it is for. Examples: "Is there any pork or lard in the scallion \
pancake? David and Tom don't eat pork." is two sentences, so instead write "Is there any \
pork or lard in the scallion pancake, since David and Tom don't eat pork?" or "Does the bok \
choy use meat stock or oyster sauce? It's for David (vegetarian) and Amy (shellfish)." -> \
"Does the bok choy use meat stock or oyster sauce, for David (vegetarian) and Amy (shellfish)?". \
No lists, no semicolons, no "ask whether". Do not invent ingredients that are not in the \
brief, and state only the allergies and diets the brief lists for each diner. Use "" for \
dishes without risks. Put only questions \
about the whole meal (not one dish) in "server_questions"; usually it is empty.
Finally, "summary": one friendly sentence (under 30 words) on how the order works for this \
table, including why this many dishes (e.g. small plates, so a few extra). Do not write the number of dishes; the app shows the count.

If no order can meet the hard rules (for example the cap is too low for a dish everyone \
can eat), return an empty "dishes" list and fill "no_fit": a one-sentence reason and, \
with change "budget", the cheapest order that meets every rule except the cap in \
"dish_ids"; the server prices it with tax, tip and rice."""


@dataclass
class Outcome:
    plan: Plan | None
    conflict: Conflict | None
    note: str
    attempts: int = 0
    violations: list[list[str]] = field(default_factory=list)
    cached: bool = False
    fallback: bool = False  # the rules built this order after the AI's tries failed
    answer: dict | None = None  # the model's accepted answer (for the change note)
    change_note: str | None = None  # refinement: what changed, checked against the diff
    changes: list[str] = field(default_factory=list)  # refinement: the code-computed diff


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


def brief(menu: Menu, request: TableRequest, hint: rules_hints.Hints | None = None) -> dict:
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
            "ok_for": ok,
        }
        if d.name_zh:
            row["zh"] = d.name_zh
        if d.family_id:
            row["family"] = d.family_name or d.family_id
            row["version"] = d.variant
        if d.menu_marks:
            row["menu_marks"] = [getattr(m, "value", m).replace("_", " ") for m in d.menu_marks]
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
        flagged = risks(d, request.diners)
        if flagged:
            # Facts from the rules; the model words the question, the rules check it.
            row["risks"] = [
                f"{r.about}" + (f" (matters for {', '.join(r.names)})" if r.names else "")
                for r in flagged
            ][:5]
        dishes.append(row)
    diners = []
    for p in request.diners:
        row = {"id": p.id, "name": p.name}
        for key in ("allergies", "diets"):
            if getattr(p, key):
                row[key] = [humanize(getattr(x, "value", x)) for x in getattr(p, key)]
        if p.other_allergies:  # hard, in their own words; "ok_for" already applies them
            row["other_allergies"] = list(p.other_allergies)
        if p.other_diets:
            row["other_diets"] = list(p.other_diets)
        tastes = [PREFERENCE_TEXT[x] for x in p.preferences]
        if p.notes:
            tastes.append(p.notes)
        if tastes:
            row["notes"] = "; ".join(tastes)
        diners.append(row)
    return {
        "diners": diners,
        "dishes": dishes,
        "budget_per_person": request.budget_per_person,
        "tax_rate": request.tax_rate,
        "tip_rate": request.tip_rate,
        "menu_price_cap": round(cap - staple_cost, 2),
        "rice_added": [f"{d.name_en or d.id} x{n}" for d in staples],
        "kept": [i for i in request.locked_dish_ids if i not in {d.id for d in staples}],
        "style": request.style_preference,
        **_hint_fields(menu, request, hint),
    }


def _hint_fields(menu: Menu, request: TableRequest, hint) -> dict:
    """Facts from the rules that make the model's job easier; never a chosen order."""
    if hint is None:
        return {}
    out: dict = {}
    if hint.feasible is not None:
        out["an_order_fits"] = hint.feasible
    if hint.feasible is False and hint.min_budget is not None:
        out["lowest_budget_per_person_that_fits"] = hint.min_budget
    names = {p.id: p.name for p in request.diners}
    if hint.must_include:
        out["only_option"] = {names[pid]: ids[0] for pid, ids in hint.must_include.items()}
    return out


def _hint_text(menu: Menu, request: TableRequest, hint) -> list[str]:
    """Retry hints: what the rules know about this table, in words."""
    if hint is None:
        return []
    names = {p.id: p.name for p in request.diners}
    lines = []
    for pid, ids in hint.must_include.items():
        lines.append(f"{names[pid]} can eat only {ids[0]} here; it must be in the order.")
    if hint.feasible:
        lines.append(
            "An order that meets every rule exists within the cap, so do not return no_fit."
        )
    elif hint.feasible is False and hint.min_budget is not None:
        lines.append(
            f"No order fits this budget; the lowest that fits is ${hint.min_budget:.2f} per "
            'person. Return no dishes and no_fit with change "budget".'
        )
    return lines


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
                        "server_question": {"type": "string"},
                    },
                    "required": ["dish_id", "reason", "for", "server_question"],
                },
            },
            "server_questions": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "no_fit": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "change": {"type": "string", "enum": ["budget"]},
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
    problems += family_repeats(menu, request, [i.dish_id for i in items])
    items += [PlanItem(dish_id=d.id, quantity=request.n_diners) for d in staples]
    report = validate_order(menu, request, items)
    for reason in report["reasons"]:
        detail = reason["detail"]
        if reason["code"] == "insufficient_coverage":
            pid = detail.split(":")[0]
            detail = (
                f"{names.get(pid, pid)} ({pid}) cannot eat any chosen dish; add one they can eat."
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
    # The prompt is part of the key, so a prompt change never serves an old answer.
    raw = json.dumps(
        {"model": model_id, "brief": payload, "system": SYSTEM}, sort_keys=True, ensure_ascii=False
    )
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


_NUMBERS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]
_COUNT = re.compile(
    r"\b(\d+|"
    + "|".join(_NUMBERS)
    + r")\s+(?:[a-z-]+\s+){0,2}(?:dish|dishes|plates|items|courses)\b(?!\s+(?:per|each|for each)\b)",
    re.IGNORECASE,
)


_SINGLE = re.compile(
    r"\b(?:single|lone|sole|only)\s+(?:[a-z-]+\s+){0,2}(?:dish|plate|item|order)\b", re.IGNORECASE
)


def _count_ok(text: str, n: int) -> bool:
    """No dish count in the text other than n ("two dishes", "this single dish")."""
    for m in _COUNT.finditer(text):
        word = m.group(1).lower()
        if (int(word) if word.isdigit() else _NUMBERS.index(word)) != n:
            return False
    return n == 1 or not _SINGLE.search(text)


def _summary(text: object, n: int) -> str | None:
    """The model's one-line summary, dropped if it states a dish count other than the plan's
    (n is the number of order lines, rice included)."""
    text = str(text or "").strip()[:240]
    return text if text and _count_ok(text, n) else None


def _noted(dish, notes: str | None) -> bool:
    """The diner's own notes mention this dish (a word of its name, e.g. "tofu")."""
    low = (notes or "").lower()
    words = re.findall(r"[a-z]{4,}", (dish.name_en or "").lower())
    return any(w.rstrip("s") in low for w in words)


def _fair_reason(text: str | None, dish, request: TableRequest, n: int = 0) -> str | None:
    """The AI's one-line reason, unless it singles out a diner the rules flag for this dish
    ("Great for everyone, especially Cai" on a dish that may hide Cai's allergen). Then the
    rule-based reason is used instead."""
    if not text or (n and not _count_ok(text, n)):
        return None  # QA r6: "This single dish is chosen…" on a two-line order
    for person in request.diners:
        name = (person.name or "").strip()
        if not name or not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
            continue
        if assessment(dish, person)["status"] != "validated_under_known_data":
            return None
        taste = rf"{re.escape(name)},? (?:who )?(?:loves|likes|enjoys|prefers|avoids|craves)\b"
        if re.search(taste, text, re.IGNORECASE) and not _noted(
            dish, " ".join([person.notes, *(PREFERENCE_TEXT[x] for x in person.preferences)])
        ):
            return None  # a taste nobody recorded ("Pat, who loves peanuts")
    return text


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
        i.model_copy(
            update={
                "reason": _fair_reason(
                    reasons.get(i.dish_id), known[i.dish_id], request, len(base.items)
                )
                or i.reason
            }
        )
        for i in base.items
    ]
    asked = server_questions(answer, selected, request)
    items = [i.model_copy(update={"server_question": asked.get(i.dish_id)}) for i in items]
    extra = [str(q).strip()[:200] for q in answer.get("server_questions") or [] if str(q).strip()]
    checks = [
        Check(name="ai", passed=True, detail="Dishes chosen by the AI, then checked by the rules."),
        Check(
            name="coverage",
            passed=True,
            detail="Everyone can eat at least one dish under their recorded requirements.",
        ),
        Check(name="budget", passed=True, detail="The total includes tax and tip and fits."),
        Check(name="diets", passed=True, detail="Allergies and diets were checked per diner."),
    ]
    return base.model_copy(
        update={
            "items": items,
            "checks": checks,
            "confirm_with_staff": [asked[d.id] for d, _ in selected if d.id in asked] + extra[:3],
            "summary": _summary(answer.get("summary"), len(items)),
        }
    )


# Allergy and diet words a server question can raise; each must match a flagged risk.
_CONCERNS = [
    "peanut",
    "sesame",
    "shellfish",
    "shrimp",
    "prawn",
    "crab",
    "oyster",
    "fish",
    "egg",
    "dairy",
    "milk",
    "butter",
    "cream",
    "soy",
    "wheat",
    "gluten",
    "flour",
    "nut",
    "cashew",
    "almond",
    "walnut",
    "pork",
    "lard",
    "bacon",
    "ham",
    "beef",
    "lamb",
    "chicken",
    "meat",
    "broth",
    "stock",
]


def humanize(text: str) -> str:
    """Raw ids never reach the user: "no_pork" -> "no pork", "tree_nut" -> "tree nut"."""
    return re.sub(r"\b([a-z]+)_([a-z]+)\b", r"\1 \2", text)


def _off_topic(text: str, dish, diners, flagged) -> bool:
    """True when a question names someone the dish is not for, someone it flags nothing for,
    or raises an allergy/diet concern that no flagged risk on this dish involves."""
    label = (dish.name_en or dish.name_zh or dish.id).lower()
    low = humanize(text).lower().replace(label, " ")
    eaters = set(edible_by(dish, diners))
    concerned = {n for r in flagged for n in r.names}
    for p in diners:
        if p.name and re.search(rf"\b{re.escape(p.name.lower())}\b", low):
            if p.id not in eaters or (concerned and p.name not in concerned):
                return True
            if not flagged:
                return True
    allowed = {w for r in flagged for w in r.words} | {
        w for r in flagged for w in re.findall(r"[a-z]+", r.about.lower())
    }
    for term in _CONCERNS:
        if re.search(rf"\b{term}s?\b", low) and not any(
            term == w or w.startswith(term) or term.startswith(w) for w in allowed if len(w) > 2
        ):
            return True
    return False


def _misstates(text: str, diners) -> bool:
    """True when the text gives a diner an allergy or diet they do not have
    ("Kevin has a peanut allergy", "David is allergic to sesame", "Li is vegan")."""

    def same(term: str, recorded: list[str]) -> bool:
        term = term.strip().lower().rstrip("s")
        return any(
            term in r.lower().replace("_", " ") or r.lower().rstrip("s") in term for r in recorded
        )

    for p in diners:
        name = re.escape(p.name)
        claims = re.findall(
            rf"\b{name}\s+(?:has|have)\s+(?:an?\s+)?([a-z -]+?)\s+allerg", text, re.IGNORECASE
        )
        claims += re.findall(
            rf"\b{name}\s+(?:is|are)\s+allergic\s+to\s+([a-z]+(?:\s+nuts?)?)", text, re.IGNORECASE
        )
        if any(not same(c, [*p.allergies, *p.other_allergies]) for c in claims):
            return True
        for diet in re.findall(
            rf"\b{name}\s+(?:is|are)\s+(vegetarian|vegan)\b", text, re.IGNORECASE
        ):
            ok = {"vegan"} if diet.lower() == "vegan" else {"vegan", "vegetarian"}
            if not ok & set(p.diets):
                return True
    return False


def server_questions(answer: dict, selected, request: TableRequest) -> dict[str, str]:
    """One line per dish for the server: the model's question, plus the rule-based question
    for any flagged risk it does not cover (a named diner and the risk's word must appear)."""
    written = {
        r["dish_id"]: str(r.get("server_question") or "").strip()[:300]
        for r in answer.get("dishes") or []
        if isinstance(r, dict)
    }
    out: dict[str, str] = {}
    for d, _ in selected:
        label = d.name_en or d.name_zh or d.id
        flagged = risks(d, request.diners)
        mine = _plain(written.get(d.id, ""), label)
        if _misstates(mine, request.diners) or _off_topic(mine, d, request.diners, flagged):
            # Never show a need the diner does not have, a question for someone the dish is
            # not for, or a concern nothing on this dish involves; the rule questions stand.
            mine = ""
        missing = [r for r in flagged if not (mine and r.covered_by(mine))]
        if not mine and not missing:
            continue
        # A skipped risk gets the rules' own plain question, after the model's.
        out[d.id] = " ".join(
            x for x in [mine, ask_server(d, missing, bool(mine)) if missing else ""] if x
        )
    return out


def _plain(text: str, label: str) -> str:
    """Light cleanup of a model question: one line, no "Dish:" prefix, no semicolon lists,
    the dish named, ending in a question mark."""
    text = " ".join(str(text or "").split())[:240]
    if text.lower().startswith(label.lower()) and text[len(label) : len(label) + 1] in ":-–—":
        text = text[len(label) :].lstrip(" :-–—").strip()
    text = humanize(text.replace(";", ",")).strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    words = [w for w in re.findall(r"[a-z]+", label.lower()) if len(w) > 3]
    if words and not any(w in text.lower() for w in words):
        text = f"{label}: {text}"  # the server must know which dish
    return text if text.endswith(("?", ".")) else text + "?"


THIN = 2  # a diner with fewer non-rice dishes than this is under-served
COVERAGE_NUDGE = True  # tests of other behaviour switch this off (conftest)


def counts(menu: Menu, request: TableRequest, items) -> dict[str, int]:
    """Non-rice dishes in the order each diner can eat."""
    known = {d.id: d for d in menu.dishes}
    dishes = [known[i.dish_id] for i in items if known[i.dish_id].category.value != "staple"]
    ok = [set(edible_by(d, request.diners)) for d in dishes]
    return {p.id: sum(p.id in o for o in ok) for p in request.diners}


def spread(menu: Menu, request: TableRequest, items) -> tuple[int, ...]:
    """Dish counts per diner, least-served first: compared to prefer the order whose
    least-served diner has more (then the next least-served, and so on)."""
    return tuple(sorted(counts(menu, request, items).values()))


@dataclass
class CoverageFix:
    items: list  # the changed order (rice included)
    add: str  # dish id brought in
    drop: str | None  # dish id taken out (None: added on top)
    helps: list[str]  # names of the least-served diners it helps


def coverage_fix(menu: Menu, request: TableRequest, items) -> CoverageFix | None:
    """A valid, in-budget change of one dish (or one added dish) that gives an under-served
    diner another dish without leaving anyone worse off overall: the least-served diners'
    counts strictly improve. None when coverage is already fine or nothing fits."""
    have = counts(menu, request, items)
    low = min(have.values(), default=THIN)
    if low >= THIN:
        return None
    least = {pid for pid, n in have.items() if n == low}
    names = {p.id: p.name or p.id for p in request.diners}
    known = {d.id: d for d in menu.dishes}
    chosen = [i.dish_id for i in items if known[i.dish_id].category.value != "staple"]
    excluded, locked = set(request.excluded_dish_ids), set(request.locked_dish_ids)
    now = spread(menu, request, items)
    best, best_key = None, None
    for d in menu.dishes:
        if d.id in chosen or d.id in excluded or d.price is None or d.category.value == "staple":
            continue
        ok = set(edible_by(d, request.diners))
        if not ok & least:
            continue
        options = [(None, [*items, PlanItem(dish_id=d.id, quantity=1)])]
        options += [
            (x, [PlanItem(dish_id=d.id, quantity=1) if i.dish_id == x else i for i in items])
            for x in chosen
            if x not in locked
        ]
        for drop, option in options:
            after = spread(menu, request, option)
            if after <= now or not validate_order(menu, request, option)["valid"]:
                continue
            if family_repeats(menu, request, [i.dish_id for i in option]):
                continue
            subtotal = sum(cents(known[i.dish_id].price) * i.quantity for i in option)
            key = (after, drop is not None, -subtotal)  # most even, then a swap, then cheaper
            if best_key is None or key > best_key:
                helps = [names[p] for p in sorted(ok & least)]
                best, best_key = CoverageFix(option, d.id, drop, helps), key
    return best


def _fix_text(menu: Menu, request: TableRequest, fix: CoverageFix) -> str:
    have = counts(menu, request, fix.items)
    who = ", ".join(fix.helps)
    name = menu.dish(fix.add).name_en or fix.add
    change = (
        f"replace {fix.drop} with {fix.add} ({name})" if fix.drop else f"add {fix.add} ({name})"
    )
    return (
        f"{who} can eat too few of the chosen dishes. A valid change within the budget: "
        f"{change}, after which the counts per diner are "
        + ", ".join(f"{p.name or p.id} {have[p.id]}" for p in request.diners)
        + ". Favour the least-served diners: return the full corrected order in the same "
        "format (this change, or a better one that passes every rule)."
    )


def _apply_fix(answer: dict, fix: CoverageFix, menu: Menu, request: TableRequest) -> dict:
    """The model's answer with the rules' coverage change made in code."""
    rows = [
        r for r in answer.get("dishes", []) if isinstance(r, dict) and r.get("dish_id") != fix.drop
    ]
    ok = edible_by(menu.dish(fix.add), request.diners)
    rows.append({"dish_id": fix.add, "reason": "", "for": ok, "server_question": ""})
    return {**answer, "dishes": rows, "summary": ""}


def fallback(menu: Menu, request: TableRequest) -> tuple[dict, list] | None:
    """The rules' own order: the cheapest valid one, then one coverage step if it fits."""
    order, _ = rules_hints.cheapest_order(menu, request)
    if not order:
        return None
    rows = [
        {
            "dish_id": d.id,
            "reason": "",
            "for": edible_by(d, request.diners),
            "server_question": "",
        }
        for d, _ in order
        if d.category.value != "staple"
    ]
    answer = {"dishes": rows, "server_questions": [], "summary": ""}
    problems, items = check(menu, request, answer, _staples(menu, request))
    if problems:
        return None
    fix = coverage_fix(menu, request, items)
    if fix is not None:
        answer = _apply_fix(answer, fix, menu, request)
        problems, fixed = check(menu, request, answer, _staples(menu, request))
        if not problems:
            items = fixed
    return answer, items


FALLBACK_SUMMARY = (
    "The AI's orders kept failing the checks, so this is the rules' own pick: the cheapest "
    "order that gives everyone a dish they can eat. Refresh to ask the AI again."
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
    menu: Menu, request: TableRequest, answer: dict, problems: list[str], hint=None
) -> Conflict | None:
    """The model's own "nothing fits" answer, with its suggested change if it is sane, plus
    the rules' minimal change so there is always one thing to change."""
    info = answer.get("no_fit") if isinstance(answer, dict) else None
    if not isinstance(info, dict) or answer.get("dishes"):
        return None
    return _conflict(menu, request, info, problems, hint)


def _conflict(menu: Menu, request: TableRequest, info: dict, problems: list[str], hint):
    """What to change when nothing fits. Every figure and claim comes from the rules: the
    model's own wording is dropped (it garbled amounts and called dishes safe for diners the
    rules flag). The suggested budget leaves a little room above the cheapest valid order,
    so the model can actually find an order there."""
    relaxations: list[Relaxation] = []
    suggest = hint.suggest if hint is not None else None
    if suggest is not None and request.budget_per_person < suggest <= 500:
        relaxations.append(_raise_to(suggest))
    ai_price = getattr(hint, "fuller", None)  # rules: TARGET dishes per diner
    if ai_price is None and info.get("change") == "budget":
        ai_price = _budget_for(menu, request, info.get("dish_ids"))
        if ai_price is not None:
            ai_price = rules_hints.suggested_budget(ai_price - 0.5, ai_price)
    if ai_price is not None and request.budget_per_person < ai_price <= 500:
        if not relaxations:
            relaxations.append(_raise_to(ai_price))
        elif ai_price > 1.25 * relaxations[0].new_value:
            relaxations.append(_raise_to(ai_price, fuller=True))
    cur = "$"
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    message = (
        f"At {cur}{request.budget_per_person:.2f} per person (about {cur}{cap:.2f} in menu "
        "prices for the table), no order gives everyone a dish they can eat within their "
        + (
            "allergies, diets and the kept dishes."
            if request.locked_dish_ids
            else "allergies and diets."
        )
    )
    if hint is not None and hint.min_subtotal is not None and hint.min_per_person is not None:
        message += (
            f" The cheapest order that does costs {cur}{hint.min_subtotal:.2f} in menu prices, "
            f"about {cur}{hint.min_per_person:.2f} per person with tax and tip."
        )
    if relaxations:
        price = relaxations[0].new_value
        message += f" {cur}{price:.2f} per person fits it with a little room"
        fuller = next((r.new_value for r in relaxations[1:] if r.kind == "budget"), None)
        message += f"; {cur}{fuller:.2f} buys a fuller meal." if fuller else "."
    return Conflict(code="no_solution", message=message, relaxations=relaxations)


def _raise_to(price: float, fuller: bool = False) -> Relaxation:
    more = " for a fuller meal" if fuller else ""
    return Relaxation(
        kind="budget",
        new_value=price,
        description=f"Raise the budget to ${price:.2f} per person{more} (tax and tip included).",
    )


def _ask(turns: list, schema: dict, menu: Menu, request: TableRequest, client):
    """One model call -> (JSON text, model used). Tests replace this with a fake."""
    return llm.generate_json("plan", system=SYSTEM, turns=turns, schema=schema, client=client)


def plan(
    menu: Menu,
    request: TableRequest,
    client=None,
    cache_path: Path | None = None,
    feedback: refine.Feedback | None = None,
) -> Outcome:
    """A model-chosen order that passed every check, or a conflict that says why not. With
    feedback, the AI revises the current order (no cached answer is reused) and the outcome
    carries a change note whose claims match the code-computed changes."""
    if feedback is not None:
        mild = _already_mild(menu, request, feedback)
        if mild is not None:
            return mild
    outcome = _plan(menu, request, client, cache_path, feedback)
    if feedback is None or outcome.plan is None:
        return outcome
    before = [(c.dish_id, c.quantity) for c in feedback.current]

    def check_goals(out):
        after = [(i.dish_id, i.quantity) for i in out.plan.items]
        d = refine.diff(menu, before, after)
        locked = request.locked_dish_ids
        return d, refine.unmet(feedback.chips, menu, before, after, locked, d)

    d, missed = check_goals(outcome)
    if missed and not outcome.fallback:
        # One retry, told in code-checked words what the revision missed.
        again = feedback.model_copy(update={"fix": refine.missed_text(missed, d)})
        second = _plan(menu, request, client, cache_path, again)
        if second.plan is not None and not second.fallback:
            d2, missed2 = check_goals(second)
            if len(missed2) <= len(missed):
                outcome, d, missed = second, d2, missed2
        outcome.attempts += 1
    ai_note = None if outcome.fallback else (outcome.answer or {}).get("change_note")
    note, from_ai = refine.final_note(ai_note, d)
    if missed:
        after = [(i.dish_id, i.quantity) for i in outcome.plan.items]
        note, from_ai = refine.honest_note(missed, d, menu, after), False
    if not from_ai and ai_note:
        log.info("Change note replaced: %r does not match the changes", str(ai_note)[:120])
    outcome.change_note = note
    outcome.changes = refine.changes_list(d)
    return outcome


def _already_mild(menu: Menu, request: TableRequest, feedback) -> Outcome | None:
    """'Less spicy' alone on an order with nothing above spice 1: the current order stays,
    checked by the rules, with no model call."""
    before = [(c.dish_id, c.quantity) for c in feedback.current]
    if feedback.chips != ["less_spicy"] or feedback.text.strip():
        return None
    if not refine.already_mild(menu, before, request.locked_dish_ids):
        return None
    known = {d.id: d for d in menu.dishes}
    answer = {
        "dishes": [
            {
                "dish_id": i,
                "reason": "",
                "for": edible_by(known[i], request.diners),
                "server_question": "",
            }
            for i, _ in before
            if i in known and known[i].category.value != "staple"
        ],
        "server_questions": [],
    }
    problems, items = check(menu, request, answer, _staples(menu, request))
    if problems:
        return None  # the current order no longer passes: let the AI revise it
    return Outcome(
        _to_plan(menu, request, answer, items),
        None,
        "No AI call: the order is already mild.",
        0,
        change_note=refine.ALREADY_MILD,
        changes=[],
    )


def _plan(menu, request, client=None, cache_path=None, feedback=None) -> Outcome:
    cache_path = cache_path or CACHE_PATH
    if not enabled() and client is None:
        return _unavailable(
            "Recommendations need an AI model, and none is configured on this server. "
            "Set OPENROUTER_API_KEY or GEMINI_API_KEY (see the README)."
        )
    try:
        hint = rules_hints.analyse(menu, request)
    except Exception:  # hints are optional help, never a reason to fail
        log.warning("Rules hints failed", exc_info=True)
        hint = None
    payload = brief(menu, request, hint)
    if feedback is not None:  # part of the payload, so part of the cache key
        payload["current_order"] = [
            {"id": c.dish_id, "quantity": c.quantity} for c in feedback.current
        ]
        payload["feedback"] = feedback.asks()
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
    if hint is not None and hint.feasible is False:
        # The rules proved nothing fits (QA r6 #4): say what to change without a model call.
        return Outcome(
            None,
            _conflict(menu, request, {}, [], hint),
            "No order fits; the rules worked out what to change.",
            0,
            [],
        )
    staples = _staples(menu, request)
    model_id = llm.model("plan")
    key = _key(payload, model_id)
    stored = None if feedback is not None else _cache_get(key, cache_path)
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
    if feedback is not None:
        schema["properties"]["change_note"] = {"type": "string"}
    intro = refine.REVISE + "\n\n" if feedback is not None else ""
    turns = [llm.Turn("user", intro + "Brief:\n" + json.dumps(payload, ensure_ascii=False))]
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
        gave_up = isinstance(answer, dict) and not answer.get("dishes") and answer.get("no_fit")
        if gave_up and not (hint and hint.feasible):
            no_fit = _no_fit(menu, request, answer, history[-1] if history else [], hint)
            history.append([])
            return Outcome(None, no_fit, "The AI found no order that fits.", attempt + 1, history)
        if gave_up:
            problems, items = (
                ["You returned no_fit, but an order that meets every rule exists."],
                [],
            )
        else:
            problems, items = check(menu, request, answer, staples)
        history.append(problems)
        if problems and hint is not None and hint.feasible is False:
            # Nothing can fit: no point retrying; say what to change.
            info = answer.get("no_fit") if isinstance(answer, dict) else None
            reason = "No order that everyone can eat fits this budget."
            return Outcome(
                None,
                _conflict(
                    menu,
                    request,
                    info if isinstance(info, dict) else {"reason": reason},
                    problems,
                    hint,
                ),
                "No order fits; the rules worked out what to change.",
                attempt + 1,
                history,
            )
        if not problems:
            calls = attempt + 1
            fix = coverage_fix(menu, request, items) if COVERAGE_NUDGE else None
            note = ""
            if fix is not None:
                # QA r5 #8: a valid in-budget change serves a least-served diner better.
                # Ask once with that hint; if the answer is not at least as even, make the
                # change in code.
                retry_turns = [
                    *turns,
                    llm.Turn("model", text or ""),
                    llm.Turn("user", _fix_text(menu, request, fix)),
                ]
                calls += 1
                better = None
                try:
                    text2, used2 = _ask(retry_turns, schema, menu, request, client)
                    answer2 = json.loads(text2 or "")
                    problems2, items2 = check(menu, request, answer2, staples)
                    history.append(problems2)
                    if not problems2 and spread(menu, request, items2) >= spread(
                        menu, request, fix.items
                    ):
                        better = (answer2, items2, used2)
                except Exception as exc:  # noqa: BLE001 - the code's fix still applies
                    log.warning("Coverage retry failed: %s", type(exc).__name__)
                if better is not None:
                    answer, items, used = better
                    note = " The AI evened out who can eat what when asked."
                else:
                    answer = _apply_fix(answer, fix, menu, request)
                    problems, items = check(menu, request, answer, staples)
                    note = " The rules swapped one dish so the least-served diner has more."
            _cache_put(key, {"model": used, "answer": answer}, cache_path)
            retried = f" after {attempt} correction{'s' * (attempt > 1)}" if attempt else ""
            return Outcome(
                _to_plan(menu, request, answer, items),
                None,
                f"AI plan by {llm.label(used)}, checked by the rules{retried}.{note}",
                calls,
                history,
                answer=answer,
            )
        turns += [
            llm.Turn("model", text or ""),
            llm.Turn(
                "user",
                "That order breaks these rules:\n- "
                + "\n- ".join(problems + _hint_text(menu, request, hint))
                + "\nReturn a corrected order in the same format. If no order can meet the "
                "rules, return no dishes and fill no_fit with the reason and one change.",
            ),
        ]
    last = history[-1] if history else []
    if hint is not None and hint.feasible is False:
        info = answer.get("no_fit") if isinstance(answer, dict) else None
        conflict = _conflict(menu, request, info if isinstance(info, dict) else {}, last, hint)
        return Outcome(None, conflict, "No order fits.", 1 + MAX_RETRIES, history)
    if hint is not None and hint.feasible:
        built = fallback(menu, request)
        if built is not None:
            answer, items = built
            plan_ = _to_plan(menu, request, answer, items)
            checks = [
                Check(
                    name="ai",
                    passed=True,
                    detail="The AI's orders failed the checks, so the rules built this one.",
                ),
                *plan_.checks[1:],
            ]
            return Outcome(
                plan_.model_copy(update={"summary": FALLBACK_SUMMARY, "checks": checks}),
                None,
                f"The AI's {1 + MAX_RETRIES} orders failed the checks ("
                + "; ".join(last[:2])
                + "), so the rules built the cheapest valid order.",
                1 + MAX_RETRIES,
                history,
                fallback=True,
            )
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
