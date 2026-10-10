"""QA round 17: the code subtitle counts only dishes a diner can eat without asking
(diner_status "ok"), names anyone whose dishes all need the server; a just-swapped dish
shows a reason, not the swap notice; vegetarians see "Ask if vegetarian", not vegan."""

import json
import re

import pytest
from test_round11 import client, demo  # noqa: F401 - fixture
from test_round15 import ORDER, _body, _plan, _setup

from michelin.plan import ai_swap, ai_text
from michelin.plan.edibility import diner_status, veg_tag
from michelin.schemas import Menu, PlanItem, TableRequest

pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]
BEEF = "sichuan_boiled_beef_in_chili_oil_sliced_beef"


@pytest.fixture
def halal_possible(monkeypatch):
    """Mia's halal is 'possible' everywhere -> every dish needs the server for her."""
    from michelin import llm
    from michelin.plan import custom_facts

    def fake(dishes, allergies, diets, client=None):
        rows = [
            {
                "id": d.id,
                "allergens": [{"item": t, "answer": "no"} for t in allergies],
                "diets": [{"item": t, "answer": "possible"} for t in diets],
            }
            for d in dishes
        ]
        return json.dumps({"dishes": rows}), "fake"

    monkeypatch.setattr(custom_facts, "_ask", fake)
    monkeypatch.setattr(llm, "provider", lambda *a, **k: "fake")


def check_subtitle(text, menu, req, ids):
    """Every number and claim in the subtitle matches the backend's per-diner status."""
    shared = [menu.dish(i) for i in ids if menu.dish(i).category.value != "staple"]
    st = [diner_status(d, req.diners) for d in shared]
    ok = {p.id: sum(s[p.id]["status"] == "ok" for s in st) for p in req.diners}
    names = {p.id: p.name or p.id for p in req.diners}
    assert text.startswith(f"{len(shared)} dish"), text
    stuck = {p for p, n in ok.items() if n == 0}
    m = re.search(r"everyone has at least (\d+|one) dish", text)
    if m:
        n = 1 if m.group(1) == "one" else int(m.group(1))
        assert not stuck and min(ok.values()) == n, (text, ok)
    m = re.search(r"everyone else has at least (\d+|one) dish", text)
    if m:
        n = 1 if m.group(1) == "one" else int(m.group(1))
        assert min(v for k, v in ok.items() if k not in stuck) == n, (text, ok)
    for p in stuck:  # named honestly
        assert names[p] in text, (text, ok)
    if stuck:
        assert "everyone has" not in text, (text, ok)
    return ok


def _req_menu(menu_json, diners):
    from michelin.plan import dish_facts

    req = TableRequest(menu_id="local-1", diners=diners, budget_per_person=40)
    return dish_facts.prepare(Menu.model_validate(menu_json), diners=req.diners), req


def test_40_plan_names_mia_halal(demo, halal_possible):  # noqa: F811
    menu_json, diners = _setup(demo)
    menu, req = _req_menu(menu_json, diners)
    items = [PlanItem(dish_id=i, quantity=1) for i in ORDER]
    s = ai_text.code_summary(menu, req, items)
    ok = check_subtitle(s, menu, req, ORDER)
    assert ok["mia"] == 0
    assert "Mia's dishes need a quick check with the server (halal)" in s, s
    assert "everyone has at least" not in s


def test_30_replan_with_beef_matches_ben(demo, halal_possible):  # noqa: F811
    menu_json, diners = _setup(demo)
    menu, req = _req_menu(menu_json, diners)
    ids = [BEEF, "cucumber_salad_garlic"]
    s = ai_text.code_summary(menu, req, [PlanItem(dish_id=i, quantity=1) for i in ids])
    check_subtitle(s, menu, req, ids)
    ids = [BEEF, *ORDER]
    s = ai_text.code_summary(menu, req, [PlanItem(dish_id=i, quantity=1) for i in ids])
    check_subtitle(s, menu, req, ids)


def test_plain_case_still_counts_ok_dishes(demo):  # noqa: F811
    menu_json, diners = demo
    menu, req = _req_menu(menu_json, [d for d in diners if d["id"] != "mia"])
    s = ai_text.code_summary(menu, req, [PlanItem(dish_id=i, quantity=1) for i in ORDER])
    check_subtitle(s, menu, req, ORDER)


def test_api_plan_subtitle_matches_status(demo, halal_possible, monkeypatch):  # noqa: F811
    menu, diners = _setup(demo)
    swap = {"dish_id": "eight_treasure_sticky_rice", "reason": "x"}
    monkeypatch.setattr(ai_swap, "_ask", lambda t, s, c: (json.dumps(swap), "fake"))
    plan = _plan(menu, diners)
    r = client.post(
        "/api/plan/swap", json=_body(menu, diners, plan=plan, dish_id="pumpkin_cake_3")
    ).json()
    assert "kind" in r, r
    if r["kind"] != "plan":
        pytest.skip(r.get("message"))
    m, req = _req_menu(menu, diners)
    ids = [i["dish_id"] for i in r["plan"]["items"]]
    check_subtitle(r["plan"]["summary"], m, req, ids)
    new = next(i for i in r["plan"]["items"] if i["dish_id"] == r["new_dish_id"])
    assert not new["reason"].startswith(("Swapped to", "Added")), new["reason"]
    assert "cheaper" not in new["reason"] and "more expensive" not in new["reason"]


def test_veg_tag_vegetarian_unless_vegan_diner(demo):  # noqa: F811
    menu_json, diners = demo
    menu = Menu.model_validate(client.post("/api/menu/facts", json=menu_json).json())
    from michelin.schemas import DinerProfile

    veg = [DinerProfile(id="ben", name="Ben", diets=["vegetarian"])]
    vegan = [DinerProfile(id="v", name="V", diets=["vegan"])]
    vegan_dishes = [d for d in menu.dishes if d.is_vegan is True and veg_tag(d, vegan)]
    assert vegan_dishes
    for d in vegan_dishes:
        assert "vegan" not in (veg_tag(d, veg) or "")
        assert "vegan" in veg_tag(d, vegan)
        assert "vegan" not in (veg_tag(d, []) or "")
