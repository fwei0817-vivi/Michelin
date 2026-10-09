"""Diners' own allergies and diets ("mango", "halal") are hard rules; quick taste chips are
soft. The AI answers per dish and term (faked here); the code decides."""

import json

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.plan import custom_facts, dish_facts
from michelin.plan.edibility import assessment, open_questions
from michelin.schemas import CustomFlag, DinerProfile, Dish, Menu, Preference

client = TestClient(api.app)
MIA = DinerProfile(id="mia", name="Mia", other_allergies=["Mango", "cilantro"])
OMAR = DinerProfile(id="omar", name="Omar", other_diets=["halal", "No Alcohol"])


def dish(name, *flags):
    return Dish(id=name.lower().replace(" ", "_"), name_en=name, price=10, custom_flags=list(flags))


def flag(term, kind, answer, printed=False):
    return CustomFlag(term=term, kind=kind, answer=answer, printed=printed)


class FakeAsk:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, dishes, allergies, diets, client=None):
        self.calls.append(([d.name_en for d in dishes], allergies, diets))
        rows = []
        for d in dishes:
            got = self.answers.get(d.name_en, {})
            rows.append(
                {
                    "id": d.id,
                    "allergens": [
                        {"item": t, "answer": got[t], "why": "fake"} for t in allergies if t in got
                    ],
                    "diets": [
                        {"item": t, "answer": got[t], "why": "fake"} for t in diets if t in got
                    ],
                }
            )
        return json.dumps({"dishes": rows}), "fake"


@pytest.fixture
def fake_custom(monkeypatch):
    def install(answers):
        fake = FakeAsk(answers)
        monkeypatch.setattr(custom_facts, "_ask", fake)
        return fake

    return install


def test_terms_are_cleaned_and_old_saved_people_still_load():
    assert MIA.other_allergies == ["mango", "cilantro"] and OMAR.other_diets == [
        "halal",
        "no alcohol",
    ]
    old = DinerProfile.model_validate(
        {"id": "a", "name": "A", "allergies": ["peanut"], "max_spice": 0}
    )
    assert old.other_allergies == [] and old.preferences == [] and "no spicy" in old.notes.lower()


def test_allergy_likely_or_possible_excludes_unknown_asks_no_is_fine():
    assert not assessment(dish("Mango Pudding", flag("mango", "allergy", "likely")), MIA)[
        "eligible"
    ]
    possible = assessment(
        dish(
            "Fruit Salad", flag("mango", "allergy", "possible"), flag("cilantro", "allergy", "no")
        ),
        MIA,
    )
    assert not possible["eligible"] and "May contain mango" in possible["reasons"]
    unknown = dish("Rice", flag("mango", "allergy", "no"))  # cilantro never answered
    a = assessment(unknown, MIA)
    assert not a["eligible"] and a["status"] == "requires_confirmation"
    assert any("cilantro" in q for q in open_questions(unknown, [MIA]))
    ok = dish("Rice", flag("mango", "allergy", "no"), flag("cilantro", "allergy", "no"))
    assert assessment(ok, MIA)["eligible"]


def test_diet_likely_excludes_possible_asks_but_stays_eligible():
    pork = dish("Pork Bun", flag("halal", "diet", "likely"), flag("no alcohol", "diet", "no"))
    assert not assessment(pork, OMAR)["eligible"]
    greens = dish("Greens", flag("halal", "diet", "no"), flag("no alcohol", "diet", "possible"))
    a = assessment(greens, OMAR)
    assert a["eligible"] and a["status"] == "requires_confirmation"
    assert any("alcohol or cooking wine" in q for q in open_questions(greens, [OMAR]))
    assert not assessment(dish("Greens", flag("halal", "diet", "no")), OMAR)[
        "eligible"
    ]  # unanswered


@pytest.mark.real_dish_facts
def test_only_the_tables_terms_are_asked_once_and_cached(fake_custom):
    menu = Menu(
        restaurant_id="m",
        restaurant_name="M",
        cuisine="chinese",
        source="t",
        dishes=[dish("Mango Pudding"), dish("Steamed Rice"), dish("Beef with Shaoxing Wine")],
    )
    fake = fake_custom(
        {
            "Steamed Rice": {"mango": "no", "cilantro": "no", "halal": "no", "no alcohol": "no"},
            "Beef with Shaoxing Wine": {"mango": "no", "cilantro": "possible", "halal": "possible"},
        }
    )
    out = dish_facts.prepare(menu, client=object(), diners=[MIA, OMAR])
    _names, allergies, diets = fake.calls[0]
    assert allergies == ["cilantro", "mango"] and diets == ["halal", "no alcohol"]
    by = {d.name_en: {(f.kind, f.term): f for f in d.custom_flags} for d in out.dishes}
    assert by["Mango Pudding"][("allergy", "mango")].printed  # the menu's own word wins
    assert by["Beef with Shaoxing Wine"][("diet", "no alcohol")].answer == "likely"
    edible = {
        d.name_en: [p.id for p in (MIA, OMAR) if assessment(d, p)["eligible"]] for d in out.dishes
    }
    assert edible == {
        "Mango Pudding": [],
        "Steamed Rice": ["mia", "omar"],
        "Beef with Shaoxing Wine": [],
    }
    dish_facts.prepare(menu, client=object(), diners=[MIA, OMAR])
    assert len(fake.calls) == 2  # only Mango Pudding's never-answered terms asked again
    assert "Steamed Rice" not in fake.calls[1][0]
    plain = DinerProfile(id="p", name="P")
    dish_facts.prepare(menu, client=object(), diners=[plain])
    assert len(fake.calls) == 2  # nobody with an own term: no call


def test_without_a_model_every_dish_is_a_question_not_safe():
    out = custom_facts.annotate([dish("Steamed Rice")], [MIA])
    assert {f.answer for f in out[0].custom_flags} == {"unknown"}
    assert not assessment(out[0], MIA)["eligible"]


def test_evaluate_shows_the_reason_on_cards():
    menu = {
        "restaurant_id": "m",
        "restaurant_name": "M",
        "cuisine": "c",
        "source": "t",
        "verified": True,
        "dishes": [{"id": "mango_pudding", "name_en": "Mango Pudding", "price": 6}],
    }
    r = client.post(
        "/api/menu/evaluate", json={"menu": menu, "diners": [MIA.model_dump(mode="json")]}
    ).json()
    assert "Contains mango (on the menu)" in r["mango_pudding"]["blocked_for"]["mia"]


def test_saved_person_keeps_own_terms_and_taste_chips():
    body = {
        "id": "zoe",
        "name": "Zoe",
        "other_allergies": ["Kiwi"],
        "other_diets": ["kosher"],
        "preferences": ["no_spicy", "light", "no_offal"],
    }
    p = DinerProfile.model_validate(body)
    again = DinerProfile.model_validate_json(p.model_dump_json())
    assert again.other_allergies == ["kiwi"] and again.preferences == [
        Preference.NO_SPICY,
        Preference.LIGHT,
        Preference.NO_OFFAL,
    ]


def test_taste_chips_reach_the_planner_brief_and_never_exclude(sample_menu):
    from michelin.plan import llm_planner
    from michelin.schemas import TableRequest

    zoe = DinerProfile(
        id="zoe",
        name="Zoe",
        preferences=["no_spicy", "no_offal"],
        notes="loves tofu",
        other_allergies=["kiwi"],
    )
    req = TableRequest(menu_id=sample_menu.restaurant_id, diners=[zoe], budget_per_person=40)
    row = llm_planner.brief(sample_menu, req)["diners"][0]
    assert row["notes"].startswith("no spicy food; no offal") and row["notes"].endswith(
        "loves tofu"
    )
    assert row["other_allergies"] == ["kiwi"]
    hot = Dish(
        id="hot",
        name_en="Chili Tripe",
        price=10,
        spice_level=3,
        is_vegetarian=False,
        custom_flags=[flag("kiwi", "allergy", "no")],
    )
    assert assessment(hot, zoe)["eligible"]  # tastes are soft: the rules never exclude for them
    assert "avoid spice 2-3 unless nothing else fits" in llm_planner.SYSTEM
