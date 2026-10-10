"""The course of each dish (2026-10-10): hot_main, staple (fried rice/noodles), cold, soup,
dessert, side, unknown. The printed category decides when it is clear; otherwise one small
AI call per menu (temperature 0), cached by dish in data/facts/dish_course.json so a
committed menu needs no AI call. Unknown never counts as a hot dish (plan.enough)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path

from michelin import llm
from michelin.plan.dish_facts import COURSES, course_of
from michelin.schemas import DishCategory

log = logging.getLogger("michelin")
ROOT = Path(__file__).resolve().parents[3]
# Committed answers (read only at runtime) and this machine's own additions (untracked),
# so running the app never changes a committed file (QA r20).
CACHE_PATH = Path(os.environ.get("MICHELIN_COURSE_CACHE", ROOT / "data/facts/dish_course.json"))
LOCAL_PATH = Path(os.environ.get("MICHELIN_COURSE_LOCAL", ROOT / "data/local/dish_course.json"))
VERSION = "1"  # the 2026-10-10 "unknown rather than guess" wording only clarifies v1
_STARTER = re.compile(
    r"dumpling|wonton|wanton|potsticker|spring roll|egg roll|fantail|\bbuns?\b|shumai|饺|馄饨|春卷",
    re.IGNORECASE,
)  # bump on any change to the prompt
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
"unknown": the name, section and description give no basis (an unfamiliar or house
  name with no description). Answer "unknown" rather than guess; it is safe.
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


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _load() -> dict:
    return {**_read(LOCAL_PATH), **_read(CACHE_PATH)}  # committed answers win


def _save(new: dict) -> None:
    """Runtime additions go to the untracked local cache only."""
    cache = {**_read(LOCAL_PATH), **new}
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOCAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
    tmp.replace(LOCAL_PATH)


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
    unclear = [d for d in dishes if d.category not in CLEAR and _by_name(d) is None]
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
    out = [d.model_copy(update={"course": _course(d, cache)}) for d in dishes]
    return _snacks(out)


_SNACK = re.compile(
    r"\bchips\b|crackers?|crispy noodles\b|"
    r"\bwings?\b|nuggets?|\bfries\b|虾片|蝦片|脆面|脆麵",
    re.IGNORECASE,
)
_WING = re.compile(r"\bwings?\b|鸡翼|雞翼|鸡翅|雞翅", re.IGNORECASE)


def _snacks(dishes: list) -> list:
    """QA r21: a snack (chips, crackers, Crispy Noodles at $1.75, or anything priced far
    below the menu's usual hot dish) is a side, never a hot main or staple. Wings are hot
    finger food: a side, never cold."""
    hot = sorted(d.price for d in dishes if d.course == "hot_main" and d.price)
    median = hot[len(hot) // 2] if hot else None
    out = []
    for d in dishes:
        text = f"{d.name_en or ''} {d.name_zh or ''}"
        c = d.course
        if (
            c == "cold"
            and _WING.search(text)
            or c in ("hot_main", "staple")
            and (
                (_SNACK.search(text) and not _WING.search(text))
                or (median and d.price and d.price < 0.35 * median)
            )
        ):
            c = "side"
        out.append(d if c == d.course else d.model_copy(update={"course": c}))
    return out


_NOODLE = re.compile(
    r"noodle|\bmein\b|chow fun|mei fun|ho fun|fried rice|udon|\bpho\b|炒饭|面(?!筋|包|粉)|河粉|米粉|米线|粉丝",
    re.IGNORECASE,
)
_COLD_NOODLE = re.compile(r"\bcold\b|凉", re.IGNORECASE)


def _by_name(d) -> str | None:
    """Rice and noodle dishes are staples by name (code, no AI); cold noodles are cold."""
    if d.course == "staple":  # set by dish_facts.plain_rice_only (printed "staple")
        return "staple"
    text = f"{d.name_en or ''} {d.name_zh or ''}"
    if d.category in CLEAR or not _NOODLE.search(text):
        return None
    return "cold" if _COLD_NOODLE.search(text) else "staple"


def _course(d, cache) -> str:
    """Fried rice, lo mein, chow mein, chow fun, mei fun are staples by name (code, no AI),
    unless printed as cold or soup; plain rice keeps category "staple"."""
    from michelin.plan.validation import staple_kind

    named = _by_name(d)
    if named:
        return named
    c = course_of(d.category, (cache.get(_key(d)) or {}).get("course"))
    # printed as a cold appetizer but a hot starter by name or section -> side (spot check)
    text = f"{d.name_en or ''} {d.name_zh or ''}"
    if c == "cold" and (_STARTER.search(text) or "hot" in (d.menu_section or "").lower()):
        return "side"
    if c in ("hot_main", "side", "unknown") and staple_kind(d):
        return "staple"
    return c
