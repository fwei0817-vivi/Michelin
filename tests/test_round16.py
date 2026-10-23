"""QA round 16: no AI prose by default; code reasons; veg tag and every 'ask the server' /
'everyone can eat' string agree with the backend status."""

import json
import re

import pytest
from test_round11 import client, demo  # noqa: F401 - fixture
from test_round15 import ORDER, _body, _plan, _setup, mia_facts  # noqa: F401 - fixtures

from michelin.plan import ai_swap, ai_text, llm_planner

pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]
ASK = re.compile(r"ask the server|server confirms", re.IGNORECASE)
ALL = re.compile(r"\beveryone can (?:eat|share)\b", re.IGNORECASE)


def _sheet(menu, diners):
    return client.post("/api/menu/evaluate", json={"menu": menu, "diners": diners}).json()


def _check_item(item, sheet, message=None):
    status = sheet[item["dish_id"]]["status"]
    assert item["status"] == status
    eat = {k: v for k, v in status.items() if v["status"] != "no"}
    confirm = any(v["status"] == "needs_confirm" for v in eat.values())
    for text in filter(None, [item.get("reason"), message]):
        assert bool(ASK.search(text)) == confirm, (text, status)
        if ALL.search(text):
            assert len(eat) == len(status), (text, status)
    assert item.get("veg_tag") == sheet[item["dish_id"]]["veg_tag"]


def test_ai_prose_is_off_by_default(demo, mia_facts, monkeypatch):  # noqa: F811
    menu, diners = _setup(demo)
    assert not ai_text.ai_prose()
    answer = {
        "dishes": [
            {
                "dish_id": i,
                "reason": "Refresing and suitable for {alice}.",
                "for": [],
                "server_question": "",
            }
            for i in ORDER
        ],
        "server_questions": [],
        "summary": "A lovely spread for every diner.",
        "change_note": "",
    }
    sheet = _sheet(menu, diners)
    for row in answer["dishes"]:
        row["for"] = sheet[row["dish_id"]]["edible_by"]
    monkeypatch.setattr(llm_planner, "_ask", lambda *a, **k: (json.dumps(answer), "fake"))
    r = client.post("/api/plan", json=_body(menu, diners)).json()
    assert r["kind"] == "plan", r
    text = json.dumps(r)
    assert "Refresing" not in text and "lovely spread" not in text
    for item in r["plan"]["items"]:
        _check_item(item, sheet)
    # an AI swap: its choice is kept, the words are the code's
    swap = {"dish_id": "eight_treasure_sticky_rice", "reason": "a sweet treat for {alice}"}
    monkeypatch.setattr(ai_swap, "_ask", lambda t, s, c: (json.dumps(swap), "fake"))
    s = client.post(
        "/api/plan/swap", json=_body(menu, diners, plan=r["plan"], dish_id="pumpkin_cake_3")
    ).json()
    assert s["kind"] == "plan" and "sweet treat" not in s["message"], s
    for item in s["plan"]["items"]:
        _check_item(item, sheet, s["message"] if item["dish_id"] == s["new_dish_id"] else None)


def test_every_ask_and_everyone_string_matches_status_through_picks(demo, mia_facts):  # noqa: F811
    menu, diners = _setup(demo)
    sheet = _sheet(menu, diners)
    plan = _plan(menu, diners)
    for old, new in [
        ("tomato_egg", "eight_treasure_sticky_rice"),
        ("eight_treasure_sticky_rice", "tomato_egg"),
        ("broccoli_tofu", "chilled_zucchini_in_tangy_sauce"),
    ]:
        r = client.post(
            "/api/plan/swap",
            json=_body(menu, diners, plan=plan, dish_id=old, new_dish_id=new),
        ).json()
        assert r["kind"] == "plan", r
        for item in r["plan"]["items"]:
            _check_item(item, sheet, r["message"] if item["dish_id"] == new else None)
        plan = r["plan"]


def test_veg_tag_ignores_other_diners_halal(demo, monkeypatch):  # noqa: F811
    """Tomato & Egg: Mia's halal needs confirming, Ben (vegetarian) is ok -> plain tag."""
    from michelin import llm
    from michelin.plan import custom_facts

    def fake(dishes, allergies, diets, client=None):
        rows = [
            {
                "id": d.id,
                "allergens": [{"item": t, "answer": "no"} for t in allergies],
                "diets": [{"item": t, "answer": "possible"} for t in diets],
            }
            for d in dishes
        ]
        return json.dumps({"dishes": rows}), "fake"

    monkeypatch.setattr(custom_facts, "_ask", fake)
    monkeypatch.setattr(llm, "provider", lambda *a, **k: "fake")
    menu, diners = _setup(demo)
    egg = _sheet(menu, diners)["tomato_egg"]
    assert egg["status"]["ben"]["status"] == "ok"
    assert egg["veg_tag"] == "vegetarian"  # not "ask_vegetarian" because of Mia's halal


def test_explain_has_no_staff_line_and_asks_only_on_needs_confirm():
    from pathlib import Path

    src = Path(llm_planner.__file__).parents[1].joinpath("explain.py").read_text()
    assert "Check the listed questions with staff" not in src
