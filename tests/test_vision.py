"""Menu photo reading with Gemini, using a fake client: transcription only, labels from the KB."""

import base64
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from michelin import api
from michelin.parse import vision

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
client = TestClient(api.app)


class FakeModels:
    def __init__(self, body):
        self.body, self.calls = body, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.body))


def fake(body):
    return SimpleNamespace(models=FakeModels(body))


def test_rows_become_unlabeled_dishes_with_unique_ids():
    dishes = vision.rows_to_dishes(
        [
            {"name_en": "Mapo Tofu", "name_zh": "麻婆豆腐", "price": 14.95},
            {"name_en": "Mapo Tofu", "price": 16},
            {"name_en": "", "price": 3},
            {"name_en": "Tea", "price": "free"},
        ]
    )
    assert [d.id for d in dishes] == ["mapo_tofu", "mapo_tofu_2"]
    assert dishes[0].is_vegetarian is None and not dishes[0].allergens


def test_photo_uses_gemini_and_knowledge_base(monkeypatch):
    fake_client = fake(
        {
            "restaurant_name": "Sky Pavilion",
            "dishes": [
                {"name_en": "Eggplant with Garlic Sauce", "name_zh": "鱼香茄子", "price": 15.5},
                {"name_en": "Steamed Rice", "price": 2},
            ],
        }
    )
    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(vision, "_client", lambda: fake_client)
    r = client.post("/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "gemini" and body["restaurant_name"] == "Sky Pavilion"
    eggplant = body["dishes"][0]
    # Looks vegetarian, but the knowledge base knows it often hides minced pork.
    assert any("pork" in i["name"] and i["tier"] != "menu" for i in eggplant["main_ingredients"])
    assert any("minced pork" in q for q in eggplant["confirm_with_staff"])
    evaluation = client.post(
        "/api/menu/evaluate",
        json={
            "menu": {
                "restaurant_id": "sky",
                "restaurant_name": "Sky Pavilion",
                "cuisine": "custom",
                "source": "photo",
                "currency": "USD",
                "verified": False,
                "dishes": body["dishes"],
            },
            "diners": [{"id": "v", "name": "V", "diets": ["vegetarian"]}],
        },
    ).json()
    assert evaluation[eggplant["id"]]["questions"]
    assert fake_client.models.calls[0]["model"].startswith("gemini")


def test_photo_without_gemini_or_ocr_asks_for_text(monkeypatch):
    monkeypatch.setattr(vision, "configured", lambda: False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    r = client.post("/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 503
    assert client.get("/api/health").json()["photo"] is None


def test_gemini_failure_without_ocr_is_a_clear_error(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("quota")

    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(vision, "read_menu_photo", boom)
    monkeypatch.setattr("shutil.which", lambda _: None)
    r = client.post("/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 502
    assert "paste the menu text" in r.json()["detail"]


def test_not_configured_without_key(monkeypatch):
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MICHELIN_VISION"):
        monkeypatch.delenv(key, raising=False)
    assert not vision.configured()
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("MICHELIN_VISION", "off")
    assert not vision.configured()
