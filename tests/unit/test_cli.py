import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from oracle_council.cli import main
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
