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


LIVE_MODEL_ENV = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "MICHELIN_LLM_MATCH",
    "MICHELIN_LLM_PROVIDER",
    "MICHELIN_GEMINI_BACKEND",
    "MICHELIN_GEMINI_MODEL",
    "MICHELIN_VISION",
    "MICHELIN_VISION_MODEL",
    "MICHELIN_LLM_MODEL",
)


@pytest.fixture(autouse=True)
def no_live_model_calls(monkeypatch):
    """Tests never reach a real model, even when a developer has a key exported."""
    from michelin import gemini

    for name in LIVE_MODEL_ENV:
        monkeypatch.delenv(name, raising=False)
    gemini.reset_cooldown()
    yield
    gemini.reset_cooldown()
