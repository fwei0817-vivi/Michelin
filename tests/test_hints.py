"""Deterministic hints: the minimal budget is really minimal, and fast."""

import itertools
import json
import time
from pathlib import Path

import pytest

from michelin.plan import hints
from michelin.plan.budget import cents
from michelin.plan.validation import validate_order
from michelin.schemas import DinerProfile, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = [
    DinerProfile.model_validate(r)
    for r in json.loads((ROOT / "data/profiles/sample_group.json").read_text())
]


def brute_force_cheapest(menu, request):
    """Cheapest valid order (budget ignored) by trying every subset of shared dishes."""
    loose = request.model_copy(update={"budget_per_person": 10_000})
    shared = [d for d in menu.dishes if d.category.value != "staple"]
    order, _ = hints.cheapest_order(menu, request)
    rice = [
        PlanItem(dish_id=d.id, quantity=q) for d, q in order or [] if d.category.value == "staple"
    ]
    best = None
    for r in range(1, 5):
        for combo in itertools.combinations(shared, r):
            items = [PlanItem(dish_id=d.id, quantity=1) for d in combo] + rice
            if validate_order(menu, loose, items)["valid"]:
                cost = sum(cents(d.price) for d in combo)
                best = cost if best is None else min(best, cost)
    return best


@pytest.mark.parametrize(
    "people",
    [
        SAMPLE[:2],
        SAMPLE,
        [
            DinerProfile(id="v", name="V", diets=["vegan"]),
            DinerProfile(id="p", name="P", allergies=["peanut", "soy"]),
        ],
    ],
)
def test_cheapest_order_matches_brute_force(people):
    menu = Menu.model_validate_json((ROOT / "data/menus/sample_sichuan.json").read_text())
    request = TableRequest(menu_id="x", diners=people, budget_per_person=5)
    order, complete = hints.cheapest_order(menu, request)
    expected = brute_force_cheapest(menu, request)
    assert complete
    if expected is None:
        assert order is None
    else:
        got = sum(cents(d.price) for d, _ in order if d.category.value != "staple")
        assert got == expected


@pytest.mark.parametrize("name", ["cafe_china", "chili", "atlas_kitchen", "sample_sichuan"])
def test_min_budget_is_minimal_and_quick(name):
    menu = Menu.model_validate_json((ROOT / f"data/menus/{name}.json").read_text())
    request = TableRequest(menu_id="x", diners=SAMPLE, budget_per_person=3)
    start = time.monotonic()
    found = hints.analyse(menu, request)
    assert time.monotonic() - start < 1.0
    assert found.feasible is False and found.min_budget is not None
    at = request.model_copy(update={"budget_per_person": found.min_budget})
    below = request.model_copy(update={"budget_per_person": found.min_budget - 0.5})
    assert hints.fits(menu, at) is True and hints.fits(menu, below) is False


def test_questions_are_merged_per_dish():
    from michelin.plan.edibility import merge_questions
    from michelin.schemas import Dish

    egg = Dish(id="egg", name_en="Eggplant with Garlic Sauce", price=15.5, category="stir_fry")
    qs = [
        "Eggplant with Garlic Sauce: ask whether it uses minced pork.",
        "Eggplant with Garlic Sauce (for Ben, Cai): Confirm pork ingredient/preparation",
        "Eggplant with Garlic Sauce (for Ben): Confirm pork ingredient/preparation",
        "Is the fish fresh today?",
    ]
    assert merge_questions(qs, [egg]) == [
        (
            "Eggplant with Garlic Sauce (for Ben, Cai): ask whether it uses minced pork; "
            "confirm pork ingredient/preparation."
        ),
        "Is the fish fresh today?",
    ]
