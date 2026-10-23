"""USD cents, ROUND_HALF_UP per tax/tip line; tip uses pre-tax subtotal.

No unlisted service fees are included. The cap uses the same rounded arithmetic as
validation, avoiding both one-cent overruns and rejection of valid boundary orders.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def cents(value):
    return int(money(value) * 100)


def subtotal_cap(
    budget_per_person: float, n_diners: int, tax_rate: float, tip_rate: float
) -> float:
    budget = cents(budget_per_person) * n_diners
    lo, hi = 0, budget
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if cents(totals(mid / 100, n_diners, tax_rate, tip_rate).total) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo / 100


@dataclass(frozen=True)
class Totals:
    subtotal: float
    tax: float
    tip: float
    total: float
    per_person: float


def totals(subtotal: float, n_diners: int, tax_rate: float, tip_rate: float) -> Totals:
    subtotal = money(subtotal)
    tax = money(subtotal * Decimal(str(tax_rate)))
    tip = money(subtotal * Decimal(str(tip_rate)))
    total = subtotal + tax + tip
    return Totals(*(float(x) for x in (subtotal, tax, tip, total, money(total / n_diners))))
