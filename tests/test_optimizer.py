import pytest

from michelin.explain import explain
from michelin.plan.budget import totals
from michelin.plan.edibility import edible_by
from michelin.plan.optimizer import solve
from michelin.plan.portions import required_range, total_units
from michelin.schemas import Conflict, Plan, TableRequest


def request_for(group, **kwargs):
    return TableRequest(menu_id="sample_sichuan", diners=group, budget_per_person=25, **kwargs)


def test_real_plan_respects_budget_coverage_and_portions(sample_menu, sample_group):
    req = request_for(sample_group)
    plan = solve(sample_menu, req)
    assert isinstance(plan, Plan)
    dishes = [sample_menu.dish(i.dish_id) for i in plan.items]
    assert plan.total <= req.budget_per_person * len(sample_group)
    lo, hi = required_range(len(sample_group))
    assert lo <= total_units(dishes) <= hi
    for person in sample_group:
        assert (
            sum(
                person.id in i.edible_by
                for i in plan.items
                if sample_menu.dish(i.dish_id).category.value != "staple"
            )
            >= 2
        )
    for item in plan.items:
        assert item.edible_by == edible_by(sample_menu.dish(item.dish_id), sample_group)
        assert item.reason
    expected = totals(
        sum(sample_menu.dish(i.dish_id).price * i.quantity for i in plan.items),
        len(sample_group),
        req.tax_rate,
        req.tip_rate,
    )
    assert plan.total == expected.total


def test_keep_and_remove_are_enforced(sample_menu, sample_group):
    req = request_for(
        sample_group,
        locked_dish_ids=["kung_pao_chicken"],
        excluded_dish_ids=["boiled_fish_chili_oil"],
    )
    plan = solve(sample_menu, req)
    assert isinstance(plan, Plan)
    ids = {i.dish_id for i in plan.items}
    assert "kung_pao_chicken" in ids
    assert "boiled_fish_chili_oil" not in ids


def test_budget_relaxation_is_actually_feasible(sample_menu, sample_group):
    req = request_for(sample_group).model_copy(update={"budget_per_person": 5})
    conflict = solve(sample_menu, req)
    assert isinstance(conflict, Conflict)
    budget = next(r.new_value for r in conflict.relaxations if r.kind == "budget")
    plan = solve(sample_menu, req.model_copy(update={"budget_per_person": budget}))
    assert isinstance(plan, Plan)
    assert plan.total <= budget * len(sample_group)


def test_impossible_kept_dish_never_silently_disappears(sample_menu, sample_group):
    req = request_for(
        sample_group, locked_dish_ids=["kung_pao_chicken"], excluded_dish_ids=["kung_pao_chicken"]
    )
    assert isinstance(solve(sample_menu, req), Conflict)


def test_explanation_does_not_recommend_fish_to_fish_allergy(sample_menu, sample_group):
    from michelin.schemas import PlanItem

    fish = sample_menu.dish("boiled_fish_chili_oil")
    plan = Plan(
        items=[PlanItem(dish_id=fish.id, edible_by=edible_by(fish, sample_group))],
        subtotal=0,
        tax=0,
        tip=0,
        total=0,
        per_person=0,
        variety_score=0,
    )
    result = explain(plan, sample_menu, request_for(sample_group))
    assert "Amy" not in result.items[0].reason


def test_search_timeout_is_not_reported_as_infeasible(sample_menu, sample_group, monkeypatch):
    from michelin.plan import optimizer

    monkeypatch.setattr(optimizer, "_search", lambda *a, **kw: (None, False))
    with pytest.raises(TimeoutError):
        optimizer.solve(sample_menu, request_for(sample_group))


def test_course_target_and_favorite_style_affect_real_selection():
    from michelin.schemas import DinerProfile, Dish, IngredientClaim, Menu

    people = [DinerProfile(id="a", name="A", likes=["tofu"]), DinerProfile(id="b", name="B")]
    menu = Menu(
        restaurant_id="small",
        restaurant_name="Small",
        cuisine="test",
        source="test",
        verified=True,
        dishes=[
            Dish(id="rice", name_en="Rice", category="staple", price=1),
            Dish(
                id="a",
                name_en="Chicken",
                price=5,
                portion="medium",
                main_ingredients=[IngredientClaim(name="chicken", tier="menu")],
            ),
            Dish(
                id="b",
                name_en="Tofu",
                price=5,
                portion="medium",
                main_ingredients=[IngredientClaim(name="tofu", tier="menu")],
            ),
            Dish(id="c", name_en="Greens", price=5, portion="small"),
            Dish(id="d", name_en="Mushrooms", price=5, portion="small"),
        ],
    )
    req = TableRequest(
        menu_id="small",
        diners=people,
        budget_per_person=30,
        min_dishes_per_person=1,
        dish_count_target=3,
    )
    shorter = solve(menu, req)
    longer = solve(menu, req.model_copy(update={"dish_count_target": 4}))
    assert isinstance(shorter, Plan) and isinstance(longer, Plan)
    assert len(shorter.items) == 3
    assert len(longer.items) == 4
    favorite = solve(menu, req.model_copy(update={"style_preference": "favorites"}))
    assert isinstance(favorite, Plan)
    assert "b" in {i.dish_id for i in favorite.items}
