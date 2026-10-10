"""Grounded explanations; never infer ingredients or change a plan.

Every per-dish reason the UI shows is written here (QA r16): who it is for, how spicy it is
in the card's words, and "ask the server" only when edibility.diner_status says so.
"""

from michelin.plan import spice
from michelin.plan.edibility import diner_status
from michelin.schemas import Menu, Plan, TableRequest


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def reason_for(dish, quantity: int, request: TableRequest) -> str:
    """One natural, specific line for a dish on this order (2026-10-10): listed only for
    diners with no allergy/diet block and no taste conflict; "if the server confirms" for
    whoever needs it; the spice word from plan.spice, the same as the card's tag."""
    if dish.category.value == "staple":
        return f"{quantity} servings of {dish.name_en or 'rice'} for the table."
    status = diner_status(dish, request.diners)
    name = {p.id: p.name or p.id for p in request.diners}
    listed = [
        p.id
        for p in request.diners
        if status[p.id]["status"] != "no" and status[p.id]["taste"] != "too_spicy"
    ]
    blocked = [p.id for p in request.diners if status[p.id]["status"] == "no"]
    hot = [
        p.id
        for p in request.diners
        if status[p.id]["status"] != "no" and status[p.id]["taste"] == "too_spicy"
    ]
    little = [i for i in listed if status[i]["taste"] == "a_little_spicy"]
    ask = [i for i in listed if status[i]["status"] == "needs_confirm"]
    if not listed:
        line = "Not a fit for anyone at this table"
    elif len(listed) == len(request.diners) and len(listed) > 1:
        line = "Everyone can share this"
        if ask:
            line += " if the server confirms" + (
                "" if len(ask) == len(listed) else f" for {_join([name[i] for i in ask])}"
            )
    else:
        line = f"For {_join([name[i] for i in listed])}"
        if ask and len(ask) == len(listed):
            line += " if the server confirms"
        elif ask:
            line += f" ({_join([name[i] for i in ask])} only if the server confirms)"
    if blocked:
        line += f"; not for {_join([name[i] for i in blocked])}"
    if hot:
        line += f"; too spicy for {_join([name[i] for i in hot])}"
    heat = spice.label(dish)
    if little:  # the spice said once (QA r20)
        line += f"; a little spicy for {_join([name[i] for i in little])}."
    else:
        line += "."
        if heat:
            line += f" {heat}."
    return line


def explain(plan: Plan, menu: Menu, request: TableRequest) -> Plan:
    items = [
        item.model_copy(
            update={"reason": reason_for(menu.dish(item.dish_id), item.quantity, request)}
        )
        for item in plan.items
    ]
    return plan.model_copy(update={"items": items})
