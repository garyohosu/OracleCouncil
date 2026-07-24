import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

import pytest

from oracle_council.adapters.grok import GrokAdapter
from oracle_council.models import AgentFailure, AgentRequest


def _prompt_file_path(cmd: list[str]) -> str:
    return cmd[cmd.index("--prompt-file") + 1]


def test_grok_passes_prompt_via_prompt_file_and_keeps_argv_data_free(monkeypatch):
    calls = []
    captured_file_content = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        path = _prompt_file_path(cmd)
        with open(path, encoding="utf-8") as stream:
            captured_file_content.append(stream.read())
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"text": '{"claims": [{"claim_id": "c1", "importance": "major", "status": "verified"}]}'}),
            stderr="",
        )

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
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

    result = GrokAdapter("grok-test").execute(request)

    assert result.output["claims"][0]["status"] == "verified"
    assert len(calls) == 2
    probe_cmd, probe_kwargs = calls[0]
    cmd, kwargs = calls[1]
    assert probe_cmd == ["grok", "--version"]
    assert probe_kwargs["stdin"] is not None

    # The prompt body must never appear on argv.
    assert "QUESTION-MARKER" not in cmd
    assert "CLAIM-SECRET" not in cmd
    assert "EVIDENCE-SECRET" not in cmd
    assert not any("QUESTION-MARKER" in part for part in cmd if isinstance(part, str))
    assert len(cmd) < 20  # argv stays short: flags + one path, not megabytes of content

    # Existing flags/behaviour preserved.
    assert cmd[0] == "grok"
    assert "--prompt-file" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert kwargs["shell"] is False
    assert "input" not in kwargs  # grok reads the prompt from the file, not stdin

    # The full prompt body did reach the CLI -- via the file.
    assert captured_file_content
    assert "QUESTION-MARKER" in captured_file_content[0]
    assert "CLAIM-SECRET" in captured_file_content[0]
    assert "EVIDENCE-SECRET" in captured_file_content[0]

    # And the temp file is cleaned up afterwards.
    assert not os.path.exists(_prompt_file_path(cmd))


def test_grok_prompt_file_preserves_japanese_content(monkeypatch):
    calls = []
    captured = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        path = _prompt_file_path(cmd)
        with open(path, encoding="utf-8") as stream:
            captured.append(stream.read())
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"text": '{"answer": "ok"}'}),
            stderr="",
        )

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    question = "富士山の標高は何メートルですか？改行を含む\n次の行です。"
    request = AgentRequest("run-1", "exec-1", "respond", {"question": question})

    result = GrokAdapter("grok-test").execute(request)

    assert result.output["answer"] == "ok"
    assert captured
    assert question in captured[0]
    # respond phase returns the raw question verbatim, so newlines inside it
    # must survive the file round-trip exactly.
    assert "改行を含む\n次の行です。" in captured[0]


def test_grok_prompt_file_handles_long_content_with_newlines(monkeypatch):
    calls = []
    captured = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        path = _prompt_file_path(cmd)
        with open(path, encoding="utf-8") as stream:
            captured.append(stream.read())
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"text": '{"answer": "ok"}'}),
            stderr="",
        )

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    line = "LINE-" + ("y" * 2000)
    question = "\n".join([line] * 50)  # ~100KB with embedded newlines
    request = AgentRequest("run-1", "exec-1", "respond", {"question": question})

    GrokAdapter("grok-test").execute(request)

    assert captured
    # respond's schema hint is appended after the question, so check
    # containment (exact equality is covered by the empty-prompt test) and
    # that none of the question's internal newlines were lost or mangled.
    assert question in captured[0]
    assert captured[0].count(line) == 50


def test_grok_prompt_file_empty_prompt_round_trips_to_empty_file(monkeypatch):
    # `_build_prompt` always attaches a schema hint for every known phase, so
    # a truly empty prompt cannot occur through the real phase pipeline; this
    # exercises the file-write path directly against that boundary case.
    monkeypatch.setattr("oracle_council.adapters.grok._build_prompt", lambda *a, **k: "")

    calls = []
    captured = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        path = _prompt_file_path(cmd)
        with open(path, encoding="utf-8") as stream:
            captured.append(stream.read())
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"text": '{"answer": "ok"}'}),
            stderr="",
        )

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "irrelevant"})

    GrokAdapter("grok-test").execute(request)

    assert captured == [""]


def test_grok_model_and_output_format_flags_preserved(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"text": '{"answer": "ok"}'}), stderr="")

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "q"})

    GrokAdapter("grok-test", model="grok-4-fast").execute(request)

    cmd = calls[1]
    assert cmd.index("--model") + 1 < len(cmd)
    assert cmd[cmd.index("--model") + 1] == "grok-4-fast"
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_grok_temp_file_removed_after_cli_nonzero_exit(monkeypatch):
    calls = []
    captured_path = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        captured_path.append(_prompt_file_path(cmd))
        return SimpleNamespace(returncode=17, stdout="opaque", stderr="generic failure text")

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "SECRET-MARKER-abc"})

    with pytest.raises(AgentFailure) as excinfo:
        GrokAdapter("grok-test").execute(request)

    assert excinfo.value.error_code == "EXECUTION_ERROR"
    # The failure message is built from stdout/stderr only, never the prompt.
    assert "SECRET-MARKER" not in str(excinfo.value)
    assert "SECRET-MARKER" not in (excinfo.value.public_summary or "")
    assert captured_path
    assert not os.path.exists(captured_path[0])


def test_grok_temp_file_removed_after_timeout(monkeypatch):
    calls = []
    captured_path = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        path = _prompt_file_path(cmd)
        captured_path.append(path)
        assert os.path.exists(path)  # file exists at the moment the CLI would read it
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "q"})

    with pytest.raises(AgentFailure) as excinfo:
        GrokAdapter("grok-test").execute(request)

    assert excinfo.value.error_code == "TIMEOUT"
    assert captured_path
    assert not os.path.exists(captured_path[0])


def test_grok_temp_file_removed_after_command_not_found(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        raise FileNotFoundError("grok not found")

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "q"})

    with pytest.raises(AgentFailure) as excinfo:
        GrokAdapter("grok-test").execute(request)

    assert excinfo.value.error_code == "COMMAND_NOT_FOUND"
    # We cannot capture the path in this scenario (fake_run raises before
    # returning it), but mkstemp() only ever creates one file per execute()
    # call, and the finally block unconditionally attempts os.unlink(path)
    # regardless of which branch raised -- covered structurally by the other
    # cleanup tests plus a temp-dir sweep here as a sanity net.
    leftover = [
        name for name in os.listdir(tempfile.gettempdir())
        if name.startswith("oracle-council-grok-")
    ]
    assert leftover == []


def test_grok_invalid_output_error_does_not_leak_prompt(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")
        return SimpleNamespace(returncode=0, stdout="not valid json at all", stderr="")

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)
    request = AgentRequest("run-1", "exec-1", "respond", {"question": "SECRET-MARKER-xyz"})

    with pytest.raises(AgentFailure) as excinfo:
        GrokAdapter("grok-test").execute(request)

    assert excinfo.value.error_code == "INVALID_OUTPUT"
    assert "SECRET-MARKER" not in str(excinfo.value)
    assert "SECRET-MARKER" not in (excinfo.value.public_summary or "")


def test_grok_closes_raw_fd_when_fdopen_construction_fails(monkeypatch):
    # Simulates os.fdopen(fd, ...) itself raising before it ever wraps the
    # raw descriptor in a file object -- the one path `with` cannot protect,
    # since there is no stream yet for its __exit__ to close.
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="grok 0.2.101", stderr="")

    monkeypatch.setattr("oracle_council.adapters.grok.subprocess.run", fake_run)

    captured_fd = []

    def failing_fdopen(fd, *args, **kwargs):
        captured_fd.append(fd)
        raise OSError("simulated fdopen construction failure")

    monkeypatch.setattr("oracle_council.adapters.grok.os.fdopen", failing_fdopen)

    request = AgentRequest("run-1", "exec-1", "respond", {"question": "q"})

    with pytest.raises(AgentFailure) as excinfo:
        GrokAdapter("grok-test").execute(request)

    assert excinfo.value.error_code == "EXECUTION_ERROR"
    assert captured_fd
    fd = captured_fd[0]
    # The adapter must have already closed the raw fd itself (os.fdopen()
    # never took ownership of it). Closing it again here must fail with a
    # "Bad file descriptor" style OSError, proving it is not left open.
    with pytest.raises(OSError):
        os.close(fd)

    # And the on-disk temp file created by mkstemp() before the fdopen
    # failure must not be left behind either.
    leftover = [
        name for name in os.listdir(tempfile.gettempdir())
        if name.startswith("oracle-council-grok-")
    ]
    assert leftover == []


def test_grok_cancel_terminates_subprocess(monkeypatch):
    infinite_sleep_cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

    adapter = GrokAdapter("grok-test", timeout_s=10)
    monkeypatch.setattr(adapter, "probe", lambda: type("ProbeResult", (object,), {"status": "OK"})())

    original_popen = subprocess.Popen
    popen_called = []

    def mock_popen(*args, **kwargs):
        if args[0][0] == "grok":
            new_args = (infinite_sleep_cmd,) + args[1:]
            proc = original_popen(*new_args, **kwargs)
        else:
            proc = original_popen(*args, **kwargs)
        popen_called.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    req = AgentRequest("run-1", "exec-1", "respond", {"question": "q"}, {})

    def cancel_thread_func():
        for _ in range(100):
            if popen_called:
                break
            time.sleep(0.01)
        assert popen_called
        adapter.cancel("exec-1")

    t = threading.Thread(target=cancel_thread_func)
    t.start()

    with pytest.raises(AgentFailure) as excinfo:
        adapter.execute(req)

    t.join()
    assert excinfo.value.error_code == "CANCELLED"
    proc = popen_called[0]
    assert proc.poll() is not None
