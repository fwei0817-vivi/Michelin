from michelin.plan.portions import is_enough, required_range, total_units, units
from michelin.schemas import Dish, DishCategory, PortionClass


def dish(portion: PortionClass, category: DishCategory = DishCategory.STIR_FRY) -> Dish:
    return Dish(id=f"{category.value}_{portion.value}", portion=portion, category=category)


def test_staples_contribute_nothing():
    assert units(dish(PortionClass.INDIVIDUAL, DishCategory.STAPLE)) == 0.0


def test_six_medium_plates_feed_six():
    plates = [dish(PortionClass.MEDIUM) for _ in range(6)]
    assert is_enough(plates, 6)


def test_two_plates_do_not_feed_six():
    assert not is_enough([dish(PortionClass.MEDIUM)] * 2, 6)


def test_range_scales_with_group_size():
    lo, hi = required_range(4)
    assert lo < hi
    assert total_units([dish(PortionClass.LARGE), dish(PortionClass.MEDIUM), dish(PortionClass.MEDIUM), dish(PortionClass.SHARED)]) >= lo
