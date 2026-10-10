"""QA round 14: the swap hint uses the card's per-diner test only; summary overclaims about
preferences are rejected; code reasons mention asking the server when the card does."""

import pytest
from test_round11 import client, demo  # noqa: F401 - fixture

from michelin.explain import explain
from michelin.plan import ai_swap, ai_text
from michelin.plan.edibility import edible_by
from michelin.schemas import CustomFlag, Menu, Plan, PlanItem, TableRequest

pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]
BEEF = "sichuan_boiled_beef_in_chili_oil_sliced_beef"


def _setup(demo, mia_flags=False):  # noqa: F811
    menu, diners = demo
    menu = Menu.model_validate(client.post("/api/menu/facts", json=menu).json())
    if mia_flags:
        # As in the app for Tomato & Egg: Mia's halal "possible" (ask), no cilantro.
        flags = [
            CustomFlag(term="halal", kind="diet", answer="possible"),
            CustomFlag(term="cilantro", kind="allergy", answer="no"),
        ]
        menu = menu.model_copy(
            update={
                "dishes": [
                    d.model_copy(update={"custom_flags": flags}) if d.id == "tomato_egg" else d
                    for d in menu.dishes
                ]
            }
        )
    req = TableRequest(menu_id="local-1", diners=diners, budget_per_person=40)
    return menu, req


def test_r14_repro_beef_for_alice_is_a_plain_can_eat(demo):  # noqa: F811
    menu, req = _setup(demo)
    assert edible_by(menu.dish(BEEF), req.diners) == ["alice"]
    line = ai_swap._line(menu, req, "chilled_zucchini_in_tangy_sauce", BEEF, None)
    assert ", Alice can eat it, " in line and "server" not in line


def test_tomato_egg_still_needs_confirming(demo):  # noqa: F811
    menu, req = _setup(demo, mia_flags=True)
    line = ai_swap._line(menu, req, "broccoli_tofu", "tomato_egg", None)
    assert "everyone can eat it if the server confirms" in line


@pytest.mark.ai_prose
def test_summary_preference_overclaims_are_rejected(demo):  # noqa: F811
    menu, req = _setup(demo)
    ids = [
        "cucumber_salad_garlic",
        "chilled_zucchini_in_tangy_sauce",
        "tomato_egg",
        "broccoli_tofu",
    ]
    items = [PlanItem(dish_id=i, quantity=1, edible_by=[]) for i in ids]
    for text in (
        "A balanced order that satisfies everyone's dietary restrictions and preferences.",
        "Tofu and rice that easily accommodate all dietary restrictions.",
        "A spread that meets everyone's needs.",
    ):
        assert ai_text.summary(text, menu, req, items) is None, text
    assert ai_text.summary("A balanced order with tofu.", menu, req, items) is not None


def test_code_reason_says_ask_the_server_when_the_card_does(demo):  # noqa: F811
    menu, req = _setup(demo, mia_flags=True)
    egg = menu.dish("tomato_egg")
    who = edible_by(egg, req.diners)
    plan = Plan(
        items=[PlanItem(dish_id="tomato_egg", quantity=1, edible_by=who)],
        subtotal=17,
        tax=0,
        tip=0,
        total=17,
        per_person=5,
        variety_score=0.5,
    )
    reason = explain(plan, menu, req).items[0].reason
    assert "Ask the server first" in reason
