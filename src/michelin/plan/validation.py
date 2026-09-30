"""Independent whole-order validation, also used after swaps and explanations.

Counts unique non-staple dishes for coverage; quantities multiply price/portion units.
No inference of serving adequacy, ingredients, or accommodation requests.
"""

from dataclasses import asdict

from michelin.plan.budget import cents, totals
from michelin.plan.edibility import assessment, edible_by, open_questions
from michelin.plan.portions import required_range, units
from michelin.schemas import Menu, PlanItem, TableRequest


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
        if cents(amounts["total"]) > cents(request.budget_per_person) * request.n_diners:
            issue("over_budget", "Rounded tax and pre-tax tip exceed the strict table budget.")
    evaluations = {d.id: {p.id: assessment(d, p) for p in request.diners} for d, _ in selected}
    for d, _ in selected:
        if not edible_by(d, request.diners):
            issue("no_eligible_diner", f"{d.id}: no diner has validated eligibility.")
    for p in request.diners:
        coverage = sum(
            1 for d, _ in selected if d.category.value != "staple" and p.id in edible_by(d, [p])
        )
        if coverage < request.min_dishes_per_person:
            issue("insufficient_coverage", f"{p.id}: {coverage} distinct validated dishes.")
        staples = sum(
            q for d, q in selected if d.category.value == "staple" and p.id in edible_by(d, [p])
        )
        if request.include_staple and staples < request.n_diners:
            issue("insufficient_staples", f"{p.id}: need a shared pool of one staple per diner.")
    lo, hi = required_range(request.n_diners)
    portion_cents = sum(round(units(d) * 100) * q for d, q in selected)
    portion = portion_cents / 100
    if not round(lo * 100) <= portion_cents <= round(hi * 100):
        issue("portion_estimate", f"{portion:g} estimated units; expected {lo:g}–{hi:g}.")
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
            "Portion units are estimates, not a people-fed guarantee.",
        ],
    }
