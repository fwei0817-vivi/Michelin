"""The diners' own allergies and diets ("mango", "cilantro", "MSG"; "halal", "no alcohol").

Hard rules, like the fixed ones. For every dish the AI answers, per term, whether it is
likely, possible or not in the dish (an allergen), or likely, possibly or not breaking the
diet. Answers are cached per dish name and term, and only terms someone at the table has are
asked about. The menu's own words win: a printed "mango" is likely whatever the AI says. No
answer stays "unknown", which the rules treat as a question for the server, never as safe.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from michelin import llm
from michelin.schemas import CustomFlag, DinerProfile, Dish

log = logging.getLogger("michelin")
MAX_DISHES = 40
ANSWERS = ("likely", "possible", "no")  # stored meaning, both kinds: likely = in it / breaks
# QA r21 OA-1: a bare "no" for a diet was read both ways ("no, not halal" vs "no violation").
# Diets are now asked with words that cannot flip: breaks / might_break / fits.
DIET_ANSWERS = {"breaks": "likely", "might_break": "possible", "fits": "no"}

SYSTEM = """You are a careful kitchen expert for restaurants in the US (mostly Chinese).
For each dish, and each item in "allergens", answer whether that ingredient is usually in the \
dish as normally cooked: "likely" (it is a usual ingredient), "possible" (some kitchens use \
it, or it can hide in a sauce, oil, stock, marinade, seasoning or garnish), or "no" (it is \
not normally used). For each item in "diets", answer whether the dish as normally cooked \
fits that diet: "breaks" (it does not fit, e.g. pork or Spam for halal), "might_break" (e.g. \
cooking wine, lard, meat stock or uncertified meat may be used), or "fits" (it fits). Be cautious: when unsure, say "possible". Give a short "why" \
(under 12 words)."""

_ALCOHOL = r"wine|beer|liquor|liqueur|sake|shaoxing|rum\b|baijiu|brandy|whisk(?:e)?y|料酒|酒"
# Words in the menu's own text that settle a diet (the AI cannot overrule them). Pork words
# come from the shared keyword list (spam, luncheon meat, char siu, lap cheong, lard...).
_DIET_WORDS = {
    "no alcohol": _ALCOHOL,
    "halal": "PORK",
    "kosher": "PORK|SHELLFISH",
}
# Diets the code can judge from the dish's own facts, as strictly as the no-pork rule.
_VEG_TERMS = {"vegetarian", "vegan", "veggie", "plant based", "plant-based"}


def derived(dish: Dish, term: str) -> tuple[str, str] | None:
    """(answer, why) from the dish's facts and printed words, or None (QA r21 OA-1b):
    pork => breaks halal, kosher and vegetarian; any meat or seafood => breaks vegetarian;
    alcohol => halal might break; meat => halal/kosher might break (certification)."""
    from michelin import keywords as kw
    from michelin.schemas import Allergen, EvidenceTier

    t = term.lower().strip()
    text = kw.dish_text(dish)
    pork = dish.contains_pork is True or bool(kw.found("pork", text))
    beef = dish.contains_beef is True or bool(kw.found("beef", text))
    meat = bool(kw.found("meat", text))
    blocking = {EvidenceTier.MENU, EvidenceTier.INFERRED}
    sea = {f.allergen for f in dish.allergens if f.tier in blocking} & {
        Allergen.FISH,
        Allergen.SHELLFISH,
    }
    sea |= {
        a
        for a, c in ((Allergen.FISH, "fish"), (Allergen.SHELLFISH, "shellfish"))
        if kw.found(c, text)
    }
    if t in ("halal", "kosher"):
        if pork:
            return "likely", "contains pork"
        if t == "kosher" and Allergen.SHELLFISH in sea:
            return "likely", "contains shellfish"
        if t == "halal" and re.search(_ALCOHOL, text, re.IGNORECASE):
            return "possible", "may be cooked with alcohol"
        if beef or meat:
            return "possible", "ask if the meat is " + t
        return None
    if t in _VEG_TERMS or t == "pescatarian":
        if pork or beef or meat or dish.is_vegetarian is False and t != "pescatarian":
            return "likely", "contains meat"
        if t != "pescatarian" and sea:
            return "likely", "contains seafood"
    return None


def _diet_answer(raw: str, why: str, term: str, new_style: bool) -> str:
    """The stored diet answer, never flipped by wording: a "fits"/"no" whose own reason names
    a forbidden ingredient or says "not halal" is treated as breaking (QA r21 OA-1a)."""
    if raw != "no":
        return raw
    w = why.lower()
    negated = re.search(
        rf"\b(not|non)[- ]{re.escape(term.lower())}|\bnot (allowed|permitted|suitable)|\bbreaks?\b|\bviolat",
        w,
    )
    pattern = _diet_pattern(term)
    named = pattern and re.search(
        pattern,
        re.sub(r"\b(no|without|free of|free from)\s+\w+(\s+or\s+\w+)?", " ", w),
        re.IGNORECASE,
    )
    if negated or named or (not new_style and re.search(r"\bcontains?\b", w)):
        return "likely"
    return "no"


def _diet_pattern(term: str) -> str | None:
    from michelin import keywords as kw

    p = _DIET_WORDS.get(term)
    if p is None:
        return None
    return (
        "|".join(f"(?:{kw.pattern(x.lower())})" if x.isupper() else x for x in p.split("|") if x)
        if any(x.isupper() for x in p.split("|"))
        else p
    )


def cache_path():
    from michelin.plan import dish_facts  # tests point dish_facts.CACHE_PATH at a temp dir

    return dish_facts.CACHE_PATH.with_name(dish_facts.CACHE_PATH.stem + "_custom.json")


def terms(diners: list[DinerProfile]) -> list[tuple[str, str]]:
    """(kind, term) pairs someone at the table has: only these are asked about."""
    out = {("allergy", t) for p in diners for t in p.other_allergies}
    out |= {("diet", t) for p in diners for t in p.other_diets}
    return sorted(out)


def _key(dish: Dish, kind: str, term: str) -> str:
    from michelin.plan import dish_facts

    return hashlib.sha256(f"{kind}|{term}|{dish_facts._key(dish)}".encode()).hexdigest()[:24]


def _load() -> dict:
    try:
        raw = json.loads(cache_path().read_text())
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(new: dict) -> dict:
    """Only this run's answers, merged by key into the file under its lock."""
    from michelin.plan import dish_facts

    return dish_facts.save_merged(cache_path(), new, lambda old, v: v)


def _text(dish: Dish) -> str:
    words = [dish.name_en, dish.name_zh, dish.description_raw, dish.variant]
    words += [i.name for i in dish.main_ingredients if i.tier.value == "menu"]
    return " ".join(w for w in words if w).lower()


def printed(dish: Dish, kind: str, term: str) -> bool:
    """The menu's own words name it: "Mango Pudding" for mango, "Shaoxing wine" for no alcohol."""
    text = _text(dish)
    if kind == "diet":
        pattern = _diet_pattern(term)
        if pattern is None and term.startswith("no "):
            pattern = rf"\b{re.escape(term[3:])}"
        return bool(pattern and re.search(pattern, text, re.IGNORECASE))
    stem = re.escape(term.rstrip("s"))
    return bool(re.search(rf"(?<![a-z]){stem}(?:s|es)?(?![a-z])", text))


def _schema(ids: list[str], allergies: list[str], diets: list[str]) -> dict:
    def items(names, enum):
        answer = {"type": "string", "enum": enum}
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "enum": names},
                    "answer": answer,
                    "why": {"type": "string"},
                },
                "required": ["item", "answer"],
            },
        }

    props = {"id": {"type": "string", "enum": ids}}
    if allergies:
        props["allergens"] = items(allergies, list(ANSWERS))
    if diets:
        props["diets"] = items(diets, list(DIET_ANSWERS))
    return {
        "type": "object",
        "properties": {
            "dishes": {
                "type": "array",
                "items": {"type": "object", "properties": props, "required": list(props)},
            }
        },
        "required": ["dishes"],
    }


def _ask(dishes: list[Dish], allergies: list[str], diets: list[str], client=None):
    """One model call -> (JSON text, model used). Tests replace this with a fake."""
    rows = [{"id": d.id, "name": d.name_en, "name_zh": d.name_zh} for d in dishes]
    brief = {"allergens": allergies, "diets": diets, "dishes": rows}
    turns = [llm.Turn("user", json.dumps(brief, ensure_ascii=False))]
    return llm.generate_json(
        "plan",
        system=SYSTEM,
        turns=turns,
        schema=_schema([d.id for d in dishes], allergies, diets),
        client=client,
        temperature=0,
    )


def annotate(dishes: list[Dish], diners: list[DinerProfile], client=None) -> list[Dish]:
    """The dishes with a CustomFlag for every term someone at the table has."""
    wanted = terms(diners)
    if not wanted:
        return dishes
    cache = _load()
    missing = [
        d
        for d in dishes
        if any(_key(d, k, t) not in cache and not printed(d, k, t) for k, t in wanted)
    ]
    if missing and (llm.provider() is not None or client is not None):
        for start in range(0, len(missing), MAX_DISHES):
            batch = missing[start : start + MAX_DISHES]
            need = {(k, t) for d in batch for k, t in wanted if _key(d, k, t) not in cache}
            allergies = sorted(t for k, t in need if k == "allergy")
            diets = sorted(t for k, t in need if k == "diet")
            try:
                text, used = _ask(batch, allergies, diets, client)
                ids = {d.id: d for d in batch}
                new: dict = {}
                for row in json.loads(text or "{}").get("dishes", []):
                    dish = ids.get(row.get("id")) if isinstance(row, dict) else None
                    if not dish:
                        continue
                    for kind, field in (("allergy", "allergens"), ("diet", "diets")):
                        for a in row.get(field) or []:
                            if not isinstance(a, dict):
                                continue
                            got = a.get("answer")
                            new_style = kind == "diet" and got in DIET_ANSWERS
                            got = DIET_ANSWERS.get(got, got) if kind == "diet" else got
                            if got not in ANSWERS:
                                continue
                            term = str(a.get("item") or "")
                            if (kind, term) in need:
                                new[_key(dish, kind, term)] = {
                                    "name": dish.name_en or dish.name_zh,
                                    "term": term,
                                    "answer": got,
                                    "why": str(a.get("why") or "")[:120],
                                }
                                if new_style:  # asked as breaks/might_break/fits
                                    new[_key(dish, kind, term)]["v"] = 2
                cache = {**cache, **_save(new)}
                log.info(
                    "Custom facts (%d terms) for %d dishes from %s", len(need), len(batch), used
                )
            except Exception as exc:  # noqa: BLE001 - answers stay unknown; the rules stay strict
                log.warning("Custom facts failed: %s: %s", type(exc).__name__, str(exc)[:300])
                break
    out = []
    for d in dishes:
        flags = []
        for kind, term in wanted:
            if printed(d, kind, term):
                flags.append(
                    CustomFlag(
                        term=term, kind=kind, answer="likely", why="on the menu", printed=True
                    )
                )
                continue
            hit = cache.get(_key(d, kind, term))
            answer = hit["answer"] if hit and hit.get("answer") in ANSWERS else "unknown"
            why = (hit or {}).get("why", "")
            if kind == "diet":
                if answer != "unknown":
                    answer = _diet_answer(answer, why, term, (hit or {}).get("v") == 2)
                code = derived(d, term)  # the dish's own facts: at least this strict
                rank = {"likely": 3, "unknown": 2, "possible": 1, "no": 0}  # unknown is not offered
                if code and rank[code[0]] > rank[answer]:
                    answer, why = code
            flags.append(CustomFlag(term=term, kind=kind, answer=answer, why=why))
        out.append(d.model_copy(update={"custom_flags": flags}))
    return out
