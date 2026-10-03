"""Map dish names the knowledge base does not recognize to one of its entries, with Claude.

The model only chooses an entry id (or "none") from a fixed list; it never writes
ingredients. Every answer is stored in `data/knowledge/llm_matches.json`, keyed by the
normalized printed text, and reused verbatim: the same dish text gets the same match every
time, and a person can review or overwrite any stored answer (set "kb_id" and
"reviewed": true). Only dishes without a stored answer reach the API.

Requires the optional `llm` extra and an Anthropic credential in the environment
(ANTHROPIC_API_KEY, e.g. `uv run --env-file .env ...`, or an `ant auth login` profile). Only dish names and descriptions are sent, never images.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from michelin.parse.knowledge import load_kb, normalize
from michelin.schemas import Dish

CACHE_PATH = Path(__file__).resolve().parents[3] / "data/knowledge/llm_matches.json"
MODEL = "claude-opus-5-5"
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


def ask_claude(dishes: list[Dish], kb: dict, client=None) -> list[str | None]:
    """One request for all dishes. Returns a kb id or None per dish, in order."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    ids = sorted(e["id"] for e in kb["dishes"])
    listing = "\n".join(
        f"{i}. " + " | ".join(filter(None, [d.name_zh, d.name_en, d.description_raw]))
        for i, d in enumerate(dishes)
    )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(ids)}},
        system=[
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": catalog_text(kb), "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": f"Dishes:\n{listing}"}],
    )
    out: list[str | None] = [None] * len(dishes)
    if response.stop_reason != "end_turn":  # refusal or truncation: match nothing
        return out
    text = next(b.text for b in response.content if b.type == "text")
    for row in json.loads(text)["matches"]:
        if 0 <= row["dish"] < len(dishes) and row["kb_id"] in ids:
            out[row["dish"]] = row["kb_id"]
    return out


def llm_enabled() -> bool:
    return os.environ.get("MICHELIN_LLM_MATCH") == "1"


def match_names(
    dishes: list[Dish],
    *,
    call_api: bool | None = None,
    client=None,
    cache_path: Path = CACHE_PATH,
) -> dict[str, str]:
    """dish id -> kb id for dishes that exact matching misses but the LLM (or a stored
    answer) maps. Stored answers are always used; the API is called only for new dish
    text, and only when `call_api` (default: MICHELIN_LLM_MATCH=1)."""
    from michelin.parse.knowledge import match

    kb = load_kb()
    cache = load_cache(cache_path)
    call_api = llm_enabled() if call_api is None else call_api
    pending = [d for d in dishes if match(d, kb) is None]
    new = [d for d in pending if cache_key(d) not in cache["matches"]]
    if new and call_api:
        for dish, kb_id in zip(new, ask_claude(new, kb, client), strict=True):
            cache["matches"][cache_key(dish)] = {
                "kb_id": kb_id,
                "model": MODEL,
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
