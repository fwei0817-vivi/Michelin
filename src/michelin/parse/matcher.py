"""Map dish names the knowledge base does not recognize to one of its entries, with an LLM.

The model only chooses an entry id (or "none") from a fixed list; it never writes
ingredients. Every answer is stored in `data/knowledge/llm_matches.json`, keyed by the
normalized printed text, and reused verbatim: the same dish text gets the same match every
time, and a person can review or overwrite any stored answer (set "kb_id" and
"reviewed": true). Only dishes without a stored answer reach the API.

Providers (MICHELIN_LLM_PROVIDER, default gemini), all behind the same closed-list prompt:

  gemini         gemini-2.5-pro on Vertex AI, Google Application Default Credentials
                 (`gcloud auth application-default login`); project from GOOGLE_CLOUD_PROJECT
                 or the gcloud default, region from GOOGLE_CLOUD_LOCATION (us-central1)
  claude-vertex  claude-opus-5-5 on Vertex AI, same credentials
  claude         claude-opus-5-5 on the Anthropic API, ANTHROPIC_API_KEY

Requires the optional `llm` extra. Only dish names and descriptions are sent, never images.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from michelin.parse.knowledge import load_kb, normalize
from michelin.schemas import Dish

CACHE_PATH = Path(__file__).resolve().parents[3] / "data/knowledge/llm_matches.json"
MODELS = {
    "gemini": "gemini-2.5-pro",
    "claude-vertex": "claude-opus-5-5",
    "claude": "claude-opus-5-5",
}
NONE = "none"

SYSTEM = """You match dishes from Chinese restaurant menus in New York to entries in a \
reviewed dish catalog. The catalog lists each entry's id, Chinese names and English aliases.

For each numbered dish, answer with the catalog id of the same dish, or "none".

Answer with an id only when the dish is the same preparation under another name, spelling \
or translation (for example "Spicy Tofu w/ Ground Pork" is mapo_tofu). Answer "none" when:
- the dish only shares a main ingredient or a sauce with an entry,
- it is a variant whose protein differs from the entry (shrimp lo mein is not \
vegetable_lo_mein),
- you are not sure.
A wrong id makes the app trust the wrong ingredient list for someone with an allergy, so \
"none" is always the safe answer. Do not guess ingredients; only choose ids."""


def cache_key(dish: Dish) -> str:
    return " | ".join(normalize(x) for x in (dish.name_zh, dish.name_en, dish.description_raw))


def load_cache(path: Path = CACHE_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"note": "LLM dish-name matches. Edit kb_id and set reviewed: true to correct one.",
            "matches": {}}  # fmt: skip


def save_cache(cache: dict, path: Path = CACHE_PATH) -> None:
    cache["matches"] = dict(sorted(cache["matches"].items()))
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def catalog_text(kb: dict) -> str:
    """Stable catalog listing, the cacheable part of every request."""
    lines = [
        f"{e['id']}: {' / '.join(e['name_zh'])} | {' / '.join(e['aliases'])}"
        for e in sorted(kb["dishes"], key=lambda e: e["id"])
    ]
    return "Catalog:\n" + "\n".join(lines)


def _schema(ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dish": {"type": "integer"},
                        "kb_id": {"type": "string", "enum": [*ids, NONE]},
                    },
                    "required": ["dish", "kb_id"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["matches"],
        "additionalProperties": False,
    }


def _listing(dishes: list[Dish]) -> str:
    return "Dishes:\n" + "\n".join(
        f"{i}. " + " | ".join(filter(None, [d.name_zh, d.name_en, d.description_raw]))
        for i, d in enumerate(dishes)
    )


def _parse(text: str | None, n: int, ids: list[str]) -> list[str | None]:
    """Keep only well-formed answers naming a real id; anything else is no match."""
    out: list[str | None] = [None] * n
    if not text:
        return out
    for row in json.loads(text).get("matches", []):
        if isinstance(row.get("dish"), int) and 0 <= row["dish"] < n and row.get("kb_id") in ids:
            out[row["dish"]] = row["kb_id"]
    return out


def _gcp_project() -> str | None:
    if os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return os.environ["GOOGLE_CLOUD_PROJECT"]
    import google.auth

    return google.auth.default()[1]


def _ask_claude(dishes: list[Dish], kb: dict, client, vertex: bool) -> list[str | None]:
    if client is None:
        import anthropic

        client = (
            anthropic.AnthropicVertex(project_id=_gcp_project(), region="global")
            if vertex
            else anthropic.Anthropic()
        )
    ids = sorted(e["id"] for e in kb["dishes"])
    # Server-side refusal fallbacks exist on the Anthropic API only, not on Vertex.
    extra = {} if vertex else {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    response = client.beta.messages.create(
        model=MODELS["claude"],
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(ids)}},
        system=[
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": catalog_text(kb), "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": _listing(dishes)}],
        **extra,
    )
    if response.stop_reason != "end_turn":  # refusal or truncation: match nothing
        return [None] * len(dishes)
    text = next(b.text for b in response.content if b.type == "text")
    return _parse(text, len(dishes), ids)


def _ask_gemini(dishes: list[Dish], kb: dict, client) -> list[str | None]:
    from google.genai import types

    if client is None:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=_gcp_project(),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    ids = sorted(e["id"] for e in kb["dishes"])
    response = client.models.generate_content(
        model=MODELS["gemini"],
        contents=_listing(dishes),
        config=types.GenerateContentConfig(
            system_instruction=[SYSTEM, catalog_text(kb)],
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=_schema(ids),
        ),
    )
    return _parse(response.text, len(dishes), ids)


def provider_name() -> str:
    name = os.environ.get("MICHELIN_LLM_PROVIDER", "gemini")
    if name not in MODELS:
        raise ValueError(f"MICHELIN_LLM_PROVIDER must be one of {sorted(MODELS)}, not {name!r}")
    return name


def ask_llm(
    dishes: list[Dish], kb: dict, provider: str | None = None, client=None
) -> list[str | None]:
    """One request for all dishes. Returns a kb id or None per dish, in order."""
    provider = provider or provider_name()
    if provider == "gemini":
        return _ask_gemini(dishes, kb, client)
    return _ask_claude(dishes, kb, client, vertex=provider == "claude-vertex")


def llm_enabled() -> bool:
    return os.environ.get("MICHELIN_LLM_MATCH") == "1"


def match_names(
    dishes: list[Dish],
    *,
    call_api: bool | None = None,
    provider: str | None = None,
    client=None,
    cache_path: Path = CACHE_PATH,
) -> dict[str, str]:
    """dish id -> kb id for dishes that exact matching misses but the LLM (or a stored
    answer) maps. Stored answers are always used; the API is called only for new dish
    text, and only when `call_api` (default: MICHELIN_LLM_MATCH=1). A stored "none" from an
    older knowledge-base version is asked again, since a new entry may now fit; reviewed
    answers are never replaced."""
    from michelin.parse.knowledge import match

    kb = load_kb()
    cache = load_cache(cache_path)
    call_api = llm_enabled() if call_api is None else call_api
    pending = [d for d in dishes if match(d, kb) is None]

    def settled(dish: Dish) -> bool:
        stored = cache["matches"].get(cache_key(dish))
        return bool(stored) and (
            bool(stored["kb_id"])
            or stored.get("reviewed")
            or stored.get("kb_version") == kb.get("version")
        )

    new = [d for d in pending if not settled(d)]
    if new and call_api:
        provider = provider or provider_name()
        for dish, kb_id in zip(new, ask_llm(new, kb, provider, client), strict=True):
            cache["matches"][cache_key(dish)] = {
                "kb_id": kb_id,
                "model": MODELS[provider],
                "kb_version": kb.get("version"),
                "date": datetime.now(UTC).date().isoformat(),
                "reviewed": False,
            }
        save_cache(cache, cache_path)
    out = {}
    for dish in pending:
        stored = cache["matches"].get(cache_key(dish))
        if stored and stored["kb_id"]:
            out[dish.id] = stored["kb_id"]
    return out


def reviewed_ids(dishes: list[Dish], cache_path: Path = CACHE_PATH) -> set[str]:
    """Dish ids whose stored match a person has accepted (reviewed: true)."""
    matches = load_cache(cache_path)["matches"]
    return {d.id for d in dishes if matches.get(cache_key(d), {}).get("reviewed")}
