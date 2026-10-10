"""QA round 12 (8f2a37c): no raw AI text reaches the UI. Every AI string goes through the
one gate in michelin.plan.ai_text; these tests prove it, and fix the less-spicy subtitle."""

import json

import pytest
from test_round11 import Fake, client, demo  # noqa: F401 - fixture

from michelin.plan import ai_swap, ai_text, llm_planner
from michelin.schemas import Menu, TableRequest

pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]
FALSE = (
    "We swapped the spicy beef for a mild broccoli tofu dish, ensuring a delicious and "
    "heat-free meal for everyone."
)
CURRENT = [
    "cucumber_salad_garlic",
    "sichuan_boiled_beef_in_chili_oil_sliced_beef",
    "chilled_zucchini_in_tangy_sauce",
    "hong_kong_rice_noodle",
    "tomato_egg",
]
AFTER = [
    "cucumber_salad_garlic",
    "broccoli_tofu",
    "chilled_zucchini_in_tangy_sauce",
    "hong_kong_rice_noodle",
    "tomato_egg",
]


def _plain(diners):
    # Mia's custom words need per-menu facts the offline fixture lacks; the standard
    # allergies and diets are enough to exercise every check here.
    return [{**d, "other_allergies": [], "other_diets": []} for d in diners]


def _facts(demo):  # noqa: F811
    """The demo menu with its committed facts (0 AI calls) and plain diners."""
    menu, diners = demo
    menu = client.post("/api/menu/facts", json=menu).json()
    return menu, _plain(diners)


def _answer(menu, diners, ids, note="", reason=""):
    """An AI answer that counts each dish only for the diners the rules allow."""
    from michelin.plan.edibility import edible_by
    from michelin.schemas import DinerProfile

    m = Menu.model_validate(menu)
    people = [DinerProfile.model_validate(d) for d in diners]
    return {
        "dishes": [
            {
                "dish_id": i,
                "reason": reason,
                "for": edible_by(m.dish(i), people),
                "server_question": "",
            }
            for i in ids
        ],
        "server_questions": [],
        "change_note": note,
    }


def _post(menu, diners, current, chips=("less_spicy",)):
    return client.post(
        "/api/plan",
        json={
            "menu_id": "local-1",
            "menu_override": menu,
            "diners": diners,
            "budget_per_person": 40,
            "tax_rate": 0.08875,
            "tip_rate": 0.18,
            "feedback": {
                "chips": list(chips),
                "text": "",
                "current": [{"dish_id": i, "quantity": 1} for i in current],
            },
        },
    ).json()


def test_r12_repro_less_spicy_subtitle_is_true(demo, monkeypatch):  # noqa: F811
    menu, diners = _facts(demo)
    answer = _answer(menu, diners, AFTER, "Swapped the beef for broccoli tofu")
    answer["summary"] = FALSE
    monkeypatch.setattr(llm_planner, "_ask", Fake(answer))
    r = _post(menu, diners, CURRENT)
    assert r["kind"] == "plan", r
    summary = r["plan"]["summary"]
    assert summary != FALSE and "heat-free" not in summary and "beef" not in summary.lower()
    assert "a little spicy" in summary  # Chilled Zucchini stays: card says "A little spicy"
    assert "5 dishes to share" in summary


def _menu_req(menu, diners):
    return Menu.model_validate(menu), TableRequest(
        menu_id="local-1", diners=diners, budget_per_person=40, tax_rate=0.08875, tip_rate=0.18
    )


def test_summary_gate_checks_each_kind_of_claim(demo):  # noqa: F811
    menu, diners = _facts(demo)
    m, req = _menu_req(menu, diners)
    items = [llm_planner.PlanItem(dish_id=i, quantity=1, edible_by=[]) for i in AFTER]
    ok = "A varied spread with something for each of you."
    assert ai_text.summary(ok, m, req, items) == ok
    assert ai_text.summary(FALSE, m, req, items) is None  # heat-free + beef not on order
    assert ai_text.summary("A heat-free dinner.", m, req, items) is None  # spice
    assert ai_text.summary("Three dishes to share.", m, req, items) is None  # count
    assert ai_text.summary("The Kung Pao keeps it lively.", m, req, items) is None  # dish
    assert ai_text.summary("A fully vegan table.", m, req, items) is None  # diet
    assert ai_text.summary("Everything here is egg-free.", m, req, items) is None  # allergen
    name = diners[0]["name"]
    assert ai_text.summary(f"Plenty for {name}.", m, req, items) is not None


def test_stale_summary_is_revalidated_after_a_swap(demo):  # noqa: F811
    menu, diners = _facts(demo)
    m, req = _menu_req(menu, diners)
    before = [llm_planner.PlanItem(dish_id=i, quantity=1, edible_by=[]) for i in CURRENT]
    after = [llm_planner.PlanItem(dish_id=i, quantity=1, edible_by=[]) for i in AFTER]
    plan = llm_planner.Plan(
        items=before,
        subtotal=1,
        tax=0,
        tip=0,
        total=1,
        per_person=1,
        variety_score=0,
        summary="The Sichuan boiled beef brings the heat.",
    )
    out = plan.model_copy(update={"items": after})
    s = ai_swap._summary_after(m, req, plan, CURRENT[1], out)
    assert "beef" not in s.lower() and s == ai_text.code_summary(m, req, after)


TOKEN = "zqxv"


def _ai_strings(obj, found):
    if isinstance(obj, str):
        if TOKEN in obj.lower():
            found.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _ai_strings(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _ai_strings(v, found)
    return found


def _assert_gated(response):
    for s in _ai_strings(response, []):
        assert any(a in s for a in ai_text.APPROVED), f"AI text bypassed ai_text: {s!r}"


def test_no_ai_text_bypasses_the_gate(demo, monkeypatch):  # noqa: F811
    """Every AI-writable field carries a marker word. Any response string with the marker
    must contain a string the gate approved; a new field that skips the gate fails here."""
    menu, diners = _facts(demo)
    ai_text.APPROVED.clear()
    answer = _answer(menu, diners, AFTER, reason=f"A nice {TOKEN} pick.")
    for row in answer["dishes"]:
        row["server_question"] = f"Is the {TOKEN} sauce halal?"
    answer = {
        **answer,
        "server_questions": [f"Any {TOKEN} in the stock?"],
        "change_note": f"Swapped the beef for broccoli tofu {TOKEN}",
        "summary": f"A relaxed {TOKEN} spread.",
        "no_fit": {"reason": f"{TOKEN} nothing fits", "change": "budget"},
    }
    monkeypatch.setattr(llm_planner, "_ask", Fake(answer))
    r = _post(menu, diners, CURRENT, chips=("cheaper",))
    assert r["kind"] == "plan", r
    _assert_gated(r)
    r2 = _post(menu, diners, CURRENT, chips=("less_spicy",))
    _assert_gated(r2)
    plan = r["plan"]
    assert any(TOKEN in (i.get("reason") or "") for i in plan["items"])  # (b) does show
    # swap: the AI's short clause
    swap_answer = {"dish_id": "broccoli_chicken", "reason": f"a {TOKEN} favourite"}
    monkeypatch.setattr(ai_swap, "_ask", lambda t, s, c: (json.dumps(swap_answer), "fake"))
    r3 = client.post(
        "/api/plan/swap",
        json={
            "menu_id": "local-1",
            "menu_override": menu,
            "diners": diners,
            "budget_per_person": 40,
            "tax_rate": 0.08875,
            "tip_rate": 0.18,
            "plan": plan,
            "dish_id": "tomato_egg",
        },
    ).json()
    _assert_gated(r3)


def test_gate_test_catches_a_bypass():
    ai_text.APPROVED.clear()
    with pytest.raises(AssertionError):
        _assert_gated({"plan": {"summary": f"raw {TOKEN} text"}})
