"""2026-10-10 (Yukino on f58a3b6): one spice source; taste conflicts (too spicy for a
no-heat diner) are never listed or counted for them; 'if the server confirms for X'; the
'enough food' rule. Regression: Yukino's Cafe Mandarin table; generic synthetic diners."""

import json
from pathlib import Path

import pytest

from michelin import explain
from michelin.parse import vision
from michelin.plan import ai_text, courses, dish_facts, enough, llm_planner, spice
from michelin.plan.edibility import diner_status, for_whom
from michelin.schemas import DinerProfile, Dish, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.real_dish_facts]


@pytest.fixture
def cafe_mandarin(monkeypatch):
    monkeypatch.setattr(dish_facts, "CACHE_PATH", ROOT / "data/facts/dish_facts.json")
    monkeypatch.setattr(courses, "CACHE_PATH", ROOT / "data/facts/dish_course.json")
    rows = json.loads((ROOT / "data/menu_reads/36dcef2dd7afddc976198c4135336542.json").read_text())
    menu = Menu(
        restaurant_id="cm",
        restaurant_name="Cafe Mandarin",
        cuisine="x",
        source="t",
        verified=True,
        dishes=vision.rows_to_dishes(rows["rows"]),
    )
    return dish_facts.prepare(menu)


YUKINO = [
    DinerProfile(id="li", name="Li", preferences=["no_spicy"]),
    DinerProfile(id="david", name="David", diets=["vegetarian"]),
    DinerProfile(id="amy", name="Amy", allergies=["shellfish", "fish"]),
    DinerProfile(id="kevin", name="Kevin", preferences=["no_spicy"]),
]


def _req(diners, budget=40):
    return TableRequest(menu_id="cm", diners=diners, budget_per_person=budget)


def _listed(reason, diners):
    head = reason.split(";")[0].split(".")[0]
    return {p.id for p in diners if p.name in head}


def test_demo_courses_need_no_ai(cafe_mandarin):
    cache = courses._load()
    unclear = [
        d
        for d in cafe_mandarin.dishes
        if d.category not in courses.CLEAR and courses._by_name(d) is None
    ]
    assert unclear and all(courses._key(d) in cache for d in unclear)
    atlas = dish_facts.prepare(
        Menu.model_validate_json((ROOT / "data/menus/atlas_kitchen.json").read_text())
    )
    assert all(
        courses._key(d) in cache
        for d in atlas.dishes
        if d.category not in courses.CLEAR and courses._by_name(d) is None
    )
    assert not [d for d in cafe_mandarin.dishes if d.course == "unknown"]


def test_one_spice_source_for_tag_and_reason(cafe_mandarin):
    req = _req(YUKINO)
    for d in cafe_mandarin.dishes:
        r = explain.reason_for(d, 1, req)
        lab = spice.label(d)
        # r21: the level is said once per card, by its tag; the reason and the heat note
        # never repeat a spice level
        assert "spicy" not in r.lower(), (d.id, r)
        note = (spice.heat_note(d, YUKINO) or "").lower()
        assert not any(x.lower() in note for x in spice.LABELS[1:]), (d.id, note)
        assert lab is None or lab == spice.label(d)


def test_yukino_table_taste_conflicts_never_listed(cafe_mandarin):
    req = _req(YUKINO)
    for d in cafe_mandarin.dishes:
        if d.category.value == "staple":
            continue
        st = diner_status(d, YUKINO)
        r = explain.reason_for(d, 1, req)
        fw = set(for_whom(d, YUKINO))
        for p in YUKINO:
            if st[p.id]["taste"] == "too_spicy":
                assert p.id not in fw and p.name not in r.split(";")[0], (d.id, r)
        if spice.level(d) >= 2:
            assert not {"li", "kevin"} & fw, d.id
            assert "Not for Li and Kevin, who avoid heat" in (spice.heat_note(d, YUKINO) or ""), d.id
        if r.startswith("Everyone can share this"):
            assert fw == {p.id for p in YUKINO}, (d.id, r)
        if spice.level(d) == 1 and {"li", "kevin"} <= fw:
            assert "Li and Kevin avoid heat; ask for it mild" in (spice.heat_note(d, YUKINO) or "")


def test_hot_sour_soup_tag_reason_agree(cafe_mandarin):
    d = cafe_mandarin.dish("hot_sour_soup")
    r = explain.reason_for(d, 1, _req(YUKINO))
    assert "spicy" not in r.lower()  # the tag alone says it (r21)
    assert spice.label(d) in spice.LABELS


def test_server_confirm_phrasing():
    d = Dish(id="dumpling", name_en="Veg Dumplings", price=12, category="other", is_vegetarian=True)
    a = DinerProfile(id="a1", name="Ana")
    b = DinerProfile(id="b1", name="Bo", diets=["vegetarian"])
    st = diner_status(d, [a, b])
    r = explain.reason_for(d, 1, _req([a, b]))
    if st["b1"]["status"] == "needs_confirm" and st["a1"]["status"] == "ok":
        assert r.startswith("Everyone can share this if the server confirms for Bo."), r
    assert "Ask the server first" not in r


def test_too_spicy_dish_synthetic_diners():
    hot = Dish(
        id="h",
        name_en="Fire Chicken",
        price=15,
        category="stir_fry",
        spice_level=2,
        is_vegetarian=False,
    )
    x = DinerProfile(id="x", name="Xia", notes="no spicy food please")
    y = DinerProfile(id="y", name="Yan")
    r = explain.reason_for(hot, 1, _req([x, y]))
    assert r == "For Yan.", r
    assert for_whom(hot, [x, y]) == ["y"]
    assert spice.heat_note(hot, [x, y]) == "Not for Xia, who avoids heat"


def _menu(dishes):
    return Menu(
        restaurant_id="s",
        restaurant_name="S",
        cuisine="x",
        source="t",
        verified=True,
        dishes=dishes,
    )


def _d(i, cat, price, course=None, veg=True, lvl=0):
    return Dish(
        id=i,
        name_en=i,
        price=price,
        category=cat,
        course=course,
        spice_level=lvl,
        is_vegetarian=veg,
        is_vegan=False,
        contains_pork=False,
        contains_beef=False,
        reviewed_allergens=list(__import__("michelin.schemas", fromlist=["Allergen"]).Allergen),
    )


def test_enough_rule_and_honest_line():
    m = _menu(
        [
            _d("cold1", "cold_appetizer", 8),
            _d("soup1", "soup", 6),
            _d("tofu", "stir_fry", 14),
            _d("greens", "stir_fry", 12),
            _d("noodle", "other", 13, "staple"),
            _d("mystery", "other", 9, "unknown"),
        ]
    )
    diners = [DinerProfile(id="p", name="Pat"), DinerProfile(id="q", name="Quinn")]
    req = _req(diners, 60)
    thin = [PlanItem(dish_id=i, quantity=1) for i in ("cold1", "soup1", "mystery")]
    assert enough.tally([m.dish(i.dish_id) for i in thin], diners).hot == 0
    assert enough.feasible(m, req)
    line = enough.honest_line(m, req, thin)
    assert line.startswith("This order has no hot dishes for 2 people"), line
    assert line in ai_text.code_summary(m, req, thin)
    full = [PlanItem(dish_id=i, quantity=1) for i in ("tofu", "noodle", "cold1")]
    assert enough.honest_line(m, req, full) is None
    poor = _req(diners, 5)
    assert not enough.feasible(m, poor)
    line = enough.honest_line(m, poor, thin)
    assert line.startswith("This order has no hot dishes") and line.endswith(
        "about $20 per person would cover it."
    ), line
    need = enough.budget_needed(m, poor)
    assert enough.feasible(m, _req(diners, need))
    check = llm_planner.enough_check(m, poor, thin)
    assert not check.passed and check.detail == line


@pytest.mark.enough
def test_planner_retries_once_for_enough_food(monkeypatch, tmp_path):
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
    req = _req(diners, 60)
    rows = lambda ids: json.dumps(
        {
            "dishes": [
                {"dish_id": i, "reason": "", "for": ["p", "q"], "server_question": ""} for i in ids
            ],
            "server_questions": [],
            "summary": "",
        }
    )
    answers = [rows(["cold1", "soup1"]), rows(["tofu", "noodle", "cold1"])]
    calls = []

    def fake(turns, schema, menu, request, client):
        calls.append(turns)
        return answers[len(calls) - 1], "fake"

    monkeypatch.setattr(llm_planner, "_ask", fake)
    monkeypatch.setattr(llm_planner, "COVERAGE_NUDGE", False)
    out = llm_planner.plan(m, req, cache_path=tmp_path / "c.json")
    assert len(calls) == 2 and "not enough food" in calls[1][-1].text
    assert {i.dish_id for i in out.plan.items} >= {"tofu", "noodle"}
    assert next(c for c in out.plan.checks if c.name == "enough").passed
