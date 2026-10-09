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
VERSION = "3"
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
  (e.g. "soy sauce", "fried in peanut oil", "egg noodles"). Leave out allergens it does not
  contain. Soy sauce means soy and wheat. Oyster sauce means shellfish. When unsure, list it
  as "possible".
- "pork", "beef": "yes" (in the dish as named or almost always), "possible" (some kitchens
  add it, e.g. minced pork in eggplant, lard), or "no".
- "vegetarian", "vegan": "yes", "possible" (only if the kitchen skips a meat stock, lard,
  fish or oyster sauce, egg or dairy that some kitchens use; name it in ingredients as
  "possible"), or "no".
- "spice": 0 none, 1 mild, 2 medium, 3 hot.
- "category": the menu section it belongs to ("staple" is plain rice, noodles or buns
  served per person); keep the given category unless it is "other".
Be conservative. A wrong "no" can send someone to hospital; a wrong "possible" only adds a
question for the server. If a well-known version of the dish sometimes has it, say
"possible". Every possible ingredient that is an allergen makes that allergen possible too
(oyster sauce -> shellfish, fish sauce -> fish, egg noodles -> egg). Examples: dan dan
noodles and cold noodles: peanut possible; Sichuan dry-fried string beans: minced pork
likely; garlic eggplant and plain sauteed string beans: minced pork possible; dumplings and
wontons: pork likely unless named otherwise; shrimp dumplings: pork fat possible; vegetable
stir-fries: chicken stock and oyster sauce possible; Sichuan cold dishes: peanut and sesame
possible; anything deep-fried: shared fryer with shrimp possible.
Answer for every dish id given, in the same order. Do not invent dishes."""


def bare(menu: Menu) -> Menu:
    """The menu as the user sees it printed: name, price and category, nothing inferred."""
    keep = ("id", "name_zh", "name_en", "price", "category")
    return menu.model_copy(
        update={"dishes": [Dish(**{k: getattr(d, k) for k in keep}) for d in menu.dishes]}
    )


def _key(dish: Dish) -> str:
    text = "|".join([VERSION, (dish.name_en or "").strip().lower(), (dish.name_zh or "").strip()])
    return hashlib.sha256(f"{text}|{dish.category.value}".encode()).hexdigest()[:24]


def _load() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return {}


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
    return llm.generate_json("plan", system=SYSTEM, turns=turns, schema=schema, client=client)


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


def apply(dish: Dish, facts: dict | None) -> Dish:
    """A bare dish plus the AI's facts, in the fields the rules read."""
    if not facts:
        return dish
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
    questions = [
        f"{label}: ask whether it uses {i['name']}."
        for i in facts.get("ingredients", [])
        if i["certainty"] == "possible"
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
            "confirm_with_staff": questions[:4],
            # The printed category wins; the AI only fills in "other" (e.g. imported rice).
            "category": DishCategory(facts["category"])
            if dish.category == DishCategory.OTHER and facts.get("category")
            else dish.category,
        }
    )


def prepare(menu: Menu, client=None) -> Menu:
    """The menu stripped to name/price/category, then annotated with the AI's facts.
    Dishes the AI has not answered for stay unknown (nobody with a restriction can eat them)."""
    plain = bare(menu)
    cache = _load()
    missing = [d for d in plain.dishes if _key(d) not in cache]
    if missing and (llm.provider() is not None or client is not None):
        try:
            text, used = _ask(missing[:MAX_DISHES], client)
            answer = json.loads(text or "{}")
            ids = {d.id: d for d in missing}
            for row in answer.get("dishes", []):
                dish = ids.get(row.get("id")) if isinstance(row, dict) else None
                facts = _clean(row) if dish else None
                if facts:
                    cache[_key(dish)] = {"name": dish.name_en or dish.name_zh, **facts}
            _save(cache)
            log.info("Dish facts for %d dishes from %s", len(missing), used)
        except Exception as exc:  # noqa: BLE001 - facts stay unknown; the rules stay strict
            log.warning("Dish facts failed: %s: %s", type(exc).__name__, str(exc)[:300])
    return plain.model_copy(update={"dishes": [apply(d, cache.get(_key(d))) for d in plain.dishes]})


def known(menu: Menu) -> bool:
    """Whether every dish has AI facts (cached)."""
    cache = _load()
    return all(_key(d) in cache for d in bare(menu).dishes)
