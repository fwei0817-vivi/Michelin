"""QA round 15: one per-diner status for card, hint and reason; the AI never writes names."""

import json
import re
from pathlib import Path

import pytest
from test_round11 import client, demo  # noqa: F401 - fixture

from michelin.plan import ai_swap, ai_text
from michelin.schemas import Menu, TableRequest

pytestmark = [pytest.mark.real_llm_path, pytest.mark.real_dish_facts]
WEB = Path(__file__).resolve().parents[1] / "web/src"
ORDER = ["cucumber_salad_garlic", "tomato_egg", "broccoli_tofu", "pumpkin_cake_3"]


USED = {*ORDER, "eight_treasure_sticky_rice"}


@pytest.fixture
def mia_facts(monkeypatch):
    """Mia's custom-word answers as the app's facts step gives them (QA r15 evaluate: all 4
    validated for Tomato & Egg): halal and cilantro "no" for the dishes used here."""
    from michelin import llm
    from michelin.plan import custom_facts

    def fake(dishes, allergies, diets, client=None):
        rows = [
            {
                "id": d.id,
                "allergens": [
                    {"item": t, "answer": "no" if d.id in USED else "unknown"} for t in allergies
                ],
                "diets": [
                    {"item": t, "answer": "no" if d.id in USED else "unknown"} for t in diets
                ],
            }
            for d in dishes
        ]
        return json.dumps({"dishes": rows}), "fake"

    monkeypatch.setattr(custom_facts, "_ask", fake)
    monkeypatch.setattr(llm, "provider", lambda *a, **k: "fake")


def _setup(demo):  # noqa: F811
    menu, diners = demo
    return client.post("/api/menu/facts", json=menu).json(), diners


def _body(menu, diners, **kw):
    return {
        "menu_id": "local-1",
        "menu_override": menu,
        "diners": diners,
        "budget_per_person": 40,
        "tax_rate": 0.08875,
        "tip_rate": 0.18,
        **kw,
    }


def _plan(menu, diners):
    req = TableRequest(menu_id="local-1", diners=diners, budget_per_person=40)
    r = client.post(
        "/api/order/validate",
        json={
            "menu": menu,
            "request": req.model_dump(mode="json"),
            "items": [{"dish_id": i, "quantity": 1} for i in ORDER],
        },
    ).json()
    assert r.get("valid", True), r
    sheet = client.post("/api/menu/evaluate", json={"menu": menu, "diners": diners}).json()
    items = [{"dish_id": i, "quantity": 1, "edible_by": sheet[i]["edible_by"]} for i in ORDER]
    return {"items": items, **r["totals"], "variety_score": 0.5, "summary": None}


def _agree(menu, diners, item, message=None):
    """Card status, hint and reason say the same about confirming."""
    sheet = client.post("/api/menu/evaluate", json={"menu": menu, "diners": diners}).json()
    expect = sheet[item["dish_id"]]["status"]  # what the menu-sheet card renders
    assert item["status"] == expect  # the plan card reads the very same status
    confirm = any(v["status"] == "needs_confirm" for v in expect.values())
    for text in filter(None, [item.get("reason"), message]):
        assert ("server confirms" in text or "Ask the server" in text) == confirm, text


def test_r15_repro_tomato_egg_out_and_back_all_surfaces_agree(demo, mia_facts):  # noqa: F811
    menu, diners = _setup(demo)
    plan = _plan(menu, diners)
    one = client.post(
        "/api/plan/swap",
        json=_body(
            menu, diners, plan=plan, dish_id="tomato_egg", new_dish_id="eight_treasure_sticky_rice"
        ),
    ).json()
    assert one["kind"] == "plan", one
    new = next(i for i in one["plan"]["items"] if i["dish_id"] == "eight_treasure_sticky_rice")
    _agree(menu, diners, new, one["message"])
    back = client.post(
        "/api/plan/swap",
        json=_body(
            menu,
            diners,
            plan=one["plan"],
            dish_id="eight_treasure_sticky_rice",
            new_dish_id="tomato_egg",
        ),
    ).json()
    assert back["kind"] == "plan", back
    egg = next(i for i in back["plan"]["items"] if i["dish_id"] == "tomato_egg")
    _agree(menu, diners, egg, back["message"])
    # Decision: with halal "no" and cilantro "no", Tomato & Egg needs no check for Mia.
    assert egg["status"]["mia"] == {"status": "ok", "reason": None, "taste": None}
    assert "everyone can eat it," in back["message"]
    # the menu sheet reads the very same status
    sheet = client.post("/api/menu/evaluate", json={"menu": menu, "diners": diners}).json()
    assert sheet["tomato_egg"]["status"] == egg["status"]
    for i in back["plan"]["items"]:
        assert i["status"], i  # every plan item carries it


def test_web_marks_read_only_the_backend_status():
    """Build-time check: the cards decide 'only if the server confirms' from the backend
    status, and (QA r16) the veg tag from the backend's veg_tag; no hidden-meat keywords."""
    for name in ("components/Ticket.tsx", "components/SwapSheet.tsx"):
        src = (WEB / name).read_text()
        assert "mayHideMeat" not in src, name
        unsure = re.findall(r"const unsure = [^\n]*", src)
        assert unsure and all("needsConfirm" in u for u in unsure), (name, unsure)
        assert "veg_tag" in src and "vegChip" not in src
    lib = (WEB / "lib/dietary.ts").read_text()
    assert "mayHideMeat" not in lib and "ANIMAL" not in lib


def _req(diners):
    return TableRequest(menu_id="local-1", diners=diners, budget_per_person=40)


def test_ai_never_writes_names(demo):  # noqa: F811
    _, diners = demo
    req = _req(diners)
    assert ai_text.detoken("{alice} and {ben} can eat it", req.diners) == "Alice and Ben can eat it"
    for raw in ("alice ben cai mia can eat it", "Alice can eat it", "for MIA", "{zed} likes it"):
        assert ai_text.detoken(raw, req.diners) is None, raw


def test_r15_repro_pumpkin_cake_ai_swap_with_raw_ids(demo, monkeypatch, mia_facts):  # noqa: F811
    menu, diners = _setup(demo)
    plan = _plan(menu, diners)
    answer = {"dish_id": "eight_treasure_sticky_rice", "reason": "alice ben cai mia can eat it"}
    monkeypatch.setattr(ai_swap, "_ask", lambda t, s, c: (json.dumps(answer), "fake"))
    r = client.post(
        "/api/plan/swap", json=_body(menu, diners, plan=plan, dish_id="pumpkin_cake_3")
    ).json()
    assert r["kind"] == "plan", r
    assert "alice ben" not in r["message"].lower()
    assert re.search(r"Eight Treasure Sticky Rice, (everyone|[A-Z]\w+)", r["message"])


def test_new_overclaims(demo, mia_facts):  # noqa: F811
    menu, diners = _setup(demo)
    m, req = Menu.model_validate(menu), _req(diners)
    from michelin.schemas import PlanItem

    items = [PlanItem(dish_id=i, quantity=1) for i in ORDER]
    for text in (
        "Covers all dietary needs.",
        "Respects everyone's dietary restrictions.",
        "Fits all dietary restrictions at the table.",
        "A spread suitable for everyone.",
    ):
        assert ai_text.summary(text, m, req, items) is None, text
