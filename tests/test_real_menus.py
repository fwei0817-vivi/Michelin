"""Findings from real NYC menus (test-menus/): no plain rice on the page, 40+ dishes."""

import base64

from fastapi.testclient import TestClient

from michelin import api
from michelin.parse import vision
from michelin.plan import hints
from michelin.plan.validation import validate_order
from michelin.schemas import Allergen, DinerProfile, Dish, Menu, PlanItem, TableRequest

PNG = b"\x89PNG\r\n\x1a\nfake"


def _dim_sum() -> Menu:
    dishes = [
        Dish(
            id="greens",
            name_en="Chinese Greens",
            price=13,
            is_vegetarian=True,
            is_vegan=True,
            contains_pork=False,
            contains_beef=False,
            reviewed_allergens=list(Allergen),
        ),
        Dish(
            id="noodle",
            name_en="Pan-Fried Noodle",
            price=13.5,
            is_vegetarian=True,
            contains_pork=False,
            contains_beef=False,
            reviewed_allergens=list(Allergen),
        ),
    ]
    return Menu(
        restaurant_id="nw",
        restaurant_name="Nom Wah",
        cuisine="x",
        source="t",
        dishes=dishes,
        verified=True,
    )


def test_a_menu_without_plain_rice_can_still_be_planned():
    """Nom Wah, Hwa Yuan and Cafe Mandarin print no plain rice. Every order failed
    "one staple per diner" and the planner said nobody could eat anything at $40."""
    menu = _dim_sum()
    diners = [
        DinerProfile(id="a", name="Ann"),
        DinerProfile(id="b", name="Bo", diets=["vegetarian"]),
    ]
    request = TableRequest(menu_id="nw", diners=diners, budget_per_person=40)
    items = [PlanItem(dish_id="greens", quantity=1), PlanItem(dish_id="noodle", quantity=1)]
    assert validate_order(menu, request, items)["valid"]
    assert hints.analyse(menu, request).feasible is True
    # With plain rice everyone can eat, rice is still required.
    rice = Dish(
        id="rice",
        name_en="Steamed Rice",
        price=2,
        category="staple",
        is_vegetarian=True,
        is_vegan=True,
        contains_pork=False,
        contains_beef=False,
        reviewed_allergens=list(Allergen),
    )
    with_rice = menu.model_copy(update={"dishes": [*menu.dishes, rice]})
    assert not validate_order(with_rice, request, items)["valid"]
    assert validate_order(with_rice, request, [*items, PlanItem(dish_id="rice", quantity=2)])[
        "valid"
    ]


def test_photo_keeps_up_to_80_dishes_and_says_what_it_dropped(monkeypatch):
    """Real menus run 45-55 lines (more once choices become versions); the first 40 were
    kept silently."""
    rows = [{"name_en": f"Dish {i}", "price": 5 + i % 7} for i in range(85)]
    dishes = vision.rows_to_dishes(rows)
    assert len(dishes) == 85
    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(vision, "read_menu_photo", lambda *_a, **_k: (dishes, "Big", "m"))
    r = TestClient(api.app).post(
        "/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()}
    )
    body = r.json()
    assert r.status_code == 200 and len(body["dishes"]) == 80
    assert "lists 85 dishes; only the first 80 were kept" in body["notice"]
