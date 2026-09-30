import base64
import json
import os
import socket
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from michelin import api, model


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MICHELIN_EXTRACTION_PROVIDER", "replay")
    monkeypatch.setattr(api, "PROFILE_DB", tmp_path / "history.sqlite3")
    monkeypatch.setattr(api, "MOCK", False)

    def no_network(*args, **kwargs):
        raise AssertionError("External network forbidden in offline regression")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    return TestClient(api.app)


def prepared_body(client, index=0):
    row = client.get("/api/model/prepared").json()[index]
    return {"menu_id": row["menu_id"], "text": row["input_text"]}


@pytest.mark.parametrize("index", [0, 1])
def test_prepared_output_is_grounded_unreviewed_and_labelled(client, index):
    body = prepared_body(client, index)
    result = client.post("/api/menu/extract", json=body)
    assert result.status_code == 200
    data = result.json()
    assert data["mode"] == "prepared_replay" and data["provider"] == "assistant-prepared"
    assert data["menu"]["restaurant_id"] == body["menu_id"]
    assert not data["menu"]["verified"]
    assert data["menu"]["preparation_mode"] == "prepared_replay"
    assert data["retrieved_at"] == "2026-09-30"
    assert all(not d["reviewed_allergens"] for d in data["menu"]["dishes"])
    assert "no live model" in data["notice"].lower()


def test_unprepared_input_never_maps_to_known_menu(client):
    body = prepared_body(client)
    assert (
        client.post(
            "/api/menu/extract", json={**body, "text": body["text"] + " changed"}
        ).status_code
        == 409
    )
    assert (
        client.post("/api/menu/extract", json={**body, "menu_id": "not-known"}).status_code == 409
    )
    assert (
        client.post(
            "/api/menu/extract",
            json={
                "menu_id": body["menu_id"],
                "image_base64": base64.b64encode(b"unrelated image").decode(),
            },
        ).status_code
        == 409
    )
    assert client.post("/api/menu/extract", json={**body, "image_base64": "abc"}).status_code == 422
    assert client.post("/api/menu/extract", json={"menu_id": body["menu_id"]}).status_code == 422
    assert client.post("/api/menu/extract", json={**body, "ignore_hash": True}).status_code == 422


@pytest.mark.parametrize(
    "fault", ["invalid_price", "duplicate_id", "wrong_identity", "empty", "failure"]
)
def test_adapter_output_is_validated_before_acceptance(client, monkeypatch, fault):
    class BrokenProvider:
        name = "synthetic-failure"
        mode = "prepared_replay"

        def extract(self, request):
            record = model.ReplayProvider().extract(request)
            if fault == "failure":
                raise RuntimeError("Synthetic failure")
            if fault == "invalid_price":
                record["menu"]["dishes"][0]["price"] = "garbled"
            if fault == "duplicate_id":
                record["menu"]["dishes"].append(record["menu"]["dishes"][0])
            if fault == "wrong_identity":
                record["menu"]["restaurant_id"] = "wrong"
            if fault == "empty":
                record["menu"]["dishes"] = []
            return record

    monkeypatch.setitem(model.PROVIDERS, "test-adapter", BrokenProvider)
    monkeypatch.setenv("MICHELIN_EXTRACTION_PROVIDER", "test-adapter")
    assert client.post("/api/menu/extract", json=prepared_body(client)).status_code == 502


def test_unknown_provider_does_not_fall_back(client, monkeypatch):
    monkeypatch.setenv("MICHELIN_EXTRACTION_PROVIDER", "not-installed")
    assert client.post("/api/menu/extract", json=prepared_body(client)).status_code == 502


def test_same_contract_supports_replacement_adapter(client, monkeypatch):
    class Replacement(model.ReplayProvider):
        name = "synthetic-replacement"

    monkeypatch.setitem(model.PROVIDERS, "replacement", Replacement)
    monkeypatch.setenv("MICHELIN_EXTRACTION_PROVIDER", "replacement")
    response = client.post("/api/menu/extract", json=prepared_body(client)).json()
    assert response["provider"] == "synthetic-replacement"
    assert response["menu"]["dishes"]


def test_replay_review_plan_swaps_restrictions_and_failure(client):
    menu = client.post("/api/menu/extract", json=prepared_body(client)).json()["menu"]
    people = [{"id": f"synthetic-{i}", "name": f"Synthetic {i}"} for i in range(3)]
    body = {
        "menu_id": menu["restaurant_id"],
        "menu_override": menu,
        "diners": people,
        "budget_per_person": 40,
        "dish_count_target": 4,
        "min_dishes_per_person": 2,
    }
    assert client.post("/api/plan", json=body).status_code == 422
    menu["verified"] = True  # explicit simulated human review of the factual extract
    result = client.post("/api/plan", json=body).json()
    assert result["kind"] == "plan"
    first = result["plan"]
    old = next(i["dish_id"] for i in first["items"] if i["dish_id"] != "rice")
    candidate = next(
        d["id"] for d in menu["dishes"] if d["id"] not in {i["dish_id"] for i in first["items"]}
    )
    result = client.post(
        "/api/plan", json={**body, "excluded_dish_ids": [old], "locked_dish_ids": [candidate]}
    ).json()
    assert result["kind"] == "plan"
    assert old not in {i["dish_id"] for i in result["plan"]["items"]}
    assert candidate in {i["dish_id"] for i in result["plan"]["items"]}
    evaluated = client.post(
        "/api/menu/evaluate",
        json={"menu": menu, "diners": [{**p, "allergies": ["shellfish"]} for p in people]},
    ).json()
    assert evaluated["chive_pancakes"]["assessments"]["synthetic-0"]["status"] == "conflict"
    assert evaluated["mapo"]["assessments"]["synthetic-0"]["status"] == "requires_confirmation"
    result = client.post(
        "/api/plan", json={**body, "diners": [{**p, "allergies": ["shellfish"]} for p in people]}
    ).json()
    assert result["conflict"]["code"] == "missing_information"
    result = client.post("/api/plan", json={**body, "budget_per_person": 1}).json()
    assert result["conflict"]["code"] == "no_solution"
    result = client.post(
        "/api/plan", json={**body, "locked_dish_ids": [old], "excluded_dish_ids": [old]}
    ).json()
    assert result["kind"] == "conflict"


def test_history_survives_separate_python_processes(tmp_path):
    path = str(tmp_path / "persistent.sqlite3")
    code = """
import os
from pathlib import Path
from michelin.profiles import ProfileStore
from michelin.schemas import DinerProfile
store = ProfileStore(Path(os.environ['MICHELIN_PROFILE_DB']))
"""
    env = {**os.environ, "MICHELIN_PROFILE_DB": path}
    subprocess.run(
        [
            sys.executable,
            "-c",
            code
            + "store.save('synthetic', DinerProfile(id='p', name='Synthetic', likes=['tofu']), 0)",
        ],
        env=env,
        check=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code + "print(store.history('synthetic', 'p')[0]['profile']['likes'][0])",
        ],
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == "tofu"


def test_prepared_records_match_public_facts():
    from pathlib import Path

    fixtures = json.loads((Path(__file__).parent / "fixtures/public_menus.json").read_text())
    for record in model.prepared_catalog():
        source = next(m for m in fixtures["menus"] if m["restaurant_id"] == record["menu_id"])
        for dish in source["dishes"]:
            actual = next(d for d in record["menu"]["dishes"] if d["id"] == dish["id"])
            for key, value in dish.items():
                assert actual[key] == value


def test_registration_roundtrip_and_no_overwrite(client, monkeypatch, tmp_path):
    from pathlib import Path

    row = model.prepared_catalog()[0]
    text_path, response_path = tmp_path / "input.txt", tmp_path / "response.json"
    text_path.write_text(row["input_text"])
    response_path.write_text(json.dumps(row["menu"]))
    output = tmp_path / "prepared" / "response.json"
    command = [
        sys.executable,
        "scripts/register_prepared_response.py",
        "--menu-id",
        row["menu_id"],
        "--input",
        str(text_path),
        "--response",
        str(response_path),
        "--source-url",
        row["source_url"],
        "--retrieved-at",
        row["retrieved_at"],
        "--output",
        str(output),
    ]
    root = Path(__file__).resolve().parents[1]
    subprocess.run(command, check=True, cwd=root, capture_output=True)
    assert subprocess.run(command, cwd=root, capture_output=True, check=False).returncode != 0
    monkeypatch.setattr(model, "PREPARED_DIR", output.parent)
    assert (
        client.post(
            "/api/menu/extract", json={"menu_id": row["menu_id"], "text": row["input_text"]}
        ).status_code
        == 200
    )
    # Identical bytes labelled as an image are not the prepared text input.
    response = client.post(
        "/api/menu/extract",
        json={
            "menu_id": row["menu_id"],
            "image_base64": base64.b64encode(row["input_text"].encode()).decode(),
        },
    )
    assert response.status_code == 409
