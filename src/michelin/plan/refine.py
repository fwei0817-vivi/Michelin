"""Feedback-driven refinement of the current order ("less spicy", "cheaper", free text).

The AI revises the table's current order and writes a one-line note of what it changed. The
code computes the real changes (the truth) and keeps the note only if its claims match them;
otherwise the note is written from the changes.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from michelin.schemas import Menu

CHIPS = {
    "less_spicy": "Make it less spicy: replace dishes with spice 2-3 by milder ones.",
    "more_seafood": "More seafood: include more fish or shellfish dishes for those who can eat them.",
    "more_veggies": "More vegetables: include more vegetable or tofu dishes.",
    "cheaper": "Cheaper: lower the total, e.g. swap expensive dishes for cheaper ones.",
    "more_filling": "More filling: add or swap in heartier dishes (noodles, rice dishes, "
    "meat or tofu mains) within the budget.",
    "something_different": "Something different: change at least two of the dishes that are "
    "not kept.",
}


class CurrentItem(BaseModel):
    dish_id: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1, le=20)


class Feedback(BaseModel):
    chips: list[str] = Field(default_factory=list, max_length=6)
    text: str = Field(default="", max_length=200)
    current: list[CurrentItem] = Field(min_length=1, max_length=40)
    # Set by the server on its one retry: why the last revision missed the goal.
    fix: list[str] = Field(default_factory=list, exclude=True)

    def asks(self) -> list[str]:
        out = [CHIPS[c] for c in self.chips if c in CHIPS]
        if self.text.strip():
            out.append("In their words: " + self.text.strip())
        out += [f"Your last revision did not do this: {f}" for f in self.fix]
        return out


REVISE = """The table saw "current_order" and asked for changes ("feedback"). Revise that \
order: make the changes the feedback asks for, keep the kept dishes, and keep the other \
current dishes unless changing them serves the feedback. Every hard rule still applies. \
Also return "change_note": ONE line (under 15 words) saying what you changed, e.g. \
"Swapped 2 spicy dishes for milder ones" or "Added a seafood dish, dropped the pork belly"."""

_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a": 1, "an": 1}
_SEAFOOD = re.compile(
    r"shrimp|prawn|fish|crab|lobster|scallop|squid|clam|oyster|seafood|鱼|虾", re.IGNORECASE
)


def _spice(d) -> int:
    return d.spice_level if d.spice_level is not None else d.menu_spice or 0


def _seafood(d) -> bool:
    return bool(_SEAFOOD.search(f"{d.name_en or ''} {d.name_zh or ''}")) or any(
        f.allergen.value in ("fish", "shellfish") and f.tier.value != "unknown" for f in d.allergens
    )


def _veg(d) -> bool:
    return d.is_vegetarian is True or "vegetarian" in [m.value for m in d.menu_marks]


def diff(menu: Menu, before: list[tuple[str, int]], after: list[tuple[str, int]]) -> dict:
    """What actually changed (the truth any note is checked against)."""
    known = {d.id: d for d in menu.dishes}
    b, a = dict(before), dict(after)
    added = [i for i in a if i not in b and i in known]
    removed = [i for i in b if i not in a and i in known]
    more = [i for i in a if i in b and a[i] > b[i]]
    fewer = [i for i in a if i in b and a[i] < b[i]]

    def total(rows, f):
        return sum(f(known[i]) * q for i, q in rows.items() if i in known)

    return {
        "added": added,
        "removed": removed,
        "more": more,
        "fewer": fewer,
        "price": round(total(a, lambda d: d.price or 0) - total(b, lambda d: d.price or 0), 2),
        "spice": total(a, _spice) - total(b, _spice),
        "seafood": total(a, _seafood) - total(b, _seafood),
        "veg": total(a, _veg) - total(b, _veg),
        "dishes": sum(a.values()) - sum(b.values()),
        "names": {i: known[i].name_en or known[i].name_zh or i for i in {*a, *b} if i in known},
        "spice_of": {i: _spice(known[i]) for i in {*a, *b} if i in known},
        "menu_names": {d.id: d.name_en or "" for d in menu.dishes},
    }


GOAL_TEXT = {
    "less_spicy": "make it less spicy",
    "cheaper": "make it cheaper",
    "more_seafood": "add more seafood",
    "more_veggies": "add more vegetables",
    "more_filling": "make it more filling",
    "something_different": "change at least half of the dishes",
}


ALREADY_MILD = "Already gentle: nothing here is more than a little spicy."


def already_mild(menu: Menu, before, locked=()) -> bool:
    """Every dish that is not kept (rice aside) is spice 1 or less: 'less spicy' is met."""
    known = {x.id: x for x in menu.dishes}
    return all(
        _spice(known[i]) <= 1
        for i, _ in before
        if i in known and i not in set(locked) and known[i].category.value != "staple"
    )


def unmet(
    chips: list[str], menu: Menu, before, after, locked=(), d: dict | None = None
) -> list[str]:
    """The chips whose goal the revision did not reach, checked on the real orders:
    less spicy = remove or swap a spicy (non-kept) dish so the max or average spice of the
    non-kept dishes drops; cheaper = total drops; more seafood/veggies = count rises; more
    filling = more dishes, or a dearer dish added; something different = at least half of the
    non-kept dishes change. A goal already met before (nothing spicy to remove) counts as met."""
    known = {x.id: x for x in menu.dishes}
    d = d or diff(menu, before, after)
    locked = set(locked)

    def free(rows):
        return [
            (i, q)
            for i, q in rows
            if i in known and i not in locked and known[i].category.value != "staple"
        ]

    fb, fa = free(before), free(after)
    simple = {
        "cheaper": d["price"] < 0,
        "more_seafood": d["seafood"] > 0,
        "more_veggies": d["veg"] > 0,
        "more_filling": d["dishes"] > 0 or bool(d["added"] and d["price"] > 0),
    }
    out = []
    for chip in chips:
        if chip == "less_spicy":
            if already_mild(menu, before, locked):
                continue
            # One rule (QA r11): the order's highest pepper level must strictly drop. Fewer
            # spicy dishes alone does not count (dropping a mild dish keeps the hottest one).
            sb = [_spice(known[i]) for i, q in fb for _ in range(q)] or [0]
            sa = [_spice(known[i]) for i, q in fa for _ in range(q)] or [0]
            if not max(sa) < max(sb):
                out.append(chip)
        elif chip in simple and not simple[chip]:
            out.append(chip)
        elif chip == "something_different":
            ids = {i for i, _ in fb}
            changed = len(ids & set(d["removed"]))
            if ids and changed * 2 < len(ids):
                out.append(chip)
    return out


def missed_text(chips: list[str], d: dict) -> list[str]:
    """Why, in words for the model's retry."""
    n = d["names"]
    added = ", ".join(n[i] for i in d["added"]) or "nothing"
    removed = ", ".join(n[i] for i in d["removed"]) or "nothing"
    return [
        f"{GOAL_TEXT[c]} (you added {added} and removed {removed}; "
        + {
            "less_spicy": "remove or swap at least one spicy dish that is not kept",
            "cheaper": f"the menu prices went {'up' if d['price'] > 0 else 'unchanged'}",
            "more_seafood": "include more fish or shellfish dishes",
            "more_veggies": "include more vegetable or tofu dishes",
            "more_filling": "add a dish or swap in a heartier one within the budget",
            "something_different": "replace at least half of the dishes that are not kept",
        }[c]
        + ")"
        for c in chips
    ]


def honest_note(chips: list[str], d: dict, menu: Menu | None = None, after=()) -> str:
    """Said plainly when a goal was not met, even after one retry."""
    goals = " or ".join(GOAL_TEXT[c] for c in chips)
    if not (d["added"] or d["removed"] or d["more"] or d["fewer"]):
        extra = ""
        if "less_spicy" in chips and menu is not None:
            known = {x.id: x for x in menu.dishes}
            top = max((_spice(known[i]) for i, _ in after if i in known), default=0)
            extra = f" Its spiciest dish is {['not spicy', 'a little spicy', 'spicy', 'very spicy'][min(top, 3)]}."
        return f"Couldn't {goals}: the AI kept the same order.{extra}"
    return (
        f"Couldn't fully {goals} within everyone's allergies, diets, kept dishes and the "
        f"budget. {code_note(d)}"
    )


def changes_list(d: dict) -> list[str]:
    n = d["names"]
    out = [f"Added {n[i]}" for i in d["added"]] + [f"Removed {n[i]}" for i in d["removed"]]
    out += [f"More {n[i]}" for i in d["more"]] + [f"Less {n[i]}" for i in d["fewer"]]
    if d["price"]:
        out.append(f"Menu prices ${abs(d['price']):.2f} {'lower' if d['price'] < 0 else 'higher'}")
    return out


SPICE_WORDS = ["not spicy", "a little spicy", "spicy", "very spicy"]


def not_less_spicy(menu: Menu, before) -> str:
    known = {x.id: x for x in menu.dishes}
    top = max((_spice(known[i]) for i, _ in before if i in known), default=0)
    return (
        "Couldn't make it less spicy within everyone's allergies, diets, kept dishes and the "
        f"budget, so the order is unchanged. Its spiciest dish is {SPICE_WORDS[min(top, 3)]}."
    )


def spice_note(d: dict) -> str:
    """The less-spicy note, from the real changes in the cards' words: "Swapped Cucumber
    Salad (Spicy Chili Oil) (spicy) for Chilled Zucchini (a little spicy)."."""
    n, s = d["names"], d.get("spice_of", {})

    def say(i):
        return f"{n[i]} ({SPICE_WORDS[min(max(s.get(i, 0), 0), 3)]})"

    if d["added"] and d["removed"]:
        text = f"Swapped {', '.join(map(say, d['removed']))} for {', '.join(map(say, d['added']))}"
    elif d["removed"]:
        text = f"Removed {', '.join(map(say, d['removed']))}"
    elif d["added"]:
        text = f"Added {', '.join(map(say, d['added']))}"
    else:
        return code_note(d)
    if d["more"] or d["fewer"]:
        text += "; changed portions"
    if d["price"]:
        text += f"; ${abs(d['price']):.2f} {'less' if d['price'] < 0 else 'more'} in menu prices"
    return text + "."


def code_note(d: dict) -> str:
    """The note written from the real changes."""
    n = d["names"]
    if not (d["added"] or d["removed"] or d["more"] or d["fewer"]):
        return "No dish changed: the current order already fits that request best."
    parts = []
    if d["added"] and d["removed"]:
        parts.append(
            f"Swapped {', '.join(n[i] for i in d['removed'])} for {', '.join(n[i] for i in d['added'])}"
        )
    elif d["added"]:
        parts.append(f"Added {', '.join(n[i] for i in d['added'])}")
    elif d["removed"]:
        parts.append(f"Removed {', '.join(n[i] for i in d['removed'])}")
    if d["more"] or d["fewer"]:
        parts.append("changed portions")
    if d["price"]:
        parts.append(
            f"${abs(d['price']):.2f} {'less' if d['price'] < 0 else 'more'} in menu prices"
        )
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def note_ok(note: str, d: dict) -> bool:
    """The AI's note may only claim what the diff shows."""
    low = note.lower().strip()
    if not low or len(low) > 160:
        return False
    changed = bool(d["added"] or d["removed"] or d["more"] or d["fewer"])
    if not changed:
        return bool(
            re.search(
                r"\b(no change|unchanged|kept (?:the same|all|every)|same order|nothing changed)",
                low,
            )
        )
    if re.search(r"\b(no change|unchanged|nothing changed|same order)\b", low):
        return False
    counts = {
        len(d["added"]),
        len(d["removed"]),
        len(d["added"]) + len(d["removed"]),
        len(d["more"]) + len(d["fewer"]),
        abs(d["dishes"]),
    }
    for m in re.finditer(
        r"\b(\d+|one|two|three|four|five|six)\s+(?:\w+\s+){0,2}?(dish|dishes|plates?)\b", low
    ):
        word = m.group(1)
        if (int(word) if word.isdigit() else _NUMS[word]) not in counts:
            return False
    if re.search(r"\b(swap|swapped|replac)", low) and not (d["added"] and d["removed"]):
        return False
    if re.search(r"\badd(ed|s)?\b", low) and not (d["added"] or d["more"]):
        return False
    if re.search(r"\b(drop|dropped|remov)", low) and not (d["removed"] or d["fewer"]):
        return False
    if re.search(r"milder|less spicy|less heat|cooler|not as spicy", low) and d["spice"] >= 0:
        return False
    if re.search(r"spicier|more spicy|more heat", low) and d["spice"] <= 0:
        return False
    if (
        re.search(
            r"cheaper|lower (?:price|cost|total|bill)|saves?|less expensive|cut (?:the )?cost", low
        )
        and d["price"] >= 0
    ):
        return False
    if (
        re.search(r"(more|added?|extra)\s+(?:\w+\s+)?(seafood|fish|shrimp)", low)
        and d["seafood"] <= 0
    ):
        return False
    if (
        re.search(r"(more|added?|extra)\s+(?:\w+\s+)?(veg|vegetable|veggie|greens)", low)
        and d["veg"] <= 0
    ):
        return False
    moved = {*d["added"], *d["removed"], *d["more"], *d["fewer"]}
    for dish_id, name in d.get("menu_names", {}).items():
        # A dish the note names must really have been added, removed or changed.
        if len(name) >= 5 and name.lower() in low and dish_id not in moved:
            return False
    if not _names_match(low, d):
        return False
    if re.search(r"\$\s*(\d+(?:\.\d+)?)", low):
        claimed = float(re.search(r"\$\s*(\d+(?:\.\d+)?)", low).group(1))
        if abs(claimed - abs(d["price"])) > 0.5:
            return False
    return True


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
}


def _tokens(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 4 and w not in _GENERIC}


def _names_match(low: str, d: dict) -> bool:
    """Words of dish names in the note must point at dishes that really moved (QA r8 AD-1:
    "swapped the spicy cucumber for a garlic one" when Garlic Cucumber was already on the
    order and Chilled Zucchini was the one added)."""
    said = set(re.findall(r"[a-z]+", low))
    moved = {*d["added"], *d["removed"], *d["more"], *d["fewer"]}
    names = d.get("names", {})
    moved_words = set().union(*(_tokens(names.get(i, "")) for i in moved)) if moved else set()
    for dish_id, name in names.items():
        if dish_id in moved:
            continue
        if (_tokens(name) - moved_words) & said:
            return False
    return True


def card_words(note: str, d: dict) -> str:
    """The cards' spice words in the note (QA r9): one pepper is "a little spicy", never
    "mild"; a dish with no pepper is "not spicy"."""
    levels = {d.get("spice_of", {}).get(i, 0) for i in d["added"]}
    if not levels or not re.search(r"\bmild\b", note, re.IGNORECASE):
        return note
    word = "a little spicy" if levels == {1} else "non-spicy" if levels == {0} else None
    if word is None:
        return note
    note = re.sub(r"\ban? mild\b", word, note, flags=re.IGNORECASE)
    return re.sub(r"\bmild\b", word, note, flags=re.IGNORECASE)


def final_note(ai_note: str | None, d: dict) -> tuple[str, bool]:
    """(note, from_ai): the AI's note when its claims match the diff, else the code's."""
    note = re.sub(r"\s+", " ", str(ai_note or "")).strip()
    if note and note_ok(note, d):
        return card_words(note, d).rstrip(".") + ".", True
    return code_note(d), False
