import json
import os
import subprocess
import sys

import pytest


@pytest.mark.live
@pytest.mark.expensive
def test_real_claude_codex_verify_json():
    """Opt-in smoke E2E; ordinary CI never invokes external CLIs."""
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
