"""AI planner with a fake Gemini client: the rules accept or reject every answer."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from michelin import api, gemini
from michelin.plan import hints, llm_planner
from michelin.plan.edibility import edible_by
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
    from conftest import _oracle_answer

    good = _oracle_answer(menu, request)
    assert good["dishes"], "a valid order must exist for this group"
    for row in good["dishes"]:
        row["reason"] = f"AI reason for {row['dish_id']}"
    good["server_questions"] = ["Is the broth made with pork?"]
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
    allergic = next(p for p in request.diners if p.allergies)
    others = next(
        d
        for d in menu.dishes
        if d.category.value != "staple"
        and edible_by(d, request.diners)
        and allergic.id not in edible_by(d, request.diners)
    )
    left_out = {
        "dishes": [{"dish_id": others.id, "reason": "x", "for": []}],
        "server_questions": [],
    }
    out, fake = run(menu, request, left_out, good, tmp_path=tmp_path)
    assert out.plan and out.attempts == 2 and "after 1 correction" in out.note
    feedback = fake.calls[1]["contents"][-1].parts[0].text
    assert "breaks these rules" in feedback
    assert f"{allergic.name} ({allergic.id}) cannot eat any chosen dish" in feedback


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
        and d.id not in {r["dish_id"] for r in good["dishes"]}
    )
    bad = {
        "dishes": [
            *good["dishes"],
            {"dish_id": unsafe.id, "reason": "x", "for": [allergic.id]},
        ],
        "server_questions": [],
    }
    out, fake = run(menu, request, *[bad] * 4, tmp_path=tmp_path)
    assert len(fake.calls) == 4  # first try + 3 retries
    # QA r5 D-6: an order exists, so the rules' own cheapest valid order is shown, labelled.
    assert out.fallback and out.plan is not None and out.conflict is None
    assert f"not safe for {allergic.name}" in out.note
    assert unsafe.id not in {i.dish_id for i in out.plan.items}
    assert out.plan.summary == llm_planner.FALLBACK_SUMMARY
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
    assert out.fallback and out.plan is not None


def test_model_no_fit_becomes_a_verified_change_one_thing(setup, tmp_path):
    menu, request, good = setup
    tight = request.model_copy(update={"budget_per_person": 2})
    order = [d["dish_id"] for d in good["dishes"]]
    no_fit = {
        "dishes": [],
        "server_questions": [],
        "no_fit": {"reason": "Too little money for six.", "change": "budget", "dish_ids": order},
    }
    out, fake = run(menu, tight, no_fit, tmp_path=tmp_path)
    assert out.plan is None and len(fake.calls) == 1
    assert out.conflict.code in ("no_solution", "missing_information")
    hint = hints.analyse(menu, tight)
    # QA r5 D-6: the offer has room above the rules minimum, so the AI can hit it.
    low, change = out.conflict.relaxations
    assert (low.kind, low.new_value) == ("budget", hint.suggest)
    assert hint.suggest >= hint.min_per_person + 1.5 and hint.suggest >= hint.min_budget
    assert change.new_value > 1.25 * low.new_value and "fuller meal" in change.description
    # The AI's suggested order really passes at its (roomier) amount.
    raised = tight.model_copy(update={"budget_per_person": change.new_value})
    items = [PlanItem(dish_id=i, quantity=1) for i in order] + [
        PlanItem(dish_id=d.id, quantity=6) for d in llm_planner._staples(menu, tight)
    ]
    assert validate_order(menu, raised, items)["valid"]
    # The model's wording is never shown: only rules figures, always with $.
    assert "Too little money" not in out.conflict.message
    assert f"${hint.min_subtotal:.2f} in menu prices" in out.conflict.message
    assert f"${hint.suggest:.2f} per person fits it with a little room" in out.conflict.message
    assert not re.search(r"(?<![$\d.])\d+\.\d\d", out.conflict.message)  # no bare amounts
    said = "Too little money. You would need 28.45 each; rice is safe for everyone."
    bad = {
        "dishes": [],
        "no_fit": {"reason": said, "change": "budget", "dish_ids": ["lobster"], "new_value": 1},
    }
    out, _ = run(menu, tight, bad, tmp_path=tmp_path)
    assert [(r.kind, r.new_value) for r in out.conflict.relaxations] == [("budget", hint.suggest)]
    assert "28.45" not in out.conflict.message and "safe" not in out.conflict.message


def test_no_fit_always_offers_a_budget_that_fits(setup, tmp_path):
    """Whatever the model says, a budget no-fit offers 'Raise to $X' and X fits."""
    menu, request, good = setup
    tight = request.model_copy(update={"budget_per_person": 3})
    out, fake = run(menu, tight, good, tmp_path=tmp_path)  # over budget: no retries needed
    assert out.plan is None and len(fake.calls) == 1
    [change] = [r for r in out.conflict.relaxations if r.kind == "budget"]
    assert "Raise the budget to $" in change.description
    price = change.new_value
    assert hints.fits(menu, tight.model_copy(update={"budget_per_person": price}))
    assert price == int(price)  # whole dollars
    out, _ = run(menu, tight, {"dishes": [], "server_questions": []}, tmp_path=tmp_path)
    assert [r.new_value for r in out.conflict.relaxations if r.kind == "budget"] == [price]


def test_giving_up_when_an_order_exists_is_retried_with_hints(setup, tmp_path):
    menu, request, good = setup
    give_up = {
        "dishes": [],
        "server_questions": [],
        "no_fit": {"reason": "Nothing fits.", "change": "budget"},
    }
    out, fake = run(menu, request, give_up, good, tmp_path=tmp_path)
    assert out.plan is not None and len(fake.calls) == 2
    feedback = str(fake.calls[1]["contents"][-1])
    assert "exists within the cap" in feedback


def test_brief_names_a_diners_only_option_and_sets_no_dish_count():
    """Ben can eat exactly one dish here, so it must be ordered; the model picks the count."""
    menu = Menu.model_validate_json((ROOT / "data/menus/sample_sichuan.json").read_text())
    only = next(d.id for d in menu.dishes if d.category.value != "staple")
    diners = [DinerProfile(id="ann", name="Ann"), DinerProfile(id="ben", name="Ben")]
    request = TableRequest(menu_id="x", diners=diners, budget_per_person=40)
    payload = llm_planner.brief(menu, request, hints.Hints(True, None, {"ben": [only]}))
    assert payload["only_option"] == {"Ben": only} and payload["an_order_fits"] is True
    assert not {"portion_units", "target_dishes", "min_dishes_per_diner"} & payload.keys()
    assert all("units" not in d for d in payload["dishes"])


def test_any_number_of_dishes_passes_when_everyone_can_eat_one(setup, tmp_path):
    """No portion or count rule: one dish everyone can eat is a valid order."""
    menu, request, _ = setup
    from michelin.plan.edibility import edible_by

    shared = next(
        d
        for d in menu.dishes
        if d.category.value != "staple" and len(edible_by(d, request.diners)) == request.n_diners
    )
    one = {
        "dishes": [{"dish_id": shared.id, "reason": "For everyone.", "for": []}],
        "server_questions": [],
    }
    out, fake = run(menu, request, one, tmp_path=tmp_path)
    assert out.plan is not None and len(fake.calls) == 1
    names = {c.name for c in out.plan.checks}
    assert "portions" not in names


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
    assert body["kind"] == "plan" and body["source"] == "rules", body
    assert "rules built" in body["source_note"] and len(fake.calls) == 4


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


def test_raise_suggestion_prefers_the_smallest_sensible_budget(setup, monkeypatch):
    menu, request, _ = setup
    tight = request.model_copy(update={"budget_per_person": 2})
    hint = SimpleNamespace(min_budget=10.0, suggest=12.0, min_subtotal=20.0, min_per_person=9.9)
    info = {"reason": "", "change": "budget", "dish_ids": ["x"]}
    # Close to the suggestion: one figure.
    monkeypatch.setattr(llm_planner, "_budget_for", lambda *a: 13.0)
    out = llm_planner._conflict(menu, tight, info, [], hint)
    assert [r.new_value for r in out.relaxations] == [12.0]
    # Far above it: the suggestion first, the AI amount (with room) as the fuller option.
    monkeypatch.setattr(llm_planner, "_budget_for", lambda *a: 25.0)
    out = llm_planner._conflict(menu, tight, info, [], hint)
    assert [r.new_value for r in out.relaxations] == [12.0, 26.0]
    assert "$12.00 per person fits it with a little room; $26.00 buys a fuller meal." in out.message


def _thin(menu, request):
    """The rules' cheapest order plus one dish few diners can eat: some diner has 1 dish."""
    order, _ = hints.cheapest_order(menu, request)
    rows = [
        {"dish_id": d.id, "reason": "r", "for": [], "server_question": ""}
        for d, _ in order
        if d.category.value != "staple"
    ]
    narrow = min(
        (
            d
            for d in menu.dishes
            if d.category.value != "staple"
            and d.price is not None
            and 0 < len(edible_by(d, request.diners)) < request.n_diners
            and d.id not in {r["dish_id"] for r in rows}
        ),
        key=lambda d: d.price,
    )
    rows.append({"dish_id": narrow.id, "reason": "r", "for": [], "server_question": ""})
    return {"dishes": rows, "server_questions": []}


def _items(menu, request, answer):
    return llm_planner.check(menu, request, answer, llm_planner._staples(menu, request))[1]


@pytest.mark.coverage
def test_thin_coverage_is_retried_once_then_fixed_in_code(setup, tmp_path):
    """QA r5 #8: a valid in-budget change gives the least-served diner more; the AI is asked
    once, and if it does not even things out the rules make the change."""
    menu, request, _ = setup
    thin = _thin(menu, request)
    before = llm_planner.spread(menu, request, _items(menu, request, thin))
    fix = llm_planner.coverage_fix(menu, request, _items(menu, request, thin))
    assert before[0] < llm_planner.THIN and fix is not None
    assert llm_planner.spread(menu, request, fix.items) > before
    assert validate_order(menu, request, fix.items)["valid"]
    out, fake = run(menu, request, thin, thin, tmp_path=tmp_path)
    assert len(fake.calls) == 2 and "Favour the least-served" in str(fake.calls[1]["contents"])
    assert llm_planner.spread(menu, request, out.plan.items) == llm_planner.spread(
        menu, request, fix.items
    )
    assert "rules swapped one dish" in out.note
    # An AI answer at least as even is taken as is.
    better = llm_planner._apply_fix(thin, fix, menu, request)
    llm_planner._memory.clear()
    out, fake = run(menu, request, thin, better, tmp_path=tmp_path / "b")
    assert len(fake.calls) == 2 and "AI evened out" in out.note


@pytest.mark.coverage
def test_raise_budget_from_3_then_apply_always_gives_a_plan(setup, tmp_path):
    """QA r5 D-6 repro: $3 -> 'Raise the budget to $X' -> apply. X leaves room above the
    cheapest valid order; if the AI still misses it four times, the rules' own cheapest valid
    order is shown, labelled, instead of only 'Try again'."""
    menu, request, good = setup
    tight = request.model_copy(update={"budget_per_person": 3})
    out, _ = run(menu, tight, good, tmp_path=tmp_path)
    [raise_to] = [r for r in out.conflict.relaxations if r.kind == "budget"]
    hint = hints.analyse(menu, tight)
    assert raise_to.new_value >= hint.min_per_person + 1.5
    assert "$" in out.conflict.message and "3.00" in out.conflict.message
    raised = tight.model_copy(update={"budget_per_person": raise_to.new_value})
    assert hints.fits(menu, raised)
    # The AI keeps proposing an order over the cap.
    pricey = sorted(
        (d for d in menu.dishes if d.category.value != "staple" and d.price),
        key=lambda d: -d.price,
    )[:3]
    over = {
        "dishes": [
            {"dish_id": d.id, "reason": "", "for": [], "server_question": ""} for d in pricey
        ],
        "server_questions": [],
    }
    llm_planner._memory.clear()
    out, fake = run(menu, raised, *[over] * 4, tmp_path=tmp_path / "r")
    assert len(fake.calls) == 4 and out.fallback and out.plan is not None
    assert validate_order(menu, raised, out.plan.items)["valid"]
    assert out.plan.summary == llm_planner.FALLBACK_SUMMARY
