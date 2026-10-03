"""Run the bad-case scenarios and score the answers against ground truth.

    uv run python eval/run_eval.py                      # our planner, labels from the menu text
    uv run python eval/run_eval.py --labels kb          # our planner, knowledge-base labels
    uv run python eval/run_eval.py --labels oracle      # our planner, perfect labels
    uv run python eval/run_eval.py --answers eval/baselines/chatgpt_run1.json --name chatgpt

The planner runs in-process through the FastAPI app (no server needed), so whatever branch is
checked out is what gets measured. Results go to eval/results/<name>.json and .md.

Whether a safe order exists (for the over-refusal check) is decided by running the same
planner on `reference` labels (truth, definite/likely only). Its plan is re-scored
independently; a reference plan that fails safety or budget is reported as inconclusive.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from labels import build_menu, load_eval_menu, printed_dish
from truth import Answer, LabelFinding, Score, score, score_labels

EVAL = Path(__file__).resolve().parent
TRAPS = [
    "explicit",
    "hidden",
    "name_inference",
    "ambiguous",
    "compound_sauce",
    "false_alarm",
    "negative_control",
]


def load_scenarios(only: list[str] | None) -> list[dict]:
    out = []
    for path in sorted((EVAL / "scenarios").glob("*.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        if not only or s["id"] in only:
            out.append(s)
    return out


def ask_planner(client, scenario: dict, labels: str) -> Answer:
    menu = build_menu(scenario["menu"], labels, scenario.get("dish_subset"))
    body = {
        "menu_id": menu["restaurant_id"],
        "menu_override": menu,
        "diners": scenario["diners"],
        "budget_per_person": scenario["budget_per_person"],
        "tax_rate": scenario.get("tax_rate", 0.08875),
        "tip_rate": scenario.get("tip_rate", 0.18),
        "min_dishes_per_person": scenario.get("min_dishes_per_person", 2),
        "locked_dish_ids": scenario.get("locked_dish_ids", []),
        "excluded_dish_ids": scenario.get("excluded_dish_ids", []),
    }
    ev = client.post("/api/menu/evaluate", json={"menu": menu, "diners": scenario["diners"]})
    eligibility = (
        {dish_id: r["edible_by"] for dish_id, r in ev.json().items()}
        if ev.status_code == 200
        else None
    )
    resp = client.post("/api/plan", json=body)
    if resp.status_code != 200:
        return Answer(kind="error", detail=f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data["kind"] == "conflict":
        return Answer(kind="conflict", detail=data["conflict"]["message"], eligibility=eligibility)
    plan = data["plan"]
    return Answer(
        kind="plan",
        items=[
            {"dish_id": i["dish_id"], "quantity": i["quantity"], "edible_by": i["edible_by"]}
            for i in plan["items"]
        ],
        reported_total=plan["total"],
        staff_questions=plan.get("confirm_with_staff", []),
        eligibility=eligibility,
    )


def safe_order_exists(client, scenario: dict, dishes: dict) -> bool | None:
    ref = ask_planner(client, scenario, "reference")
    if ref.kind == "conflict":
        return False
    if ref.kind == "plan":
        checked = score({**scenario, "expect": "any"}, dishes, ref)
        return True if checked.passed else None
    return None


def load_answers(path: Path) -> dict[str, Answer]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        sid: Answer(
            kind=a["kind"],
            items=a.get("items", []),
            reported_total=a.get("reported_total"),
            staff_questions=a.get("staff_questions", []),
            detail=a.get("detail", ""),
        )
        for sid, a in raw.items()
    }


def _pairs(findings) -> dict[tuple[str, str], list[str]]:
    """Distinct diner x dish pairs with the union of their trap types; one dish can conflict
    with a diner through several components."""
    out: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        traps = out.setdefault((f.diner, f.dish), [])
        traps += [t for t in f.traps if t not in traps]
    return out


def _count(scores: list[Score], attr: str) -> int:
    return sum(len(_pairs(getattr(s, attr))) for s in scores)


def _yn(flag: bool | None, good: str = "ok", bad: str = "off") -> str:
    return "" if flag is None else (good if flag else bad)


def in_knowledge_base(menu_name: str) -> dict[str, bool]:
    """Whether each eval dish is matched by the knowledge base. Holdouts must not be."""
    from michelin.parse.knowledge import match
    from michelin.schemas import Dish

    out = {}
    for dish_id, dish in load_eval_menu(menu_name).items():
        out[dish_id] = match(Dish.model_validate(printed_dish(dish))) is not None
        if dish.get("holdout") and out[dish_id]:
            raise SystemExit(f"holdout dish {dish_id} leaked into the knowledge base")
    return out


def label_findings(labels: str) -> tuple[list[LabelFinding], dict[str, bool]]:
    findings, known = [], {}
    for menu_name in ("trap", "sample_sichuan"):
        dishes = load_eval_menu(menu_name)
        built = {d["id"]: d for d in build_menu(menu_name, labels)["dishes"]}
        kb = in_knowledge_base(menu_name)
        for f in score_labels(dishes, built):
            f.dish = f"{menu_name}:{f.dish}"
            findings.append(f)
        known |= {f"{menu_name}:{k}": v for k, v in kb.items()}
    return findings, known


def label_report(findings: list[LabelFinding], known: dict[str, bool]) -> list[str]:
    kinds = ["correct", "missed", "weakened", "unflagged", "stricter"]
    lines = [
        "",
        "## Label accuracy",
        "",
        "Every dish x restriction (9 allergens, 4 diets) on both eval menus: does the label say",
        "block / ask staff / clear, as the reference does? **missed** = reference blocks, label",
        "clears (dangerous). **weakened** = reference blocks, label only asks. **unflagged** =",
        "reference asks, label clears. **stricter** = label more cautious than the reference.",
        "",
        "| Dishes | " + " | ".join(kinds) + " | accuracy |",
        "|---|" + "---|" * (len(kinds) + 1),
    ]
    groups = {
        "in knowledge base": [f for f in findings if known[f.dish]],
        "not in knowledge base (holdout)": [f for f in findings if not known[f.dish]],
        "all": findings,
    }
    for name, group in groups.items():
        c = Counter(f.kind for f in group)
        acc = f"{c['correct'] / len(group):.0%}" if group else ""
        lines.append(f"| {name} | " + " | ".join(str(c[k]) for k in kinds) + f" | {acc} |")
    bad = [f for f in findings if f.kind in ("missed", "weakened")]
    by_trap = Counter(f.trap for f in bad)
    if bad:
        lines += [
            "",
            "Missed or weakened, by trap: "
            + ", ".join(f"{t or 'n/a'} {n}" for t, n in by_trap.most_common()),
            "",
        ]
        lines += [
            f"- {f.kind}: {f.dish} / {f.restriction} (reference {f.truth}, label "
            f"{f.system}, {f.trap})"
            for f in bad
        ]
    return lines


def report(name: str, scores: list[Score], label_lines: list[str] | None = None) -> str:
    n = len(scores)
    has_menu_level = any(s.unsafe_eligible or s.over_blocked or s.cautious_blocked for s in scores)
    lines = [
        f"# Bad-case eval: {name}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Scenarios passed (safety + money) | **{sum(s.passed for s in scores)}/{n}** |",
        f"| Scenarios with a severe violation | {sum(bool(s.severe) for s in scores)} |",
        f"| Severe violations (diner x dish) | {_count(scores, 'severe')} |",
        f"| Unflagged possible risks | {_count(scores, 'unflagged')} |",
        f"| Over budget | {sum(s.over_budget for s in scores)} |",
        f"| Wrong arithmetic | {sum(s.math_error is not None for s in scores)} |",
        f'| False "no order works" | {sum(bool(s.false_conflict) for s in scores)} |',
    ]
    if has_menu_level:
        lines += [
            f"| Menu level: unsafe dishes allowed | {_count(scores, 'unsafe_eligible')} |",
            f"| Menu level: safe dishes refused | {_count(scores, 'over_blocked')} |",
            (
                "| Menu level: possible-only dishes refused | "
                f"{_count(scores, 'cautious_blocked')} |"
            ),
        ]

    severe_by, allowed_by, refused_by = Counter(), Counter(), Counter()
    for s in scores:
        for traps in _pairs(s.severe).values():
            severe_by.update(traps)
        for traps in _pairs(s.unsafe_eligible).values():
            allowed_by.update(traps)
        for traps in _pairs(s.over_blocked).values():
            refused_by.update(traps)
    lines += [
        "",
        "## By trap type",
        "",
        "Counts are diner x dish pairs; a pair counts under every trap type among its conflicts.",
        "",
        "| Trap | Severe in plan | Unsafe allowed (menu) | Safe refused (menu) |",
        "|---|---|---|---|",
    ]
    for t in TRAPS:
        lines.append(f"| {t} | {severe_by[t]} | {allowed_by[t]} | {refused_by[t]} |")

    lines += [
        "",
        "## Scenarios",
        "",
        (
            "| Scenario | Category | Result | Expected | Pass | Usable | Severe | False coverage "
            "| Unflagged | Total / limit | Portions |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        money = f"{s.total} / {s.budget_limit}" if s.total else ""
        lines.append(
            f"| {s.scenario} | {s.category} | {s.kind} | {s.expected} | "
            f"{'✅' if s.passed else '❌'} | {_yn(s.usable, '✅', '❌ refused')} | "
            f"{len(s.severe)} | {len(s.false_coverage)} | {len(s.unflagged)} | "
            f"{money}{' ⚠️' if s.over_budget else ''} | {_yn(s.portions_ok)} |"
        )

    lines += label_lines or []
    lines += ["", "## Details", ""]
    for s in scores:
        problems = (
            [f"severe: {f}" for f in s.severe]
            + [f"false coverage: {m}" for m in s.false_coverage]
            + [f"lock/exclude: {m}" for m in s.lock_violations]
            + ([f"math: {s.math_error}"] if s.math_error else [])
            + ([f"outcome {s.kind}, expected {s.expected}"] if not s.outcome_ok else [])
            + (["refused although a safe order exists"] if s.false_conflict else [])
            + [f"unflagged: {f}" for f in s.unflagged]
            + [f"menu: unsafe allowed: {f}" for f in s.unsafe_eligible]
            + [f"menu: safe refused: {f}" for f in s.over_blocked]
            + [f"menu: possible-only refused: {f}" for f in s.cautious_blocked]
            + ([f"detail: {s.detail}"] if s.detail and s.kind != "plan" else [])
        )
        if problems:
            lines.append(f"**{s.scenario}**")
            lines += [f"- {p}" for p in problems]
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", choices=["current", "kb", "oracle"], default="current")
    ap.add_argument("--answers", type=Path, help="score a saved baseline instead of the planner")
    ap.add_argument("--name", help="output name (default: planner-<labels>)")
    ap.add_argument("--only", nargs="*", help="scenario ids")
    args = ap.parse_args()

    from fastapi.testclient import TestClient

    from michelin.api import app

    client = TestClient(app)
    scenarios = load_scenarios(args.only)
    name = args.name or (args.answers.stem if args.answers else f"planner-{args.labels}")
    answers = load_answers(args.answers) if args.answers else None

    scores = []
    for s in scenarios:
        dishes = load_eval_menu(s["menu"])
        if answers is not None:
            answer = answers.get(s["id"], Answer(kind="error", detail="no answer recorded"))
        else:
            answer = ask_planner(client, s, args.labels)
        feasible = safe_order_exists(client, s, dishes) if answer.kind == "conflict" else None
        result = score(s, dishes, answer, feasible)
        scores.append(result)
        flag = "" if result.usable else "  (refused a feasible table)"
        print(
            f"{s['id']:4} {'PASS' if result.passed else 'FAIL'}  {result.kind:8} {s['title']}{flag}"
        )

    out = EVAL / "results"
    out.mkdir(exist_ok=True)
    (out / f"{name}.json").write_text(
        json.dumps(
            [asdict(s) | {"passed": s.passed, "usable": s.usable} for s in scores],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    label_lines = None
    if answers is None:
        findings, known = label_findings(args.labels)
        label_lines = label_report(findings, known)
    (out / f"{name}.md").write_text(report(name, scores, label_lines), encoding="utf-8")
    print(f"\nWrote {out / (name + '.md')}")


if __name__ == "__main__":
    main()
