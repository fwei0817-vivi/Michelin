"""Build the Menu the system sees from an eval menu, under different labeling regimes.

current  What the pipeline produces today without a knowledge base: a reviewer labels only
         what the menu prints (dish name + description). The repo's sample menu is used
         unchanged, exactly as the app loads it.
oracle   Labels derived from the truth block: the upper bound if extraction were perfect.
         Isolates the planner's rule logic from data quality.
kb       What the pipeline produces with the knowledge base: printed text, dish and sauce
         knowledge from src/michelin/parse/knowledge.py. Holdout dishes are not in it.
reference  Like oracle, but `possible` components are dropped: only definite/likely conflicts
         block. Used to decide whether a safe order exists at all (over-refusal check).

The system never sees `truth` directly; scoring compares its answer against it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from truth import ALLERGEN_HITS, DIET_BREAKERS, SEVERE

ROOT = Path(__file__).resolve().parents[1]
EVAL = Path(__file__).resolve().parent
TIER = {"definite": "menu", "likely": "inferred", "possible": "unknown"}

# Printed-text keywords a reviewer without domain knowledge would act on.
PRINTED = {
    "pork": r"\bpork\b|\bham\b|\bbacon\b|猪",
    "beef": r"\bbeef\b|牛",
    "poultry": r"\bchicken\b|\bduck\b|鸡|鸭",
    "meat": r"\bmeat\b|\blamb\b|羊|肉",
    "fish": r"\bfish\b|鱼",
    "shellfish": r"\bshrimp\b|\bprawns?\b|\bcrab\b|\bscallops?\b|\boyster\b|\blobster\b|虾|蟹",
    "egg": r"\beggs?\b|蛋",
    "dairy": r"\bmilk\b|\bcheese\b|\bbutter\b|\bcream\b",
    "peanut": r"\bpeanuts?\b|花生",
    "tree_nut": r"\bcashews?\b|\bwalnuts?\b|\balmonds?\b|腰果|核桃",
    "sesame": r"\bsesame\b|芝麻|麻酱",
    "wheat": r"\bwheat\b|\bnoodles?\b|\bwrapper\b|\bflour\b|面",
    "soy": r"\btofu\b|\bsoy\b|\bbean sauce\b|豆腐",
}


def load_eval_menu(name: str) -> dict[str, dict]:
    """Eval dishes keyed by id, each with category/portion/price/truth for scoring."""
    if name == "trap":
        data = json.loads((EVAL / "menus/trap_menu.json").read_text(encoding="utf-8"))
        return {d["id"]: d for d in data["dishes"]}
    if name == "sample_sichuan":
        spec = json.loads((EVAL / "menus/sample_sichuan_truth.json").read_text(encoding="utf-8"))
        repo = json.loads((ROOT / spec["menu"]).read_text(encoding="utf-8"))
        return {
            d["id"]: {
                **d,
                "portion": d.get("portion", "medium"),
                "traps": spec["truth"][d["id"]].get("traps", []),
                "truth": spec["truth"][d["id"]],
            }
            for d in repo["dishes"]
        }
    raise ValueError(f"unknown eval menu {name!r}")


def _diet_flag(found: dict[str, str], breakers: set[str]) -> bool | None:
    certs = [c for hit, c in found.items() if hit in breakers]
    if any(c in SEVERE for c in certs):
        return False
    return None if certs else True


def _flags(dish: dict, found: dict[str, str], printed_only: bool) -> dict:
    """found: hit -> strongest certainty."""
    allergens = [
        {
            "allergen": hit,
            "tier": TIER[cert],
            "confidence": {"definite": 0.95, "likely": 0.7, "possible": 0.3}[cert],
            "reason": "printed on the menu" if printed_only else f"{cert} in typical recipes",
        }
        for hit, cert in sorted(found.items())
        if hit in ALLERGEN_HITS
    ]
    pork = _diet_flag(found, {"pork"})
    beef = _diet_flag(found, {"beef"})
    if "meat" in found:  # unspecified meat: pork/beef status unknown unless established
        pork = pork if pork is False else None
        beef = beef if beef is False else None
    return {
        "allergens": allergens,
        "is_vegetarian": _diet_flag(found, DIET_BREAKERS["vegetarian"]),
        "is_vegan": _diet_flag(found, DIET_BREAKERS["vegan"]),
        "contains_pork": None if pork is None else not pork,
        "contains_beef": None if beef is None else not beef,
        # Read by the backend branch; ignored by main. The reviewer looked at every allergen.
        "reviewed_allergens": sorted(ALLERGEN_HITS),
    }


def _base(dish: dict) -> dict:
    return {
        "id": dish["id"],
        "name_zh": dish.get("name_zh"),
        "name_en": dish.get("name_en"),
        "price": dish["price"],
        "description_raw": dish.get("printed"),
        "category": dish["category"],
        "portion": dish["portion"],
    }


def label_current(dish: dict) -> dict:
    text = " ".join(filter(None, [dish.get("name_en"), dish.get("name_zh"), dish.get("printed")]))
    found = {hit: "definite" for hit, pat in PRINTED.items() if re.search(pat, text, re.IGNORECASE)}
    out = _base(dish) | _flags(dish, found, printed_only=True)
    out["main_ingredients"] = [
        {"name": part.strip(), "tier": "menu"}
        for part in (dish.get("printed") or "").split(",")
        if part.strip()
    ]
    out["confirm_with_staff"] = []
    return out


def label_oracle(dish: dict, keep: frozenset = frozenset(TIER)) -> dict:
    rank = {"possible": 0, "likely": 1, "definite": 2}
    found: dict[str, str] = {}
    components = [c for c in dish["truth"]["components"] if c["certainty"] in keep]
    for c in components:
        for hit in c["hits"]:
            if hit not in found or rank[c["certainty"]] > rank[found[hit]]:
                found[hit] = c["certainty"]
    out = _base(dish) | _flags(dish, found, printed_only=False)
    out["main_ingredients"] = [
        {"name": c["name"], "tier": TIER[c["certainty"]]} for c in components
    ]
    label = dish.get("name_en") or dish["id"]
    out["confirm_with_staff"] = [
        f"{label}: ask whether it uses {c['name']}."
        for c in components
        if c["certainty"] == "possible"
    ]
    return out


def label_reference(dish: dict) -> dict:
    return label_oracle(dish, keep=frozenset(SEVERE))


def printed_dish(dish: dict) -> dict:
    """Only what a menu shows: name, price, description. No labels."""
    return {
        "id": dish["id"],
        "name_zh": dish.get("name_zh"),
        "name_en": dish.get("name_en"),
        "price": dish["price"],
        "description_raw": dish.get("printed", dish.get("description_raw")),
        "category": dish["category"],
        "portion": dish["portion"],
    }


def kb_labels(dish: dict) -> tuple[dict, str | None]:
    from michelin.parse.knowledge import label_dish
    from michelin.schemas import Dish

    labeled = label_dish(Dish.model_validate(printed_dish(dish)))
    return labeled.dish.model_dump(mode="json"), labeled.match


def label_kb(dish: dict) -> dict:
    return kb_labels(dish)[0]


def build_menu(menu_name: str, labels: str, subset: list[str] | None = None) -> dict:
    """The Menu JSON the system receives as `menu_override`."""
    dishes = load_eval_menu(menu_name)
    ids = subset or list(dishes)
    if labels == "current" and menu_name == "sample_sichuan":
        repo = json.loads((ROOT / "data/menus/sample_sichuan.json").read_text(encoding="utf-8"))
        menu = {**repo, "dishes": [d for d in repo["dishes"] if d["id"] in ids]}
        menu["verified"] = True
        return menu
    labeler = {
        "current": label_current,
        "oracle": label_oracle,
        "reference": label_reference,
        "kb": label_kb,
    }[labels]
    return {
        "restaurant_id": f"eval_{menu_name}",
        "restaurant_name": f"Eval {menu_name}",
        "cuisine": "chinese_sichuan",
        "source": "sample",
        "verified": True,
        "dishes": [labeler(dishes[i]) for i in ids],
    }
