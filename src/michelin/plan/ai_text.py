"""The one gate for text the AI wrote (QA r12 audit).

Every AI-written string that can reach the UI or the receipt passes through exactly one
function here, per surface. Each checks every claim the code can check against the order it
will be shown with, and returns None when any claim fails, so the caller uses its
code-written fallback:

- dish names: a word naming a menu dish must belong to a dish on this order (or, for a
  change note, one that really moved);
- diners: a diner it names must be able to eat what it says (per dish for a reason; some
  dish on the order for a summary), and "everyone" must be true;
- counts: a stated dish count must match;
- spice: "mild", "heat-free", "not spicy", "spicy", "hot" must match the cards' levels;
- allergies and diets: "vegetarian", "vegan", "halal", "gluten-free", "nut-free", "<x>-free"
  must hold under the rules for the dishes it covers.

Approved strings are recorded (`APPROVED`) so a test can prove no AI text bypassed the gate.

Surfaces (decision):
  plan summary           (b) AI, validated here against the shown order; else code summary
  per-dish reason        (b) AI, validated here per dish; else code reason (explain.py)
  swap note              (b) AI clause, validated here; else code clause (ai_swap._line)
  refine change note     (b) AI note checked against the real diff (refine.note_ok) and
                             here; "less spicy" notes are always the code's
  dish server question   (a) code only (edibility.ask_server)
  whole-meal questions   (c) dropped
  no-fit reason          (a) code only (the AI's no_fit text is never shown)
  "already gentle", no-fit, coverage, notices   (a) code only
"""

from __future__ import annotations

import os
import re

from michelin.plan import spice
from michelin.plan.edibility import assessment, diner_status, edible_by

APPROVED: set[str] = set()  # every AI string this gate let through (tests read it)
_MAX_APPROVED = 5000

_NUMBERS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]
_COUNT = re.compile(
    r"\b(\d+|" + "|".join(_NUMBERS) + r")\s+(?:[a-z-]+\s+){0,2}?(?:dish|dishes|plates?|items?)\b",
    re.IGNORECASE,
)
_GENERIC = {
    "dish",
    "dishes",
    "spicy",
    "mild",
    "milder",
    "sauce",
    "with",
    "style",
    "special",
    "house",
    "plate",
    "order",
    "one",
    "ones",
    "the",
    "and",
    "for",
    "less",
    "more",
    "small",
    "large",
    "fried",
    "steamed",
    "chicken",
    "beef",
    "pork",
    "shrimp",
    "tofu",
    "fish",
    "vegetable",
    "vegetables",
    "rice",
    "noodle",
    "noodles",
    "soup",
    "everyone",
    "table",
    "meal",
}
_NO_HEAT = re.compile(
    r"heat[- ]free|no heat|without (?:any )?heat|not spicy|non[- ]spicy|zero heat|no spice|"
    r"spice[- ]free|no chil(?:i|li)",
    re.IGNORECASE,
)
_MILD = re.compile(r"\bmild(?:er|ly)?\b|\bgentle\b", re.IGNORECASE)
_HOT = re.compile(r"\b(?:spicy|hot|fiery|heat|kick|numbing|chil(?:i|li))\b", re.IGNORECASE)
_EVERYONE = re.compile(
    r"\b(everyone|everybody|all (?:diners|of you|four|three|five|six)|whole table|the table)\b",
    re.IGNORECASE,
)
_DIETS = {
    "vegetarian": ("vegetarian", r"\bvegetarian|\bveggie\b|meat[- ]free|meatless"),
    "vegan": ("vegan", r"\bvegan\b|plant[- ]based"),
    "halal": ("halal", r"\bhalal\b"),
    "no_pork": ("no_pork", r"pork[- ]free|no pork|without pork"),
    "no_beef": ("no_beef", r"beef[- ]free|no beef|without beef"),
}
_FREE = re.compile(
    r"\b([a-z]+)[- ]free\b|\bno ([a-z]+)\b|\bwithout (?:any )?([a-z]+)\b", re.IGNORECASE
)
_ALLERGEN_WORDS = {
    "gluten": "wheat",
    "wheat": "wheat",
    "nut": "tree_nut",
    "nuts": "tree_nut",
    "peanut": "peanut",
    "peanuts": "peanut",
    "dairy": "dairy",
    "milk": "dairy",
    "egg": "egg",
    "eggs": "egg",
    "soy": "soy",
    "sesame": "sesame",
    "shellfish": "shellfish",
    "seafood": "shellfish",
    "fish": "fish",
    "allergen": "*",
    "allergens": "*",
}


NAME_RULE = (
    "Never write a diner's name or id in any text you write. To mention a diner, write "
    "their id in curly braces, e.g. {alice}; the app puts in their name."
)


def detoken(text: str, diners) -> str | None:
    """The AI writes {id} tokens, never names (QA r15). Unknown tokens, or any raw id or name
    (any case, e.g. 'alice ben cai mia'), reject the text; tokens become display names."""
    ids = {p.id: (p.name or p.id) for p in diners}
    tokens = re.findall(r"\{([^{}]*)\}", text)
    if any(t.strip() not in ids for t in tokens):
        return None
    bare = re.sub(r"\{[^{}]*\}", " ", text)
    for p in diners:
        for word in {p.id, p.name or ""}:
            if word and re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", bare, re.IGNORECASE):
                return None
    return re.sub(r"\{([^{}]*)\}", lambda m: ids[m.group(1).strip()], text)


def ai_prose() -> bool:
    """MICHELIN_AI_PROSE (default off, QA r16 team decision): when off, no prose the AI
    writes (summary, reasons, swap or change notes) reaches the UI; the code writes them.
    The AI still reads menus, infers ingredients and picks dishes."""
    return os.environ.get("MICHELIN_AI_PROSE", "").strip().lower() in {"1", "true", "on", "yes"}


def _approve(text: str) -> str:
    if len(APPROVED) < _MAX_APPROVED:
        APPROVED.add(text)
    return text


def _clean(text: object, limit: int = 240) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def _tokens(name: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (name or "").lower()) if len(w) >= 4} - _GENERIC


def _spice(d) -> int:
    return spice.level(d)  # the one spice source


_SINGLE = re.compile(
    r"\b(?:single|lone|sole|only)\s+(?:[a-z-]+\s+){0,2}(?:dish|plate|item|order)\b", re.IGNORECASE
)


def count_ok(text: str, n: int) -> bool:
    for m in _COUNT.finditer(text):
        word = m.group(1).lower()
        if (int(word) if word.isdigit() else _NUMBERS.index(word)) != n:
            return False
    return n == 1 or not _SINGLE.search(text)


def _dishes_ok(low: str, menu, shown: set[str]) -> bool:
    """Words naming menu dishes must belong to dishes in `shown`."""
    said = set(re.findall(r"[a-z]+", low))
    allowed = (
        set().union(
            *(_tokens(menu.dish(i).name_en) | _tokens(menu.dish(i).family_name) for i in shown)
        )
        if shown
        else set()
    )
    for d in menu.dishes:
        if d.id in shown:
            continue
        if (_tokens(d.name_en) - allowed) & said:
            return False
    return True


def _spice_ok(low: str, dishes, hot_words: bool = True) -> bool:
    top = max((_spice(d) for d in dishes), default=0)
    if _NO_HEAT.search(low) and top > 0:
        return False
    if _MILD.search(low) and top > 1:
        return False
    return not (hot_words and top == 0 and _HOT.search(low) and not _NO_HEAT.search(low))


def _diet_ok(low: str, dishes, diners) -> bool:
    for diet, pattern in _DIETS.values():
        if not re.search(pattern, low, re.IGNORECASE):
            continue
        if diet == "halal":  # only the table's own halal diner(s) can vouch for it
            who = [p for p in diners if any("halal" in x.lower() for x in p.other_diets)]
        else:
            who = [p for p in diners if diet in {x.value for x in p.diets}] or [_probe(diet)]
        if not who or not all(len(edible_by(d, who)) == len(who) for d in dishes):
            return False
    for m in _FREE.finditer(low):
        word = (m.group(1) or m.group(2) or m.group(3) or "").lower()
        allergen = _ALLERGEN_WORDS.get(word)
        if allergen is None:
            continue
        for d in dishes:
            flags = {f.allergen.value for f in d.allergens}
            if (allergen == "*" and flags) or allergen in flags:
                return False
    return True


def _probe(diet: str):
    from michelin.schemas import Diet, DinerProfile

    return DinerProfile(id="_p", name="_p", diets=[Diet(diet)])


def _named(text: str, diners) -> list:
    return [
        p
        for p in diners
        if p.name and re.search(rf"(?<!\w){re.escape(p.name)}(?!\w)", text, re.IGNORECASE)
    ]


def summary(text: object, menu, request, items, shown: bool = False) -> str | None:
    """The plan subtitle, checked against the order it will be shown with. `shown=True`
    re-checks a subtitle already on screen (names already in) against a new order."""
    if not shown and not ai_prose():
        return None
    t = _clean(text) if shown else detoken(_clean(text), request.diners)
    if not t:
        return None
    low = t.lower()
    ids = {i.dish_id for i in items}
    dishes = [menu.dish(i) for i in ids]
    shared = [d for d in dishes if d.category.value != "staple"]
    if not (count_ok(t, len(items)) or count_ok(t, len(shared))):
        return None
    if not _dishes_ok(low, menu, ids):
        return None
    if not _spice_ok(low, shared) or not _diet_ok(low, shared, request.diners):
        return None
    for p in _named(t, request.diners):
        if not any(edible_by(d, [p]) for d in shared):
            return None
    if _OVERCLAIM.search(low) and not _all_well_served(shared, request.diners):
        return None  # "meets everyone's preferences" / "easily accommodates all" (QA r14)
    if _SUITS_ALL.search(low) and any(
        v["status"] != "ok" for d in shared for v in diner_status(d, request.diners).values()
    ):
        return None  # "suitable for everyone" only if no one needs a check anywhere (QA r15)
    if _EVERYONE.search(low):
        fed = {pid for d in shared for pid in edible_by(d, request.diners)}
        if len(fed) < len(request.diners):
            return None
        if re.search(r"every(?:one|body)(?:'s)? (?:can eat|enjoy)s? (?:every|all)", low) and any(
            len(edible_by(d, request.diners)) < len(request.diners) for d in shared
        ):
            return None
    return _approve(t)


_OVERCLAIM = re.compile(
    r"\bpreferences?\b|\baccommodat\w*\s+(?:\w+\s+){0,2}?all\b|\beveryone'?s?\s+needs\b"
    r"|\bdietary needs\b|\beveryone'?s?\s+dietary\b|\ball dietary\b",
    re.IGNORECASE,
)
_SUITS_ALL = re.compile(
    r"\bsuit(?:able|s|ed)? (?:for |to )?(?:everyone|everybody|all)\b", re.IGNORECASE
)
_CHECKABLE_PREFS = {"no_spicy", "mild"}


def _pref_ok(dish, person) -> bool:
    prefs = {getattr(x, "value", x) for x in person.preferences}
    if prefs - _CHECKABLE_PREFS:
        return False  # a taste the code cannot check: the claim is not provable
    return spice.taste(dish, person) is None


def _all_well_served(dishes, diners) -> bool:
    """Every diner has at least 2 dishes needing no server check and clashing with no taste."""
    return all(
        sum(
            assessment(d, p)["status"] == "validated_under_known_data" and _pref_ok(d, p)
            for d in dishes
        )
        >= 2
        for p in diners
    )


def _topic(diner, reasons: list[str]) -> str:
    """What the server must confirm for this diner, in their own words ("halal")."""
    low = " ".join(r for r in reasons if r).lower().replace("_", " ")
    rules = [getattr(x, "value", x) for x in list(diner.diets or []) + list(diner.allergies or [])]
    rules += list(getattr(diner, "other_allergies", None) or []) + list(
        getattr(diner, "other_diets", None) or []
    )
    hit = [str(r).replace("_", " ") for r in rules if str(r).replace("_", " ").lower() in low]
    return ", ".join(dict.fromkeys(hit))


def code_summary(menu, request, items) -> str:
    """A true one-liner about the order. Counts only dishes each diner can eat without
    asking ("ok" in diner_status, QA r17); anyone with none is named honestly."""
    shared = [
        menu.dish(i.dish_id) for i in items if menu.dish(i.dish_id).category.value != "staple"
    ]
    st = [diner_status(d, request.diners) for d in shared]
    # counted only when "ok" (no server check) and not too spicy for them (2026-10-10)
    ok = {
        p.id: sum(s[p.id]["status"] == "ok" and s[p.id]["taste"] != "too_spicy" for s in st)
        for p in request.diners
    }
    top = max((_spice(d) for d in shared), default=0)
    heat = "nothing spicy" if not top else f"at most {spice.word(top)}"

    def n_dishes(n):
        return f"{n} dishes" if n != 1 else "one dish"

    stuck = [p for p in request.diners if ok[p.id] == 0]
    rest = [p for p in request.diners if ok[p.id] > 0]
    parts = []
    if not stuck:
        parts.append(f"everyone has at least {n_dishes(min(ok.values(), default=0))} they can eat")
    else:
        if rest:
            low = min(ok[p.id] for p in rest)
            who = "everyone else has" if len(rest) > 1 else f"{rest[0].name or rest[0].id} has"
            parts.append(f"{who} at least {n_dishes(low)} they can eat")
        for p in stuck:
            name = p.name or p.id
            asks = [
                s[p.id]["reason"]
                for s in st
                if s[p.id]["status"] == "needs_confirm" and s[p.id]["taste"] != "too_spicy"
            ]
            if asks:
                t = _topic(p, asks)
                parts.append(
                    f"{name}'s dishes need a quick check with the server" + (f" ({t})" if t else "")
                )
            elif any(s[p.id]["taste"] == "too_spicy" for s in st):
                parts.append(f"{name} has no dish that is not too spicy for them")
            else:
                parts.append(f"{name} has no dish they can eat")
    n = len(shared)
    line = f"{n} dish{'es' if n != 1 else ''} to share; " + "; ".join(parts) + f"; {heat}."
    from michelin.plan import enough  # the 'enough food' rule, said honestly when unmet

    short = enough.honest_line(menu, request, items)
    return f"{line} {short}" if short else line


def with_enough(text: str, menu, request, items) -> str:
    """Any summary (the AI's or the code's) ends with the 'enough food' line when the order
    misses it, so a short order is never shown silently."""
    from michelin.plan import enough

    short = enough.honest_line(menu, request, items)
    return f"{text} {short}" if short and short not in text else text


def coverage_check(menu, request, items) -> tuple[bool, str]:
    """The plan's coverage check, same rule as code_summary (QA r18): "everyone" only when
    every diner has a dish that is "ok" in diner_status; anyone with only dishes the server
    must confirm is named."""
    shared = [
        menu.dish(i.dish_id) for i in items if menu.dish(i.dish_id).category.value != "staple"
    ]
    st = [diner_status(d, request.diners) for d in shared]
    none, ask = [], []
    for p in request.diners:
        mine = [
            s[p.id] for s in st if s[p.id]["taste"] != "too_spicy"
        ]  # taste conflict: not theirs
        if any(v["status"] == "ok" for v in mine):
            continue
        asks = [v["reason"] for v in mine if v["status"] == "needs_confirm"]
        if asks:
            t = _topic(p, asks)
            ask.append(f"{p.name or p.id}'s only if the server confirms" + (f" ({t})" if t else ""))
        else:
            none.append(p.name or p.id)
    if none:
        return False, f"Not enough for: {', '.join(none)}."
    if ask:
        return True, "Everyone has a dish; " + "; ".join(ask) + "."
    return True, "Everyone has at least one dish they can eat without asking."


def reason(text: object, dish, menu, request, n: int = 0, shown: bool = False) -> str | None:
    """A per-dish reason, checked for this dish on this order. `shown=True` re-checks a
    reason already on screen (names already in) against a new order."""
    if not shown and not ai_prose():
        return None
    t = _clean(text, 200) if shown else detoken(_clean(text, 200), request.diners)
    return _approve(t) if t and _reason_ok(t, dish, menu, request, n) else None


def _reason_ok(t: str, dish, menu, request, n: int = 0) -> bool:
    low = t.lower()
    if n and not count_ok(t, n):
        return False
    if not _dishes_ok(low, menu, {dish.id}):
        return False
    if not _spice_ok(low, [dish]) or not _diet_ok(low, [dish], request.diners):
        return False
    status = diner_status(dish, request.diners)  # the status the card renders (QA r15)
    for p in _named(t, request.diners):
        if status[p.id]["status"] != "ok":
            return False
    # "suitable for everyone" beside a card that says ask the server is false
    claims_all = _EVERYONE.search(low) or _SUITS_ALL.search(low)
    return not (claims_all and any(v["status"] != "ok" for v in status.values()))


def swap_clause(text: object, dish, menu, request) -> str | None:
    """The short 'why' in a swap note, checked for the new dish."""
    if not ai_prose():
        return None
    t = detoken(_clean(text, 120), request.diners)
    if not t or len(t.split()) > 10 or re.search(r"[;:]|\$\d", t):
        return None
    ok = set(edible_by(dish, request.diners))
    named = {p.id for p in _named(t, request.diners)}
    if named - ok:
        return None
    if (
        len(named) >= 2
        and named != ok
        and re.search(r"\b(can|could) (?:eat|have)|\bsuits?\b|\bfor\b", t, re.IGNORECASE)
    ):
        return None
    return _approve(t) if _reason_ok(t, dish, menu, request) else None


def change_note(text: object, menu, d: dict, after_ids, request_diners=()) -> str | None:
    """A refine note that already matched the real diff (refine.note_ok); the dish, spice
    and diet words are checked against the dishes it names."""
    if not ai_prose():
        return None
    t = detoken(_clean(text, 160), request_diners)
    if not t:
        return None
    low = t.lower()
    moved = set(d["added"]) | set(d["removed"]) | set(d["more"]) | set(d["fewer"])
    if not _dishes_ok(low, menu, moved | set(after_ids)):
        return None
    # The note may call the removed dish spicy; its heat claims about the result are checked
    # against the whole new order ("heat-free" while a little spicy dish stays is false).
    after = [menu.dish(i) for i in after_ids]
    if not _spice_ok(low, after, hot_words=False) or not _diet_ok(low, after, request_diners):
        return None
    return _approve(t)
