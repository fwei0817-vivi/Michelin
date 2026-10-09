"""Read dish names and prices from a menu photo with Gemini.

Gemini only transcribes what is printed: names (English and Chinese), prices, and the
printed description. It never labels ingredients or diets; `label_imported` does that from
the reviewed knowledge base, and every row still needs human review before planning.

Configuration (any one; otherwise the API falls back to local OCR, then to text paste):

  GEMINI_API_KEY or GOOGLE_API_KEY      Gemini Developer API
  MICHELIN_VISION=vertex                Vertex AI with Application Default Credentials,
                                        GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION
  MICHELIN_VISION=off                   never call a model
  MICHELIN_VISION_MODEL                 default gemini-2.5-flash

Requires the optional `llm` extra (google-genai). Only the image is sent.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

from michelin.schemas import Dish

MODEL = "gemini-2.5-flash"
MAX_DISHES = 40

PROMPT = """Transcribe the dishes on this restaurant menu photo.

For every dish with a readable price, return its English name as printed, its Chinese name \
if printed, the price as a number (no currency sign), and any printed description. Copy what \
is printed; do not translate, guess ingredients, or add dishes that are not on the photo. \
Skip section headings, drinks and lines without a price. If nothing is readable, return an \
empty list."""

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
    "required": ["dishes"],
}


def configured() -> bool:
    mode = os.environ.get("MICHELIN_VISION", "").lower()
    if mode == "off":
        return False
    if not (
        mode == "vertex" or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    ):
        return False
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def _client():
    from google import genai

    if os.environ.get("MICHELIN_VISION", "").lower() == "vertex":
        from michelin.parse.matcher import _gcp_project

        return genai.Client(
            vertexai=True,
            project=_gcp_project(),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    return genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )


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
    for row in rows[:MAX_DISHES]:
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


def read_menu_photo(image: bytes, mime: str, client=None) -> tuple[list[Dish], str | None]:
    """(dishes, restaurant name if printed). Raises on transport or malformed output."""
    from google.genai import types

    client = client or _client()
    response = client.models.generate_content(
        model=os.environ.get("MICHELIN_VISION_MODEL", MODEL),
        contents=[types.Part.from_bytes(data=image, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=SCHEMA,
        ),
    )
    body = json.loads(response.text)
    name = str(body.get("restaurant_name") or "").strip() or None
    return rows_to_dishes(body.get("dishes") or []), name
