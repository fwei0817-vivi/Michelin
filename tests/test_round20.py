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


def test_still_short_after_retry_says_exactly_what_is_missing(monkeypatch, tmp_path):
    from test_round19 import _d, _menu, _req

    from michelin.schemas import DinerProfile, PlanItem

    m = _menu(
        [
            _d("cold1", "cold_appetizer", 8),
            _d("soup1", "soup", 6),
            _d("tofu", "stir_fry", 14),
            _d("greens", "stir_fry", 12),
            _d("noodle", "other", 13, "staple"),
        ]
    )
    diners = [DinerProfile(id="p", name="Pat"), DinerProfile(id="q", name="Quinn")]
    short = json.dumps(
        {
            "dishes": [
                {"dish_id": i, "reason": "", "for": ["p", "q"], "server_question": ""}
                for i in ("cold1", "tofu")
            ],
            "server_questions": [],
            "summary": "",
        }
    )
    calls = []

    def fake(turns, schema, menu, request, client):
        calls.append(1)
        return short, "fake"

    monkeypatch.setattr(llm_planner, "_ask", fake)
    monkeypatch.setattr(llm_planner, "COVERAGE_NUDGE", False)
    monkeypatch.setattr(llm_planner, "enabled", lambda: True)
    out = llm_planner.plan(m, _req(diners, 60), cache_path=tmp_path / "c.json")
    assert len(calls) == 2 and out.plan is not None  # one retry, then the order is kept
    check = next(c for c in out.plan.checks if c.name == "enough")
    assert not check.passed
    assert check.detail == "This order has only 1 hot dish for 2 people.", check.detail
    # a diner short of dishes is named with exactly what they lack
    from michelin.plan import enough

    items = [PlanItem(dish_id=i, quantity=1) for i in ("cold1", "soup1", "tofu")]
    line = enough.honest_line(
        m, _req([*diners, DinerProfile(id="v", name="Val", allergies=["soy"])], 60), items
    )
    assert "Val has" in line and "they can eat without asking" in line, line
    assert check.detail in out.plan.summary  # the subtitle says it too
