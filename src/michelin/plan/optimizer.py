"""Bounded branch-and-bound over small verified menus. Hard constraints are
server-owned. The objective rewards variety and preferences with a soft course
target. Search exhaustion never proves infeasibility: return a valid incumbent
or a retryable timeout. No external solver or LLM credentials are required.
"""

from __future__ import annotations

import math
import time

from michelin.explain import explain
from michelin.plan.budget import cents, subtotal_cap, totals
from michelin.plan.edibility import assessment, edible_by, open_questions
from michelin.plan.portions import required_range, units
from michelin.plan.score import variety_score
from michelin.schemas import Check, Conflict, Menu, Plan, PlanItem, Relaxation, TableRequest


def _search(menu: Menu, req: TableRequest, *, budget: bool = True, min_cost: bool = False):
    n = req.n_diners
    cap = math.floor(
        subtotal_cap(req.budget_per_person, n, req.tax_rate, req.tip_rate) * 100 + 1e-7
    )
    excluded, locked = set(req.excluded_dish_ids), set(req.locked_dish_ids)
    available = [
        d for d in menu.dishes if d.id not in excluded and d.price is not None and d.price >= 0
    ]
    eligible = {d.id: edible_by(d, req.diners) for d in available}
    if locked & excluded or any(not eligible.get(i) for i in locked):
        return None, True
    staples = [d for d in available if d.category.value == "staple" and len(eligible[d.id]) == n]
    locked_staples = [d for d in available if d.id in locked and d.category.value == "staple"]
    if any(len(eligible[d.id]) != n for d in locked_staples):
        return None, True
    base = locked_staples or (
        [min(staples, key=lambda d: d.price)] if staples and req.include_staple else []
    )
    if req.include_staple and not base:
        return None, True
    choices = [d for d in available if d.category.value != "staple" and eligible[d.id]]
    choices.sort(key=lambda d: (d.id not in locked, -len(eligible[d.id]), d.price))
    m = len(choices)
    costs = [cents(d.price) for d in choices]
    weights = [round(units(d) * 100) for d in choices]
    masks = [[int(p.id in eligible[d.id]) for p in req.diners] for d in choices]
    suffix = [[0] * n for _ in range(m + 1)]
    unit_suffix = [0] * (m + 1)
    for i in range(m - 1, -1, -1):
        suffix[i] = [a + b for a, b in zip(suffix[i + 1], masks[i])]
        unit_suffix[i] = unit_suffix[i + 1] + weights[i]
    lo, hi = (round(v * 100) for v in required_range(n))
    base_cost = sum(cents(d.price) * n for d in base)
    best, best_score, best_cost = None, -float("inf"), float("inf")
    deadline, complete, nodes = time.monotonic() + 2.5, True, 0

    def visit(i, chosen, cost, portion, coverage):
        nonlocal best, best_score, best_cost, complete, nodes
        nodes += 1
        if nodes % 1024 == 0 and time.monotonic() > deadline:
            complete = False
            return
        if not complete or (budget and cost > cap) or portion > hi or portion + unit_suffix[i] < lo:
            return
        if min_cost and cost >= best_cost:
            return
        if any(c + suffix[i][j] < req.min_dishes_per_person for j, c in enumerate(coverage)):
            return
        if i == m:
            if portion < lo or any(c < req.min_dishes_per_person for c in coverage):
                return
            if (
                budget
                and totals(cost / 100, n, req.tax_rate, req.tip_rate).total
                > req.budget_per_person * n + 1e-7
            ):
                return
            dishes = [choices[j] for j in chosen]
            target = req.dish_count_target or n + len(base)
            score = 20 * variety_score(dishes) - 4 * abs(len(dishes) + len(base) - target)
            for d in dishes:
                ingredients = " ".join(x.name.lower() for x in d.main_ingredients)
                if req.style_preference == "lighter":
                    score += 2 * (d.is_vegetarian is True) - 3 * (
                        d.cooking_method in ("deep_fry", "dry_fry")
                    )
                for p in req.diners:
                    if p.id not in eligible[d.id]:
                        continue
                    score -= 2 * sum(x.lower() in ingredients for x in p.dislikes)
                    score += (3 if req.style_preference == "favorites" else 1) * sum(
                        x.lower() in ingredients for x in p.likes
                    )
                    score -= max(0, d.spice_level - p.max_spice) if p.max_spice is not None else 0
            if (min_cost and cost < best_cost) or (
                not min_cost and (score > best_score or (score == best_score and cost < best_cost))
            ):
                best = [(d, 1) for d in dishes] + [(d, n) for d in base]
                best_score, best_cost = score, cost
            return
        visit(
            i + 1,
            chosen + [i],
            cost + costs[i],
            portion + weights[i],
            [a + b for a, b in zip(coverage, masks[i])],
        )
        if choices[i].id not in locked:
            visit(i + 1, chosen, cost, portion, coverage)

    visit(0, [], base_cost, 0, [0] * n)
    return best, complete


def solve(menu: Menu, request: TableRequest) -> Plan | Conflict:
    if (
        not menu.verified
        or menu.currency != "USD"
        or any(d.price is None for d in menu.dishes)
        or len({d.id for d in menu.dishes}) != len(menu.dishes)
    ):
        return Conflict(
            code="missing_information", message="Review menu, currency, IDs and prices first."
        )
    selected, complete = _search(menu, request)
    if selected is None:
        if not complete:
            raise TimeoutError(
                "The menu search took too long. Narrow the menu or keep a few dishes and try again."
            )
        relaxations = []
        cheapest, _ = _search(menu, request, budget=False, min_cost=True)
        if cheapest:
            amount = sum(cents(d.price) * qty for d, qty in cheapest) / 100
            price = (
                math.ceil(
                    totals(amount, request.n_diners, request.tax_rate, request.tip_rate).total
                    / request.n_diners
                    * 2
                )
                / 2
            )
            if price > request.budget_per_person:
                relaxations.append(
                    Relaxation(
                        kind="budget",
                        new_value=price,
                        description=f"Set the all-in budget to {price:.2f} per person for a feasible order.",
                    )
                )
        if request.min_dishes_per_person > 1:
            lower = request.model_copy(
                update={"min_dishes_per_person": request.min_dishes_per_person - 1}
            )
            candidate, _ = _search(menu, lower)
            if candidate:
                relaxations.append(
                    Relaxation(
                        kind="coverage",
                        new_value=lower.min_dishes_per_person,
                        description=f"Allow at least {lower.min_dishes_per_person} non-staple dishes per diner.",
                    )
                )
        uncertain = any(
            assessment(d, p)["status"] == "requires_confirmation"
            for d in menu.dishes
            for p in request.diners
        )
        return Conflict(
            code="missing_information" if uncertain else "no_solution",
            message=(
                "A validated order was not found and some dietary evidence is unresolved; confirm with staff. "
                if uncertain
                else ""
            )
            + "No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.",
            relaxations=relaxations,
        )
    dishes = [d for d, _ in selected]
    t = totals(
        sum(cents(d.price) * qty for d, qty in selected) / 100,
        request.n_diners,
        request.tax_rate,
        request.tip_rate,
    )
    questions = list(dict.fromkeys(q for d in dishes for q in open_questions(d, request.diners)))
    checks = [
        Check(name=name, passed=True, detail=detail)
        for name, detail in (
            (
                "coverage",
                f"Each diner has at least {request.min_dishes_per_person} non-staple dishes under recorded requirements.",
            ),
            ("budget", "The total includes tax and tip and fits the table budget."),
            ("portions", "Shared portions meet the table's estimated range."),
            ("diets", "Dietary eligibility is recorded separately for each diner."),
        )
    ]
    plan = Plan(
        items=[
            PlanItem(dish_id=d.id, quantity=q, edible_by=edible_by(d, request.diners))
            for d, q in selected
        ],
        subtotal=t.subtotal,
        tax=t.tax,
        tip=t.tip,
        total=t.total,
        per_person=t.per_person,
        variety_score=variety_score(dishes),
        checks=checks,
        confirm_with_staff=questions,
    )
    return explain(plan, menu, request)
