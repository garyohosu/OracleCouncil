import json
import subprocess

from oracle_council.adapters.claude import ClaudeAdapter
from oracle_council.adapters.codex import CodexAdapter
from oracle_council.models import AgentRequest


def completed(stdout: str):
    return subprocess.CompletedProcess(args=["mock"], returncode=0, stdout=stdout, stderr="")


def test_claude_adapter_accepts_japanese_question_with_mocked_subprocess(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return completed(json.dumps({"result": json.dumps({"answer": "ok"})}))

    adapter = ClaudeAdapter("claude-code")
    monkeypatch.setattr(adapter, "probe", lambda: "OK")
    monkeypatch.setattr("oracle_council.adapters.claude.subprocess.run", fake_run)

    result = adapter.execute(
        AgentRequest("run-1", "exec-1", "respond", {"question": "富士山の標高は何メートルですか？"})
    )

    assert result.output == {"answer": "ok"}
    cmd, kwargs = calls[0]
    assert all("富士山" not in part for part in cmd)
    assert "富士山" in kwargs["input"]
    assert "stdin" not in kwargs
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


def test_codex_adapter_accepts_japanese_question_with_mocked_subprocess(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return completed(json.dumps({"answer": "ok"}))

    adapter = CodexAdapter("codex-cli")
    monkeypatch.setattr(adapter, "probe", lambda: "OK")
    monkeypatch.setattr("oracle_council.adapters.codex.subprocess.run", fake_run)

    result = adapter.execute(
        AgentRequest("run-1", "exec-1", "respond", {"question": "富士山の標高は何メートルですか？"})
    )

    assert result.output == {"answer": "ok"}
    cmd, kwargs = calls[0]
    assert "富士山の標高は何メートルですか？" not in cmd
    assert "富士山の標高は何メートルですか？" in kwargs["input"]
    assert cmd[-1] == "-"
    assert "stdin" not in kwargs
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
