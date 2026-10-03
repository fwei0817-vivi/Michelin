"""Accuracy and run-to-run consistency of the LLM name matcher (live API, costs money).

    uv run --extra llm python eval/matcher_eval.py --runs 5

Sends every name in menus/name_variants.json to Claude `--runs` times, bypassing the stored
answers, and reports how often each answer matches the expected entry and whether repeated
runs agree. In the app, stored answers make matching deterministic; this measures what the
model does before an answer is stored. Results go to eval/results/matcher.md.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from michelin.parse.knowledge import load_kb, match
from michelin.parse.matcher import MODEL, ask_claude
from michelin.schemas import Dish

EVAL = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    kb = load_kb()
    variants = json.loads((EVAL / "menus/name_variants.json").read_text(encoding="utf-8"))
    rows = []
    for i, v in enumerate(variants["variants"]):
        d = Dish(id=f"v{i}", name_en=v["name_en"], name_zh=v.get("name_zh"), price=1.0)
        if match(d, kb):
            print(f"skip {v['name_en']!r}: already an exact knowledge-base match")
            continue
        rows.append((v, d))
    dishes = [d for _, d in rows]

    answers = [[a or "none" for a in ask_claude(dishes, kb)] for _ in range(args.runs)]
    per_name = [[run[i] for run in answers] for i in range(len(rows))]

    correct = sum(a == v["expect"] for (v, _), got in zip(rows, per_name, strict=True)
                  for a in got)  # fmt: skip
    stable = sum(len(set(got)) == 1 for got in per_name)
    dangerous = [
        (v["name_en"], a)
        for (v, _), got in zip(rows, per_name, strict=True)
        for a in set(got)
        if v["expect"] == "none" and a != "none"
    ]
    lines = [
        f"# LLM matcher: {MODEL}, {args.runs} runs x {len(rows)} names",
        "",
        "| Metric | Value |",
        "|---|---|",
        (
            f"| Correct answers | {correct}/{len(rows) * args.runs} "
            f"({correct / (len(rows) * args.runs):.0%}) |"
        ),
        f"| Names with the same answer every run | {stable}/{len(rows)} |",
        f"| Expected none, got an entry (any run) | {len(dangerous)} |",
        "",
        "| Name | Expected | Answers |",
        "|---|---|---|",
    ]
    for (v, _), got in zip(rows, per_name, strict=True):
        counts = ", ".join(f"{a} x{n}" for a, n in Counter(got).most_common())
        mark = "" if all(a == v["expect"] for a in got) else " ❌"
        lines.append(f"| {v['name_en']} | {v['expect']} | {counts}{mark} |")
    out = EVAL / "results/matcher.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
