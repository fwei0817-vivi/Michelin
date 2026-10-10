"""QA round 22 (2026-10-10): halal/kosher never looser than no pork (kosher also than a
shellfish allergy), vegetarian never looser than no pork/no beef, over every committed menu;
plainly vegetarian dishes are halal without asking; the top-up adds only hot dishes and
never claims "enough" when it is not; its note survives the plan cache."""

import json
from pathlib import Path

import pytest

from michelin.parse import vision
from michelin.plan import courses, dish_facts, edibility, enough, llm_planner
from michelin.schemas import CustomFlag, DinerProfile, Menu, PlanItem, TableRequest

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
pytestmark = [pytest.mark.real_dish_facts]
RANK = {"ok": 0, "needs_confirm": 1, "no": 2}


def _menus(monkeypatch):
    monkeypatch.setattr(dish_facts, "CACHE_PATH", ROOT / "data/facts/dish_facts.json")
    monkeypatch.setattr(courses, "CACHE_PATH", ROOT / "data/facts/dish_course.json")
    out = []
    for f in sorted((ROOT / "data/menu_reads").glob("*.json")):
        rows = json.loads(f.read_text()).get("rows") or []
        if rows:
            out.append(
                Menu(
                    restaurant_id=f.stem,
                    restaurant_name=f.stem,
                    cuisine="",
                    source="t",
                    dishes=vision.rows_to_dishes(rows),
                )
            )
    for f in sorted((ROOT / "data/menus").glob("*.json")):
        out.append(Menu.model_validate_json(f.read_text()))
    for f in ("qa_r10_wohop_menu.json", "qa_r22_wohop_menu.json"):
        out.append(Menu.model_validate(json.loads((FIX / f).read_text())))
    return [dish_facts.prepare(m) for m in out]


P = {
    "pork": DinerProfile(id="pork", name="P", diets=["no_pork"]),
    "beef": DinerProfile(id="beef", name="B", diets=["no_beef"]),
    "shell": DinerProfile(id="shell", name="S", allergies=["shellfish"]),
    "halal": DinerProfile(id="halal", name="H", other_diets=["halal"]),
    "kosher": DinerProfile(id="kosher", name="K", other_diets=["kosher"]),
    "veg": DinerProfile(id="veg", name="V", diets=["vegetarian"]),
}


@pytest.mark.parametrize("ai", ["no", "possible", None])
def test_property_diets_never_looser_than_what_they_imply(monkeypatch, ai):
    """Every dish of every committed menu; the AI's own halal/kosher answer at its loosest
    ('fits'), 'possible', or missing."""
    n = 0
    for m in _menus(monkeypatch):
        for d in m.dishes:
            if ai:
                d = d.model_copy(
                    update={
                        "custom_flags": [
                            CustomFlag(term=t, kind="diet", answer=ai) for t in ("halal", "kosher")
                        ]
                    }
                )
            st = {k: v["status"] for k, v in edibility.diner_status(d, list(P.values())).items()}
            for diet, floor in (
                ("halal", ["pork"]),
                ("kosher", ["pork"]),  # r23: kosher kept simple (veg / no pork)
                ("veg", ["pork", "beef"]),
            ):
                for f in floor:
                    assert RANK[st[diet]] >= RANK[st[f]], (m.restaurant_id, d.name_en, diet, f, st)
            n += 1
    assert n > 200


def test_tomato_egg_is_halal_without_asking(monkeypatch):
    cm = next(m for m in _menus(monkeypatch) if m.dish("tomato_egg"))
    d = cm.dish("tomato_egg").model_copy(
        update={"custom_flags": [CustomFlag(term="halal", kind="diet", answer="possible")]}
    )
    assert edibility.diner_status(d, [P["halal"]])["halal"]["status"] == "ok"


def test_spicy_strip_is_a_side():
    from michelin.schemas import Dish

    ds = [
        Dish(id=f"m{i}", name_en=f"Main {i}", price=30 + i, category="stir_fry", course="hot_main")
        for i in range(5)
    ]
    ds.append(
        Dish(
            id="s",
            name_en="Fragrant Spicy Strip",
            name_zh="香辣条",
            price=12,
            category="other",
            course="hot_main",
        )
    )
    assert {d.id: d.course for d in courses._snacks(ds)}["s"] == "side"


TABLE = [
    DinerProfile(id="li", name="Li", preferences=["no_spicy"]),
    DinerProfile(id="david", name="David", diets=["vegetarian"]),
    DinerProfile(id="amy", name="Amy", allergies=["shellfish", "fish"]),
    DinerProfile(id="kevin", name="Kevin", preferences=["no_spicy"]),
]
QA_ORDER = [
    "cold_sesame_noodles",
    "string_beans_w_garlic_sauce",
    "sesame_beef",
    "sliced_chicken_w_baby_corn",
]


def _wohop():
    m = Menu.model_validate(json.loads((FIX / "qa_r22_wohop_menu.json").read_text()))
    return m.model_copy(update={"dishes": courses._snacks(m.dishes)})


def test_wohop_26_top_up_adds_only_hot_dishes():
    m = _wohop()
    assert m.dish("crispy_noodles").course == "side"
    req = TableRequest(menu_id="w", diners=TABLE, budget_per_person=26)
    out = enough.top_up(m, req, [PlanItem(dish_id=i, quantity=1) for i in QA_ORDER])
    assert out and "crispy_noodles" not in out[1]
    assert all(enough.is_hot(m.dish(i)) for i in out[1])
    before = enough.tally([m.dish(i) for i in QA_ORDER], TABLE).hot
    assert enough.tally([m.dish(i.dish_id) for i in out[0]], TABLE).hot > before


@pytest.mark.enough
def test_note_never_claims_enough_when_short_and_survives_the_cache(monkeypatch, tmp_path):
    m = _wohop()
    req = TableRequest(menu_id="w", diners=TABLE, budget_per_person=26)
    answer = json.dumps(
        {
            "dishes": [
                {"dish_id": i, "reason": "", "for": [], "server_question": ""} for i in QA_ORDER
            ],
            "server_questions": [],
            "summary": "",
        }
    )
    calls = []

    def fake(turns, schema, menu, request, client):
        calls.append(1)
        return answer, "fake"

    monkeypatch.setattr(llm_planner, "_ask", fake)
    monkeypatch.setattr(llm_planner, "COVERAGE_NUDGE", False)
    monkeypatch.setattr(llm_planner, "enabled", lambda: True)
    out = llm_planner.plan(m, req, cache_path=tmp_path / "c.json")
    assert "The rules added" in out.note, out.note
    passed = next(c for c in out.plan.checks if c.name == "enough").passed
    assert ("so there is enough food" in out.note) == passed, out.note
    if not passed:
        assert "still short" in out.note
    llm_planner._memory.clear()
    n = len(calls)
    again = llm_planner.plan(m, req, cache_path=tmp_path / "c.json")
    assert len(calls) == n and again.cached
    assert out.note.split("checked by the rules", 1)[1].split(".", 1)[1].strip() in again.note
    assert "The rules added" in again.note


_MEATY = ("meat", "stock", "pork", "beef", "fish", "shellfish", "non-vegetarian")


@pytest.mark.parametrize("ai", ["no", None])
def test_property_halal_kosher_never_ok_when_vegetarian_is_blocked_for_meat(monkeypatch, ai):
    """QA r23: if vegetarian is blocked or asked for meat, stock or seafood reasons (not egg
    or dairy), halal and kosher are never 'ok'; and never looser than no pork."""
    n = 0
    for m in _menus(monkeypatch):
        for d in m.dishes:
            if ai:
                d = d.model_copy(
                    update={
                        "custom_flags": [
                            CustomFlag(term=t, kind="diet", answer=ai) for t in ("halal", "kosher")
                        ]
                    }
                )
            veg = edibility.assessment(d, P["veg"])
            meaty = any(w in r.lower() for r in veg["reasons"] for w in _MEATY)
            st = {k: v["status"] for k, v in edibility.diner_status(d, list(P.values())).items()}
            for diet in ("halal", "kosher"):
                # r23 rule: ok only if vegetarian is ok; never looser than no pork
                assert st[diet] != "ok" or st["veg"] == "ok", (m.restaurant_id, d.name_en, diet, st)
                assert RANK[st[diet]] >= RANK[st["pork"]], (m.restaurant_id, d.name_en, diet, st)
                if meaty and st["veg"] != "ok":
                    assert st[diet] != "ok", (m.restaurant_id, d.name_en, diet, veg["reasons"])
                    n += 1
    assert n > 50


def _atlas(monkeypatch):
    monkeypatch.setattr(dish_facts, "CACHE_PATH", ROOT / "data/facts/dish_facts.json")
    return dish_facts.prepare(
        Menu.model_validate_json((ROOT / "data/menus/atlas_kitchen.json").read_text())
    )


@pytest.mark.parametrize("name", ["Sautéed Bok Choy", "Egg Drop with Seaweed Soup"])
def test_atlas_bok_choy_and_egg_drop_ask_for_halal_mia(monkeypatch, name):
    m = _atlas(monkeypatch)
    d = next(x for x in m.dishes if (x.name_en or "").startswith(name))
    d = d.model_copy(update={"custom_flags": [CustomFlag(term="halal", kind="diet", answer="no")]})
    table = [
        DinerProfile(id="alice", name="Alice", allergies=["peanut"]),
        DinerProfile(id="cai", name="Cai", allergies=["shellfish"], diets=["no_pork"]),
        DinerProfile(id="mia", name="Mia", allergies=["sesame"], other_diets=["halal"]),
    ]
    assert edibility.diner_status(d, table)["mia"]["status"] != "ok"
    from michelin import explain

    r = explain.reason_for(d, 1, TableRequest(menu_id="a", diners=table, budget_per_person=20))
    assert "Mia" not in r.split(";")[0] or "server" in r, r
