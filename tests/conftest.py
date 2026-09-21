import json
from pathlib import Path

import pytest

from michelin.schemas import DinerProfile, Menu

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_menu() -> Menu:
    return Menu.model_validate_json((ROOT / "data/menus/sample_sichuan.json").read_text())


@pytest.fixture
def sample_group() -> list[DinerProfile]:
    rows = json.loads((ROOT / "data/profiles/sample_group.json").read_text())
    return [DinerProfile.model_validate(r) for r in rows]
