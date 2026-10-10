"""Independent whole-order validation, also used after swaps and explanations.

Hard rules only: dishes on the menu, kept/removed dishes, allergies and diets, the budget
with tax and tip, and every diner able to eat at least one chosen dish. How many dishes to
order is the AI's call; there is no portion or per-person dish-count rule (2026-10-09).
"""

import re
from dataclasses import asdict

from michelin.plan.budget import cents, totals
from michelin.plan.edibility import assessment, edible_by, open_questions
from michelin.schemas import Menu, PlanItem, TableRequest


def staple_required(menu: Menu, request: TableRequest) -> bool:
    """Rice is added only when the menu has a staple everyone can eat. Many real menus (dim
    sum, a page of a longer menu) print no plain rice; then no staple is required."""
    if not request.include_staple:
        return False
    excluded = set(request.excluded_dish_ids)
    return any(
        d.category.value == "staple"
        and d.id not in excluded
        and d.price is not None
        and len(edible_by(d, request.diners)) == request.n_diners
        for d in menu.dishes
    )


def family_repeats(menu: Menu, request: TableRequest, dish_ids) -> list[str]:
    """Versions of one menu line ("Kung Pao (Chicken)", "Kung Pao (Tofu)") are one dish: the
    AI orders a second version only when each feeds someone the other cannot (tofu for the
    vegetarian, chicken for the shellfish-allergic friend), and never three. The user's own
    picks are not limited by this."""
    known = {d.id: d for d in menu.dishes}
    groups: dict[str, list] = {}
    for i in dict.fromkeys(dish_ids):
        d = known.get(i)
        if d is not None and d.family_id:
            groups.setdefault(d.family_id, []).append(d)
    out = []
    for family, dishes in groups.items():
        if len(dishes) < 2:
            continue
        name = dishes[0].family_name or family
        both = " and ".join(d.name_en or d.id for d in dishes)
        if len(dishes) > 2:
            out.append(f"{both} are {len(dishes)} versions of {name}; order at most two.")
            continue
        a, b = (set(edible_by(d, request.diners)) for d in dishes)
        if a <= b or b <= a:
            out.append(
                f"{both} are two versions of {name}, and one feeds nobody the other doesn't; "
                "order just one of them."
            )
    return out


_STAPLE_KINDS = {
    "fried rice": r"fried rice|炒饭",
    "lo mein": r"lo mein|捞面",
    "chow mein": r"chow mein|炒面",
    "chow fun": r"chow fun|mei fun|炒河粉|炒米粉",
}


def staple_kind(dish) -> str | None:
    """'Pineapple Fried Rice' and 'Yang Chow Fried Rice' are both fried rice."""
    text = f"{dish.family_name or ''} {dish.name_en or ''} {dish.name_zh or ''}".lower()
    return next((k for k, pat in _STAPLE_KINDS.items() if re.search(pat, text)), None)


def staple_repeats(menu: Menu, request: TableRequest, dish_ids) -> list[str]:
    """Two fried rices (QA r8) read as a repetitive order and crowd out a dish for someone
    else: a second one of the same kind only when it feeds someone the first cannot."""
    known = {d.id: d for d in menu.dishes}
    groups: dict[str, list] = {}
    for i in dict.fromkeys(dish_ids):
        d = known.get(i)
        kind = staple_kind(d) if d is not None else None
        if kind:
            groups.setdefault(kind, []).append(d)
    out = []
    for kind, dishes in groups.items():
        fams = {d.family_id for d in dishes}
        if len(dishes) < 2 or (len(fams) == 1 and None not in fams):
            continue  # versions of one line are handled by family_repeats
        sets = [set(edible_by(d, request.diners)) for d in dishes]
        union = set().union(*sets)
        others = [set().union(*(s for j, s in enumerate(sets) if j != k)) for k in range(len(sets))]
        top = max(d.price or 0 for d in dishes)
        chosen = set(dish_ids)
        alternative = any(
            d.id not in chosen
            and d.id not in set(request.excluded_dish_ids)
            and d.price is not None
            and d.price <= top
            and d.category.value != "staple"
            and staple_kind(d) != kind
            and edible_by(d, request.diners)
            for d in menu.dishes
        )
        if alternative and any(o >= union for o in others):
            both = " and ".join(d.name_en or d.id for d in dishes)
            out.append(
                f"{both} are both {kind}, and one feeds nobody the other doesn't; keep one and "
                "pick a different kind of dish, ideally one the least-served diner can eat."
            )
    return out


def validate_order(menu: Menu, request: TableRequest, items: list[PlanItem]) -> dict:
    reasons = []

    def issue(code, detail):
        reasons.append({"code": code, "detail": detail})

    ids = [i.dish_id for i in items]
    known = {d.id: d for d in menu.dishes}
    if not menu.verified:
        issue("unverified_menu", "Review the menu first.")
    if menu.currency != "USD":
        issue("unsupported_currency", "Only USD arithmetic is supported.")
    if len(known) != len(menu.dishes) or len(ids) != len(set(ids)):
        issue("duplicate_dish", "Use unique dish IDs and one line per dish.")
    if set(ids) - known.keys():
        issue("unknown_dish", "Order references dishes outside this menu.")
    if set(request.locked_dish_ids) - set(ids):
        issue("missing_locked_dish", "Every kept dish must remain in the order.")
    if set(request.excluded_dish_ids) & set(ids):
        issue("excluded_dish", "An excluded dish is in the order.")
    selected = [(known[i.dish_id], i.quantity) for i in items if i.dish_id in known]
    missing_price = any(d.price is None for d, _ in selected)
    if missing_price:
        issue("missing_price", "Obtain every selected dish price; missing prices are not zero.")
    amounts = None
    if not missing_price:
        subtotal = sum(cents(d.price) * q for d, q in selected) / 100
        amounts = asdict(totals(subtotal, request.n_diners, request.tax_rate, request.tip_rate))
        if cents(amounts["total"]) > cents(request.all_in_budget):
            issue("over_budget", "Rounded tax and pre-tax tip exceed the strict table budget.")
    evaluations = {d.id: {p.id: assessment(d, p) for p in request.diners} for d, _ in selected}
    for d, _ in selected:
        if not edible_by(d, request.diners):
            issue("no_eligible_diner", f"{d.id}: no diner has validated eligibility.")
    need_staple = staple_required(menu, request)
    for p in request.diners:
        coverage = sum(
            1 for d, _ in selected if d.category.value != "staple" and p.id in edible_by(d, [p])
        )
        if coverage < 1:
            issue("insufficient_coverage", f"{p.id}: {coverage} distinct validated dishes.")
        staples = sum(
            q for d, q in selected if d.category.value == "staple" and p.id in edible_by(d, [p])
        )
        if need_staple and staples < request.n_diners:
            issue("insufficient_staples", f"{p.id}: need a shared pool of one staple per diner.")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "totals": amounts,
        "evaluations": evaluations,
        "confirm_with_staff": list(
            dict.fromkeys(q for d, _ in selected for q in open_questions(d, request.diners))
        ),
        "assumptions": [
            "USD; tax and tip rounded separately, tip on pre-tax subtotal.",
            "No unlisted fees included; confirm charges and cross-contact with staff.",
        ],
    }
