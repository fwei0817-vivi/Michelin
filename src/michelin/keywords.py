"""The one keyword list for allergens and meat (data/keywords.json), as compiled regexes.

Used by plan/dish_facts.py (what the menu prints, and the floor), plan/edibility.py and,
through an identical copy, web/src/lib/dietary.ts. Text to scan: a dish's English and
Chinese names, its printed description and its variant ("Kung Pao" + "Shrimp").
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

PATH = Path(__file__).with_name("data") / "keywords.json"
# "no pork", "w/o pork", "vegetarian chicken", "mock duck": not the real thing.
NOT = (
    r"(?<!no )(?<!w/o )(?<!without )(?<!vegetarian )(?<!vegan )(?<!mock )(?<!faux )(?<!imitation )"
)
ALLERGENS = ("shellfish", "fish", "peanut", "tree_nut", "sesame", "egg", "dairy", "soy", "wheat")
MEATS = ("pork", "beef", "meat")


@cache
def raw() -> dict:
    return {k: v for k, v in json.loads(PATH.read_text(encoding="utf-8")).items() if k[0] != "_"}


def pattern(concept: str) -> str:
    entry = raw()[concept]
    prefix = NOT if entry.get("negatable") else ""
    parts = []
    if entry.get("en"):
        parts.append(prefix + r"\b(?:" + "|".join(entry["en"]) + r")\b")
    if entry.get("zh"):
        parts.append("|".join(entry["zh"]))
    return "|".join(parts)


@cache
def regex(concept: str) -> re.Pattern:
    return re.compile(pattern(concept), re.IGNORECASE)


def found(concept: str, text: str) -> str | None:
    """The first word for this concept in the text, or None."""
    m = regex(concept).search(text or "")
    return m.group(0).strip() if m else None


_CHOICE = re.compile(r"choice of[^\n.;]*", re.IGNORECASE)


def description(dish) -> str:
    """The printed description; for one version of a dish ("Kung Pao", variant "Beef") the
    choice line listing the other versions is left out (it describes them, not this one)."""
    text = str(dish.description_raw or "")
    return _CHOICE.sub(" ", text) if getattr(dish, "variant", None) else text


def dish_text(dish) -> str:
    """Everything printed about a dish: names, description and variant."""
    return " ".join(
        str(x) for x in (dish.name_en, dish.name_zh, description(dish), dish.variant) if x
    )


def concepts_in(text: str) -> set[str]:
    return {c for c in raw() if regex(c).search(text or "")}
