import json
from types import SimpleNamespace

from oracle_council.adapters.claude import ClaudeAdapter
from oracle_council.models import AgentRequest


def test_claude_passes_long_phase_input_via_stdin_and_keeps_argv_data_free(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="claude 1.0", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"result": '{"answer": "ok"}'}),
            stderr="",
        )

    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)
    question = "QUESTION-MARKER " + ("x" * 50000)
    request = AgentRequest("run-1", "exec-1", "synthesize", {"question": question})

    result = ClaudeAdapter("claude-test").execute(request)

    assert result.output["answer"] == "ok"
    assert len(calls) == 2
    probe_cmd, probe_kwargs = calls[0]
    cmd, kwargs = calls[1]
    assert probe_cmd == ["claude", "--version"]
    assert probe_kwargs["stdin"] is not None
    assert cmd[:2] == ["claude", "-p"]
    assert "QUESTION-MARKER" not in cmd
    assert len(cmd) < 1000
    assert kwargs["input"].startswith("Phase: synthesize")
    assert "QUESTION-MARKER" in kwargs["input"]
    assert "stdin" not in kwargs
    assert kwargs["shell"] is False

