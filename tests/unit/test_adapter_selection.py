from unittest.mock import patch
import os
import tempfile

import pytest
import yaml

from oracle_council.cli import FakeAgentAdapter, main


@pytest.fixture
def temp_config(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        yaml.safe_dump({"agents": [
            {"id": "claude", "adapter": "claude", "enabled": True},
            {"id": "codex", "adapter": "codex", "enabled": True},
        ]}, handle)
        path = handle.name
    monkeypatch.setenv("ORACLE_COUNCIL_CONFIG", path)
    yield path
    os.unlink(path)


def test_cli_adapter_mode_fake_overrides_environment(temp_config, capsys, monkeypatch):
    monkeypatch.setenv("ORACLE_COUNCIL_USE_REAL", "1")
    with patch("oracle_council.cli.ClaudeAdapter") as claude, patch("oracle_council.cli.CodexAdapter") as codex:
        assert main(["ask", "question", "--adapter-mode", "fake", "--no-store"]) == 0
        assert not claude.called
        assert not codex.called
    capsys.readouterr()


def test_cli_adapter_mode_real_overrides_config(temp_config, capsys):
    fake_real = FakeAgentAdapter("real")
    with patch("oracle_council.cli.ClaudeAdapter", return_value=fake_real) as claude, \
         patch("oracle_council.cli.CodexAdapter", return_value=fake_real) as codex:
        assert main(["ask", "question", "--adapter-mode", "real", "--no-store"]) == 0
        assert claude.called
        assert codex.called
    capsys.readouterr()
