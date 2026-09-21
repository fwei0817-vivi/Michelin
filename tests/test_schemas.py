"""Every JSON file under data/ must validate against schemas.py."""

import json
from pathlib import Path

from michelin.schemas import Conflict, DinerProfile, Menu, Plan

ROOT = Path(__file__).resolve().parents[1]


def test_all_menus_validate_and_have_unique_ids():
    for path in (ROOT / "data/menus").glob("*.json"):
        menu = Menu.model_validate_json(path.read_text())
        ids = [d.id for d in menu.dishes]
        assert len(ids) == len(set(ids)), f"duplicate dish ids in {path.name}"
        if menu.verified:
            assert all(d.price is not None for d in menu.dishes), f"verified menu {path.name} has a missing price"


def test_all_profiles_validate():
    for path in (ROOT / "data/profiles").glob("*.json"):
        for row in json.loads(path.read_text()):
            DinerProfile.model_validate(row)



def test_fixtures_validate_and_reference_sample_menu():
    menu = Menu.model_validate_json((ROOT / "data/menus/sample_sichuan.json").read_text())
    ids = {d.id for d in menu.dishes}
    plan = Plan.model_validate_json((ROOT / "data/fixtures/plan_sample.json").read_text())
    assert {i.dish_id for i in plan.items} <= ids
    Conflict.model_validate_json((ROOT / "data/fixtures/conflict_sample.json").read_text())
