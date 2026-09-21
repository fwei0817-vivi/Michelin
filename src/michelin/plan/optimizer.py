"""Stage 2: Menu + TableRequest -> Plan | Conflict.   [NOT IMPLEMENTED YET]

Model (OR-Tools CP-SAT). Prices are scaled to integer cents.

Variables
    x[d] in {0, 1}        for each non-staple dish d with a known price
    s    in {0..N}        staple quantity (N = number of diners), if request.include_staple

Hard constraints
    allergy / diet   x[d] = 0 is NOT forced globally. Instead a dish simply does not count
                     toward a diner's coverage if that diner cannot eat it (see edibility.py).
                     A dish nobody at the table can eat is excluded up front.
    coverage         for each diner p: sum(x[d] for d edible by p) >= min_dishes_per_person
    budget           sum(price_cents[d] * x[d]) + staple_cents * s <= subtotal_cap in cents
    portions         lo <= sum(units[d] * x[d]) <= hi   (portions.required_range, scaled x10)
    staple           s == N if include_staple else 0

Objective (maximize)
    W_VARIETY * variety proxy  (distinct categories + distinct proteins, linearized with
                                indicator vars per category / protein)
  - W_DISLIKE * sum over (p, d) of x[d] where a p.dislikes term appears in d's ingredients
  - W_SPICE   * sum over (p, d) of x[d] * max(0, d.spice_level - p.max_spice)
  - W_SLACK   * unspent budget (cents), small, so we use the money we have

On INFEASIBLE, return plan.relax.diagnose(menu, request).

Post-processing: build PlanItem.edible_by from edibility.edible_by, totals from
budget.totals, checks (one per hard constraint, all passed=True here), confirm_with_staff
from edibility.open_questions over the chosen dishes, variety_score from score.variety_score.
"""

from __future__ import annotations

from michelin.schemas import Conflict, Menu, Plan, TableRequest


def solve(menu: Menu, request: TableRequest) -> Plan | Conflict:
    raise NotImplementedError("CP-SAT model not implemented yet; see this module's docstring")
