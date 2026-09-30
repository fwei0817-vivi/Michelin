"""Hard-constraint check: can diner p eat dish d?

Explicit conflicts and unresolved evidence both exclude a dish from diner coverage.
A review establishes only no recorded evidence, never an allergy safety guarantee.
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
        if (
            diet == Diet.VEGETARIAN
            and dish.is_vegetarian is not True
            or diet == Diet.VEGAN
            and dish.is_vegan is not True
            or diet == Diet.NO_PORK
            and dish.contains_pork is not False
            or diet == Diet.NO_BEEF
            and dish.contains_beef is not False
        ):
            out.append(diet)
    return out


def assessment(dish: Dish, diner: DinerProfile) -> dict:
    conflicts, unknown = [], []
    for allergen in diner.allergies:
        flags = [f for f in dish.allergens if f.allergen == allergen]
        if any(f.tier in BLOCKING_TIERS for f in flags):
            conflicts.append(f"Recorded or inferred {allergen.value} ingredient")
        elif (
            any(f.tier == EvidenceTier.UNKNOWN for f in flags)
            or allergen not in dish.reviewed_allergens
        ):
            unknown.append(f"Confirm {allergen.value}, including sauces and cross-contact")
    fields = {
        Diet.VEGETARIAN: ("is_vegetarian", True),
        Diet.VEGAN: ("is_vegan", True),
        Diet.NO_PORK: ("contains_pork", False),
        Diet.NO_BEEF: ("contains_beef", False),
    }
    for diet in diner.diets:
        field, required = fields[diet]
        value = getattr(dish, field)
        if value is None:
            unknown.append(f"Confirm {diet.value} preparation")
        elif value != required:
            conflicts.append(f"Conflicts with {diet.value}")
    return {
        "status": "conflict"
        if conflicts
        else "requires_confirmation"
        if unknown
        else "validated_under_known_data",
        "reasons": conflicts + unknown,
    }


def can_eat(dish: Dish, diner: DinerProfile) -> bool:
    return assessment(dish, diner)["status"] == "validated_under_known_data"


def edible_by(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    return [p.id for p in diners if can_eat(dish, p)]


def open_questions(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    """Staff questions that matter for someone at this table: the dish's own questions plus
    any `unknown`-tier flag that matches a diner's allergy."""
    questions = list(dish.confirm_with_staff)
    for person in diners:
        result = assessment(dish, person)
        questions.extend(
            f"{dish.name_en or dish.id} / {person.id}: {r}"
            for r in result["reasons"]
            if r.startswith("Confirm")
        )
    table_allergies = {a for p in diners for a in p.allergies}
    for f in dish.allergens:
        if f.tier == EvidenceTier.UNKNOWN and f.allergen in table_allergies:
            label = dish.name_en or dish.name_zh or dish.id
            questions.append(f"{label}: {f.reason} (someone is allergic to {f.allergen.value})")
    return questions
