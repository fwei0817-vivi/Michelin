"""Grounded explanations; never infer ingredients or change a plan."""

from michelin.schemas import Menu, Plan, TableRequest


def explain(plan: Plan, menu: Menu, request: TableRequest) -> Plan:
    items = []
    for item in plan.items:
        dish = menu.dish(item.dish_id)
        names = [p.name for p in request.diners if p.id in item.edible_by]
        if dish.category.value == "staple":
            reason = f"Adds {item.quantity} staple servings to the table."
        elif len(names) == request.n_diners:
            reason = (
                "Contributes to every diner's coverage under the recorded dietary requirements."
            )
        elif names:
            reason = f"Adds an option for {', '.join(names)}."
        else:
            reason = "No diner meets the recorded requirements for this dish; choose a replacement."
        heat = [
            p.name
            for p in request.diners
            if p.id in item.edible_by
            and p.max_spice is not None
            and dish.spice_level is not None
            and dish.spice_level > p.max_spice
        ]
        if heat:
            reason += f" Above the preferred spice level for {', '.join(heat)}."
        if dish.confirm_with_staff:
            reason += " Check the listed questions with staff."
        items.append(item.model_copy(update={"reason": reason}))
    return plan.model_copy(update={"items": items})
