import os
from unittest.mock import patch

import pytest

from oracle_council.adapters import ClaudeAdapter, CodexAdapter
from oracle_council.cli import FakeAgentAdapter
from oracle_council.models import AgentFailure, AgentRequest, AgentResult


def verify_adapter_contract(adapter):
    # probe()
    status = adapter.probe()
    assert isinstance(status, str)

    # capabilities()
    caps = adapter.capabilities()
    assert isinstance(caps, dict)
    assert "supported_models" in caps
    assert caps.get("supports_read_only") is True
    assert caps.get("supports_no_tools") is True


def test_fake_adapter_contract():
    adapter = FakeAgentAdapter("claude", "OK")
    verify_adapter_contract(adapter)

    req = AgentRequest("run-1", "exec-1", "respond", {"question": "test"})
    res = adapter.execute(req)
    assert isinstance(res, AgentResult)
    assert "answer" in res.output


@pytest.mark.live
def test_claude_adapter_live_probe():
    adapter = ClaudeAdapter("claude-test")
    status = adapter.probe()
    assert status in ("OK", "QUOTA_EXCEEDED", "COMMAND_NOT_FOUND", "TIMEOUT")


@pytest.mark.live
def test_codex_adapter_live_probe():
    adapter = CodexAdapter("codex-test")
    status = adapter.probe()
    assert status in ("OK", "QUOTA_EXCEEDED", "COMMAND_NOT_FOUND", "TIMEOUT")


@pytest.mark.live
def test_claude_adapter_live_execute():
    adapter = ClaudeAdapter("claude-test")
    status = adapter.probe()
    if status not in ("OK", "QUOTA_EXCEEDED"):
        pytest.skip(f"Claude Code is not in usable status: {status}")

    req = AgentRequest("run-1", "exec-1", "respond", {"question": "Say hello"})
    try:
        res = adapter.execute(req)
        assert isinstance(res, AgentResult)
        assert isinstance(res.output, dict)
    except AgentFailure as e:
        assert e.error_code in ("QUOTA_EXCEEDED", "AUTH_REQUIRED", "EXECUTION_ERROR")


@pytest.mark.live
def test_codex_adapter_live_execute():
    adapter = CodexAdapter("codex-test")
    status = adapter.probe()
    if status not in ("OK", "QUOTA_EXCEEDED"):
        pytest.skip(f"Codex CLI is not in usable status: {status}")

    req = AgentRequest("run-1", "exec-1", "respond", {"question": "Say hello"})
    try:
        res = adapter.execute(req)
        assert isinstance(res, AgentResult)
        assert "answer" in res.output
    except AgentFailure as e:
        assert e.error_code in ("QUOTA_EXCEEDED", "AUTH_REQUIRED", "EXECUTION_ERROR")
