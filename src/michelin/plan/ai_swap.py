"""AI single-dish swap: replace one dish in a checked plan, keep every other dish as is.

One model call (same provider and model as the planner; OpenRouter `google/gemini-3.5-flash-lite`
when `OPENROUTER_API_KEY` is set) gets the current order, the dish to replace, the diners'
allergies and diets, the money left (menu prices and all-in, tax and tip included) and the
removed dishes. It answers one replacement dish id and a short reason. The rules then check
the whole new order exactly like a plan: dish on the menu, not already ordered, not removed,
allergies and diets, budget with tax and tip, every diner still able to eat a non-staple
dish. A failing answer is retried once with the reason; after that the caller offers the
manual pick from the menu.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from michelin import llm
from michelin.plan import llm_planner
from michelin.plan.budget import cents, subtotal_cap, totals
from michelin.plan.edibility import assessment, edible_by, risks
from michelin.plan.validation import family_repeats, validate_order
from michelin.schemas import PREFERENCE_TEXT, Menu, Plan, PlanItem, TableRequest

log = logging.getLogger(__name__)
MAX_RETRIES = 1

SYSTEM = """You replace ONE dish in a shared, family-style order at a Chinese restaurant.
Every other dish stays exactly as it is. Pick one replacement from "candidates" (dish ids
only, never one already ordered or removed). Hard rules: it must fit the money left
("menu_price_left" is the most its menu price can be; tax and tip are added on top), and
it should suit the diners' allergies and diets ("ok_for" lists who can eat it; never pick a
dish nobody can eat). After the swap every diner must still have at least one non-rice dish
they can eat. Prefer, in order: the dish that the MOST diners can eat (longest "ok_for";
all diners is best), then one the least-served diners can eat (lowest
"dishes_they_can_eat_after_swap"), a price close to the replaced dish (cheaper is fine), and a dish that does not repeat the main ingredient, category
or cooking method of the dishes that stay. Follow each diner's "notes" (tastes in their own
words, e.g. "no spicy food"). Return "dish_id", "reason": ONE short clause (under 10 words), naming only diners in
its "ok_for", e.g. "Kevin can eat it" or "adds a vegetable", and
"server_question": ONE plain sentence a diner would say to the server about the dish's
"risks", naming the dish, the concern and who it is for, e.g. "Is there any pork or lard in
the scallion pancake, since David is vegetarian?" (no lists or semicolons), or "" if none.
State only the allergies and diets the brief lists for each diner."""


@dataclass
class SwapOutcome:
    plan: Plan | None
    message: str  # shown to the user: the reason, or why no swap passed the checks
    new_dish_id: str | None = None
    reason: str | None = None
    attempts: int = 0
    history: list[list[str]] = field(default_factory=list)
    model: str | None = None


def _name(d) -> str:
    return d.name_en or d.name_zh or d.id


def picked(request: TableRequest, new_id: str) -> TableRequest:
    """The user explicitly chose new_id: it is no longer excluded."""
    return request.model_copy(
        update={"excluded_dish_ids": [i for i in request.excluded_dish_ids if i != new_id]}
    )


def _swap_request(request: TableRequest, old_id: str) -> TableRequest:
    """The replaced dish counts as removed; it is no longer kept."""
    return request.model_copy(
        update={
            "locked_dish_ids": [i for i in request.locked_dish_ids if i != old_id],
            "excluded_dish_ids": list(dict.fromkeys([*request.excluded_dish_ids, old_id])),
        }
    )


def brief(menu: Menu, request: TableRequest, plan: Plan, old_id: str) -> dict:
    known = {d.id: d for d in menu.dishes}
    others = [i for i in plan.items if i.dish_id != old_id]
    ordered = {i.dish_id for i in plan.items}
    excluded = set(request.excluded_dish_ids)
    spent = sum(cents(known[i.dish_id].price) * i.quantity for i in others) / 100
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    now = totals(spent, request.n_diners, request.tax_rate, request.tip_rate)
    old = known[old_id]
    candidates = []
    for d in menu.dishes:
        if d.id in ordered or d.id in excluded or d.category.value == "staple" or d.price is None:
            continue
        ok = edible_by(d, request.diners)
        if not ok:
            continue
        if family_repeats(menu, request, [*(i.dish_id for i in others), d.id]):
            continue  # a second version of a dish that stays, feeding nobody new
        row = {"id": d.id, "name": _name(d), "price": d.price, "category": d.category.value}
        row["ok_for"] = ok
        if d.spice_level is not None:
            row["spice"] = d.spice_level
        if d.cooking_method:
            row["method"] = d.cooking_method
        main = [i.name for i in d.main_ingredients if i.tier.value == "menu"]
        if main:
            row["ingredients"] = main[:6]
        flagged = risks(d, request.diners)
        if flagged:
            row["risks"] = [
                r.about + (f" (matters for {', '.join(r.names)})" if r.names else "")
                for r in flagged
            ][:5]
        candidates.append(row)
    diners = []
    for p in request.diners:
        row = {"id": p.id, "name": p.name}
        for key in ("allergies", "diets"):
            if getattr(p, key):
                row[key] = [llm_planner.humanize(getattr(x, "value", x)) for x in getattr(p, key)]
        if p.other_allergies:  # hard, in their own words; "ok_for" already applies them
            row["other_allergies"] = list(p.other_allergies)
        if p.other_diets:
            row["other_diets"] = list(p.other_diets)
        tastes = [PREFERENCE_TEXT[x] for x in p.preferences]
        if p.notes:
            tastes.append(p.notes)
        if tastes:
            row["notes"] = "; ".join(tastes)
        # How many of the dishes that stay this diner can eat (rice aside): favour the
        # least-served diners when choosing.
        row["dishes_they_can_eat_after_swap"] = sum(
            p.id in edible_by(known[i.dish_id], request.diners)
            for i in others
            if known[i.dish_id].category.value != "staple"
        )
        diners.append(row)
    return {
        "replace": {
            "id": old_id,
            "name": _name(old),
            "price": old.price,
            "category": old.category.value,
            "ok_for": edible_by(old, request.diners),
        },
        "order_stays": [
            {
                "id": i.dish_id,
                "name": _name(known[i.dish_id]),
                "quantity": i.quantity,
                "price": known[i.dish_id].price,
                "category": known[i.dish_id].category.value,
                "ok_for": edible_by(known[i.dish_id], request.diners),
            }
            for i in others
        ],
        "diners": diners,
        "removed": sorted(excluded),
        "budget_per_person_all_in": request.budget_per_person,
        "tax_rate": request.tax_rate,
        "tip_rate": request.tip_rate,
        "menu_price_left": round(cap - spent, 2),
        "all_in_left_for_table": round(request.all_in_budget - now.total, 2),
        "candidates": candidates,
    }


def _schema(ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "dish_id": {"type": "string", "enum": ids},
            "reason": {"type": "string"},
            "server_question": {"type": "string"},
        },
        "required": ["dish_id", "reason", "server_question"],
    }


def check(
    menu: Menu, request: TableRequest, plan: Plan, old_id: str | None, answer, family=True
) -> tuple[list, list]:
    """(problems, items): the whole new order through the same hard checks as a plan.
    old_id None adds the dish (before the rice) instead of replacing one. family=False for
    the user's own pick: they may want two versions of one dish."""
    known = {d.id: d for d in menu.dishes}
    new_id = answer.get("dish_id") if isinstance(answer, dict) else None
    # Messages name dishes, never ids: the user sees them when a swap is refused.
    if new_id not in known:
        return ["that dish is not on this menu; pick one from the candidates."], []
    label = _name(known[new_id])
    if new_id == old_id or new_id in {i.dish_id for i in plan.items}:
        return [f"{label} is already in the order; pick a dish that is not."], []
    if known[new_id].category.value == "staple":
        return [f"{label} is rice, which is added automatically; pick a shared dish."], []
    if new_id in request.excluded_dish_ids:
        return [f"{label} was taken out of this order earlier; pick another dish."], []
    items = [
        PlanItem(dish_id=new_id, quantity=1)
        if i.dish_id == old_id
        else PlanItem(dish_id=i.dish_id, quantity=i.quantity)
        for i in plan.items
    ]
    if old_id is None:
        at = next(
            (n for n, i in enumerate(items) if known[i.dish_id].category.value == "staple"),
            len(items),
        )
        items.insert(at, PlanItem(dish_id=new_id, quantity=1))
    names = {p.id: p.name for p in request.diners}
    problems = family_repeats(menu, request, [i.dish_id for i in items]) if family else []
    for reason in validate_order(menu, request, items)["reasons"]:
        detail = reason["detail"]
        if reason["code"] == "insufficient_coverage":
            pid = detail.split(":")[0]
            detail = f"{names.get(pid, pid)} would have nothing left to eat."
        elif reason["code"] == "over_budget":
            subtotal = sum(cents(known[i.dish_id].price) * i.quantity for i in items) / 100
            t = totals(subtotal, request.n_diners, request.tax_rate, request.tip_rate)
            over = max(t.total - request.all_in_budget, 0.01)
            detail = f"it would put the table ${over:.2f} over budget (with tax and tip)."
        elif reason["code"] == "no_eligible_diner":
            detail = "nobody at the table can eat it."
        problems.append(_named(detail, known, names))
    return list(dict.fromkeys(problems)), items


def _named(text: str, known: dict, names: dict) -> str:
    """Dish and diner ids in a rule's detail replaced by their names (QA r6 Q-2)."""
    for i in sorted([*known, *names], key=len, reverse=True):
        if i in text:
            name = _name(known[i]) if i in known else (names[i] or i)
            text = re.sub(rf"(?<![\w]){re.escape(i)}(?![\w])", name, text)
    return text


def _price_note(menu: Menu, old_id: str | None, new_id: str) -> str:
    if old_id is None:
        return f"${menu.dish(new_id).price:.2f} more"
    diff = (cents(menu.dish(new_id).price) - cents(menu.dish(old_id).price)) / 100
    if abs(diff) < 0.005:
        return "same price"
    return f"${abs(diff):.2f} {'cheaper' if diff < 0 else 'more'}"


def _line(
    menu: Menu, request: TableRequest, old_id: str | None, new_id: str, why: str | None
) -> str:
    """'Swapped to X, Kevin can eat it, $3.00 cheaper.' The price part is always computed."""
    new = menu.dish(new_id)
    ok = set(edible_by(new, request.diners))
    everyone = re.compile(
        r"\b(everyone|everybody|all (?:diners|diets|of you)|whole table)\b", re.IGNORECASE
    )
    if why and len(ok) < len(request.diners) and everyone.search(why):
        why = None  # the model claimed a dish suits everyone when the rules say it does not
    if why and any(
        (p.id not in ok or assessment(new, p)["status"] != "validated_under_known_data")
        and p.name
        and re.search(rf"\b{re.escape(p.name)}\b", why, re.IGNORECASE)
        for p in request.diners
    ):
        # It named someone the rules say cannot eat this dish, or can only if the server
        # confirms ("especially Cai" on a dish that may hide Cai's allergen).
        why = None
    if why and (len(why.split()) > 10 or re.search(r"[;:]|\$\d", why)):
        why = None  # one short clause only; the price part is computed below
    if not why:
        who = [p.name for p in request.diners if p.id in ok]
        why = (
            "everyone can eat it"
            if len(who) == len(request.diners)
            else f"{_join_names(who)} can eat it"
        )
    why = why.strip().rstrip(".")
    first = why.split(" ", 1)[0].rstrip(",")
    if first not in {p.name for p in request.diners}:  # keep names capitalised
        why = why[:1].lower() + why[1:]
    done = "Added" if old_id is None else "Swapped to"
    return f"{done} {_name(new)}, {why}, {_price_note(menu, old_id, new_id)}."


def _join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _score(menu: Menu, request: TableRequest, plan: Plan, old_id: str, new_id: str) -> tuple:
    """How evenly the order serves the table after swapping in new_id: the dish counts per
    diner least-served first (QA r5 #8), then whether the new dish helps a diner who has the
    fewest dishes now, then how many diners can eat it."""
    after = [i for i in plan.items if i.dish_id != old_id]
    after.append(PlanItem(dish_id=new_id, quantity=1))
    now = llm_planner.counts(menu, request, plan.items)
    ok = edible_by(menu.dish(new_id), request.diners)
    neediest = min((now[p] for p in ok), default=99)
    return (llm_planner.spread(menu, request, after), -neediest, len(ok))


def _better(
    menu: Menu, request: TableRequest, plan: Plan, old_id: str, new_id: str, payload: dict
) -> list[dict]:
    """Candidates that pass the same checks (budget included) and serve the table more
    evenly than new_id: the least-served diner gets more, or more diners can eat it. Best
    first, then closest in price. No price window: a cheaper dish that serves the
    least-served diner is better. Empty when the model's pick is already the best."""
    got = _score(menu, request, plan, old_id, new_id)
    ref = menu.dish(old_id).price or 0
    out = []
    for c in payload["candidates"]:
        score = _score(menu, request, plan, old_id, c["id"])
        if score <= got:
            continue
        if not check(menu, request, plan, old_id, {"dish_id": c["id"]})[0]:
            out.append((score, c))
    out.sort(key=lambda x: abs((x[1]["price"] or 0) - ref))
    out.sort(key=lambda x: x[0], reverse=True)  # stable: best score first, then nearest price
    return [c for _, c in out[:4]]


def manual(
    menu: Menu, request: TableRequest, plan: Plan, old_id: str | None, new_id: str
) -> SwapOutcome:
    """The user's own pick: no model call, same hard checks, only that dish changes.
    old_id None adds the dish; nothing else in the order moves. Picking a dish that was
    removed or swapped out earlier brings it back (QA r6 S-3)."""
    request = picked(request, new_id)
    if old_id is not None:
        request = _swap_request(request, old_id)
    problems, items = check(menu, request, plan, old_id, {"dish_id": new_id}, family=False)
    if problems:
        name = _name(menu.dish(new_id)) if new_id in {d.id for d in menu.dishes} else new_id
        what = "be added" if old_id is None else f"replace {_name(menu.dish(old_id))}"
        return SwapOutcome(None, f"{name} can't {what}: " + " ".join(problems))
    line = _line(menu, request, old_id, new_id, None)
    answer = {"dish_id": new_id, "reason": line, "server_question": ""}
    new_plan = _to_plan(menu, request, plan, old_id, answer, items)
    return SwapOutcome(new_plan, line, new_id, line, 0)


def _to_plan(
    menu: Menu, request: TableRequest, plan: Plan, old_id: str | None, answer, items
) -> Plan:
    """The new plan: other dishes keep their reasons and questions; totals are recomputed."""
    new_id = answer["dish_id"]
    rows = []
    for i in plan.items:
        if i.dish_id == old_id:
            rows.append(
                {
                    "dish_id": new_id,
                    "reason": str(answer.get("reason") or "")[:200],
                    "server_question": str(answer.get("server_question") or ""),
                }
            )
        elif menu.dish(i.dish_id).category.value != "staple":
            rows.append(
                {
                    "dish_id": i.dish_id,
                    "reason": i.reason or "",
                    "server_question": i.server_question or "",
                }
            )
    if old_id is None:
        rows.append(
            {
                "dish_id": new_id,
                "reason": str(answer.get("reason") or "")[:200],
                "server_question": "",
            }
        )
    out = llm_planner._to_plan(menu, request, {"dishes": rows, "summary": plan.summary}, items)
    kept_reasons = {i.dish_id: i.reason for i in plan.items if i.dish_id != old_id}
    return out.model_copy(
        update={
            "items": [
                i.model_copy(update={"reason": kept_reasons.get(i.dish_id) or i.reason})
                for i in out.items
            ],
            "summary": _summary_after(menu, request, plan, old_id, out),
        }
    )


def _summary_after(menu: Menu, request: TableRequest, plan: Plan, old_id, out: Plan) -> str:
    """Keep the plan's summary when it still holds (same dish count, does not name the
    replaced dish); otherwise a plain rule-written line about the new order."""
    old = plan.summary or ""
    shared = sum(1 for i in out.items if menu.dish(i.dish_id).category.value != "staple")
    gone = _name(menu.dish(old_id)).lower() if old_id else None
    if (
        old
        and old_id is not None
        and gone not in old.lower()
        and llm_planner._summary(old, len(out.items)) is not None
    ):
        return old
    fed = {p for i in out.items for p in i.edible_by}
    who = "everyone has" if len(fed) >= len(request.diners) else "not everyone has"
    return (
        f"{shared} shared dish{'es' if shared != 1 else ''} plus rice, "
        f"${out.per_person:.2f} per person with tax and tip; {who} something to eat."
    )


def _ask(turns: list, schema: dict, client):
    """One model call -> (JSON text, model used). Tests replace this with a fake."""
    return llm.generate_json("plan", system=SYSTEM, turns=turns, schema=schema, client=client)


def swap(menu: Menu, request: TableRequest, plan: Plan, old_id: str, client=None) -> SwapOutcome:
    request = _swap_request(request, old_id)
    payload = brief(menu, request, plan, old_id)
    old_name = payload["replace"]["name"]
    manual = "Pick a replacement from the menu instead."
    if not llm_planner.enabled() and client is None:
        return SwapOutcome(None, f"No AI model is configured on this server. {manual}")
    if not payload["candidates"]:
        return SwapOutcome(None, f"No other dish on this menu can replace {old_name}. {manual}")
    schema = _schema([c["id"] for c in payload["candidates"]])
    turns = [llm.Turn("user", "Brief:\n" + json.dumps(payload, ensure_ascii=False))]
    history: list[list[str]] = []
    used = None
    nudged, first = False, None
    for attempt in range(1 + MAX_RETRIES):
        try:
            text, used = _ask(turns, schema, client)
        except Exception as exc:  # noqa: BLE001 - network, quota, provider errors
            log.warning("AI swap failed: %s: %s", type(exc).__name__, str(exc)[:300])
            return SwapOutcome(
                None, f"The AI did not answer. {manual}", attempts=attempt, history=history
            )
        try:
            answer = json.loads(text or "")
        except ValueError:
            answer = {}
        problems, items = check(menu, request, plan, old_id, answer)
        history.append(problems)
        better = (
            []
            if problems or nudged
            else _better(menu, request, plan, old_id, answer["dish_id"], payload)
        )
        if better and attempt < MAX_RETRIES:
            nudged, first = True, (answer, items)
            turns += [
                llm.Turn("model", text or ""),
                llm.Turn(
                    "user",
                    f"{answer['dish_id']} suits only "
                    f"{len(edible_by(menu.dish(answer['dish_id']), request.diners))} of "
                    f"{request.n_diners} diners and does not help the least-served diners "
                    "(see dishes_they_can_eat_after_swap). These dishes fit the budget and "
                    "suit more or serve the least-served: "
                    + ", ".join(f"{c['id']} (ok_for {', '.join(c['ok_for'])})" for c in better)
                    + ". Pick the best of them in the same format.",
                ),
            ]
            continue
        if first is not None:

            def covers(a):
                return _score(menu, request, plan, old_id, a["dish_id"])

            if problems or covers(first[0]) > covers(answer):
                problems, (answer, items) = [], first  # the nudge did not help; first pick stands
        if not problems:
            new_id = answer["dish_id"]
            reason = _line(menu, request, old_id, new_id, str(answer.get("reason") or "")[:120])
            answer = {**answer, "reason": reason}
            new_plan = _to_plan(menu, request, plan, old_id, answer, items)
            return SwapOutcome(
                new_plan,
                reason,
                new_id,
                reason,
                attempt + 1,
                history,
                used,
            )
        turns += [
            llm.Turn("model", text or ""),
            llm.Turn(
                "user",
                "That swap breaks these rules:\n- "
                + "\n- ".join(problems)
                + "\nPick a different replacement in the same format.",
            ),
        ]
    return SwapOutcome(
        None,
        f"The AI could not find a replacement for {old_name} that passes the checks "
        f"({'; '.join(history[-1][:2])}). {manual}",
        attempts=1 + MAX_RETRIES,
        history=history,
        model=used,
    )
