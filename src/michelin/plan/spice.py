"""The one spice source (2026-10-10): every tag, reason, swap hint, note, refine message and
the planner read a dish's heat and a diner's heat limit from here.

Dish heat: the larger of the dish's recorded spice_level and the menu's printed peppers
(menu_spice), 0-3. Diner limit: "no heat" (no_spicy, or a note such as "no spicy food") may
be listed for at most "a little spicy" dishes, flagged; "mild" likewise allows up to
"a little spicy". Spicy / Very spicy is a taste conflict for both: never listed for them.
"""

import re

LABELS = ["Not spicy", "A little spicy", "Spicy", "Very spicy"]
WORDS = [w.lower() for w in LABELS]
_AVOIDS = re.compile(
    r"\b(no|not|avoids?|hates?|without|can't|cannot|don't)\b[^.;]*\b(spic|heat|hot|chil)"
    r"|\bmild\b|不吃辣|不辣",
    re.IGNORECASE,
)


# Dishes known to be spicy wherever they are cooked (QA r20: Kung Pao, Mapo were "a little").
_KNOWN = re.compile(
    r"kung ?pao|gong ?bao|ma ?po|dan ?dan|chong ?qing|la ?zi ji|sichuan boiled|water[- ]boiled|"
    r"hot pot|mala|ma la|宫保|宮保|麻婆|担担|擔擔|辣子鸡|辣子雞|水煮|麻辣",
    re.IGNORECASE,
)


def known(dish) -> int:
    text = f"{dish.name_en or ''} {dish.name_zh or ''} {dish.family_name or ''}"
    if _KNOWN.search(text) and not re.search(r"\bmild\b|不辣", text, re.IGNORECASE):
        return 2
    return 0


def level(dish) -> int:
    """Printed peppers, the AI's facts and known dishes: whichever is hottest."""
    if dish is None:
        return 0
    return min(max(dish.spice_level or 0, dish.menu_spice or 0, known(dish), 0), 3)


def label(dish) -> str | None:
    """The card's tag, or None for a dish that is not spicy."""
    n = level(dish)
    return LABELS[n] if n else None


def word(n: int) -> str:
    return WORDS[min(max(n, 0), 3)]


def _prefs(p) -> set[str]:
    return {getattr(x, "value", x) for x in (p.preferences or [])}


def no_heat(p) -> bool:
    """The diner avoids heat: the "no spicy" / "mild" chip or their own note."""
    return bool(_prefs(p) & {"no_spicy", "mild"}) or bool(_AVOIDS.search(p.notes or ""))


def taste(dish, p) -> str | None:
    """'too_spicy' (a taste conflict: not listed for them), 'a_little_spicy' (listed, flagged
    for a no-heat diner), or None."""
    if not no_heat(p):
        return None
    n = level(dish)
    if n >= 2:
        return "too_spicy"
    if n == 1 and _prefs(p) & {"no_spicy", "mild"} != {"mild"}:
        return "a_little_spicy"  # "mild" alone allows a little; "no heat" gets a flag
    return None


def too_spicy_for(dish, diners) -> list:
    return [p for p in diners if taste(dish, p) == "too_spicy"]


def _join(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def heat_note(dish, diners) -> str | None:
    """The card's note: 'Too spicy for <names>' / 'A little spicy for <names>, who avoid heat'."""
    hot = [p.name or p.id for p in diners if taste(dish, p) == "too_spicy"]
    little = [p.name or p.id for p in diners if taste(dish, p) == "a_little_spicy"]
    parts = []
    # the level itself is the card's tag; this says only who it concerns (QA r21)
    if hot:
        parts.append(f"Not for {_join(hot)}, who {'avoids' if len(hot) == 1 else 'avoid'} heat")
    if little:
        parts.append(
            f"{_join(little)} {'avoids' if len(little) == 1 else 'avoid'} heat; ask for it mild"
        )
    return "; ".join(parts) or None
