from fastapi.testclient import TestClient

from michelin.api import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


def test_menus_and_profiles_load():
    menus = client.get("/api/menus").json()
    assert any(m["slug"] == "sample_sichuan" for m in menus)
    menu = client.get("/api/menus/sample_sichuan").json()
    assert menu["dishes"]
    profiles = client.get("/api/profiles").json()
    assert {p["id"] for p in profiles} >= {"li", "amy", "ben"}


def test_unknown_menu_is_404():
    assert client.get("/api/menus/nope").status_code == 404
    r = client.post("/api/plan", json={"menu_id": "nope", "diner_ids": ["li"], "budget_per_person": 25})
    assert r.status_code == 404


def test_frontend_is_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Michelin" in r.text


def test_mock_mode_returns_plan_and_conflict(monkeypatch):
    import michelin.api as api

    monkeypatch.setattr(api, "MOCK", True)
    body = {"menu_id": "sample_sichuan", "diner_ids": ["li", "amy"], "budget_per_person": 25}
    r = client.post("/api/plan", json=body).json()
    assert r["kind"] == "plan" and r["plan"]["items"]
    r = client.post("/api/plan", json={**body, "budget_per_person": 12}).json()
    assert r["kind"] == "conflict" and r["conflict"]["relaxations"]


def test_plan_is_501_until_optimizer_exists(monkeypatch):
    import michelin.api as api

    monkeypatch.setattr(api, "MOCK", False)
    r = client.post("/api/plan", json={"menu_id": "sample_sichuan", "diner_ids": ["li"], "budget_per_person": 25})
    assert r.status_code in (200, 501)
