"""QA round 25 QF-1 (2026-10-10): on Cafe China the demo table (Alice no heat, Ben
vegetarian, Cai shellfish, Mia no pork, $40) got 3 hot dishes for 4 with $40 left. The
top-up picked a second fried rice, which check() then rejected as a repeat, so nothing was
added. The top-up now skips repeats and meets the hot-dish count on its own even when a
diner's own shortfall cannot be fixed on this menu; the message says why for each part."""

from pathlib import Path

import pytest

from michelin.plan import enough
from michelin.plan.validation import staple_repeats, validate_order
from michelin.schemas import DinerProfile, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
D = [
    DinerProfile(id="alice", name="Alice", max_spice=0),
    DinerProfile(id="ben", name="Ben", diets=["vegetarian"]),
    DinerProfile(id="cai", name="Cai", allergies=["shellfish"]),
    DinerProfile(id="mia", name="Mia", diets=["no_pork"]),
]
QA_ORDER = [
    "house_smoked_tofu",
    "spicy_cucumbers",
    "tea_smoked_duck",
    "stir_fried_cabbage",
    "fried_rice_with_shredded_duck",
]


@pytest.fixture
def cafe_china():
    # the facts recorded in the bundled menu (offline, no AI)
    menu = Menu.model_validate_json((ROOT / "data/menus/cafe_china.json").read_text())
    items = [PlanItem(dish_id=i, quantity=1) for i in QA_ORDER]
    items.append(PlanItem(dish_id="white_rice", quantity=4))
    return menu, items


def _hot(menu, items):
    return sum(enough.is_hot(menu.dish(i.dish_id)) for i in items)


def test_top_up_adds_the_missing_hot_dish(cafe_china):
    menu, items = cafe_china
    req = TableRequest(menu_id="cafe_china", diners=D, budget_per_person=40)
    assert _hot(menu, items) == 3
    out = enough.top_up(menu, req, items)
    assert out is not None, "a hot dish fits the budget and must be added"
    new, added, _ = out
    assert _hot(menu, new) >= 4
    ids = [i.dish_id for i in new]
    assert not staple_repeats(menu, req, ids), "never a second fried rice"
    assert validate_order(menu, req, new)["valid"]
    for a in added:
        d = menu.dish(a)
        assert enough.is_hot(d) and not any(enough.spice.taste(d, p) for p in D)
    # Ben's own gap is the menu's (no vegetarian hot dish he can eat without asking); the
    # message says so and no longer claims the table is short of hot dishes
    line = enough.honest_line(menu, req, new)
    assert line and "Ben" in line and "This menu" in line and "hot dishes for" not in line


def test_message_explains_the_hot_dish_gap_by_budget(cafe_china):
    menu, items = cafe_china
    tight = TableRequest(menu_id="cafe_china", diners=D, budget_per_person=22)
    line = enough.honest_line(menu, tight, items)
    assert "only 3 hot dishes for 4 people" in line
    assert "cheapest other hot dish costs" in line  # the budget, said plainly
    assert "Ben" in line
