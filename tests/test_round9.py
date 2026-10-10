"""Regression tests for QA round 9 (73feccc)."""

import base64
import json
from pathlib import Path

from michelin.plan import dish_facts, llm_planner, refine
from michelin.schemas import CustomFlag, DinerProfile, Dish, Menu, TableRequest

FIX = Path(__file__).parent / "fixtures"


def test_q2_yu_xiang_tofu_gets_one_short_question():
    data = json.loads((FIX / "qa_r9_yu_xiang_tofu.json").read_text())
    dish = Dish.model_validate(data["dish"])
    # As the server annotates it for Mia (live r9: halal and cilantro both "possible").
    dish = dish.model_copy(
        update={
            "custom_flags": [
                CustomFlag(term="cilantro", kind="allergy", answer="possible"),
                CustomFlag(term="halal", kind="diet", answer="possible"),
            ]
        }
    )
    diners = [DinerProfile.model_validate(p) for p in data["diners"]]
    Menu(
        restaurant_id="t",
        restaurant_name="T",
        cuisine="x",
        source="t",
        verified=True,
        dishes=[dish],
    )
    request = TableRequest(menu_id="t", diners=diners, budget_per_person=40)
    # The AI's own (r9) question is ignored; the code writes one.
    answer = {"dishes": [{"dish_id": dish.id, "server_question": data["r9_question"]}]}
    q = llm_planner.server_questions(answer, [(dish, 1)], request)[dish.id]
    low = q.lower()
    assert low.count("pork") <= 1 and "since" not in low and "avoids" not in low
    assert "also," not in low and q.count("?") == 1
    assert "halal" in low and "halal in" not in low and "or halal" not in low
    assert q.startswith("Is there any ") and "Yu Xiang (Tofu)" in q


def test_curly_and_straight_quotes_share_a_cache_key():
    a = Dish(id="g", name_en="General Tso’s (Tofu)", price=15, description_raw="“crispy” – sweet")
    b = Dish(id="g", name_en="General Tso's (Tofu)", price=15, description_raw='"crispy" - sweet')
    assert dish_facts._key(a) == dish_facts._key(b)


def test_change_notes_use_the_card_spice_words():
    menu = Menu(
        restaurant_id="t",
        restaurant_name="T",
        cuisine="x",
        source="t",
        verified=True,
        dishes=[
            Dish(id="a", name_en="Yu Xiang (Tofu)", price=17, spice_level=2),
            Dish(id="b", name_en="Yu Xiang Eggplant", price=16, spice_level=1),
        ],
    )
    d = refine.diff(menu, [("a", 1)], [("b", 1)])
    note, _ = refine.final_note("Replaced the spicy tofu with a mild eggplant dish.", d)
    assert "mild" not in note and "a little spicy" in note


def test_same_upload_is_read_once(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from michelin import api
    from michelin.parse import vision

    calls = []

    def ask(pages, client=None):
        calls.append(1)
        return {"dishes": [{"name_en": "Mapo Tofu", "price": 15}], "restaurant_name": "X"}, "m"

    monkeypatch.setattr(vision, "_ask", ask)
    monkeypatch.setattr(vision, "configured", lambda: True)
    img = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    body = {"image_base64": base64.b64encode(img).decode()}
    c = TestClient(api.app)
    assert c.post("/api/menu/parse", json=body).status_code == 200
    assert c.post("/api/menu/parse", json=body).status_code == 200
    assert len(calls) == 1
    other = {"image_base64": base64.b64encode(img + b"1").decode()}
    assert c.post("/api/menu/parse", json=other).status_code == 200
    assert len(calls) == 2
    # A prompt change is a different key.
    k = vision.read_key([img])
    monkeypatch.setattr(vision, "READ_VERSION", vision.READ_VERSION + "x")
    assert vision.read_key([img]) != k


def test_a_diner_with_nothing_to_eat_gets_a_plain_reason_without_ai():
    from michelin.schemas import AllergenFlag, EvidenceTier

    soy = [
        AllergenFlag(
            allergen="wheat",
            tier=EvidenceTier.INFERRED,
            confidence=0.8,
            reason="usually contain wheat (soy sauce)",
        ),
    ]
    dishes = [Dish(id=f"d{i}", name_en=f"Dish {i}", price=12, allergens=soy) for i in range(3)]
    menu = Menu(
        restaurant_id="t",
        restaurant_name="T",
        cuisine="x",
        source="t",
        verified=True,
        dishes=dishes,
    )
    wes = DinerProfile(id="w", name="Wes", allergies=["wheat"])
    request = TableRequest(
        menu_id="t", diners=[DinerProfile(id="a", name="Ana"), wes], budget_per_person=40
    )
    out = llm_planner._plan(menu, request)  # no model configured in tests: still answered
    assert out.plan is None and out.attempts == 0
    msg = out.conflict.message
    assert "Wes" in msg and "soy sauce" in msg and "wheat" in msg


def test_committed_cafe_mandarin_read_is_complete_and_has_facts(monkeypatch):
    """The demo menu: one good read, committed, with its v7 facts (no AI on import)."""
    from michelin.parse import vision

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(vision, "READ_CACHE", root / "data/menu_reads")
    monkeypatch.setattr(dish_facts, "CACHE_PATH", root / "data/facts/dish_facts.json")
    key = vision.read_key([(root / "test-menus/cafe-mandarin.pdf").read_bytes()])
    hit = vision.cached_read(key)
    assert hit is not None
    dishes = vision.rows_to_dishes(hit["rows"])
    assert len(dishes) == 100
    fluke = [d.variant for d in dishes if (d.family_name or "").startswith("Fluke")]
    assert len(fluke) == 4 and "Sweet & Sour" in fluke
    assert {d.name_en for d in dishes if d.name_en.startswith("Cucumber Salad")} == {
        "Cucumber Salad (Garlic)",
        "Cucumber Salad (Spicy Chili Oil)",
    }
    for name in ("Yu Xiang (Pork)", "Kung Pao Chicken (Spicy)", "Broccoli (Chicken)"):
        d = next(x for x in dishes if x.name_en == name)
        assert "vegetarian_possible" in [m.value for m in d.menu_marks]
    menu = Menu(
        restaurant_id="cm",
        restaurant_name="Cafe Mandarin",
        cuisine="x",
        source="t",
        verified=True,
        dishes=dishes,
    )
    assert dish_facts.coverage(menu) == (100, 100)
