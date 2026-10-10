"""Regression tests for QA round 8 (34d0af2): Q-2, MO-1, AD-1, wording, swap hint, repeated
staples and the facts cache key."""

import json

import pytest

from michelin.parse.vision import _choice_line, clean_choices, rows_to_dishes
from michelin.plan import ai_swap, dish_facts, refine
from michelin.plan.edibility import Risk, ask_server
from michelin.plan.validation import staple_repeats
from michelin.schemas import DinerProfile, Dish, Menu, TableRequest

ALICE = DinerProfile(id="alice", name="Alice")
BEN = DinerProfile(id="ben", name="Ben", diets=["no_pork"])
CAI = DinerProfile(id="cai", name="Cai", diets=["no_pork"])
MIA = DinerProfile(
    id="mia", name="Mia", allergies=["sesame"], other_allergies=["cilantro"], other_diets=["halal"]
)


def _menu(*dishes) -> Menu:
    return Menu(
        restaurant_id="t",
        restaurant_name="T",
        cuisine="x",
        source="test",
        verified=True,
        dishes=list(dishes),
    )


# Q-2 ---------------------------------------------------------------------------------------
def test_halal_is_asked_as_a_diet_not_an_ingredient():
    rice = Dish(id="r", name_en="Fried Rice", price=14)
    flagged = [
        Risk("pork", ["Ben", "Cai"], ["pork"], ""),
        Risk("halal", ["Mia"], ["halal"], ""),
    ]
    q = ask_server(rice, flagged)
    assert "halal in" not in q and "or halal" not in q
    assert q == "Is there any pork in the Fried Rice (for Ben and Cai), and is it halal (for Mia)?"
    follow = ask_server(rice, flagged, follow_up=True)
    assert follow.startswith("Also, is there any pork in it") and "is it halal" in follow


def test_shared_names_stay_one_tail_and_no_pork_reads_as_pork():
    rice = Dish(id="r", name_en="Fried Rice", price=14)
    q = ask_server(rice, [Risk("no pork", ["Ben"], ["pork"], ""), Risk("halal", ["Ben"], [], "")])
    assert q == "Is there any pork in the Fried Rice, and is it halal (for Ben)?"


# MO-1 --------------------------------------------------------------------------------------
FLUKE = (
    "Choice of Steamed w/ Ginger Scallion / Hunan Fermented Chili / Salt & Pepper / Sweet & Sour"
)


def test_w_slash_is_not_an_option_separator():
    names = [n for n, _ in _choice_line(FLUKE)]
    assert names == [
        "Steamed with Ginger Scallion",
        "Hunan Fermented Chili",
        "Salt & Pepper",
        "Sweet & Sour",
    ]


def test_truncated_and_duplicate_choices_are_merged():
    out = clean_choices(
        [
            {"name_en": "Steamed w"},
            {"name_en": "Ginger Scallion"},
            {"name_en": "Salt & Pepper"},
            {"name_en": "salt & pepper"},
        ]
    )
    assert [c["name_en"] for c in out] == ["Steamed with Ginger Scallion", "Salt & Pepper"]


def test_fluke_fish_filet_has_the_four_printed_versions():
    split = [
        "Steamed w",
        "Ginger Scallion",
        "Hunan Fermented Chili",
        "Salt & Pepper",
        "Sweet & Sour",
    ]
    rows = [
        {
            "name_en": "Fluke Fish Filet",
            "price": 28,
            "choice_text": FLUKE,
            "choices": [{"name_en": n} for n in split],
        }
    ]
    dishes = rows_to_dishes(rows)
    assert len(dishes) == 4 and all(d.price == 28 for d in dishes)
    assert not any(d.name_en.endswith("(Steamed w)") for d in dishes)


# AD-1 --------------------------------------------------------------------------------------
def _cucumbers():
    return _menu(
        Dish(id="cuc_garlic", name_en="Cucumber Salad (Garlic)", price=9, spice_level=0),
        Dish(id="cuc_chili", name_en="Cucumber Salad (Spicy Chili Oil)", price=9, spice_level=2),
        Dish(id="zucchini", name_en="Chilled Zucchini", price=9, spice_level=1),
        Dish(id="mapo", name_en="Mapo Tofu", price=16, spice_level=1),
    )


def test_a_note_naming_an_unchanged_dish_is_replaced_by_the_real_change():
    menu = _cucumbers()
    before = [("cuc_garlic", 1), ("cuc_chili", 1), ("mapo", 1)]
    after = [("cuc_garlic", 1), ("zucchini", 1), ("mapo", 1)]
    d = refine.diff(menu, before, after)
    bad = "Replaced the spicy cucumber salad with a garlic one to reduce spice."
    note, from_ai = refine.final_note(bad, d)
    assert not from_ai
    assert note == "Swapped Cucumber Salad (Spicy Chili Oil) for Chilled Zucchini."
    good = "Swapped the chili oil cucumber for chilled zucchini to cut the heat."
    assert refine.final_note(good, d) == (good, True)


def test_already_mild_wording_is_plain():
    assert "hotter than a 1" not in refine.ALREADY_MILD
    assert "little spicy" in refine.ALREADY_MILD


def test_one_pepper_is_never_labelled_mild_in_the_web_app():
    from pathlib import Path

    web = Path(__file__).resolve().parents[1] / "web/src/components"
    for f in ("Ticket.tsx", "SwapSheet.tsx"):
        text = (web / f).read_text()
        assert 'const SPICE = ["", "A little spicy", "Spicy", "Very spicy"];' in text


# Swap hint ---------------------------------------------------------------------------------
def test_swap_hint_does_not_undersell_who_can_eat():
    menu = _menu(
        Dish(id="old", name_en="Pineapple Fried Rice", price=14),
        Dish(
            id="new",
            name_en="Tomato and Egg",
            price=14,
            is_vegetarian=True,
            contains_pork=False,
            contains_beef=False,
            spice_level=0,
        ),
    )
    people = [ALICE, BEN, DinerProfile(id="cai", name="Cai"), DinerProfile(id="pat", name="Pat")]
    request = TableRequest(menu_id="t", diners=people, budget_per_person=40)
    from michelin.plan.edibility import edible_by

    ok = edible_by(menu.dish("new"), people)
    line = ai_swap._line(menu, request, "old", "new", "Ben and Cai can eat it")
    assert len(ok) == len(people)
    assert "everyone can eat it" in line and "Ben and Cai can eat it" not in line


# Repeated staples --------------------------------------------------------------------------
def test_two_fried_rices_for_the_same_people_are_flagged_when_there_is_another_dish():
    menu = _menu(
        Dish(id="fr1", name_en="Pineapple Fried Rice", price=14, contains_pork=False),
        Dish(id="fr2", name_en="Yang Chow Fried Rice", price=15, contains_pork=False),
        Dish(id="greens", name_en="Garlic Greens", price=12, is_vegetarian=True),
    )
    request = TableRequest(menu_id="t", diners=[ALICE], budget_per_person=60)
    assert staple_repeats(menu, request, ["fr1", "fr2"])
    assert not staple_repeats(menu, request, ["fr1", "greens"])
    only = _menu(*menu.dishes[:2])  # no other option: allowed
    assert not staple_repeats(only, request, ["fr1", "fr2"])


# Facts cache key ---------------------------------------------------------------------------
@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(dish_facts, "CACHE_PATH", tmp_path / "facts.json")
    calls = []

    def ask(batch, client=None):
        calls.append([d.id for d in batch])
        rows = [
            {
                "id": d.id,
                "ingredients": [],
                "allergens": [],
                "absent": [],
                "pork": "no",
                "beef": "no",
                "vegetarian": "no",
                "vegan": "no",
                "spice": 0,
            }
            for d in batch
        ]
        return json.dumps({"dishes": rows}), "fake"

    monkeypatch.setattr(dish_facts, "_ask", ask)
    return calls


def _read(desc, zh="宫保鸡 / 牛", variant="Chicken"):
    return Dish(
        id="kp_chicken",
        name_en="Kung Pao (Chicken)",
        name_zh=zh,
        variant=variant,
        price=18,
        description_raw=desc,
    )


@pytest.mark.real_dish_facts
def test_a_reread_of_the_same_line_hits_the_cache(cache):
    dish_facts.prepare(
        _menu(_read("宫保 Kung Pao. Peanuts, dried chili, scallion.")), client=object()
    )
    assert len(cache) == 1
    # Another read: different punctuation, order, case, plural, and spacing in the Chinese.
    dish_facts.prepare(
        _menu(_read("Kung Pao — scallions, PEANUTS & dried chili", zh="宫保鸡/牛")), client=object()
    )
    assert len(cache) == 1


@pytest.mark.real_dish_facts
def test_fallback_on_name_and_variant_when_the_chinese_name_is_dropped(cache):
    dish_facts.prepare(_menu(_read("peanuts, dried chili")), client=object())
    dish_facts.prepare(_menu(_read("peanuts, dried chili, garlic", zh=None)), client=object())
    assert len(cache) == 1


@pytest.mark.real_dish_facts
def test_fallback_never_reuses_facts_across_an_ingredient_concern(cache):
    g1 = Dish(id="g", name_en="Greens", price=12, description_raw="garlic")
    dish_facts.prepare(_menu(g1), client=object())
    g2 = Dish(id="g", name_en="Greens", price=12, description_raw="XO sauce dried shrimp")
    dish_facts.prepare(_menu(g2), client=object())
    assert len(cache) == 2  # XO sauce / shrimp is a new concern: asked again


def test_the_old_collisions_stay_apart():
    k = dish_facts._key
    assert k(Dish(id="a", name_en="Noodles", name_zh="阳春面", price=1)) != k(
        Dish(id="a", name_en="Noodles", name_zh="鱿鱼面", price=1)
    )
    assert k(_read("", variant="Chicken")) != k(_read("", variant="Shrimp"))


@pytest.mark.real_dish_facts
def test_a_version_mismatch_is_a_cache_miss(cache, monkeypatch):
    m = _menu(_read("peanuts"))
    dish_facts.prepare(m, client=object())
    assert len(cache) == 1 and dish_facts.coverage(m) == (1, 1)
    monkeypatch.setattr(dish_facts, "VERSION", dish_facts.VERSION + "-next")
    assert dish_facts.coverage(m) == (0, 1)
    dish_facts.prepare(m, client=object())
    assert len(cache) == 2


def test_menu_sheet_asks_nothing_for_a_diner_the_dish_already_rules_out():
    from michelin.plan.edibility import open_questions

    veg = DinerProfile(id="ben", name="Ben", diets=["vegetarian"])
    pork = Dish(
        id="yx", name_en="Yu Xiang (Pork)", price=18, contains_pork=True, is_vegetarian=False
    )
    assert not any("(for Ben)" in q for q in open_questions(pork, [veg]))


@pytest.mark.real_dish_facts
def test_a_version_ignores_the_other_options_listed_in_its_text(cache):
    """Live r8 re-read: "Fried Rice (Shrimp)" once read with "Chicken | Beef | Combo" in its
    text and once without; the version itself is in the key."""

    def fr(desc):
        return Dish(
            id="fr_s",
            name_en="Fried Rice (Shrimp)",
            name_zh="炒饭虾",
            variant="Shrimp",
            price=15,
            description_raw=desc,
        )

    dish_facts.prepare(_menu(fr("Fried Rice. Chicken, Beef, Combo, Vegetable")), client=object())
    dish_facts.prepare(_menu(fr("Fried Rice")), client=object())
    assert len(cache) == 1


@pytest.mark.parametrize("ct", [FLUKE, ""])
def test_fluke_split_options_follow_the_printed_line(ct):
    desc = "Choice of Steamed\nw/ Ginger Scallion / Hunan Fermented Chili / Salt & Pepper / Sweet & Sour"
    split = ["Steamed", "Ginger Scallion", "Hunan Fermented Chili", "Salt & Pepper", "Sweet & Sour"]
    rows = [
        {
            "name_en": "Fluke Fish Filet",
            "price": 28,
            "choice_text": ct,
            "description": desc,
            "choices": [{"name_en": n} for n in split],
        }
    ]
    assert [d.variant for d in rows_to_dishes(rows)] == [
        "Steamed with Ginger Scallion",
        "Hunan Fermented Chili",
        "Salt & Pepper",
        "Sweet & Sour",
    ]
