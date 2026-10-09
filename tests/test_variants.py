"""Photo import normalises the menu: choices become orderable versions, printed marks count.

Key case: Cafe Mandarin (test-menus/cafe-mandarin.jpg) prints "Kung Pao 宫保鸡/牛/虾/豆腐 VP,
Scallion | Peanut, Choice of Chicken | Beef +$2 | Shrimp +$4 | Tofu, $18" and a legend
"Spicy, V Vegetarian, VP Vegetarian Possible, V Vegan, GF Gluten Free, GP Gluten Free Possible".
"""

from michelin.parse import vision
from michelin.plan import dish_facts, llm_planner
from michelin.plan.ai_swap import check as swap_check
from michelin.plan.ai_swap import manual
from michelin.plan.edibility import assessment, edible_by, open_questions
from michelin.plan.validation import family_repeats
from michelin.schemas import Allergen, DinerProfile, Dish, Menu, Plan, PlanItem, TableRequest

ALICE = DinerProfile(id="alice", name="Alice", allergies=["peanut"])
SAM = DinerProfile(id="sam", name="Sam", allergies=["shellfish"])
BEN = DinerProfile(id="ben", name="Ben", diets=["vegetarian"])
CAI = DinerProfile(id="cai", name="Cai", diets=["no_pork"])
TABLE = [ALICE, SAM, BEN, CAI]

KUNG_PAO = {
    "name_en": "Kung Pao",
    "name_zh": "宫保鸡 / 牛 / 虾 / 豆腐",
    "price": 18,
    "description": "Scallion | Peanut  Choice of Chicken | Beef +$2 | Shrimp +$4 | Tofu",
    "marks": ["vegetarian_possible", "made_up"],
    "spicy": 1,
    "choices": [
        {"name_en": "Chicken", "name_zh": "鸡", "price": 18},
        {"name_en": "Beef", "name_zh": "牛", "price": 20},
        {"name_en": "Shrimp", "name_zh": "虾", "price": 4},  # surcharge only: +$4
        {"name_en": "Tofu", "name_zh": "豆腐"},  # no price: the dish price
    ],
}


def _versions():
    return {d.variant: d for d in vision.rows_to_dishes([KUNG_PAO])}


def test_a_choice_line_becomes_one_orderable_dish_per_choice():
    v = _versions()
    assert list(v) == ["Chicken", "Beef", "Shrimp", "Tofu"]
    assert [d.price for d in v.values()] == [18, 20, 22, 18]
    assert {d.family_id for d in v.values()} == {"kung_pao"}
    assert v["Tofu"].name_en == "Kung Pao (Tofu)" and v["Tofu"].family_name == "Kung Pao"
    # The tofu version's Chinese name never carries the chicken (宫保鸡 -> 宫保).
    assert v["Tofu"].name_zh == "宫保（豆腐）" and v["Chicken"].name_zh == "宫保（鸡）"
    assert "Choice of" not in v["Tofu"].description_raw and "Peanut" in v["Tofu"].description_raw
    assert [m.value for m in v["Tofu"].menu_marks] == ["vegetarian_possible"]
    assert v["Tofu"].menu_spice == 1
    assert len({d.id for d in v.values()}) == 4


def test_option_words_leave_the_versions_name():
    """Live run: the model kept "Yu Xiang Pork" and "Sesame Chicken or Tofu" as the line's
    name, so "Yu Xiang Pork (Tofu)" said pork and the vegetarian lost the tofu version."""
    rows = [
        {**KUNG_PAO, "name_en": "Kung Pao Chicken", "name_zh": "宫保鸡丁"},
        {
            "name_en": "Sesame Chicken or Tofu",
            "price": 18,
            "choices": [{"name_en": "Chicken"}, {"name_en": "Tofu"}],
        },
        {
            "name_en": "Yu Xiang Pork",
            "price": 18,
            "choices": [
                {"name_en": "Pork"},
                {"name_en": "Shrimp", "price": 22},
                {"name_en": "Tofu"},
            ],
        },
    ]
    names = [d.name_en for d in vision.rows_to_dishes(rows)]
    assert names == [
        "Kung Pao (Chicken)",
        "Kung Pao (Beef)",
        "Kung Pao (Shrimp)",
        "Kung Pao (Tofu)",
        "Sesame (Chicken)",
        "Sesame (Tofu)",
        "Yu Xiang (Pork)",
        "Yu Xiang (Shrimp)",
        "Yu Xiang (Tofu)",
    ]
    tofu = dish_facts.apply(vision.rows_to_dishes(rows)[-1], None)
    assert tofu.contains_pork is not True and tofu.is_vegetarian is not False
    # 宫保鸡丁 holds the chicken option: no Chinese name beats a wrong one for the tofu version.
    assert vision.rows_to_dishes(rows)[3].name_zh == "豆腐"


def test_version_facts_come_from_the_version():
    """No AI facts at all: the printed words alone keep each version honest."""
    v = {k: dish_facts.apply(d, None) for k, d in _versions().items()}
    assert edible_by(v["Shrimp"], [SAM]) == []  # shellfish printed in its name
    assert v["Chicken"].is_vegetarian is False and v["Beef"].contains_beef is True
    for d in v.values():
        assert edible_by(d, [ALICE]) == []  # "Peanut" printed for the whole line
    assert v["Tofu"].is_vegetarian is not False  # not refused: vegetarian possible


VEG = {
    "ingredients": [{"name": "chicken stock", "certainty": "possible"}],
    "allergens": [
        {"allergen": "soy", "certainty": "likely", "why": "soy sauce"},
        {"allergen": "shellfish", "certainty": "likely", "why": "oyster sauce"},
    ],
    "pork": "no",
    "beef": "no",
    "vegetarian": "possible",
    "vegan": "possible",
    "spice": 1,
}


def _dish(name, marks=(), desc="", **kw):
    return Dish(
        id=name.lower().replace(" ", "_").replace("(", "").replace(")", ""),
        name_en=name,
        price=10,
        description_raw=f"{name} {desc}".strip(),
        menu_marks=list(marks),
        **kw,
    )


def test_vp_means_vegetarian_only_if_ordered_that_way():
    tofu = dish_facts.apply(
        _dish("Kung Pao (Tofu)", ["vegetarian_possible"], family_id="kp", variant="Tofu"), VEG
    )
    a = assessment(tofu, BEN)
    assert a["eligible"]
    asked = " ".join(open_questions(tofu, [BEN]))
    assert "order it vegetarian" in asked
    # The AI's oyster sauce is a guess: Sam stays off (allergies are strict), Ben is asked.
    assert edible_by(tofu, [SAM]) == []


def test_printed_v_beats_the_guess_but_printed_meat_beats_v():
    """Cafe Mandarin marks Hot & Sour Soup "V"; the keyword floor said pork. A "V" next to
    printed pork belly is still pork (safety first)."""
    pork_guess = {**VEG, "pork": "yes", "vegetarian": "no", "vegan": "no"}
    pork_guess["ingredients"] = [{"name": "pork", "certainty": "likely"}]
    soup = dish_facts.apply(_dish("Hot & Sour Soup", ["vegetarian"]), pork_guess)
    assert soup.is_vegetarian is True and soup.contains_pork is False
    assert edible_by(soup, [BEN, CAI]) == ["ben", "cai"]
    assert any("pork" in q for q in open_questions(soup, [BEN, CAI]))  # still asked
    belly = dish_facts.apply(
        _dish("Hunan Wild Mushroom (w/ Pork Belly)", ["vegetarian"], "Pork Belly | Chili Oil"),
        VEG,
    )
    assert edible_by(belly, [BEN, CAI]) == []
    vp_belly = dish_facts.apply(
        _dish("Hunan Wild Mushroom (w/ Pork Belly)", ["vegetarian_possible"]), VEG
    )
    assert edible_by(vp_belly, [BEN, CAI]) == []


def test_v_without_ai_and_gf_never_clears_an_allergy():
    soup = dish_facts.apply(_dish("Egg Drop Soup", ["vegetarian", "gluten_free"]), None)
    assert soup.is_vegetarian is True and soup.contains_pork is False
    wheat = DinerProfile(id="w", name="W", allergies=["wheat"])
    assert edible_by(soup, [wheat]) == []  # GF is shown, not trusted for an allergy
    assert edible_by(soup, [DinerProfile(id="e", name="E", allergies=["egg"])]) == []


def test_menu_peppers_set_the_heat():
    d = dish_facts.apply(_dish("Hunan Beef", menu_spice=3), {**VEG, "spice": 1})
    assert d.spice_level == 3


MEAT = {"ingredients": [], "allergens": [], "pork": "no", "beef": "no", "spice": 1}
MEAT |= {"vegetarian": "no", "vegan": "no"}


def _menu():
    dishes = [dish_facts.apply(d, MEAT) for d in vision.rows_to_dishes([KUNG_PAO])]
    greens = Dish(
        id="greens",
        name_en="Chinese Greens",
        price=12,
        is_vegetarian=True,
        is_vegan=True,
        contains_pork=False,
        contains_beef=False,
        reviewed_allergens=list(Allergen),
    )
    return Menu(
        restaurant_id="cm",
        restaurant_name="Cafe Mandarin",
        cuisine="x",
        source="photo",
        dishes=[*dishes, greens],
        verified=True,
    )


def test_two_versions_only_when_each_feeds_someone_new():
    menu = _menu()
    request = TableRequest(menu_id="cm", diners=[SAM, CAI], budget_per_person=60)
    ids = {d.variant: d.id for d in menu.dishes if d.variant}
    assert family_repeats(menu, request, [ids["Chicken"], "greens"]) == []
    # Chicken feeds Sam and Cai; Beef feeds the same people: one is enough.
    assert family_repeats(menu, request, [ids["Chicken"], ids["Beef"]])
    assert family_repeats(menu, request, [ids["Chicken"], ids["Beef"], ids["Tofu"]])
    # Shrimp is not for Sam, Chicken is for both: redundant too.
    assert family_repeats(menu, request, [ids["Chicken"], ids["Shrimp"]])


def test_the_planner_refuses_a_redundant_second_version_but_the_user_may_add_one():
    menu = _menu()
    request = TableRequest(menu_id="cm", diners=[SAM, CAI], budget_per_person=60)
    ids = {d.variant: d.id for d in menu.dishes if d.variant}
    answer = {
        "dishes": [
            {"dish_id": ids["Chicken"], "reason": "", "for": ["sam", "cai"], "server_question": ""},
            {"dish_id": ids["Beef"], "reason": "", "for": ["sam", "cai"], "server_question": ""},
        ]
    }
    problems, _ = llm_planner.check(menu, request, answer, [])
    assert any("versions of Kung Pao" in p for p in problems)
    brief = llm_planner.brief(menu, request)
    row = next(r for r in brief["dishes"] if r["id"] == ids["Chicken"])
    assert row["family"] == "Kung Pao" and row["version"] == "Chicken"
    assert row["menu_marks"] == ["vegetarian possible"]
    plan = Plan(
        items=[PlanItem(dish_id=ids["Chicken"], quantity=1, edible_by=["sam", "cai"])],
        subtotal=18,
        tax=1.6,
        tip=3.24,
        total=22.84,
        per_person=11.42,
        variety_score=0.5,
    )
    ai, _ = swap_check(menu, request, plan, None, {"dish_id": ids["Beef"]})
    assert any("versions of Kung Pao" in p for p in ai)
    out = manual(menu, request, plan, None, ids["Beef"])
    assert out.plan is not None and "Kung Pao (Beef)" in out.message


def test_the_floor_keeps_hidden_shellfish_whatever_the_model():
    """3.5 Flash Lite cleared shrimp in wonton soup and oyster sauce on greens."""
    clean = {"ingredients": [], "allergens": [], "pork": "no", "beef": "no", "spice": 0}
    clean |= {"vegetarian": "no", "vegan": "no"}
    for name in (
        "Traditional Wonton Soup",
        "Supreme Broth Baby Bok Choy",
        "Spring Rolls",
        "Stuffed Eggplant",
        "Okra and Chinese Broccoli with Chinese Wine Sauce",
    ):
        assert edible_by(dish_facts.apply(_dish(name), clean), [SAM]) == [], name
    veg = dish_facts.apply(_dish("Vegetarian Egg Rolls"), clean)
    assert all(f.allergen != Allergen.SHELLFISH for f in veg.allergens)
