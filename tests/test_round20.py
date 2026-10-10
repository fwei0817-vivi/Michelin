"""2026-10-10: refines ('Change suggestions', incl. less spicy) and AI single-dish swaps use
the plan cache: the same request again makes zero AI calls, even with the AI disabled."""

import json

import pytest
from test_round11 import HOT, SAMPLE, Fake, _order, client, demo  # noqa: F401
from test_round15 import _body, _plan, _setup, mia_facts  # noqa: F401

from michelin.plan import ai_swap, llm_planner

pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]


def _boom(*a, **k):
    raise AssertionError("AI was called")


def test_refine_second_identical_call_makes_no_ai_call(demo, monkeypatch):  # noqa: F811
    fake = Fake(_order(["kung_pao_chicken", "garlic_seasonal_greens"], ["li", "jo"], "x"))
    monkeypatch.setattr(llm_planner, "_ask", fake)
    body = {**SAMPLE, "feedback": {"chips": ["less_spicy"], "text": "more veg", "current": HOT}}
    first = client.post("/api/plan", json=body).json()
    n = len(fake.calls)
    assert n >= 1 and first["kind"] == "plan"
    monkeypatch.setattr(llm_planner, "_ask", _boom)
    monkeypatch.setattr(llm_planner, "enabled", lambda: False)  # AI off entirely
    again = client.post("/api/plan", json=body).json()
    assert again["kind"] == "plan"
    assert again["plan"]["items"] == first["plan"]["items"]
    assert again["change_note"] == first["change_note"]


def test_ai_swap_second_identical_call_makes_no_ai_call(demo, mia_facts, monkeypatch):  # noqa: F811
    menu, diners = _setup(demo)
    plan = _plan(menu, diners)
    calls = []

    def fake(t, s, c):
        calls.append(1)
        return json.dumps({"dish_id": "eight_treasure_sticky_rice", "reason": "x"}), "fake"

    monkeypatch.setattr(ai_swap, "_ask", fake)
    body = _body(menu, diners, plan=plan, dish_id="pumpkin_cake_3")
    first = client.post("/api/plan/swap", json=body).json()
    assert first["kind"] == "plan" and calls
    monkeypatch.setattr(ai_swap, "_ask", _boom)
    monkeypatch.setattr(llm_planner, "enabled", lambda: False)
    again = client.post("/api/plan/swap", json=body).json()
    assert again["kind"] == "plan" and again["new_dish_id"] == first["new_dish_id"]
    assert again["plan"]["items"] == first["plan"]["items"]
    assert again["message"] == first["message"]
    # a different current order is a different key: no cached answer, AI is off -> honest
    body2 = _body(menu, diners, plan=plan, dish_id="cucumber_salad_garlic")
    r = client.post("/api/plan/swap", json=body2).json()
    assert r["kind"] == "failed" and "No AI model" in r["message"]


def test_refine_different_text_is_not_served_from_cache(demo, monkeypatch):  # noqa: F811
    fake = Fake(_order(["kung_pao_chicken", "garlic_seasonal_greens"], ["li", "jo"], "x"))
    monkeypatch.setattr(llm_planner, "_ask", fake)
    body = {**SAMPLE, "feedback": {"chips": ["less_spicy"], "text": "a", "current": HOT}}
    client.post("/api/plan", json=body)
    n = len(fake.calls)
    body["feedback"]["text"] = "b"
    client.post("/api/plan", json=body)
    assert len(fake.calls) > n


def test_staple_by_name_is_a_staple():
    from michelin.plan import courses
    from michelin.schemas import Dish

    d = Dish(id="r", name_en="House Special Fried Rice", price=12, category="other")
    assert courses._course(d, {}) == "staple"
    d = Dish(id="n", name_en="Beef Chow Fun", price=14, category="stir_fry")
    assert courses._course(d, {}) == "staple"
    d = Dish(id="c", name_en="Cold Sesame Noodles", price=8, category="cold_appetizer")
    assert courses._course(d, {}) == "cold"
