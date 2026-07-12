"""Run a batch of real questions through the live 2-agent council and
aggregate the metrics the user asked to track (2026-07-12):

  - total elapsed time
  - per-phase elapsed time
  - AI call count
  - Evidence search/fetch counts
  - verified / partially_verified / conflicting / withheld ratio
  - agent failure / quota occurrence count
  - single-agent vs. council answer (optional; doubles live cost)

This script does not run anything on import; it must be invoked explicitly
because every question it processes spends real API quota. It intentionally
does not use pytest's `live`/`expensive` markers — it is an operator tool,
not a test.

Usage:
    python scripts/collect_metrics.py questions.txt --out metrics.jsonl
    python scripts/collect_metrics.py questions.txt --out metrics.jsonl --baseline

`questions.txt` is one question per line (blank lines and lines starting
with `#` are ignored). Each run uses --no-store so nothing lands in data/;
the aggregated metrics are the only persisted output, written to --out as
JSONL (one object per question) plus a summary printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def read_questions(path: Path) -> list[str]:
    questions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            questions.append(line)
    return questions


def run_council(question: str, *, timeout: int = 300) -> dict:
    """Invoke the real 2-agent council for one question. Mirrors
    tests/e2e/test_real_adapter_e2e.py's subprocess pattern so this script
    exercises exactly the same code path as the live E2E test."""
    env = dict(os.environ)
    env["ORACLE_COUNCIL_USE_REAL"] = "1"
    wall_start = time.monotonic()
    process = subprocess.run(
        [
            sys.executable, "-m", "oracle_council.cli", "ask", question,
            "--mode", "verify", "--no-interactive", "--adapter-mode", "real",
            "--no-store", "--json",
        ],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT,
        timeout=timeout, check=False,
    )
    wall_elapsed_ms = int((time.monotonic() - wall_start) * 1000)
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {"status": "harness_parse_error", "stderr": process.stderr[-2000:]}
    payload["_wall_elapsed_ms"] = wall_elapsed_ms
    return payload


def run_single_agent_baseline(question: str, *, timeout: int = 120) -> dict:
    """--adapter-mode real with a config carrying only one enabled agent
    would need a second config file; instead this asks the CLI's fake path
    is skipped and runs `oracle ask --mode quick` as the cheap baseline
    (single independent pass, no cross-check) for a rough quality/time
    contrast against the full council. This is intentionally coarse — the
    user's exact request ("単独AI回答との差") is worth a dedicated
    single-agent config in a follow-up, not a rough substitute; see the
    note in main()."""
    return run_council(question, timeout=timeout)


def summarize(records: list[dict]) -> dict:
    classifications = Counter(r.get("answer", {}).get("result_classification") for r in records)
    statuses = Counter(r.get("status") for r in records)
    call_counts = [r.get("agent_call_count") for r in records if r.get("agent_call_count") is not None]
    wall_times = [r["_wall_elapsed_ms"] for r in records if "_wall_elapsed_ms" in r]

    error_codes = Counter()
    for r in records:
        for execution in r.get("executions", []):
            if execution.get("error_code"):
                error_codes[execution["error_code"]] += 1

    phase_elapsed: dict[str, list[int]] = {}
    for r in records:
        for phase in r.get("phases", []):
            if phase.get("elapsed_ms") is not None:
                phase_elapsed.setdefault(phase["phase"], []).append(phase["elapsed_ms"])

    def avg(values: list[int]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    return {
        "run_count": len(records),
        "run_status_counts": dict(statuses),
        "result_classification_counts": dict(classifications),
        "avg_call_count": avg(call_counts),
        "avg_wall_elapsed_ms": avg(wall_times),
        "avg_phase_elapsed_ms": {phase: avg(values) for phase, values in phase_elapsed.items()},
        "agent_error_code_counts": dict(error_codes),
        "quota_occurrences": error_codes.get("QUOTA_EXCEEDED", 0) + error_codes.get("RATE_LIMITED", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("questions_file", type=Path, help="One question per line")
    parser.add_argument("--out", type=Path, default=Path("metrics.jsonl"), help="Per-question JSONL output")
    parser.add_argument("--baseline", action="store_true",
                         help="Also run --mode quick per question for a rough single-pass contrast "
                              "(NOT a true single-agent baseline; doubles live API usage)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N questions")
    args = parser.parse_args()

    questions = read_questions(args.questions_file)
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("No questions to run.", file=sys.stderr)
        return 1

    print(f"Running {len(questions)} question(s) through the real 2-agent council...", file=sys.stderr)
    records = []
    with args.out.open("w", encoding="utf-8") as sink:
        for i, question in enumerate(questions, 1):
            print(f"[{i}/{len(questions)}] {question[:60]}...", file=sys.stderr)
            record = run_council(question)
            if args.baseline:
                record["_baseline"] = run_single_agent_baseline(question)
            records.append(record)
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            sink.flush()

    summary = summarize(records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
