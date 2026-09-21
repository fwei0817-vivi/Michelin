"""Pydantic models shared by every stage.

This file is the contract between parse/, plan/, explain.py, the Streamlit app and the JSON
files under data/. Change it first, then update everything that reads or writes it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


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


class DishCategory(str, Enum):
    COLD_APPETIZER = "cold_appetizer"
    STIR_FRY = "stir_fry"
    BRAISE_OR_STEW = "braise_or_stew"
    SOUP = "soup"
    STAPLE = "staple"  # rice, noodles, buns
    DESSERT = "dessert"
    DRINK = "drink"
    OTHER = "other"


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


class Dish(BaseModel):
    id: str  # stable ASCII slug, e.g. "mapo_tofu"
    name_zh: str | None = None
    name_en: str | None = None
    price: float | None = None  # None = unreadable on photo; must be filled before verified
    description_raw: str | None = None  # verbatim menu text, never edited
    category: DishCategory = DishCategory.OTHER
    cooking_method: str | None = None  # "stir_fry", "deep_fry", "braise", "steam", ...
    spice_level: int = Field(default=0, ge=0, le=3)
    portion: PortionClass = PortionClass.MEDIUM
    main_ingredients: list[IngredientClaim] = Field(default_factory=list)
    allergens: list[AllergenFlag] = Field(default_factory=list)
    # None = unknown. Hard constraints treat None as False (not safe to assume).
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    contains_pork: bool | None = None
    contains_beef: bool | None = None
    confirm_with_staff: list[str] = Field(default_factory=list)  # questions to ask the waiter


class Menu(BaseModel):
    restaurant_id: str
    restaurant_name: str
    cuisine: str  # e.g. "chinese_sichuan"
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
    id: str
    name: str
    allergies: list[Allergen] = Field(default_factory=list)  # HARD
    diets: list[Diet] = Field(default_factory=list)  # HARD
    max_spice: int | None = Field(default=None, ge=0, le=3)  # SOFT
    dislikes: list[str] = Field(default_factory=list)  # SOFT, free text ("cilantro")
    likes: list[str] = Field(default_factory=list)  # SOFT


class TableRequest(BaseModel):
    menu_id: str
    diners: list[DinerProfile]
    budget_per_person: float  # all-in: includes tax and tip
    tax_rate: float = 0.08875  # NYC sales tax
    tip_rate: float = 0.18
    min_dishes_per_person: int = 2  # non-staple dishes each diner must be able to eat
    include_staple: bool = True  # add one staple (rice) per person

    @property
    def n_diners(self) -> int:
        return len(self.diners)


# ---------------------------------------------------------------------------
# Stage 2 / 3 output
# ---------------------------------------------------------------------------


class PlanItem(BaseModel):
    dish_id: str
    quantity: int = 1
    edible_by: list[str] = Field(default_factory=list)  # diner ids, under hard constraints
    reason: str | None = None  # one-liner from explain.py


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


class Relaxation(BaseModel):
    """One change that would make the request feasible."""

    kind: str  # "budget" | "allergy" | "diet" | "coverage" | "portions"
    description: str  # human-readable, e.g. "Raise the budget to $28.00 per person"
    diner_id: str | None = None
    new_value: float | None = None


class Conflict(BaseModel):
    message: str
    relaxations: list[Relaxation] = Field(default_factory=list)
