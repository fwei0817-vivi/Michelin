"""Repeatable offline regression metrics, not extraction-accuracy or live-model comparison."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


class Results:
    def __init__(self):
        self.cases = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.failed):
            self.cases.append({"case": report.nodeid, "outcome": report.outcome})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/michelin-offline-evaluation.json")
    )
    args = parser.parse_args()
    results = Results()
    root = Path(__file__).resolve().parents[1]
    exit_code = pytest.main(
        [
            "-q",
            str(root / "tests/test_replay.py"),
            str(root / "tests/test_backend_validation.py"),
            str(root / "tests/test_profiles.py"),
        ],
        plugins=[results],
    )
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "mode": "offline_prepared_response_regression",
        "live_model_comparison": "NOT RUN",
        "image_ocr_evaluation": "NOT RUN",
        "extraction_accuracy": "NOT MEASURED",
        "total": len(results.cases),
        "passed": sum(c["outcome"] == "passed" for c in results.cases),
        "cases": results.cases,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Offline regression report: {args.output}")
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
