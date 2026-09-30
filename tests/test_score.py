from michelin.plan.score import variety_score
from michelin.schemas import Dish, DishCategory, EvidenceTier, IngredientClaim


def d(id, category, method, protein):
    return Dish(
        id=id,
        category=category,
        cooking_method=method,
        main_ingredients=[IngredientClaim(name=protein, tier=EvidenceTier.MENU)],
    )


def test_varied_table_scores_higher_than_monotone_table():
    varied = [
        d("a", DishCategory.COLD_APPETIZER, "poach", "pork"),
        d("b", DishCategory.STIR_FRY, "stir_fry", "chicken"),
        d("c", DishCategory.SOUP, "simmer", "egg"),
        d("d", DishCategory.BRAISE_OR_STEW, "braise", "tofu"),
    ]
    monotone = [d(f"m{i}", DishCategory.STIR_FRY, "stir_fry", "pork") for i in range(4)]
    assert variety_score(varied) > variety_score(monotone)


def test_mostly_fried_table_is_penalized():
    fried = [d(f"f{i}", DishCategory.STIR_FRY, "deep_fry", p) for i, p in enumerate(("pork", "chicken", "fish"))]
    not_fried = [d(f"n{i}", DishCategory.STIR_FRY, "stir_fry", p) for i, p in enumerate(("pork", "chicken", "fish"))]
    assert variety_score(fried) < variety_score(not_fried)


def test_staples_are_ignored():
    assert variety_score([Dish(id="rice", category=DishCategory.STAPLE)]) == 0.0
