"""QA round 21 (2026-10-10): diet answers can never flip polarity (halal Mia was "ok" for
Spam), diets follow the dish's own pork/meat facts, snacks are not mains, the top-up adds
nothing too hot, spice is said once per card, plain rice needs no allergy question."""

import json
from pathlib import Path

import pytest

from michelin import explain, llm
from michelin.plan import courses, custom_facts, dish_facts, edibility, enough, spice
from michelin.schemas import Allergen, DinerProfile, Dish, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.real_dish_facts]


def _fake(answer, why=""):
    def fake(dishes, allergies, diets, client=None):
        rows = [
            {
                "id": d.id,
                "allergens": [{"item": t, "answer": "no"} for t in allergies],
                "diets": [{"item": t, "answer": answer, "why": why} for t in diets],
            }
            for d in dishes
        ]
        return json.dumps({"dishes": rows}), "fake"

    return fake


@pytest.fixture
def atlas(monkeypatch):
    monkeypatch.setattr(dish_facts, "CACHE_PATH", ROOT / "data/facts/dish_facts.json")
    monkeypatch.setattr(custom_facts, "cache_path", lambda: Path("/nonexistent/c.json"))
    monkeypatch.setattr(custom_facts, "_save", lambda new: new)
    monkeypatch.setattr(llm, "provider", lambda *a, **k: "fake")
    return Menu.model_validate_json((ROOT / "data/menus/atlas_kitchen.json").read_text())


MIA = DinerProfile(
    id="mia", name="Mia", allergies=["sesame"], other_allergies=["cilantro"], other_diets=["halal"]
)


@pytest.mark.parametrize("answer,why", [("fits", ""), ("no", "Contains spam (pork)"), ("no", "")])
def test_atlas_mia_halal_never_ok_for_spam_or_yang_chow(atlas, monkeypatch, answer, why):
    """Whatever the AI says (even a wrong 'fits'), pork/Spam dishes are not halal."""
    monkeypatch.setattr(custom_facts, "_ask", _fake(answer, why))
    m = dish_facts.prepare(atlas, diners=[MIA])
    hits = [d for d in m.dishes if "spam" in (d.name_en or "").lower()]
    assert len(hits) == 2
    for d in m.dishes:
        if "spam" in (d.name_en or "").lower() or "yang chow" in (d.name_en or "").lower():
            assert edibility.diner_status(d, [MIA])["mia"]["status"] == "no", d.name_en
    req = TableRequest(menu_id="a", diners=[MIA], budget_per_person=40)
    pool = {d.id for d in enough._pool(m, req)}  # top-up and recommender: same status
    assert not any("spam" in (m.dish(i).name_en or "").lower() for i in pool)


def _pork(name="Wintermelon with Luncheon Meat", **kw):
    return Dish(id="p", name_en=name, price=12, category="stir_fry", **kw)


@pytest.mark.parametrize("term", ["halal", "kosher", "vegetarian"])
@pytest.mark.parametrize(
    "name",
    ["Wintermelon with Luncheon Meat", "Lap Cheong Fried Rice", "Char Siu Bao", "Spam Musubi"],
)
def test_synthetic_diets_vs_pork_when_ai_says_fits(monkeypatch, term, name):
    monkeypatch.setattr(custom_facts, "cache_path", lambda: Path("/nonexistent/c.json"))
    monkeypatch.setattr(custom_facts, "_save", lambda new: new)
    monkeypatch.setattr(custom_facts, "_ask", _fake("fits"))
    p = DinerProfile(id="x", name="Xu", other_diets=[term])
    d = custom_facts.annotate([_pork(name)], [p], client=object())[0]
    assert edibility.diner_status(d, [p])["x"]["status"] == "no", (term, name)


def test_legacy_no_is_read_by_its_reason():
    assert custom_facts._diet_answer("no", "Contains spam (pork)", "halal", False) == "likely"
    assert custom_facts._diet_answer("no", "Not halal", "halal", True) == "likely"
    assert custom_facts._diet_answer("no", "No pork or alcohol used", "halal", False) == "no"
    assert custom_facts._diet_answer("no", "Vegetable dish", "halal", True) == "no"


def test_alcohol_makes_halal_a_question_and_veg_fact_is_strict():
    wine = Dish(id="w", name_en="Drunken Tofu in Shaoxing Wine", price=10, category="stir_fry")
    assert custom_facts.derived(wine, "halal")[0] == "possible"
    assert custom_facts.derived(_pork("Mystery", contains_pork=True), "kosher")[0] == "likely"
    assert (
        custom_facts.derived(Dish(id="c", name_en="Chicken", price=9), "vegetarian")[0] == "likely"
    )


def test_snacks_are_sides_and_wings_are_not_cold():
    ds = [
        Dish(id=f"m{i}", name_en=f"Main {i}", price=14 + i, category="stir_fry", course="hot_main")
        for i in range(5)
    ]
    ds += [
        Dish(id="cn", name_en="Crispy Noodles", price=1.75, category="other", course="staple"),
        Dish(id="chips", name_en="Shrimp Chips", price=4, category="other", course="hot_main"),
        Dish(
            id="w",
            name_en="Green Tea Chicken Wings (5)",
            price=11,
            category="cold_appetizer",
            course="cold",
        ),
    ]
    out = {d.id: d.course for d in courses._snacks(ds)}
    assert out["cn"] == "side" and out["chips"] == "side" and out["w"] == "side"
    assert out["m0"] == "hot_main"


def _d(i, price, lvl=0, course="hot_main"):
    return Dish(
        id=i,
        name_en=i,
        price=price,
        category="stir_fry",
        course=course,
        spice_level=lvl,
        is_vegetarian=True,
        is_vegan=False,
        contains_pork=False,
        contains_beef=False,
        reviewed_allergens=list(Allergen),
    )


def test_top_up_never_adds_spicy_for_no_heat_diners():
    m = Menu(
        restaurant_id="s",
        restaurant_name="S",
        cuisine="x",
        source="t",
        verified=True,
        dishes=[_d("cold", 5, course="cold"), _d("fire", 9, 2), _d("mild", 15)],
    )
    diners = [
        DinerProfile(id="a", name="Ann", preferences=["no_spicy"]),
        DinerProfile(id="b", name="Bo"),
    ]
    out = enough.top_up(
        m,
        TableRequest(menu_id="s", diners=diners, budget_per_person=60),
        [PlanItem(dish_id="cold", quantity=1)],
    )
    assert out and "fire" not in out[1] and "mild" in out[1]


def test_spice_said_once_per_card():
    d = _d("hot", 10, 1)
    diners = [
        DinerProfile(id="a", name="Ann", preferences=["no_spicy"]),
        DinerProfile(id="b", name="Bo"),
    ]
    r = explain.reason_for(d, 1, TableRequest(menu_id="s", diners=diners, budget_per_person=40))
    note = spice.heat_note(d, diners)
    said = [x for x in (r, note, spice.label(d)) if x and "little spicy" in x.lower()]
    assert said == [spice.label(d)], (r, note)


def test_plain_rice_needs_no_allergy_question():
    rice = dish_facts.plain_rice_only(
        Dish(id="r", name_en="Steamed Rice", price=2, category="staple")
    )
    p = DinerProfile(id="p", name="Pat", allergies=["peanut", "shellfish", "egg"], diets=["vegan"])
    assert edibility.diner_status(rice, [p])["p"]["status"] == "ok"
