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

from michelin.plan import spice
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


def _pool(menu, request):
    excluded = set(request.excluded_dish_ids)
    return [
        d
        for d in menu.dishes
        if d.category.value != "staple"
        and d.price is not None
        and d.id not in excluded
        and edible_by(d, request.diners)
    ]


def best_possible(menu, request) -> int:
    """The smallest deficit this menu allows at any price (e.g. nothing on it is 'ok' for a
    diner): the rule asks for this much, not the impossible."""
    pool = _pool(menu, request)
    return _deficit_v([_vec(d, request.diners) for d in pool], request.n_diners)


def cheapest(menu, request, start_ids=()) -> tuple[list, float] | None:
    """A greedy cheap order reaching the best this menu allows, from kept dishes: (dishes,
    menu subtotal incl. rice). None only if the menu has no priced dish at all."""
    key = (
        menu.model_dump_json(include={"dishes"}).__hash__(),
        request.model_dump_json().__hash__(),
        tuple(start_ids),
    )
    if key in _CHEAP:
        return _CHEAP[key]
    diners, n = request.diners, request.n_diners
    known = {d.id: d for d in menu.dishes}
    chosen = [known[i] for i in dict.fromkeys([*request.locked_dish_ids, *start_ids]) if i in known]
    pool = _pool(menu, request)
    if not pool:
        return None
    vec = {d.id: _vec(d, diners) for d in [*pool, *chosen]}
    target = _deficit_v([vec[d.id] for d in pool], n)
    cur_v = [vec[d.id] for d in chosen if d.category.value != "staple"]
    cur = _deficit_v(cur_v, n)
    while cur > target:
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
    result = (chosen, sum(d.price or 0 for d in chosen) + _rice(menu, request))
    if len(_CHEAP) > 256:
        _CHEAP.clear()
    _CHEAP[key] = result
    return result


def _cap(request) -> float:
    return subtotal_cap(request.all_in_budget, 1, request.tax_rate, request.tip_rate)


def budget_needed(menu, request) -> float | None:
    """The per-person all-in budget (whole dollars) that would buy the best order."""
    found = cheapest(menu, request)
    if found is None:
        return None
    t = totals(found[1], request.n_diners, request.tax_rate, request.tip_rate)
    return float(math.ceil(t.per_person))


def feasible(menu, request) -> bool:
    """The best this menu allows fits the budget."""
    found = cheapest(menu, request)
    return found is not None and found[1] <= _cap(request) + 1e-6


def top_up(menu, request, items):
    """Code's own fix after the AI (QA r20): add, or swap in for a dish that is not kept,
    the cheapest suitable dishes until the rule is met as far as this menu and budget allow.
    Every step must pass validate_order (allergies, diets, budget, kept dishes). Returns
    (new items, added ids, dropped ids) or None when nothing improves."""
    from michelin.plan.validation import family_repeats, validate_order
    from michelin.schemas import PlanItem

    target = best_possible(menu, request)
    cur_items = list(items)
    added, dropped = [], []
    locked = set(request.locked_dish_ids)
    pool = _pool(menu, request)
    n = request.n_diners
    vec = {d.id: _vec(d, request.diners) for d in pool}

    def v(i):
        d = menu.dish(i)
        return vec.get(i) or _vec(d, request.diners) if d.category.value != "staple" else None

    for _ in range(2 * n + 2):
        vs = {i.dish_id: v(i.dish_id) for i in cur_items}
        base = [x for x in vs.values() if x is not None]
        cur = _deficit_v(base, n)
        if cur <= target:
            break
        have = set(vs)
        sub0 = sum((menu.dish(i.dish_id).price or 0) * i.quantity for i in cur_items)
        cands = []
        for d in pool:
            if d.id in have:
                continue
            if any(spice.taste(d, p) for p in request.diners):  # no heat for no-heat diners
                continue
            if not is_hot(d):  # QA r22: only dishes that count toward the rule (no snacks)
                continue
            new = _deficit_v([*base, vec[d.id]], n)
            if new < cur:
                cands.append(((new, sub0 + d.price, 0), d.id, None))
            for x in cur_items:
                if x.dish_id in locked or vs[x.dish_id] is None:
                    continue
                rest = [y for k, y in vs.items() if k != x.dish_id and y is not None]
                new = _deficit_v([*rest, vec[d.id]], n)
                if new < cur:
                    price = sub0 - (menu.dish(x.dish_id).price or 0) * x.quantity + d.price
                    cands.append(((new, price, 1), d.id, x.dish_id))
        cands.sort(key=lambda c: c[0])
        best = None
        for _k, add, drop in cands[:60]:
            option = [i for i in cur_items if i.dish_id != drop] + [
                PlanItem(dish_id=add, quantity=1)
            ]
            if family_repeats(menu, request, [i.dish_id for i in option]):
                continue
            if validate_order(menu, request, option)["valid"]:
                best = (option, add, drop)
                break
        if best is None:
            break
        cur_items, add, drop = best
        added.append(add)
        if drop:
            dropped.append(drop)
    if not added:
        return None
    return cur_items, added, dropped


def _plural(n, word):
    return f"{n} {word}{'es' if word.endswith('sh') and n != 1 else ('s' if n != 1 else '')}"


def honest_line(menu, request, items) -> str | None:
    """None when the order meets the rule; otherwise plain sentences: what is missing for
    whom, then the cause (this menu, or the budget) (QA r20: one sentence per message)."""
    dishes = [menu.dish(i.dish_id) for i in items]
    if deficit(dishes, request.diners) == 0:
        return None
    t = tally(dishes, request.diners)
    pool = _pool(menu, request)
    out = []
    if t.hot < request.n_diners:
        out.append(
            f"This order has no hot dishes for {request.n_diners} people."
            if t.hot == 0
            else f"This order has only {_plural(t.hot, 'hot dish')} for {request.n_diners} people."
        )
    menu_short = []
    for p in request.diners:
        g, gh = t.good[p.id], t.good_hot[p.id]
        if g >= 2 and gh >= 1:
            continue
        name = p.name or p.id
        on_menu = sum(good_for(d, p) for d in pool)
        hot_on_menu = sum(good_for(d, p) and is_hot(d) for d in pool)
        if g == 0:
            out.append(f"{name} has no dish they can eat without asking the server.")
        elif g < 2:
            out.append(f"{name} has only 1 dish they can eat without asking the server.")
        else:
            out.append(f"{name} has no hot dish they can eat without asking the server.")
        if on_menu < 2 or (gh < 1 and hot_on_menu == 0):
            menu_short.append(name)
    if menu_short:
        who = (
            menu_short[0]
            if len(menu_short) == 1
            else ", ".join(menu_short[:-1]) + " and " + menu_short[-1]
        )
        out.append(f"This menu has too few dishes {who} can eat without asking.")
    if not feasible(menu, request):
        need = budget_needed(menu, request)
        if need is not None:
            out.append(
                f"The budget is too tight for more: about ${need:.0f} per person would cover it."
            )
    return " ".join(out)
