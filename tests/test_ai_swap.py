"""AI single-dish swap with a faked model: one dish changes, the rules check the rest."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.plan import ai_swap, llm_planner
from michelin.plan.budget import subtotal_cap
from michelin.plan.edibility import edible_by
from michelin.plan.validation import validate_order
from michelin.schemas import DinerProfile, Menu, TableRequest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.real_llm_path


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # calls are faked below
    llm_planner._memory.clear()


class Fake:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, turns, schema, client):
        self.calls.append({"turns": turns, "schema": schema})
        return json.dumps(self.answers.pop(0)), "google/gemini-2.5-flash"


@pytest.fixture
def table(tmp_path):
    menu = Menu.model_validate_json((ROOT / "data/menus/cafe_china.json").read_text())
    rows = json.loads((ROOT / "data/profiles/sample_group.json").read_text())
    diners = [DinerProfile.model_validate(r) for r in rows]
    request = TableRequest(
        menu_id=menu.restaurant_id, diners=diners, budget_per_person=40, excluded_dish_ids=[]
    )
    from conftest import _oracle_answer

    good = _oracle_answer(menu, request)
    for row in good["dishes"]:
        row["reason"] = f"AI reason for {row['dish_id']}"
    fake = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **k: SimpleNamespace(text=json.dumps(good)))
    )
    out = llm_planner.plan(menu, request, client=fake, cache_path=tmp_path / "c.json")
    assert out.plan is not None
    return menu, request, out.plan


def _target_and_candidate(menu, request, plan, pick=None):
    """A non-staple dish to replace, and a candidate the brief offers."""
    old = next(i.dish_id for i in plan.items if menu.dish(i.dish_id).category.value != "staple")
    brief = ai_swap.brief(menu, ai_swap._swap_request(request, old), plan, old)
    ids = [c["id"] for c in brief["candidates"]]
    new = pick(brief["candidates"]) if pick else ids[0]
    return old, new, brief


def test_only_the_swapped_dish_changes(table, monkeypatch):
    menu, request, plan = table
    old, new, _ = _target_and_candidate(
        menu, request, plan, pick=lambda c: min(c, key=lambda r: r["price"])["id"]
    )
    fake = Fake({"dish_id": new, "reason": "Lighter, and Kevin can eat it.", "server_question": ""})
    meat = next(
        d.id
        for d in menu.dishes
        if d.category.value != "staple" and 0 < len(edible_by(d, request.diners)) < 6
    )
    who = ", ".join(
        p.name for p in request.diners if p.id in edible_by(menu.dish(meat), request.diners)
    )
    line = ai_swap._line(menu, request, old, meat, "Tom likes beef and it suits all diets")
    assert "all diets" not in line and f", for {who}, " in line  # no false "everyone"
    assert ai_swap._line(menu, request, old, new, "Tom likes beef").startswith(
        f"Swapped to {menu.dish(new).name_en}, Tom likes beef, "
    )
    monkeypatch.setattr(ai_swap, "_ask", fake)
    out = ai_swap.swap(menu, request, plan, old)
    assert out.plan is not None and out.new_dish_id == new and len(fake.calls) == 1
    diff = menu.dish(new).price - menu.dish(old).price
    price = (
        "same price"
        if abs(diff) < 0.005
        else f"${abs(diff):.2f} " + ("cheaper" if diff < 0 else "more")
    )
    name = menu.dish(new).name_en
    assert out.message == f"Swapped to {name}, lighter, and Kevin can eat it, {price}."
    before = [(i.dish_id, i.quantity, i.reason) for i in plan.items if i.dish_id != old]
    after = [(i.dish_id, i.quantity, i.reason) for i in out.plan.items if i.dish_id != new]
    assert before == after  # same dishes, same order, same quantities and reasons
    assert [i.dish_id for i in out.plan.items].index(new) == [i.dish_id for i in plan.items].index(
        old
    )
    report = validate_order(menu, ai_swap._swap_request(request, old), out.plan.items)
    assert report["valid"]
    assert out.plan.total == report["totals"]["total"]
    assert out.plan.per_person == report["totals"]["per_person"]
    assert next(i for i in out.plan.items if i.dish_id == new).reason == out.message


def test_brief_has_plan_target_diners_money_left_and_removed(table, monkeypatch):
    menu, request, plan = table
    removed = next(
        d.id
        for d in menu.dishes
        if d.category.value != "staple" and d.id not in {i.dish_id for i in plan.items}
    )
    request = request.model_copy(update={"excluded_dish_ids": [removed]})
    old, _, brief = _target_and_candidate(menu, request, plan)
    ids = {c["id"] for c in brief["candidates"]}
    assert removed not in ids and old not in ids
    assert not ids & {i.dish_id for i in plan.items}
    assert brief["replace"]["id"] == old and removed in brief["removed"] and old in brief["removed"]
    assert {r["id"] for r in brief["order_stays"]} == {i.dish_id for i in plan.items} - {old}
    assert any(d.get("allergies") for d in brief["diners"])
    spent = sum(menu.dish(i.dish_id).price * i.quantity for i in plan.items if i.dish_id != old)
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    assert brief["menu_price_left"] == pytest.approx(cap - spent, abs=0.01)
    assert 0 < brief["all_in_left_for_table"] < request.all_in_budget
    assert all(c["ok_for"] for c in brief["candidates"])


def test_invalid_answer_is_retried_once_with_the_reason(table, monkeypatch):
    menu, request, plan = table
    old, new, _ = _target_and_candidate(menu, request, plan)
    already = next(i.dish_id for i in plan.items if i.dish_id != old)
    fake = Fake(
        {"dish_id": already, "reason": "x", "server_question": ""},
        {"dish_id": new, "reason": "Fixed.", "server_question": ""},
    )
    monkeypatch.setattr(ai_swap, "_ask", fake)
    out = ai_swap.swap(menu, request, plan, old)
    assert out.plan is not None and out.attempts == 2
    feedback = fake.calls[1]["turns"][-1].text
    assert "already in the order" in feedback


def test_two_failures_offer_the_manual_pick(table, monkeypatch):
    menu, request, plan = table
    old, _, _ = _target_and_candidate(menu, request, plan)
    fake = Fake({"dish_id": "lobster", "reason": "x"}, {"dish_id": old, "reason": "x"})
    monkeypatch.setattr(ai_swap, "_ask", fake)
    out = ai_swap.swap(menu, request, plan, old)
    assert out.plan is None and len(fake.calls) == 2
    assert "Pick a replacement from the menu instead." in out.message


def test_over_budget_and_lost_coverage_are_rejected(table):
    menu, request, plan = table
    old, _, brief = _target_and_candidate(menu, request, plan)
    swapped = ai_swap._swap_request(request, old)
    # Budget: the dearest candidate at a budget that only just covers the current order.
    dear = max(brief["candidates"], key=lambda c: c["price"])["id"]
    tight = swapped.model_copy(update={"budget_per_person": plan.per_person})
    problems, _ = ai_swap.check(menu, tight, plan, old, {"dish_id": dear})
    if menu.dish(dear).price > menu.dish(old).price:
        assert any("your budget allows" in p for p in problems)
    # Coverage: a one-dish order for someone who can then eat nothing.
    vegetarian = DinerProfile(id="v", name="Vee", diets=["vegetarian"])
    solo = swapped.model_copy(update={"diners": [vegetarian], "budget_per_person": 500})
    veg = next(
        d.id for d in menu.dishes if d.category.value != "staple" and edible_by(d, [vegetarian])
    )
    meat = next(
        d.id for d in menu.dishes if d.category.value != "staple" and not edible_by(d, [vegetarian])
    )
    one = plan.model_copy(update={"items": [plan.items[0].model_copy(update={"dish_id": veg})]})
    problems, _ = ai_swap.check(menu, solo, one, veg, {"dish_id": meat})
    assert any(
        "nobody at the table can eat it" in p or "could no longer eat" in p for p in problems
    )


def test_swap_endpoint(table, monkeypatch):
    menu, request, plan = table
    old, new, _ = _target_and_candidate(menu, request, plan)
    monkeypatch.setattr(ai_swap, "_ask", Fake({"dish_id": new, "reason": "Good swap."}))
    body = {
        "menu_id": "cafe_china",
        "diners": [d.model_dump(mode="json") for d in request.diners],
        "budget_per_person": 40,
        "plan": plan.model_dump(mode="json"),
        "dish_id": old,
    }
    client = TestClient(api.app)
    r = client.post("/api/plan/swap", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kind"] == "plan" and data["new_dish_id"] == new
    assert (
        data["message"].endswith(("more.", "cheaper.", "same price."))
        and "checked by the rules" in data["source_note"]
    )
    assert len(data["plan"]["items"]) == len(plan.items)
    monkeypatch.setattr(ai_swap, "_ask", Fake({"dish_id": "x"}, {"dish_id": "y"}))
    data = client.post("/api/plan/swap", json=body).json()
    assert data["kind"] == "failed" and "from the menu" in data["message"]
    assert client.post("/api/plan/swap", json={**body, "dish_id": "nope"}).status_code == 404


def _no_model(*a, **k):
    raise AssertionError("a manual pick must not call the model")


def test_manual_pick_changes_only_that_dish_without_a_model_call(table, monkeypatch):
    menu, request, plan = table
    monkeypatch.setattr(ai_swap, "_ask", _no_model)
    old, new, _ = _target_and_candidate(menu, request, plan)
    out = ai_swap.manual(menu, request, plan, old, new)
    assert out.plan is not None and out.model is None
    assert [i.dish_id for i in out.plan.items] == [
        new if i.dish_id == old else i.dish_id for i in plan.items
    ]
    assert out.message.startswith(f"Swapped to {menu.dish(new).name_en}, ")
    report = validate_order(menu, ai_swap._swap_request(request, old), out.plan.items)
    assert report["valid"] and out.plan.total == report["totals"]["total"]


def test_manual_pick_that_breaks_a_rule_says_why(table, monkeypatch):
    menu, request, plan = table
    monkeypatch.setattr(ai_swap, "_ask", _no_model)
    old, _, brief = _target_and_candidate(menu, request, plan)
    dear = max(brief["candidates"], key=lambda c: c["price"])["id"]
    assert menu.dish(dear).price > menu.dish(old).price
    tight = request.model_copy(update={"budget_per_person": plan.per_person})
    out = ai_swap.manual(menu, tight, plan, old, dear)
    assert out.plan is None and "your budget allows" in out.message
    assert out.message.startswith(f"{menu.dish(dear).name_en} can't replace")
    taken = next(i.dish_id for i in plan.items if i.dish_id != old)
    out = ai_swap.manual(menu, request, plan, old, taken)
    assert out.plan is None and "already in the order" in out.message
    # Diets: a meat dish for a vegetarian-only table is refused, not rebalanced around.
    vee = DinerProfile(id="v", name="Vee", diets=["vegetarian"])
    solo = request.model_copy(update={"diners": [vee], "budget_per_person": 500})
    veg = next(d.id for d in menu.dishes if d.category.value != "staple" and edible_by(d, [vee]))
    meat = next(
        d.id for d in menu.dishes if d.category.value != "staple" and not edible_by(d, [vee])
    )
    one = plan.model_copy(update={"items": [plan.items[0].model_copy(update={"dish_id": veg})]})
    out = ai_swap.manual(menu, solo, one, veg, meat)
    assert out.plan is None and "nobody at the table can eat it" in out.message


def test_manual_pick_endpoint(table, monkeypatch):
    menu, request, plan = table
    monkeypatch.setattr(ai_swap, "_ask", _no_model)
    old, new, _ = _target_and_candidate(menu, request, plan)
    body = {
        "menu_id": "cafe_china",
        "diners": [d.model_dump(mode="json") for d in request.diners],
        "budget_per_person": 40,
        "plan": plan.model_dump(mode="json"),
        "dish_id": old,
        "new_dish_id": new,
    }
    data = TestClient(api.app).post("/api/plan/swap", json=body).json()
    assert data["kind"] == "plan" and data["new_dish_id"] == new
    assert data["source_note"] == "Your pick, checked by the rules."
    assert [i["dish_id"] for i in data["plan"]["items"]] == [
        new if i.dish_id == old else i.dish_id for i in plan.items
    ]


def test_adding_a_dish_changes_nothing_else(table, monkeypatch):
    menu, request, plan = table
    monkeypatch.setattr(ai_swap, "_ask", _no_model)
    _, new, _ = _target_and_candidate(menu, request, plan)
    out = ai_swap.manual(menu, request, plan, None, new)
    assert out.plan is not None
    ids = [i.dish_id for i in out.plan.items]
    assert [i for i in ids if i != new] == [i.dish_id for i in plan.items]
    assert menu.dish(ids[-1]).category.value == "staple"  # added before the rice
    assert out.message.startswith(f"Added {menu.dish(new).name_en}, ")
    assert out.message.endswith(f"${menu.dish(new).price:.2f} more.")
    report = validate_order(menu, request, out.plan.items)
    assert report["valid"] and out.plan.total == report["totals"]["total"]
    # Over budget: refused with the reason, not rebalanced.
    tight = request.model_copy(update={"budget_per_person": plan.per_person})
    out = ai_swap.manual(menu, tight, plan, None, new)
    assert (
        out.plan is None and "can't be added" in out.message and "your budget allows" in out.message
    )
    taken = plan.items[0].dish_id
    out = ai_swap.manual(menu, request, plan, None, taken)
    assert out.plan is None and "already in the order" in out.message


def test_add_endpoint(table, monkeypatch):
    menu, request, plan = table
    monkeypatch.setattr(ai_swap, "_ask", _no_model)
    _, new, _ = _target_and_candidate(menu, request, plan)
    body = {
        "menu_id": "cafe_china",
        "diners": [d.model_dump(mode="json") for d in request.diners],
        "budget_per_person": 40,
        "plan": plan.model_dump(mode="json"),
        "new_dish_id": new,
    }
    client = TestClient(api.app)
    data = client.post("/api/plan/swap", json=body).json()
    assert data["kind"] == "plan" and len(data["plan"]["items"]) == len(plan.items) + 1
    assert data["message"].startswith("Added ")
    assert client.post("/api/plan/swap", json={**body, "new_dish_id": None}).status_code == 422
