"""Stage 3: fill `PlanItem.reason` with a one-line justification per dish.
Owned by the LLM teammate.

Contract: return the same Plan with `reason` set on every item. Called by the API only when
the request has `explain: true`.
"""

from __future__ import annotations

from michelin.schemas import Menu, Plan, TableRequest


def explain(plan: Plan, menu: Menu, request: TableRequest) -> Plan:
    raise NotImplementedError("owned by the LLM teammate")
