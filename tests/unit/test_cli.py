import json
import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from oracle_council.cli import output_run_result, main
from oracle_council.evidence import ManualEvidenceProvider, WebEvidenceProvider
from oracle_council.fakes import FakeEvidenceProvider
from oracle_council.models import (
    AgentExecutionRecord,
    AgentExecutionStatus,
    PhaseRecord,
    PhaseStatus,
    ResultClassification,
    RunResult,
    RunStatus,
    SearchError,
    SearchResult,
)
from oracle_council.storage import JSONLStorageBackend


@pytest.fixture
def temp_config():
    """Create a temporary agents.yaml and yield its path."""
    config_data = {
        "agents": [
            {
                "id": "claude",
                "adapter": "claude",
                "enabled": True,
                "role_priority": {"synthesize": 100},
            },
            {
                "id": "codex",
                "adapter": "codex",
                "enabled": True,
                "role_priority": {"verify": 100},
            },
        ]
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8") as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    # Set env var
    old_val = os.environ.get("ORACLE_COUNCIL_CONFIG")
    os.environ["ORACLE_COUNCIL_CONFIG"] = temp_path
    yield temp_path

    # Restore
    if old_val:
        os.environ["ORACLE_COUNCIL_CONFIG"] = old_val
    else:
        del os.environ["ORACLE_COUNCIL_CONFIG"]
    os.unlink(temp_path)


def test_cli_help(capsys):
    exit_code = main(["--help"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Oracle Council CLI" in captured.out or "Oracle Council CLI" in captured.err


def test_cli_ask_happy_path(temp_config, capsys, tmp_path):
    # Use custom storage directory via monkeypatching data directory if possible,
    # or let it write to ./data and then cleanup. For unit tests, we'll patch JSONLStorageBackend to use tmp_path.
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", "What is the height of Fuji?"])
        assert exit_code == 0

        captured = capsys.readouterr()
        # Non-json: stdout contains answer, stderr contains progress
        assert "Mock final synthesized answer." in captured.out
        assert "ev-1" not in captured.out
        assert "Starting Oracle Council..." in captured.err
        assert "[1/7]" in captured.err


def test_cli_ask_json_happy_path(temp_config, capsys, tmp_path):
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", "What is the height of Fuji?", "--json"])
        assert exit_code == 0

        captured = capsys.readouterr()
        # Json output: stdout is pure JSON, stderr has no progress output
        assert captured.err == ""
        
        data = json.loads(captured.out)
        assert data["schema_version"] == "1.0"
        assert data["status"] == "completed"
        assert data["answer"]["text"] == "Mock final synthesized answer."
        assert all(execution["substitute_for"] is None for execution in data["executions"])
        assert data["answer"]["result_classification"] == "verified"
        assert data["claims"][0]["claim_role"] == "proposed_answer"
        assert data["evidence"] == [{"evidence_id": "ev-1"}]
        assert data["metadata"]["evidence_count"] == len(data["evidence"]) == 1
        assert all("metrics" in phase for phase in data["phases"])
        assert next(phase for phase in data["phases"] if phase["phase"] == "respond")["metrics"] == {}
        evidence_phase = next(phase for phase in data["phases"] if phase["phase"] == "evidence_collect")
        assert evidence_phase["success_count"] == 1
        assert evidence_phase["outcome"] == "evidence_found"
        assert evidence_phase["metrics"]["evidence_count"] == 1


def test_cli_ask_insufficient_agents_when_one_agent_unavailable(temp_config, capsys, monkeypatch):
    """Deterministic counterpart of the live insufficient-agents E2E: one of
    two agents fails its availability probe, so the CLI must stop pre-flight
    with insufficient_agents / exit 3 instead of skipping or half-running."""
    monkeypatch.setenv("ORACLE_MOCK_PROBE_CLAUDE", "QUOTA_EXCEEDED")
    exit_code = main(["ask", "What is the height of Fuji?", "--json", "--no-store"])
    assert exit_code == 3

    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "insufficient_agents"
    assert data["run_id"] is None  # V-1: no Run is created for a pre-flight stop
    assert data["exit_code"] == 3


def test_cli_ask_manual_evidence_file(temp_config, capsys, tmp_path):
    """--evidence-file switches to the manual provider; the run's evidence
    count in the metadata snapshot reflects the file contents."""
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "claim-1": [
                    {"evidence_id": "ev-manual-1", "url": "https://example.com/a", "stance": "supports"},
                    {"evidence_id": "ev-manual-2", "url": "https://example.com/b", "stance": "supports"},
                ]
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(
        ["ask", "What is the height of Fuji?", "--json", "--no-store",
         "--evidence-file", str(evidence_path)]
    )
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "completed"
    assert data["metadata"]["evidence_count"] == 2
    assert data["evidence"] == [
        {
            "evidence_id": "ev-manual-1",
            "claim_id": "claim-1",
            "url": "https://example.com/a",
        },
        {
            "evidence_id": "ev-manual-2",
            "claim_id": "claim-1",
            "url": "https://example.com/b",
        },
    ]


def test_cli_ask_manual_evidence_summary_tolerates_missing_and_unknown_fields(temp_config, capsys, tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "claim-1": [
                    {
                        "evidence_id": "ev-manual-1",
                        "content": "secret body",
                        "stdout": "raw stdout",
                        "prompt": "raw prompt",
                        "unknown": "ignored",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-file", str(evidence_path)])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["evidence"] == [{"evidence_id": "ev-manual-1", "claim_id": "claim-1"}]
    assert "secret body" not in json.dumps(data, ensure_ascii=False)
    assert "raw stdout" not in json.dumps(data, ensure_ascii=False)
    assert "raw prompt" not in json.dumps(data, ensure_ascii=False)


class CaptureOrchestrator:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        CaptureOrchestrator.instances.append(self)

    def run_verify(self, question, mode="verify"):
        return RunResult(
            "run-test",
            RunStatus.COMPLETED,
            ResultClassification.VERIFIED,
            "captured answer",
            0,
            0,
            mode=mode,
        )


def capture_provider():
    CaptureOrchestrator.instances = []
    return patch("oracle_council.cli.Orchestrator", CaptureOrchestrator)


def test_cli_ask_default_evidence_provider_remains_fake(temp_config, capsys):
    with capture_provider():
        assert main(["ask", "q", "--json", "--no-store"]) == 0
    capsys.readouterr()
    provider = CaptureOrchestrator.instances[0].kwargs["evidence_provider"]
    assert isinstance(provider, FakeEvidenceProvider)


def test_cli_ask_evidence_provider_fake_selects_fake(temp_config, capsys):
    with capture_provider():
        assert main(["ask", "q", "--json", "--no-store", "--evidence-provider", "fake"]) == 0
    capsys.readouterr()
    provider = CaptureOrchestrator.instances[0].kwargs["evidence_provider"]
    assert isinstance(provider, FakeEvidenceProvider)


def test_cli_ask_evidence_file_only_selects_manual_provider(temp_config, capsys, tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({"claim-1": [{"evidence_id": "ev"}]}), encoding="utf-8")
    with capture_provider():
        assert main(["ask", "q", "--json", "--no-store", "--evidence-file", str(evidence_path)]) == 0
    capsys.readouterr()
    provider = CaptureOrchestrator.instances[0].kwargs["evidence_provider"]
    assert isinstance(provider, ManualEvidenceProvider)


def test_cli_ask_cli_search_builds_web_provider_with_cli_search_and_safe_fetcher(temp_config, capsys):
    fetcher = object()
    searcher = object()
    with patch("oracle_council.cli.SafeHttpFetcher", return_value=fetcher) as fetcher_cls, \
         patch("oracle_council.cli.CliSearchProvider", return_value=searcher) as searcher_cls, \
         capture_provider():
        assert main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"]) == 0
    capsys.readouterr()
    provider = CaptureOrchestrator.instances[0].kwargs["evidence_provider"]
    assert isinstance(provider, WebEvidenceProvider)
    assert provider._fetcher is fetcher
    assert provider._searcher is searcher
    fetcher_cls.assert_called_once_with()
    searcher_cls.assert_called_once_with()


def test_cli_ask_rejects_evidence_file_and_provider_conflict(temp_config, capsys, tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text("[]", encoding="utf-8")
    with patch("oracle_council.cli.load_config") as load_config:
        exit_code = main(
            [
                "ask",
                "q",
                "--json",
                "--no-store",
                "--evidence-file",
                str(evidence_path),
                "--evidence-provider",
                "fake",
            ]
        )
    captured = capsys.readouterr()
    assert exit_code == 3
    assert not load_config.called
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "configuration_error"
    assert data["exit_code"] == 3


class SearchErrorProvider:
    def collect(self, claims):
        raise SearchError("SEARCH_QUOTA_EXCEEDED", "raw stderr must not leak")


class PartialSearchErrorProvider:
    def collect_with_metrics(self, claims):
        error = SearchError("SEARCH_QUOTA_EXCEEDED", "raw stderr must not leak")
        error.partial_evidence = (
            {
                "evidence_id": "web-claim-a-1",
                "claim_id": "claim-a",
                "url": "https://example.com/a",
                "title": "safe title",
                "excerpt": "safe excerpt",
                "content": "secret full body",
            },
        )
        error.evidence_metrics = {
            "search_count": 2,
            "candidate_count": 1,
            "fetch_attempt_count": 1,
            "fetch_success_count": 1,
            "fetch_failure_count": 0,
            "evidence_count": 1,
            "target_claim_count": 2,
            "claims_with_evidence_count": 1,
            "search_error_codes": {"SEARCH_QUOTA_EXCEEDED": 1},
            "fetch_error_codes": {},
        }
        raise error


class InvalidIriSearchProvider:
    def search(self, query, limit):
        return [
            SearchResult(
                "https://example.com/\udcff",
                "invalid iri",
                "snippet",
                1,
                "fake-search",
                "2026-07-13T00:00:00+00:00",
            )
        ]


class SingleUrlSearchProvider:
    def search(self, query, limit):
        return [
            SearchResult(
                "https://dns-fail.example.com/a",
                "dns candidate",
                "snippet",
                1,
                "fake-search",
                "2026-07-13T00:00:00+00:00",
            )
        ]


def test_cli_ask_cli_search_search_error_becomes_json_verification_unavailable(temp_config, capsys):
    with patch("oracle_council.cli.WebEvidenceProvider", return_value=SearchErrorProvider()), \
         patch("oracle_council.cli.SafeHttpFetcher"), \
         patch("oracle_council.cli.CliSearchProvider"):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["schema_version"] == "1.0"
    assert data["run_id"]
    assert data["status"] == "verification_unavailable"
    assert data["exit_code"] == 3
    assert data["message"] == "web evidence unavailable: SEARCH_QUOTA_EXCEEDED"
    evidence_phase = next(phase for phase in data["phases"] if phase["phase"] == "evidence_collect")
    assert evidence_phase["status"] == "failed"
    assert evidence_phase["success_count"] == 0
    assert evidence_phase["error_code"] == "SEARCH_QUOTA_EXCEEDED"
    assert evidence_phase["finished_at"] is not None
    assert evidence_phase["metrics"]["search_error_codes"] == {"SEARCH_QUOTA_EXCEEDED": 1}
    assert "raw stderr" not in captured.out


def test_cli_ask_search_error_json_keeps_partial_sanitized_evidence(temp_config, capsys):
    with patch("oracle_council.cli.WebEvidenceProvider", return_value=PartialSearchErrorProvider()), \
         patch("oracle_council.cli.SafeHttpFetcher"), \
         patch("oracle_council.cli.CliSearchProvider"):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    evidence_phase = next(phase for phase in data["phases"] if phase["phase"] == "evidence_collect")
    assert exit_code == 3
    assert captured.err == ""
    assert data["status"] == "verification_unavailable"
    assert data["run_id"]
    assert data["evidence"] == [
        {
            "evidence_id": "web-claim-a-1",
            "claim_id": "claim-a",
            "url": "https://example.com/a",
            "title": "safe title",
            "excerpt": "safe excerpt",
        }
    ]
    assert evidence_phase["status"] == "failed"
    assert evidence_phase["metrics"]["evidence_count"] == 1
    assert evidence_phase["metrics"]["search_count"] == 2
    assert "secret full body" not in captured.out
    assert "raw stderr" not in captured.out


def test_cli_ask_invalid_iri_fetch_error_does_not_become_internal_error(temp_config, capsys):
    with patch("oracle_council.cli.CliSearchProvider", return_value=InvalidIriSearchProvider()):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "completed"
    assert data["run_id"]
    assert data["evidence"] == []
    evidence_phase = next(phase for phase in data["phases"] if phase["phase"] == "evidence_collect")
    assert evidence_phase["status"] == "succeeded"
    assert evidence_phase["success_count"] == 1
    assert evidence_phase["outcome"] == "no_evidence"
    assert evidence_phase["metrics"]["fetch_attempt_count"] == 1
    assert evidence_phase["metrics"]["fetch_failure_count"] == 1
    assert evidence_phase["metrics"]["fetch_error_codes"] == {"INVALID_URL_ENCODING": 1}
    rendered = json.dumps(data, ensure_ascii=False)
    assert "UnicodeEncodeError" not in rendered
    assert "\udcff" not in rendered


def test_cli_ask_dns_resolution_failure_does_not_become_internal_error(temp_config, capsys):
    """X-8.20: reproduces the q03 holdout leak (X-8.14). A DNS resolution
    failure on a fetch candidate previously propagated as a raw
    socket.gaierror out of SafeHttpFetcher, uncaught by
    WebEvidenceProvider/Orchestrator, all the way to cli.py's generic
    `except Exception` handler -> internal_error / exit_code 1 with the raw
    `[Errno 11001] getaddrinfo failed` text as the public message.

    This uses the real SafeHttpFetcher (not mocked) with only
    socket.getaddrinfo faked, per the instructed reproduction shape."""
    with patch("oracle_council.cli.CliSearchProvider", return_value=SingleUrlSearchProvider()), \
         patch(
             "oracle_council.evidence.socket.getaddrinfo",
             side_effect=socket.gaierror(11001, "getaddrinfo failed"),
         ):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])

    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)

    assert data["status"] != "internal_error"
    assert exit_code != 1
    assert data["oracle_exit_code"] == data["exit_code"]
    assert data["oracle_exit_code"] == exit_code
    assert data["run_id"]
    assert data["evidence"] == []

    evidence_phase = next(phase for phase in data["phases"] if phase["phase"] == "evidence_collect")
    assert evidence_phase["status"] == "succeeded"
    assert evidence_phase["success_count"] == 1
    assert evidence_phase["outcome"] == "no_evidence"
    assert evidence_phase["metrics"]["fetch_attempt_count"] == 1
    assert evidence_phase["metrics"]["fetch_failure_count"] == 1
    assert evidence_phase["metrics"]["fetch_error_codes"] == {"FETCH_FAILED": 1}

    rendered = json.dumps(data, ensure_ascii=False)
    assert "getaddrinfo" not in rendered
    assert "11001" not in rendered
    assert "gaierror" not in rendered
    assert "dns-fail.example.com" not in rendered


def test_cli_ask_cli_search_does_not_fallback_to_fake_provider(temp_config, capsys):
    with patch("oracle_council.cli.FakeEvidenceProvider") as fake_provider, \
         patch("oracle_council.cli.WebEvidenceProvider", return_value=SearchErrorProvider()), \
         patch("oracle_council.cli.SafeHttpFetcher"), \
         patch("oracle_council.cli.CliSearchProvider"):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])
    capsys.readouterr()
    assert exit_code == 3
    assert not fake_provider.called


def test_json_evidence_summary_allows_only_safe_web_fields_and_caps_excerpt(capsys):
    result = RunResult(
        run_id="run-test",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=0,
        oracle_exit_code=0,
        evidence=(
            {
                "evidence_id": "web-claim-1-1",
                "claim_id": "claim-1",
                "url": "https://example.com",
                "title": "Example",
                "source": "claude-code-websearch",
                "rank": 1,
                "content_type": "text/html",
                "retrieved_at": "2026-07-13T00:00:00+00:00",
                "excerpt": "x" * 401,
                "content": "full body must not leak",
                "body": "body must not leak",
                "raw_content": "raw must not leak",
                "stdout": "stdout must not leak",
                "stderr": "stderr must not leak",
                "prompt": "prompt must not leak",
                "environment": {"TOKEN": "secret"},
                "headers": {"Authorization": "secret"},
                "cookies": "secret",
                "tokens": "secret",
                "diagnostics": "secret",
                "notes": "internal note",
                "unknown": "ignored",
            },
        ),
    )

    exit_code = output_run_result(result, use_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    item = data["evidence"][0]
    assert exit_code == 0
    assert set(item) == {
        "evidence_id",
        "claim_id",
        "url",
        "title",
        "source",
        "rank",
        "content_type",
        "retrieved_at",
        "excerpt",
    }
    assert len(item["excerpt"]) == 400
    rendered = json.dumps(data, ensure_ascii=False)
    for forbidden in (
        "full body must not leak",
        "body must not leak",
        "raw must not leak",
        "stdout must not leak",
        "stderr must not leak",
        "prompt must not leak",
        "TOKEN",
        "Authorization",
        "internal note",
        "ignored",
    ):
        assert forbidden not in rendered


def test_json_evidence_summary_non_string_excerpt_is_safe(capsys):
    result = RunResult(
        run_id="run-test",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=0,
        oracle_exit_code=0,
        evidence=({"evidence_id": "ev-1", "excerpt": {"not": "string"}},),
    )

    output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data["evidence"] == [{"evidence_id": "ev-1", "excerpt": ""}]


def test_json_evidence_summary_does_not_serialize_nested_allowed_values(capsys):
    result = RunResult(
        run_id="run-test",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=0,
        oracle_exit_code=0,
        evidence=(
            {
                "evidence_id": {"stdout": "raw stdout"},
                "claim_id": ["prompt", "raw prompt"],
                "url": {"environment": {"TOKEN": "secret"}},
                "title": {"headers": {"Authorization": "secret"}},
                "source": {"cookies": "secret"},
                "rank": {"tokens": "secret"},
                "content_type": {"diagnostics": "secret"},
                "retrieved_at": {"unknown": "secret"},
                "excerpt": {"body": "secret body"},
            },
        ),
    )

    output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data["evidence"] == [
        {
            "evidence_id": "",
            "claim_id": "",
            "url": "",
            "title": "",
            "source": "",
            "content_type": "",
            "retrieved_at": "",
            "excerpt": "",
        }
    ]
    rendered = json.dumps(data, ensure_ascii=False)
    for forbidden in (
        "stdout",
        "raw stdout",
        "prompt",
        "raw prompt",
        "environment",
        "TOKEN",
        "headers",
        "Authorization",
        "cookies",
        "tokens",
        "diagnostics",
        "unknown",
        "secret body",
    ):
        assert forbidden not in rendered


def test_json_phase_metrics_summary_excludes_unsafe_values(capsys):
    result = RunResult(
        run_id="run-test",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=0,
        oracle_exit_code=0,
        phases=(
            PhaseRecord(
                phase_id="phase-1",
                run_id="run-test",
                phase="evidence_collect",
                minimum_success_count=1,
                status=PhaseStatus.SUCCEEDED,
                success_count=1,
                metrics={
                    "search_count": 1,
                    "candidate_count": 5,
                    "fetch_attempt_count": -1,
                    "query": "secret query",
                    "url": "https://example.com/secret",
                    "fetch_error_codes": {"FETCH_FAILED": 1, "NEGATIVE": -1, "bad": "secret"},
                    "diagnostics": {"prompt": "secret prompt"},
                },
            ),
        ),
    )

    output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data["phases"][0]["metrics"] == {
        "search_count": 1,
        "candidate_count": 5,
        "fetch_error_codes": {"FETCH_FAILED": 1},
    }
    rendered = json.dumps(data, ensure_ascii=False)
    assert "secret query" not in rendered
    assert "https://example.com/secret" not in rendered
    assert "secret prompt" not in rendered


def test_json_includes_only_safe_error_summary(capsys):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = RunResult(
        run_id="run-test",
        status=RunStatus.FAILED,
        result_classification=ResultClassification.UNVERIFIED,
        final_answer=None,
        call_count=1,
        oracle_exit_code=1,
        phases=(
            PhaseRecord(
                phase_id="phase-1",
                run_id="run-test",
                phase="criticize",
                minimum_success_count=1,
                status=PhaseStatus.FAILED,
                error_code="INVALID_OUTPUT",
                error_summary="criticize invalid output: missing field: critique.",
            ),
            PhaseRecord(
                phase_id="phase-2",
                run_id="run-test",
                phase="synthesize",
                minimum_success_count=1,
                status=PhaseStatus.FAILED,
                error_code="INVALID_OUTPUT",
                error_summary="raw stderr with SECRET-TOKEN",
            ),
        ),
        executions=(
            AgentExecutionRecord(
                execution_id="exec-1",
                run_id="run-test",
                agent_id="claude-code",
                phase="criticize",
                status=AgentExecutionStatus.FAILED,
                started_at=now,
                finished_at=now,
                elapsed_ms=0,
                error_code="INVALID_OUTPUT",
                error_summary="criticize invalid output: missing field: critique.",
            ),
            AgentExecutionRecord(
                execution_id="exec-2",
                run_id="run-test",
                agent_id="claude-code",
                phase="synthesize",
                status=AgentExecutionStatus.FAILED,
                started_at=now,
                finished_at=now,
                elapsed_ms=0,
                error_code="INVALID_OUTPUT",
                error_summary="raw stderr with SECRET-TOKEN",
            ),
        ),
    )

    output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)

    assert data["phases"][0]["error_summary"] == (
        "criticize invalid output: missing field: critique."
    )
    assert data["phases"][1]["error_summary"] is None
    assert data["executions"][0]["error_summary"] == (
        "criticize invalid output: missing field: critique."
    )
    assert data["executions"][1]["error_summary"] is None
    assert "SECRET-TOKEN" not in json.dumps(data, ensure_ascii=False)


def test_json_evidence_empty_without_evidence(capsys):
    result = RunResult(
        run_id="run-test",
        status=RunStatus.COMPLETED,
        result_classification=ResultClassification.VERIFIED,
        final_answer="answer",
        call_count=0,
        oracle_exit_code=0,
    )

    output_run_result(result, use_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data["evidence"] == []


def test_cli_ask_evidence_file_unreadable_is_configuration_error(temp_config, capsys, tmp_path):
    exit_code = main(
        ["ask", "q", "--json", "--no-store", "--evidence-file", str(tmp_path / "missing.json")]
    )
    assert exit_code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "configuration_error"


def test_cli_ask_high_risk_strict_trigger_non_interactive(temp_config, capsys):
    exit_code = main(["ask", "high_risk trigger test", "--no-interactive"])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "Stop: strictへの切り替えが必要です" in captured.err


def test_cli_ask_high_risk_strict_trigger_json_non_interactive(temp_config, capsys):
    exit_code = main(["ask", "high_risk trigger test", "--no-interactive", "--json"])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "strict_required"
    assert data["exit_code"] == 2


def test_cli_ask_safety_trigger(temp_config, capsys):
    exit_code = main(["ask", "safety_trigger test"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "safety_blocked" in captured.err


def test_cli_agents_status(temp_config, capsys):
    exit_code = main(["agents", "status"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Agent ID: claude" in captured.out
    assert "Status: OK" in captured.out


def test_cli_agents_validate(temp_config, capsys):
    exit_code = main(["agents", "validate"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Configuration is valid." in captured.out


def test_cli_history_purge_and_list(temp_config, capsys, tmp_path):
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        # Run one run
        main(["ask", "Fuji"])
        capsys.readouterr()  # flush stdout

        # List runs
        with patch("oracle_council.cli.Path", return_value=tmp_path), patch("oracle_council.cli.os.path.exists", return_value=True):
            exit_code = main(["history", "list"])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "Run ID:" in captured.out

            # Show run
            # Get run id from directory
            run_ids = [p.name for p in tmp_path.iterdir() if p.is_dir() and not p.name.startswith(".")]
            assert len(run_ids) == 1
            run_id = run_ids[0]

            exit_code = main(["history", "show", run_id])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "Run Metadata for" in captured.out
            assert "本文は保存されていません" in captured.out

            # Purge requires --yes
            exit_code = main(["history", "purge"])
            assert exit_code == 1

            # Purge with --yes
            exit_code = main(["history", "purge", "--yes"])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "Purged 1 runs." in captured.out


def test_cli_ask_quick_mode_success(temp_config, capsys, tmp_path):
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", "What is the third planet?", "--mode", "quick", "--json", "--adapter-mode", "fake"])
        assert exit_code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["mode"] == "quick"
        assert data["answer"]["external_verification"] is False
        assert data["status"] == "completed"
        assert data["oracle_exit_code"] == 0

        phases = [p["phase"] for p in data["phases"]]
        assert phases == ["respond", "compare", "synthesize"]
# ---------------------------------------------------------------------------
# S-4: ClarificationEngine -> Clarifier Agent CLI wiring (QandA S-4.1-S-4.4)
# ---------------------------------------------------------------------------

_AMBIGUOUS_CLI_QUESTION = "どちらのプランが良いですか？"


def test_cli_ask_ordinary_question_keeps_one_of_seven_progress(temp_config, capsys, tmp_path):
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", "What is the height of Fuji?"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[1/7]" in captured.err


def test_cli_ask_ambiguous_question_shows_one_of_eight_progress(temp_config, capsys, tmp_path):
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", _AMBIGUOUS_CLI_QUESTION])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[1/8]" in captured.err


def test_cli_ask_ambiguous_question_json_has_eight_calls(temp_config, capsys, tmp_path):
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", _AMBIGUOUS_CLI_QUESTION, "--json"])
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["agent_call_count"] == 8


def test_cli_ask_needs_clarification_stops_before_run_json(temp_config, capsys, tmp_path):
    os.environ["ORACLE_MOCK_CLARIFY_STATUS"] = "needs_clarification"
    try:
        with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
            exit_code = main(["ask", _AMBIGUOUS_CLI_QUESTION, "--json"])
    finally:
        del os.environ["ORACLE_MOCK_CLARIFY_STATUS"]
    assert exit_code == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "needs_clarification"
    assert data["run_id"] is None
    assert data["oracle_exit_code"] == 2
    assert data["exit_code"] == 2


@pytest.mark.parametrize(
    "status,expected_exit",
    [
        ("premise_issue", 2),
        ("unsupported", 2),
        ("safety_blocked", 2),
    ],
)
def test_cli_ask_stop_statuses_use_exit_code_two(temp_config, capsys, tmp_path, status, expected_exit):
    os.environ["ORACLE_MOCK_CLARIFY_STATUS"] = status
    try:
        with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
            exit_code = main(["ask", _AMBIGUOUS_CLI_QUESTION, "--json"])
    finally:
        del os.environ["ORACLE_MOCK_CLARIFY_STATUS"]
    assert exit_code == expected_exit
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == status
    assert data["run_id"] is None


def test_cli_ask_clarify_trigger_string_is_no_longer_special_cased(temp_config, capsys, tmp_path):
    # S-4: the dead magic-string simulator is removed. The literal text
    # "clarify_trigger" is now just ordinary question text and is handled
    # like any other question by the real ClarificationEngine (it resolves
    # via tiers 1/2 without needing the Clarifier Agent, since it contains
    # none of the six critical-ambiguity signals).
    with patch("oracle_council.cli.JSONLStorageBackend", return_value=JSONLStorageBackend(tmp_path)):
        exit_code = main(["ask", "clarify_trigger", "--no-interactive", "--json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] != "needs_clarification"


def test_cli_ask_clarify_trigger_source_removed():
    import inspect
    import oracle_council.cli as cli_module

    source = inspect.getsource(cli_module)
    assert '"clarify_trigger" in args.question' not in source
