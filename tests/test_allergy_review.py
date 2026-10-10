"""Regression tests for the allergy-safety review (2026-10-09): the reviewer's repros."""

import json
from pathlib import Path

import pytest

from michelin import keywords
from michelin.plan import dish_facts, llm_planner
from michelin.plan.edibility import assessment, edible_by
from michelin.plan.validation import validate_order
from michelin.schemas import DinerProfile, Dish, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
SHELL = DinerProfile(id="sam", name="Sam", allergies=["shellfish"])
PEANUT = DinerProfile(id="pia", name="Pia", allergies=["peanut"])
WHEAT = DinerProfile(id="wu", name="Wu", allergies=["wheat"])
FISH = DinerProfile(id="fay", name="Fay", allergies=["fish"])
NO_PORK = DinerProfile(id="cai", name="Cai", diets=["no_pork"])
VEG = DinerProfile(id="ben", name="Ben", diets=["vegetarian"])
NINE = ["peanut", "tree_nut", "shellfish", "fish", "egg", "dairy", "soy", "wheat", "sesame"]


def ai(allergens=(), absent=None, ingredients=(), **kw):
    """An AI answer; by default it calls every allergen it did not list absent."""
    listed = {a for a, _ in allergens}
    out = {
        "ingredients": [{"name": n, "certainty": "likely"} for n in ingredients],
        "allergens": [{"allergen": a, "certainty": c, "why": ""} for a, c in allergens],
        "absent": [a for a in NINE if a not in listed] if absent is None else absent,
        "pork": "no",
        "beef": "no",
        "vegetarian": "no",
        "vegan": "no",
        "spice": 0,
    }
    return out | kw


def dish(name, zh=None, desc=None, **kw):
    return Dish(
        id=name.lower().replace(" ", "_"),
        name_en=name,
        name_zh=zh,
        price=12,
        description_raw=desc,
        category="stir_fry",
        **kw,
    )


def test_the_web_copy_of_the_keyword_list_is_the_same_list():
    a = json.loads((ROOT / "src/michelin/data/keywords.json").read_text(encoding="utf-8"))
    b = json.loads((ROOT / "web/src/lib/keywords.json").read_text(encoding="utf-8"))
    assert a == b


@pytest.mark.parametrize(
    "text,concept",
    [
        ("Salt and Pepper Squid", "shellfish"),
        ("Grilled Octopus", "shellfish"),
        ("Fried Calamari", "shellfish"),
        ("Cuttlefish balls", "shellfish"),
        ("Crawfish Noodles", "shellfish"),
        ("Crayfish", "shellfish"),
        ("Lobster", "shellfish"),
        ("Clams in black bean", "shellfish"),
        ("Mussels", "shellfish"),
        ("greens in oyster sauce", "shellfish"),
        ("with XO sauce", "shellfish"),
        ("椒盐鱿鱼", "shellfish"),
        ("麻辣小龙虾", "shellfish"),
        ("satay sauce", "peanut"),
        ("沙爹牛肉", "peanut"),
        ("fish sauce", "fish"),
        ("鱼露", "fish"),
        ("soy sauce", "soy"),
        ("soy sauce", "wheat"),
        ("酱油", "wheat"),
        ("五花肉", "pork"),
        ("肉末茄子", "pork"),
        ("猪油", "pork"),
        ("牛肉", "beef"),
    ],
)
def test_the_shared_list_knows_these(text, concept):
    assert keywords.found(concept, text.lower())


@pytest.mark.parametrize(
    "d,facts,who",
    [
        # The AI forgot shellfish; the printed word does not.
        (dish("Salt and Pepper Squid"), ai(ingredients=["squid"]), SHELL),
        (dish("Crawfish Noodles"), ai([("egg", "likely")]), SHELL),
        (dish("Morning Glory", desc="with XO sauce"), ai(), SHELL),
        (dish("Seafood Noodles", zh="鱿鱼面"), ai(), SHELL),
        (dish("Chicken Skewers", desc="grilled, satay sauce"), ai([("soy", "likely")]), PEANUT),
        (dish("Steamed Fish Fillet", desc="ginger, fish sauce"), ai(), FISH),
        (dish("Stir-fried Greens", desc="garlic, soy sauce"), ai([("soy", "likely")]), WHEAT),
        (dish("Kung Pao", variant="Shrimp"), ai([("peanut", "likely")]), SHELL),
    ],
)
def test_printed_allergens_win_over_an_ai_that_left_them_out(d, facts, who):
    out = dish_facts.apply(d, facts)
    assert edible_by(out, [who]) == []
    assert not assessment(out, who)["eligible"]


def test_a_squid_only_order_is_invalid_for_a_shellfish_allergy():
    squid = dish_facts.apply(dish("Salt and Pepper Squid"), ai(ingredients=["squid"]))
    menu = Menu(
        restaurant_id="r",
        restaurant_name="R",
        cuisine="x",
        source="test",
        dishes=[squid],
        verified=True,
    )
    request = TableRequest(menu_id="r", diners=[SHELL], budget_per_person=60, include_staple=False)
    out = validate_order(menu, request, [PlanItem(dish_id=squid.id, quantity=1, edible_by=["sam"])])
    assert out["valid"] is False


def test_an_allergen_the_ai_did_not_answer_is_unknown_not_safe():
    silent = dish_facts.apply(dish("Tofu Stir Fry"), ai(absent=[]))
    assert silent.reviewed_allergens == []
    assert edible_by(silent, [PEANUT, SHELL]) == []
    told = dish_facts.apply(dish("Tofu Stir Fry"), ai([("soy", "likely")]))
    assert edible_by(told, [PEANUT, SHELL]) == ["pia", "sam"]


def test_a_v_mark_never_clears_the_ais_pork_or_a_chinese_meat_word():
    """五花肉 + V: not for Cai (no pork) or Ben (vegetarian)."""
    tofu = dish("Tofu", zh="豆腐", menu_marks=["vegetarian"])
    belly = ai([("soy", "likely")], ingredients=["五花肉"], pork="yes", vegetarian="yes")
    out = dish_facts.apply(tofu, belly)
    assert out.contains_pork is True and out.is_vegetarian is not True
    assert edible_by(out, [NO_PORK, VEG]) == []
    a = assessment(out, NO_PORK)
    assert not a["eligible"] and a["status"] != "validated_under_known_data"
    # Even if the AI forgot to say pork "yes", a likely 肉末 keeps the diet unknown.
    mince = ai([("soy", "likely")], ingredients=["肉末"], vegetarian="yes")
    assert edible_by(dish_facts.apply(tofu, mince), [VEG]) == []
    # A clean V dish is still vegetarian.
    clean = ai([("soy", "likely")], ingredients=["tofu"], vegetarian="yes", vegan="yes")
    assert edible_by(dish_facts.apply(tofu, clean), [NO_PORK, VEG]) == ["cai", "ben"]


def test_possibly_vegetarian_is_never_vegetarian_without_a_question():
    out = dish_facts.apply(dish("Garlic Eggplant"), ai(vegetarian="possible", vegan="possible"))
    a = assessment(out, VEG)
    assert a["status"] == "requires_confirmation"
    assert a["eligible"] and a["reasons"]


def test_the_facts_key_tells_apart_chinese_names_variants_and_descriptions():
    k = dish_facts._key
    assert k(dish("Noodles", zh="阳春面")) != k(dish("Noodles", zh="鱿鱼面"))
    assert k(dish("Kung Pao", variant="Chicken")) != k(dish("Kung Pao", variant="Shrimp"))
    assert k(dish("Greens", desc="garlic")) != k(dish("Greens", desc="XO sauce"))
    assert k(dish("Scallion Pancakes (4)")) == k(dish("scallion pancake"))


def test_the_facts_call_gets_description_and_variant(monkeypatch):
    seen = {}

    def fake(system, turns, schema, **kw):
        seen["text"] = turns[0].text if hasattr(turns[0], "text") else str(turns[0])
        seen["schema"] = schema
        return json.dumps({"dishes": []}), "fake"

    monkeypatch.setattr(dish_facts.llm, "generate_json", lambda kind, **kw: fake(**kw))
    dish_facts._ask([dish("Kung Pao", desc="peanuts, chili", variant="Shrimp")])
    assert "peanuts, chili" in seen["text"] and "Shrimp" in seen["text"]
    row = seen["schema"]["properties"]["dishes"]["items"]
    assert "absent" in row["required"]


def test_saving_merges_by_key_and_keeps_a_concurrent_runs_entries(tmp_path, monkeypatch):
    path = tmp_path / "facts.json"
    monkeypatch.setattr(dish_facts, "CACHE_PATH", path)
    a = {"name": "A", **ai([("peanut", "possible")])}
    b = {"name": "B", **ai()}
    dish_facts._save({"ka": a})
    dish_facts._save({"kb": b})  # another run that never saw "ka"
    disk = json.loads(path.read_text())
    assert set(disk) == {"ka", "kb"}
    dish_facts._save({"ka": {"name": "A", **ai([("sesame", "likely")])}})
    merged = json.loads(path.read_text())["ka"]
    assert {x["allergen"] for x in merged["allergens"]} == {"peanut", "sesame"}  # union
    assert "peanut" not in merged["absent"] and "sesame" not in merged["absent"]


def test_the_ais_extra_meal_questions_pass_the_same_checks():
    d = dish_facts.apply(dish("Kung Pao Chicken"), ai([("peanut", "likely")]))
    selected = [(d, None)]
    diners = [SHELL, VEG]
    assert not llm_planner.meal_question_ok(
        "Sam has a peanut allergy; please keep it apart.", selected, diners
    )
    assert not llm_planner.meal_question_ok("Ask whether the sauces use sesame.", selected, diners)
    assert llm_planner.meal_question_ok(
        "Please bring the dishes as they are ready.", selected, diners
    )
