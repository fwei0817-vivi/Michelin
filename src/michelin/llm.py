"""Which LLM answers: OpenRouter (paid key) first, then the free Gemini key, else none.

  OPENROUTER_API_KEY            OpenRouter, OpenAI-compatible, https://openrouter.ai/api/v1
  MICHELIN_OPENROUTER_MODEL     default google/gemini-3.5-flash-lite (photos, plans, dish
                                facts, swaps); 2.5 Flash is retired on OpenRouter 2026-10-20
  MICHELIN_OPENROUTER_VISION_MODEL  menu photos; must accept images; default as above
  MICHELIN_OPENROUTER_REASONING  reasoning effort for OpenRouter models: "low" (default),
                                "minimal", "medium", "high", or "" to send none
  GEMINI_API_KEY                free Gemini Developer API (see michelin.gemini)
  MICHELIN_LLM_PROVIDER         force "openrouter" or "gemini"

Every call asks for JSON that matches a schema. Callers validate the content themselves.
Never log keys.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

from michelin import gemini
from michelin.gemini import RateLimited

log = logging.getLogger("michelin")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT = "google/gemini-3.5-flash-lite"
REASONING_DEFAULT = "low"  # thinking tokens are billed as output; low keeps latency down
TIMEOUT_S = 120
spent_usd = {"total": 0.0}  # OpenRouter cost reported by the API in this process


class Unavailable(RuntimeError):
    """No LLM is configured."""


class BadKey(RuntimeError):
    """OpenRouter rejected the key (401/403)."""


@dataclass
class Turn:
    role: str  # "user" | "model"
    text: str
    image: bytes | None = None
    mime: str | None = None


def openrouter_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or None


def provider() -> str | None:
    choice = os.environ.get("MICHELIN_LLM_PROVIDER", "").lower()
    if choice == "openrouter":
        return "openrouter" if openrouter_key() else None
    if choice == "gemini":
        return "gemini" if gemini.available() else None
    if openrouter_key():
        return "openrouter"
    if gemini.available():
        return "gemini"
    return None


def model(task: str, which: str | None = None) -> str:
    which = which or provider()
    if which == "openrouter":
        if task == "vision" and os.environ.get("MICHELIN_OPENROUTER_VISION_MODEL"):
            return os.environ["MICHELIN_OPENROUTER_VISION_MODEL"]
        return os.environ.get("MICHELIN_OPENROUTER_MODEL") or OPENROUTER_DEFAULT
    return gemini.model(task)


def label(model_id: str) -> str:
    """Readable model name for notices."""
    return f"{model_id} via OpenRouter" if "/" in model_id else model_id


def generate_json(
    task: str,
    *,
    turns: list[Turn],
    schema: dict,
    system: str | None = None,
    which: str | None = None,
    client=None,
    temperature: float | None = None,
) -> tuple[str, str]:
    """(JSON text, model used). Raises Unavailable, RateLimited, or provider errors."""
    which = which or provider()
    if which is None:
        raise Unavailable("No AI model is configured. Set OPENROUTER_API_KEY or GEMINI_API_KEY.")
    model_id = model(task, which)
    if which == "openrouter":
        try:
            return _openrouter(model_id, turns, schema, system, client, temperature), model_id
        except BadKey:
            forced = os.environ.get("MICHELIN_LLM_PROVIDER", "").lower() == "openrouter"
            if forced or not gemini.available():
                raise Unavailable(
                    "OpenRouter rejected the API key. Check OPENROUTER_API_KEY, or set "
                    "GEMINI_API_KEY to use the free Gemini tier."
                ) from None
            log.warning("OpenRouter rejected the key; using the Gemini key instead.")
            return _gemini(model(task, "gemini"), turns, schema, system, None, temperature)
    return _gemini(model_id, turns, schema, system, client, temperature)


def _gemini(model_id, turns, schema, system, client, temperature=None):
    from google.genai import types

    contents = []
    for t in turns:
        parts = []
        if t.image is not None:
            parts.append(types.Part.from_bytes(data=t.image, mime_type=t.mime or "image/png"))
        parts.append(types.Part.from_text(text=t.text))
        contents.append(types.Content(role=t.role, parts=parts))
    response, used = gemini.generate(
        client or gemini.client(),
        model=model_id,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            **(
                {"temperature": temperature}
                if temperature is not None
                else gemini.sampling(model_id)
            ),
        ),
    )
    return response.text or "", used


def _openrouter(model_id, turns, schema, system, client, temperature=None) -> str:
    import httpx

    messages = [{"role": "system", "content": system}] if system else []
    for t in turns:
        role = "assistant" if t.role == "model" else "user"
        if t.image is None:
            messages.append({"role": role, "content": t.text})
            continue
        url = f"data:{t.mime or 'image/png'};base64,{base64.b64encode(t.image).decode()}"
        messages.append(
            {
                "role": role,
                "content": [
                    {"type": "text", "text": t.text},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        )
    body = {
        "model": model_id,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": False, "schema": schema},
        },
        "usage": {"include": True},
    }
    if temperature is not None:
        body["temperature"] = temperature
    effort = os.environ.get("MICHELIN_OPENROUTER_REASONING", REASONING_DEFAULT).strip().lower()
    if effort:
        body["reasoning"] = {"effort": effort, "exclude": True}
    headers = {
        "Authorization": f"Bearer {openrouter_key()}",
        "X-Title": "Michelin table planner",
    }
    http = client or httpx
    for attempt in range(2):
        r = http.post(OPENROUTER_URL, json=body, headers=headers, timeout=TIMEOUT_S)
        if r.status_code == 429:
            raise RateLimited(
                message="The AI service is rate limited right now. Wait a minute and try again."
            )
        if r.status_code == 402:
            raise RateLimited(
                daily=True,
                message="The OpenRouter credit is used up. Add credit, or set GEMINI_API_KEY "
                "to use the free Gemini tier.",
            )
        if r.status_code in (401, 403):
            raise BadKey()
        if r.status_code >= 500 and attempt == 0:
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"OpenRouter error {r.status_code}")
        data = r.json()
        if "error" in data and not data.get("choices"):
            code = data["error"].get("code") if isinstance(data["error"], dict) else None
            if code == 429:
                raise RateLimited(message="The AI service is rate limited right now.")
            raise RuntimeError(f"OpenRouter error {code}")
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        if isinstance(cost, int | float):
            spent_usd["total"] += cost
            thinking = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            log.info(
                "OpenRouter %s cost $%.5f (in %s, out %s, reasoning %s)",
                model_id,
                cost,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                thinking,
            )
        content = data["choices"][0]["message"].get("content") or ""
        if isinstance(content, list):
            content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
        return _strip_fence(content)
    raise RuntimeError("OpenRouter did not answer")


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
