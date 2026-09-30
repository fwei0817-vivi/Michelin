import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from michelin import api
from michelin.plan.budget import totals
from michelin.plan.edibility import assessment, can_eat
from michelin.plan.optimizer import solve
from michelin.plan.validation import validate_order
from michelin.schemas import AllergenFlag, DinerProfile, Dish, Menu, Plan, PlanItem, TableRequest

FIXTURE = json.loads((Path(__file__).parent / "fixtures/public_menus.json").read_text())


def people(n=4, **kw):
    return [DinerProfile(id=f"synthetic-{i}", name=f"Synthetic {i}", **kw) for i in range(n)]


def request(n=4, **kw):
    return TableRequest(
        menu_id="test", diners=people(n), budget_per_person=100, min_dishes_per_person=1, **kw
    )


def public_menu(index=0):
    return Menu.model_validate(FIXTURE["menus"][index])


def test_public_price_quantities_exact_edge_and_one_cent_over():
    menu = public_menu()
    items = [
        PlanItem(dish_id="pot_stickers", quantity=2),
        PlanItem(dish_id="mapo"),
        PlanItem(dish_id="rice", quantity=4),
    ]
    req = request(tax_rate=0, tip_rate=0)
    report = validate_order(menu, req, items)
    assert report["totals"]["subtotal"] == 51
    # Boundary arithmetic is a synthetic no-fee scenario, not an all-in restaurant quote.
    assert totals(51, 1, 0, 0).total == 51
    req = req.model_copy(update={"budget_per_person": 12.75})
    assert not any(r["code"] == "over_budget" for r in validate_order(menu, req, items)["reasons"])
    # one diner and no staple/coverage feasibility assertion: exact total budget $50.99
    req = req.model_copy(update={"diners": people(1), "budget_per_person": 50.99})
    assert any(r["code"] == "over_budget" for r in validate_order(menu, req, items)["reasons"])
    assert totals(12 * 3, 1, 0, 0).subtotal == 36
    assert FIXTURE["pieces_per_order"]["cafe_china_regular"]["pot_stickers"] * 3 == 12
    assert FIXTURE["pieces_per_order"]["cafe_china_regular"]["scallion_pancakes"] is None
    assert FIXTURE["pieces_per_order"]["chili_regular"]["scallion_pancakes"] == 6
    chili = validate_order(
        public_menu(1), request(2), [PlanItem(dish_id="mapo"), PlanItem(dish_id="rice", quantity=2)]
    )
    assert chili["totals"]["subtotal"] == 26


def test_public_hidden_ingredients_and_unknowns():
    menu = public_menu()
    assert assessment(menu.dish("fish"), people(1, diets=["no_pork"])[0])["status"] == "conflict"
    assert (
        assessment(menu.dish("chive_pancakes"), people(1, allergies=["shellfish"])[0])["status"]
        == "conflict"
    )
    assert (
        assessment(public_menu(1).dish("bok_choy"), people(1, allergies=["sesame"])[0])["status"]
        == "requires_confirmation"
    )
    assert (
        assessment(menu.dish("mapo"), people(1, diets=["vegan"])[0])["status"]
        == "requires_confirmation"
    )
    assert (
        assessment(menu.dish("mapo"), people(1, diets=["vegetarian"])[0])["status"]
        == "validated_under_known_data"
    )
    person = people(1, allergies=["egg"])[0]
    dish = Dish(
        id="synthetic",
        reviewed_allergens=["egg"],
        allergens=[
            AllergenFlag(allergen="egg", tier="unknown", confidence=0, reason="Sauce unknown")
        ],
    )
    assert not can_eat(dish, person)  # review never overrides conflicting/unknown evidence


@pytest.mark.parametrize("price", [-1, float("inf"), float("nan"), "not a price", 1.001])
def test_malformed_prices_fail_closed(price):
    with pytest.raises(ValidationError):
        Dish(id="bad", price=price)


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "2", 101])
def test_quantities_must_be_positive_bounded_integers(quantity):
    with pytest.raises(ValidationError):
        PlanItem(dish_id="x", quantity=quantity)


def test_missing_price_never_free():
    menu = public_menu()
    menu.dish("mapo").price = None  # explicitly synthetic mutation
    report = validate_order(menu, request(), [PlanItem(dish_id="mapo")])
    assert report["totals"] is None
    assert "missing_price" in {r["code"] for r in report["reasons"]}
    client = TestClient(api.app)
    result = client.post(
        "/api/plan",
        json={
            "menu_id": "test",
            "menu_override": menu.model_dump(),
            "diners": [p.model_dump() for p in people()],
            "budget_per_person": 100,
        },
    )
    assert result.status_code == 422


def synthetic_menu():
    return Menu(
        restaurant_id="synthetic",
        restaurant_name="Synthetic",
        cuisine="test",
        source="synthetic",
        verified=True,
        dishes=[
            Dish(id="rice", category="staple", price=1, is_vegan=True),
            Dish(id="a", price=5, is_vegan=True),
            Dish(id="b", price=5, is_vegan=True),
            Dish(id="c", price=5, is_vegan=True),
            Dish(id="pork", price=5, is_vegan=False),
        ],
    )


def test_whole_order_swaps_and_changed_inputs():
    menu, req = synthetic_menu(), request(3)
    plan = solve(menu, req)
    assert isinstance(plan, Plan)
    assert validate_order(menu, req, plan.items)["valid"]
    items = [PlanItem(dish_id=x) for x in ["a", "b", "pork"]] + [
        PlanItem(dish_id="rice", quantity=3)
    ]
    assert validate_order(menu, req, items)["valid"]
    vegan = req.model_copy(update={"diners": people(3, diets=["vegan"])})
    assert not validate_order(menu, vegan, items)["valid"]
    swapped = items[:2] + [PlanItem(dish_id="c"), items[-1]]
    assert validate_order(menu, vegan, swapped)["valid"]
    assert not validate_order(menu, req.model_copy(update={"budget_per_person": 1}), swapped)[
        "valid"
    ]
    assert not validate_order(menu, req.model_copy(update={"excluded_dish_ids": ["c"]}), swapped)[
        "valid"
    ]
    assert not validate_order(menu, req, swapped + [PlanItem(dish_id="a")])["valid"]
    assert not validate_order(menu, req, [PlanItem(dish_id="missing")])["valid"]


def test_provable_no_solution_vs_missing_information():
    menu = synthetic_menu()
    req = request(3).model_copy(update={"budget_per_person": 1})
    assert solve(menu, req).code == "no_solution"
    req = req.model_copy(update={"diners": people(3, allergies=["sesame"])})
    assert solve(menu, req).code == "missing_information"


def test_mocked_planner_and_explanation_fail_closed(monkeypatch):
    client, menu = TestClient(api.app), synthetic_menu()
    body = {
        "menu_id": "test",
        "menu_override": menu.model_dump(),
        "diners": [p.model_dump() for p in people(3)],
        "budget_per_person": 100,
        "explain": True,
    }
    monkeypatch.setattr(api, "MOCK", False)
    monkeypatch.setattr(api, "solve", lambda *a: {"items": [{"dish_id": "a", "quantity": -1}]})
    assert client.post("/api/plan", json=body).status_code == 502
    monkeypatch.setattr(api, "solve", solve)
    monkeypatch.setattr(api, "explain", lambda plan, *a: plan.model_copy(update={"total": 0}))
    assert client.post("/api/plan", json=body).status_code == 502
    monkeypatch.setattr(api, "explain", lambda *a: None)
    assert client.post("/api/plan", json=body).status_code == 502


def test_decimal_rounding():
    assert totals(1, 1, 0.005, 0.005).total == 1.02
    assert totals(2.675, 1, 0, 0).subtotal == 2.68


def test_order_endpoint_and_valid_plan(monkeypatch):
    monkeypatch.setattr(api, "MOCK", False)
    client, menu, req = TestClient(api.app), synthetic_menu(), request(3)
    result = client.post(
        "/api/plan",
        json={
            "menu_id": "test",
            "menu_override": menu.model_dump(),
            "diners": [p.model_dump() for p in req.diners],
            "budget_per_person": 100,
        },
    )
    assert result.status_code == 200 and result.json()["kind"] == "plan"
    plan = result.json()["plan"]
    result = client.post(
        "/api/order/validate",
        json={"menu": menu.model_dump(), "request": req.model_dump(), "items": plan["items"]},
    )
    assert result.status_code == 200 and result.json()["valid"]


def test_explanation_exception_and_timeout_are_actionable(monkeypatch):
    client, menu = TestClient(api.app), synthetic_menu()
    body = {
        "menu_id": "test",
        "menu_override": menu.model_dump(),
        "diners": [p.model_dump() for p in people(3)],
        "budget_per_person": 100,
        "explain": True,
    }
    monkeypatch.setattr(api, "MOCK", False)

    def fail(*args):
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(api, "explain", fail)
    assert client.post("/api/plan", json=body).status_code == 502

    def timeout(*args):
        raise TimeoutError("Retry with a smaller menu")

    monkeypatch.setattr(api, "solve", timeout)
    assert client.post("/api/plan", json=body).status_code == 503


def test_duplicate_people_are_rejected():
    client = TestClient(api.app)
    person = {"id": "same", "name": "Synthetic"}
    result = client.post(
        "/api/plan",
        json={"menu_id": "sample_sichuan", "diners": [person, person], "budget_per_person": 30},
    )
    assert result.status_code == 422


def test_total_budget_applies_to_same_four_people_at_exact_cent_boundary():
    menu = public_menu()
    items = [
        PlanItem(dish_id="pot_stickers", quantity=2),
        PlanItem(dish_id="mapo"),
        PlanItem(dish_id="rice", quantity=4),
    ]
    req = request(tax_rate=0, tip_rate=0, budget_total=51)
    assert not any(r["code"] == "over_budget" for r in validate_order(menu, req, items)["reasons"])
    req = req.model_copy(update={"budget_total": 50.99})
    assert any(r["code"] == "over_budget" for r in validate_order(menu, req, items)["reasons"])


def test_plan_endpoint_forwards_authoritative_total_budget():
    menu = public_menu()
    response = TestClient(api.app).post(
        "/api/plan",
        json={
            "menu_id": "synthetic",
            "menu_override": menu.model_dump(mode="json"),
            "diners": [p.model_dump(mode="json") for p in people(3)],
            "budget_per_person": 100,
            "budget_total": 1,
            "tax_rate": 0,
            "tip_rate": 0,
            "min_dishes_per_person": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "conflict"
    assert response.json()["subtotal_cap"] == 1
