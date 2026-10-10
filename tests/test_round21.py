"""QA round 20 fixes (2026-10-10): code tops up a short order, the enough-food line reads
as plain sentences with the right cause, a short order never blocks the ticket (web test),
noodles printed as "staple" are food, misread name pairs are never "ok" for an allergic
diner, and the course cache is never written at runtime."""

import itertools
import json
import re

import pytest
from test_round19 import YUKINO, _d, _menu, _req, cafe_mandarin  # noqa: F401

from michelin import explain
from michelin.parse import vision
from michelin.plan import courses, dish_facts, edibility, enough, names
from michelin.schemas import Allergen, DinerProfile, Dish, PlanItem

pytestmark = [pytest.mark.real_dish_facts]


def _items(*ids):
    return [PlanItem(dish_id=i, quantity=1) for i in ids]


def _sentences_ok(line):
    assert "has only" not in line.split(".")[0] or line.count("has only") <= 1 or "  " not in line
    assert not re.search(r"has only \S+ \S+ has only", line), line  # QA r20 broken join
    assert "only 0 " not in line, line
    for s in re.split(r"(?<=\.) ", line):
        assert s[0].isupper() and s.endswith("."), (s, line)


# -- 1. every message combination ------------------------------------------------------
def test_every_message_combination_is_plain_sentences():
    meat = {"veg": False}
    m = _menu(
        [
            _d("cold1", "cold_appetizer", 8),
            _d("soup1", "soup", 6),
            _d("tofu", "stir_fry", 14),
            _d("greens", "stir_fry", 12),
            _d("noodle", "other", 13, "staple"),
            _d("pork", "stir_fry", 15, **meat),
            _d("beef", "stir_fry", 16, **meat),
        ]
    )
    pat, quinn = DinerProfile(id="p", name="Pat"), DinerProfile(id="q", name="Quinn")
    veg = DinerProfile(id="v", name="Vera", diets=["vegetarian"])
    seen = set()
    for diners in ([pat, quinn], [pat, veg], [pat, quinn, veg]):
        for budget in (6, 15, 60):
            req = _req(diners, budget)
            for k in (1, 2, 3):
                for combo in itertools.combinations(
                    ["cold1", "soup1", "tofu", "pork", "beef", "noodle"], k
                ):
                    line = enough.honest_line(m, req, _items(*combo))
                    if line:
                        _sentences_ok(line)
                        seen.add(re.sub(r"\d+|Pat|Quinn|Vera", "#", line))
    # all message kinds were produced: hot count, no dish, only 1 dish, no hot dish, budget
    joined = " ".join(seen)
    for part in (
        "hot dish",
        "has no dish",
        "has only # dish",
        "has no hot dish",
        "budget is too tight",
    ):
        assert part in joined, part


def test_cause_is_the_menu_not_the_budget():
    """Wo Hop shape: nothing on the menu is 'ok' for the vegetarian; budget is fine."""
    m = _menu(
        [
            _d("pork", "stir_fry", 10, veg=False),
            _d("beef", "stir_fry", 11, veg=False),
            _d("soup", "soup", 5, veg=False),
        ]
    )
    diners = [
        DinerProfile(id="p", name="Pat"),
        DinerProfile(id="v", name="Vera", diets=["vegetarian"]),
    ]
    line = enough.honest_line(m, _req(diners, 80), _items("pork", "beef"))
    assert "This menu has too few dishes Vera can eat without asking." in line, line
    assert "budget" not in line, line


def test_code_tops_up_the_cheapest_hot_dish_within_budget(cafe_mandarin):  # noqa: F811
    """Yukino's table at $25: the QA order (3 hot dishes, $17 left) is fixed by code."""
    req = _req(YUKINO, 25)
    ids = ["cucumber_salad_garlic", "tomato_egg", "sesame_tofu", "fried_rice_vegetable"]
    ids = [i for i in ids if cafe_mandarin.dish(i)]
    assert len(ids) == 4
    short = _items(*ids)
    assert enough.deficit([cafe_mandarin.dish(i) for i in ids], YUKINO) > 0
    fixed, added, _dropped = enough.top_up(cafe_mandarin, req, short)
    assert added and enough.honest_line(cafe_mandarin, req, fixed) is None
    from michelin.plan.validation import validate_order

    assert validate_order(cafe_mandarin, req, fixed)["valid"]


def test_top_up_keeps_locked_dishes(cafe_mandarin):  # noqa: F811
    ids = ["cucumber_salad_garlic", "tomato_egg", "sesame_tofu", "fried_rice_vegetable"]
    req = _req(YUKINO, 25).model_copy(update={"locked_dish_ids": ids})
    out = enough.top_up(cafe_mandarin, req, _items(*ids))
    assert out is None or set(ids) <= {i.dish_id for i in out[0]}


# -- 3. noodles printed as "staple" ----------------------------------------------------
def test_only_plain_rice_is_a_staple():
    dan = Dish(id="dd", name_en="Dan Dan Noodle", name_zh="担担面", price=12, category="staple")
    rice = Dish(id="r", name_en="Steamed Rice", name_zh="米饭", price=2, category="staple")
    assert dish_facts.plain_rice_only(dan).category.value == "other"
    assert dish_facts.plain_rice_only(dan).course == "staple"
    assert dish_facts.plain_rice_only(rice).category.value == "staple"
    assert enough.is_hot(dish_facts.plain_rice_only(dan))
    assert courses._by_name(Dish(id="c", name_en="Cold Sesame Noodles", price=8)) == "cold"
    assert (
        courses._by_name(Dish(id="g", name_en="Wheat Gluten", name_zh="烤麸面筋", price=8)) is None
    )


def test_atlas_dan_dan_counts_and_is_pickable():
    from pathlib import Path

    from michelin.schemas import Menu

    root = Path(__file__).resolve().parents[1]
    m = dish_facts.prepare(
        Menu.model_validate_json((root / "data/menus/atlas_kitchen.json").read_text())
    )
    dd = next(d for d in m.dishes if "dan dan" in (d.name_en or "").lower())
    assert dd.category.value != "staple" and enough.is_hot(dd)


# -- 4. misread name pairs (North Garden) ----------------------------------------------
NG = [
    ("Pan Fried Pork Bun", "巧手潮州蒸粉果"),
    ("Steamed Beef Tendon in Soup", "古法馬拉糕"),
    ("Steamed Egg Custard Buns", "京式叉燒包"),
    ("Steamed Pork Dumpling with Crab Roe", "黃金流沙包"),
]


def test_misread_pairs_are_flagged_and_true_pairs_are_not():
    for en, zh in NG:
        assert names.mismatch(en, zh), (en, zh)
    for en, zh in [
        ("Chiu Chow Dumplings", "巧手潮州蒸粉果"),
        ("Malay Sponge Cake", "古法馬拉糕"),
        ("BBQ Pork Buns", "京式叉燒包"),
        ("Yu Xiang Eggplant", "鱼香茄子"),
        ("Crab with Pork Soup Dumplings (6Pc)", "蟹粉小笼包"),
        ("Scramble Egg & Chopped Tomato", "山海番茄炒鸡蛋"),
        ("Hunan Beef", "小炒黄牛肉"),
    ]:
        assert not names.mismatch(en, zh), (en, zh)


def test_misread_dish_is_never_ok_for_an_allergic_diner():
    ellie = DinerProfile(id="e", name="Ellie", allergies=["egg"])
    pat = DinerProfile(id="p", name="Pat", allergies=["peanut", "shellfish"])
    free = DinerProfile(id="f", name="Fay")
    for (en, zh), i in zip(NG[:2], ("fenguo", "malai")):
        d = Dish(
            id=i,
            name_en=en,
            name_zh=zh,
            price=6,
            category="other",
            is_vegetarian=False,
            is_vegan=False,
            contains_pork=True,
            contains_beef=False,
            reviewed_allergens=list(Allergen),  # the misread description said "nothing"
        )
        d = d.model_copy(update={"names_clash": names.mismatch(en, zh)})
        st = edibility.diner_status(d, [ellie, pat, free])
        assert st["e"]["status"] != "ok" and st["p"]["status"] != "ok", st
        assert st["f"]["status"] == "ok"
        r = explain.reason_for(d, 1, _req([ellie, pat, free]))
        assert "Everyone can share this" not in r or "if the server confirms" in r, r


def test_partial_read_and_currency_are_stated():
    vision.LAST_PRINTED["k"] = 110
    vision.LAST_CURRENCY["k"] = "HKD"
    assert "Only 18 of about 110 dishes" in vision.partial_note(18, "k")
    assert vision.partial_note(100, "k") == ""
    assert "HKD, not US dollars" in vision.currency_note("k")
    assert vision.currency_note("none") == ""


def test_advisory_schema_fields_keep_committed_read_keys():
    assert "printed_dish_count" not in json.dumps(vision._key_schema())


# -- 5. the committed course cache is read only at runtime -----------------------------
def test_runtime_never_writes_the_committed_course_cache(monkeypatch, tmp_path):
    committed = tmp_path / "committed.json"
    committed.write_text("{}")
    monkeypatch.setattr(courses, "CACHE_PATH", committed)
    monkeypatch.setattr(courses, "LOCAL_PATH", tmp_path / "local.json")
    monkeypatch.setattr(
        courses, "_ask", lambda batch, client=None: {d.id: "hot_main" for d in batch}
    )
    d = Dish(id="x", name_en="Mystery Plate", price=9, category="other")
    courses.annotate([d], client=object())
    assert committed.read_text() == "{}"
    assert json.loads((tmp_path / "local.json").read_text())


# -- non-blocking: known-spicy dishes --------------------------------------------------
def test_known_spicy_dishes_are_at_least_spicy():
    from michelin.plan import spice

    for n in ("Kung Pao Chicken", "Mapo Tofu", "麻婆豆腐"):
        assert spice.level(Dish(id="k", name_en=n, price=10, menu_spice=1)) >= 2, n
