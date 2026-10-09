"""Server questions are written by the model in the planning call; the rules make sure
every flagged risk is still asked about, one line per dish."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from michelin.plan import llm_planner
from michelin.schemas import DinerProfile, Menu, TableRequest

ROOT = Path(__file__).resolve().parents[1]
MENU = Menu.model_validate_json((ROOT / "tests/data/sky_pavilion.json").read_text())
DINERS = [
    DinerProfile(id="alice", name="Alice", allergies=["peanut"]),
    DinerProfile(id="ben", name="Ben", diets=["vegetarian"]),
    DinerProfile(id="cai", name="Cai", allergies=["shellfish"], diets=["no_pork"]),
]
REQUEST = TableRequest(menu_id="sky", diners=DINERS, budget_per_person=25, dish_count_target=4)
ORDER = ["scallion_pancake", "eggplant_with_garlic_sauce", "fish_fillet_in_hot_chili_oil"]
pytestmark = pytest.mark.real_llm_path


@pytest.fixture(autouse=True)
def gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    llm_planner._memory.clear()
    yield
    llm_planner._memory.clear()


def answer(questions: dict[str, str]) -> dict:
    return {
        "dishes": [
            {
                "dish_id": i,
                "reason": "Good for the table.",
                "for": ["alice", "cai"] if i.startswith("fish") else ["alice", "ben", "cai"],
                "server_question": questions.get(i, ""),
            }
            for i in ORDER
        ],
        "server_questions": [],
        "summary": "Plates everyone can share, with fish for Alice and Cai.",
    }


def plan_with(body, tmp_path):
    calls = []

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=json.dumps(body))

    out = llm_planner.plan(
        MENU, REQUEST, client=SimpleNamespace(models=Models()), cache_path=tmp_path / "c.json"
    )
    return out, calls


def test_brief_gives_the_model_the_rule_flagged_risks():
    payload = llm_planner.brief(MENU, REQUEST)
    rows = {d["id"]: d for d in payload["dishes"]}
    assert any(
        r.endswith("pork (matters for Ben, Cai)")
        for r in rows["eggplant_with_garlic_sauce"]["risks"]
    )
    assert rows["scallion_pancake"]["risks"] == ["lard (matters for Ben, Cai)"]
    assert all("ask" not in r for r in rows.values())


def test_model_questions_replace_the_templates_one_per_dish(tmp_path):
    good = {
        "eggplant_with_garlic_sauce": "Ben is vegetarian and Cai avoids pork: is the garlic "
        "sauce made with minced pork?",
        "scallion_pancake": "Ben is vegetarian and Cai avoids pork: are these fried in lard?",
    }
    out, calls = plan_with(answer(good), tmp_path)
    assert out.plan is not None and len(calls) == 1  # no extra model call
    asked = out.plan.confirm_with_staff
    assert asked == [
        "Scallion Pancake: " + good["scallion_pancake"],  # the model forgot the dish name
        good["eggplant_with_garlic_sauce"],  # names "garlic sauce": no prefix needed
    ]
    by_id = {i.dish_id: i.server_question for i in out.plan.items}
    assert by_id["eggplant_with_garlic_sauce"] == asked[1]
    assert by_id["fish_fillet_in_hot_chili_oil"] is None
    assert out.plan.summary.startswith("Plates everyone can share")


def test_a_missed_risk_gets_the_rule_question_appended(tmp_path):
    # Names Ben but not Cai, so the no-pork risk for Cai is not covered.
    partial = {"eggplant_with_garlic_sauce": "Ben is vegetarian: does it have minced pork?"}
    out, _ = plan_with(answer(partial), tmp_path)
    by_id = {i.dish_id: i.server_question for i in out.plan.items}
    egg = by_id["eggplant_with_garlic_sauce"]
    assert egg == (
        "Eggplant with Garlic Sauce: Ben is vegetarian: does it have minced pork? "
        "Also, is there any minced pork in it (for Ben and Cai)?"
    )
    # No question at all from the model: the rules' own plain question.
    assert (
        by_id["scallion_pancake"] == "Is there any lard in the Scallion Pancake (for Ben and Cai)?"
    )


def test_rule_questions_skip_what_nobody_at_the_table_avoids():
    """Before: "Sautéed Bok Choy: ...; ask whether it uses soy; ask whether it uses wheat."
    even though nobody at the table avoids soy or wheat."""
    from michelin.plan.edibility import ask_server, risks

    pancake = MENU.dish("scallion_pancake")
    alice_only = [DINERS[0]]  # peanut allergy only: lard does not matter to her
    assert [r.about for r in risks(pancake, alice_only)] == []
    flagged = risks(pancake, DINERS)
    assert ask_server(pancake, flagged) == (
        "Is there any lard in the Scallion Pancake (for Ben and Cai)?"
    )


def test_model_questions_are_cleaned_to_one_plain_line():
    from michelin.plan.llm_planner import _plain

    assert _plain("Scallion Pancake: is it fried in lard; any pork", "Scallion Pancake") == (
        "Scallion Pancake: Is it fried in lard, any pork?"
    )
    assert _plain("  Is there lard in the  scallion pancake?\n", "Scallion Pancake") == (
        "Is there lard in the scallion pancake?"
    )
    assert _plain("", "Scallion Pancake") == ""


def test_summary_never_contradicts_the_dish_count():
    """Atlas Kitchen regression: the header said 8, another line 7, the summary 'six dishes'."""
    from michelin.plan.llm_planner import _summary

    assert _summary("Seven dishes, one per person plus rice.", 7) == (
        "Seven dishes, one per person plus rice."
    )
    assert _summary("A good variety of six dishes so everyone has options.", 7) is None
    assert _summary("Three main dishes plus rice for sharing.", 4) is None
    assert _summary("One dish per person plus rice, so 2 people share.", 4) == (
        "One dish per person plus rice, so 2 people share."
    )
    assert _summary("", 3) is None


def test_a_question_that_invents_an_allergy_falls_back_to_the_rules():
    """Live Atlas run: "Kevin has a peanut allergy" for a diner with none recorded."""
    from michelin.plan.llm_planner import _misstates

    diners = [
        DinerProfile(id="k", name="Kevin", max_spice=0),
        DinerProfile(id="d", name="David", diets=["vegetarian"]),
        DinerProfile(id="a", name="Amy", allergies=["shellfish", "fish"]),
    ]
    assert _misstates("Any peanuts? Kevin has a peanut allergy.", diners)
    assert _misstates("David is allergic to sesame.", diners)
    assert _misstates("Kevin is vegetarian: any pork?", diners)
    assert not _misstates(
        "Amy has a shellfish allergy and David is vegetarian: oyster sauce?", diners
    )
    assert not _misstates("Amy is allergic to fish; any fish sauce?", diners)


# QA round 3, Q-2 repros (Sky Pavilion; Alice peanut, Ben vegetarian, Cai shellfish + no pork).
def _asked(dish_id: str, question: str) -> str | None:
    selected = [(MENU.dish(dish_id), 1)]
    body = {"dishes": [{"dish_id": dish_id, "server_question": question}]}
    return llm_planner.server_questions(body, selected, REQUEST).get(dish_id)


def test_q2_no_allergy_the_dish_does_not_involve():
    # Hot and Sour Soup is flagged egg/soy/wheat; nobody here avoids those, and only Alice
    # can eat it. A peanut question is dropped and nothing replaces it.
    assert (
        _asked(
            "hot_and_sour_soup",
            "Does the hot and sour soup contain peanuts, because Alice has a peanut allergy?",
        )
        is None
    )


def test_q2_no_question_for_someone_the_dish_is_not_for():
    # Mapo Tofu is "Not for Ben" (pork), so asking about beef for Ben is moot.
    assert _asked("mapo_tofu", "Is there any beef in the Mapo Tofu, as Ben is vegetarian?") is None
    from michelin.plan.edibility import risks

    assert risks(MENU.dish("mapo_tofu"), DINERS) == []
    assert risks(MENU.dish("dry_fried_green_beans"), DINERS) == []  # not for Ben or Cai


def test_q2_raw_labels_are_humanised():
    q = _asked(
        "scallion_pancake",
        "Is there any lard in the scallion pancake, for Ben (vegetarian) and Cai (no_pork)?",
    )
    assert q == "Is there any lard in the scallion pancake, for Ben (vegetarian) and Cai (no pork)?"
    # Rule fallbacks and the brief never carry raw ids either.
    assert "_" not in _asked("eggplant_with_garlic_sauce", "")
    brief = json.dumps(llm_planner.brief(MENU, REQUEST))
    assert "no_pork" not in brief


def test_q2_a_true_question_still_passes():
    q = "Is there any minced pork in the eggplant, since Ben is vegetarian and Cai avoids pork?"
    assert _asked("eggplant_with_garlic_sauce", q) == q


def test_q2_swap_path_drops_the_same_questions(tmp_path, monkeypatch):
    from michelin.plan import ai_swap

    out, _ = plan_with(answer({}), tmp_path)
    plan = out.plan
    fake_answer = {
        "dish_id": "hot_and_sour_soup",
        "reason": "Alice can eat it",
        "server_question": "Does the hot and sour soup contain peanuts, because Alice has a "
        "peanut allergy?",
    }
    monkeypatch.setattr(ai_swap, "_ask", lambda *a: (json.dumps(fake_answer), "m"))
    request = REQUEST.model_copy(update={"budget_per_person": 40})
    swapped = ai_swap.swap(MENU, request, plan, "fish_fillet_in_hot_chili_oil")
    assert swapped.plan is not None
    soup = next(i for i in swapped.plan.items if i.dish_id == "hot_and_sour_soup")
    assert soup.server_question is None
    assert not any("peanut" in q for q in swapped.plan.confirm_with_staff)
