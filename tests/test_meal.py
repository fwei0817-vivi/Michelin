"""Synthetic contradictions and meal actions, not additional restaurant facts."""

import pytest
from fastapi.testclient import TestClient

from michelin.api import app
from michelin.plan.edibility import assessment, open_questions
from michelin.plan.portions import units
from michelin.schemas import DinerProfile, Dish, TableRequest

client = TestClient(app)


@pytest.mark.parametrize(
    "dish,restriction,status",
    [
        ({"is_vegetarian": True, "contains_pork": True}, {"diets": ["vegetarian"]}, "conflict"),
        ({"is_vegan": True, "is_vegetarian": False}, {"diets": ["vegan"]}, "conflict"),
        (
            {
                "is_vegan": True,
                "allergens": [
                    {"allergen": "egg", "tier": "menu", "confidence": 1, "reason": "egg"}
                ],
            },
            {"diets": ["vegan"]},
            "conflict",
        ),
        ({"is_vegetarian": True}, {"diets": ["vegetarian"]}, "validated_under_known_data"),
        ({}, {"diets": ["vegetarian"]}, "requires_confirmation"),
        (
            {"is_vegetarian": True, "main_ingredients": [{"name": "minced pork", "tier": "menu"}]},
            {"diets": ["vegetarian"]},
            "conflict",
        ),
        (
            {
                "reviewed_allergens": ["sesame"],
                "main_ingredients": [{"name": "sesame paste", "tier": "menu"}],
            },
            {"allergies": ["sesame"]},
            "conflict",
        ),
        (
            {"is_vegan": True, "main_ingredients": [{"name": "egg", "tier": "unknown"}]},
            {"diets": ["vegan"]},
            "requires_confirmation",
        ),
        (
            {"is_vegan": True, "main_ingredients": [{"name": "eggplant", "tier": "menu"}]},
            {"diets": ["vegan"]},
            "validated_under_known_data",
        ),
    ],
)
def test_contradictions(dish, restriction, status):
    assert (
        assessment(
            Dish(id="d", name_en="Synthetic", **dish), DinerProfile(id="p", name="P", **restriction)
        )["status"]
        == status
    )


def test_unknown_values_remain_unknown_and_estimate_is_disclosed():
    dish = Dish(id="d", name_en="Synthetic")
    assert dish.spice_level is None and dish.portion is None
    assert units(dish) == 1
    assert any("portion unknown" in x for x in open_questions(dish, []))
    assert any("spice level unknown" in x for x in open_questions(dish, []))


def test_meal_actions_identity_and_explicit_loading():
    first = {"id": "p", "name": "Same name", "allergies": ["sesame"], "likes": ["tofu"]}
    second = {"id": "q", "name": "Same name"}

    def action(diners, action, **extra):
        return client.post("/api/meal/people", json={"diners": diners, "action": action, **extra})

    added = action([first], "add", person=second).json()
    assert added["recommendation_invalidated"] is True
    assert len(added["diners"]) == 2
    assert action([first], "add", person=first).status_code == 422
    loaded = action(
        added["diners"], "load_preferences", saved=[{**first, "allergies": [], "likes": ["rice"]}]
    ).json()["diners"]
    assert loaded[0]["allergies"] == ["sesame"] and loaded[0]["likes"] == ["rice"]
    assert loaded[1]["id"] == "q"
    updated = action(loaded, "update", person={**first, "diets": ["no_pork"]}).json()["diners"]
    assert updated[0]["diets"] == ["no_pork"]
    assert len(action(updated, "remove", person_id="q").json()["diners"]) == 1
    assert action([], "remove", person_id="q").status_code == 422
    assert action([], "unknown").status_code == 422
    assert action([first, first], "remove", person_id="p").status_code == 422
    six = [{"id": str(i), "name": "Synthetic"} for i in range(6)]
    assert action(six, "load_preferences", saved=[first]).status_code == 422


def test_total_budget_is_authoritative_and_does_not_round_per_person():
    req = TableRequest(
        menu_id="m",
        diners=[DinerProfile(id=str(i), name="P") for i in range(3)],
        budget_per_person=100,
        budget_total=50.99,
    )
    assert req.all_in_budget == 50.99
    assert req.model_copy(update={"budget_total": None}).all_in_budget == 300
    with pytest.raises(ValueError):
        TableRequest(**{**req.model_dump(), "budget_total": 50.991})
