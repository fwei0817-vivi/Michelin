"""Read dish names and prices from a menu photo with Gemini.

Gemini only transcribes what is printed: names (English and Chinese), prices, the printed
description, the menu's own marks (V, VP, GF, peppers) and choices ("Chicken | Beef +$2"),
which become one orderable dish per choice. It never guesses ingredients or diets; the AI
dish facts (plan/dish_facts.py) do that from the name, and every row still needs human
review before planning.

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

PROMPT = """Transcribe this restaurant menu photo into orderable dishes.

For every dish with a readable price, return its English name as printed, its Chinese name \
if printed, the price as a number (no currency sign), and the printed description (the \
ingredient line under the name). Copy what is printed; do not translate, guess ingredients, \
or add dishes that are not on the photo. Skip section headings, drinks and lines without a \
price. If nothing is readable, return an empty list.

Choices: when one line offers a choice of protein or version ("Kung Pao Chicken / Beef / \
Shrimp / Tofu", "Choice of Chicken | Beef +$2 | Shrimp +$4 | Tofu", "Sesame Chicken or \
Tofu"), return it ONCE with "choices": one entry per option, each with its own name as \
printed ("Chicken", "Beef", "Tofu"), its Chinese if printed (鸡, 牛, 豆腐), and its full \
price (the dish price plus any printed surcharge: $18 and "Beef +$2" is 20). Then "name_en" \
and "name_zh" are the dish name WITHOUT the options ("Kung Pao", "宫保"), and "description" \
leaves out the choice list. Sizes or piece counts are not choices. Read each dish's own \
choice line: surcharges differ between dishes, and an option with no printed surcharge \
costs the dish price even if another dish charges extra for it.

Marks: read the menu's legend (often at the bottom: e.g. a pepper = spicy, V = vegetarian, \
VG or a different V = vegan, VP = vegetarian possible, GF = gluten free, GP = gluten-free \
possible). For each dish return "marks" (what its printed symbols mean, using that legend) \
and "spicy": how many pepper/chili icons it has (0 if none). Return "legend" as printed.

Sections: give each dish "section", the menu heading it is printed under ("Cold \
Appetizers", "Dim Sum"), or "" if none.

Also return the restaurant's name as printed on the menu (usually at the top), or an empty \
string if no name is printed."""

PAGES = """

These {n} photos are pages of ONE menu. Read every page in order. A dish printed on two \
pages (or twice on one) is listed once. The legend may be on any page; apply it to all."""

MAX_PAGES = 8  # pages per menu
ONE_CALL_BYTES = 12 * 1024 * 1024  # all pages in one vision call up to this much image data

MARKS = ["vegetarian", "vegan", "vegetarian_possible", "gluten_free", "gluten_free_possible"]

SCHEMA = {
    "type": "object",
    "properties": {
        "restaurant_name": {"type": "string"},
        "legend": {"type": "string"},
        "dishes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_en": {"type": "string"},
                    "name_zh": {"type": "string"},
                    "price": {"type": "number"},
                    "description": {"type": "string"},
                    "marks": {"type": "array", "items": {"type": "string", "enum": MARKS}},
                    "spicy": {"type": "integer"},
                    "section": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name_en": {"type": "string"},
                                "name_zh": {"type": "string"},
                                "price": {"type": "number"},
                            },
                            "required": ["name_en"],
                        },
                    },
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


def _price(value) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= value <= 1000:
        return None
    return round(float(value), 2)


def _marks(row: dict) -> list[str]:
    marks = row.get("marks") if isinstance(row.get("marks"), list) else []
    return list(dict.fromkeys(m for m in marks if m in MARKS))


def _spicy(row: dict) -> int | None:
    n = row.get("spicy")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        return None
    return min(n, 3)


_SEP = re.compile(r"\s*[/|｜]\s*")
_CHOICE_LINE = re.compile(r"\bchoice of\b.*$", re.IGNORECASE | re.DOTALL)


def _base_zh(zh: str | None, options: list[str]) -> str | None:
    """'宫保鸡 / 牛 / 虾 / 豆腐' with options 鸡, 牛, 虾, 豆腐 -> '宫保': one option's Chinese
    never leaks into another version (the tofu version is not 宫保鸡)."""
    if not zh:
        return None
    split = _SEP.split(zh)
    base = split[0].strip()
    for option in sorted(options, key=len, reverse=True):
        if option and base.endswith(option) and base != option:
            return base[: -len(option)].strip() or None
    if len(split) > 1 or any(o and o in base for o in options):
        return None  # options we cannot separate: no Chinese name beats a wrong one
    return base or None


def _stem(name: str, options: list[str]) -> str:
    """'Sesame Chicken or Tofu' -> 'Sesame', 'Yu Xiang Pork' -> 'Yu Xiang' (options Pork,
    Chicken, ...): the tofu version must not be called 'Yu Xiang Pork (Tofu)', or its name
    would say pork (live run, Cafe Mandarin)."""
    words = sorted({re.escape(o) for o in options if o}, key=len, reverse=True)
    if not words:
        return name
    alt = "|".join(words)
    pattern = rf"\b(?:{alt})\b(?:\s*(?:\bor\b|/|,|&|\band\b)\s*\b(?:{alt})\b)*"
    stem = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    stem = re.sub(r"\s+", " ", stem).strip(" -/,&")
    stem = re.sub(r"\s+(?:or|and|with|w/)$", "", stem, flags=re.IGNORECASE).strip()
    return stem or name


_PROTEINS = ("chicken", "beef", "pork", "shrimp", "tofu", "lamb", "fish", "duck", "vegetable")
_OR_PAIR = re.compile(
    rf"^(.+?)\s+({'|'.join(_PROTEINS)})\s+or\s+({'|'.join(_PROTEINS)})$", re.IGNORECASE
)


def _fill_choices(name: str, price: float | None, choices: list[dict]) -> list[dict]:
    """What the printed name already says, kept even when the model's choice list slips
    (live 4-page Cafe Mandarin runs): 'Sesame Chicken or Tofu' is two versions at the dish
    price; 'Yu Xiang Pork' with a choice list keeps its pork version; and the protein in
    the name costs the printed price ('Mongolian Beef $18': beef is not +$2)."""
    if price is None:
        return choices
    if len(choices) < 2:
        pair = _OR_PAIR.match(name.strip())
        if pair:
            return [
                {"name_en": pair[2].title(), "price": price},
                {"name_en": pair[3].title(), "price": price},
            ]
        return choices
    named = [p for p in _PROTEINS if re.search(rf"\b{p}\b", name, re.IGNORECASE)]
    if len(named) != 1:
        return choices
    head = named[0]
    out = [dict(c) for c in choices]
    same = [c for c in out if _same(c.get("name_en")) == head]
    if not same:
        return [{"name_en": head.title(), "price": price}, *out]
    for c in same:
        cost = _price(c.get("price"))
        if cost is not None and cost > price:
            c["price"] = price
    return out


def _same(text) -> str:
    """'Classic Soup Dumplings (4)' and 'classic soup dumplings' are one printed dish."""
    ascii_text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    ascii_text = re.sub(r"\(\s*\d+\s*(?:pcs?|pieces?)?\s*\)", " ", ascii_text.lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


def _key(row: dict) -> tuple:
    choices = row.get("choices") if isinstance(row.get("choices"), list) else []
    options = tuple(sorted(_same(c.get("name_en")) for c in choices if isinstance(c, dict)))
    return (_same(row.get("name_en")), _price(row.get("price")), options)


def dedupe(rows: list) -> list[dict]:
    """A dish printed twice (on two pages, or read twice) is one dish; the copies' marks,
    peppers, section and description are kept together."""
    out: dict[tuple, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not _same(row.get("name_en")):
            continue
        key = _key(row)
        if key not in out:
            out[key] = dict(row)
            continue
        kept = out[key]
        kept["marks"] = list(dict.fromkeys([*(_marks(kept)), *(_marks(row))]))
        kept["spicy"] = max(_spicy(kept) or 0, _spicy(row) or 0)
        for k in ("name_zh", "description", "section"):
            if not str(kept.get(k) or "").strip() and str(row.get(k) or "").strip():
                kept[k] = row[k]
    return list(out.values())


def rows_to_dishes(rows: list[dict]) -> list[Dish]:
    """The model's rows as orderable dishes. A line with choices becomes one dish per choice
    ("Kung Pao (Tofu)", its own price), grouped by family_id so the app shows them as one
    dish and the planner picks a version. Printed marks and peppers are kept as printed."""
    taken: set[str] = set()
    families: set[str] = set()
    dishes = []
    for row in dedupe(rows):  # the API keeps the first MAX_DISHES and says how many it dropped
        name = str(row.get("name_en") or "").strip()
        price = _price(row.get("price"))
        zh = str(row.get("name_zh") or "").strip() or None
        desc = str(row.get("description") or "").strip()
        marks, spicy = _marks(row), _spicy(row)
        section = str(row.get("section") or "").strip()[:60] or None
        choices = [
            c
            for c in (row.get("choices") if isinstance(row.get("choices"), list) else [])
            if isinstance(c, dict) and str(c.get("name_en") or "").strip()
        ]
        if not name:
            continue
        choices = _fill_choices(name, price, choices)
        if len(choices) < 2:
            if price is None:
                continue
            dishes.append(
                Dish(
                    id=slug(name, taken),
                    name_en=name,
                    name_zh=zh,
                    price=price,
                    description_raw=" ".join(x for x in (zh, name, desc) if x),
                    menu_marks=marks,
                    menu_spice=spicy,
                    menu_section=section,
                    confirm_with_staff=[
                        f"Confirm ingredients, allergens, and preparation for {name}."
                    ],
                )
            )
            continue
        family = slug(name, families)
        stem = _stem(name, [str(c["name_en"]).strip() for c in choices])
        base_zh = _base_zh(zh, [str(c.get("name_zh") or "").strip() for c in choices])
        desc = _CHOICE_LINE.sub("", desc).strip(" |,;")
        for c in choices:
            option = str(c["name_en"]).strip()
            option_zh = str(c.get("name_zh") or "").strip() or None
            cost = _price(c.get("price"))
            if cost is not None and price is not None and cost < price / 2:
                cost = round(price + cost, 2)  # the model gave the surcharge ("+$2"), not the price
            cost = cost if cost is not None else price
            if cost is None:
                continue
            label = f"{stem} ({option})"
            label_zh = (
                f"{base_zh}（{option_zh}）"
                if base_zh and option_zh and option_zh not in base_zh
                else base_zh or option_zh
            )
            dishes.append(
                Dish(
                    id=slug(label, taken),
                    name_en=label,
                    name_zh=label_zh,
                    price=cost,
                    description_raw=" ".join(x for x in (label_zh, label, desc) if x),
                    family_id=family,
                    family_name=name,
                    variant=option,
                    menu_marks=marks,
                    menu_spice=spicy,
                    menu_section=section,
                    confirm_with_staff=[
                        f"Confirm ingredients, allergens, and preparation for {label}."
                    ],
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


def read_menu_photo(
    image: bytes, mime: str, client=None
) -> tuple[list[Dish], str | None, str, str]:
    """(dishes, restaurant name if printed, model used, printed legend). Raises
    gemini.RateLimited on 429, and other errors on transport or malformed output."""
    return read_menu_pages([(image, mime)], client)


def _ask(pages: list[tuple[bytes, str]], client=None) -> tuple[dict, str]:
    prompt = PROMPT + (PAGES.format(n=len(pages)) if len(pages) > 1 else "")
    (first, mime), more = pages[0], pages[1:]
    turn = llm.Turn("user", prompt, first, mime, more=list(more))
    text, used = llm.generate_json("vision", turns=[turn], schema=SCHEMA, client=client)
    body = json.loads(text)
    return (body if isinstance(body, dict) else {}), used


def read_menu_pages(
    pages: list[tuple[bytes, str]], client=None
) -> tuple[list[Dish], str | None, str, str]:
    """Several photos (or PDF pages) of one menu, merged into one menu: one vision call when
    the pages fit together, else one call per page; dishes printed twice are kept once."""
    pages = pages[:MAX_PAGES]
    if sum(len(p) for p, _ in pages) <= ONE_CALL_BYTES:
        batches = [pages]
    else:
        batches = [[p] for p in pages]
    rows: list = []
    names, legends, used = [], [], ""
    for batch in batches:
        body, used = _ask(batch, client)
        rows += body.get("dishes") or []
        names.append(str(body.get("restaurant_name") or "").strip())
        legends.append(str(body.get("legend") or "").strip())
    name = nice_name(next((n for n in names if n), "")) or None
    legend = " ".join(dict.fromkeys(x for x in legends if x))[:300]
    return rows_to_dishes(rows), name, used, legend
