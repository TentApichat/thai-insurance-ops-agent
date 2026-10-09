"""Score the agent on the labelled sample emails and compare extractors.

Usage:
    python eval/evaluate.py                        # rule-based baseline (and Gemini too if a key is set)
    python eval/evaluate.py --extractor gemini     # only Gemini
    python eval/evaluate.py --extractor rules      # only the offline baseline

Results are printed and saved to eval/results.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.graph import build_graph  # noqa: E402
from agent.llm import GeminiExtractor, RuleBasedExtractor, get_extractor  # noqa: E402
from agent.store import RequestStore  # noqa: E402

FIELDS = ["policy_number", "plate_number", "key_date", "contact_phone", "insured_name"]
METRICS = ["request_type", "route"] + FIELDS
LABELS = {
    "request_type": "Request type",
    "route": "Routing decision",
    "policy_number": "Policy number",
    "plate_number": "Licence plate",
    "key_date": "Key date",
    "contact_phone": "Contact phone",
    "insured_name": "Insured name",
}


def normalise(field: str, value):
    if value is None or value == "":
        return None
    value = str(value).strip()
    if field == "plate_number":
        return re.sub(r"\s+", "", value)
    if field == "contact_phone":
        return re.sub(r"\D", "", value)
    return value


def evaluate(extractor, samples: list[dict], today: str, delay: float) -> dict:
    hits = {metric: 0 for metric in METRICS}
    totals = {metric: 0 for metric in METRICS}
    mistakes: list[str] = []
    errors = 0

    with tempfile.TemporaryDirectory() as tmp:
        graph = build_graph(extractor, RequestStore(str(Path(tmp) / "eval.db")))
        for number, sample in enumerate(samples, start=1):
            expected = sample["expected"]
            try:
                result = graph.invoke({"text": sample["text"], "today": today})
            except Exception as error:  # one failed call should not stop the whole evaluation
                errors += 1
                result = None
                mistakes.append(f"#{sample['id']} error: {str(error)[:150]}")

            got = result["extraction"] if result else {}
            predicted = {"request_type": got.get("request_type"), "route": result["route"] if result else None}
            predicted.update({field: got.get(field) for field in FIELDS})

            for metric in METRICS:
                if metric not in expected:
                    continue
                totals[metric] += 1
                if normalise(metric, predicted[metric]) == normalise(metric, expected[metric]):
                    hits[metric] += 1
                elif result:
                    detail = f" {result['issues']}" if metric == "route" else ""
                    mistakes.append(
                        f"#{sample['id']} {metric}: expected {expected[metric]!r}, got {predicted[metric]!r}{detail}"
                    )

            if isinstance(extractor, GeminiExtractor):
                print(f"  {extractor.name}: {number}/{len(samples)}", end="\r", flush=True)
                time.sleep(delay)  # stay inside the free tier's requests-per-minute limit

    return {"name": extractor.name, "hits": hits, "totals": totals, "mistakes": mistakes, "errors": errors}


def score(run: dict, metric: str) -> str:
    total = run["totals"][metric]
    return f"{run['hits'][metric]}/{total} ({run['hits'][metric] / total:.0%})" if total else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(ROOT / "data" / "sample_requests.jsonl"))
    parser.add_argument("--today", default="2026-10-10", help="Fixed date so results are reproducible")
    parser.add_argument("--extractor", choices=["auto", "rules", "gemini"], default="auto")
    parser.add_argument("--delay", type=float, default=4.0, help="Seconds between Gemini calls")
    parser.add_argument("--out", default=str(ROOT / "eval" / "results.md"))
    args = parser.parse_args()

    samples = [json.loads(line) for line in Path(args.data).read_text(encoding="utf-8").splitlines() if line.strip()]

    extractors = []
    if args.extractor in ("auto", "rules"):
        extractors.append(RuleBasedExtractor())
    if args.extractor in ("auto", "gemini"):
        llm = get_extractor()
        if isinstance(llm, GeminiExtractor):
            extractors.append(llm)
        elif args.extractor == "gemini":
            sys.exit("No GEMINI_API_KEY found. Set it first, for example: export GEMINI_API_KEY=your-key")

    runs = []
    for extractor in extractors:
        print(f"Evaluating {extractor.name} on {len(samples)} emails...")
        runs.append(evaluate(extractor, samples, args.today, args.delay))
    print()

    header = "| Metric | " + " | ".join(run["name"] for run in runs) + " |"
    divider = "| --- | " + " | ".join("---" for _ in runs) + " |"
    rows = [f"| {LABELS[m]} | " + " | ".join(score(run, m) for run in runs) + " |" for m in METRICS]
    table = "\n".join([header, divider, *rows])
    print(table)

    report = [
        "# Evaluation results",
        "",
        f"{len(samples)} labelled emails, evaluation date {args.today}.",
        "",
        table,
        "",
    ]
    for run in runs:
        report.append(f"## Mistakes: {run['name']} ({len(run['mistakes'])}, errors: {run['errors']})")
        report.append("")
        if run["mistakes"]:
            report.extend(f"- {mistake}" for mistake in run["mistakes"])
        else:
            report.append("None.")
        report.append("")
    Path(args.out).write_text("\n".join(report), encoding="utf-8")
    print(f"\nFull results saved to {os.path.relpath(args.out)}")


if __name__ == "__main__":
    main()
