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

import hashlib
import json
import logging
import os
import re
import unicodedata
from pathlib import Path

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
Tofu", "Boiled Beef / Fish $24 / $28"), return it ONCE. Copy the choice line exactly as \
printed, surcharges included, into "choice_text" ("Choice of Pork | Chicken | Beef +$2 | \
Shrimp +$4 | Tofu"), and the printed price exactly as shown into "price_text" ("$18", or \
"$24 / $28"). Then "choices": one entry per option in printed order, each with its own name \
as printed ("Chicken", "Beef", "Tofu"), its Chinese if printed (鸡, 牛, 豆腐), and \
"upcharge": the surcharge printed right next to THAT option ("+$2"), or "" if that option \
has none. Do not add up prices; the app does. "price" is the dish's base price. \
"name_en" and "name_zh" are the dish name WITHOUT the options ("Kung Pao", "宫保"), and \
"description" leaves out the choice list. Sizes or piece counts are not choices.

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
                    "price_text": {"type": "string"},
                    "choice_text": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name_en": {"type": "string"},
                                "name_zh": {"type": "string"},
                                "upcharge": {"type": "string"},
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
    proteins = [c for c in out if _same(c.get("name_en")) in _PROTEINS]
    if not same and len(proteins) * 2 > len(out):  # a protein choice, not cooking styles
        return [{"name_en": head.title(), "price": price}, *out]
    for c in same:
        cost = _price(c.get("price"))
        if cost is not None and cost > price:
            c["price"] = price
    return out


_MONEY = re.compile(r"\$?\s*(\d+(?:\.\d{1,2})?)")
_UP = re.compile(r"\+\s*\$?\s*(\d+(?:\.\d{1,2})?)")
_ZH_OPTION = {
    "牛": "Beef",
    "鱼": "Fish",
    "鸡": "Chicken",
    "虾": "Shrimp",
    "猪": "Pork",
    "肉": "Pork",
    "豆腐": "Tofu",
    "羊": "Lamb",
    "鸭": "Duck",
    "蔬菜": "Vegetable",
}


def _up(text) -> float | None:
    """'+$2' -> 2.0; '' -> 0.0; anything else -> None (not a surcharge we can read)."""
    t = str(text or "").strip()
    if not t:
        return 0.0
    m = _UP.fullmatch(t) or _UP.search(t)
    return float(m[1]) if m else None


def _choice_line(text: str) -> list[tuple[str, float]]:
    """'Choice of Pork | Chicken | Beef +$2 | Shrimp +$4 | Tofu' -> [(Pork, 0), (Chicken, 0),
    (Beef, 2), (Shrimp, 4), (Tofu, 0)]: each surcharge stays with the option it is printed
    next to. Chinese-only parts are skipped; fewer than two options means no choice line."""
    t = re.sub(r"^.*?\bchoice of\b[:\s]*", "", str(text or ""), flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"\bw/\s*", "with ", t, flags=re.IGNORECASE)  # "Steamed w/ Ginger" is one option
    out = []
    for part in re.split(r"\s*[|｜/,]\s*|\s+or\s+", t):
        m = re.fullmatch(r"\s*([A-Za-z][A-Za-z '&.-]*?)\s*(\+\s*\$?\s*\d+(?:\.\d{1,2})?)?\s*", part)
        if m:
            out.append((m[1].strip(), _up(m[2]) or 0.0))
    return out if len(out) >= 2 else []


def _with(text) -> str:
    return re.sub(r"\bw/\s*", "with ", str(text or ""), flags=re.IGNORECASE)


_DANGLING = re.compile(r"\s+(?:w|with|and|or|&|in)\s*/?\s*$", re.IGNORECASE)


def clean_choices(choices: list[dict]) -> list[dict]:
    """A choice cut at "w/" ("Steamed w" + "Ginger Scallion", QA r8 MO-1) is joined back to
    the option it belongs to, and a repeated option is kept once."""
    out: list[dict] = []
    pending: dict | None = None
    for c in choices:
        c = dict(c)
        name = str(c.get("name_en") or "").strip()
        if pending is not None:
            c["name_en"] = f"{_DANGLING.sub('', str(pending['name_en']))} with {name}"
            pending = None
            name = c["name_en"]
        if _DANGLING.search(name):
            pending = c
            continue
        if any(_same(o.get("name_en")) == _same(name) for o in out):
            continue
        out.append(c)
    return out


def _priced_choices(row: dict, name: str, price: float | None, choices: list[dict]) -> list[dict]:
    """Every version's price computed here, as base price + that option's own printed
    surcharge. The printed choice line (choice_text, or a 'Choice of' line in the
    description) wins over the model's per-option numbers, so a surcharge array shifted onto
    the wrong options ('Pork 18, Chicken 20, Beef 22, Shrimp 18' for 'Beef +$2 | Shrimp +$4')
    is repaired. 'Beef / Fish $24 / $28' pairs names and prices in order."""
    prices = [
        float(x)
        for x in _MONEY.findall(str(row.get("price_text") or ""))
        if "$" in str(row.get("price_text") or "")
    ]
    if len(prices) >= 2:  # paired prices: one per option, in printed order
        opts = [str(c.get("name_en") or "").strip() for c in choices]
        if len(opts) != len(prices):
            zh = str(row.get("name_zh") or "")
            parts = [p.strip() for p in _SEP.split(zh)]
            if len(parts) == len(prices):
                opts = []
                for p in parts:
                    hit = next(
                        (
                            v
                            for k, v in sorted(_ZH_OPTION.items(), key=lambda kv: -len(kv[0]))
                            if p.endswith(k)
                        ),
                        None,
                    )
                    opts.append(hit or "")
        if len(opts) == len(prices) and all(opts):
            return [
                {
                    "name_en": o,
                    "price": p,
                    **(
                        {"name_zh": c.get("name_zh")}
                        if (
                            c := next(
                                (c for c in choices if _same(c.get("name_en")) == _same(o)), None
                            )
                        )
                        else {}
                    ),
                }
                for o, p in zip(opts, prices)
            ]
    if price is None:
        return choices
    line = _choice_line(row.get("choice_text") or "")
    if not line:
        m = _CHOICE_LINE.search(str(row.get("description") or ""))
        # A choice line wrapped onto the next line ("Choice of Steamed\nw/ Ginger ...").
        text = re.sub(r"\n\s*(?=w/|[a-z/|])", " ", m[0]) if m else ""
        line = _choice_line(text.split("\n")[0]) if m else []
    if line:
        printed = {_same(n): up for n, up in line}
        names = {_same(_with(c.get("name_en"))) for c in choices}
        whole = " ".join(printed)
        # The printed line wins when every model option is (part of) a printed one: a split
        # "Steamed" + "Ginger Scallion" is the printed "Steamed w/ Ginger Scallion" (QA r8).
        if not choices or names <= set(printed) or all(n and n in whole for n in names):
            zh = {_same(_with(c.get("name_en"))): c.get("name_zh") for c in choices}
            return [
                {"name_en": n, "name_zh": zh.get(_same(n)), "price": round(price + up, 2)}
                for n, up in line
            ]
    out = []
    for c in choices:
        c = dict(c)
        up = _up(c["upcharge"]) if "upcharge" in c else None
        if up is not None:
            c["price"] = round(price + up, 2)
        out.append(c)
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
        choices = clean_choices(choices)
        choices = clean_choices(_priced_choices(row, name, price, choices))
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
    image: bytes, mime: str, client=None, key: str | None = None
) -> tuple[list[Dish], str | None, str, str]:
    """(dishes, restaurant name if printed, model used, printed legend). Raises
    gemini.RateLimited on 429, and other errors on transport or malformed output."""
    return read_menu_pages([(image, mime)], client, key)


def _ask(pages: list[tuple[bytes, str]], client=None) -> tuple[dict, str]:
    prompt = PROMPT + (PAGES.format(n=len(pages)) if len(pages) > 1 else "")
    (first, mime), more = pages[0], pages[1:]
    turn = llm.Turn("user", prompt, first, mime, more=list(more))
    text, used = llm.generate_json(
        "vision", turns=[turn], schema=SCHEMA, client=client, temperature=0
    )
    body = json.loads(text)
    return (body if isinstance(body, dict) else {}), used


# The model's raw read of an upload, cached by the file contents (QA r9 MU-1: two reads of
# one PDF differed). Bump READ_VERSION when the reading prompt or schema changes; the
# prompt text is hashed into the key too, so an edit can never serve a stale read.
READ_VERSION = "1"
READ_CACHE = Path(
    os.environ.get("MICHELIN_READ_CACHE", Path(__file__).resolve().parents[3] / "data/menu_reads")
)


def read_key(files: list[bytes]) -> str:
    """The uploaded files' ordered content hashes plus the reading prompt's version."""
    prompt = hashlib.sha256(
        (PROMPT + PAGES + json.dumps(SCHEMA, sort_keys=True)).encode()
    ).hexdigest()[:12]
    hashes = [hashlib.sha256(f).hexdigest() for f in files]
    return hashlib.sha256(f"{READ_VERSION}|{prompt}|{'|'.join(hashes)}".encode()).hexdigest()[:32]


def cached_read(key: str) -> dict | None:
    try:
        raw = json.loads((READ_CACHE / f"{key}.json").read_text())
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) and isinstance(raw.get("rows"), list) else None


def _save_read(key: str, read: dict) -> None:
    try:
        READ_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = READ_CACHE / f"{key}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(read, ensure_ascii=False, indent=1))
        tmp.replace(READ_CACHE / f"{key}.json")
    except OSError:
        logging.getLogger("michelin").warning("Could not save the menu read", exc_info=True)


def read_menu_pages(
    pages: list[tuple[bytes, str]], client=None, key: str | None = None
) -> tuple[list[Dish], str | None, str, str]:
    """Several photos (or PDF pages) of one menu, merged into one menu: one vision call when
    the pages fit together, else one call per page; dishes printed twice are kept once.
    With a `key` (see read_key) the same upload is read once and then served from cache."""
    hit = cached_read(key) if key else None
    if hit is not None:
        name = nice_name(str(hit.get("restaurant_name") or "")) or None
        return (
            rows_to_dishes(hit["rows"]),
            name,
            f"{hit.get('model', '')} (cached)",
            hit.get("legend", ""),
        )
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
    if key and rows:
        _save_read(
            key,
            {
                "rows": rows,
                "restaurant_name": name or "",
                "legend": legend,
                "model": used,
                "version": READ_VERSION,
            },
        )
    return rows_to_dishes(rows), name, used, legend
