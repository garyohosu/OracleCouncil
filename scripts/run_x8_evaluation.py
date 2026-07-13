from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oracle_council.models import safe_error_summary


RUNNER_VERSION = "x8-runner-v1"
FORBIDDEN_JSON_KEYS = {
    "content", "body", "raw_content", "prompt", "stdout", "stderr",
    "environment", "headers", "cookies", "tokens", "diagnostics", "notes",
}
SYSTEMIC_STATUSES = {"internal_error", "configuration_error", "verification_unavailable"}
SUMMARY_FIELDS = [
    "question_id", "category", "exit_code", "status", "classification", "run_id",
    "elapsed_ms", "evidence_collect_elapsed_ms", "evidence_count", "search_count",
    "candidate_count", "fetch_attempt_count", "fetch_success_count", "fetch_failure_count",
    "outcome", "retry_count", "error_codes", "json_valid", "leakage_check",
    "acceptance_status",
]
REQUIRED_QUESTION_FIELDS = {
    "id", "category", "question", "expected_behavior", "acceptance_checks",
    "allowed_classifications", "max_external_runs",
}


class EvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitState:
    repo_root: Path
    head: str
    origin_main: str
    worktree_clean: bool = True
    origin_matches: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(args: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise EvaluationError(f"git {' '.join(args)} failed")
    return result.stdout.strip()


def inspect_git(cwd: Path, *, allow_dirty: bool = False) -> GitState:
    repo_root = Path(run_git(["rev-parse", "--show-toplevel"], cwd=cwd)).resolve()
    dirty = bool(run_git(["status", "--short"], cwd=repo_root))
    if dirty and not allow_dirty:
        raise EvaluationError("git worktree is not clean")
    head = run_git(["rev-parse", "--short", "HEAD"], cwd=repo_root)
    origin_main = run_git(["rev-parse", "--short", "refs/remotes/origin/main"], cwd=repo_root)
    return GitState(
        repo_root=repo_root,
        head=head,
        origin_main=origin_main,
        worktree_clean=not dirty,
        origin_matches=head == origin_main,
    )


def is_relative_to(child: Path, parent: Path) -> bool:
    child_s = os.path.normcase(str(child.resolve()))
    parent_s = os.path.normcase(str(parent.resolve()))
    try:
        return os.path.commonpath([child_s, parent_s]) == parent_s
    except ValueError:
        return False


def ensure_safe_environment(
    cwd: Path,
    output_dir: Path,
    expected_head: str,
    *,
    allow_dirty: bool = False,
    allow_origin_mismatch: bool = False,
) -> GitState:
    state = inspect_git(cwd, allow_dirty=allow_dirty)
    if state.head != expected_head:
        raise EvaluationError(f"HEAD mismatch: expected {expected_head}, actual {state.head}")
    if state.origin_main != state.head and not allow_origin_mismatch:
        raise EvaluationError(f"origin/main mismatch: HEAD {state.head}, origin/main {state.origin_main}")
    if is_relative_to(output_dir, state.repo_root):
        raise EvaluationError("output directory must be outside the repository")
    return state


def load_eval_set(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions")
    if not isinstance(data.get("evaluation_version"), str) or not data["evaluation_version"]:
        raise EvaluationError("eval set must contain evaluation_version")
    if not isinstance(questions, list) or not questions:
        raise EvaluationError("eval set must contain a non-empty questions list")
    seen: set[str] = set()
    for question in questions:
        missing = REQUIRED_QUESTION_FIELDS - set(question)
        if missing:
            raise EvaluationError(f"question is missing fields: {sorted(missing)}")
        qid = question.get("id")
        if not isinstance(qid, str) or not qid:
            raise EvaluationError("each question must have an id")
        if qid in seen:
            raise EvaluationError(f"duplicate question id: {qid}")
        seen.add(qid)
        if not isinstance(question.get("question"), str) or not question["question"].strip():
            raise EvaluationError(f"{qid}: question must be non-empty")
        if question.get("max_external_runs") != 1:
            raise EvaluationError(f"{qid}: max_external_runs must be 1")
        if not isinstance(question.get("acceptance_checks"), list):
            raise EvaluationError(f"{qid}: acceptance_checks must be a list")
        if not isinstance(question.get("allowed_classifications"), list):
            raise EvaluationError(f"{qid}: allowed_classifications must be a list")
    return data


def select_questions(eval_set: dict[str, Any], question_id: str | None, run_all: bool) -> list[dict[str, Any]]:
    if run_all:
        return list(eval_set["questions"])
    for question in eval_set["questions"]:
        if question["id"] == question_id:
            return [question]
    raise EvaluationError(f"unknown question id: {question_id}")


def command_for(question: str) -> list[str]:
    return [
        "py", "-m", "oracle_council.cli", "ask", question,
        "--adapter-mode", "real", "--evidence-provider", "cli-search", "--json", "--no-store",
    ]


def command_template() -> list[str]:
    return command_for("<question>")


def atomic_write_json(path: Path, payload: dict[str, Any], *, fail_if_exists: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if fail_if_exists:
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise EvaluationError(f"{path.name} already exists")
        finally:
            tmp.unlink(missing_ok=True)
    else:
        os.replace(tmp, path)


def build_manifest(eval_set_path: Path, eval_set: dict[str, Any], eval_hash: str,
                   questions: list[dict[str, Any]], expected_head: str,
                   actual_head: str, output_dir: Path) -> dict[str, Any]:
    return {
        "evaluation_version": eval_set["evaluation_version"],
        "eval_set_path": str(eval_set_path),
        "eval_set_sha256": eval_hash,
        "question_ids": [q["id"] for q in questions],
        "question_count": len(questions),
        "expected_head": expected_head,
        "actual_head": actual_head,
        "runner_version": RUNNER_VERSION,
        "started_at": utc_now_iso(),
        "command_template": command_template(),
        "max_external_runs_per_question": 1,
        "output_dir": str(output_dir.resolve()),
        "one_run_policy": "attempted.json is written before each external run and is never removed",
        "status": "started",
    }


def ensure_manifest(path: Path, expected: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key in ("eval_set_sha256", "expected_head", "actual_head", "question_ids"):
            if current.get(key) != expected.get(key):
                raise EvaluationError(f"manifest mismatch: {key}")
        return
    atomic_write_json(path, expected, fail_if_exists=True)


def read_stdout_json(path: Path) -> tuple[str, dict[str, Any] | None]:
    try:
        text = path.read_text(encoding="utf-8")
        return "valid", json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return "invalid", None


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def find_phase(payload: dict[str, Any] | None, phase_name: str) -> dict[str, Any]:
    for phase in safe_list(payload.get("phases") if payload else None):
        if isinstance(phase, dict) and phase.get("phase") == phase_name:
            return phase
    return {}


def count_retries(payload: dict[str, Any] | None) -> int:
    return sum(1 for item in safe_list(payload.get("executions") if payload else None)
               if isinstance(item, dict) and item.get("retry_of"))


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in FORBIDDEN_JSON_KEYS or contains_forbidden_key(child) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_forbidden_key(item) for item in value)
    return False


def leakage_check(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "json_invalid"
    return "failed_structural_check" if contains_forbidden_key(payload) else "passed_structural_check"


def phase_summary(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for phase in safe_list(payload.get("phases") if payload else None):
        if isinstance(phase, dict):
            rows.append({
                "phase": phase.get("phase"),
                "status": phase.get("status"),
                "success_count": phase.get("success_count"),
                "elapsed_ms": phase.get("elapsed_ms"),
                "error_code": phase.get("error_code"),
                "error_summary": safe_error_summary(phase.get("error_summary")),
                "outcome": phase.get("outcome"),
            })
    return rows


def build_record(eval_version: str, eval_hash: str, question: dict[str, Any],
                 expected_head: str, actual_head: str, attempted_at: str,
                 started_at: str | None, finished_at: str | None, command: list[str],
                 exit_code: int | None, timed_out: bool, stdout_file: Path, stderr_file: Path,
                 json_status: str, payload: dict[str, Any] | None,
                 runner_error_code: str | None = None) -> dict[str, Any]:
    evidence_phase = find_phase(payload, "evidence_collect")
    evidence_metrics = evidence_phase.get("metrics") if isinstance(evidence_phase.get("metrics"), dict) else {}
    metadata = payload.get("metadata") if payload and isinstance(payload.get("metadata"), dict) else {}
    answer = payload.get("answer") if payload and isinstance(payload.get("answer"), dict) else {}
    status = "timeout" if timed_out else (payload.get("status") if payload else None)
    if runner_error_code and status is None:
        status = "runner_error"
    duration_ms = None
    if attempted_at and finished_at:
        try:
            duration_ms = int((datetime.fromisoformat(finished_at) - datetime.fromisoformat(attempted_at)).total_seconds() * 1000)
        except ValueError:
            duration_ms = None
    return {
        "evaluation_version": eval_version,
        "eval_set_sha256": eval_hash,
        "question_id": question["id"],
        "category": question["category"],
        "question": question["question"],
        "expected_head": expected_head,
        "actual_head": actual_head,
        "attempted_at": attempted_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "command": command,
        "external_run_count": 1,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_file": str(stdout_file),
        "stderr_file": str(stderr_file),
        "json_parse_status": json_status,
        "run_id": payload.get("run_id") if payload else None,
        "status": status,
        "result_classification": answer.get("result_classification"),
        "participants": payload.get("participants") if payload else [],
        "agent_call_count": payload.get("agent_call_count") if payload else None,
        "phase_summary": phase_summary(payload),
        "evidence_metrics": evidence_metrics,
        "evidence_count": metadata.get("evidence_count"),
        "error_codes": metadata.get("error_codes", []),
        "leakage_check": leakage_check(payload),
        "runner_error_code": runner_error_code,
        "acceptance_status": "not_assessed",
    }


def csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def summary_row(record: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    evidence_phase = find_phase(payload, "evidence_collect")
    metrics = evidence_phase.get("metrics") if isinstance(evidence_phase.get("metrics"), dict) else {}
    metadata = payload.get("metadata") if payload and isinstance(payload.get("metadata"), dict) else {}
    row = {
        "question_id": record["question_id"],
        "category": record["category"],
        "exit_code": record["exit_code"],
        "status": record["status"],
        "classification": record["result_classification"],
        "run_id": record["run_id"],
        "elapsed_ms": metadata.get("elapsed_ms"),
        "evidence_collect_elapsed_ms": evidence_phase.get("elapsed_ms"),
        "evidence_count": record["evidence_count"],
        "search_count": metrics.get("search_count"),
        "candidate_count": metrics.get("candidate_count"),
        "fetch_attempt_count": metrics.get("fetch_attempt_count"),
        "fetch_success_count": metrics.get("fetch_success_count"),
        "fetch_failure_count": metrics.get("fetch_failure_count"),
        "outcome": evidence_phase.get("outcome"),
        "retry_count": count_retries(payload),
        "error_codes": ",".join(str(item) for item in record.get("error_codes", [])),
        "json_valid": record["json_parse_status"] == "valid",
        "leakage_check": record["leakage_check"],
        "acceptance_status": record["acceptance_status"],
    }
    return row


def write_summary(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "summary.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    with (output_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe(row.get(key)) for key in SUMMARY_FIELDS})


def rebuild_summary(output_dir: Path, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    by_id = {q["id"]: q for q in questions}
    for qid in [q["id"] for q in questions]:
        qdir = output_dir / qid
        record_path = qdir / "record.json"
        if not record_path.exists():
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        json_status, payload = read_stdout_json(Path(record["stdout_file"]))
        rows.append(summary_row(record, payload if json_status == "valid" else None))
    write_summary(output_dir, rows)
    return rows


def recover_records(output_dir: Path, eval_set: dict[str, Any], eval_hash: str,
                    expected_head: str, actual_head: str) -> None:
    for question in eval_set["questions"]:
        qdir = output_dir / question["id"]
        attempted_path = qdir / "attempted.json"
        record_path = qdir / "record.json"
        if not attempted_path.exists() or record_path.exists():
            continue
        try:
            attempted = json.loads(attempted_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            attempted = {}
        stdout_file = qdir / "stdout.json"
        stderr_file = qdir / "stderr.txt"
        json_status, payload = read_stdout_json(stdout_file) if stdout_file.exists() else ("missing", None)
        record = build_record(
            eval_set["evaluation_version"], eval_hash, question, expected_head, actual_head,
            attempted.get("attempted_at", utc_now_iso()), attempted.get("started_at"),
            utc_now_iso(), attempted.get("command", command_for(question["question"])),
            None, False, stdout_file, stderr_file, json_status, payload,
            runner_error_code=None if stdout_file.exists() else "INDETERMINATE_ATTEMPT",
        )
        if record["status"] is None:
            record["status"] = "indeterminate"
        atomic_write_json(record_path, record)


def should_stop_all(record: dict[str, Any]) -> bool:
    if record.get("runner_error_code") in {"SUBPROCESS_START_FAILED"}:
        return True
    if record.get("timed_out"):
        return True
    if record.get("json_parse_status") != "valid":
        return True
    if record.get("status") in SYSTEMIC_STATUSES:
        return True
    if record.get("run_id") is None:
        return True
    return False


def run_one(eval_version: str, eval_hash: str, question: dict[str, Any],
            output_dir: Path, expected_head: str, actual_head: str,
            repo_root: Path, timeout_seconds: int) -> tuple[int, bool]:
    qdir = output_dir / question["id"]
    attempted_path = qdir / "attempted.json"
    if attempted_path.exists():
        raise EvaluationError(f"{question['id']} already has attempted record")
    stdout_path = qdir / "stdout.json"
    stderr_path = qdir / "stderr.txt"
    record_path = qdir / "record.json"
    command = command_for(question["question"])
    attempted_at = utc_now_iso()
    attempted = {
        "evaluation_version": eval_version,
        "eval_set_sha256": eval_hash,
        "question_id": question["id"],
        "expected_head": expected_head,
        "actual_head": actual_head,
        "attempted_at": attempted_at,
        "command": command,
    }
    atomic_write_json(attempted_path, attempted, fail_if_exists=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    started_at = utc_now_iso()
    exit_code: int | None = None
    timed_out = False
    runner_error_code: str | None = None
    qdir.mkdir(parents=True, exist_ok=True)
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            result = subprocess.run(
                command, cwd=str(repo_root), stdout=stdout, stderr=stderr, env=env,
                check=False, shell=False, timeout=timeout_seconds,
            )
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        runner_error_code = "TIMEOUT"
    except OSError:
        runner_error_code = "SUBPROCESS_START_FAILED"
    finished_at = utc_now_iso()
    json_status, payload = read_stdout_json(stdout_path) if stdout_path.exists() else ("missing", None)
    record = build_record(
        eval_version, eval_hash, question, expected_head, actual_head, attempted_at,
        started_at, finished_at, command, exit_code, timed_out, stdout_path, stderr_path,
        json_status, payload, runner_error_code,
    )
    atomic_write_json(record_path, record)
    return (exit_code if exit_code is not None else 2), should_stop_all(record)


def dry_run(eval_set: dict[str, Any], eval_hash: str, questions: list[dict[str, Any]],
            output_dir: Path, state: GitState) -> int:
    print(f"evaluation_version={eval_set['evaluation_version']}")
    print(f"eval_set_sha256={eval_hash}")
    print(f"repo_root={state.repo_root}")
    print(f"head={state.head}")
    print(f"origin_main={state.origin_main}")
    print(f"origin_matches={str(state.origin_matches).lower()}")
    print(f"worktree_clean={str(state.worktree_clean).lower()}")
    print("dry_run_would_reject_dirty=true")
    print("dry_run_would_reject_origin_mismatch=true")
    print(f"output_dir={output_dir.resolve()}")
    for question in questions:
        print(f"{question['id']} {question['category']}: {question['question']}")
        print("  " + json.dumps(command_for(question["question"]), ensure_ascii=False))
    return 0


def run(args: argparse.Namespace) -> int:
    if args.timeout_seconds <= 0:
        raise EvaluationError("--timeout-seconds must be a positive integer")
    cwd = Path.cwd()
    eval_set_path = Path(args.eval_set)
    eval_hash = sha256_file(eval_set_path)
    eval_set = load_eval_set(eval_set_path)
    questions = select_questions(eval_set, args.question_id, args.all)
    output_dir = Path(args.output_dir)
    state = ensure_safe_environment(
        cwd,
        output_dir,
        args.expected_head,
        allow_dirty=args.dry_run,
        allow_origin_mismatch=args.dry_run,
    )
    if args.dry_run:
        return dry_run(eval_set, eval_hash, questions, output_dir, state)

    manifest = build_manifest(eval_set_path, eval_set, eval_hash, questions, args.expected_head, state.head, output_dir)
    ensure_manifest(output_dir / "manifest.json", manifest, dry_run=False)

    if args.rebuild_summary:
        recover_records(output_dir, eval_set, eval_hash, args.expected_head, state.head)
        rebuild_summary(output_dir, questions)
        return 0

    exit_code = 0
    completed_records: list[dict[str, Any]] = []
    for question in questions:
        code, stop = run_one(
            eval_set["evaluation_version"], eval_hash, question, output_dir,
            args.expected_head, state.head, state.repo_root, args.timeout_seconds,
        )
        record = json.loads((output_dir / question["id"] / "record.json").read_text(encoding="utf-8"))
        completed_records.append(record)
        rows = []
        for item in completed_records:
            json_status, payload = read_stdout_json(Path(item["stdout_file"]))
            rows.append(summary_row(item, payload if json_status == "valid" else None))
        write_summary(output_dir, rows)
        if code != 0 and exit_code == 0:
            exit_code = code
        if stop:
            break
    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the X-8 fixed evaluation set")
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--rebuild-summary", action="store_true")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--question-id")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except EvaluationError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
