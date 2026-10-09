"""Deterministic hints for the AI planner. These never pick the order shown to the user.

They answer yes/no and "how much" questions from the menu and the diners' allergies and
diets, so the app can always say what to change when nothing fits ("Raise to $X per
person") and can steer the model's retries with facts instead of guesses. The dishes in a
plan still come only from the model (see llm_planner).

The hard rules are the ones in validation.validate_order: dishes on the menu, kept and
removed dishes, allergies and diets, the budget with tax and tip, rice for everyone, and
every diner able to eat at least one chosen dish. There is no portion or dish-count rule.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from michelin.plan.budget import cents, subtotal_cap, totals
from michelin.plan.edibility import edible_by
from michelin.plan.validation import validate_order
from michelin.schemas import Menu, PlanItem, TableRequest


@dataclass
class Hints:
    feasible: bool | None  # a valid order exists at the current budget (None: search timed out)
    min_budget: float | None  # smallest per-person all-in budget (next 50 cents) that fits
    must_include: dict[str, list[str]]  # diner id -> their only option(s) on this menu
    suggest: float | None = None  # a budget to offer: the minimum plus ~$1.50-2.50 a person
    min_subtotal: float | None = None  # menu prices of the cheapest valid order
    min_per_person: float | None = None  # that order per person, with tax and tip
    fuller: float | None = None  # a budget for TARGET dishes per diner (same from any budget)


SLACK = 1.5  # headroom per person in a suggested budget, so a model's order has room
TARGET = 2  # dishes each diner can eat in a "fuller meal"


def fuller_budget(menu: Menu, request: TableRequest, order) -> float | None:
    """The per-person budget for a fuller meal: the cheapest order plus the cheapest dishes
    for whoever has fewest, until everyone has TARGET dishes they can eat (or the menu runs
    out). It depends on the table and menu only, never on the budget the user started at."""
    if not order:
        return None
    ids = {p.id for p in request.diners}
    excluded = set(request.excluded_dish_ids)
    chosen = list(order)
    have = {d.id for d, _ in chosen}
    count = {p: 0 for p in ids}
    for d, _ in chosen:
        if d.category.value != "staple":
            for p in edible_by(d, request.diners):
                count[p] += 1
    pool = sorted(
        (
            d
            for d in menu.dishes
            if d.id not in excluded | have and d.price is not None and d.category.value != "staple"
        ),
        key=lambda d: d.price,
    )
    eats = {d.id: set(edible_by(d, request.diners)) for d in pool}
    while count and min(count.values()) < TARGET:
        low = min(count.values())
        neediest = {p for p, c in count.items() if c == low}
        pick = next((d for d in pool if eats[d.id] & neediest), None)
        if pick is None:
            break
        pool.remove(pick)
        chosen.append((pick, 1))
        for p in eats[pick.id]:
            count[p] += 1
    if len(chosen) == len(order):
        return None
    subtotal = sum(cents(d.price) * q for d, q in chosen) / 100
    t = totals(subtotal, request.n_diners, request.tax_rate, request.tip_rate)
    return suggested_budget(t.total / request.n_diners, None)


def suggested_budget(per_person: float, floor: float | None) -> float:
    """The cheapest order's per-person cost plus at least SLACK, rounded up to a dollar."""
    price = float(math.ceil(per_person + SLACK - 1e-9))
    return max(price, floor or 0.0)


def cheapest_order(menu: Menu, request: TableRequest, deadline_s: float = 1.5):
    """(the cheapest valid order ignoring the budget as [(dish, qty)], proven minimal).

    It is a small set cover: every diner needs one dish they can eat. Branch and bound over
    dishes sorted by price; nothing here is shown to the user, only its price is used."""
    n = request.n_diners
    excluded, locked = set(request.excluded_dish_ids), set(request.locked_dish_ids)
    available = [d for d in menu.dishes if d.id not in excluded and d.price is not None]
    ok = {d.id: set(edible_by(d, request.diners)) for d in available}
    if locked - ok.keys() or any(not ok[i] for i in locked):
        return None, True
    staples = [d for d in available if d.category.value == "staple"]
    kept = [d for d in staples if d.id in locked]
    everyone = [d for d in staples if len(ok[d.id]) == n]
    base = kept or ([min(everyone, key=lambda d: d.price)] if everyone else [])
    # No staple everyone can eat (e.g. a dim sum menu without plain rice): none is required.
    if not request.include_staple and not kept:
        base = []
    forced = [d for d in available if d.id in locked and d.category.value != "staple"]
    choices = sorted(
        (d for d in available if d.category.value != "staple" and ok[d.id] and d not in forced),
        key=lambda d: d.price,
    )
    people = [p.id for p in request.diners]
    costs = [cents(d.price) for d in choices]
    covers = [frozenset(j for j, p in enumerate(people) if p in ok[d.id]) for d in choices]
    start = frozenset(j for j, p in enumerate(people) if any(p in ok[d.id] for d in forced))
    everybody = frozenset(range(len(people)))
    # Cheapest remaining dish for each diner, by position, for the lower bound.
    cheapest_from = [[math.inf] * len(people) for _ in range(len(choices) + 1)]
    for i in range(len(choices) - 1, -1, -1):
        cheapest_from[i] = [
            min(cheapest_from[i + 1][j], costs[i] if j in covers[i] else math.inf)
            for j in range(len(people))
        ]
    best, best_cost = None, math.inf
    deadline, complete, nodes = time.monotonic() + deadline_s, True, 0

    def visit(i, chosen, cost, covered):
        nonlocal best, best_cost, complete, nodes
        nodes += 1
        if nodes % 1024 == 0 and time.monotonic() > deadline:
            complete = False
        if not complete or cost >= best_cost:
            return
        if covered == everybody:
            best, best_cost = list(chosen), cost
            return
        if i == len(choices):
            return
        bound = max(cheapest_from[i][j] for j in everybody - covered)
        if cost + bound >= best_cost:
            return
        if covers[i] - covered:
            visit(i + 1, chosen + [i], cost + costs[i], covered | covers[i])
        visit(i + 1, chosen, cost, covered)

    base_cost = sum(cents(d.price) * n for d in base) + sum(cents(d.price) for d in forced)
    visit(0, [], base_cost, start)
    if best is None:
        return None, complete
    order = [(d, 1) for d in forced] + [(choices[i], 1) for i in best] + [(d, n) for d in base]
    return order, complete


def _price_up(menu: Menu, request: TableRequest, selected) -> float | None:
    subtotal = sum(cents(d.price) * q for d, q in selected) / 100
    t = totals(subtotal, request.n_diners, request.tax_rate, request.tip_rate)
    price = math.ceil(t.total / request.n_diners * 2 - 1e-9) / 2
    items = [PlanItem(dish_id=d.id, quantity=q) for d, q in selected]
    raised = request.model_copy(update={"budget_per_person": price, "budget_total": None})
    return price if validate_order(menu, raised, items)["valid"] else None


def min_budget(menu: Menu, request: TableRequest) -> float | None:
    """Per-person budget (rounded up to 50 cents) of the cheapest valid order for this
    table; None if no order is valid at any price."""
    cheapest, _ = cheapest_order(menu, request)
    return _price_up(menu, request, cheapest) if cheapest else None


def _within(menu: Menu, request: TableRequest, order) -> bool:
    subtotal = sum(cents(d.price) * q for d, q in order) / 100
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    items = [PlanItem(dish_id=d.id, quantity=q) for d, q in order]
    return subtotal <= cap + 1e-9 and validate_order(menu, request, items)["valid"]


def fits(menu: Menu, request: TableRequest) -> bool | None:
    """A valid order exists for this request, budget included (None: search timed out)."""
    order, complete = cheapest_order(menu, request)
    if order is None:
        return False if complete else None
    return True if _within(menu, request, order) else (False if complete else None)


def analyse(menu: Menu, request: TableRequest) -> Hints:
    order, complete = cheapest_order(menu, request)
    if order is not None and _within(menu, request, order):
        feasible: bool | None = True
    else:
        feasible = False if complete else None
    floor = _price_up(menu, request, order) if order and not feasible else None
    subtotal = per_person = suggest = None
    if order:
        subtotal = sum(cents(d.price) * q for d, q in order) / 100
        t = totals(subtotal, request.n_diners, request.tax_rate, request.tip_rate)
        per_person = t.total / request.n_diners
        if floor is not None:
            suggest = suggested_budget(per_person, floor)
    excluded = set(request.excluded_dish_ids)
    must: dict[str, list[str]] = {}
    for p in request.diners:
        options = [
            d.id
            for d in menu.dishes
            if d.id not in excluded
            and d.category.value != "staple"
            and d.price is not None
            and edible_by(d, [p])
        ]
        if len(options) == 1:
            must[p.id] = options
    fuller = fuller_budget(menu, request, order) if feasible is False else None
    return Hints(feasible, floor, must, suggest, subtotal, per_person, fuller)
