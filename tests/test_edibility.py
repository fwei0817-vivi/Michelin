from michelin.plan.edibility import can_eat, edible_by, open_questions
from michelin.schemas import Allergen, Diet, DinerProfile


def by_id(diners, diner_id):
    return next(p for p in diners if p.id == diner_id)


def test_menu_tier_peanut_blocks_peanut_allergy(sample_menu, sample_group):
    dan = by_id(sample_group, "dan")
    assert not can_eat(sample_menu.dish("kung_pao_chicken"), dan)


def test_inferred_tier_also_blocks(sample_menu, sample_group):
    # Dan Dan noodles: peanut is inferred at 0.6, still blocks the peanut allergy.
    dan = by_id(sample_group, "dan")
    assert not can_eat(sample_menu.dish("dan_dan_noodles"), dan)


def test_unknown_tier_does_not_block_but_raises_a_question(sample_menu, sample_group):
    ben = by_id(sample_group, "ben")  # shellfish allergy
    dish = sample_menu.dish("di_san_xian")  # shellfish flag is tier=unknown (oyster sauce)
    assert can_eat(dish, ben)
    qs = open_questions(dish, [ben])
    assert any("oyster" in q.lower() or "shellfish" in q.lower() for q in qs)


def test_null_vegetarian_flag_is_unsafe(sample_menu, sample_group):
    amy = by_id(sample_group, "amy")
    assert not can_eat(sample_menu.dish("mapo_tofu"), amy)  # is_vegetarian: null
    assert can_eat(sample_menu.dish("garlic_seasonal_greens"), amy)


def test_edible_by_lists_everyone_for_plain_greens(sample_menu, sample_group):
    assert edible_by(sample_menu.dish("garlic_seasonal_greens"), sample_group) == [p.id for p in sample_group]


def test_no_pork_treats_null_as_unsafe():
    diner = DinerProfile(id="x", name="X", diets=[Diet.NO_PORK])
    from michelin.schemas import Dish

    assert not can_eat(Dish(id="a", contains_pork=None), diner)
    assert can_eat(Dish(id="b", contains_pork=False), diner)
    assert not can_eat(Dish(id="c", contains_pork=True), diner)


def test_allergen_enum_roundtrip():
    assert Allergen("shellfish") is Allergen.SHELLFISH
