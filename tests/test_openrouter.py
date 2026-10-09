"""OpenRouter provider with a fake HTTP client: request shape, preference, errors."""

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from michelin import api, gemini, llm
from michelin.parse import vision

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeHTTP:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers})
        status, body = self.replies.pop(0)
        return SimpleNamespace(status_code=status, json=lambda: body)


def ok(content, cost=0.0012):
    return 200, {"choices": [{"message": {"content": content}}], "usage": {"cost": cost}}


def test_openrouter_is_preferred_over_the_free_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert llm.provider() == "gemini"
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    assert llm.provider() == "openrouter"
    assert llm.model("plan") == "google/gemini-3.5-flash-lite"
    monkeypatch.setenv("MICHELIN_OPENROUTER_MODEL", "google/gemini-3.8-flash")
    assert llm.model("vision") == "google/gemini-3.8-flash"
    monkeypatch.setenv("MICHELIN_LLM_PROVIDER", "gemini")
    assert llm.provider() == "gemini"


def test_request_shape_and_cost(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    http = FakeHTTP(ok('```json\n{"a": 1}\n```'))
    before = llm.spent_usd["total"]
    text, used = llm.generate_json(
        "plan",
        system="sys",
        turns=[llm.Turn("user", "hi"), llm.Turn("model", "{}"), llm.Turn("user", "again")],
        schema={"type": "object"},
        client=http,
    )
    assert json.loads(text) == {"a": 1} and used == "google/gemini-3.5-flash-lite"
    body = http.calls[0]["json"]
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["reasoning"] == {"effort": "low", "exclude": True}
    assert http.calls[0]["headers"]["Authorization"] == "Bearer o"
    assert llm.spent_usd["total"] == pytest.approx(before + 0.0012)


def test_photo_goes_as_a_data_url_and_fills_the_import(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    reply = {"restaurant_name": "Sky", "dishes": [{"name_en": "Mapo Tofu", "price": 14.95}]}
    http = FakeHTTP(ok(json.dumps(reply)))
    monkeypatch.setattr("httpx.post", http.post)
    r = TestClient(api.app).post(
        "/api/menu/parse", json={"image_base64": base64.b64encode(PNG).decode()}
    )
    assert r.status_code == 200, r.text
    assert "google/gemini-3.5-flash-lite via OpenRouter" in r.json()["notice"]
    image = http.calls[0]["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")
    assert vision.configured()
    assert r.json()["restaurant_name"] == "Sky"
    assert TestClient(api.app).get("/api/health").json()["photo"] == "openrouter"


def test_photos_can_use_their_own_openrouter_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setenv("MICHELIN_OPENROUTER_VISION_MODEL", "openai/gpt-4o-mini")
    assert llm.model("vision") == "openai/gpt-4o-mini"
    assert llm.model("plan") == "google/gemini-3.5-flash-lite"
    http = FakeHTTP(ok(json.dumps({"restaurant_name": "", "dishes": []})))
    vision.read_menu_photo(PNG, "image/png", client=http)
    assert http.calls[0]["json"]["model"] == "openai/gpt-4o-mini"
    # Without an OpenRouter key the free Gemini key reads photos.
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert TestClient(api.app).get("/api/health").json()["photo"] == "gemini"


def test_errors_are_clear(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    turns = [llm.Turn("user", "x")]
    with pytest.raises(gemini.RateLimited, match="credit is used up"):
        llm.generate_json("plan", turns=turns, schema={}, client=FakeHTTP((402, {})))
    with pytest.raises(gemini.RateLimited, match="rate limited"):
        llm.generate_json("plan", turns=turns, schema={}, client=FakeHTTP((429, {})))
    http = FakeHTTP((503, {}), ok("{}"))
    assert llm.generate_json("plan", turns=turns, schema={}, client=http)[0] == "{}"
    with pytest.raises(llm.Unavailable):
        monkeypatch.delenv("OPENROUTER_API_KEY")
        llm.generate_json("plan", turns=turns, schema={})


def test_rejected_key_uses_the_gemini_key_or_explains(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "bad")
    turns = [llm.Turn("user", "x")]
    with pytest.raises(llm.Unavailable, match="rejected the API key"):
        llm.generate_json("plan", turns=turns, schema={}, client=FakeHTTP((401, {})))
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    gem = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **k: SimpleNamespace(text='{"ok": 1}'))
    )
    monkeypatch.setattr(gemini, "client", lambda: gem)
    text, used = llm.generate_json("plan", turns=turns, schema={}, client=FakeHTTP((401, {})))
    assert json.loads(text) == {"ok": 1} and used == "gemini-3.8-flash"
