"""Variety score in [0, 1]. Replaces the proposal's "nutritional balance", which the menu
cannot support. Rewards distinct categories, proteins and cooking methods; penalizes a table
that is mostly deep-fried."""

from __future__ import annotations

from collections.abc import Sequence

from michelin.schemas import Dish, DishCategory

PROTEINS = ("pork", "beef", "chicken", "lamb", "fish", "shrimp", "tofu", "egg", "duck")
FRIED_METHODS = {"deep_fry", "dry_fry"}


def _protein_of(dish: Dish) -> str | None:
    for ing in dish.main_ingredients:
        name = ing.name.lower()
        for p in PROTEINS:
            if p in name:
                return p
    return None


def variety_score(dishes: Sequence[Dish]) -> float:
    main = [d for d in dishes if d.category != DishCategory.STAPLE]
    if not main:
        return 0.0
    n = len(main)
    categories = len({d.category for d in main}) / n
    methods = len({d.cooking_method or "unknown" for d in main}) / n
    proteins = len({_protein_of(d) for d in main}) / n
    score = (categories + methods + proteins) / 3.0
    fried = sum(1 for d in main if (d.cooking_method or "") in FRIED_METHODS) / n
    if fried > 0.5:
        score -= 0.2
    return max(0.0, min(1.0, round(score, 3)))
