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


@pytest.fixture(autouse=True)
def recorded_dish_facts(request, monkeypatch, tmp_path):
    """At runtime the AI supplies each dish's facts (plan/dish_facts.py). Tests use the facts
    already recorded in the bundled menu files as that AI answer, so they stay offline and
    deterministic; tests marked real_dish_facts exercise the real path with a fake model."""
    from michelin.plan import dish_facts

    monkeypatch.setattr(dish_facts, "CACHE_PATH", tmp_path / "dish_facts.json")
    if "real_dish_facts" not in request.keywords:
        monkeypatch.setattr(dish_facts, "prepare", lambda menu, client=None: menu)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_dish_facts: use the real AI dish-facts path (tests pass a fake)"
    )
    config.addinivalue_line(
        "markers", "real_llm_path: use the real planner model call (tests pass their own fake)"
    )


def _oracle_answer(menu, request):
    """A stand-in model for API tests: the cheapest order everyone can eat, topped up with
    the cheapest other dishes to about one per person while the budget allows; or a budget
    no-fit. The real validation still runs on it."""
    from michelin.plan import hints
    from michelin.plan.budget import subtotal_cap
    from michelin.plan.edibility import edible_by

    order, _ = hints.cheapest_order(menu, request)
    if not order or not hints._within(menu, request, order):
        return {
            "dishes": [],
            "server_questions": [],
            "no_fit": {
                "reason": "The budget is too low for a dish everyone can eat.",
                "change": "budget",
                "dish_ids": [d.id for d, _ in order or [] if d.category.value != "staple"],
            },
        }
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    chosen = [d for d, _ in order if d.category.value != "staple"]
    spent = sum(d.price * q for d, q in order)
    extras = sorted(
        (
            d
            for d in menu.dishes
            if d.category.value != "staple"
            and d.price is not None
            and d not in chosen
            and d.id not in request.excluded_dish_ids
            and edible_by(d, request.diners)
        ),
        key=lambda d: d.price,
    )
    for d in extras:
        if len(chosen) >= request.n_diners or spent + d.price > cap - 0.01:
            break
        chosen.append(d)
        spent += d.price
    return {
        "dishes": [
            {"dish_id": d.id, "reason": "", "for": edible_by(d, request.diners)} for d in chosen
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
