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
    "OPENROUTER_API_KEY",
    "MICHELIN_OPENROUTER_MODEL",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "MICHELIN_LLM_MATCH",
    "MICHELIN_LLM_PROVIDER",
    "MICHELIN_GEMINI_BACKEND",
    "MICHELIN_GEMINI_MODEL",
    "MICHELIN_VISION",
    "MICHELIN_VISION_MODEL",
    "MICHELIN_LLM_MODEL",
    "MICHELIN_PLANNER_MODEL",
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


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_llm_path: use the real planner model call (tests pass their own fake)"
    )


def _oracle_answer(menu, request):
    """A stand-in model for API tests: it answers with the rules optimizer's order, or a
    no-fit with the optimizer's suggested change. The real validation still runs on it."""
    from michelin.plan.optimizer import solve
    from michelin.schemas import Conflict

    result = solve(menu, request)
    if isinstance(result, Conflict):
        change = next(iter(result.relaxations), None)
        return {
            "dishes": [],
            "server_questions": [],
            "no_fit": {
                "reason": result.message,
                "change": change.kind if change else "budget",
                "new_value": change.new_value if change and change.new_value else 0,
            },
        }
    return {
        "dishes": [
            {"dish_id": i.dish_id, "reason": i.reason or "", "for": i.edible_by}
            for i in result.items
            if menu.dish(i.dish_id).category.value != "staple"
        ],
        "server_questions": [],
    }


@pytest.fixture(autouse=True)
def oracle_planner(request, monkeypatch, tmp_path):
    """API tests get plans without a network call; tests marked real_llm_path opt out."""
    from michelin.plan import llm_planner

    monkeypatch.setattr(llm_planner, "CACHE_PATH", tmp_path / "llm_plans.json")
    llm_planner._memory.clear()
    if request.node.get_closest_marker("real_llm_path"):
        yield
        return

    def fake_ask(turns, schema, menu, table, client):
        return json.dumps(_oracle_answer(menu, table)), "oracle-test-model"

    monkeypatch.setattr(llm_planner, "_ask", fake_ask)
    monkeypatch.setattr(llm_planner, "enabled", lambda: True)
    yield
    llm_planner._memory.clear()
