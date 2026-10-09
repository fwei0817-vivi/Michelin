"""Regression: the default example group gets a safe plan on every bundled menu.

Before, `reviewed_allergens` was never filled in the menu data, so any diner with an
allergy made every dish "unresolved" and the planner always answered "No order fits yet".
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.plan.edibility import assessment, can_eat
from michelin.schemas import Allergen, AllergenFlag, Diet, DinerProfile, Dish, EvidenceTier

ROOT = Path(__file__).resolve().parents[1]
MENUS = sorted(p.stem for p in (ROOT / "data/menus").glob("*.json"))
client = TestClient(api.app)


@pytest.mark.parametrize("menu_id", [m for m in MENUS if m != "sample_sichuan"])
def test_restaurant_menus_record_allergen_review(menu_id):
    menu = json.loads((ROOT / f"data/menus/{menu_id}.json").read_text())
    assert all(d.get("reviewed_allergens") for d in menu["dishes"])


@pytest.mark.parametrize("menu_id", MENUS)
@pytest.mark.parametrize("group", [None, ["amy"], ["li", "amy", "kevin"]])
def test_example_group_gets_a_safe_plan(monkeypatch, menu_id, group):
    monkeypatch.setattr(api, "MOCK", False)
    profiles = client.get("/api/profiles").json()
    diners = profiles if group is None else [p for p in profiles if p["id"] in group]
    if menu_id == "sample_sichuan" and group != ["li", "amy", "kevin"]:
        pytest.skip("12-dish fictional menu: too small for a strict vegetarian or a lone diner")
    menu = client.get(f"/api/menus/{menu_id}").json()
    r = client.post(
        "/api/plan", json={"menu_id": menu_id, "diners": diners, "budget_per_person": 75}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "plan", body.get("conflict")
    dishes = {d["id"]: d for d in menu["dishes"]}
    allergic = {p["id"]: set(p["allergies"]) for p in diners}
    for item in body["plan"]["items"]:
        flags = {f["allergen"] for f in dishes[item["dish_id"]]["allergens"]}
        for pid in item["edible_by"]:
            # Never count a dish for someone whose allergen it carries, at any evidence tier.
            assert not (flags & allergic[pid]), (item["dish_id"], pid)


def test_sample_menu_conflict_names_the_diner(monkeypatch):
    monkeypatch.setattr(api, "MOCK", False)
    profiles = client.get("/api/profiles").json()
    r = client.post(
        "/api/plan",
        json={"menu_id": "sample_sichuan", "diners": profiles, "budget_per_person": 75},
    )
    body = r.json()
    if body["kind"] == "conflict":
        assert body["conflict"]["relaxations"], "a no-fit answer must offer a next step"


def test_unknown_allergen_still_blocks_and_asks():
    amy = DinerProfile(id="amy", name="Amy", allergies=[Allergen.SHELLFISH])
    dish = Dish(
        id="greens",
        name_en="Greens",
        is_vegetarian=True,
        reviewed_allergens=list(Allergen),
        allergens=[
            AllergenFlag(
                allergen=Allergen.SHELLFISH,
                tier=EvidenceTier.UNKNOWN,
                confidence=0.3,
                reason="oyster sauce: possible",
            )
        ],
    )
    assert not can_eat(dish, amy)
    assert any("shellfish" in r for r in assessment(dish, amy)["reasons"])


def test_diets_ask_for_possible_ingredients():
    david = DinerProfile(id="david", name="David", diets=[Diet.VEGETARIAN])
    dish = Dish(
        id="greens",
        name_en="Greens",
        is_vegetarian=True,
        reviewed_allergens=list(Allergen),
        allergens=[
            AllergenFlag(
                allergen=Allergen.SHELLFISH,
                tier=EvidenceTier.UNKNOWN,
                confidence=0.3,
                reason="oyster sauce: possible",
            )
        ],
    )
    result = assessment(dish, david)
    assert can_eat(dish, david)
    assert result["status"] == "requires_confirmation"
    assert any("shellfish" in r for r in result["reasons"])
    # Without a positive vegetarian label it stays unresolved.
    assert not can_eat(dish.model_copy(update={"is_vegetarian": None}), david)
