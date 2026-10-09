"""Hard-constraint check: can diner p eat dish d?

Explicit conflicts and unresolved evidence both exclude a dish from diner coverage.
A review establishes only no recorded evidence, never an allergy safety guarantee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from michelin.schemas import Allergen, Diet, DinerProfile, Dish, EvidenceTier

BLOCKING_TIERS = {EvidenceTier.MENU, EvidenceTier.INFERRED}


def blocking_allergens(dish: Dish, diner: DinerProfile) -> list[Allergen]:
    wanted = set(diner.allergies)
    return [f.allergen for f in dish.allergens if f.allergen in wanted and f.tier in BLOCKING_TIERS]


def blocking_diets(dish: Dish, diner: DinerProfile) -> list[Diet]:
    out: list[Diet] = []
    for diet in diner.diets:
        if (
            diet == Diet.VEGETARIAN
            and dish.is_vegetarian is not True
            or diet == Diet.VEGAN
            and dish.is_vegan is not True
            or diet == Diet.NO_PORK
            and dish.contains_pork is not False
            or diet == Diet.NO_BEEF
            and dish.contains_beef is not False
        ):
            out.append(diet)
    return out


def _diet_labeled_ok(dish: Dish, diet: Diet) -> bool:
    """The dish carries a positive label for this diet (e.g. is_vegetarian is True)."""
    field, required = DIET_FIELDS[diet]
    return getattr(dish, field) is required


DIET_FIELDS = {
    Diet.VEGETARIAN: ("is_vegetarian", True),
    Diet.VEGAN: ("is_vegan", True),
    Diet.NO_PORK: ("contains_pork", False),
    Diet.NO_BEEF: ("contains_beef", False),
}


def assessment(dish: Dish, diner: DinerProfile) -> dict:
    """Allergies are strict, diets ask (docs/decisions.md).

    - conflicts: recorded or inferred evidence against a restriction; never eligible.
    - unknown: unresolved allergen evidence, or a diet field with no label; not eligible.
    - ask: a dish positively labeled for a diet that only *possibly* contains a breaking
      ingredient (unknown tier). Eligible, with a question for the server.
    """
    conflicts, unknown, ask = [], [], []
    # A small explicit vocabulary is contradiction detection, not an ingredient
    # extractor. Unrecognized text never establishes absence or safety.
    terms = {
        "pork": (r"\bpork\b|猪肉", {Diet.VEGETARIAN, Diet.VEGAN, Diet.NO_PORK}, set()),
        "beef": (r"\bbeef\b|牛肉", {Diet.VEGETARIAN, Diet.VEGAN, Diet.NO_BEEF}, set()),
        "chicken": (r"\bchicken\b|鸡肉", {Diet.VEGETARIAN, Diet.VEGAN}, set()),
        "fish": (r"\bfish\b|\btilapia\b", {Diet.VEGETARIAN, Diet.VEGAN}, {Allergen.FISH}),
        "shellfish": (
            r"\bshrimp\b|\bprawn\b|\bcrab\b|\boyster sauce\b",
            {Diet.VEGETARIAN, Diet.VEGAN},
            {Allergen.SHELLFISH},
        ),
        "egg": (r"\beggs?\b", {Diet.VEGAN}, {Allergen.EGG}),
        "dairy": (r"\bmilk\b|\bbutter\b|\bcheese\b", {Diet.VEGAN}, {Allergen.DAIRY}),
        "sesame": (r"\bsesame\b", set(), {Allergen.SESAME}),
        "peanut": (r"\bpeanuts?\b", set(), {Allergen.PEANUT}),
    }
    for claim in dish.main_ingredients:
        for label, (pattern, diets, allergens) in terms.items():
            if re.search(pattern, claim.name, re.IGNORECASE) and (
                diets.intersection(diner.diets) or allergens.intersection(diner.allergies)
            ):
                # Substitutions/negations need review; do not certify an omission.
                ambiguous = re.search(
                    r"\b(no|without|free|vegan|substitute|omit|plant)\b", claim.name, re.IGNORECASE
                )
                if claim.tier in BLOCKING_TIERS and not ambiguous:
                    conflicts.append(
                        f"Recorded or inferred {label} ingredient conflicts with restrictions"
                    )
                elif not allergens.intersection(diner.allergies) and all(
                    _diet_labeled_ok(dish, d) for d in diets.intersection(diner.diets)
                ):
                    ask.append(f"Confirm {label} ingredient/preparation")
                else:
                    unknown.append(f"Confirm {label} ingredient/preparation")
    for allergen in diner.allergies:
        flags = [f for f in dish.allergens if f.allergen == allergen]
        if any(f.tier in BLOCKING_TIERS for f in flags):
            conflicts.append(f"Recorded or inferred {allergen.value} ingredient")
        elif (
            any(f.tier == EvidenceTier.UNKNOWN for f in flags)
            or allergen not in dish.reviewed_allergens
        ):
            unknown.append(f"Confirm {allergen.value}, including sauces and cross-contact")
    fields = DIET_FIELDS
    # Positive labels cannot erase contradictory recorded evidence. Allergen evidence
    # still wins over reviewed_allergens. Unknown claims remain confirmation questions.
    animal_allergens = {Allergen.FISH, Allergen.SHELLFISH}
    for diet in diner.diets:
        incompatible = animal_allergens | (
            {Allergen.EGG, Allergen.DAIRY} if diet == Diet.VEGAN else set()
        )
        if diet in {Diet.VEGETARIAN, Diet.VEGAN}:
            if dish.contains_pork is True or dish.contains_beef is True:
                conflicts.append(f"Recorded meat conflicts with {diet.value}")
            if diet == Diet.VEGAN and dish.is_vegetarian is False:
                conflicts.append("Non-vegetarian preparation conflicts with vegan")
            for flag in dish.allergens:
                if flag.allergen in incompatible:
                    if flag.tier in BLOCKING_TIERS:
                        conflicts.append(
                            f"Recorded or inferred {flag.allergen.value} conflicts with {diet.value}"
                        )
                    elif _diet_labeled_ok(dish, diet):
                        ask.append(f"Confirm {flag.allergen.value} for {diet.value} preparation")
                    else:
                        unknown.append(
                            f"Confirm {flag.allergen.value} for {diet.value} preparation"
                        )
        field, required = fields[diet]
        value = getattr(dish, field)
        if value is None:
            unknown.append(f"Confirm {diet.value} preparation")
        elif value != required:
            conflicts.append(f"Conflicts with {diet.value}")
    return {
        "status": "conflict"
        if conflicts
        else "requires_confirmation"
        if unknown or ask
        else "validated_under_known_data",
        "reasons": conflicts + unknown + [q for q in ask if q not in unknown],
        "eligible": not conflicts and not unknown,
    }


def can_eat(dish: Dish, diner: DinerProfile) -> bool:
    return assessment(dish, diner)["eligible"]


def edible_by(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    return [p.id for p in diners if can_eat(dish, p)]


def open_questions(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    """Staff questions that matter for someone at this table: the dish's own questions plus
    any `unknown`-tier flag that matches a diner's allergy."""
    questions = list(dish.confirm_with_staff)
    if dish.spice_level is None and (not diners or any(p.max_spice is not None for p in diners)):
        questions.append(f"{dish.name_en or dish.id}: spice level unknown. Confirm heat.")
    # One question per dish and concern, naming everyone it matters for (names, not ids).
    who: dict[str, list[str]] = {}
    for person in diners:
        for r in assessment(dish, person)["reasons"]:
            if r.startswith("Confirm"):
                who.setdefault(r, []).append(person.name or person.id)
    questions.extend(
        f"{dish.name_en or dish.id} (for {', '.join(names)}): {r}" for r, names in who.items()
    )
    table_allergies = {a for p in diners for a in p.allergies}
    for f in dish.allergens:
        if f.tier == EvidenceTier.UNKNOWN and f.allergen in table_allergies:
            label = dish.name_en or dish.name_zh or dish.id
            questions.append(f"{label}: {f.reason} (someone is allergic to {f.allergen.value})")
    return questions


def merge_questions(questions: list[str], dishes: list[Dish]) -> list[str]:
    """One line per dish for the server: "Eggplant (for Ben, Cai): ask whether it uses
    minced pork; confirm pork ingredient/preparation." Questions about no single dish stay."""
    labels = sorted({d.name_en or d.name_zh or d.id for d in dishes}, key=len, reverse=True)
    merged: dict[str, dict] = {}
    out: list = []
    for q in questions:
        q = q.strip()
        label = next(
            (
                lab
                for lab in labels
                if q.lower().startswith(lab.lower())
                and q[len(lab) : len(lab) + 1] in (":", " ")
                and (q[len(lab) :].lstrip().startswith((":", "(for ")))
            ),
            None,
        )
        if label is None:
            if q and q not in out:
                out.append(q)
            continue
        rest = q[len(label) :].strip()
        names: list[str] = []
        if rest.startswith("(for "):
            close = rest.find(")")
            names = [n.strip() for n in rest[5:close].split(",") if n.strip()]
            rest = rest[close + 1 :].strip()
        body = rest.lstrip(":").strip().rstrip(".")
        if label not in merged:
            merged[label] = {"names": [], "bodies": []}
            out.append(merged[label])
        entry = merged[label]
        entry["names"] += [n for n in names if n not in entry["names"]]
        if body and body.lower() not in (b.lower() for b in entry["bodies"]):
            entry["bodies"].append(body)
        entry["label"] = label
    lines = []
    for item in out:
        if isinstance(item, str):
            lines.append(item)
            continue
        who = f" (for {', '.join(item['names'])})" if item["names"] else ""
        bodies = [b[0].lower() + b[1:] if i else b for i, b in enumerate(item["bodies"])]
        text = "; ".join(bodies)
        lines.append(f"{item['label']}{who}: {text}{'' if text.endswith('?') else '.'}")
    return lines


# Words that show a server question covers a risk ("lard" covers a pork risk, etc.).
_SYNONYMS = {
    "pork": ["pork", "lard", "bacon"],
    "lard": ["lard", "pork"],
    "beef": ["beef"],
    "chicken": ["chicken", "meat"],
    "fish": ["fish", "seafood", "anchov"],
    "shellfish": ["shellfish", "shrimp", "prawn", "crab", "oyster", "seafood"],
    "peanut": ["peanut"],
    "tree_nut": ["nut", "cashew", "almond", "walnut"],
    "egg": ["egg"],
    "dairy": ["dairy", "milk", "butter", "cream", "cheese"],
    "wheat": ["wheat", "gluten", "flour"],
    "soy": ["soy"],
    "sesame": ["sesame"],
    "vegetarian": ["vegetarian", "meat", "animal", "pork", "lard", "chicken", "broth"],
    "vegan": ["vegan", "animal", "egg", "dairy", "meat", "lard"],
    "no_pork": ["pork", "lard"],
    "no_beef": ["beef"],
}
_STOP = {"with", "from", "that", "this", "uses", "used", "sauce", "made", "fresh", "dried"}


@dataclass
class Risk:
    """Something the rules flag for this dish that a server question must cover."""

    about: str  # e.g. "pork", "sesame", "spice level"
    names: list[str]  # diners it matters for; empty = the whole table
    words: list[str]  # any of these in a question counts as covering it
    question: str  # the rule-based question, used if the model's question misses it

    def covered_by(self, text: str) -> bool:
        low = text.lower()
        return any(w in low for w in self.words) and all(n.lower() in low for n in self.names)


def _words(term: str) -> list[str]:
    key = term.lower().strip().replace(" ", "_")
    if key in _SYNONYMS:
        return _SYNONYMS[key]
    words = [w for w in re.findall(r"[a-z]+", term.lower()) if len(w) > 3 and w not in _STOP]
    for w in list(words):
        words += _SYNONYMS.get(w, [])
    return list(dict.fromkeys(words)) or [term.lower()]


def risks(dish: Dish, diners: list[DinerProfile]) -> list[Risk]:
    """The rule-flagged risks behind open_questions, one per dish and concern."""
    label = dish.name_en or dish.name_zh or dish.id
    out: list[Risk] = []
    for q in dish.confirm_with_staff:
        m = re.search(r"uses (.+?)\.?$", q)
        about = m.group(1) if m else "ingredients"
        words = _words(about) if m else ["ingredient", "allergen", "contain", "made", "use"]
        out.append(Risk(about, [], words, q))
    hot = [p.name or p.id for p in diners if p.max_spice is not None]
    if dish.spice_level is None and hot:
        out.append(
            Risk(
                "spice level",
                [],
                ["spic", "heat", "hot", "chili", "mild"],
                f"{label}: spice level unknown. Confirm heat.",
            )
        )
    who: dict[str, list[str]] = {}
    for person in diners:
        for r in assessment(dish, person)["reasons"]:
            if r.startswith("Confirm"):
                who.setdefault(r, []).append(person.name or person.id)
    for reason, names in who.items():
        term = re.match(r"Confirm (\S+?)(,| ingredient| for| preparation|$)", reason)
        about = term.group(1) if term else reason
        out.append(Risk(about, names, _words(about), f"{label} (for {', '.join(names)}): {reason}"))
    table = {a for p in diners for a in p.allergies}
    for f in dish.allergens:
        if f.tier == EvidenceTier.UNKNOWN and f.allergen in table:
            names = [p.name or p.id for p in diners if f.allergen in p.allergies]
            if any(r.about == f.allergen.value and r.names == names for r in out):
                continue
            out.append(
                Risk(
                    f.allergen.value,
                    names,
                    _words(f.allergen.value),
                    f"{label}: {f.reason} (someone is allergic to {f.allergen.value})",
                )
            )
    return out
