"""Extract explicit name/price rows. Never guess ingredients or dietary flags."""

import re
import uuid

from michelin.schemas import Dish


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
                description_raw=line,
                confirm_with_staff=[f"Confirm ingredients, allergens, and preparation for {name}."],
            )
        )
    return dishes[:40]
