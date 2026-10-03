"""Label dishes from a reviewed hidden-ingredient knowledge base. Deterministic: the same
dish text always yields the same labels.

Three evidence sources, combined per dish:

1. Printed text. Restricted ingredients named in the dish name or description are `menu`
   tier. Known misleading phrases ("fish-fragrant", "lobster sauce") are removed first.
2. Dish knowledge. An exact Chinese name or normalized English alias selects one entry in
   `data/knowledge/hidden_ingredients.json`. Its components become `inferred` (definite or
   likely) or `unknown` (possible, with a staff question).
3. Sauce knowledge. Named sauces in the text (XO, oyster, hoisin...) add their contents,
   even when the dish itself is not in the knowledge base.

A dish with no knowledge-base match is never certified: diet flags stay `None` (unsafe by
product rule 3), every allergen without stronger evidence gets an `unknown` flag, and staff must be asked. An LLM
matcher may later map unusual names to an entry id; it never writes ingredients itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from michelin.schemas import (
    Allergen,
    AllergenFlag,
    Dish,
    DishCategory,
    EvidenceTier,
    IngredientClaim,
    PortionClass,
)

KB_PATH = Path(__file__).resolve().parents[3] / "data/knowledge/hidden_ingredients.json"

HITS = {
    "pork", "beef", "poultry", "meat", "meat_stock", "fish", "shellfish",
    "egg", "dairy", "honey", "peanut", "tree_nut", "soy", "wheat", "sesame",
}  # fmt: skip
CERTAINTIES = ("definite", "likely", "possible")
VEGETARIAN_BREAKERS = {"pork", "beef", "poultry", "meat", "meat_stock", "fish", "shellfish"}
VEGAN_BREAKERS = VEGETARIAN_BREAKERS | {"egg", "dairy", "honey"}

# Restricted ingredients a reader can see in printed text.
PRINTED = {
    "pork": r"\bpork\b|\bham\b|\bbacon\b|\blard\b|猪",
    "beef": r"\bbeef\b|牛",
    "poultry": r"\bchicken\b|\bduck\b|鸡|鸭",
    "meat": r"\bmeat\b|\blamb\b|\bmutton\b|羊",
    "fish": r"\bfish\b|\bsalmon\b|\bcod\b|\btilapia\b|鱼",
    "shellfish": r"\bshrimps?\b|\bprawns?\b|\bcrab\b|\bscallops?\b|\blobster\b|\bclams?\b"
    r"|\bmussels?\b|\boysters?\b|虾|蟹|贝",
    "egg": r"\beggs?\b|蛋",
    "dairy": r"\bmilk\b|\bcheese\b|\bbutter\b|\bcream\b",
    "peanut": r"\bpeanuts?\b|花生",
    "tree_nut": r"\bcashews?\b|\bwalnuts?\b|\balmonds?\b|\bpine nuts?\b|腰果|核桃|杏仁",
    "sesame": r"\bsesame\b|芝麻|麻酱",
    "wheat": r"\bwheat\b|\bnoodles?\b|\bflour\b|\bwrappers?\b|\bdumplings?\b|面|饺",
    "soy": r"\btofu\b|\bbean curd\b|\bsoy\b|豆腐",
}
# Names that suggest an ingredient the dish does not contain.
MISLEADING = [
    r"fish[- ]?(fragrant|flavou?red)",
    r"\byu[- ]?xiang\b",
    "鱼香",
    r"lobster sauce",
    "龙糊",
    r"\begg ?plant\b",
    r"\bpeanut[- ]free\b",
]


@dataclass(frozen=True)
class Component:
    name: str
    hits: tuple[str, ...]
    certainty: str
    printed: bool = False


@dataclass(frozen=True)
class Labeled:
    dish: Dish
    match: str | None  # knowledge-base dish id, or None when not recognized
    sauces: tuple[str, ...]


def normalize(name: str | None) -> str:
    """Lowercase, drop punctuation, counts and numbering: "C12. Kung Pao Chicken (2)"."""
    if not name:
        return ""
    s = name.lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"^\s*[a-z]?\d+[.)]?\s+", "", s)
    s = re.sub(r"\(\s*\d+\s*(pcs?|pieces?)?\s*\)", " ", s)
    s = re.sub(r"[^\w一-鿿]+", " ", s.replace("'", ""))
    return re.sub(r"\s+", " ", s).strip()


@cache
def load_kb(path: Path = KB_PATH) -> dict:
    kb = json.loads(path.read_text(encoding="utf-8"))
    by_zh, by_en = {}, {}
    for entry in kb["dishes"]:
        for zh in entry["name_zh"]:
            by_zh[normalize(zh)] = entry
        for alias in entry["aliases"]:
            by_en[normalize(alias)] = entry
    kb["_by_zh"], kb["_by_en"] = by_zh, by_en
    return kb


def validate_kb(kb: dict) -> list[str]:
    """Problems that would make labels wrong. Empty means the file is usable."""
    problems = []
    seen_ids, seen_names = set(), {}
    for entry in kb["dishes"]:
        if entry["id"] in seen_ids:
            problems.append(f"duplicate id {entry['id']}")
        seen_ids.add(entry["id"])
        DishCategory(entry["category"])
        PortionClass(entry["portion"])
        for key in [normalize(n) for n in entry["name_zh"] + entry["aliases"]]:
            if key in seen_names and seen_names[key] != entry["id"]:
                problems.append(f"{key!r} names both {seen_names[key]} and {entry['id']}")
            seen_names[key] = entry["id"]
    for entry in kb["dishes"] + kb["sauces"]:
        for c in entry["components"]:
            if c["certainty"] not in CERTAINTIES:
                problems.append(f"{entry['id']}: bad certainty {c['certainty']!r}")
            if not c["hits"] or set(c["hits"]) - HITS:
                problems.append(f"{entry['id']}: bad hits {c['hits']}")
    return problems


def match(dish: Dish, kb: dict | None = None) -> dict | None:
    kb = kb or load_kb()
    zh = normalize(dish.name_zh)
    if zh and zh in kb["_by_zh"]:
        return kb["_by_zh"][zh]
    en = normalize(dish.name_en)
    return kb["_by_en"].get(en) if en else None


def _text(dish: Dish) -> str:
    text = " ".join(filter(None, [dish.name_en, dish.name_zh, dish.description_raw]))
    for pattern in MISLEADING:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return text


def _components(entry: dict, printed: bool = False) -> list[Component]:
    return [
        Component(c["name"], tuple(c["hits"]), c["certainty"], printed) for c in entry["components"]
    ]


def gather(dish: Dish, kb: dict | None = None) -> tuple[list[Component], dict | None, list[str]]:
    kb = kb or load_kb()
    text = _text(dish)
    out = [
        Component(f"{hit} (printed)", (hit,), "definite", printed=True)
        for hit, pattern in PRINTED.items()
        if re.search(pattern, text, re.IGNORECASE)
    ]
    sauces = [
        s for s in kb["sauces"] if any(re.search(p, text, re.IGNORECASE) for p in s["patterns"])
    ]
    for s in sauces:
        out += _components(s)
    entry = match(dish, kb)
    if entry:
        out += _components(entry)
    return out, entry, [s["id"] for s in sauces]


def _tier(c: Component) -> EvidenceTier:
    if c.printed:
        return EvidenceTier.MENU
    return EvidenceTier.UNKNOWN if c.certainty == "possible" else EvidenceTier.INFERRED


def _strongest(components: list[Component], wanted: set[str]) -> str | None:
    found = [c.certainty for c in components if wanted & set(c.hits)]
    for cert in CERTAINTIES:
        if cert in found:
            return cert
    return None


def _diet_ok(components: list[Component], breakers: set[str], known: bool) -> bool | None:
    """False if a definite/likely breaker; None if only possible ones or the dish is unknown."""
    cert = _strongest(components, breakers)
    if cert in ("definite", "likely"):
        return False
    return None if cert == "possible" or not known else True


def _contains(components: list[Component], hit: str, known: bool) -> bool | None:
    cert = _strongest(components, {hit})
    if cert in ("definite", "likely"):
        return True
    if cert == "possible" or not known or _strongest(components, {"meat"}):
        return None  # unspecified meat: cannot rule this one out
    return False


def label_dish(dish: Dish, kb: dict | None = None) -> Labeled:
    """Return a copy of `dish` with ingredients, allergens, diet flags and staff questions
    filled from printed text and the knowledge base. Name, price and id are untouched."""
    components, entry, sauce_ids = gather(dish, kb)
    known = entry is not None
    label = dish.name_en or dish.name_zh or dish.id

    allergens: dict[Allergen, AllergenFlag] = {}
    rank = {EvidenceTier.MENU: 0, EvidenceTier.INFERRED: 1, EvidenceTier.UNKNOWN: 2}
    for c in components:
        for hit in c.hits:
            if hit not in Allergen._value2member_map_:
                continue
            tier = _tier(c)
            flag = AllergenFlag(
                allergen=Allergen(hit),
                tier=tier,
                confidence={"definite": 0.9, "likely": 0.7, "possible": 0.3}[c.certainty],
                reason=f"{c.name}: printed on the menu"
                if c.printed
                else f"{c.name}: {c.certainty} in typical recipes",
            )
            old = allergens.get(flag.allergen)
            if old is None or rank[tier] < rank[old.tier]:
                allergens[flag.allergen] = flag
    if not known:
        for a in Allergen:
            allergens.setdefault(
                a,
                AllergenFlag(
                    allergen=a,
                    tier=EvidenceTier.UNKNOWN,
                    confidence=0.0,
                    reason="dish not in the knowledge base; ingredients unverified",
                ),
            )

    questions = [
        f"{label}: ask whether it uses {c.name}."
        for c in components
        if c.certainty == "possible" and not c.printed
    ]
    if not known:
        questions.append(
            f"{label}: not a dish we recognize. Ask staff about meat, seafood, egg, nuts and "
            "the sauce before serving anyone with a restriction."
        )

    update = {
        "main_ingredients": [
            IngredientClaim(name=c.name, tier=_tier(c)) for c in components if not c.printed
        ]
        + [
            IngredientClaim(name=i.name, tier=i.tier)
            for i in dish.main_ingredients
            if i.tier == EvidenceTier.MENU
        ],
        "allergens": sorted(allergens.values(), key=lambda f: f.allergen.value),
        "is_vegetarian": _diet_ok(components, VEGETARIAN_BREAKERS, known),
        "is_vegan": _diet_ok(components, VEGAN_BREAKERS, known),
        "contains_pork": _contains(components, "pork", known),
        "contains_beef": _contains(components, "beef", known),
        "confirm_with_staff": list(dict.fromkeys(dish.confirm_with_staff + questions)),
    }
    if known and dish.category == DishCategory.OTHER:
        update["category"] = DishCategory(entry["category"])
        update["portion"] = PortionClass(entry["portion"])
    if "reviewed_allergens" in Dish.model_fields:  # backend branch: evidence was reviewed
        update["reviewed_allergens"] = list(Allergen) if known else []
    return Labeled(dish.model_copy(update=update), entry["id"] if known else None,
                   tuple(sauce_ids))  # fmt: skip
