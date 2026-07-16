import pytest
import os
import subprocess
from typing import Any

from oracle_council.adapters.claude import ClaudeAdapter
from oracle_council.adapters.codex import CodexAdapter
from oracle_council.cli import FakeAgentAdapter
from oracle_council.models import AgentCapabilities, ProbeResult


def test_fake_agent_adapter_probe_and_capabilities():
    adapter = FakeAgentAdapter("claude", "OK", {"supported_models": ["mock-model-1"]})
    probe_res = adapter.probe()
    assert isinstance(probe_res, ProbeResult)
    assert probe_res.status == "OK"
    assert probe_res.capabilities is not None
    assert isinstance(probe_res.capabilities, AgentCapabilities)
    assert probe_res.capabilities.adapter_family == "fake-family"
    assert probe_res.capabilities.supports_read_only is True
    assert probe_res.capabilities.supports_no_tools is True
    assert probe_res.capabilities.supported_phases == (
        "respond", "claim_extract", "verify", "criticize", "synthesize", "audit"
    )
    # Check capabilities method does not exist or raises AttributeError
    with pytest.raises(AttributeError):
        adapter.capabilities()


def test_claude_adapter_probe_success(monkeypatch):
    class MockCompletedProcess:
        returncode = 0
        stdout = "claude-code v0.1.0"
        stderr = ""

    def mock_run(*args, **kwargs):
        return MockCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)

    adapter = ClaudeAdapter("claude-test", model="claude-3-5-sonnet")
    probe_res = adapter.probe()
    assert isinstance(probe_res, ProbeResult)
    assert probe_res.status == "OK"
    assert probe_res.capabilities is not None
    assert probe_res.capabilities.adapter_family == "claude-code"
    assert probe_res.capabilities.cli_version == "claude-code v0.1.0"
    assert probe_res.capabilities.supports_read_only is True
    assert probe_res.capabilities.supports_no_tools is True

    with pytest.raises(AttributeError):
        adapter.capabilities()


def test_codex_adapter_probe_success(monkeypatch):
    class MockCompletedProcess:
        returncode = 0
        stdout = "codex-cli v1.2.3"
        stderr = ""

    def mock_run(*args, **kwargs):
        return MockCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)

    adapter = CodexAdapter("codex-test", model="gpt-4")
    probe_res = adapter.probe()
    assert isinstance(probe_res, ProbeResult)
    assert probe_res.status == "OK"
    assert probe_res.capabilities is not None
    assert probe_res.capabilities.adapter_family == "codex-cli"
    assert probe_res.capabilities.cli_version == "codex-cli v1.2.3"
    assert probe_res.capabilities.supports_read_only is True
    assert probe_res.capabilities.supports_no_tools is True

    with pytest.raises(AttributeError):
        adapter.capabilities()
