"""Score the agent on the labelled sample requests.

Usage:
    python eval/evaluate.py                 # offline rule-based baseline
    GEMINI_API_KEY=... python eval/evaluate.py   # the LLM
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.graph import build_graph  # noqa: E402
from agent.llm import get_extractor  # noqa: E402
from agent.store import RequestStore  # noqa: E402

FIELDS = ["policy_number", "plate_number", "key_date", "contact_phone", "insured_name"]


def normalise(field: str, value):
    if value is None or value == "":
        return None
    value = str(value).strip()
    if field == "plate_number":
        return re.sub(r"\s+", "", value)
    if field == "contact_phone":
        return re.sub(r"\D", "", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(ROOT / "data" / "sample_requests.jsonl"))
    parser.add_argument("--today", default="2026-10-10", help="Fixed date so results are reproducible")
    args = parser.parse_args()

    samples = [json.loads(line) for line in Path(args.data).read_text(encoding="utf-8").splitlines() if line.strip()]
    extractor = get_extractor()
    with tempfile.TemporaryDirectory() as tmp:
        graph = build_graph(extractor, RequestStore(str(Path(tmp) / "eval.db")))

        type_hits = route_hits = 0
        field_hits = {field: 0 for field in FIELDS}
        field_totals = {field: 0 for field in FIELDS}
        mistakes = []

        for sample in samples:
            result = graph.invoke({"text": sample["text"], "today": args.today})
            expected, got = sample["expected"], result["extraction"]

            if got["request_type"] == expected["request_type"]:
                type_hits += 1
            else:
                mistakes.append(f"#{sample['id']} type: expected {expected['request_type']}, got {got['request_type']}")

            if result["route"] == expected["route"]:
                route_hits += 1
            else:
                mistakes.append(f"#{sample['id']} route: expected {expected['route']}, got {result['route']} {result['issues']}")

            for field in FIELDS:
                if field not in expected:
                    continue
                field_totals[field] += 1
                if normalise(field, got.get(field)) == normalise(field, expected[field]):
                    field_hits[field] += 1
                else:
                    mistakes.append(f"#{sample['id']} {field}: expected {expected[field]!r}, got {got.get(field)!r}")

    n = len(samples)
    reviewed = sum(1 for s in samples if s["expected"]["route"] == "human_review")
    print(f"Extractor: {extractor.name}   Samples: {n}   Expected human reviews: {reviewed}\n")
    print(f"{'Metric':<22}{'Score':>10}")
    print(f"{'Request type':<22}{type_hits:>4}/{n:<3} {type_hits / n:>4.0%}")
    print(f"{'Routing decision':<22}{route_hits:>4}/{n:<3} {route_hits / n:>4.0%}")
    for field in FIELDS:
        total = field_totals[field]
        if total:
            print(f"{field:<22}{field_hits[field]:>4}/{total:<3} {field_hits[field] / total:>4.0%}")
    if mistakes:
        print("\nMistakes:")
        for mistake in mistakes:
            print(f"  {mistake}")


if __name__ == "__main__":
    main()
