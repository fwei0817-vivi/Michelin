"""Menu photo reading with Gemini, using a fake client: transcription only, labels from the KB."""

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.parse import vision


@pytest.fixture(autouse=True)
def gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # provider "gemini"; clients are faked


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
    monkeypatch.setattr(vision.gemini, "client", lambda: fake_client)
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
    call = fake_client.models.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert call["config"].temperature is None  # Gemini 3: keep the default temperature
    assert "Gemini (gemini-3.8-flash) read the dish names" in body["notice"]
    assert "No model API" not in body["notice"]


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
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MICHELIN_VISION", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert not vision.configured()
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("MICHELIN_VISION", "off")
    assert not vision.configured()


class RateLimitedModels:
    def generate_content(self, **_kwargs):
        from google.genai import errors

        raise errors.ClientError(
            429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}}
        )


def test_free_tier_rate_limit_is_explained(monkeypatch):
    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(
        vision.gemini, "client", lambda: SimpleNamespace(models=RateLimitedModels())
    )
    monkeypatch.setattr("shutil.which", lambda _: None)
    r = client.post("/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"] and "paste the menu text" in r.json()["detail"]


def test_rate_limit_falls_back_to_local_ocr(monkeypatch):
    import subprocess

    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(
        vision.gemini, "client", lambda: SimpleNamespace(models=RateLimitedModels())
    )
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="Mapo Tofu 14.95\n"),
    )
    r = client.post("/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "local_ocr" and body["dishes"][0]["name_en"] == "Mapo Tofu"
    assert "rate limit" in body["notice"]


def test_model_is_configurable(monkeypatch):
    assert vision.model_name() == "gemini-3.8-flash"
    monkeypatch.setenv("MICHELIN_GEMINI_MODEL", "gemini-3.5-flash-lite")
    assert vision.model_name() == "gemini-3.5-flash-lite"
    monkeypatch.setenv("MICHELIN_VISION_MODEL", "gemini-2.5-flash")
    assert vision.model_name() == "gemini-2.5-flash"
    assert vision.gemini.sampling("gemini-2.5-flash") == {"temperature": 0}


def test_developer_api_by_default_vertex_on_request(monkeypatch):
    from michelin import gemini

    assert gemini.available() and not gemini.use_vertex()
    monkeypatch.setenv("MICHELIN_GEMINI_BACKEND", "vertex")
    assert gemini.use_vertex()


def test_text_paste_notice_says_no_model(monkeypatch):
    r = client.post("/api/menu/parse", json={"text": "Mapo Tofu 14.95"})
    assert "No model API was called" in r.json()["notice"]


class BusyThenOk:
    def __init__(self, body):
        self.body, self.calls = body, []

    def generate_content(self, **kwargs):
        from google.genai import errors

        self.calls.append(kwargs["model"])
        if kwargs["model"] == "gemini-3.8-flash":
            raise errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})
        return SimpleNamespace(text=json.dumps(self.body))


def test_overloaded_model_retries_then_uses_fallback(monkeypatch):
    models = BusyThenOk({"dishes": [{"name_en": "Mapo Tofu", "price": 14.95}]})
    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(vision.gemini, "client", lambda: SimpleNamespace(models=models))
    monkeypatch.setattr("time.sleep", lambda _s: None)
    r = client.post("/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 200, r.text
    assert models.calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-2.5-flash"]
    assert "Gemini (gemini-2.5-flash) read" in r.json()["notice"]


class DailyQuotaGone:
    def __init__(self):
        self.calls = 0

    def generate_content(self, **_kwargs):
        from google.genai import errors

        self.calls += 1
        raise errors.ClientError(
            429,
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Quota exceeded for metric generate_content_free_tier_requests, "
                    "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                }
            },
        )


def test_daily_quota_is_friendly_and_stops_further_calls(monkeypatch):
    models = DailyQuotaGone()
    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(vision.gemini, "client", lambda: SimpleNamespace(models=models))
    monkeypatch.setattr("shutil.which", lambda _: None)
    image = {"image_base64": base64.b64encode(PNG).decode()}
    first = client.post("/api/menu/parse", json=image)
    assert first.status_code == 429
    assert "free Gemini quota is used up" in first.json()["detail"]
    second = client.post("/api/menu/parse", json=image)
    assert second.status_code == 429
    assert models.calls == 1  # the cooldown skips the request instead of spending another
