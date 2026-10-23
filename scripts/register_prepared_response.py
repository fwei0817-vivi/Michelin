"""Register an explicitly authored text-to-Menu response, without calling any model.

An existing destination is never overwritten. Keep one JSON record per input/response pair
in data/prepared. The response must use Menu schema and the same restaurant ID as --menu-id.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from michelin.model import ExtractionRequest, extract


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--menu-id", required=True)
    parser.add_argument("--input", type=Path, required=True, help="Exact UTF-8 input text")
    parser.add_argument("--response", type=Path, required=True, help="Assistant-authored Menu JSON")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New data/prepared/*.json path")
    args = parser.parse_args()
    request = ExtractionRequest(menu_id=args.menu_id, text=args.input.read_text())
    record = {
        "menu_id": args.menu_id,
        "input_kind": "text",
        "input_text": request.text,
        "input_sha256": request.input_hash(),
        "source_url": args.source_url,
        "retrieved_at": args.retrieved_at.isoformat(),
        "preparation": "Explicitly registered prepared response; no model or OCR was run.",
        "menu": json.loads(args.response.read_text()),
    }

    class AuthoredProvider:
        name = "assistant-prepared"
        mode = "prepared_replay"

        def extract(self, request):
            return record

    record["menu"] = extract(request, AuthoredProvider()).menu.model_dump(mode="json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as target:
        target.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(f"Prepared response registered at {args.output}; no external call made.")


if __name__ == "__main__":
    main()
