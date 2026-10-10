"""The course of each dish (2026-10-10): hot_main, staple (fried rice/noodles), cold, soup,
dessert, side, unknown. The printed category decides when it is clear; otherwise one small
AI call per menu (temperature 0), cached by dish in data/facts/dish_course.json so a
committed menu needs no AI call. Unknown never counts as a hot dish (plan.enough)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from michelin import llm
from michelin.plan.dish_facts import COURSES, course_of
from michelin.schemas import DishCategory

log = logging.getLogger("michelin")
ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = Path(os.environ.get("MICHELIN_COURSE_CACHE", ROOT / "data/facts/dish_course.json"))
VERSION = "1"  # bump on any change to the prompt
BATCH = 80
CLEAR = {
    DishCategory.COLD_APPETIZER,
    DishCategory.SOUP,
    DishCategory.DESSERT,
    DishCategory.DRINK,
    DishCategory.STAPLE,
}

SYSTEM = """For each dish on a Chinese restaurant menu, say how it eats as part of a meal:
"hot_main": a hot, substantial shared dish (stir-fries, braises, roast or fried meat,
  fish, tofu or hot vegetable dishes, sizzling plates, egg foo young, curries).
"staple": fried rice, noodles, lo mein, chow mein, chow fun, mei fun (NOT plain steamed rice).
"cold": cold dishes and salads. "soup". "dessert": desserts and sweet drinks.
"side": small starters and snacks: dumplings, buns, spring or egg rolls, pancakes,
  wontons, dim sum, spare-rib or wing appetizers, pickles.
"unknown": you cannot tell from the name, section and description.
Use the printed section when it says (e.g. "Appetizers" -> side, "Chow Mein" -> staple)."""


def _key(d) -> str:
    raw = "|".join(
        [
            VERSION,
            d.name_en or "",
            d.name_zh or "",
            d.category.value,
            d.menu_section or "",
            (d.description_raw or "")[:200],
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _load() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _save(new: dict) -> None:
    cache = {**_load(), **new}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
    tmp.replace(CACHE_PATH)


def _ask(batch, client=None) -> dict:
    rows = [
        {
            k: v
            for k, v in {
                "id": d.id,
                "name": d.name_en,
                "zh": d.name_zh,
                "section": d.menu_section,
                "description": (d.description_raw or "")[:160] or None,
            }.items()
            if v
        }
        for d in batch
    ]
    schema = {
        "type": "object",
        "properties": {
            "dishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": [d.id for d in batch]},
                        "course": {"type": "string", "enum": list(COURSES)},
                    },
                    "required": ["id", "course"],
                },
            }
        },
        "required": ["dishes"],
    }
    text, _ = llm.generate_json(
        "plan",
        system=SYSTEM,
        turns=[llm.Turn("user", json.dumps(rows, ensure_ascii=False))],
        schema=schema,
        client=client,
        temperature=0,
    )
    out = {}
    for row in json.loads(text or "{}").get("dishes", []):
        if isinstance(row, dict) and row.get("course") in COURSES:
            out[row.get("id")] = row["course"]
    return out


def annotate(dishes: list, client=None) -> list:
    cache = _load()
    unclear = [d for d in dishes if d.category not in CLEAR]
    missing = list({_key(d): d for d in unclear if _key(d) not in cache}.values())
    if missing and (llm.provider() is not None or client is not None):
        new = {}
        for start in range(0, len(missing), BATCH):
            batch = missing[start : start + BATCH]
            try:
                got = _ask(batch, client)
            except Exception as exc:  # noqa: BLE001 - unknown course; never counts as hot
                log.warning("Courses failed: %s: %s", type(exc).__name__, str(exc)[:200])
                break
            for d in batch:
                if d.id in got:
                    new[_key(d)] = {"name": d.name_en or d.name_zh, "course": got[d.id]}
        if new:
            _save(new)
            cache = {**cache, **new}
    return [d.model_copy(update={"course": _course(d, cache)}) for d in dishes]


def _course(d, cache) -> str:
    """Fried rice, lo mein, chow mein, chow fun, mei fun are staples by name (code, no AI),
    unless printed as cold or soup; plain rice keeps category "staple"."""
    from michelin.plan.validation import staple_kind

    c = course_of(d.category, (cache.get(_key(d)) or {}).get("course"))
    if c in ("hot_main", "side", "unknown") and staple_kind(d):
        return "staple"
    return c
