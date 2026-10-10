"""Grounded explanations; never infer ingredients or change a plan."""

from michelin.plan.edibility import assessment
from michelin.schemas import Menu, Plan, TableRequest


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def explain(plan: Plan, menu: Menu, request: TableRequest) -> Plan:
    items = []
    for item in plan.items:
        dish = menu.dish(item.dish_id)
        names = [p.name for p in request.diners if p.id in item.edible_by]
        if dish.category.value == "staple":
            reason = f"Adds {item.quantity} staple servings to the table."
        elif len(names) == request.n_diners:
            reason = "A dish everyone can share."
        elif names:
            reason = f"Gives {_join(names)} another option."
        else:
            reason = "No diner meets the recorded requirements for this dish; choose a replacement."
        ask = [
            p.name
            for p in request.diners
            if p.id in item.edible_by and assessment(dish, p)["status"] == "requires_confirmation"
        ]
        if ask and len(ask) == len(names) == request.n_diners:
            reason += " Ask the server first."
        elif ask:
            reason += f" Ask the server first for {_join(ask)}."
        elif dish.confirm_with_staff:
            reason += " Check the listed questions with staff."
        items.append(item.model_copy(update={"reason": reason}))
    return plan.model_copy(update={"items": items})
