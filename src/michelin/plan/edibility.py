"""Hard-constraint check: can diner p eat dish d?

Explicit conflicts and unresolved evidence both exclude a dish from diner coverage.
A review establishes only no recorded evidence, never an allergy safety guarantee.
"""

from __future__ import annotations

import re

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
    # A small explicit vocabulary is contradiction detection, not an ingredient
    # extractor. Unrecognized text never establishes absence or safety.
    terms = {
        "pork": (r"\bpork\b|猪肉", {Diet.VEGETARIAN, Diet.VEGAN, Diet.NO_PORK}, set()),
        "beef": (r"\bbeef\b|牛肉", {Diet.VEGETARIAN, Diet.VEGAN, Diet.NO_BEEF}, set()),
        "chicken": (r"\bchicken\b|鸡肉", {Diet.VEGETARIAN, Diet.VEGAN}, set()),
        "fish": (r"\bfish\b|\btilapia\b", {Diet.VEGETARIAN, Diet.VEGAN}, {Allergen.FISH}),
        "shellfish": (
            r"\bshrimp\b|\bprawn\b|\bcrab\b|\boyster sauce\b",
            {Diet.VEGETARIAN, Diet.VEGAN},
            {Allergen.SHELLFISH},
        ),
        "egg": (r"\beggs?\b", {Diet.VEGAN}, {Allergen.EGG}),
        "dairy": (r"\bmilk\b|\bbutter\b|\bcheese\b", {Diet.VEGAN}, {Allergen.DAIRY}),
        "sesame": (r"\bsesame\b", set(), {Allergen.SESAME}),
        "peanut": (r"\bpeanuts?\b", set(), {Allergen.PEANUT}),
    }
    for claim in dish.main_ingredients:
        for label, (pattern, diets, allergens) in terms.items():
            if re.search(pattern, claim.name, re.IGNORECASE) and (
                diets.intersection(diner.diets) or allergens.intersection(diner.allergies)
            ):
                # Substitutions/negations need review; do not certify an omission.
                ambiguous = re.search(
                    r"\b(no|without|free|vegan|substitute|omit|plant)\b", claim.name, re.IGNORECASE
                )
                if claim.tier in BLOCKING_TIERS and not ambiguous:
                    conflicts.append(
                        f"Recorded or inferred {label} ingredient conflicts with restrictions"
                    )
                else:
                    unknown.append(f"Confirm {label} ingredient/preparation")
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
    # Positive labels cannot erase contradictory recorded evidence. Allergen evidence
    # still wins over reviewed_allergens. Unknown claims remain confirmation questions.
    animal_allergens = {Allergen.FISH, Allergen.SHELLFISH}
    for diet in diner.diets:
        incompatible = animal_allergens | (
            {Allergen.EGG, Allergen.DAIRY} if diet == Diet.VEGAN else set()
        )
        if diet in {Diet.VEGETARIAN, Diet.VEGAN}:
            if dish.contains_pork is True or dish.contains_beef is True:
                conflicts.append(f"Recorded meat conflicts with {diet.value}")
            if diet == Diet.VEGAN and dish.is_vegetarian is False:
                conflicts.append("Non-vegetarian preparation conflicts with vegan")
            for flag in dish.allergens:
                if flag.allergen in incompatible:
                    if flag.tier in BLOCKING_TIERS:
                        conflicts.append(
                            f"Recorded or inferred {flag.allergen.value} conflicts with {diet.value}"
                        )
                    else:
                        unknown.append(
                            f"Confirm {flag.allergen.value} for {diet.value} preparation"
                        )
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
    if dish.portion is None:
        questions.append(
            f"{dish.name_en or dish.id}: portion unknown; planning estimates 1 unit per non-staple order, not people fed. Confirm size."
        )
    if dish.spice_level is None:
        questions.append(f"{dish.name_en or dish.id}: spice level unknown. Confirm heat.")
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
