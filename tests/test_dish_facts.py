"""Dish facts come from the AI (faked here); the rules enforce diners' needs on top."""

import json

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.plan import dish_facts
from michelin.plan.edibility import assessment, edible_by, risks
from michelin.schemas import DinerProfile, Dish, Menu

pytestmark = pytest.mark.real_dish_facts

FACTS = {
    "Kung Pao Chicken": {
        "ingredients": [
            {"name": "chicken", "certainty": "likely"},
            {"name": "peanuts", "certainty": "likely"},
        ],
        "allergens": [
            {"allergen": "peanut", "certainty": "likely", "why": "peanuts"},
            {"allergen": "soy", "certainty": "likely", "why": "soy sauce"},
        ],
        "pork": "no",
        "beef": "no",
        "vegetarian": "no",
        "vegan": "no",
        "spice": 2,
    },
    "Scallion Pancake": {
        "ingredients": [
            {"name": "flour", "certainty": "likely"},
            {"name": "lard", "certainty": "possible"},
        ],
        "allergens": [
            {"allergen": "wheat", "certainty": "likely", "why": "flour"},
            {"allergen": "sesame", "certainty": "possible", "why": "sesame oil"},
        ],
        "pork": "possible",
        "beef": "no",
        "vegetarian": "possible",
        "vegan": "possible",
        "spice": 0,
    },
    "Steamed Rice": {
        "ingredients": [{"name": "rice", "certainty": "likely"}],
        "allergens": [],
        "pork": "no",
        "beef": "no",
        "vegetarian": "yes",
        "vegan": "yes",
        "spice": 0,
        "category": "staple",
    },
}


class Fake:
    def __init__(self, facts=FACTS):
        self.facts, self.calls = facts, []

    def __call__(self, dishes, client=None):
        self.calls.append([d.name_en for d in dishes])
        rows = [{"id": d.id, **self.facts[d.name_en]} for d in dishes if d.name_en in self.facts]
        return json.dumps({"dishes": rows}), "fake"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")  # calls are faked
    f = Fake()
    monkeypatch.setattr(dish_facts, "_ask", f)
    return f


def menu(**over) -> Menu:
    dishes = [
        Dish(
            id="kung_pao",
            name_en="Kung Pao Chicken",
            price=16.95,
            category="stir_fry",
            # Whatever a menu file or client claims beyond name/price/category is ignored.
            is_vegetarian=True,
            description_raw="secretly vegan",
        ),
        Dish(id="pancake", name_en="Scallion Pancake", price=6.95, category="cold_appetizer"),
        Dish(id="rice", name_en="Steamed Rice", price=2.0),
    ]
    return Menu(
        restaurant_id="t", restaurant_name="T", cuisine="x", source="test", dishes=dishes, **over
    )


ALICE = DinerProfile(id="alice", name="Alice", allergies=["peanut"])
BEN = DinerProfile(id="ben", name="Ben", diets=["vegetarian"])
CAI = DinerProfile(id="cai", name="Cai", allergies=["sesame"], diets=["no_pork"])


def test_menus_keep_only_name_price_and_category():
    plain = dish_facts.bare(menu())
    kp = plain.dish("kung_pao")
    assert (kp.name_en, kp.price, kp.category.value) == ("Kung Pao Chicken", 16.95, "stir_fry")
    assert kp.is_vegetarian is None and kp.description_raw is None and not kp.allergens


def test_one_call_per_menu_then_cached(fake):
    out = dish_facts.prepare(menu())
    assert len(fake.calls) == 1 and len(fake.calls[0]) == 3
    kp = out.dish("kung_pao")
    assert kp.is_vegetarian is False  # the client's claim was dropped; the AI's facts stand
    assert {f.allergen.value for f in kp.allergens} == {"peanut", "soy"}
    assert out.dish("rice").category.value == "staple"  # filled in for an "other" row
    again = dish_facts.prepare(menu())
    assert len(fake.calls) == 1 and again == out
    assert dish_facts.known(menu())


def test_rules_enforce_diners_against_ai_facts(fake):
    m = dish_facts.prepare(menu())
    kp, pancake = m.dish("kung_pao"), m.dish("pancake")
    assert "alice" not in edible_by(kp, [ALICE]) and "ben" not in edible_by(kp, [BEN])
    # Allergies are strict: a "possible" sesame keeps Cai off the pancake.
    assert edible_by(pancake, [CAI]) == []
    # Diets ask: possibly-lard pancake stays allowed for Ben, with a server question.
    assert edible_by(pancake, [BEN]) == ["ben"]
    asked = risks(pancake, [ALICE, BEN])
    assert any("lard" in r.about and r.names == ["Ben"] for r in asked)
    assert assessment(pancake, ALICE)["eligible"]


def test_no_ai_means_unknown_and_conservative(monkeypatch):
    for name in ("OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    m = dish_facts.prepare(menu())
    kp = m.dish("kung_pao")
    assert kp.is_vegetarian is None and not kp.allergens
    assert edible_by(kp, [ALICE, BEN, CAI]) == []
    assert edible_by(kp, [DinerProfile(id="x", name="X")]) == ["x"]
    assert not dish_facts.known(menu())


def test_malformed_answers_stay_unknown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    bad = {"Kung Pao Chicken": {"allergens": [{"allergen": "plutonium", "certainty": "likely"}]}}
    monkeypatch.setattr(dish_facts, "_ask", Fake(bad))
    kp = dish_facts.prepare(menu()).dish("kung_pao")
    assert not kp.allergens and kp.is_vegetarian is None and kp.contains_pork is None


def test_api_uses_ai_facts_not_the_clients(fake):
    client = TestClient(api.app)
    body = menu(verified=True).model_dump(mode="json")
    r = client.post("/api/menu/evaluate", json={"menu": body, "diners": [BEN.model_dump()]})
    assert r.status_code == 200
    assert r.json()["kung_pao"]["edible_by"] == []  # the client said vegetarian; the AI did not
    assert len(fake.calls) == 1
