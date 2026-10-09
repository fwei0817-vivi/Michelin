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
    # The AI's peanut and soy; the code's floor adds peanut too (already there).
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
    assert kp.is_vegetarian is None
    # Only the code's floor: possible peanut, nothing cleared.
    assert {(f.allergen.value, f.tier.value) for f in kp.allergens} == {("peanut", "unknown")}
    assert edible_by(kp, [ALICE, BEN, CAI]) == []
    assert edible_by(kp, [DinerProfile(id="x", name="X")]) == ["x"]
    assert not dish_facts.known(menu())


def test_malformed_answers_stay_unknown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    bad = {"Kung Pao Chicken": {"allergens": [{"allergen": "plutonium", "certainty": "likely"}]}}
    monkeypatch.setattr(dish_facts, "_ask", Fake(bad))
    kp = dish_facts.prepare(menu()).dish("kung_pao")
    assert kp.is_vegetarian is None and kp.contains_pork is None
    assert "plutonium" not in str(kp.allergens)


def test_api_uses_ai_facts_not_the_clients(fake):
    client = TestClient(api.app)
    body = menu(verified=True).model_dump(mode="json")
    r = client.post("/api/menu/evaluate", json={"menu": body, "diners": [BEN.model_dump()]})
    assert r.status_code == 200
    assert r.json()["kung_pao"]["edible_by"] == []  # the client said vegetarian; the AI did not
    assert len(fake.calls) == 1


def _menu(*dishes) -> Menu:
    return Menu(
        restaurant_id="t", restaurant_name="T", cuisine="x", source="test", dishes=list(dishes)
    )


# The QA round-4 repros: an AI answer that missed the hidden allergen still keeps the
# allergic diner (or the no-pork diner) off the dish, or asks, through the code's floor.
CLEAN = {
    "ingredients": [{"name": "chicken", "certainty": "likely"}],
    "allergens": [{"allergen": "soy", "certainty": "likely", "why": "soy sauce"}],
    "pork": "no",
    "beef": "no",
    "vegetarian": "no",
    "vegan": "no",
    "spice": 2,
}
VEG = {
    **CLEAN,
    "ingredients": [{"name": "cucumber", "certainty": "likely"}],
    "vegetarian": "yes",
    "vegan": "yes",
    "spice": 1,
}
SHRIMP = {
    **CLEAN,
    "ingredients": [{"name": "shrimp", "certainty": "likely"}],
    "allergens": [{"allergen": "shellfish", "certainty": "likely", "why": "shrimp"}],
    "spice": 0,
}
REPROS = {
    "Chungking Spicy Chicken": CLEAN,
    "Three Pepper Chicken": CLEAN,
    "Spicy Wonton (6 pcs)": CLEAN,
    "Smashed Cucumber": VEG,
    "Crystal Shrimp Dumplings": SHRIMP,
}
PEANUT = DinerProfile(id="p", name="Pia", allergies=["peanut"])
PAT = DinerProfile(id="pat", name="Pat", diets=["no_pork"])


@pytest.mark.parametrize(
    "name",
    ["Chungking Spicy Chicken", "Three Pepper Chicken", "Spicy Wonton (6 pcs)", "Smashed Cucumber"],
)
def test_peanut_floor_keeps_allergic_diner_off(monkeypatch, name):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(dish_facts, "_ask", Fake(REPROS))
    dish = dish_facts.prepare(_menu(Dish(id="d", name_en=name, price=10))).dish("d")
    assert "peanut" in {f.allergen.value for f in dish.allergens}
    assert edible_by(dish, [PEANUT]) == []


@pytest.mark.parametrize("name", ["Crystal Shrimp Dumplings", "Spicy Wonton (6 pcs)"])
def test_dumplings_may_hide_pork(monkeypatch, name):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(dish_facts, "_ask", Fake(REPROS))
    dish = dish_facts.prepare(_menu(Dish(id="d", name_en=name, price=10))).dish("d")
    a = assessment(dish, PAT)
    assert a["status"] != "ok"  # never a plain yes for a no-pork diner
    assert any("pork" in r.about and r.names == ["Pat"] for r in risks(dish, [PAT]))


def test_same_name_same_facts_across_menus_and_categories(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    fake = Fake({"Crystal Shrimp Dumplings": SHRIMP, "Crystal Shrimp Dumplings (4)": SHRIMP})
    monkeypatch.setattr(dish_facts, "_ask", fake)
    a = dish_facts.prepare(
        _menu(Dish(id="a", name_en="Crystal Shrimp Dumplings", price=8, category="cold_appetizer"))
    ).dish("a")
    b = dish_facts.prepare(
        _menu(Dish(id="b", name_en="crystal shrimp dumplings (4)", price=9, category="other"))
    ).dish("b")
    assert len(fake.calls) == 1  # the second menu's row hits the same cache entry
    assert a.allergens == b.allergens and a.main_ingredients == b.main_ingredients
    assert a.category.value == "cold_appetizer"  # the user's category is kept


def test_repeated_runs_union_never_remove(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    first = {
        "Plain Tofu": {
            **VEG,
            "allergens": [
                {"allergen": "soy", "certainty": "likely", "why": "tofu"},
                {"allergen": "sesame", "certainty": "possible", "why": "sesame oil"},
            ],
            "pork": "possible",
        }
    }
    second = {
        "Plain Tofu": {
            **VEG,
            "allergens": [
                {"allergen": "soy", "certainty": "likely", "why": "tofu"},
                {"allergen": "egg", "certainty": "possible", "why": "some batter"},
            ],
        }
    }
    monkeypatch.setattr(dish_facts, "_ask", Fake(first))
    m = _menu(Dish(id="t", name_en="Plain Tofu", price=9))
    dish_facts.prepare(m)
    # Simulate a later run whose answer dropped sesame and pork: the cache keeps both.
    cache = dish_facts._load()
    key = dish_facts._key(m.dish("t"))
    cache[key] = {"name": "Plain Tofu", **dish_facts.merge(cache[key], second["Plain Tofu"])}
    dish_facts._save(cache)
    tofu = dish_facts.prepare(m).dish("t")
    assert {f.allergen.value for f in tofu.allergens} == {"soy", "sesame", "egg"}
    assert tofu.contains_pork is not True and assessment(tofu, PAT)["status"] != "ok"


def test_merge_keeps_the_riskier_answer():
    a = {
        "allergens": [{"allergen": "peanut", "certainty": "possible", "why": ""}],
        "ingredients": [],
        "pork": "no",
        "beef": "possible",
        "vegetarian": "yes",
        "vegan": "possible",
        "spice": 1,
    }
    b = {
        "allergens": [{"allergen": "peanut", "certainty": "likely", "why": ""}],
        "ingredients": [],
        "pork": "possible",
        "beef": "no",
        "vegetarian": "possible",
        "vegan": "yes",
        "spice": 3,
    }
    m = dish_facts.merge(a, b)
    assert m["allergens"][0]["certainty"] == "likely"
    assert (m["pork"], m["beef"], m["vegetarian"], m["vegan"], m["spice"]) == (
        "possible",
        "possible",
        "possible",
        "possible",
        3,
    )


def test_name_normalisation():
    assert dish_facts.norm("Spicy Wonton (6 pcs)") == dish_facts.norm("spicy wonton")
    assert dish_facts.norm("Crystal Shrimp Dumplings (4)") == "crystal shrimp dumpling"
    assert dish_facts.norm("Scallion Pancakes") == dish_facts.norm("Scallion Pancake")
    assert dish_facts.norm("Café China's Dan-Dan") == "cafe china s dan dan"


def test_ai_reason_cannot_single_out_a_flagged_diner(monkeypatch):
    """QA round 4 #7: 'especially Pat' on a dish that may hide Pat's pork is replaced."""
    from michelin.plan.llm_planner import _fair_reason
    from michelin.schemas import TableRequest

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(dish_facts, "_ask", Fake(REPROS))
    dish = dish_facts.prepare(_menu(Dish(id="d", name_en="Crystal Shrimp Dumplings", price=8)))
    d = dish.dish("d")
    request = TableRequest(
        menu_id="t", diners=[PAT, DinerProfile(id="x", name="Xu")], budget_per_person=40
    )
    assert _fair_reason("Delicate dim sum, especially for Pat", d, request) is None
    assert _fair_reason("Delicate dim sum Xu will love", d, request) is not None
    assert _fair_reason("A chicken dish for Xu, who loves peanuts", d, request) is None
    noted = request.model_copy(
        update={"diners": [PAT, DinerProfile(id="x", name="Xu", notes="loves dumplings")]}
    )
    assert _fair_reason("Dim sum Xu loves", d, noted) is not None
    tofu = noted.model_copy(
        update={"diners": [PAT, DinerProfile(id="x", name="Xu", notes="loves tofu")]}
    )
    assert _fair_reason("A dish that Xu loves", d, tofu) is None


def test_questions_only_for_concerns_at_the_table(monkeypatch):
    """QA round 4 #4: 'ask whether it uses bamboo shoots' is not shown to anyone."""
    from michelin.plan.edibility import open_questions

    d = Dish(
        id="d",
        name_en="Braised Tofu",
        price=9,
        confirm_with_staff=[
            "Braised Tofu: ask whether it uses bamboo shoots.",
            "Braised Tofu: ask whether it uses pork.",
        ],
    )
    nobody = DinerProfile(id="n", name="Nia")
    assert open_questions(d, [nobody]) == []
    asked = open_questions(d, [PAT])
    assert "Braised Tofu: ask whether it uses pork." in asked
    assert not any("bamboo" in q for q in asked)


def test_possible_lard_asks_a_no_pork_diner(fake):
    pancake = dish_facts.prepare(menu()).dish("pancake")
    a = assessment(pancake, PAT)
    assert a["status"] == "requires_confirmation" and a["eligible"]
    assert any("pork" in r for r in a["reasons"])


@pytest.mark.parametrize(
    "name",
    [
        "Hot and Sour Soup",
        "Fish Fillet in Hot Chili Oil",
        "Spicy Cumin Lamb",
        "Shredded Beef with Green Chili",
        "Braised Pork Szechuan Style",
        "Red Style Chungking Braised Fish Stew",
        "Spicy Cucumbers",
        "Scallion Pancake",
    ],
)
def test_floor_does_not_flag_peanut_on_every_spicy_name(name):
    """QA r5 over-strictness: only real peanut dish families trigger the floor."""
    base = dish_facts.floor(Dish(id="d", name_en=name, price=5))
    assert "peanut" not in {a["allergen"] for a in base["allergens"]}


@pytest.mark.parametrize(
    ("name", "zh"),
    [
        ("Kung Pao Chicken", None),
        ("Dan Dan Noodles", None),
        ("Chicken Satay", None),
        ("Mouth-Watering Chicken", "口水鸡"),
        ("Strange Flavor Chicken", "怪味鸡"),
        ("Bang Bang Chicken", "棒棒鸡"),
        ("Wontons in Red Chili Oil", "红油抄手"),
        ("Dry Chili Chicken", "辣子鸡"),
        ("Smashed Cucumber", "拍黄瓜"),
    ],
)
def test_floor_keeps_real_peanut_signals(name, zh):
    base = dish_facts.floor(Dish(id="d", name_en=name, name_zh=zh, price=5))
    assert "peanut" in {a["allergen"] for a in base["allergens"]}


def test_fried_rice_is_not_auto_flagged_shellfish():
    for name in ("Fried Rice with Shredded Duck", "Fried Rice with Preserved Vegetable"):
        base = dish_facts.floor(Dish(id="d", name_en=name, price=9))
        assert "shellfish" not in {a["allergen"] for a in base["allergens"]}


def test_ai_cannot_make_a_shared_dish_a_per_person_staple(monkeypatch):
    """QA r5: Scallion Pancake and Dan Dan were priced per person as 'staples'."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    facts = {**VEG, "category": "staple"}
    names = ["Scallion Pancake", "Dan Dan Noodles", "Steamed Rice", "Vegetable Fried Rice"]
    monkeypatch.setattr(dish_facts, "_ask", Fake({n: facts for n in names}))
    m = dish_facts.prepare(
        _menu(*[Dish(id=f"d{i}", name_en=n, price=5) for i, n in enumerate(names)])
    )
    got = {d.name_en: d.category.value for d in m.dishes}
    assert got == {
        "Scallion Pancake": "other",
        "Dan Dan Noodles": "other",
        "Steamed Rice": "staple",
        "Vegetable Fried Rice": "other",
    }
