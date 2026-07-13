import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from oracle_council.cli import main
from oracle_council.evidence import ManualEvidenceProvider, WebEvidenceProvider
from oracle_council.fakes import FakeEvidenceProvider
from oracle_council.models import ResultClassification, RunResult, RunStatus, SearchError
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
        assert data["answer"]["result_classification"] == "verified"


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


class CaptureOrchestrator:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        CaptureOrchestrator.instances.append(self)

    def run_verify(self, question):
        return RunResult(
            "run-test",
            RunStatus.COMPLETED,
            ResultClassification.VERIFIED,
            "captured answer",
            0,
            0,
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


def test_cli_ask_cli_search_search_error_becomes_json_verification_unavailable(temp_config, capsys):
    with patch("oracle_council.cli.WebEvidenceProvider", return_value=SearchErrorProvider()), \
         patch("oracle_council.cli.SafeHttpFetcher"), \
         patch("oracle_council.cli.CliSearchProvider"):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data == {
        "schema_version": "1.0",
        "run_id": None,
        "status": "verification_unavailable",
        "exit_code": 3,
        "message": "web evidence unavailable: SEARCH_QUOTA_EXCEEDED",
    }
    assert "raw stderr" not in captured.out


def test_cli_ask_cli_search_does_not_fallback_to_fake_provider(temp_config, capsys):
    with patch("oracle_council.cli.FakeEvidenceProvider") as fake_provider, \
         patch("oracle_council.cli.WebEvidenceProvider", return_value=SearchErrorProvider()), \
         patch("oracle_council.cli.SafeHttpFetcher"), \
         patch("oracle_council.cli.CliSearchProvider"):
        exit_code = main(["ask", "q", "--json", "--no-store", "--evidence-provider", "cli-search"])
    capsys.readouterr()
    assert exit_code == 3
    assert not fake_provider.called


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
