import json
from types import SimpleNamespace

from oracle_council.adapters.codex import CodexAdapter
from oracle_council.models import AgentRequest


def test_codex_passes_phase_input_via_stdin_and_keeps_argv_data_free(monkeypatch):
    calls = []
    schema_snapshots = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="codex 1.0", stderr="")
        schema_path = cmd[cmd.index("--output-schema") + 1]
        with open(schema_path, encoding="utf-8") as stream:
            schema_snapshots.append(stream.read())
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "claims": [
                        {"claim_id": "c1", "importance": "major", "status": "verified"}
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)
    question = "QUESTION-MARKER " + ("x" * 50000)
    claim_text = "CLAIM-SECRET-" + ("c" * 1000)
    evidence_text = "EVIDENCE-SECRET-" + ("e" * 1000)
    request = AgentRequest(
        "run-1",
        "exec-1",
        "verify",
        {
            "question": question,
            "claims": [{"claim_id": "c1", "text": claim_text}],
            "evidence": [{"evidence_id": "e1", "excerpt": evidence_text}],
        },
    )

    result = CodexAdapter("codex-test").execute(request)

    assert result.output["claims"][0]["status"] == "verified"
    assert len(calls) == 2
    probe_cmd, probe_kwargs = calls[0]
    cmd, kwargs = calls[1]
    assert probe_cmd[-1] == "--version"
    assert probe_kwargs["stdin"].__class__.__name__ == "DEVNULL".replace("DEVNULL", "int") or probe_kwargs["stdin"] is not None
    assert cmd[0] in {"codex", "codex.cmd"}
    assert cmd[1] == "exec"
    assert cmd[-1] == "-"
    assert "QUESTION-MARKER" not in cmd
    assert "CLAIM-SECRET" not in cmd
    assert "EVIDENCE-SECRET" not in cmd
    assert kwargs["input"].startswith("Phase: verify")
    assert "QUESTION-MARKER" in kwargs["input"]
    assert "CLAIM-SECRET" in kwargs["input"]
    assert "EVIDENCE-SECRET" in kwargs["input"]
    assert "stdin" not in kwargs
    assert kwargs["shell"] is False
    assert len(cmd) < 1000
    assert schema_snapshots
    assert "QUESTION-MARKER" not in schema_snapshots[0]
    assert "CLAIM-SECRET" not in schema_snapshots[0]
    assert "EVIDENCE-SECRET" not in schema_snapshots[0]


def test_codex_schema_temp_file_is_removed_after_failure(monkeypatch):
    schema_path = None
    calls = 0

    def fake_run(cmd, **kwargs):
        nonlocal schema_path, calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(returncode=0, stdout="codex 1.0", stderr="")
        schema_path = cmd[cmd.index("--output-schema") + 1]
        return SimpleNamespace(returncode=17, stdout="opaque", stderr="failure")

    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "q"})

    try:
        CodexAdapter("codex-test").execute(request)
    except Exception:
        pass

    assert schema_path is not None
    assert not __import__("os").path.exists(schema_path)
