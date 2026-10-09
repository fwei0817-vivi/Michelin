"""Extract explicit name/price rows from menu text.

`parse_text` never guesses: it returns names and prices only. Likely ingredients and
allergen risks come from the AI (plan/dish_facts.py); the menu stays unverified until a
person reviews it.
"""

import re
import uuid

from michelin.schemas import Dish


def generic_question(name: str) -> str:
    return f"Confirm ingredients, allergens, and preparation for {name}."


def parse_text(text: str) -> list[Dish]:
    dishes = []
    for line in text.splitlines():
        match = re.match(r"^\s*(.+?)\s+(?:\$|USD\s*)?(\d{1,3}(?:\.\d{1,2})?)\s*$", line)
        if not match:
            continue
        name, price = match.groups()
        name = name.strip(" .-–·\t")
        if len(name) < 2:
            continue
        dishes.append(
            Dish(
                id=f"import_{uuid.uuid4().hex[:12]}",
                name_en=name,
                price=float(price),
            )
        )
    return dishes[:40]
