"""S-8: child-CLI process exit codes and the Oracle exit code are separate.

process_exit_code is the OS exit code of one child agent process (None when
no process ran or the code was unobservable); oracle_exit_code is Oracle
Council's own external exit code (SPEC §13.4). Neither may be derived from
the other, and semantic results stay on the status/error-code enums.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from oracle_council.adapters.claude import ClaudeAdapter
from oracle_council.adapters.codex import CodexAdapter
from oracle_council.assignment import RegisteredAgent
from oracle_council.budget import TokenBudget
from oracle_council.cli import exit_stop, output_run_result
from oracle_council.fakes import FakeEvidenceProvider, ScriptedAgentAdapter
from oracle_council.models import (
    AgentExecutionRecord,
    AgentExecutionStatus,
    AgentFailure,
    AgentRequest,
    AgentResult,
    ResultClassification,
    RunMetadataRecord,
    RunResult,
    RunStatus,
    utc_now,
)
from oracle_council.orchestrator import EXIT_FAILED, EXIT_OK, EXIT_WITHHELD, Orchestrator
from oracle_council.storage import InMemoryStorageBackend


# --- models -----------------------------------------------------------------


def test_agent_result_process_exit_code_defaults_to_none():
    assert AgentResult({"answer": "x"}).process_exit_code is None


def test_agent_failure_holds_process_exit_code():
    failure = AgentFailure("EXECUTION_ERROR", "boom", process_exit_code=17)
    assert failure.process_exit_code == 17
    assert AgentFailure("TIMEOUT").process_exit_code is None


def test_agent_execution_record_holds_process_exit_code():
    now = utc_now()
    record = AgentExecutionRecord(
        execution_id="exec-1",
        run_id="run-1",
        agent_id="agent-a",
        phase="respond",
        status=AgentExecutionStatus.SUCCEEDED,
        started_at=now,
        finished_at=now,
        elapsed_ms=0,
        process_exit_code=0,
    )
    assert record.process_exit_code == 0
    assert not hasattr(record, "exit_code")


def test_run_result_oracle_exit_code_with_compat_alias():
    result = RunResult(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=7,
        oracle_exit_code=0,
    )
    assert result.oracle_exit_code == 0
    assert result.exit_code == result.oracle_exit_code


def test_run_metadata_record_to_dict_includes_oracle_exit_code():
    metadata = _metadata(oracle_exit_code=4)
    assert metadata.to_dict()["oracle_exit_code"] == 4


def _metadata(oracle_exit_code: int) -> RunMetadataRecord:
    return RunMetadataRecord(
        run_id="run-1",
        created_at=utc_now(),
        mode="verify",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        consensus_status="not_applicable",
        participant_count=2,
        claim_count=1,
        evidence_count=0,
        error_codes=(),
        elapsed_ms=1,
        content_saved=False,
        oracle_exit_code=oracle_exit_code,
    )


# --- adapter transport (monkeypatched subprocess; no real CLI) ---------------


def _claude_run_factory(final):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="claude 1.0", stderr="")
        return final(cmd, kwargs)

    return fake_run


def test_claude_success_propagates_returncode_zero(monkeypatch):
    fake_run = _claude_run_factory(
        lambda cmd, kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"result": '{"answer": "ok"}'}), stderr=""
        )
    )
    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    result = ClaudeAdapter("claude-test").execute(
        AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
    )
    assert result.process_exit_code == 0


def test_claude_nonzero_exit_keeps_actual_process_code(monkeypatch):
    fake_run = _claude_run_factory(
        lambda cmd, kwargs: SimpleNamespace(returncode=17, stdout="opaque", stderr="opaque")
    )
    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        ClaudeAdapter("claude-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "EXECUTION_ERROR"
    assert excinfo.value.process_exit_code == 17


def test_claude_invalid_output_after_clean_exit_keeps_process_zero(monkeypatch):
    fake_run = _claude_run_factory(
        lambda cmd, kwargs: SimpleNamespace(returncode=0, stdout="not json at all", stderr="")
    )
    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        ClaudeAdapter("claude-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "INVALID_OUTPUT"
    assert excinfo.value.process_exit_code == 0


def test_claude_schema_invalid_output_after_clean_exit_keeps_process_zero(monkeypatch):
    fake_run = _claude_run_factory(
        lambda cmd, kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"result": '{"wrong_field": "x"}'}), stderr=""
        )
    )
    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        ClaudeAdapter("claude-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "INVALID_OUTPUT"
    assert excinfo.value.process_exit_code == 0


def test_claude_command_not_found_has_no_process_code(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="claude 1.0", stderr="")
        raise FileNotFoundError("claude")

    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        ClaudeAdapter("claude-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "COMMAND_NOT_FOUND"
    assert excinfo.value.process_exit_code is None


def test_claude_timeout_has_no_process_code(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="claude 1.0", stderr="")
        raise subprocess.TimeoutExpired(cmd, 180)

    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        ClaudeAdapter("claude-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "TIMEOUT"
    assert excinfo.value.process_exit_code is None


def _codex_run_factory(final):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="codex 1.0", stderr="")
        return final(cmd, kwargs)

    return fake_run


def test_codex_success_propagates_returncode_zero(monkeypatch):
    fake_run = _codex_run_factory(
        lambda cmd, kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"answer": "ok"}), stderr=""
        )
    )
    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)

    result = CodexAdapter("codex-test").execute(
        AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
    )
    assert result.process_exit_code == 0


def test_codex_nonzero_exit_keeps_actual_process_code(monkeypatch):
    fake_run = _codex_run_factory(
        lambda cmd, kwargs: SimpleNamespace(returncode=17, stdout="opaque", stderr="opaque")
    )
    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        CodexAdapter("codex-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "EXECUTION_ERROR"
    assert excinfo.value.process_exit_code == 17


def test_codex_invalid_output_after_clean_exit_keeps_process_zero(monkeypatch):
    fake_run = _codex_run_factory(
        lambda cmd, kwargs: SimpleNamespace(returncode=0, stdout="not json at all", stderr="")
    )
    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        CodexAdapter("codex-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "INVALID_OUTPUT"
    assert excinfo.value.process_exit_code == 0


def test_codex_schema_invalid_output_after_clean_exit_keeps_process_zero(monkeypatch):
    fake_run = _codex_run_factory(
        lambda cmd, kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps({"wrong_field": "x"}), stderr=""
        )
    )
    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)

    with pytest.raises(AgentFailure) as excinfo:
        CodexAdapter("codex-test").execute(
            AgentRequest("run-1", "exec-1", "respond", {"question": "q"})
        )
    assert excinfo.value.error_code == "INVALID_OUTPUT"
    assert excinfo.value.process_exit_code == 0


# --- orchestrator -----------------------------------------------------------


def _claims(status="verified", importance="major"):
    return {"claims": [{"claim_id": "claim-1", "importance": importance, "status": status}]}


def _build(a_script, b_script, storage=None):
    adapter_a = ScriptedAgentAdapter(a_script)
    adapter_b = ScriptedAgentAdapter(b_script)
    orchestrator = Orchestrator(
        [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)],
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
    )
    return orchestrator


def test_fake_agent_success_records_no_process_code():
    storage = InMemoryStorageBackend()
    orchestrator = _build(
        [{"answer": "A"}, _claims("unverified"), _claims(), {"critique": "ok"}, {"answer": "final"}],
        [{"answer": "B"}, {"status": "approved"}],
        storage=storage,
    )

    result = orchestrator.run_verify("q")

    assert result.oracle_exit_code == EXIT_OK
    assert result.executions
    assert all(e.process_exit_code is None for e in result.executions)
    events = storage.load(result.run_id).events
    succeeded = [e for e in events if e.event_type == "agent_execution_succeeded"]
    assert succeeded
    assert all("process_exit_code" in e.payload for e in succeeded)
    assert all(e.payload["process_exit_code"] is None for e in succeeded)


def test_failure_process_code_is_kept_without_overriding_semantics():
    storage = InMemoryStorageBackend()
    orchestrator = _build(
        [{"answer": "A"}, AgentFailure("INVALID_OUTPUT", "bad", public_summary="malformed JSON", process_exit_code=0)],
        [{"answer": "B"}],
        storage=storage,
    )

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.oracle_exit_code == EXIT_FAILED
    failed = [e for e in result.executions if e.status is not AgentExecutionStatus.SUCCEEDED]
    assert len(failed) == 1
    # A clean process exit (0) does not soften the semantic failure.
    assert failed[0].process_exit_code == 0
    assert failed[0].error_code == "INVALID_OUTPUT"
    events = storage.load(result.run_id).events
    failure_events = [e for e in events if e.event_type == "agent_execution_failed"]
    assert failure_events[0].payload["process_exit_code"] == 0
    assert failure_events[0].payload["error_code"] == "INVALID_OUTPUT"
    forbidden = {"stderr", "stdout", "prompt", "question", "answer", "env", "environment", "path"}
    assert not (forbidden & set(failure_events[0].payload))


def test_retry_executions_record_individual_process_codes():
    orchestrator = _build(
        [
            AgentFailure("RATE_LIMITED", "slow down", process_exit_code=3),
            {"answer": "A"},
            _claims("unverified"),
            _claims(),
            {"critique": "ok"},
            {"answer": "final"},
        ],
        [{"answer": "B"}, {"status": "approved"}],
    )

    result = orchestrator.run_verify("q")

    assert result.oracle_exit_code == EXIT_OK
    first, second = result.executions[0], result.executions[1]
    assert first.error_code == "RATE_LIMITED"
    assert first.process_exit_code == 3
    assert second.retry_of == first.execution_id
    assert second.process_exit_code is None


def test_substitute_execution_records_individual_process_codes():
    orchestrator = _build(
        [
            {"answer": "A"},
            AgentFailure("EXECUTION_ERROR", "boom", process_exit_code=17),
            _claims(),
            {"critique": "ok"},
            {"answer": "final"},
        ],
        [{"answer": "B"}, _claims("unverified"), {"status": "approved"}],
    )

    result = orchestrator.run_verify("q")

    assert result.oracle_exit_code == EXIT_OK
    by_phase = [e for e in result.executions if e.phase == "claim_extract"]
    assert len(by_phase) == 2
    assert by_phase[0].process_exit_code == 17
    assert by_phase[1].substitute_for == by_phase[0].execution_id
    assert by_phase[1].process_exit_code is None


def test_metadata_snapshot_carries_oracle_exit_code():
    storage = InMemoryStorageBackend()
    orchestrator = _build(
        [
            {"answer": "A"},
            _claims("unverified", importance="critical"),
            _claims("unverified", importance="critical"),
        ],
        [{"answer": "B"}],
        storage=storage,
    )

    result = orchestrator.run_verify("q")

    # An unverified critical claim withholds before the publish phases run.
    assert result.oracle_exit_code == EXIT_WITHHELD
    assert result.metadata.oracle_exit_code == EXIT_WITHHELD
    events = storage.load(result.run_id).events
    terminal = events[-1]
    assert terminal.payload["metadata"]["oracle_exit_code"] == EXIT_WITHHELD


# --- CLI JSON ---------------------------------------------------------------


def _execution(process_exit_code, error_code=None):
    now = utc_now()
    return AgentExecutionRecord(
        execution_id="exec-1",
        run_id="run-test",
        agent_id="agent-a",
        phase="respond",
        status=AgentExecutionStatus.SUCCEEDED if error_code is None else AgentExecutionStatus.FAILED,
        started_at=now,
        finished_at=now,
        elapsed_ms=1,
        process_exit_code=process_exit_code,
        error_code=error_code,
    )


@pytest.mark.parametrize(
    "run_status, classification, oracle_exit_code",
    [
        (RunStatus.COMPLETED, ResultClassification.VERIFIED, 0),
        (RunStatus.FAILED, ResultClassification.UNVERIFIED, 1),
        (RunStatus.COMPLETED, ResultClassification.WITHHELD, 4),
    ],
)
def test_json_top_level_oracle_exit_code_with_alias(capsys, run_status, classification, oracle_exit_code):
    result = RunResult(
        run_id="run-test",
        status=run_status,
        result_classification=classification,
        final_answer="answer" if oracle_exit_code == 0 else None,
        call_count=1,
        oracle_exit_code=oracle_exit_code,
        executions=(_execution(0),),
    )

    returned = output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)

    assert returned == oracle_exit_code
    assert data["oracle_exit_code"] == oracle_exit_code
    assert data["exit_code"] == data["oracle_exit_code"]
    assert data["executions"][0]["process_exit_code"] == 0
    assert "exit_code" not in data["executions"][0]


def test_json_execution_process_code_null_for_fake_agents(capsys):
    result = RunResult(
        run_id="run-test",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=1,
        oracle_exit_code=0,
        executions=(_execution(None),),
    )

    output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)

    assert data["executions"][0]["process_exit_code"] is None


def test_exit_stop_json_has_oracle_exit_code_with_alias(capsys):
    returned = exit_stop("insufficient_agents", 3, "stop message", use_json=True)
    data = json.loads(capsys.readouterr().out)

    assert returned == 3
    assert data["run_id"] is None
    assert data["oracle_exit_code"] == 3
    assert data["exit_code"] == data["oracle_exit_code"]
