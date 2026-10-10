"""Regression tests for QA round 10 (1a9bf87): the committed demo read checked against the
PDF text, the Wo Hop no-fit count, and the bundled default menu's facts."""

import json
from pathlib import Path

from michelin.parse import vision
from michelin.plan import dish_facts, llm_planner
from michelin.schemas import DinerProfile, Menu, TableRequest

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"


def _demo(monkeypatch):
    monkeypatch.setattr(vision, "READ_CACHE", ROOT / "data/menu_reads")
    monkeypatch.setattr(dish_facts, "CACHE_PATH", ROOT / "data/facts/dish_facts.json")
    key = vision.read_key([(ROOT / "test-menus/cafe-mandarin.pdf").read_bytes()])
    hit = vision.cached_read(key)
    assert hit is not None
    return vision.rows_to_dishes(hit["rows"])


def test_demo_read_matches_the_printed_vp_marks(monkeypatch):
    dishes = _demo(monkeypatch)
    vp = [d.name_en for d in dishes if "vegetarian_possible" in [m.value for m in d.menu_marks]]
    assert len(vp) == 27
    wok = next(d for d in dishes if d.name_en == "Wok Organic Cauliflower with Pork Belly")
    assert [m.value for m in wok.menu_marks] == ["gluten_free_possible"]


def test_demo_read_peppers_and_names_follow_the_pdf(monkeypatch):
    by = {d.name_en: d for d in _demo(monkeypatch)}
    assert by["Cucumber Salad (Spicy Chili Oil)"].menu_spice == 1
    assert by["Cucumber Salad (Garlic)"].menu_spice is None
    assert by["Fluke Fish Filet (Hunan Fermented Chili)"].menu_spice == 1
    for other in ("Steamed w/ Ginger Scallion", "Salt & Pepper", "Sweet & Sour"):
        assert by[f"Fluke Fish Filet ({other})"].menu_spice is None
    kung = [d for d in by.values() if d.family_name == "Kung Pao Chicken (Spicy)"]
    assert len(kung) == 4 and "Kung Pao Chicken (Spicy)" in by


def test_demo_import_needs_no_ai(monkeypatch):
    dishes = _demo(monkeypatch)
    menu = Menu(
        restaurant_id="cm",
        restaurant_name="CM",
        cuisine="x",
        source="t",
        verified=True,
        dishes=dishes,
    )
    cache = dish_facts._load()
    assert all(dish_facts._key(d) in cache for d in dishes)  # exact keys, no fallback
    assert dish_facts.coverage(menu) == (100, 100)


def test_default_menu_atlas_kitchen_has_committed_facts(monkeypatch):
    monkeypatch.setattr(dish_facts, "CACHE_PATH", ROOT / "data/facts/dish_facts.json")
    menu = Menu.model_validate_json((ROOT / "data/menus/atlas_kitchen.json").read_text())
    found, total = dish_facts.coverage(menu)
    assert found == total


def test_wo_hop_no_fit_counts_soy_sauce_like_the_rules():
    menu = Menu.model_validate(json.loads((FIX / "qa_r10_wohop_menu.json").read_text()))
    request = TableRequest(
        menu_id="wohop",
        diners=[
            DinerProfile(id="a", name="Ana"),
            DinerProfile(id="w", name="Wendy", allergies=["wheat"]),
        ],
        budget_per_person=40,
    )
    conflict = llm_planner.nothing_for(menu, request)
    assert conflict is not None
    assert "all 48 dishes" in conflict.message and "45 of them use soy sauce" in conflict.message
