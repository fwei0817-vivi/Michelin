"""Extract explicit name/price rows, then label them from the reviewed knowledge base.

`parse_text` never guesses: it returns names and prices only. `label_imported` adds what the
printed text and `knowledge.py` support, with evidence tiers; unrecognized dishes stay
unknown. Either way the result is unverified until a person reviews it.
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
                description_raw=line,
                confirm_with_staff=[generic_question(name)],
            )
        )
    return dishes[:40]


def label_imported(dishes: list[Dish]) -> list[Dish]:
    """Knowledge-base labels for imported rows. A recognized dish drops the generic
    question in favour of specific ones; an unrecognized dish keeps it. Names the knowledge
    base misses go to the LLM matcher (stored answers always; new ones only when
    MICHELIN_LLM_MATCH=1)."""
    from michelin.parse.knowledge import label_dish
    from michelin.parse.matcher import match_names

    suggested = match_names(dishes)
    out = []
    for dish in dishes:
        labeled = label_dish(dish, suggested=suggested.get(dish.id))
        if labeled.match:
            generic = generic_question(dish.name_en or "")
            questions = [q for q in labeled.dish.confirm_with_staff if q != generic]
            out.append(labeled.dish.model_copy(update={"confirm_with_staff": questions}))
        else:
            out.append(labeled.dish)
    return out
