"""Conflict diagnosis: when the optimizer is infeasible, find the smallest changes that
restore feasibility and report them as Relaxations.   [NOT IMPLEMENTED YET]

Algorithm
    1. Budget: re-solve as min-cost with the budget constraint removed. If feasible, report
       kind="budget", new_value = smallest per-person budget that works (round up to $0.50).
    2. Per diner, per hard constraint: re-solve with that one allergy or diet dropped.
       Each success becomes kind="allergy" | "diet" with diner_id.
    3. Coverage: re-solve with min_dishes_per_person - 1. Success -> kind="coverage".
    4. Portions: re-solve with the portion range widened by 20%. Success -> kind="portions".
    If nothing single-step works, say so in Conflict.message and list nothing rather than
    inventing a multi-step relaxation.

Never drop an allergy silently: every relaxation is a suggestion the user must accept.
"""

from __future__ import annotations

from michelin.schemas import Conflict, Menu, TableRequest


def diagnose(menu: Menu, request: TableRequest) -> Conflict:
    raise NotImplementedError("see this module's docstring")
