import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_x8_evaluation.py"
spec = importlib.util.spec_from_file_location("run_x8_evaluation", SCRIPT_PATH)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def write_eval_set(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "evaluation_version": "test-v1",
                "questions": [
                    {
                        "id": "q01",
                        "category": "stable_fact",
                        "question": "富士山の標高は何メートルですか？",
                        "expected_behavior": "answer",
                        "acceptance_checks": ["check"],
                        "allowed_classifications": ["verified"],
                        "max_external_runs": 1,
                    },
                    {
                        "id": "q02",
                        "category": "false_premise",
                        "question": "日本の法定成人年齢は現在も20歳なのはなぜですか？",
                        "expected_behavior": "correct premise",
                        "acceptance_checks": ["check"],
                        "allowed_classifications": ["verified", "withheld"],
                        "max_external_runs": 1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def payload(status="completed", evidence_metrics=None):
    evidence_metrics = evidence_metrics or {
        "search_count": 1,
        "candidate_count": 5,
        "fetch_attempt_count": 4,
        "fetch_success_count": 3,
        "fetch_failure_count": 1,
        "evidence_count": 3,
    }
    return {
        "run_id": "run-1",
        "status": status,
        "participants": ["claude-code", "codex-cli"],
        "agent_call_count": 7,
        "answer": {"result_classification": "verified", "text": "secret answer not copied"},
        "metadata": {"elapsed_ms": 100, "evidence_count": 3, "error_codes": []},
        "phases": [
            {"phase": "respond", "status": "succeeded", "elapsed_ms": 10},
            {
                "phase": "evidence_collect",
                "status": "succeeded",
                "elapsed_ms": 20,
                "outcome": "partial_evidence",
                "metrics": evidence_metrics,
            },
        ],
        "executions": [
            {"agent_id": "claude-code", "phase": "respond", "status": "succeeded", "retry_of": None},
            {"agent_id": "codex-cli", "phase": "verify", "status": "succeeded", "retry_of": "exec-1"},
        ],
    }


@pytest.fixture
def harness(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    eval_set = tmp_path / "eval.json"
    write_eval_set(eval_set)
    output = tmp_path / "evals"
    monkeypatch.setattr(
        runner,
        "inspect_git",
        lambda cwd, allow_dirty=False: runner.GitState(
            repo_root=repo,
            head="b990707",
            origin_main="b990707",
            worktree_clean=not allow_dirty,
            origin_matches=True,
        ),
    )
    return repo, eval_set, output


def test_question_order_is_loaded_from_json():
    data = runner.load_eval_set(Path("evaluation/x8/eval-set-v1.json"))
    assert [question["id"] for question in data["questions"]] == [
        "q01",
        "q02",
        "q03",
        "q04",
        "q05",
        "q06",
        "q07",
        "q08",
    ]


def test_dry_run_does_not_run_subprocess_or_write_attempted(harness, monkeypatch, capsys):
    repo, eval_set, output = harness

    def fail_subprocess(*args, **kwargs):
        raise AssertionError("subprocess must not run in dry-run")

    monkeypatch.setattr(runner.subprocess, "run", fail_subprocess)
    exit_code = runner.main(
        [
            "--eval-set",
            str(eval_set),
            "--output-dir",
            str(output),
            "--expected-head",
            "b990707",
            "--all",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    printed = capsys.readouterr().out
    assert "q01 stable_fact" in printed
    assert "q02 false_premise" in printed
    assert "富士山の標高" in printed
    assert "origin_matches=true" in printed
    assert not (output / "q01" / "attempted.json").exists()


def test_one_question_writes_attempted_stdout_stderr_record_and_summary(harness, monkeypatch):
    repo, eval_set, output = harness
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        kwargs["stdout"].write(json.dumps(payload(), ensure_ascii=False).encode("utf-8"))
        kwargs["stderr"].write(b"progress only")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner.main(
        [
            "--eval-set",
            str(eval_set),
            "--output-dir",
            str(output),
            "--expected-head",
            "b990707",
            "--question-id",
            "q01",
        ]
    )

    assert exit_code == 0
    command, kwargs = calls[0]
    assert kwargs["shell"] is False
    assert command[0:4] == ["py", "-m", "oracle_council.cli", "ask"]
    assert command[4] == "富士山の標高は何メートルですか？"
    assert kwargs["stdout"] is not kwargs["stderr"]
    assert kwargs["env"]["PYTHONPATH"] == str(repo / "src")
    assert kwargs["env"]["PYTHONUTF8"] == "1"
    assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    assert kwargs["timeout"] == 600
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    attempted = json.loads((output / "q01" / "attempted.json").read_text(encoding="utf-8"))
    assert manifest["eval_set_sha256"] == attempted["eval_set_sha256"]
    assert manifest["question_ids"] == ["q01"]
    assert (output / "q01" / "attempted.json").exists()
    record = json.loads((output / "q01" / "record.json").read_text(encoding="utf-8"))
    assert record["run_id"] == "run-1"
    assert record["json_parse_status"] == "valid"
    assert record["acceptance_status"] == "not_assessed"
    assert record["evidence_metrics"]["fetch_failure_count"] == 1
    assert "secret answer not copied" not in json.dumps(record, ensure_ascii=False)
    summary = (output / "summary.csv").read_text(encoding="utf-8-sig")
    assert "q01,stable_fact,0,completed,verified,run-1,100,20,3,1,5,4,3,1,partial_evidence,1,,True,passed_structural_check,not_assessed" in summary


def test_attempted_after_success_rejects_rerun(harness, monkeypatch):
    repo, eval_set, output = harness

    def fake_run(cmd, **kwargs):
        kwargs["stdout"].write(json.dumps(payload()).encode("utf-8"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    args = [
        "--eval-set",
        str(eval_set),
        "--output-dir",
        str(output),
        "--expected-head",
        "b990707",
        "--question-id",
        "q01",
    ]
    assert runner.main(args) == 0
    assert runner.main(args) == 2


def test_attempted_after_failure_rejects_rerun(harness, monkeypatch):
    repo, eval_set, output = harness

    def fake_run(cmd, **kwargs):
        kwargs["stdout"].write(b"not-json")
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    args = [
        "--eval-set",
        str(eval_set),
        "--output-dir",
        str(output),
        "--expected-head",
        "b990707",
        "--question-id",
        "q01",
    ]
    assert runner.main(args) == 1
    assert runner.main(args) == 2
    record = json.loads((output / "q01" / "record.json").read_text(encoding="utf-8"))
    assert record["json_parse_status"] == "invalid"


def test_all_stops_after_systemic_invalid_json_failure(harness, monkeypatch):
    repo, eval_set, output = harness
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            kwargs["stdout"].write(b"not-json")
            return subprocess.CompletedProcess(cmd, 1)
        kwargs["stdout"].write(json.dumps(payload()).encode("utf-8"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    exit_code = runner.main(
        [
            "--eval-set",
            str(eval_set),
            "--output-dir",
            str(output),
            "--expected-head",
            "b990707",
            "--all",
        ]
    )

    assert exit_code == 1
    assert len(calls) == 1
    assert (output / "q01" / "attempted.json").exists()
    assert not (output / "q02" / "attempted.json").exists()


def test_all_continues_after_question_level_failure(harness, monkeypatch):
    repo, eval_set, output = harness
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            kwargs["stdout"].write(json.dumps(payload(status="withheld")).encode("utf-8"))
            return subprocess.CompletedProcess(cmd, 4)
        kwargs["stdout"].write(json.dumps(payload()).encode("utf-8"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main([
        "--eval-set", str(eval_set), "--output-dir", str(output),
        "--expected-head", "b990707", "--all",
    ]) == 4
    assert len(calls) == 2
    assert (output / "q02" / "attempted.json").exists()


def test_head_mismatch_dirty_origin_mismatch_and_repo_output_are_rejected(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    original_inspect_git = runner.inspect_git

    monkeypatch.setattr(
        runner,
        "inspect_git",
        lambda cwd, allow_dirty=False: runner.GitState(repo_root=repo, head="badhead", origin_main="badhead"),
    )
    with pytest.raises(runner.EvaluationError, match="HEAD mismatch"):
        runner.ensure_safe_environment(repo, tmp_path / "out", "b990707")

    monkeypatch.setattr(
        runner,
        "inspect_git",
        lambda cwd, allow_dirty=False: runner.GitState(repo_root=repo, head="b990707", origin_main="c572303"),
    )
    with pytest.raises(runner.EvaluationError, match="origin/main mismatch"):
        runner.ensure_safe_environment(repo, tmp_path / "out", "b990707")
    state = runner.ensure_safe_environment(
        repo,
        tmp_path / "out",
        "b990707",
        allow_origin_mismatch=True,
    )
    assert state.origin_main == "c572303"

    monkeypatch.setattr(
        runner,
        "inspect_git",
        lambda cwd, allow_dirty=False: runner.GitState(repo_root=repo, head="b990707", origin_main="b990707"),
    )
    with pytest.raises(runner.EvaluationError, match="outside"):
        runner.ensure_safe_environment(repo, repo / "inside", "b990707")
    with pytest.raises(runner.EvaluationError, match="outside"):
        runner.ensure_safe_environment(repo, repo / ".." / "repo" / "results", "b990707")
    with pytest.raises(runner.EvaluationError, match="outside"):
        runner.ensure_safe_environment(repo, Path(str(repo).upper()) / "RESULTS", "b990707")

    def fake_run_git(args, cwd):
        if args == ["rev-parse", "--show-toplevel"]:
            return str(repo)
        if args == ["status", "--short"]:
            return " M file.py"
        return "b990707"

    monkeypatch.setattr(runner, "inspect_git", original_inspect_git)
    monkeypatch.setattr(runner, "run_git", fake_run_git)
    with pytest.raises(runner.EvaluationError, match="not clean"):
        runner.inspect_git(repo)

    def missing_origin(args, cwd):
        if args == ["rev-parse", "--show-toplevel"]:
            return str(repo)
        if args == ["status", "--short"]:
            return ""
        if args == ["rev-parse", "--short", "refs/remotes/origin/main"]:
            raise runner.EvaluationError("git rev-parse failed")
        return "b990707"

    monkeypatch.setattr(runner, "run_git", missing_origin)
    with pytest.raises(runner.EvaluationError):
        runner.inspect_git(repo)


def test_missing_fields_and_unsafe_metrics_are_tolerated(harness, monkeypatch):
    repo, eval_set, output = harness

    def fake_run(cmd, **kwargs):
        kwargs["stdout"].write(json.dumps({"run_id": "run-min", "status": "completed"}).encode("utf-8"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main(
        [
            "--eval-set",
            str(eval_set),
            "--output-dir",
            str(output),
            "--expected-head",
            "b990707",
            "--question-id",
            "q01",
        ]
    ) == 0
    record = json.loads((output / "q01" / "record.json").read_text(encoding="utf-8"))
    assert record["run_id"] == "run-min"
    assert record["phase_summary"] == []
    row = json.loads((output / "summary.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["json_valid"] is True


def test_leakage_check_fails_on_forbidden_json_key():
    assert runner.leakage_check({"evidence": [{"content": "secret body"}]}) == "failed_structural_check"
    assert runner.leakage_check(None) == "json_invalid"


def test_phase_summary_keeps_safe_error_summary():
    payload = {
        "phases": [
            {
                "phase": "criticize",
                "status": "failed",
                "success_count": 0,
                "elapsed_ms": 123,
                "error_code": "INVALID_OUTPUT",
                "error_summary": "criticize invalid output: missing field: critique.",
                "outcome": None,
                "ignored": "not copied",
            }
        ]
    }

    assert runner.phase_summary(payload) == [
        {
            "phase": "criticize",
            "status": "failed",
            "success_count": 0,
            "elapsed_ms": 123,
            "error_code": "INVALID_OUTPUT",
            "error_summary": "criticize invalid output: missing field: critique.",
            "outcome": None,
        }
    ]


def test_phase_summary_drops_unsafe_error_summary():
    payload = {
        "phases": [
            {
                "phase": "criticize",
                "status": "failed",
                "success_count": 0,
                "elapsed_ms": 123,
                "error_code": "INVALID_OUTPUT",
                "error_summary": "raw stderr with SECRET-TOKEN",
                "outcome": None,
            }
        ]
    }

    assert runner.phase_summary(payload)[0]["error_summary"] is None


def test_manifest_mismatch_attempted_corruption_timeout_and_rebuild(harness, monkeypatch):
    repo, eval_set, output = harness

    def timeout_run(cmd, **kwargs):
        kwargs["stdout"].write("進捗".encode("utf-8"))
        kwargs["stderr"].write("標準エラー".encode("utf-8"))
        raise subprocess.TimeoutExpired(cmd, timeout=1)

    monkeypatch.setattr(runner.subprocess, "run", timeout_run)
    assert runner.main([
        "--eval-set", str(eval_set), "--output-dir", str(output),
        "--expected-head", "b990707", "--question-id", "q01", "--timeout-seconds", "1",
    ]) == 2
    record = json.loads((output / "q01" / "record.json").read_text(encoding="utf-8"))
    assert record["timed_out"] is True
    assert record["status"] == "timeout"
    assert record["runner_error_code"] == "TIMEOUT"
    (output / "q01" / "record.json").unlink()
    assert runner.main([
        "--eval-set", str(eval_set), "--output-dir", str(output),
        "--expected-head", "b990707", "--question-id", "q01", "--rebuild-summary",
    ]) == 0
    assert (output / "q01" / "record.json").exists()

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["expected_head"] = "other"
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert runner.main([
        "--eval-set", str(eval_set), "--output-dir", str(output),
        "--expected-head", "b990707", "--all",
    ]) == 2


def test_spawn_failure_records_and_stops_all(harness, monkeypatch):
    repo, eval_set, output = harness

    def fail_spawn(cmd, **kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(runner.subprocess, "run", fail_spawn)
    assert runner.main([
        "--eval-set", str(eval_set), "--output-dir", str(output),
        "--expected-head", "b990707", "--all",
    ]) == 2
    record = json.loads((output / "q01" / "record.json").read_text(encoding="utf-8"))
    assert record["runner_error_code"] == "SUBPROCESS_START_FAILED"
    assert not (output / "q02" / "attempted.json").exists()


def test_summary_csv_formula_injection_is_escaped(tmp_path):
    output = tmp_path / "out"
    row = {key: "" for key in runner.SUMMARY_FIELDS}
    row.update({"question_id": "q01", "category": "=cmd", "json_valid": True})
    runner.write_summary(output, [row])
    text = (output / "summary.csv").read_text(encoding="utf-8-sig")
    assert "q01,'=cmd" in text
