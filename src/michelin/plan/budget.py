"""Budget arithmetic. The per-person budget is all-in: it includes tax and tip.

Tip is computed on the pre-tax subtotal (US convention), so for a menu subtotal S:
    total = S * (1 + tax_rate + tip_rate)
"""

from __future__ import annotations

from dataclasses import dataclass


def subtotal_cap(budget_per_person: float, n_diners: int, tax_rate: float, tip_rate: float) -> float:
    """Largest menu-price subtotal whose all-in total fits the group's budget."""
    return budget_per_person * n_diners / (1.0 + tax_rate + tip_rate)


@dataclass(frozen=True)
class Totals:
    subtotal: float
    tax: float
    tip: float
    total: float
    per_person: float


def totals(subtotal: float, n_diners: int, tax_rate: float, tip_rate: float) -> Totals:
    tax = round(subtotal * tax_rate, 2)
    tip = round(subtotal * tip_rate, 2)
    total = round(subtotal + tax + tip, 2)
    return Totals(
        subtotal=round(subtotal, 2),
        tax=tax,
        tip=tip,
        total=total,
        per_person=round(total / n_diners, 2),
    )
