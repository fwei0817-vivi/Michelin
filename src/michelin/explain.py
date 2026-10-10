"""Grounded explanations; never infer ingredients or change a plan."""

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
        if dish.confirm_with_staff:
            reason += " Check the listed questions with staff."
        items.append(item.model_copy(update={"reason": reason}))
    return plan.model_copy(update={"items": items})
