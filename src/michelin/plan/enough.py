"""The 'enough food' rule (2026-10-10), enforced in code; the AI only picks dishes.

1. At least N hot dishes for N diners: course "hot_main" or "staple" (fried rice, noodles).
   Plain rice (category "staple") is extra; cold dishes, soups, desserts, sides and dishes
   of unknown course are allowed but do not count.
2. Each diner has at least 2 dishes that are "ok" for them (no server confirmation) and not
   a taste conflict (too spicy), and at least 1 of those is a hot dish.
3. When the budget cannot buy such an order, the plan is kept but says so honestly, with
   the per-person budget that would cover it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from michelin.plan.budget import subtotal_cap, totals
from michelin.plan.dish_facts import course_of
from michelin.plan.edibility import diner_status, edible_by

HOT = {"hot_main", "staple"}


def course(dish) -> str:
    return dish.course or course_of(dish.category, None)


def is_hot(dish) -> bool:
    """A hot dish that counts as food: never plain rice, never unknown."""
    return dish.category.value != "staple" and course(dish) in HOT


def good_for(dish, p) -> bool:
    """'ok' (no server confirm) and no taste conflict."""
    s = diner_status(dish, [p])[p.id]
    return s["status"] == "ok" and s["taste"] != "too_spicy"


@dataclass
class Tally:
    hot: int
    good: dict  # diner id -> dishes good for them
    good_hot: dict  # diner id -> hot dishes good for them


def tally(dishes, diners) -> Tally:
    shared = [d for d in dishes if d.category.value != "staple"]
    return Tally(
        hot=sum(is_hot(d) for d in shared),
        good={p.id: sum(good_for(d, p) for d in shared) for p in diners},
        good_hot={p.id: sum(good_for(d, p) and is_hot(d) for d in shared) for p in diners},
    )


def deficit(dishes, diners) -> int:
    t = tally(dishes, diners)
    n = len(diners)
    return max(0, n - t.hot) + sum(
        max(0, 2 - t.good[p.id]) + max(0, 1 - t.good_hot[p.id]) for p in diners
    )


def _names(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def gaps(dishes, diners) -> list[str]:
    """What the order misses, in words for the AI's retry and for the page."""
    t = tally(dishes, diners)
    out = []
    if t.hot < len(diners):
        out.append(
            f"Only {t.hot} hot dish{'es' if t.hot != 1 else ''} (hot mains, fried rice or "
            f"noodles) for {len(diners)} people; order at least {len(diners)}."
        )
    for p in diners:
        name = p.name or p.id
        if t.good[p.id] < 2 or t.good_hot[p.id] < 1:
            out.append(
                f"{name} ({p.id}) has {t.good[p.id]} dish{'es' if t.good[p.id] != 1 else ''} "
                f"they can eat without asking the server and that suit their taste "
                f"({t.good_hot[p.id]} hot); they need at least 2, one of them hot."
            )
    return out


def _rice(menu, request) -> float:
    from michelin.plan.validation import staple_required

    if not staple_required(menu, request):
        return 0.0
    rice = [
        d
        for d in menu.dishes
        if d.category.value == "staple"
        and d.price is not None
        and len(edible_by(d, request.diners)) == request.n_diners
    ]
    return min(d.price for d in rice) * request.n_diners if rice else 0.0


def _vec(d, diners):
    hot = is_hot(d)
    good = tuple(good_for(d, p) for p in diners)
    return hot, good


def _deficit_v(vecs, n) -> int:
    hot = sum(v[0] for v in vecs)
    out = max(0, n - hot)
    for k in range(n):
        g = sum(v[1][k] for v in vecs)
        gh = sum(v[1][k] and v[0] for v in vecs)
        out += max(0, 2 - g) + max(0, 1 - gh)
    return out


_CHEAP: dict = {}


def cheapest(menu, request, start_ids=()) -> tuple[list, float] | None:
    """A greedy cheap order meeting the rule, starting from kept dishes: (dishes, menu
    subtotal incl. rice), or None if the menu cannot meet it at any price."""
    key = (
        id(menu),
        menu.model_dump_json(include={"dishes"}).__hash__(),
        request.model_dump_json().__hash__(),
        tuple(start_ids),
    )
    if key in _CHEAP:
        return _CHEAP[key]
    diners, n = request.diners, request.n_diners
    excluded = set(request.excluded_dish_ids)
    known = {d.id: d for d in menu.dishes}
    chosen = [known[i] for i in dict.fromkeys([*request.locked_dish_ids, *start_ids]) if i in known]
    pool = [
        d
        for d in menu.dishes
        if d.category.value != "staple" and d.price is not None and d.id not in excluded
    ]
    vec = {d.id: _vec(d, diners) for d in [*pool, *chosen]}
    cur_v = [vec[d.id] for d in chosen if d.category.value != "staple"]
    cur = _deficit_v(cur_v, n)
    result = None
    while True:
        if cur == 0:
            result = (chosen, sum(d.price or 0 for d in chosen) + _rice(menu, request))
            break
        best = None
        ids = {d.id for d in chosen}
        for d in pool:
            if d.id in ids:
                continue
            gain = cur - _deficit_v([*cur_v, vec[d.id]], n)
            if gain > 0:
                k = (-(gain / max(d.price, 0.5)), d.price)
                if best is None or k < best[0]:
                    best = (k, d, gain)
        if best is None:
            break
        chosen.append(best[1])
        cur_v.append(vec[best[1].id])
        cur -= best[2]
    if len(_CHEAP) > 256:
        _CHEAP.clear()
    _CHEAP[key] = result
    return result


def budget_needed(menu, request) -> float | None:
    """The per-person all-in budget (whole dollars) that would buy an order meeting the rule."""
    found = cheapest(menu, request)
    if found is None:
        return None
    t = totals(found[1], request.n_diners, request.tax_rate, request.tip_rate)
    return float(math.ceil(t.per_person))


def feasible(menu, request) -> bool:
    found = cheapest(menu, request)
    if found is None:
        return False
    cap = subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)
    return found[1] <= cap + 1e-6


def honest_line(menu, request, items) -> str | None:
    """None when the order meets the rule; otherwise one plain sentence for the page."""
    dishes = [menu.dish(i.dish_id) for i in items]
    if deficit(dishes, request.diners) == 0:
        return None
    t = tally(dishes, request.diners)
    short = [p for p in request.diners if t.good[p.id] < 2 or t.good_hot[p.id] < 1]
    parts = []
    if t.hot < request.n_diners:
        parts.append(f"{t.hot} hot dish{'es' if t.hot != 1 else ''} for {request.n_diners} people")
    for p in short:
        g, gh = t.good[p.id], t.good_hot[p.id]
        name = p.name or p.id
        if g < 2:
            parts.append(
                f"{name} has only {g} dish{'es' if g != 1 else ''} they can eat without asking"
                + (f" ({gh} hot)" if g else "")
            )
        else:
            parts.append(f"{name} has no hot dish they can eat without asking")
    need = budget_needed(menu, request)
    lead = "At this budget only " if not feasible(menu, request) else "This order has only "
    line = lead + "; ".join(parts) + "."
    if need is not None and not feasible(menu, request):
        line += f" About ${need:.0f} per person would cover enough hot dishes for everyone."
    elif need is None:
        line += " This menu has no order that covers everyone that way."
    return line
