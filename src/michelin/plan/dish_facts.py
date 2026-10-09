"""Dish facts come from the AI, not from a rule base.

A menu keeps only each dish's name, price and category (category tells rice from shared
dishes). Before anything checks a diner against a dish, `prepare` strips every other field
and asks the planner's model, once per menu, what each dish is usually made of: likely and
possible ingredients, the nine allergens, pork/beef, vegetarian/vegan, heat. Answers are
cached by dish name (data/facts/dish_facts.json), so a menu costs one call the first time
and none after.

The code still enforces the rules on top of these facts (plan/edibility.py):
- an allergen the AI calls likely or possible keeps an allergic diner off the dish
  (allergies are strict; "possible" is still a risk);
- a dish the AI calls vegetarian/no-pork/no-beef only "if the kitchen skips X" stays
  allowed for that diet, and X becomes a server question;
- anything the AI did not answer stays unknown, which no diner with that allergy or diet
  can eat (conservative).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from pathlib import Path

from michelin import llm
from michelin.schemas import (
    Allergen,
    AllergenFlag,
    Dish,
    DishCategory,
    EvidenceTier,
    IngredientClaim,
    Menu,
)

log = logging.getLogger("michelin")
ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = Path(os.environ.get("MICHELIN_FACTS_CACHE", ROOT / "data/facts/dish_facts.json"))
VERSION = "5"
ALLERGENS = [a.value for a in Allergen]
MAX_DISHES = 40

SYSTEM = """You are a careful kitchen expert for restaurants in the US (mostly Chinese).
For each dish you get only its name (English and/or Chinese) and menu category. Say what
the dish is usually made of in a typical US restaurant kitchen, erring on the side of
caution: people with allergies rely on this.

For every dish return:
- "ingredients": the main ingredients and the hidden ones that matter for allergies and
  diets (sauces, stocks, fats, noodles, garnishes), each with "certainty": "likely" (most
  kitchens use it) or "possible" (some kitchens do: e.g. lard in scallion pancakes, chicken
  stock in vegetable dishes, oyster sauce in stir-fries, egg in noodles, fish sauce).
- "allergens": every one of peanut, tree_nut, shellfish, fish, egg, dairy, soy, wheat,
  sesame that the dish likely or possibly contains, with "certainty" and a short "why"
  (e.g. "soy sauce", "peanut sauce", "egg noodles"). Leave out allergens it does not
  contain. Soy sauce means soy and wheat. Oyster sauce means shellfish. When unsure, list it
  as "possible".
- "pork", "beef": "yes" (in the dish as named or almost always), "possible" (some kitchens
  add it, e.g. minced pork in eggplant, lard), or "no".
- "vegetarian", "vegan": "yes", "possible" (only if the kitchen skips a meat stock, lard,
  fish or oyster sauce, egg or dairy that some kitchens use; name it in ingredients as
  "possible"), or "no".
- "spice": 0 none, 1 mild, 2 medium, 3 hot.
- "category": the menu section it belongs to; keep the given category unless it is
  "other". "staple" means plain steamed rice served per person ONLY; noodles, pancakes,
  dumplings and fried rice are shared dishes, never "staple".
Allergen rule: if any common recipe variant of the dish contains an allergen (as an
ingredient, a sauce or paste, or a garnish), mark it at least "possible". Refined frying
oil and a shared fryer are not ingredients: do not flag peanut or shellfish for them alone.
Be conservative. A wrong "no" can send someone to hospital; a wrong "possible" only adds a
question for the server. If a well-known version of the dish sometimes has it, say
"possible". Every possible ingredient that is an allergen makes that allergen possible too
(oyster sauce -> shellfish, fish sauce -> fish, egg noodles -> egg). Examples: dan dan
noodles and cold noodles: peanut possible; Chungking/Chongqing spicy chicken, three pepper
chicken, kung pao, chili-oil wontons: peanut possible (or likely); a dish that is merely
spicy or "Szechuan style" is not a peanut risk by itself; smashed cucumber: peanut and sesame possible; Sichuan dry-fried string beans: minced pork
likely; garlic eggplant and plain sauteed string beans: minced pork possible; dumplings and
wontons: pork likely unless named otherwise; shrimp dumplings: pork fat possible; vegetable
stir-fries: chicken stock and oyster sauce possible; mouth-watering chicken, bang bang
chicken and strange-flavour dishes: peanut and sesame possible; scallion pancakes: lard
possible, no peanut or shellfish; fried rice: egg likely, shellfish only if named.
Answer for every dish id given, in the same order. Do not invent dishes."""


def bare(menu: Menu) -> Menu:
    """The menu as the user sees it printed: name, price and category, nothing inferred."""
    keep = ("id", "name_zh", "name_en", "price", "category")
    return menu.model_copy(
        update={"dishes": [Dish(**{k: getattr(d, k) for k in keep}) for d in menu.dishes]}
    )


def norm(name: str | None) -> str:
    """'Crystal Shrimp Dumplings (4)' and 'crystal shrimp dumplings (5 pcs)' are one dish."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(
        r"\((?:\d+\s*(?:pcs?|pieces?)?|\w*\s*pcs?)\)|\b\d+\s*(?:pcs?|pieces?)\b", " ", text
    )
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    # "Scallion Pancakes" and "Scallion Pancake" are one dish.
    return " ".join(
        w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
        for w in text.split()
    )


def _key(dish: Dish) -> str:
    """One fact entry per dish name, whatever the menu or category: the same name never gets
    different facts. English name if any, else the Chinese name."""
    return _name_key(_label(dish))


def _label(dish: Dish) -> str:
    return dish.name_en if norm(dish.name_en) else (dish.name_zh or dish.name_en or dish.id)


def _name_key(name: str) -> str:
    text = norm(name) or (name or "").strip()
    return hashlib.sha256(f"{VERSION}|{text}".encode()).hexdigest()[:24]


_RANK = {"no": 0, "possible": 1, "yes": 2}


def merge(old: dict | None, new: dict | None) -> dict | None:
    """Union of two answers for one dish, never less cautious than either: an allergen or
    ingredient once possible stays at least possible; pork/beef take the riskier answer;
    vegetarian/vegan the less certain one; heat the higher."""
    if not old or not new:
        return old or new
    out = dict(old)
    for key, label in (("allergens", "allergen"), ("ingredients", "name")):
        seen = {}
        for row in [*old.get(key, []), *new.get(key, [])]:
            k = str(row[label]).lower()
            if k not in seen or (row["certainty"] == "likely" and seen[k]["certainty"] != "likely"):
                seen[k] = row
        out[key] = list(seen.values())
    for k in ("pork", "beef"):
        vals = [v for v in (old.get(k), new.get(k)) if v in _RANK]
        out[k] = max(vals, key=_RANK.get) if vals else None
    for k in ("vegetarian", "vegan"):
        vals = [v for v in (old.get(k), new.get(k)) if v in _RANK]
        out[k] = min(vals, key=_RANK.get) if vals else None
    spices = [v for v in (old.get("spice"), new.get("spice")) if isinstance(v, int)]
    out["spice"] = max(spices) if spices else None
    out["category"] = old.get("category") or new.get("category")
    return out


# A conservative floor in code, on top of the AI: names that commonly hide an allergen or
# meat. Matches only ADD "possible" risks (union); they never remove anything.
_FLOOR: list[tuple[str, dict]] = [
    # Peanut: only dish families that really use it (QA r5: not every spicy or 辣 name).
    (
        (
            r"kung ?pao|gong ?bao|宫保|dan ?dan|担担|satay|peanut|花生|怪味|"
            r"(?:chungking|chongqing)\b[^,;]*\bchicken|重庆[^,;]*鸡|辣子鸡|three pepper|"
            r"smashed cucumber|拍黄瓜|spicy wontons?|wontons? in (?:hot |red |chil+i )*oil|"
            r"红油抄手|口水鸡|棒棒鸡|bang ?bang chicken|mouth[- ]watering chicken"
        ),
        {"allergens": ["peanut"]},
    ),
    # Sesame: sesame paste or oil is part of the dish.
    (
        r"dan ?dan|担担|smashed cucumber|拍黄瓜|口水鸡|棒棒鸡|怪味|bang ?bang|sesame|芝麻|麻酱",
        {"allergens": ["sesame"]},
    ),
    (r"cashew|walnut|almond|pecan|pistachio|腰果|核桃", {"allergens": ["tree_nut"]}),
    (
        (
            r"dumpling|wonton|won ton|\bbao\b|\bbuns?\b|potsticker|xiao ?long|shu ?mai|siu ?mai|"
            r"spring roll|egg roll|dan ?dan|fried rice|lo ?mein|chow ?mein|string bean|green bean|"
            r"eggplant|ma ?po|cabbage|dry[ -]?pot|scallion pancake|chive pancake|hot and sour soup|"
            r"饺|馄饨|包|抄手|麻婆|酸辣汤"
        ),
        {"pork": "possible"},
    ),
    (r"seafood|\bxo\b|oyster|海鲜", {"allergens": ["shellfish"]}),
    (r"fish[ -]?fragrant|yu[ -]?xiang|鱼香", {"allergens": ["fish"], "pork": "possible"}),
    (
        r"noodle|lo ?mein|chow ?mein|fried rice|dumpling|wonton|pancake|batter|tempura|面|饺",
        {"allergens": ["egg"]},
    ),
]


def floor(dish: Dish) -> dict:
    """The code's own conservative "possible" risks for this dish name."""
    text = f"{dish.name_en or ''} {dish.name_zh or ''}".lower()
    allergens: dict[str, str] = {}
    pork = None
    for pattern, adds in _FLOOR:
        if re.search(pattern, text):
            for a in adds.get("allergens", []):
                allergens[a] = "commonly hidden in dishes like this"
            pork = adds.get("pork", pork)
    out: dict = {
        "allergens": [
            {"allergen": a, "certainty": "possible", "why": w} for a, w in allergens.items()
        ],
        "ingredients": [],
    }
    if pork:
        out["pork"] = "possible"
        out["ingredients"].append({"name": "pork", "certainty": "possible"})
    return out


def _load() -> dict:
    """The cache, keyed by normalized dish name. Entries from older keys (which included the
    category, so one name could hold two answers) are folded together by union."""
    try:
        raw = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return {}
    out: dict = {}
    for entry in raw.values():
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        key = _name_key(entry["name"])
        merged = merge(out.get(key), {k: v for k, v in entry.items() if k != "name"})
        out[key] = {"name": entry["name"] if key not in out else out[key]["name"], **merged}
    return out


def _save(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
        tmp.replace(CACHE_PATH)
    except OSError:
        log.warning("Could not write the dish facts cache", exc_info=True)


def _schema(ids: list[str]) -> dict:
    certain = {"type": "string", "enum": ["likely", "possible"]}
    three = {"type": "string", "enum": ["yes", "possible", "no"]}
    return {
        "type": "object",
        "properties": {
            "dishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ids},
                        "ingredients": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}, "certainty": certain},
                                "required": ["name", "certainty"],
                            },
                        },
                        "allergens": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "allergen": {"type": "string", "enum": ALLERGENS},
                                    "certainty": certain,
                                    "why": {"type": "string"},
                                },
                                "required": ["allergen", "certainty", "why"],
                            },
                        },
                        "pork": three,
                        "beef": three,
                        "vegetarian": three,
                        "vegan": three,
                        "spice": {"type": "integer", "minimum": 0, "maximum": 3},
                        "category": {"type": "string", "enum": [c.value for c in DishCategory]},
                    },
                    "required": [
                        "id",
                        "ingredients",
                        "allergens",
                        "pork",
                        "beef",
                        "vegetarian",
                        "vegan",
                        "spice",
                    ],
                },
            }
        },
        "required": ["dishes"],
    }


def _ask(dishes: list[Dish], client=None) -> tuple[str, str]:
    """One model call -> (JSON text, model used). Tests replace this with a fake."""
    rows = [
        {"id": d.id, "name": d.name_en, "name_zh": d.name_zh, "category": d.category.value}
        for d in dishes
    ]
    turns = [llm.Turn("user", "Dishes:\n" + json.dumps(rows, ensure_ascii=False))]
    schema = _schema([d.id for d in dishes])
    return llm.generate_json(
        "plan", system=SYSTEM, turns=turns, schema=schema, client=client, temperature=0
    )


def _clean(row: dict) -> dict | None:
    """Keep only well-formed answers; anything malformed is dropped (stays unknown)."""
    three = {"yes", "possible", "no"}
    try:
        facts = {
            "ingredients": [
                {"name": str(i["name"]).strip()[:60], "certainty": i["certainty"]}
                for i in row.get("ingredients", [])
                if str(i.get("name", "")).strip() and i.get("certainty") in ("likely", "possible")
            ][:12],
            "allergens": [
                {
                    "allergen": a["allergen"],
                    "certainty": a["certainty"],
                    "why": str(a.get("why") or "")[:80],
                }
                for a in row.get("allergens", [])
                if a.get("allergen") in ALLERGENS and a.get("certainty") in ("likely", "possible")
            ],
            **{k: row[k] for k in ("pork", "beef", "vegetarian", "vegan") if row.get(k) in three},
            "spice": int(row["spice"]) if str(row.get("spice", "")).isdigit() else None,
            "category": row.get("category")
            if row.get("category") in {c.value for c in DishCategory}
            else None,
        }
    except (TypeError, KeyError, ValueError):
        return None
    if facts["spice"] is not None and not 0 <= facts["spice"] <= 3:
        facts["spice"] = None
    return facts


_PLAIN_RICE = re.compile(
    r"^\s*(?:steamed |white |brown |jasmine |plain )*rice(?: \(.*\))?\s*$|米饭|白饭", re.IGNORECASE
)


def _category(dish: Dish, ai: str | None) -> DishCategory:
    """The printed category wins; the AI only fills in "other". It may call a dish a
    per-person "staple" only if it is plain rice (QA r5: not Scallion Pancake or Dan Dan)."""
    if dish.category != DishCategory.OTHER or not ai:
        return dish.category
    if ai == DishCategory.STAPLE.value:
        name = f"{dish.name_en or ''}".strip() or ""
        if not (_PLAIN_RICE.search(name) or _PLAIN_RICE.search(dish.name_zh or "")):
            return DishCategory.OTHER
    return DishCategory(ai)


def apply(dish: Dish, facts: dict | None) -> Dish:
    """A bare dish plus the AI's facts (unioned with the code's floor), in the fields the
    rules read. Without AI facts the floor alone is not enough to clear anything: diets and
    the allergens it does not mention stay unknown."""
    base = floor(dish)
    if not facts:
        flags = [
            AllergenFlag(
                allergen=Allergen(a["allergen"]),
                tier=EvidenceTier.UNKNOWN,
                confidence=0.4,
                reason=f"may contain {a['allergen'].replace('_', ' ')} ({a['why']})",
            )
            for a in base["allergens"]
        ]
        return dish.model_copy(update={"allergens": flags})
    facts = _floor_merge(facts, base)
    label = dish.name_en or dish.name_zh or dish.id
    tier = {"likely": EvidenceTier.INFERRED, "possible": EvidenceTier.UNKNOWN}
    ingredients = [
        IngredientClaim(name=i["name"], tier=tier[i["certainty"]], note="AI, from the dish name")
        for i in facts.get("ingredients", [])
    ]
    flags, seen = [], set()
    for a in facts.get("allergens", []):
        if a["allergen"] in seen:
            continue
        seen.add(a["allergen"])
        likely = a["certainty"] == "likely"
        flags.append(
            AllergenFlag(
                allergen=Allergen(a["allergen"]),
                tier=tier[a["certainty"]],
                confidence=0.8 if likely else 0.4,
                reason=f"{'usually' if likely else 'may'} contain {a['allergen'].replace('_', ' ')}"
                + (f" ({a['why']})" if a.get("why") else ""),
            )
        )
    pork, beef = facts.get("pork"), facts.get("beef")
    veg, vegan = facts.get("vegetarian"), facts.get("vegan")
    meat = "yes" in (pork, beef)
    is_veg = None if veg is None else (veg in ("yes", "possible") and not meat)
    is_vegan = None if vegan is None else (vegan in ("yes", "possible") and is_veg is True)
    # A "possible" diet risk becomes a server question about the ingredient the AI named.
    # Only ingredients that can touch an allergy or diet ("bamboo shoots" asks nothing).
    questions = [
        f"{label}: ask whether it uses {i['name']}."
        for i in facts.get("ingredients", [])
        if i["certainty"] == "possible" and _sensitive(i["name"])
    ]
    for word, value in (("pork", pork), ("beef", beef)):
        if value == "possible" and not any(word in q.lower() for q in questions):
            questions.append(f"{label}: ask whether it uses {word}.")
    return dish.model_copy(
        update={
            "main_ingredients": ingredients,
            "allergens": flags,
            # The AI was asked about all nine allergens: the ones it left out are reviewed.
            "reviewed_allergens": [a for a in Allergen if a.value not in seen],
            "contains_pork": None if pork is None else pork == "yes",
            "contains_beef": None if beef is None else beef == "yes",
            "is_vegetarian": is_veg,
            "is_vegan": is_vegan,
            "spice_level": facts.get("spice"),
            "confirm_with_staff": list(dict.fromkeys(questions))[:6],
            # The printed category wins; the AI only fills in "other" (e.g. imported rice).
            "category": _category(dish, facts.get("category")),
        }
    )


def _sensitive(name: str) -> bool:
    """Whether an ingredient can matter to any allergy or diet."""
    from michelin.plan.edibility import _SYNONYMS

    words = {w for ws in _SYNONYMS.values() for w in ws} | {
        "noodle",
        "stock",
        "broth",
        "gelatin",
    }
    low = name.lower()
    return any(w in low for w in words)


def _floor_merge(facts: dict, base: dict) -> dict:
    """Union the floor into the AI's facts: never removes, only adds "possible"."""
    if any(
        re.search(r"pork|lard|bacon|ham\b", i["name"], re.IGNORECASE)
        for i in facts.get("ingredients", [])
    ):
        base = {**base, "ingredients": []}  # the AI already names the pork; don't repeat it
    out = merge(
        facts,
        {
            **base,
            "pork": base.get("pork") or facts.get("pork"),
            "beef": facts.get("beef"),
            "vegetarian": facts.get("vegetarian"),
            "vegan": facts.get("vegan"),
            "spice": facts.get("spice"),
        },
    )
    if base.get("pork") and out.get("vegetarian") == "yes":
        out["vegetarian"] = "possible"  # vegetarian if the kitchen skips the pork: ask
    if base.get("pork") and out.get("vegan") == "yes":
        out["vegan"] = "possible"
    return out


def prepare(menu: Menu, client=None) -> Menu:
    """The menu stripped to name/price/category, then annotated with the AI's facts.
    Dishes the AI has not answered for stay unknown (nobody with a restriction can eat them)."""
    plain = bare(menu)
    cache = _load()
    missing = [d for d in plain.dishes if _key(d) not in cache]
    if not missing or (llm.provider() is None and client is None):
        missing = []
    for start in range(0, min(len(missing), 3 * MAX_DISHES), MAX_DISHES):
        batch = missing[start : start + MAX_DISHES]
        try:
            text, used = _ask(batch, client)
            answer = json.loads(text or "{}")
            ids = {d.id: d for d in batch}
            for row in answer.get("dishes", []):
                dish = ids.get(row.get("id")) if isinstance(row, dict) else None
                facts = _clean(row) if dish else None
                if facts:
                    key = _key(dish)
                    old = cache.get(key)
                    # Union with any earlier answer: once possible, stays possible.
                    cache[key] = {"name": _label(dish), **merge(old, facts)}
            _save(cache)
            log.info("Dish facts for %d dishes from %s", len(batch), used)
        except Exception as exc:  # noqa: BLE001 - facts stay unknown; the rules stay strict
            log.warning("Dish facts failed: %s: %s", type(exc).__name__, str(exc)[:300])
            break
    return plain.model_copy(update={"dishes": [apply(d, cache.get(_key(d))) for d in plain.dishes]})


def known(menu: Menu) -> bool:
    """Whether every dish has AI facts (cached)."""
    found, total = coverage(menu)
    return found == total


def coverage(menu: Menu) -> tuple[int, int]:
    """How many of the menu's dishes have AI facts (cached), of how many."""
    cache = _load()
    dishes = bare(menu).dishes
    return sum(_key(d) in cache for d in dishes), len(dishes)
