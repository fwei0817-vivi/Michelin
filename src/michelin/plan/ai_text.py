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

import re

from michelin.plan.edibility import assessment, edible_by

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


def _approve(text: str) -> str:
    if len(APPROVED) < _MAX_APPROVED:
        APPROVED.add(text)
    return text


def _clean(text: object, limit: int = 240) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def _tokens(name: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (name or "").lower()) if len(w) >= 4} - _GENERIC


def _spice(d) -> int:
    return max(d.spice_level or 0, d.menu_spice or 0) if d is not None else 0


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


def summary(text: object, menu, request, items) -> str | None:
    """The plan subtitle, checked against the order it will be shown with."""
    t = _clean(text)
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
    r"\bpreferences?\b|\baccommodat\w*\s+(?:\w+\s+){0,2}?all\b|\beveryone'?s?\s+needs\b",
    re.IGNORECASE,
)
_CHECKABLE_PREFS = {"no_spicy", "mild"}


def _pref_ok(dish, person) -> bool:
    prefs = {getattr(x, "value", x) for x in person.preferences}
    if prefs - _CHECKABLE_PREFS:
        return False  # a taste the code cannot check: the claim is not provable
    heat = _spice(dish)
    return not (("no_spicy" in prefs and heat >= 1) or ("mild" in prefs and heat >= 2))


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


def code_summary(menu, request, items) -> str:
    """A true one-liner when the AI's summary fails (or there is none)."""
    shared = [
        menu.dish(i.dish_id) for i in items if menu.dish(i.dish_id).category.value != "staple"
    ]
    counts = {p.id: sum(p.id in edible_by(d, [p]) for d in shared) for p in request.diners}
    low = min(counts.values(), default=0)
    top = max((_spice(d) for d in shared), default=0)
    heat = ["nothing spicy", "at most a little spicy", "up to spicy", "up to very spicy"][
        min(top, 3)
    ]
    who = (
        "everyone has at least " + (f"{low} dishes" if low != 1 else "one dish") + " they can eat"
        if low
        else "not everyone has a dish they can eat"
    )
    return f"{len(shared)} dish{'es' if len(shared) != 1 else ''} to share; {who}; {heat}."


def reason(text: object, dish, menu, request, n: int = 0) -> str | None:
    """A per-dish reason, checked for this dish on this order."""
    t = _clean(text, 200)
    if not t:
        return None
    low = t.lower()
    if n and not count_ok(t, n):
        return None
    if not _dishes_ok(low, menu, {dish.id}):
        return None
    if not _spice_ok(low, [dish]) or not _diet_ok(low, [dish], request.diners):
        return None
    for p in _named(t, request.diners):
        if assessment(dish, p)["status"] != "validated_under_known_data":
            return None
    if _EVERYONE.search(low) and len(edible_by(dish, request.diners)) < len(request.diners):
        return None
    return _approve(t)


def swap_clause(text: object, dish, menu, request) -> str | None:
    """The short 'why' in a swap note, checked for the new dish."""
    t = _clean(text, 120)
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
    return _approve(t) if reason(t, dish, menu, request) is not None else None


def change_note(text: object, menu, d: dict, after_ids, request_diners=()) -> str | None:
    """A refine note that already matched the real diff (refine.note_ok); the dish, spice
    and diet words are checked against the dishes it names."""
    t = _clean(text, 160)
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
