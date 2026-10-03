"""Write a review checklist for labeled, unverified menus.

    uv run python -m michelin.parse.review_sheet data/menus/a.json data/menus/b.json -o REVIEW.md

Orders the work by risk: dishes the knowledge base does not know (labels are all "unknown"),
dishes matched by the LLM (confirm it is the same dish), and dishes where the restaurant's own
tags disagree with the labels (for example a dish printed as [V] that the knowledge base
says contains meat). Everything else still needs the normal check against the menu.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from michelin.parse.knowledge import load_kb, match
from michelin.parse.matcher import cache_key, load_cache
from michelin.schemas import Menu


def _blocks(dish) -> str:
    out = []
    if dish.is_vegetarian is False:
        out.append("not vegetarian")
    elif dish.is_vegetarian is None:
        out.append("vegetarian unknown")
    out += [
        f"{f.allergen.value} ({f.tier.value})"
        for f in dish.allergens
        if f.tier.value != "unknown" or f.confidence > 0
    ]
    return "; ".join(out) or "nothing flagged"


def sheet(menu: Menu) -> list[str]:
    kb, cache = load_kb(), load_cache()
    unknown, by_llm, disagree, rest = [], [], [], []
    for d in menu.dishes:
        name = f"{d.name_en} {d.name_zh or ''} (${d.price:g})".strip()
        printed = d.description_raw or ""
        if match(d, kb) is None:
            stored = cache["matches"].get(cache_key(d))
            if stored and stored["kb_id"]:
                by_llm.append(f"- [ ] **{name}** read as `{stored['kb_id']}`: {_blocks(d)}")
            else:
                unknown.append(f"- [ ] **{name}**: {printed or 'no description'}")
        else:
            rest.append(f"- [ ] {name}: {_blocks(d)}")
        if re.search(r"\[V( GF)?\]|\bV\b", printed) and d.is_vegetarian is False:
            disagree.append(f"- [ ] **{name}**: restaurant marks it vegetarian; labels say not.")
    return [
        f"## {menu.restaurant_name} (`{menu.restaurant_id}`)",
        "",
        f"### 1. Not recognized ({len(unknown)}): fill ingredients and diet flags by hand",
        *unknown,
        "",
        f"### 2. Matched by the LLM ({len(by_llm)}): confirm it is the same dish",
        *by_llm,
        "",
        f"### 3. Restaurant tags disagree with labels ({len(disagree)})",
        *(disagree or ["- none"]),
        "",
        f"### 4. Recognized ({len(rest)}): spot-check against the menu",
        *rest,
        "",
    ]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("menus", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args(argv)
    lines = [
        "# Menu review checklist",
        "",
        (
            "Check each dish against the restaurant's menu, fix labels in the menu JSON (or in "
            'the app\'s menu editor), then set `"verified": true`. Unknown stays unknown when '
            "the menu does not say: ask the restaurant rather than guess."
        ),
        "",
    ]
    for path in args.menus:
        lines += sheet(Menu.model_validate_json(path.read_text(encoding="utf-8")))
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
