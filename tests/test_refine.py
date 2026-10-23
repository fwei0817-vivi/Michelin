"""'What should change?': the AI revises the current order from feedback; the code computes
what changed and keeps the AI's one-line note only if it matches."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.plan import llm_planner, refine
from michelin.schemas import Menu

client = TestClient(api.app)
pytestmark = pytest.mark.real_llm_path
MENU = Menu.model_validate_json(Path("data/menus/sample_sichuan.json").read_text())
DINERS = [{"id": "li", "name": "Li"}, {"id": "jo", "name": "Jo"}]
CURRENT = [
    {"dish_id": "mapo_tofu", "quantity": 1},
    {"dish_id": "kung_pao_chicken", "quantity": 1},
    {"dish_id": "steamed_rice", "quantity": 2},
]


class FakeAsk:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, turns, schema, menu, table, client):
        self.calls.append((turns, schema))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return json.dumps(a), "fake-model"


def order(*ids, note=None):
    out = {
        "dishes": [
            {"dish_id": i, "reason": "", "for": ["li", "jo"], "server_question": ""} for i in ids
        ],
        "server_questions": [],
    }
    if note is not None:
        out["change_note"] = note
    return out


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(llm_planner, "enabled", lambda: True)

    def install(*answers):
        f = FakeAsk(*answers)
        monkeypatch.setattr(llm_planner, "_ask", f)
        return f

    return install


def post(feedback=None, locked=()):
    body = {
        "menu_id": "sample_sichuan",
        "diners": DINERS,
        "budget_per_person": 40,
        "locked_dish_ids": list(locked),
    }
    if feedback is not None:
        body["feedback"] = feedback
    return client.post("/api/plan", json=body).json()


def test_note_claims_are_checked_against_the_diff():
    d = refine.diff(
        MENU,
        [("mapo_tofu", 1), ("kung_pao_chicken", 1)],
        [("garlic_seasonal_greens", 1), ("di_san_xian", 1)],
    )
    assert refine.note_ok("Swapped 2 spicy dishes for milder ones", d)
    assert not refine.note_ok("Swapped 3 spicy dishes for milder ones", d)
    assert not refine.note_ok("Made it spicier", d)
    assert refine.note_ok("Cheaper and milder: swapped mapo tofu and kung pao", d)
    up = refine.diff(MENU, [("garlic_seasonal_greens", 1)], [("boiled_fish_chili_oil", 1)])
    assert not refine.note_ok("Made it cheaper", up)
    assert refine.note_ok("Added more seafood", up)
    same = refine.diff(MENU, [("mapo_tofu", 1)], [("mapo_tofu", 1)])
    assert not refine.note_ok("Swapped a dish", same) and refine.note_ok("No change needed", same)
    assert refine.note_ok("Kept all dishes as they are", same)
    assert refine.final_note("", d)[0].startswith("Swapped Mapo Tofu")


def test_feedback_revises_the_current_order_with_a_checked_note(fake):
    f = fake(
        order(
            "garlic_seasonal_greens", "di_san_xian", note="Swapped 2 spicy dishes for milder ones"
        )
    )
    r = post({"chips": ["less_spicy"], "text": "my mom can't do heat", "current": CURRENT})
    # QA r11: a less-spicy note is always the code's, in the cards' words.
    assert r["kind"] == "plan" and r["change_note"].startswith(
        "Swapped Mapo Tofu (very spicy), Kung Pao Chicken (spicy) for Garlic Seasonal Greens "
        "(not spicy)"
    )
    assert "Removed Mapo Tofu" in " ".join(r["changes"]) and any(
        c.startswith("Added") for c in r["changes"]
    )
    turns, schema = f.calls[0]
    text = turns[0].text
    assert (
        "current_order" in text and "less spicy" in text.lower() and "my mom can't do heat" in text
    )
    assert text.startswith(refine.REVISE) and "change_note" in schema["properties"]


def test_a_note_that_does_not_match_is_rewritten_by_the_code(fake):
    fake(
        order(
            "mapo_tofu",
            "kung_pao_chicken",
            "boiled_fish_chili_oil",
            note="Made it cheaper and milder",
        )
    )
    r = post({"text": "something fancier", "current": CURRENT})
    assert r["kind"] == "plan" and "cheaper" not in r["change_note"].lower()
    assert r["change_note"].startswith("Added Boiled Fish")


def test_feedback_bypasses_the_cache_and_is_part_of_its_key(fake):
    f = fake(order("mapo_tofu", "kung_pao_chicken"))
    post()
    post()
    assert len(f.calls) == 1  # a plain refresh is cached
    post({"text": "more veg please", "current": CURRENT})
    post({"text": "more veg please", "current": CURRENT})
    assert len(f.calls) == 2  # 2026-10-10: the same refinement again is cached too
    a = llm_planner._key({"x": 1, "feedback": ["a"]}, "m")
    assert a != llm_planner._key({"x": 1, "feedback": ["b"]}, "m")


def test_kept_dishes_stay_and_failures_retry_then_the_rules_build(fake):
    f = fake(
        order("garlic_seasonal_greens", note="Dropped kung pao"),
        order("garlic_seasonal_greens", "kung_pao_chicken", note="Added garlic greens"),
    )
    r = post({"chips": ["more_veggies"], "current": CURRENT}, locked=["kung_pao_chicken"])
    assert len(f.calls) == 2 and "kung_pao_chicken" in [i["dish_id"] for i in r["plan"]["items"]]
    fake(order("not_a_dish", note="Swapped everything"))
    r = post({"chips": ["something_different"], "current": CURRENT})
    assert r["source"] == "rules" and r["kind"] == "plan"
    assert "everything" not in r["change_note"]  # the rules' order: the code writes the note


def test_each_chip_goal_is_checked_on_the_real_orders():
    cur = [("mapo_tofu", 1), ("kung_pao_chicken", 1), ("steamed_rice", 2)]

    def miss(chips, after, locked=()):
        return refine.unmet(chips, MENU, cur, after, locked)

    only_added = [*cur, ("garlic_seasonal_greens", 1)]
    assert miss(["less_spicy"], only_added) == ["less_spicy"]  # a mild dish added is not enough
    swapped = [("garlic_seasonal_greens", 1), ("kung_pao_chicken", 1), ("steamed_rice", 2)]
    assert miss(["less_spicy", "cheaper", "more_veggies"], swapped) == []
    assert miss(["less_spicy"], swapped, locked=["mapo_tofu"]) == ["less_spicy"]  # kept stays
    assert miss(["more_seafood"], [*cur, ("boiled_fish_chili_oil", 1)]) == []
    assert miss(["more_seafood", "cheaper"], swapped) == ["more_seafood"]
    assert miss(["more_filling"], only_added) == [] and miss(["more_filling"], cur) == [
        "more_filling"
    ]
    assert miss(["something_different"], swapped) == []  # 1 of 2 changed: half
    assert miss(["something_different"], only_added) == ["something_different"]


def test_note_may_only_name_dishes_that_really_changed():
    d = refine.diff(
        MENU,
        [("mapo_tofu", 1), ("kung_pao_chicken", 1)],
        [("mapo_tofu", 1), ("kung_pao_chicken", 1), ("garlic_seasonal_greens", 1)],
    )
    assert refine.note_ok("Added Garlic Seasonal Greens", d)
    assert not refine.note_ok("Added garlic seasonal greens, kept mapo tofu", d)
    assert not refine.note_ok("Replaced the spicy mapo tofu with garlic seasonal greens", d)


def test_less_spicy_that_only_adds_a_dish_is_retried_with_the_reason(fake):
    f = fake(
        order(
            "mapo_tofu",
            "kung_pao_chicken",
            "garlic_seasonal_greens",
            note="Added Garlic Seasonal Greens",
        ),
        order(
            "garlic_seasonal_greens",
            "kung_pao_chicken",
            note="Swapped Mapo Tofu for Garlic Seasonal Greens",
        ),
    )
    r = post({"chips": ["less_spicy"], "current": CURRENT})
    assert len(f.calls) == 2
    assert "Your last revision did not do this: make it less spicy" in f.calls[1][0][0].text
    assert (
        r["change_note"]
        == "Swapped Mapo Tofu (very spicy) for Garlic Seasonal Greens (not spicy); $2.00 less in menu prices."
    )
    assert "Removed Mapo Tofu" in r["changes"]


def test_still_not_less_spicy_after_the_retry_says_so_honestly(fake):
    f = fake(
        order("mapo_tofu", "kung_pao_chicken", "garlic_seasonal_greens", note="Made it milder")
    )
    r = post({"chips": ["less_spicy"], "current": CURRENT})
    assert len(f.calls) == 2 and r["kind"] == "plan"
    # QA r11: the AI's order is discarded; the current order stays, said honestly.
    assert r["change_note"].startswith("Couldn't make it less spicy within")
    ids = sorted(i["dish_id"] for i in r["plan"]["items"])
    assert "garlic_seasonal_greens" not in ids


def test_unchanged_order_says_plainly_that_nothing_changed(fake):
    fake(order("mapo_tofu", "kung_pao_chicken", note="Kept all dishes as they are"))
    r = post({"chips": ["less_spicy"], "current": CURRENT})
    assert r["change_note"].startswith("Couldn't make it less spicy") and r["change_note"].endswith(
        "Its spiciest dish is very spicy."
    )


def test_less_spicy_on_an_already_mild_order_needs_no_ai_call(fake):
    f = fake(order("mapo_tofu"))
    mild = [
        {"dish_id": "garlic_seasonal_greens", "quantity": 1},
        {"dish_id": "hot_and_sour_soup", "quantity": 1},
        {"dish_id": "steamed_rice", "quantity": 2},
    ]
    r = post({"chips": ["less_spicy"], "current": mild})
    assert f.calls == [] and r["kind"] == "plan"
    assert r["change_note"] == refine.ALREADY_MILD and r["changes"] == []
    assert sorted(i["dish_id"] for i in r["plan"]["items"]) == sorted(i["dish_id"] for i in mild)
    assert (
        refine.unmet(["less_spicy"], MENU, [("hot_and_sour_soup", 1)], [("hot_and_sour_soup", 1)])
        == []
    )
    hot_but_kept = [("mapo_tofu", 1), ("hot_and_sour_soup", 1)]
    assert refine.already_mild(MENU, hot_but_kept, locked=["mapo_tofu"])
    assert not refine.already_mild(MENU, hot_but_kept)
