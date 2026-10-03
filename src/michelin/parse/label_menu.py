"""Label a menu JSON from its printed names and descriptions, for human review.

    uv run python -m michelin.parse.label_menu draft.json -o data/menus/<slug>.json

The input is a `Menu` whose dishes need only id, names, price and description; any existing
ingredient, allergen or diet labels are replaced. The output is always `verified: false`.
A person must check every dish against the menu photo, then set `verified: true`. The
summary lists unrecognized dishes first: those are the ones to review hardest. With `--llm`,
names the knowledge base misses are sent to Claude (see parse/matcher.py); its answers are
stored in data/knowledge/llm_matches.json and reused.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from michelin.parse.knowledge import label_dish
from michelin.parse.matcher import match_names
from michelin.schemas import Dish, Menu

PRINTED_FIELDS = ("id", "name_zh", "name_en", "price", "description_raw", "category", "portion")


def relabel(
    menu: Menu, call_api: bool | None = None
) -> tuple[Menu, list[tuple[str, str | None, tuple[str, ...]]]]:
    printed = [Dish(**{k: getattr(d, k) for k in PRINTED_FIELDS}) for d in menu.dishes]
    suggested = match_names(printed, call_api=call_api)
    dishes, summary = [], []
    for dish in printed:
        labeled = label_dish(dish, suggested=suggested.get(dish.id))
        dishes.append(labeled.dish)
        summary.append((dish.id, labeled.match, labeled.sauces))
    return menu.model_copy(update={"dishes": dishes, "verified": False}), summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("menu", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="write here instead of stdout")
    ap.add_argument("--llm", action="store_true", help="ask Claude about unrecognized names")
    args = ap.parse_args(argv)

    menu = Menu.model_validate_json(args.menu.read_text(encoding="utf-8"))
    labeled, summary = relabel(menu, call_api=args.llm or None)
    body = labeled.model_dump_json(indent=2) + "\n"
    if args.out:
        args.out.write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)

    unknown = [row for row in summary if row[1] is None]
    print(
        f"{len(summary)} dishes, {len(summary) - len(unknown)} recognized, "
        f"{len(unknown)} not in the knowledge base. Output is unverified.",
        file=sys.stderr,
    )
    for dish_id, match, sauces in sorted(summary, key=lambda r: r[1] is not None):
        via = f" + sauces {', '.join(sauces)}" if sauces else ""
        print(f"  {dish_id:28} {match or 'NOT RECOGNIZED: review by hand'}{via}", file=sys.stderr)


if __name__ == "__main__":
    main()
