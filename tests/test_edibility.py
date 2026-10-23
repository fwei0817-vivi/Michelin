from michelin.plan.edibility import can_eat, edible_by, open_questions
from michelin.schemas import Allergen, Diet, DinerProfile, Dish


def by_id(diners, diner_id):
    return next(p for p in diners if p.id == diner_id)


def test_menu_tier_peanut_blocks_peanut_allergy(sample_menu):
    dan = DinerProfile(id="dan", name="Dan", allergies=[Allergen.PEANUT])
    assert not can_eat(sample_menu.dish("kung_pao_chicken"), dan)


def test_inferred_tier_also_blocks(sample_menu):
    # Dan Dan noodles: peanut is inferred at 0.6, still blocks the peanut allergy.
    dan = DinerProfile(id="dan", name="Dan", allergies=[Allergen.PEANUT])
    assert not can_eat(sample_menu.dish("dan_dan_noodles"), dan)


def test_unknown_tier_blocks_coverage_and_raises_a_question(sample_menu, sample_group):
    amy = by_id(sample_group, "amy")  # shellfish + fish allergy
    dish = sample_menu.dish("di_san_xian")  # shellfish flag is tier=unknown (oyster sauce)
    assert not can_eat(dish, amy)
    qs = open_questions(dish, [amy])
    assert any("oyster" in q.lower() or "shellfish" in q.lower() for q in qs)


def test_menu_tier_fish_blocks_fish_allergy(sample_menu, sample_group):
    amy = by_id(sample_group, "amy")
    assert not can_eat(sample_menu.dish("boiled_fish_chili_oil"), amy)


def test_null_vegetarian_flag_is_unsafe(sample_menu, sample_group):
    david = by_id(sample_group, "david")
    assert not can_eat(sample_menu.dish("mapo_tofu"), david)  # is_vegetarian: null
    assert can_eat(sample_menu.dish("garlic_seasonal_greens"), david)


def test_no_pork_treats_null_as_unsafe(sample_menu, sample_group):
    tom = by_id(sample_group, "tom")
    assert not can_eat(sample_menu.dish("hot_and_sour_soup"), tom)  # contains_pork: null
    assert can_eat(sample_menu.dish("kung_pao_chicken"), tom)


def test_plain_greens_do_not_imply_allergen_review(sample_menu, sample_group):
    assert edible_by(sample_menu.dish("garlic_seasonal_greens"), sample_group) == [
        p.id for p in sample_group if not p.allergies
    ]


def test_diet_flags_on_ad_hoc_dishes():
    diner = DinerProfile(id="x", name="X", diets=[Diet.NO_BEEF])
    assert not can_eat(Dish(id="a", contains_beef=None), diner)
    assert can_eat(Dish(id="b", contains_beef=False), diner)
