"""QA round 13 wording: swap hint matches the card's 'only if the server confirms'; the
code's fallback reason is plain and names who it helps."""

from michelin.explain import explain
from michelin.plan import ai_swap
from michelin.schemas import (
    Diet,
    DinerProfile,
    Dish,
    EvidenceTier,
    IngredientClaim,
    Menu,
    Plan,
    PlanItem,
    TableRequest,
)


def _dish(i, name, price, ingredients=()):
    return Dish(
        id=i, name_en=name, price=price, category="stir_fry", main_ingredients=list(ingredients)
    )


def _setup(egg_tier):
    dishes = [
        _dish("tomato_egg", "Tomato & Egg", 17, [IngredientClaim(name="egg", tier=egg_tier)]),
        _dish("greens", "Garlic Greens", 12),
    ]
    menu = Menu(
        restaurant_id="t",
        restaurant_name="T",
        cuisine="custom",
        source="test",
        currency="USD",
        verified=True,
        dishes=dishes,
    )
    req = TableRequest(
        menu_id="t",
        diners=[DinerProfile(id="a", name="Alice"), DinerProfile(id="b", name="Ben")],
        budget_per_person=40,
    )
    return menu, req


def test_swap_hint_without_doubt_stays_plain():
    menu, req = _setup(EvidenceTier("menu"))
    line = ai_swap._line(menu, req, "greens", "tomato_egg", None)
    assert ", everyone can eat it, " in line


def test_fallback_reason_is_natural_and_names_who():
    menu, req = _setup(EvidenceTier("menu"))
    req = req.model_copy(
        update={"diners": [*req.diners, DinerProfile(id="m", name="Mia", diets=[Diet.VEGAN])]}
    )
    plan = Plan(
        items=[
            PlanItem(dish_id="greens", quantity=1, edible_by=["a", "b", "m"]),
            PlanItem(dish_id="tomato_egg", quantity=1, edible_by=["a", "b"]),
        ],
        subtotal=29,
        tax=0,
        tip=0,
        total=29,
        per_person=10,
        variety_score=0.5,
    )
    out = explain(plan, menu, req)
    assert out.items[0].reason.startswith("A dish everyone can share.")
    assert out.items[1].reason == "Gives Alice and Ben another option."
    assert all("coverage" not in i.reason for i in out.items)
