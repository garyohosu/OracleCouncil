import json
import os
import subprocess
import sys

import pytest


@pytest.mark.live
@pytest.mark.expensive
def test_real_two_agent_council():
    """Opt-in smoke E2E; ordinary CI never invokes external CLIs.
    Skips while either agent is quota-limited."""
    if os.environ.get("ORACLE_COUNCIL_LIVE") != "1":
        pytest.skip("set ORACLE_COUNCIL_LIVE=1 to invoke Claude/Codex")
    env = dict(os.environ)
    env["ORACLE_COUNCIL_USE_REAL"] = "1"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "oracle_council.cli",
            "ask",
            "Pythonの辞書とリストの違いを、初心者向けに説明してください。",
            "--mode",
            "verify",
            "--no-interactive",
            "--adapter-mode",
            "real",
            "--no-store",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert process.stderr == ""
    payload = json.loads(process.stdout)
    if payload["status"] in {"insufficient_agents", "configuration_error"}:
        pytest.fail(payload)
    if payload["status"] == "failed":
        codes = {item.get("error_code") for item in payload.get("executions", [])}
        if codes & {"QUOTA_EXCEEDED", "AUTH_REQUIRED", "COMMAND_NOT_FOUND"}:
            pytest.skip(f"external adapter unavailable: {sorted(codes)}")
    assert payload["status"] in {"completed", "partial"}
    assert len(payload["participants"]) >= 2


@pytest.mark.live
@pytest.mark.expensive
def test_real_insufficient_agents_when_claude_unavailable():
    """Passes in environments where Claude cannot even be probed (not
    installed, broken PATH). Quota exhaustion is not probe-detectable —
    a version probe succeeds while execute() fails — so that scenario is
    covered by the deterministic fake-based CLI test instead."""
    if os.environ.get("ORACLE_COUNCIL_LIVE") != "1":
        pytest.skip("set ORACLE_COUNCIL_LIVE=1 to invoke Claude/Codex")

    from oracle_council.adapters import ClaudeAdapter, CodexAdapter

    claude_status = ClaudeAdapter("claude-probe").probe()
    if claude_status == "OK":
        pytest.skip("Claude probe is OK; the unavailable scenario is not reproducible now")
    if CodexAdapter("codex-probe").probe() != "OK":
        pytest.skip("Codex unavailable too; scenario needs exactly one usable agent")

    env = dict(os.environ)
    env["ORACLE_COUNCIL_USE_REAL"] = "1"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "oracle_council.cli",
            "ask",
            "テスト質問",
            "--mode",
            "verify",
            "--no-interactive",
            "--adapter-mode",
            "real",
            "--no-store",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert process.returncode == 3
    payload = json.loads(process.stdout)
    assert payload["status"] == "insufficient_agents"
    assert payload["run_id"] is None
    assert payload["exit_code"] == 3
