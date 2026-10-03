"""Ground truth and scoring for the bad-case evaluation.

Every eval dish carries a `truth` block, written independently of the labels the system sees:

    {"components": [{"name": "oyster sauce", "hits": ["shellfish"], "certainty": "possible"}]}

`hits` use the vocabulary below. `certainty` is how often the component is present in the
typical NYC restaurant version of the dish:

    definite  defines the dish or is printed on the menu
    likely    in most versions (minced pork in dry-fried string beans)
    possible  in some versions (oyster sauce in garlic greens, chicken powder in stir-fries)

Scoring, applied the same way to our planner and to any baseline answer:

Plan level (what the answer serves)
    severe          a diner is said to be able to eat a dish with a definite/likely conflict
    unflagged       same with only a possible conflict, and no staff question names the dish
    false coverage  under truth a diner has fewer than min_dishes_per_person safe dishes

Menu level (every dish x diner, planner only, from /api/menu/evaluate)
    unsafe eligible   allowed although a definite/likely conflict exists
    over blocked      refused although truth has no conflict at all
    cautious blocked  refused, truth has only possible conflicts (a policy choice, reported)

Over-refusal
    false conflict  "no order works" while a safe order exists under truth

Trap types group findings by why they are hard. Each component has one `trap` (explicit,
hidden, name_inference, ambiguous, compound_sauce); each dish lists `traps`, which also mark
dish-level cases with no component to blame (false_alarm, negative_control).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

HITS = {
    "pork",
    "beef",
    "poultry",
    "meat",
    "meat_stock",
    "fish",
    "shellfish",
    "egg",
    "dairy",
    "honey",
    "peanut",
    "tree_nut",
    "soy",
    "wheat",
    "sesame",
}
ALLERGEN_HITS = {
    "shellfish",
    "fish",
    "peanut",
    "tree_nut",
    "egg",
    "dairy",
    "soy",
    "wheat",
    "sesame",
}
VEGETARIAN_BREAKERS = {"pork", "beef", "poultry", "meat", "meat_stock", "fish", "shellfish"}
DIET_BREAKERS = {
    "vegetarian": VEGETARIAN_BREAKERS,
    "vegan": VEGETARIAN_BREAKERS | {"egg", "dairy", "honey"},
    "no_pork": {"pork"},
    "no_beef": {"beef"},
}
SEVERE = {"definite", "likely"}
PORTION_UNITS = {"individual": 0.35, "small": 0.6, "medium": 1.0, "large": 1.5, "shared": 0.8}


def restricted_hits(diner: dict) -> set[str]:
    out = set(diner.get("allergies", []))
    for diet in diner.get("diets", []):
        out |= DIET_BREAKERS[diet]
    return out


def conflicts(dish: dict, diner: dict) -> list[tuple[str, str, str, str]]:
    """(component, hit, certainty, trap) for every truth component this diner cannot have."""
    bad = restricted_hits(diner)
    return [
        (c["name"], hit, c["certainty"], c.get("trap", ""))
        for c in dish["truth"]["components"]
        for hit in c["hits"]
        if hit in bad
    ]


def truly_safe(dish: dict, diner: dict) -> bool:
    return not any(cert in SEVERE for _, _, cert, _ in conflicts(dish, diner))


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def all_in_total(subtotal: Decimal, tax_rate: float, tip_rate: float) -> Decimal:
    """Tax and pre-tax tip rounded separately, as on a NYC check."""
    tax = money(subtotal * Decimal(str(tax_rate)))
    tip = money(subtotal * Decimal(str(tip_rate)))
    return subtotal + tax + tip


@dataclass
class Answer:
    """A normalized answer from any system: our planner, ChatGPT, or a future variant."""

    kind: str  # "plan" | "conflict" | "error"
    items: list[dict] = field(default_factory=list)  # {dish_id, quantity, edible_by}
    reported_total: float | None = None
    staff_questions: list[str] = field(default_factory=list)
    detail: str = ""
    # Optional, planner only: dish id -> diner ids the system would let eat it, whole menu.
    eligibility: dict[str, list[str]] | None = None


@dataclass
class Finding:
    diner: str
    dish: str
    traps: list[str]
    component: str = ""
    hit: str = ""
    certainty: str = ""

    def __str__(self) -> str:
        what = f": {self.component} ({self.hit}, {self.certainty})" if self.component else ""
        return f"{self.diner} <- {self.dish}{what}"


@dataclass
class Score:
    scenario: str
    category: str
    kind: str
    expected: str
    outcome_ok: bool
    # Plan level: what the answer actually serves.
    severe: list[Finding] = field(default_factory=list)
    unflagged: list[Finding] = field(default_factory=list)
    false_coverage: list[str] = field(default_factory=list)
    lock_violations: list[str] = field(default_factory=list)
    total: str | None = None
    budget_limit: str | None = None
    over_budget: bool = False
    math_error: str | None = None
    portions_ok: bool | None = None
    # Menu level: every dish x diner, from the eligibility check.
    unsafe_eligible: list[Finding] = field(default_factory=list)
    over_blocked: list[Finding] = field(default_factory=list)  # no conflict at all, refused
    cautious_blocked: list[Finding] = field(default_factory=list)  # only possible, refused
    # Over-refusal: said "no order works" while a safe order exists.
    false_conflict: bool | None = None
    detail: str = ""

    @property
    def passed(self) -> bool:
        """Safety and money: nothing restricted served, budget and arithmetic exact."""
        return (
            self.outcome_ok
            and not self.severe
            and not self.false_coverage
            and not self.lock_violations
            and not self.over_budget
            and self.math_error is None
        )

    @property
    def usable(self) -> bool:
        """Did not refuse a table that a safe order exists for."""
        return not self.false_conflict


def _flagged(dish: dict, questions: list[str]) -> bool:
    names = [n.lower() for n in (dish["id"], dish.get("name_en"), dish.get("name_zh")) if n]
    return any(n in q.lower() for q in questions for n in names)


def _finding(diner_id: str, dish: dict, comp="", hit="", cert="", trap="") -> Finding:
    """Component findings carry that component's trap; dish-level ones the dish's traps."""
    traps = [trap] if trap else dish.get("traps", [])
    return Finding(diner_id, dish["id"], traps, comp, hit, cert)


def score_eligibility(
    s: Score, diners: dict[str, dict], dishes: dict[str, dict], eligibility: dict[str, list[str]]
) -> None:
    for dish_id, allowed in eligibility.items():
        dish = dishes[dish_id]
        for diner_id, diner in diners.items():
            found = conflicts(dish, diner)
            if diner_id in allowed:
                s.unsafe_eligible += [_finding(diner_id, dish, *f) for f in found if f[2] in SEVERE]
            elif not found:
                s.over_blocked.append(_finding(diner_id, dish))
            elif not any(cert in SEVERE for _, _, cert, _ in found):
                s.cautious_blocked.append(_finding(diner_id, dish))


def score(
    scenario: dict, dishes: dict[str, dict], answer: Answer, feasible: bool | None = None
) -> Score:
    """`feasible`: whether a safe order exists under truth (None = not checked)."""
    s = Score(
        scenario=scenario["id"],
        category=scenario["category"],
        kind=answer.kind,
        expected=scenario.get("expect", "any"),
        outcome_ok=scenario.get("expect", "any") in ("any", answer.kind),
        detail=answer.detail,
    )
    diners = {d["id"]: d for d in scenario["diners"]}
    if answer.eligibility is not None:
        score_eligibility(s, diners, dishes, answer.eligibility)
    if feasible is not None:
        s.false_conflict = answer.kind == "conflict" and feasible
    if answer.kind != "plan":
        return s

    n = len(diners)
    in_plan = {it["dish_id"] for it in answer.items}

    for dish_id in scenario.get("locked_dish_ids", []):
        if dish_id not in in_plan:
            s.lock_violations.append(f"locked {dish_id} missing")
    for dish_id in scenario.get("excluded_dish_ids", []):
        if dish_id in in_plan:
            s.lock_violations.append(f"excluded {dish_id} present")

    for it in answer.items:
        dish = dishes[it["dish_id"]]
        for diner_id in it.get("edible_by", []):
            for f in conflicts(dish, diners[diner_id]):
                if f[2] in SEVERE:
                    s.severe.append(_finding(diner_id, dish, *f))
                elif not _flagged(dish, answer.staff_questions):
                    s.unflagged.append(_finding(diner_id, dish, *f))

    need = scenario.get("min_dishes_per_person", 2)
    for diner_id, diner in diners.items():
        safe = [
            d for d in in_plan if dishes[d]["category"] != "staple" and truly_safe(dishes[d], diner)
        ]
        if len(safe) < need:
            s.false_coverage.append(f"{diner_id}: {len(safe)} truly safe dishes, needs {need}")

    subtotal = sum(
        money(dishes[it["dish_id"]]["price"]) * it.get("quantity", 1) for it in answer.items
    )
    total = all_in_total(
        subtotal, scenario.get("tax_rate", 0.08875), scenario.get("tip_rate", 0.18)
    )
    limit = money(scenario["budget_per_person"]) * n
    s.total, s.budget_limit, s.over_budget = str(total), str(limit), total > limit
    if answer.reported_total is not None and abs(money(answer.reported_total) - total) > Decimal(
        "0.01"
    ):
        s.math_error = f"reported {answer.reported_total}, actual {total}"

    units = sum(
        PORTION_UNITS[dishes[it["dish_id"]]["portion"]] * it.get("quantity", 1)
        for it in answer.items
        if dishes[it["dish_id"]]["category"] != "staple"
    )
    s.portions_ok = 0.9 * n <= units <= 1.3 * n
    return s


# ---------------------------------------------------------------------------
# Label level: does each dish's label say the right thing about each restriction?
# ---------------------------------------------------------------------------

DIET_FLAGS = {
    "vegetarian": ("is_vegetarian", False),
    "vegan": ("is_vegan", False),
    "no_pork": ("contains_pork", True),
    "no_beef": ("contains_beef", True),
}
RESTRICTIONS = sorted(ALLERGEN_HITS) + list(DIET_FLAGS)
STRICTNESS = {"clear": 0, "ask": 1, "block": 2}


def truth_status(dish: dict, restriction: str) -> tuple[str, str]:
    """('block' | 'ask' | 'clear', trap of the deciding component)."""
    hits = DIET_BREAKERS.get(restriction, {restriction})
    found = [c for c in dish["truth"]["components"] if hits & set(c["hits"])]
    severe = [c for c in found if c["certainty"] in SEVERE]
    if severe:
        return "block", severe[0].get("trap", "")
    if found:
        return "ask", found[0].get("trap", "")
    return "clear", ""


def label_status(label: dict, restriction: str) -> str:
    """What the system's Dish label tells the planner about this restriction."""
    if restriction in DIET_FLAGS:
        field_name, bad = DIET_FLAGS[restriction]
        value = label.get(field_name)
        return "ask" if value is None else ("block" if value == bad else "clear")
    tiers = {f["tier"] for f in label.get("allergens", []) if f["allergen"] == restriction}
    if tiers & {"menu", "inferred"}:
        return "block"
    return "ask" if "unknown" in tiers else "clear"


@dataclass
class LabelFinding:
    dish: str
    restriction: str
    truth: str
    system: str
    trap: str

    @property
    def kind(self) -> str:
        if self.truth == self.system:
            return "correct"
        if self.truth == "block":
            return "missed" if self.system == "clear" else "weakened"
        if self.truth == "ask" and self.system == "clear":
            return "unflagged"
        return "stricter"


def score_labels(dishes: dict[str, dict], labels: dict[str, dict]) -> list[LabelFinding]:
    out = []
    for dish_id, dish in dishes.items():
        for r in RESTRICTIONS:
            truth, trap = truth_status(dish, r)
            system = label_status(labels[dish_id], r)
            out.append(LabelFinding(dish_id, r, truth, system, trap or ",".join(dish["traps"])))
    return out
