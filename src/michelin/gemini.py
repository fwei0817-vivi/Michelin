"""Shared Gemini client setup for menu photo reading and dish-name matching.

Default backend is the Gemini Developer API (Google AI Studio), which has a free tier:

  GEMINI_API_KEY (or GOOGLE_API_KEY)   key from https://aistudio.google.com/apikey
  MICHELIN_GEMINI_MODEL                model for every Gemini call (default gemini-3.8-flash)
  MICHELIN_VISION_MODEL                override for menu photos only
  MICHELIN_LLM_MODEL                   override for dish-name matching only
  MICHELIN_GEMINI_FALLBACK_MODEL       tried when the model is overloaded (default
                                       gemini-2.5-flash, also free; empty disables)
  MICHELIN_GEMINI_BACKEND=vertex       use Vertex AI instead (billing project, Application
                                       Default Credentials, GOOGLE_CLOUD_PROJECT and
                                       GOOGLE_CLOUD_LOCATION). MICHELIN_VISION=vertex also works.

Requires the optional `llm` extra (google-genai). Never log the key.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-2.5-flash"
TIMEOUT_MS = 90_000


RATE_LIMIT_MESSAGE = (
    "Gemini's free-tier rate limit was reached. Wait a minute and try again, "
    "or paste the menu text."
)
DAILY_LIMIT_MESSAGE = (
    "Today's free Gemini quota is used up; it resets daily. Set OPENROUTER_API_KEY for a "
    "paid model, or paste the menu text instead of a photo."
)


class RateLimited(RuntimeError):
    """Gemini answered 429 / RESOURCE_EXHAUSTED (free-tier quota). `daily` when the
    per-day quota is gone rather than the per-minute one."""

    def __init__(self, daily: bool = False, message: str | None = None):
        self.daily = daily
        super().__init__(message or (DAILY_LIMIT_MESSAGE if daily else RATE_LIMIT_MESSAGE))


# While a quota is exhausted, skip calls instead of spending requests on more 429s.
_blocked_until = {"until": 0.0, "daily": False}
MINUTE_COOLDOWN_S = 60
DAILY_COOLDOWN_S = 60 * 60


def _is_daily(exc: BaseException) -> bool:
    return "PerDay" in str(exc) or "per day" in str(exc).lower()


def reset_cooldown() -> None:
    _blocked_until.update(until=0.0, daily=False)


def api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def use_vertex() -> bool:
    return (
        os.environ.get("MICHELIN_GEMINI_BACKEND", "").lower() == "vertex"
        or os.environ.get("MICHELIN_VISION", "").lower() == "vertex"
    )


def available() -> bool:
    """A backend is configured and the SDK is installed."""
    if not (use_vertex() or api_key()):
        return False
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def model(task: str = "") -> str:
    """task "vision", "match" or "plan" picks its own override first."""
    specific = {
        "vision": "MICHELIN_VISION_MODEL",
        "match": "MICHELIN_LLM_MODEL",
        "plan": "MICHELIN_PLANNER_MODEL",
    }.get(task)
    return (
        (specific and os.environ.get(specific))
        or os.environ.get("MICHELIN_GEMINI_MODEL")
        or DEFAULT_MODEL
    )


def gcp_project() -> str | None:
    if os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return os.environ["GOOGLE_CLOUD_PROJECT"]
    import google.auth

    return google.auth.default()[1]


def client():
    from google import genai
    from google.genai import types

    http = types.HttpOptions(timeout=TIMEOUT_MS)
    if use_vertex():
        return genai.Client(
            vertexai=True,
            project=gcp_project(),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            http_options=http,
        )
    return genai.Client(api_key=api_key(), http_options=http)


def is_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, RateLimited):
        return True
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "")
    return code == 429 or "RESOURCE_EXHAUSTED" in status or "RESOURCE_EXHAUSTED" in str(exc)


def fallback_model() -> str | None:
    """Tried once when the main model is overloaded (5xx). Empty string disables it."""
    value = os.environ.get("MICHELIN_GEMINI_FALLBACK_MODEL", FALLBACK_MODEL)
    return value or None


def _overloaded(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    return isinstance(code, int) and code >= 500


def generate(client, *, model: str, config=None, retry_wait: float = 2.0, **kwargs):
    """client.models.generate_content -> (response, model actually used).

    429 raises RateLimited. A 5xx ("high demand") is retried once after a short wait, then
    sent once to the fallback model. Other errors propagate."""
    import time

    if time.time() < _blocked_until["until"]:
        raise RateLimited(daily=_blocked_until["daily"])
    attempts = [model, model]
    alt = fallback_model()
    if alt and alt != model:
        attempts.append(alt)
    for i, model_id in enumerate(attempts):
        try:
            config_for = config
            if config is not None and model_id != model:
                config_for = config.model_copy(
                    update={"temperature": sampling(model_id).get("temperature")}
                )
            return client.models.generate_content(
                model=model_id, config=config_for, **kwargs
            ), model_id
        except Exception as exc:
            if is_rate_limit(exc):
                daily = _is_daily(exc)
                wait = DAILY_COOLDOWN_S if daily else MINUTE_COOLDOWN_S
                _blocked_until.update(until=time.time() + wait, daily=daily)
                raise RateLimited(daily=daily) from exc
            if not _overloaded(exc) or i == len(attempts) - 1:
                raise
            if i == 0 and retry_wait:
                time.sleep(retry_wait)
    raise AssertionError("unreachable")


def sampling(model_id: str) -> dict:
    """Gemini 2.x is steadiest at temperature 0; Gemini 3 models are tuned for the default
    (Google advises against lowering it), so leave it unset there."""
    return {"temperature": 0} if model_id.startswith("gemini-2") else {}
