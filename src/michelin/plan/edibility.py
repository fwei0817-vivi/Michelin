"""Hard-constraint check: can diner p eat dish d?

Only tiers `menu` and `inferred` block a dish. `unknown` flags never block; they surface as
questions in Plan.confirm_with_staff. A `None` diet flag is treated as False (unsafe).
"""

from __future__ import annotations

from michelin.schemas import Allergen, Diet, DinerProfile, Dish, EvidenceTier

BLOCKING_TIERS = {EvidenceTier.MENU, EvidenceTier.INFERRED}


def blocking_allergens(dish: Dish, diner: DinerProfile) -> list[Allergen]:
    wanted = set(diner.allergies)
    return [f.allergen for f in dish.allergens if f.allergen in wanted and f.tier in BLOCKING_TIERS]


def blocking_diets(dish: Dish, diner: DinerProfile) -> list[Diet]:
    out: list[Diet] = []
    for diet in diner.diets:
        if diet == Diet.VEGETARIAN and dish.is_vegetarian is not True:
            out.append(diet)
        elif diet == Diet.VEGAN and dish.is_vegan is not True:
            out.append(diet)
        elif diet == Diet.NO_PORK and dish.contains_pork is not False:
            out.append(diet)
        elif diet == Diet.NO_BEEF and dish.contains_beef is not False:
            out.append(diet)
    return out


def can_eat(dish: Dish, diner: DinerProfile) -> bool:
    return not blocking_allergens(dish, diner) and not blocking_diets(dish, diner)


def edible_by(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    return [p.id for p in diners if can_eat(dish, p)]


def open_questions(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    """Staff questions that matter for someone at this table: the dish's own questions plus
    any `unknown`-tier flag that matches a diner's allergy."""
    questions = list(dish.confirm_with_staff)
    table_allergies = {a for p in diners for a in p.allergies}
    for f in dish.allergens:
        if f.tier == EvidenceTier.UNKNOWN and f.allergen in table_allergies:
            label = dish.name_en or dish.name_zh or dish.id
            questions.append(f"{label}: {f.reason} (someone is allergic to {f.allergen.value})")
    return questions
