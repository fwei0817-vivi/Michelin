"""QA round 25 (2026-10-10): the order lists everything the code adds. Plain rice (one per
diner) and any code top-up dish are plan items with a count and a price, the plan subtotal,
tax, tip and per-person include them, and a cached plan served with the AI off keeps them."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from michelin.plan import llm_planner
from michelin.plan.budget import cents, totals
from michelin.schemas import DinerProfile, Menu, TableRequest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.real_llm_path


class Fake:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.answers.pop(0)))


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # calls are faked
    llm_planner._memory.clear()
    menu = Menu.model_validate_json((ROOT / "data/menus/cafe_china.json").read_text())
    rows = json.loads((ROOT / "data/profiles/sample_group.json").read_text())
    diners = [DinerProfile.model_validate(r) for r in rows]
    request = TableRequest(menu_id=menu.restaurant_id, diners=diners, budget_per_person=40)
    from conftest import _oracle_answer

    yield menu, request, _oracle_answer(menu, request)
    llm_planner._memory.clear()


def _assert_rice_and_totals(menu, request, plan):
    known = {d.id: d for d in menu.dishes}
    rice = [i for i in plan.items if known[i.dish_id].category.value == "staple"]
    assert rice, "plain rice is a plan item"
    assert all(i.quantity == request.n_diners for i in rice)
    assert all(known[i.dish_id].price for i in rice), "rice has a price"
    lines = sum(cents(known[i.dish_id].price) * i.quantity for i in plan.items) / 100
    assert plan.subtotal == pytest.approx(lines), "subtotal is the sum of every line, rice included"
    t = totals(lines, request.n_diners, request.tax_rate, request.tip_rate)
    assert (plan.tax, plan.tip, plan.total, plan.per_person) == pytest.approx(
        (t.tax, t.tip, t.total, t.per_person)
    )


def test_rice_is_listed_and_counted(setup, tmp_path):
    menu, request, good = setup
    out = llm_planner.plan(
        menu, request, client=SimpleNamespace(models=Fake(good)), cache_path=tmp_path / "c.json"
    )
    assert out.plan is not None
    _assert_rice_and_totals(menu, request, out.plan)


def test_cached_plan_with_ai_off_keeps_rice(setup, tmp_path, monkeypatch):
    menu, request, good = setup
    first = llm_planner.plan(
        menu, request, client=SimpleNamespace(models=Fake(good)), cache_path=tmp_path / "c.json"
    )
    llm_planner._memory.clear()
    for k in ("GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    again = llm_planner.plan(menu, request, cache_path=tmp_path / "c.json")
    assert again.cached and again.plan is not None
    _assert_rice_and_totals(menu, request, again.plan)
    assert [(i.dish_id, i.quantity) for i in again.plan.items] == [
        (i.dish_id, i.quantity) for i in first.plan.items
    ]
    assert again.plan.per_person == first.plan.per_person
