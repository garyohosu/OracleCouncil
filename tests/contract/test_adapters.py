import os
from unittest.mock import patch

import pytest

from oracle_council.adapters import ClaudeAdapter, CodexAdapter
from oracle_council.adapters.base import validate_phase_output
from oracle_council.cli import FakeAgentAdapter
from oracle_council.models import AgentFailure, AgentRequest, AgentResult


class TestValidatePhaseOutputClaimEnums:
    """Regression coverage for the live-testing finding (QandA W-5 follow-up):
    a real model returned importance="high", an unhandled ValueError crashed
    downstream in Claim.from_dict(), and the run surfaced as an uncontrolled
    internal_error instead of the SPEC §8.5 fail-closed INVALID_OUTPUT path."""

    def test_out_of_enum_importance_is_rejected(self):
        with pytest.raises(AgentFailure) as excinfo:
            validate_phase_output(
                "claim_extract",
                {"claims": [{"claim_id": "c1", "importance": "high", "status": "unverified"}]},
            )
        assert excinfo.value.error_code == "INVALID_OUTPUT"

    def test_out_of_enum_status_is_rejected(self):
        with pytest.raises(AgentFailure):
            validate_phase_output(
                "verify",
                {"claims": [{"claim_id": "c1", "importance": "major", "status": "probably_true"}]},
            )

    def test_missing_status_is_allowed_and_defaults_downstream(self):
        # claim_extract may omit status; Claim.from_dict defaults to unverified.
        output = validate_phase_output(
            "claim_extract", {"claims": [{"claim_id": "c1", "importance": "minor"}]}
        )
        assert output["claims"][0]["importance"] == "minor"

    def test_missing_claim_id_is_rejected(self):
        with pytest.raises(AgentFailure):
            validate_phase_output("claim_extract", {"claims": [{"importance": "major"}]})

    def test_valid_claims_pass_through_unchanged(self):
        claims = [{"claim_id": "c1", "importance": "critical", "status": "verified"}]
        assert validate_phase_output("verify", {"claims": claims})["claims"] == claims


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
    """Skips (not fails) while Claude is quota-limited, so the suite result
    shows exactly what is usable right now."""
    adapter = ClaudeAdapter("claude-test")
    status = adapter.probe()
    if status != "OK":
        pytest.skip(f"Claude Code unavailable at probe: {status}")

    req = AgentRequest("run-1", "exec-1", "respond", {"question": "Say hello"})
    try:
        res = adapter.execute(req)
    except AgentFailure as e:
        if e.error_code in ("QUOTA_EXCEEDED", "AUTH_REQUIRED", "RATE_LIMITED"):
            pytest.skip(f"Claude Code unusable right now: {e.error_code}")
        raise
    assert isinstance(res, AgentResult)
    assert isinstance(res.output, dict)


@pytest.mark.live
def test_codex_adapter_live_execute():
    adapter = CodexAdapter("codex-test")
    status = adapter.probe()
    if status != "OK":
        pytest.skip(f"Codex CLI unavailable at probe: {status}")

    req = AgentRequest("run-1", "exec-1", "respond", {"question": "Say hello"})
    try:
        res = adapter.execute(req)
    except AgentFailure as e:
        if e.error_code in ("QUOTA_EXCEEDED", "AUTH_REQUIRED", "RATE_LIMITED"):
            pytest.skip(f"Codex CLI unusable right now: {e.error_code}")
        raise
    assert isinstance(res, AgentResult)
    assert "answer" in res.output
