from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.profiles import ProfileStore
from michelin.schemas import DinerProfile


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PROFILE_DB", tmp_path / "profiles.sqlite3")
    return TestClient(api.app)


def test_crud_history_isolation_restart_and_delete(client):
    a, b = {"X-Profile-Scope": "group-a"}, {"X-Profile-Scope": "group-b"}
    person = {"id": "person-1", "name": "Synthetic A", "likes": ["tofu"]}
    assert client.post("/api/profiles", json=person).status_code == 422
    assert client.post("/api/profiles", headers=a, json=person).status_code == 201
    assert client.post("/api/profiles", headers=a, json=person).status_code == 409
    assert client.get("/api/profiles", headers=b).json() == []
    assert client.get("/api/profiles/person-1", headers=b).status_code == 404
    other = {**person, "name": "Synthetic B", "likes": ["mushrooms"]}
    assert client.post("/api/profiles", headers=b, json=other).status_code == 201
    changed = {**person, "likes": [], "dislikes": ["tofu"], "allergies": ["egg"]}
    body = {"profile": changed, "expected_revision": 1}
    assert client.put("/api/profiles/person-1", headers=a, json=body).json()["revision"] == 2
    assert client.put("/api/profiles/person-1", headers=a, json=body).status_code == 409
    history = client.get("/api/profiles/person-1/history", headers=a).json()
    assert [h["revision"] for h in history] == [1, 2]
    assert history[0]["profile"]["likes"] == ["tofu"]
    assert history[1]["profile"]["dislikes"] == ["tofu"]
    assert ProfileStore(api.PROFILE_DB).list("group-a")["person-1"].allergies == ["egg"]
    assert client.get("/api/profiles/person-1", headers=b).json()["profile"]["likes"] == [
        "mushrooms"
    ]
    assert client.delete("/api/profiles/person-1", headers=a).json()["deleted"]
    assert client.get("/api/profiles/person-1/history", headers=a).status_code == 404
    assert client.get("/api/profiles/person-1", headers=b).status_code == 200


def test_current_input_overrides_history_without_writes(client):
    scope = {"X-Profile-Scope": "a"}
    client.post(
        "/api/profiles",
        headers=scope,
        json={"id": "p", "name": "Synthetic", "likes": ["pork"], "allergies": ["egg"]},
    )
    req = api.PlanRequest(
        menu_id="sample_sichuan",
        diner_ids=["p"],
        budget_per_person=30,
        diners=[{"id": "p", "name": "Synthetic", "diets": ["vegan"]}],
    )
    current = api._resolve_diners(req, "a")[0]
    assert current.diets == ["vegan"] and current.likes == ["pork"]
    assert current.allergies == []  # inline profile is authoritative, no allergy inference
    req.diners[0] = DinerProfile(id="p", name="Synthetic", likes=[], diets=["vegan"])
    assert api._resolve_diners(req, "a")[0].likes == []
    assert len(client.get("/api/profiles/p/history", headers=scope).json()) == 1
    with pytest.raises(api.HTTPException):
        api._resolve_diners(req.model_copy(update={"diners": []}), "another-scope")


def test_concurrent_update_cannot_lose_revision(tmp_path):
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    person = DinerProfile(id="p", name="Synthetic")
    store.save("s", person, 0)

    def save(_):
        try:
            return store.save("s", person, 1)
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(map(str, pool.map(save, range(2)))) == ["2", "conflict"]


def test_saved_likes_cannot_override_current_vegan_restriction(client, monkeypatch):
    from michelin.schemas import Dish, IngredientClaim, Menu

    monkeypatch.setattr(api, "MOCK", False)
    headers = {"X-Profile-Scope": "synthetic"}
    client.post(
        "/api/profiles", headers=headers, json={"id": "p", "name": "Synthetic", "likes": ["pork"]}
    )
    menu = Menu(
        restaurant_id="test",
        restaurant_name="Synthetic",
        cuisine="test",
        source="synthetic",
        verified=True,
        dishes=[
            Dish(id="rice", category="staple", price=1, is_vegan=True),
            Dish(id="greens", price=4, is_vegan=True),
            Dish(
                id="pork",
                price=3,
                is_vegan=False,
                main_ingredients=[IngredientClaim(name="pork", tier="menu")],
            ),
        ],
    )
    response = client.post(
        "/api/plan",
        headers=headers,
        json={
            "menu_id": "test",
            "menu_override": menu.model_dump(),
            "diner_ids": ["p"],
            "diners": [{"id": "p", "name": "Synthetic", "diets": ["vegan"]}],
            "budget_per_person": 30,
            "min_dishes_per_person": 1,
            "style_preference": "favorites",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "plan"
    assert {i["dish_id"] for i in result["plan"]["items"]} == {"greens", "rice"}
