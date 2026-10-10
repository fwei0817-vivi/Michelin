"""Hard-constraint check: can diner p eat dish d?

Explicit conflicts and unresolved evidence both exclude a dish from diner coverage.
A review establishes only no recorded evidence, never an allergy safety guarantee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from michelin import keywords
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
    # The shared keyword list (michelin/data/keywords.json) is contradiction detection, not
    # an ingredient extractor. Unrecognized text never establishes absence or safety.
    veg = {Diet.VEGETARIAN, Diet.VEGAN}
    terms = {
        "pork": (keywords.regex("pork"), veg | {Diet.NO_PORK}, set()),
        "beef": (keywords.regex("beef"), veg | {Diet.NO_BEEF}, set()),
        "meat": (keywords.regex("meat"), veg, set()),
        "meat stock": (keywords.regex("stock"), veg, set()),
        "fish": (keywords.regex("fish"), veg, {Allergen.FISH}),
        "shellfish": (keywords.regex("shellfish"), veg, {Allergen.SHELLFISH}),
        "egg": (keywords.regex("egg"), {Diet.VEGAN}, {Allergen.EGG}),
        "dairy": (keywords.regex("dairy"), {Diet.VEGAN}, {Allergen.DAIRY}),
        "sesame": (keywords.regex("sesame"), set(), {Allergen.SESAME}),
        "peanut": (keywords.regex("peanut"), set(), {Allergen.PEANUT}),
        "tree nut": (keywords.regex("tree_nut"), set(), {Allergen.TREE_NUT}),
        "soy": (keywords.regex("soy"), set(), {Allergen.SOY}),
        "wheat": (keywords.regex("wheat"), set(), {Allergen.WHEAT}),
    }
    # Words printed on the menu (names, description, variant) for this diner's allergens.
    printed_text = keywords.dish_text(dish).lower()
    for allergen in diner.allergies:
        word = keywords.found(allergen.value, printed_text)
        if word:
            conflicts.append(f"Recorded or inferred {allergen.value} ingredient ({word})")
    for claim in dish.main_ingredients:
        for label, (pattern, diets, allergens) in terms.items():
            if pattern.search(claim.name) and (
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
    # The diner's own allergies and diets, in their words (Yukino, 2026-10-09). Allergies:
    # likely (or printed) excludes; possible or no answer is allowed with a server question.
    # Diets: likely excludes, possible asks, no answer is not offered and asks. The nine
    # standard allergens above keep the strict rule.
    custom = {(f.kind, f.term): f for f in dish.custom_flags}
    for term in diner.other_allergies:
        flag = custom.get(("allergy", term))
        answer = flag.answer if flag else "unknown"
        if answer == "likely":
            conflicts.append(f"Contains {term}" + (" (on the menu)" if flag.printed else ""))
        elif answer == "possible":  # allowed, asking the kitchen to leave it out
            ask.append(f"Confirm {term.replace(' ', '_')}, can it be left out")
        elif answer != "no":  # no answer: allowed, with a question
            ask.append(f"Confirm {term.replace(' ', '_')} ingredient/preparation")
    for term in diner.other_diets:
        flag = custom.get(("diet", term))
        answer = flag.answer if flag else "unknown"
        if answer == "likely":
            conflicts.append(f"Breaks {term}" + (" (on the menu)" if flag.printed else ""))
        elif answer == "possible":
            ask.append(f"Confirm {term.replace(' ', '_')} preparation")
        elif answer != "no":
            unknown.append(f"Confirm {term.replace(' ', '_')} preparation")
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
    # QA r20 WM-1: the English and Chinese names describe different dishes (a misread):
    # what is in it is uncertain, so anyone with an allergy or diet must ask, never "ok".
    restricted = diner.allergies or diner.diets or diner.other_allergies or diner.other_diets
    if getattr(dish, "names_clash", None) and restricted and not conflicts:
        ask.append(
            "The menu's English and Chinese names don't match; ask what this dish is and "
            "what is in it"
        )
    return {
        "status": "conflict"
        if conflicts
        else "requires_confirmation"
        if unknown or ask
        else "validated_under_known_data",
        "reasons": conflicts + unknown + [q for q in ask if q not in unknown],
        # What keeps the dish off this diner's list (empty when eligible): cards show only
        # these for an excluded dish, not the questions that would merely be asked.
        "blocking": conflicts + unknown,
        "eligible": not conflicts and not unknown,
    }


def diner_status(dish: Dish, diners: list[DinerProfile]) -> dict[str, dict]:
    """The one per-dish, per-diner status every surface reads (QA r15): the card chips, the
    swap hint and the code-written reason. "ok": eat it; "needs_confirm": eat it once the
    server confirms (reason says what); "no": not for them (reason says why).
    "taste" (2026-10-10) is the soft taste conflict, from plan.spice: "too_spicy" (not
    listed for them anywhere), "a_little_spicy" (listed, flagged) or None."""
    from michelin.plan import spice

    out = {}
    for p in diners:
        a = assessment(dish, p)
        if not a["eligible"]:
            out[p.id] = {"status": "no", "reason": "; ".join(a["blocking"]) or None}
        elif a["status"] == "requires_confirmation":
            out[p.id] = {"status": "needs_confirm", "reason": "; ".join(a["reasons"]) or None}
        else:
            out[p.id] = {"status": "ok", "reason": None}
        out[p.id]["taste"] = spice.taste(dish, p) if out[p.id]["status"] != "no" else None
    return out


def for_whom(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    """Who a dish is listed / recommended / counted for: allowed by allergies and diets AND
    no taste conflict (not too spicy for a no-heat diner). edible_by stays the hard
    allergy/diet floor."""
    from michelin.plan import spice

    return [p.id for p in diners if can_eat(dish, p) and spice.taste(dish, p) != "too_spicy"]


def veg_tag(dish: Dish, diners: list[DinerProfile] | None = None) -> str | None:
    """The vegetarian/vegan tag the cards show (QA r16), from the backend's own diet check
    for a diner with only that diet, so another diner's halal or allergy never changes it:
    "vegan"/"vegetarian" (settled), "ask_vegan"/"ask_vegetarian" (the server must confirm),
    or None (no tag)."""
    if dish.is_vegetarian is not True:
        return None
    # QA r17: "vegan" only when a vegan diner is at the table; vegetarians see "vegetarian"
    vegan_here = diners is None or any(Diet.VEGAN in (p.diets or []) for p in diners)
    diet = Diet.VEGAN if dish.is_vegan is True and vegan_here else Diet.VEGETARIAN
    probe = DinerProfile(id="_veg", name="_veg", diets=[diet])
    status = diner_status(dish, [probe])["_veg"]["status"]
    if status == "no":
        return None
    return ("ask_" if status == "needs_confirm" else "") + diet.value


def can_eat(dish: Dish, diner: DinerProfile) -> bool:
    return assessment(dish, diner)["eligible"]


def edible_by(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    return [p.id for p in diners if can_eat(dish, p)]


_DIET_ASK = {
    "vegetarian": "Is it vegetarian, with no meat, seafood or meat broth?",
    "vegan": "Is it vegan, with no meat, seafood, egg, dairy or meat broth?",
    "no_pork": "Is there any pork or lard in it?",
    "no_beef": "Is there any beef in it?",
    "no_alcohol": "Is there any alcohol or cooking wine in it?",
    "halal": "Is it halal, with no pork, lard or alcohol, and halal meat?",
    "kosher": "Is it kosher, with no pork or shellfish?",
}


def natural(reason: str) -> str:
    """A rule's "Confirm …" note as a question a diner could ask the server (QA r6):
    "Confirm peanut ingredient/preparation" -> "Is there any peanut in it?"."""
    m = re.fullmatch(r"Confirm (.+?), can it be left out", reason)
    if m:
        return f"Can it be made without {m.group(1).replace('_', ' ')}?"
    m = re.fullmatch(r"Confirm (.+?), including sauces and cross-contact", reason)
    if m:
        x = m.group(1).replace("_", " ")
        return f"Is there any {x} in it, including the sauce, and is it kept apart from {x}?"
    m = re.fullmatch(r"Confirm (.+?) ingredient/preparation", reason)
    if m:
        return f"Is there any {m.group(1).replace('_', ' ')} in it?"
    m = re.fullmatch(r"Confirm (.+?) for (.+?) preparation", reason)
    if m:
        return f"Is there any {m.group(1).replace('_', ' ')} in it? It needs to be {m.group(2)}."
    m = re.fullmatch(r"Confirm (.+?) preparation", reason)
    if m:
        diet = m.group(1).replace("_", " ")
        if diet.startswith("no "):
            return _DIET_ASK.get(m.group(1), f"Is there any {diet[3:]} in it?")
        return _DIET_ASK.get(m.group(1), f"Is it {diet}?")
    return reason


def open_questions(dish: Dish, diners: list[DinerProfile]) -> list[str]:
    """Staff questions that matter for someone at this table: the dish's own questions plus
    any `unknown`-tier flag that matches a diner's allergy."""
    # Only the dish's own questions that touch someone here ("uses bamboo shoots" asks
    # nothing of a table without such an allergy or diet).
    questions = []
    for q in dish.confirm_with_staff:
        m = re.search(r"uses (.+?)\.?$", q)
        if not m or not diners or any(_matters(_words(m.group(1)), p) for p in diners):
            questions.append(q)
    # One question per dish and concern, naming everyone it matters for (names, not ids).
    # A diner the dish already excludes is not asked about ("Yu Xiang (Pork) (for Ben): is
    # it vegetarian?", QA r8 note 8).
    eaters = {p.id for p in diners if assessment(dish, p)["status"] != "conflict"}
    who: dict[str, list[str]] = {}
    for person in diners:
        if person.id not in eaters:
            continue
        for r in assessment(dish, person)["reasons"]:
            if r.startswith("Confirm"):
                who.setdefault(r, []).append(person.name or person.id)
    label = dish.name_en or dish.name_zh or dish.id
    questions.extend(f"{label} (for {', '.join(names)}): {natural(r)}" for r, names in who.items())
    for f in dish.allergens:
        names = [p.name or p.id for p in diners if f.allergen in p.allergies and p.id in eaters]
        if f.tier == EvidenceTier.UNKNOWN and names:
            q = f"{label} (for {', '.join(names)}): " + natural(
                f"Confirm {f.allergen.value}, including sauces and cross-contact"
            )
            if q not in questions:
                questions.append(q)
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


def _matters(words: list[str], person: DinerProfile) -> bool:
    """Whether an ingredient question (its cover words) touches this diner's allergies/diets."""
    terms = [getattr(x, "value", x) for x in [*person.allergies, *person.diets]]
    terms += [t.replace(" ", "_") for t in [*person.other_allergies, *person.other_diets]]
    return any(set(words) & set(_words(t)) for t in terms)


def _join(items: list[str], last: str) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {last} {items[-1]}"


# Diets are asked as "is it halal?", never as an ingredient ("any pork or halal in it", QA r8).
_DIET_WORDS = {"vegetarian", "vegan", "halal", "kosher", "pescatarian", "jain"}


def _is_diet(term: str) -> bool:
    t = term.lower().strip()
    return t in _DIET_WORDS or t.endswith(("-free", " free", "friendly", "certified"))


# One concern per clause: "lard" and "minced pork" are the pork question.
_CONCERN = {
    "lard": "pork or lard",
    "bacon": "pork",
    "ham": "pork",
    "minced pork": "pork",
    "pork fat": "pork or lard",
    "meat stock": "meat or meat stock",
    "meat broth": "meat or meat stock",
    "tree nut": "tree nuts",
    "nuts": "tree nuts",
    "shrimp": "shellfish",
    "crab": "shellfish",
}


def ask_server(
    dish: Dish, flagged: list[Risk], follow_up: bool = False, restricted: bool = True
) -> str:
    """One short question a diner could say to the server, covering these risks, one clause
    per concern and no repeats: "Is there any pork or cilantro in the Yu Xiang (Tofu) (for
    Cai and Mia), and is it vegetarian and halal (for Ben and Mia)?" Diets are asked as
    "is it halal?", never as an ingredient. A dish's generic "confirm ingredients" note asks
    only when someone at the table has an allergy or diet and nothing else is asked."""
    label = dish.name_en or dish.name_zh or dish.id

    def about(r: Risk) -> str:
        t = r.about.replace("_", " ").strip().lower()
        t = t[3:] if t.startswith("no ") and not _is_diet(t) else t
        return _CONCERN.get(t, t)

    generic = [r for r in flagged if about(r) in ("ingredients", "ingredient")]
    flagged = [r for r in flagged if r not in generic]
    spice = [r for r in flagged if r.about == "spice level"]
    rest = [r for r in flagged if r.about != "spice level"]
    ingr = [r for r in rest if not _is_diet(about(r))]
    diet = [r for r in rest if _is_diet(about(r))]

    def names(rs: list[Risk]) -> list[str]:
        return list(dict.fromkeys(n for r in rs for n in r.names))

    def things(rs: list[Risk]) -> list[str]:
        ts = list(dict.fromkeys(about(r) for r in rs))
        return [t for t in ts if not any(t != o and t in o.split(" ") for o in ts)]

    where = "it" if follow_up else f"the {label}"
    clauses: list[tuple[str, list[str]]] = []
    if ingr:
        clauses.append((f"is there any {_join(things(ingr), 'or')} in {where}", names(ingr)))
    if diet:
        subject = "it" if clauses else where
        clauses.append((f"is {subject} {_join(things(diet), 'and')}", names(diet)))
    if spice:
        clauses.append(("how spicy is it" if clauses else f"how spicy is {where}", names(spice)))
    if not clauses:
        if not (generic and restricted):
            return ""
        clauses.append((f"what goes into {where}, including the sauce", []))
    every = names([*ingr, *diet, *spice])
    split = len({tuple(n) for _, n in clauses if n}) > 1
    parts = []
    for text, who in clauses:
        if split and who:
            text += f" (for {_join(who, 'and')})"
        parts.append(text)
    text = ", and ".join(parts)
    if not split and every:
        text += f" (for {_join(every, 'and')})"
    if follow_up:
        text = "Also, " + text
    elif text.startswith("what"):
        text = "Can you tell us " + text
    else:
        text = text[0].upper() + text[1:]
    return text + "?"


def risks(dish: Dish, diners: list[DinerProfile]) -> list[Risk]:
    """The rule-flagged risks behind open_questions, one per dish and concern."""
    label = dish.name_en or dish.name_zh or dish.id
    out: list[Risk] = []
    for q in dish.confirm_with_staff:
        m = re.search(r"uses (.+?)\.?$", q)
        about = m.group(1) if m else "ingredients"
        words = _words(about) if m else ["ingredient", "allergen", "contain", "made", "use"]
        names = [p.name or p.id for p in diners if m and _matters(words, p)]
        if m and diners and not names:
            continue  # e.g. "uses soy" when nobody at the table avoids soy
        out.append(Risk(about, names, words, q))
    who: dict[str, list[str]] = {}
    for person in diners:
        for r in assessment(dish, person)["reasons"]:
            if r.startswith("Confirm"):
                who.setdefault(r, []).append(person.name or person.id)
    for reason, names in who.items():
        term = re.match(r"Confirm (\S+?)(,| ingredient| for| preparation|$)", reason)
        about = term.group(1) if term else reason
        words = _words(about)
        if any(set(r.words) & set(words) and set(names) <= set(r.names) for r in out):
            continue  # "uses lard" already asks Ben and Cai about pork
        out.append(
            Risk(about, names, words, f"{label} (for {', '.join(names)}): {natural(reason)}")
        )
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
                    f"{label} (for {', '.join(names)}): "
                    + natural(f"Confirm {f.allergen.value}, including sauces and cross-contact"),
                )
            )
    # Only people who may eat the dish are asked about; a "Not for Ben" dish asks nothing
    # for Ben. Labels are humanised ("no_pork" -> "no pork").
    eaters = {p.name or p.id for p in diners if p.id in edible_by(dish, diners)}
    kept = []
    for r in out:
        names = [n for n in r.names if n in eaters]
        if r.names and not names:
            continue
        kept.append(Risk(r.about.replace("_", " "), names, r.words, r.question))
    return kept
