import pytest

from michelin.plan.budget import subtotal_cap, totals


def test_cap_is_all_in():
    # 6 people x $25 with NYC tax and 18% tip leaves about $118 of menu price.
    cap = subtotal_cap(25.0, 6, 0.08875, 0.18)
    assert cap == 118.23
    assert totals(cap + 0.01, 6, 0.08875, 0.18).total > 150
    assert totals(cap, 6, 0.08875, 0.18).total == pytest.approx(150.0, abs=0.02)


def test_per_person_matches_budget_at_the_cap():
    cap = subtotal_cap(25.0, 4, 0.08875, 0.18)
    assert totals(cap, 4, 0.08875, 0.18).per_person == pytest.approx(25.0, abs=0.01)


def test_zero_tax_and_tip_means_cap_equals_budget():
    assert subtotal_cap(20.0, 3, 0.0, 0.0) == 60.0
