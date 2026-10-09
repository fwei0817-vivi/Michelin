"""AI planner with a fake Gemini client: the rules accept or reject every answer."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from michelin import api, gemini
from michelin.plan import llm_planner
from michelin.plan.edibility import edible_by
from michelin.plan.optimizer import solve
from michelin.plan.validation import validate_order
from michelin.schemas import DinerProfile, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(api.app)
pytestmark = pytest.mark.real_llm_path


@pytest.fixture(autouse=True)
def gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # provider "gemini"; calls are faked


@pytest.fixture(autouse=True)
def fresh_cache():
    llm_planner._memory.clear()
    yield
    llm_planner._memory.clear()


class FakeModels:
    """Returns the queued answers in order and records every request."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(text=answer if isinstance(answer, str) else json.dumps(answer))


@pytest.fixture
def setup():
    menu = Menu.model_validate_json((ROOT / "data/menus/cafe_china.json").read_text())
    rows = json.loads((ROOT / "data/profiles/sample_group.json").read_text())
    diners = [DinerProfile.model_validate(r) for r in rows]
    request = TableRequest(menu_id=menu.restaurant_id, diners=diners, budget_per_person=40)
    rules = solve(menu, request)
    assert rules.items, "the rules planner must find an order for this group"
    shared = [i for i in rules.items if menu.dish(i.dish_id).category.value != "staple"]
    good = {
        "dishes": [
            {"dish_id": i.dish_id, "reason": f"AI reason for {i.dish_id}", "for": i.edible_by}
            for i in shared
        ],
        "server_questions": ["Is the broth made with pork?"],
    }
    return menu, request, good


def run(menu, request, *answers, tmp_path):
    fake = FakeModels(*answers)
    out = llm_planner.plan(
        menu, request, client=SimpleNamespace(models=fake), cache_path=tmp_path / "c.json"
    )
    return out, fake


def test_valid_answer_becomes_the_plan(setup, tmp_path):
    menu, request, good = setup
    out, fake = run(menu, request, good, tmp_path=tmp_path)
    assert out.plan and out.attempts == 1 and len(fake.calls) == 1
    reasons = {i.dish_id: i.reason for i in out.plan.items}
    assert all(reasons[r["dish_id"]] == r["reason"] for r in good["dishes"])
    assert "Is the broth made with pork?" in out.plan.confirm_with_staff
    assert out.plan.total <= request.all_in_budget
    call = fake.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert call["config"].response_json_schema["required"] == ["dishes", "server_questions"]


def test_invalid_answer_gets_violations_and_a_retry(setup, tmp_path):
    menu, request, good = setup
    too_few = {"dishes": good["dishes"][:1], "server_questions": []}
    out, fake = run(menu, request, too_few, good, tmp_path=tmp_path)
    assert out.plan and out.attempts == 2 and "after 1 correction" in out.note
    feedback = fake.calls[1]["contents"][-1].parts[0].text
    assert "breaks these rules" in feedback and "needs 2" in feedback


def test_hallucinated_dish_is_rejected(setup, tmp_path):
    menu, request, good = setup
    fake_dish = {
        "dishes": [*good["dishes"], {"dish_id": "golden_dragon_lobster", "reason": "x", "for": []}],
        "server_questions": [],
    }
    out, _ = run(menu, request, fake_dish, good, tmp_path=tmp_path)
    assert "'golden_dragon_lobster' is not a dish id on this menu." in out.violations[0]
    assert out.plan and out.attempts == 2


def test_dish_claimed_for_an_allergic_diner_is_rejected(setup, tmp_path):
    menu, request, good = setup
    allergic = next(p for p in request.diners if p.allergies)
    unsafe = next(
        d
        for d in menu.dishes
        if d.category.value != "staple"
        and allergic.id not in edible_by(d, request.diners)
        and edible_by(d, request.diners)
    )
    bad = {
        "dishes": [
            *good["dishes"],
            {"dish_id": unsafe.id, "reason": "x", "for": [allergic.id]},
        ],
        "server_questions": [],
    }
    out, fake = run(menu, request, *[bad] * 4, tmp_path=tmp_path)
    assert out.plan is None and len(fake.calls) == 4  # first try + 3 retries
    assert out.conflict.code == "ai_no_valid_order"
    assert f"not safe for {allergic.name}" in out.conflict.message
    assert any(f"not safe for {allergic.name}" in v for v in out.violations[0])


def test_no_model_answer_is_an_explained_error_not_another_planner(setup, tmp_path):
    from google.genai import errors

    menu, request, _ = setup
    limited = errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})
    out, fake = run(menu, request, limited, tmp_path=tmp_path)
    assert out.plan is None and out.conflict.code == "ai_unavailable"
    assert "rate limit" in out.conflict.message and len(fake.calls) == 1
    gemini.reset_cooldown()
    out, _ = run(menu, request, TimeoutError("slow"), tmp_path=tmp_path)
    assert out.conflict.code == "ai_unavailable" and "did not answer" in out.conflict.message
    out, _ = run(menu, request, *["not json"] * 4, tmp_path=tmp_path)
    assert out.conflict.code == "ai_no_valid_order"


def test_model_no_fit_becomes_a_verified_change_one_thing(setup, tmp_path):
    menu, request, good = setup
    tight = request.model_copy(update={"budget_per_person": 10})
    order = [d["dish_id"] for d in good["dishes"]]
    no_fit = {
        "dishes": [],
        "server_questions": [],
        "no_fit": {"reason": "Too little money for six.", "change": "budget", "dish_ids": order},
    }
    out, fake = run(menu, tight, no_fit, tmp_path=tmp_path)
    assert out.plan is None and len(fake.calls) == 1
    assert out.conflict.code in ("no_solution", "missing_information")
    assert "Too little money" in out.conflict.message
    [change] = out.conflict.relaxations
    assert change.kind == "budget" and change.new_value * 2 == int(change.new_value * 2)
    # The suggested order really passes at the suggested budget, and not 50 cents below.
    raised = tight.model_copy(update={"budget_per_person": change.new_value})
    lower = tight.model_copy(update={"budget_per_person": change.new_value - 0.5})
    items = [PlanItem(dish_id=i, quantity=1) for i in order] + [
        PlanItem(dish_id=d.id, quantity=6) for d in llm_planner._staples(menu, tight)
    ]
    assert validate_order(menu, raised, items)["valid"]
    assert not validate_order(menu, lower, items)["valid"]
    # An order that breaks another rule (an unsafe dish for everyone) gives no budget fix,
    # and a model figure below the current budget is ignored.
    bad = {**no_fit, "no_fit": {**no_fit["no_fit"], "dish_ids": order[:1], "new_value": 5}}
    out, _ = run(menu, tight, bad, tmp_path=tmp_path)
    assert out.conflict.relaxations == []


def test_identical_requests_are_cached(setup, tmp_path):
    menu, request, good = setup
    first, _ = run(menu, request, good, tmp_path=tmp_path)
    llm_planner._memory.clear()  # the file cache alone is enough
    again, fake2 = run(menu, request, tmp_path=tmp_path)
    assert again.cached and again.plan and not fake2.calls
    assert [i.dish_id for i in again.plan.items] == [i.dish_id for i in first.plan.items]


def test_brief_hides_unsafe_and_removed_dishes(setup):
    menu, request, _ = setup
    removed = menu.dishes[0].id
    payload = llm_planner.brief(menu, request.model_copy(update={"excluded_dish_ids": [removed]}))
    assert removed not in {d["id"] for d in payload["dishes"]}
    assert all(d["ok_for"] for d in payload["dishes"])
    assert payload["menu_price_cap"] > 0 and payload["rice_added"]


def _post(menu_id="cafe_china", budget=40):
    profiles = client.get("/api/profiles").json()
    return client.post(
        "/api/plan",
        json={"menu_id": menu_id, "diners": profiles, "budget_per_person": budget, "explain": True},
    )


def test_api_returns_ai_plans_and_explains_failures(setup, monkeypatch):
    good = setup[2]
    monkeypatch.setattr(api, "MOCK", False)
    fake = FakeModels(good)
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=fake))
    body = _post().json()
    assert body["kind"] == "plan" and body["source"] == "ai", body
    assert "AI plan by gemini-3.8-flash" in body["source_note"]
    assert any(i["reason"] == good["dishes"][0]["reason"] for i in body["plan"]["items"])

    llm_planner._memory.clear()
    llm_planner.CACHE_PATH.unlink()
    fake = FakeModels(*[{"dishes": [], "server_questions": []}] * 4)
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=fake))
    body = _post().json()
    assert body["kind"] == "conflict" and body["conflict"]["code"] == "ai_no_valid_order"
    assert len(fake.calls) == 4


def test_without_any_model_there_is_no_recommendation(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setattr(api, "MOCK", False)
    body = _post().json()
    assert body["kind"] == "conflict" and body["conflict"]["code"] == "ai_unavailable"
    assert "OPENROUTER_API_KEY or GEMINI_API_KEY" in body["conflict"]["message"]
    assert client.get("/api/health").json()["planner"] is None


def test_brief_marks_likely_hot_names(setup):
    menu, request, _ = setup
    dish = next(d for d in menu.dishes if d.category.value != "staple")
    hot = dish.model_copy(update={"spice_level": None, "name_en": "Fish in Hot Chili Oil"})
    mild = dish.model_copy(
        update={"id": "soup", "spice_level": None, "name_en": "Hot and Sour Soup"}
    )
    payload = llm_planner.brief(menu.model_copy(update={"dishes": [hot, mild]}), request)
    spice = {d["id"]: d.get("spice") for d in payload["dishes"]}
    assert spice[hot.id] == "unknown, name suggests hot" and spice["soup"] is None
