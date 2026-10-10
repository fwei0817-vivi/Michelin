"""Pydantic models shared by every stage.

This file is the contract between parse/, plan/, explain.py, the Streamlit app and the JSON
files under data/. Change it first, then update everything that reads or writes it.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_MENU_DISHES = 150  # a 4-page menu runs ~75 lines, ~110 once choices become versions


class EvidenceTier(str, Enum):
    """How we know an ingredient or allergen claim. Drives UI wording and staff questions."""

    MENU = "menu"  # printed on the menu (high confidence)
    INFERRED = "inferred"  # LLM inferred from dish name + typical recipe (medium)
    UNKNOWN = "unknown"  # hidden components: sauces, broths, frying oil (low) -> ask staff


class Allergen(str, Enum):
    SHELLFISH = "shellfish"
    FISH = "fish"
    PEANUT = "peanut"
    TREE_NUT = "tree_nut"
    EGG = "egg"
    DAIRY = "dairy"
    SOY = "soy"
    WHEAT = "wheat"
    SESAME = "sesame"


class Diet(str, Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    NO_PORK = "no_pork"
    NO_BEEF = "no_beef"


class Preference(str, Enum):
    """SOFT tastes picked as quick chips: the AI weighs them, the rules never exclude a dish."""

    NO_SPICY = "no_spicy"
    MILD = "mild"
    LOVES_SPICY = "loves_spicy"
    LIKES_SEAFOOD = "likes_seafood"
    LIKES_MEAT = "likes_meat"
    LIGHT = "light"  # 清淡: light, not oily or heavy
    NO_OFFAL = "no_offal"  # 内脏


PREFERENCE_TEXT = {
    Preference.NO_SPICY: "no spicy food",
    Preference.MILD: "mild heat at most",
    Preference.LOVES_SPICY: "loves spicy food",
    Preference.LIKES_SEAFOOD: "likes seafood",
    Preference.LIKES_MEAT: "likes meat dishes",
    Preference.LIGHT: "prefers light, not oily or heavy dishes (清淡)",
    Preference.NO_OFFAL: "no offal (内脏: tripe, intestine, liver, kidney, blood)",
}


def clean_terms(values) -> list[str]:
    """Free-text allergy/diet chips ("Mango ", "no  alcohol") -> ["mango", "no alcohol"]:
    lower case, single spaces, letters/digits/'-' only, at most 10 of 40 characters."""
    import re

    out: list[str] = []
    for v in values or []:
        t = re.sub(r"[^a-z0-9 '\-]+", " ", str(v).lower())
        t = " ".join(t.split())[:40].strip()
        if t and t not in out:
            out.append(t)
    return out[:10]


class DishCategory(str, Enum):
    COLD_APPETIZER = "cold_appetizer"
    STIR_FRY = "stir_fry"
    BRAISE_OR_STEW = "braise_or_stew"
    SOUP = "soup"
    STAPLE = "staple"  # rice, noodles, buns
    DESSERT = "dessert"
    DRINK = "drink"
    OTHER = "other"


class MenuMark(str, Enum):
    """A symbol the menu itself prints next to a dish, as its legend explains it."""

    VEGETARIAN = "vegetarian"  # "V": menu-stated, stronger than the AI's guess
    VEGAN = "vegan"
    VEGETARIAN_POSSIBLE = "vegetarian_possible"  # "VP": only if ordered vegetarian; ask
    GLUTEN_FREE = "gluten_free"  # stored and shown; never clears a wheat allergy
    GLUTEN_FREE_POSSIBLE = "gluten_free_possible"


class PortionClass(str, Enum):
    """Label only. The unit weights live in plan/portions.py."""

    INDIVIDUAL = "individual"  # one person: a bowl of noodles, a bowl of rice
    SMALL = "small"  # cold appetizer, side
    MEDIUM = "medium"  # typical stir-fry plate
    LARGE = "large"  # whole fish, dry pot, casserole
    SHARED = "shared"  # whole-table soup or hotpot


# ---------------------------------------------------------------------------
# Stage 1 output: the menu
# ---------------------------------------------------------------------------


class IngredientClaim(BaseModel):
    name: str
    tier: EvidenceTier
    note: str | None = None


class AllergenFlag(BaseModel):
    allergen: Allergen
    tier: EvidenceTier
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


def validate_money(value):
    if value is not None and abs(value) > 1_000_000_000:
        raise ValueError("USD amounts must not exceed one billion")
    if value is not None and Decimal(str(value)) != Decimal(str(value)).quantize(Decimal("0.01")):
        raise ValueError("USD amounts must have at most two decimal places")
    return value


class Dish(BaseModel):
    id: str  # stable ASCII slug, e.g. "mapo_tofu"
    name_zh: str | None = None
    name_en: str | None = None
    price: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )  # None = unreadable on photo; must be filled before verified
    description_raw: str | None = None  # verbatim menu text, never edited
    category: DishCategory = DishCategory.OTHER
    cooking_method: str | None = None  # "stir_fry", "deep_fry", "braise", "steam", ...
    spice_level: int | None = Field(default=None, ge=0, le=3)
    portion: PortionClass | None = None
    main_ingredients: list[IngredientClaim] = Field(default_factory=list)
    allergens: list[AllergenFlag] = Field(default_factory=list)
    # Explicit review of available evidence, never a guarantee about cross-contact.
    reviewed_allergens: list[Allergen] = Field(default_factory=list)
    _price_cents = field_validator("price")(validate_money)
    # None = unknown. Hard constraints treat None as False (not safe to assume).
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    contains_pork: bool | None = None
    contains_beef: bool | None = None
    confirm_with_staff: list[str] = Field(default_factory=list)  # questions to ask the waiter
    # As printed on the menu (photo import). One line with a choice of protein becomes one
    # dish per choice ("Kung Pao (Tofu)", own price) sharing a family_id.
    family_id: str | None = None
    family_name: str | None = None  # "Kung Pao"
    variant: str | None = None  # "Tofu"
    menu_marks: list[MenuMark] = Field(default_factory=list)
    menu_spice: int | None = Field(default=None, ge=0, le=3)  # pepper icons, capped at 3
    menu_section: str | None = None  # the printed heading ("Dim Sum"), as read
    # The AI's answer for a diner's own allergy or diet ("mango", "halal"); set by the server.
    custom_flags: list[CustomFlag] = Field(default_factory=list)


class CustomFlag(BaseModel):
    """Does this dish hold a free-text allergen, or break a free-text diet?"""

    term: str  # "mango", "halal"
    kind: str = Field(pattern="^(allergy|diet)$")
    answer: str = Field(pattern="^(likely|possible|no|unknown)$")
    why: str = ""
    printed: bool = False  # the menu's own words name it


class Menu(BaseModel):
    restaurant_id: str
    restaurant_name: str
    cuisine: str  # e.g. "chinese_sichuan"
    preparation_mode: str | None = None  # explicit provider provenance, never an accuracy claim
    source: str  # "google_maps_photo" | "own_photo" | "restaurant_site" | "sample"
    currency: str = "USD"
    verified: bool = False  # True only after a human checked every dish against the photo
    dishes: list[Dish]

    def dish(self, dish_id: str) -> Dish:
        for d in self.dishes:
            if d.id == dish_id:
                return d
        raise KeyError(dish_id)


# ---------------------------------------------------------------------------
# User input
# ---------------------------------------------------------------------------


class DinerProfile(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    allergies: list[Allergen] = Field(default_factory=list)  # HARD
    diets: list[Diet] = Field(default_factory=list)  # HARD
    # HARD, in the diner's words: "mango", "cilantro", "MSG"; "halal", "kosher", "no alcohol".
    other_allergies: list[str] = Field(default_factory=list, max_length=10)
    other_diets: list[str] = Field(default_factory=list, max_length=10)
    # SOFT quick chips (spice, seafood, meat, light, offal); the AI weighs them.
    preferences: list[Preference] = Field(default_factory=list)
    # SOFT: tastes and preferences in the diner's own words; the AI reads it, the rules don't.
    notes: str = Field(default="", max_length=500)

    @field_validator("other_allergies", "other_diets", mode="before")
    @classmethod
    def _clean_terms(cls, v):
        return clean_terms(v if isinstance(v, list) else [])

    @model_validator(mode="before")
    @classmethod
    def _migrate_preferences(cls, data):
        """Saved people from before 2026-10-09 had heat/likes/dislikes fields: fold them into
        the one free-text note so nothing they told us is lost."""
        if not isinstance(data, dict) or not ({"max_spice", "likes", "dislikes"} & data.keys()):
            return data
        data = dict(data)
        spice, likes, dislikes = (
            data.pop("max_spice", None),
            data.pop("likes", None),
            data.pop("dislikes", None),
        )
        parts = [data.get("notes") or ""]
        if spice is not None:
            heat = ["no spicy food", "mild heat at most", "medium heat at most", "likes it hot"]
            parts.append(heat[spice] if isinstance(spice, int) and 0 <= spice <= 3 else "")
        if likes:
            parts.append("likes " + ", ".join(map(str, likes)))
        if dislikes:
            parts.append("dislikes " + ", ".join(map(str, dislikes)))
        note = "; ".join(p.strip() for p in parts if p and p.strip())
        data["notes"] = note[:1].upper() + note[1:] if note else ""
        return data


class TableRequest(BaseModel):
    menu_id: str
    diners: list[DinerProfile] = Field(min_length=1, max_length=6)
    budget_per_person: float = Field(gt=0, allow_inf_nan=False)  # all-in: includes tax and tip
    tax_rate: float = Field(default=0.08875, ge=0, le=0.3, allow_inf_nan=False)  # NYC sales tax
    tip_rate: float = Field(default=0.18, ge=0, le=0.4, allow_inf_nan=False)
    style_preference: str = "balanced"
    include_staple: bool = True  # add one staple (rice) per person
    locked_dish_ids: list[str] = Field(default_factory=list)  # user pinned these, must stay
    excluded_dish_ids: list[str] = Field(
        default_factory=list
    )  # user removed these, must not appear

    budget_total: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    _budget_cents = field_validator("budget_per_person", "budget_total")(validate_money)

    @model_validator(mode="after")
    def unique_people(self):
        if len({p.id for p in self.diners}) != len(self.diners):
            raise ValueError("Diner IDs must be unique")
        return self

    @property
    def all_in_budget(self) -> float:
        return (
            self.budget_total
            if self.budget_total is not None
            else float(Decimal(str(self.budget_per_person)) * self.n_diners)
        )

    @property
    def n_diners(self) -> int:
        return len(self.diners)


# ---------------------------------------------------------------------------
# Stage 2 / 3 output
# ---------------------------------------------------------------------------


class PlanItem(BaseModel):
    dish_id: str
    quantity: int = Field(default=1, ge=1, le=100, strict=True)
    edible_by: list[str] = Field(default_factory=list)  # diner ids, under hard constraints
    reason: str | None = None  # one-liner from explain.py
    server_question: str | None = None  # one question for the server about this dish
    # diner id -> {"status": "ok"|"needs_confirm"|"no", "reason": str|None}; filled by the
    # API from edibility.diner_status, the one source the web cards render (QA r15).
    status: dict[str, dict] = Field(default_factory=dict)


class Check(BaseModel):
    """One requirement the UI shows as pass / fail."""

    name: str
    passed: bool
    detail: str


class Plan(BaseModel):
    items: list[PlanItem]
    subtotal: float
    tax: float
    tip: float
    total: float
    per_person: float
    variety_score: float = Field(ge=0.0, le=1.0)
    checks: list[Check] = Field(default_factory=list)
    confirm_with_staff: list[str] = Field(default_factory=list)
    summary: str | None = None  # AI plans: one sentence on how the order suits the table


class Relaxation(BaseModel):
    """One change that would make the request feasible."""

    kind: str  # "budget" | "allergy" | "diet" | "coverage" | "portions"
    description: str  # human-readable, e.g. "Raise the budget to $28.00 per person"
    diner_id: str | None = None
    new_value: float | None = None


class Conflict(BaseModel):
    code: str = "no_solution"
    message: str
    relaxations: list[Relaxation] = Field(default_factory=list)
