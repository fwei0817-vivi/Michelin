from fastapi.testclient import TestClient

from michelin import api

client = TestClient(api.app)


def test_health():
    assert client.get("/api/health").json()["ok"] is True


def test_menus_and_profiles_load():
    menus = client.get("/api/menus").json()
    assert any(m["slug"] == "sample_sichuan" for m in menus)
    menu = client.get("/api/menus/sample_sichuan").json()
    assert menu["dishes"]
    profiles = client.get("/api/profiles").json()
    assert {p["id"] for p in profiles} >= {"li", "david", "amy"}


def test_unknown_menu_or_diner_is_404():
    assert client.get("/api/menus/nope").status_code == 404
    r = client.post(
        "/api/plan", json={"menu_id": "nope", "diner_ids": ["li"], "budget_per_person": 25}
    )
    assert r.status_code == 404
    r = client.post(
        "/api/plan",
        json={"menu_id": "sample_sichuan", "diner_ids": ["nobody"], "budget_per_person": 25},
    )
    assert r.status_code == 404


def test_plan_needs_at_least_one_diner():
    r = client.post("/api/plan", json={"menu_id": "sample_sichuan", "budget_per_person": 25})
    assert r.status_code == 422


def test_root_answers_even_without_a_frontend_build():
    assert client.get("/").status_code == 200


def test_mock_mode_plan_conflict_and_edits(monkeypatch):
    monkeypatch.setattr(api, "MOCK", True)
    base = {
        "menu_id": "sample_sichuan",
        "diner_ids": ["li", "david", "amy"],
        "budget_per_person": 25,
    }

    r = client.post("/api/plan", json=base).json()
    assert r["kind"] == "plan"
    ids = [i["dish_id"] for i in r["plan"]["items"]]
    assert "kung_pao_chicken" in ids
    fish = next(i for i in r["plan"]["items"] if i["dish_id"] == "boiled_fish_chili_oil")
    assert "amy" not in fish["edible_by"]  # fish allergy applied for real, even in mock mode

    r = client.post(
        "/api/plan",
        json={**base, "excluded_dish_ids": ["kung_pao_chicken"], "locked_dish_ids": ["mapo_tofu"]},
    ).json()
    ids = [i["dish_id"] for i in r["plan"]["items"]]
    assert "kung_pao_chicken" not in ids and "mapo_tofu" in ids

    r = client.post("/api/plan", json={**base, "budget_per_person": 12}).json()
    assert r["kind"] == "conflict" and r["conflict"]["relaxations"]


def test_inline_diners_override_saved_profiles(monkeypatch):
    monkeypatch.setattr(api, "MOCK", True)
    li_vegan = {
        "id": "li",
        "name": "Li",
        "allergies": [],
        "diets": ["vegan"],
        "dislikes": [],
        "likes": [],
    }
    r = client.post(
        "/api/plan",
        json={
            "menu_id": "sample_sichuan",
            "diner_ids": ["li"],
            "diners": [li_vegan],
            "budget_per_person": 25,
        },
    ).json()
    pork = next(i for i in r["plan"]["items"] if i["dish_id"] == "yuxiang_shredded_pork")
    assert "li" not in pork["edible_by"]


def test_planner_is_available_without_mock(monkeypatch):
    monkeypatch.setattr(api, "MOCK", False)
    r = client.post(
        "/api/plan",
        json={"menu_id": "sample_sichuan", "diner_ids": ["li"], "budget_per_person": 25},
    )
    assert r.status_code == 200


def test_real_plan_and_eligibility(monkeypatch):
    monkeypatch.setattr(api, "MOCK", False)
    profiles = client.get("/api/profiles").json()
    menu = client.get("/api/menus/sample_sichuan").json()
    r = client.post(
        "/api/plan",
        json={
            "menu_id": "sample_sichuan",
            "diners": profiles,
            "budget_per_person": 25,
            "dish_count_target": 7,
            "style_preference": "favorites",
            "explain": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "plan"
    evaluation = client.post("/api/menu/evaluate", json={"menu": menu, "diners": profiles}).json()
    fish = evaluation["boiled_fish_chili_oil"]
    assert "amy" not in fish["edible_by"]
    assert "amy" in fish["blocked_for"]


def test_menu_import_is_reviewed_before_planning(monkeypatch):
    monkeypatch.setattr(api, "MOCK", False)
    r = client.post(
        "/api/menu/parse", json={"text": "Garlic greens $12.95\nSteamed rice $2.00\nNo price here"}
    )
    assert r.status_code == 200
    dishes = r.json()["dishes"]
    assert len(dishes) == 2
    assert dishes[0]["price"] == 12.95
    assert dishes[0]["is_vegetarian"] is None
    assert dishes[0]["confirm_with_staff"]
    menu = client.get("/api/menus/sample_sichuan").json()
    menu["verified"] = False
    r = client.post(
        "/api/plan",
        json={
            "menu_id": "custom",
            "menu_override": menu,
            "diner_ids": ["li"],
            "budget_per_person": 25,
        },
    )
    assert r.status_code == 422


def test_invalid_settings_and_duplicate_dishes_rejected():
    base = {"menu_id": "sample_sichuan", "diner_ids": ["li"], "budget_per_person": 25}
    assert client.post("/api/plan", json={**base, "tax_rate": -1}).status_code == 422
    assert (
        client.post("/api/plan", json={**base, "style_preference": "not-a-style"}).status_code
        == 422
    )
    menu = client.get("/api/menus/sample_sichuan").json()
    menu["dishes"].append(menu["dishes"][0])
    assert client.post("/api/plan", json={**base, "menu_override": menu}).status_code == 422
