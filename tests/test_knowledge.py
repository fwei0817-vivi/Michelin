from michelin.parse.knowledge import label_dish, load_kb, normalize, validate_kb
from michelin.schemas import Allergen, Dish, DishCategory, EvidenceTier


def dish(name_en=None, name_zh=None, description=None):
    return Dish(id="d", name_en=name_en, name_zh=name_zh, price=10.0, description_raw=description)


def tiers(labeled, allergen):
    return {f.tier for f in labeled.dish.allergens if f.allergen == allergen}


def test_knowledge_base_is_valid():
    assert validate_kb(load_kb()) == []


def test_name_inference_mapo_tofu_has_meat_even_when_menu_says_tofu():
    out = label_dish(dish("Mapo Tofu", description="soft tofu, chili bean sauce"))
    assert out.match == "mapo_tofu"
    assert out.dish.is_vegetarian is False
    assert out.dish.contains_pork is True  # likely pork blocks a no-pork diner
    assert out.dish.contains_beef is None  # possible beef: ask, never certify


def test_chinese_name_matches_without_english():
    assert label_dish(dish(name_zh="宫保鸡丁")).match == "kung_pao_chicken"


def test_hidden_peanut_in_kung_pao_is_inferred_not_printed():
    out = label_dish(dish("Kung Pao Chicken", description="diced chicken, dried chili"))
    assert tiers(out, Allergen.PEANUT) == {EvidenceTier.INFERRED}


def test_fish_fragrant_eggplant_is_not_a_fish_dish():
    out = label_dish(dish("Fish-Fragrant Eggplant", "鱼香茄子", "eggplant in garlic sauce"))
    assert out.match == "yuxiang_eggplant"
    assert Allergen.FISH not in {f.allergen for f in out.dish.allergens}
    # Possible minced pork: a vegetarian may order after asking; no-pork stays strict.
    assert out.dish.is_vegetarian is True
    assert out.dish.contains_pork is None
    assert any("minced pork" in q for q in out.dish.confirm_with_staff)


def test_printed_ingredient_is_menu_tier():
    out = label_dish(dish("Vegetable Lo Mein", description="egg noodles, cabbage"))
    assert tiers(out, Allergen.EGG) == {EvidenceTier.MENU}
    assert out.dish.is_vegan is False


def test_possible_oyster_sauce_is_unknown_with_a_question():
    out = label_dish(dish("Garlic Bok Choy"))
    assert tiers(out, Allergen.SHELLFISH) == {EvidenceTier.UNKNOWN}  # allergy: strict
    assert out.dish.is_vegetarian is True  # diet: eligible, with the question below
    assert any("oyster sauce" in q for q in out.dish.confirm_with_staff)


def test_unknown_dish_is_never_certified():
    out = label_dish(dish("Chef's Mystery Special", description="seasonal vegetables"))
    assert out.match is None
    assert out.dish.is_vegetarian is None and out.dish.is_vegan is None
    assert out.dish.contains_pork is None
    assert {f.allergen for f in out.dish.allergens} == set(Allergen)
    assert all(f.tier == EvidenceTier.UNKNOWN for f in out.dish.allergens)
    assert any("not a dish we recognize" in q for q in out.dish.confirm_with_staff)


def test_sauce_rule_catches_xo_on_an_unknown_dish():
    out = label_dish(dish("Long Beans in XO Sauce", description="long beans, XO sauce"))
    assert out.match is None
    assert "xo_sauce" in out.sauces
    assert tiers(out, Allergen.SHELLFISH) == {EvidenceTier.INFERRED}
    assert out.dish.is_vegetarian is False


def test_lobster_sauce_is_egg_not_lobster():
    out = label_dish(dish("Shrimp with Lobster Sauce"))
    assert out.match == "shrimp_lobster_sauce"
    shellfish = [f for f in out.dish.allergens if f.allergen == Allergen.SHELLFISH]
    assert all("lobster" not in f.reason for f in shellfish)
    assert tiers(out, Allergen.EGG)


def test_labels_are_deterministic():
    d = dish("House Special Fried Rice", description="rice, peas, scallion")
    assert label_dish(d).dish == label_dish(d).dish


def test_category_filled_only_when_unknown():
    out = label_dish(dish("Hot and Sour Soup"))
    assert out.dish.category == DishCategory.SOUP
    kept = label_dish(dish("Hot and Sour Soup").model_copy(update={"category": "stir_fry"}))
    assert kept.dish.category == DishCategory.STIR_FRY


def test_normalize_handles_menu_numbering_and_counts():
    assert normalize("C12. General Tso's Chicken (2)") == "general tsos chicken"
    assert normalize("Hot & Sour Soup") == "hot and sour soup"
    assert normalize("AS8. Kung Pao Chicken") == "kung pao chicken"
    assert normalize("A20.Crispy Chicken Wings") == "crispy chicken wings"
    assert normalize("CSM3. Lobster") == "lobster"


def test_relabel_menu_is_unverified_and_keeps_printed_fields(sample_menu):
    from michelin.parse.label_menu import relabel

    labeled, summary = relabel(sample_menu.model_copy(update={"verified": True}))
    assert labeled.verified is False
    assert [d.price for d in labeled.dishes] == [d.price for d in sample_menu.dishes]
    matches = {dish_id: m for dish_id, m, _ in summary}
    assert matches["mapo_tofu"] == "mapo_tofu"
    assert matches["dry_pot_cauliflower"] is None  # not in the knowledge base


def test_crab_meat_is_shellfish_not_meat():
    from michelin.parse.knowledge import gather

    d = dish("Braised Tofu with Crab Meat", description="stewed crab roe and tofu")
    hits = {h for c in gather(d)[0] for h in c.hits}
    assert "shellfish" in hits and "meat" not in hits
    assert "meat" in {h for c in gather(dish("Lamb with Cumin"))[0] for h in c.hits}
