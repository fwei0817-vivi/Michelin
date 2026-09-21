"""Portion heuristic.

Family-style rule of thumb: N people order about N dishes plus a staple each. We express it
as "portion units": a typical stir-fry plate is 1.0 unit, and the table needs between
0.9·N and 1.3·N units of non-staple food. Numbers are a starting point; tune them against
real orders and record changes in docs/decisions.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from michelin.schemas import Dish, DishCategory, PortionClass

PORTION_UNITS: dict[PortionClass, float] = {
    PortionClass.INDIVIDUAL: 0.35,
    PortionClass.SMALL: 0.6,
    PortionClass.MEDIUM: 1.0,
    PortionClass.LARGE: 1.5,
    PortionClass.SHARED: 0.8,  # soup fills less than a plate
}

UNITS_PER_PERSON_MIN = 0.9
UNITS_PER_PERSON_MAX = 1.3


def units(dish: Dish) -> float:
    """Portion units a dish contributes. Staples (rice, noodles) contribute 0; they are
    handled separately by `TableRequest.include_staple`."""
    if dish.category == DishCategory.STAPLE:
        return 0.0
    return PORTION_UNITS[dish.portion]


def required_range(n_diners: int) -> tuple[float, float]:
    return n_diners * UNITS_PER_PERSON_MIN, n_diners * UNITS_PER_PERSON_MAX


def total_units(dishes: Iterable[Dish]) -> float:
    return sum(units(d) for d in dishes)


def is_enough(dishes: Iterable[Dish], n_diners: int) -> bool:
    lo, hi = required_range(n_diners)
    return lo <= total_units(dishes) <= hi
