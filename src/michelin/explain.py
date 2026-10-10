"""Grounded explanations; never infer ingredients or change a plan.

Every per-dish reason the UI shows is written here (QA r16): who it is for, how spicy it is
in the card's words, and "ask the server" only when edibility.diner_status says so.
"""

from michelin.plan.edibility import diner_status
from michelin.schemas import Menu, Plan, TableRequest

SPICE = ["", "A little spicy.", "Spicy.", "Very spicy."]  # the card's labels


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _spice(dish) -> int:
    return min(max(dish.spice_level or 0, dish.menu_spice or 0), 3)


def reason_for(dish, quantity: int, request: TableRequest) -> str:
    """One natural, specific line for a dish on this table's order."""
    if dish.category.value == "staple":
        return f"{quantity} servings of {dish.name_en or 'rice'} for the table."
    status = diner_status(dish, request.diners)
    eat = [p for p in request.diners if status[p.id]["status"] != "no"]
    names = [p.name or p.id for p in eat]
    if not eat:
        return "No one at this table can eat this under their restrictions; swap it out."
    if len(eat) == len(request.diners):
        line = "Everyone can share this." if len(eat) > 1 else f"For {names[0]}."
    else:
        others = [p.name or p.id for p in request.diners if p not in eat]
        line = f"For {_join(names)}; not for {_join(others)}."
    heat = SPICE[_spice(dish)]
    if heat:
        line += f" {heat}"
    ask = [p.name or p.id for p in eat if status[p.id]["status"] == "needs_confirm"]
    if ask and len(ask) == len(request.diners):
        line += " Ask the server first."
    elif ask:
        line += f" Ask the server first for {_join(ask)}."
    return line


def explain(plan: Plan, menu: Menu, request: TableRequest) -> Plan:
    items = [
        item.model_copy(
            update={"reason": reason_for(menu.dish(item.dish_id), item.quantity, request)}
        )
        for item in plan.items
    ]
    return plan.model_copy(update={"items": items})
