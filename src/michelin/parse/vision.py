"""Read dish names and prices from a menu photo with Gemini.

Gemini only transcribes what is printed: names (English and Chinese), prices, and the
printed description. It never labels ingredients or diets; the AI dish facts (plan/dish_facts.py) do that from
the name, and every row still needs human review before planning.

Configuration lives in `michelin.llm`: OPENROUTER_API_KEY (preferred), else GEMINI_API_KEY
(free Google AI Studio key) or MICHELIN_GEMINI_BACKEND=vertex. MICHELIN_VISION=off never calls a model; MICHELIN_VISION_MODEL
overrides the model (default gemini-3.8-flash). Without a backend the API falls back to local
OCR, then to text paste. Only the image is sent.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

from michelin import gemini, llm  # noqa: F401 - gemini is patched in tests
from michelin.schemas import MAX_MENU_DISHES, Dish

MAX_DISHES = MAX_MENU_DISHES

PROMPT = """Transcribe the dishes on this restaurant menu photo.

For every dish with a readable price, return its English name as printed, its Chinese name \
if printed, the price as a number (no currency sign), and any printed description. Copy what \
is printed; do not translate, guess ingredients, or add dishes that are not on the photo. \
Skip section headings, drinks and lines without a price. If nothing is readable, return an \
empty list. Also return the restaurant's name as printed on the menu (usually at the top), \
or an empty string if no name is printed."""

SCHEMA = {
    "type": "object",
    "properties": {
        "restaurant_name": {"type": "string"},
        "dishes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_en": {"type": "string"},
                    "name_zh": {"type": "string"},
                    "price": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["name_en", "price"],
            },
        },
    },
    "required": ["restaurant_name", "dishes"],
}


def configured() -> bool:
    if os.environ.get("MICHELIN_VISION", "").lower() == "off":
        return False
    return llm.provider() is not None


def model_name() -> str:
    return llm.model("vision")


def slug(text: str, taken: set[str]) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:48] or "dish"
    out, n = base, 2
    while out in taken:
        out, n = f"{base}_{n}", n + 1
    taken.add(out)
    return out


def rows_to_dishes(rows: list[dict]) -> list[Dish]:
    taken: set[str] = set()
    dishes = []
    for row in rows:  # the API keeps the first MAX_DISHES and says how many it dropped
        name = str(row.get("name_en") or "").strip()
        price = row.get("price")
        if not name or not isinstance(price, int | float) or price < 0 or price > 1000:
            continue
        zh = str(row.get("name_zh") or "").strip() or None
        desc = str(row.get("description") or "").strip()
        dishes.append(
            Dish(
                id=slug(name, taken),
                name_en=name,
                name_zh=zh,
                price=round(float(price), 2),
                description_raw=" ".join(x for x in (zh, name, desc) if x),
                confirm_with_staff=[f"Confirm ingredients, allergens, and preparation for {name}."],
            )
        )
    return dishes


_KEEP_CAPS = {"BBQ", "XO", "NYC", "USA", "UK", "LA", "NY", "II", "III"}


def nice_name(name: str) -> str:
    """'SKY PAVILION 天阁' -> 'Sky Pavilion 天阁'. Only an all-caps Latin part is changed."""
    letters = [c for c in name if c.isascii() and c.isalpha()]
    if len(letters) < 4 or not all(c.isupper() for c in letters):
        return name
    return re.sub(
        r"[A-Za-z][A-Za-z']*",
        lambda m: m.group(0) if m.group(0) in _KEEP_CAPS else m.group(0).capitalize(),
        name,
    )


def read_menu_photo(image: bytes, mime: str, client=None) -> tuple[list[Dish], str | None, str]:
    """(dishes, restaurant name if printed, model used). Raises gemini.RateLimited on 429,
    and other errors on transport or malformed output."""
    text, used = llm.generate_json(
        "vision", turns=[llm.Turn("user", PROMPT, image, mime)], schema=SCHEMA, client=client
    )
    body = json.loads(text)
    name = nice_name(str(body.get("restaurant_name") or "").strip()) or None
    return rows_to_dishes(body.get("dishes") or []), name, used
