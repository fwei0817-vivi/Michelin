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

    def asks(self) -> list[str]:
        out = [CHIPS[c] for c in self.chips if c in CHIPS]
        if self.text.strip():
            out.append("In their words: " + self.text.strip())
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
    }


def changes_list(d: dict) -> list[str]:
    n = d["names"]
    out = [f"Added {n[i]}" for i in d["added"]] + [f"Removed {n[i]}" for i in d["removed"]]
    out += [f"More {n[i]}" for i in d["more"]] + [f"Less {n[i]}" for i in d["fewer"]]
    if d["price"]:
        out.append(f"Menu prices ${abs(d['price']):.2f} {'lower' if d['price'] < 0 else 'higher'}")
    return out


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
            re.search(r"\b(no change|unchanged|kept the same|same order|nothing changed)", low)
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
    if re.search(r"\$\s*(\d+(?:\.\d+)?)", low):
        claimed = float(re.search(r"\$\s*(\d+(?:\.\d+)?)", low).group(1))
        if abs(claimed - abs(d["price"])) > 0.5:
            return False
    return True


def final_note(ai_note: str | None, d: dict) -> tuple[str, bool]:
    """(note, from_ai): the AI's note when its claims match the diff, else the code's."""
    note = re.sub(r"\s+", " ", str(ai_note or "")).strip()
    if note and note_ok(note, d):
        return note.rstrip(".") + ".", True
    return code_note(d), False
