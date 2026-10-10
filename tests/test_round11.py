"""Regression tests for QA round 11 (b8f2622): less spicy and dish-only questions."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.parse import vision
from michelin.plan import dish_facts, llm_planner, refine

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]
client = TestClient(api.app)


class Fake:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, turns, schema, menu, table, c):
        self.calls.append(1)
        return json.dumps(self.answer), "fake"


def _order(ids, who, note=""):
    return {
        "dishes": [{"dish_id": i, "reason": "", "for": who, "server_question": ""} for i in ids],
        "server_questions": [],
        "change_note": note,
    }


@pytest.fixture
def demo(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "READ_CACHE", ROOT / "data/menu_reads")
    facts = tmp_path / "facts.json"
    facts.write_text((ROOT / "data/facts/dish_facts.json").read_text())
    monkeypatch.setattr(dish_facts, "CACHE_PATH", facts)
    monkeypatch.setattr(llm_planner, "CACHE_PATH", tmp_path / "plans.json")
    monkeypatch.setattr(llm_planner, "enabled", lambda: True)
    key = vision.read_key([(ROOT / "test-menus/cafe-mandarin.pdf").read_bytes()])
    dishes = vision.rows_to_dishes(vision.cached_read(key)["rows"])
    menu = {
        "restaurant_id": "local-1",
        "restaurant_name": "Cafe Mandarin",
        "cuisine": "custom",
        "source": "User-imported menu",
        "currency": "USD",
        "verified": True,
        "dishes": [d.model_dump(mode="json") for d in dishes],
    }
    return menu, json.loads((FIX / "qa_r11_diners.json").read_text())


def test_r11_repro_less_spicy_on_a_gentle_hand_edited_order_is_already_gentle(demo, monkeypatch):
    menu, diners = demo
    # Plan was Cucumber (Garlic), Sesame (Tofu), Hong Kong Rice Noodle, Tomato & Egg; the
    # user swapped Sesame (Tofu) for Cucumber Salad (Spicy Chili Oil), then pressed less spicy.
    current = [
        "cucumber_salad_garlic",
        "sichuan_crispy_eggplant",  # a little spicy (r20: chili-oil cucumber is now Spicy)
        "hong_kong_rice_noodle",
        "tomato_egg",
    ]
    fake = Fake(
        _order(
            [
                "cucumber_salad_garlic",
                "chilled_zucchini_in_tangy_sauce",
                "hong_kong_rice_noodle",
                "tomato_egg",
            ],
            ["alice"],
            "Replaced the spicy cucumber salad with a little spicy zucchini",
        )
    )
    monkeypatch.setattr(llm_planner, "_ask", fake)
    r = client.post(
        "/api/plan",
        json={
            "menu_id": "local-1",
            "menu_override": menu,
            "diners": diners,
            "budget_per_person": 40,
            "tax_rate": 0.08875,
            "tip_rate": 0.18,
            "excluded_dish_ids": ["sesame_tofu"],
            "feedback": {
                "chips": ["less_spicy"],
                "text": "",
                "current": [{"dish_id": i, "quantity": 1} for i in current],
            },
        },
    ).json()
    assert fake.calls == []  # 0 AI calls
    assert r["kind"] == "plan" and r["change_note"].startswith(refine.ALREADY_MILD)
    assert sorted(i["dish_id"] for i in r["plan"]["items"]) == sorted(current)


SAMPLE = {
    "menu_id": "sample_sichuan",
    "diners": [{"id": "li", "name": "Li"}, {"id": "jo", "name": "Jo"}],
    "budget_per_person": 40,
}
HOT = [
    {"dish_id": "mapo_tofu", "quantity": 1},
    {"dish_id": "kung_pao_chicken", "quantity": 1},
    {"dish_id": "steamed_rice", "quantity": 2},
]


def test_fewer_spicy_dishes_alone_is_not_less_spicy(demo, monkeypatch):
    # Drops Kung Pao (spicy) but keeps Mapo Tofu (very spicy): the hottest dish stays.
    fake = Fake(_order(["mapo_tofu", "garlic_seasonal_greens"], ["li", "jo"], "Milder now"))
    monkeypatch.setattr(llm_planner, "_ask", fake)
    r = client.post(
        "/api/plan", json={**SAMPLE, "feedback": {"chips": ["less_spicy"], "current": HOT}}
    ).json()
    assert r["change_note"].startswith("Couldn't make it less spicy")
    ids = sorted(i["dish_id"] for i in r["plan"]["items"])
    assert "garlic_seasonal_greens" not in ids and "kung_pao_chicken" in ids


def test_a_lower_top_pepper_level_is_accepted_with_a_code_note(demo, monkeypatch):
    fake = Fake(_order(["kung_pao_chicken", "garlic_seasonal_greens"], ["li", "jo"], "x"))
    monkeypatch.setattr(llm_planner, "_ask", fake)
    r = client.post(
        "/api/plan", json={**SAMPLE, "feedback": {"chips": ["less_spicy"], "current": HOT}}
    ).json()
    assert r["change_note"] == (
        "Swapped Mapo Tofu (very spicy) for Garlic Seasonal Greens (not spicy); "
        "$2.00 less in menu prices."
    )


def test_unit_rule_max_must_strictly_drop():
    from michelin.schemas import Menu

    menu = Menu.model_validate_json((ROOT / "data/menus/sample_sichuan.json").read_text())
    before = [("mapo_tofu", 1), ("kung_pao_chicken", 1)]
    assert refine.unmet(
        ["less_spicy"], menu, before, [("mapo_tofu", 1), ("garlic_seasonal_greens", 1)]
    ) == ["less_spicy"]
    assert (
        refine.unmet(
            ["less_spicy"], menu, before, [("kung_pao_chicken", 1), ("garlic_seasonal_greens", 1)]
        )
        == []
    )


def test_meal_questions_naming_a_dish_are_dropped(demo):
    """r11: 'Is the Hong Kong Rice Noodle halal (for Mia)?' on the receipt while Mia was not
    counted for it. Dish questions are the code's, for counted eaters only; the AI's
    meal-level questions that name a dish are dropped."""
    from michelin.plan.edibility import edible_by
    from michelin.schemas import DinerProfile, Menu, TableRequest

    menu_json, diners_json = demo
    menu = dish_facts.prepare(Menu.model_validate(menu_json))
    diners = [DinerProfile.model_validate(p) for p in diners_json]
    request = TableRequest(menu_id="local-1", diners=diners, budget_per_person=40)
    ids = ["cucumber_salad_garlic", "hong_kong_rice_noodle", "tomato_egg"]
    answer = _order(ids, ["alice"])
    answer["server_questions"] = ["Is the Hong Kong Rice Noodle halal (for Mia)?"]
    from michelin.schemas import PlanItem

    plan = llm_planner._to_plan(
        menu, request, answer, [PlanItem(dish_id=i, quantity=1) for i in ids]
    )
    assert "Is the Hong Kong Rice Noodle halal (for Mia)?" not in plan.confirm_with_staff
    noodle = menu.dish("hong_kong_rice_noodle")
    eaters = {p.name for p in diners if p.id in edible_by(noodle, diners)}
    item = next(i for i in plan.items if i.dish_id == "hong_kong_rice_noodle")
    for p in diners:
        if p.name not in eaters:
            assert f"(for {p.name}" not in (item.server_question or "")
            assert f" {p.name})" not in (item.server_question or "")
