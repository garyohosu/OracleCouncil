from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any

from ..models import AgentCapabilities, AgentFailure, AgentRequest, AgentResult, ProbeResult, Usage
from ..phase_schema import get_phase_schema
from .base import build_phase_input, classify_cli_error, execution_failure_summary, validate_phase_output, extract_json_object


import threading

_thread_local = threading.local()

def _custom_run(*args, **kwargs):
    adapter = getattr(_thread_local, "adapter", None)
    execution_id = getattr(_thread_local, "execution_id", None)

    if adapter is None or execution_id is None:
        return _orig_subprocess_run(*args, **kwargs)

    with adapter._lock:
        if execution_id in adapter._cancelled:
            raise AgentFailure("CANCELLED", "execution cancelled")

    timeout = kwargs.get("timeout")
    input_data = kwargs.get("input")
    env = kwargs.get("env")
    cmd = args[0]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        shell=False,
    )
    with adapter._lock:
        if execution_id in adapter._cancelled:
            proc.terminate()
            raise AgentFailure("CANCELLED", "execution cancelled")
        adapter._processes[execution_id] = proc

    try:
        stdout, stderr = proc.communicate(input=input_data, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise subprocess.TimeoutExpired(
            cmd,
            timeout,
            output=stdout if "stdout" in locals() else None,
            stderr=stderr if "stderr" in locals() else None,
        ) from exc
    finally:
        with adapter._lock:
            adapter._processes.pop(execution_id, None)

    with adapter._lock:
        is_cancelled = execution_id in adapter._cancelled

    if is_cancelled:
        raise AgentFailure("CANCELLED", "execution cancelled")

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr
    )

_orig_subprocess_run = subprocess.run
subprocess.run = _custom_run


class CodexAdapter:
    def __init__(self, agent_id: str, model: str | None = None, timeout_s: int = 180) -> None:
        self.agent_id, self.model, self.timeout_s = agent_id, model, timeout_s
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()

    def cancel(self, execution_id: str) -> None:
        with self._lock:
            self._cancelled.add(execution_id)
            proc = self._processes.get(execution_id)
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def probe(self) -> ProbeResult:
        try:
            res = subprocess.run(["codex.cmd" if os.name == "nt" else "codex", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, shell=False, stdin=subprocess.DEVNULL)
            text = res.stderr + "\n" + res.stdout
            if "session limit" in text.lower() or "limit" in text.lower(): return ProbeResult("QUOTA_EXCEEDED")
            if res.returncode != 0: return ProbeResult("EXECUTION_ERROR")
            cli_version = res.stdout.strip() or res.stderr.strip() or "unknown"
            caps = AgentCapabilities(
                adapter_family="codex-cli",
                adapter_version="1.0",
                cli_version=cli_version,
                supported_phases=("respond", "claim_extract", "verify", "criticize", "synthesize", "audit"),
                supports_read_only=True,
                supports_no_tools=True,
            )
            return ProbeResult("OK", caps)
        except FileNotFoundError: return ProbeResult("COMMAND_NOT_FOUND")
        except subprocess.TimeoutExpired: return ProbeResult("TIMEOUT")
        except Exception: return ProbeResult("EXECUTION_ERROR")

    def execute(self, request: AgentRequest) -> AgentResult:
        probe_res = self.probe()
        if probe_res.status != "OK": raise AgentFailure(probe_res.status, f"Codex Agent {self.agent_id} is unavailable: {probe_res.status}")
        schema = request.output_schema or get_phase_schema(request.phase)
        fd, path = tempfile.mkstemp(suffix=".json")
        _thread_local.adapter = self
        _thread_local.execution_id = request.execution_id
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream: json.dump(schema, stream)
            cmd = ["codex.cmd" if os.name == "nt" else "codex", "exec", "-s", "read-only", "--ephemeral", "--output-schema", path]
            if self.model: cmd.extend(["--model", self.model])
            cmd.append("-")
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout_s, env=dict(os.environ), input=build_phase_input(request), shell=False)
            err_text = res.stderr + "\n" + res.stdout
            error_code = classify_cli_error(res.stdout, res.stderr)
            if error_code: raise AgentFailure(error_code, err_text, process_exit_code=res.returncode)
            if res.returncode != 0: raise AgentFailure("EXECUTION_ERROR", err_text, public_summary=execution_failure_summary(request.phase, "subprocess_nonzero_exit"), process_exit_code=res.returncode)
            try:
                output = extract_json_object(res.stdout)
            except json.JSONDecodeError as exc:
                raise AgentFailure(
                    "INVALID_OUTPUT",
                    f"Failed to extract JSON from Codex output: {res.stdout}",
                    public_summary="malformed JSON",
                    process_exit_code=res.returncode,
                ) from exc
            try:
                return AgentResult(validate_phase_output(request.phase, output), Usage(100, 20), process_exit_code=res.returncode)
            except AgentFailure as failure:
                # Schema validation in base.py cannot see the subprocess
                # result; the process itself exited 0 (S-8 §1.1).
                if failure.process_exit_code is None: failure.process_exit_code = res.returncode
                raise
        except OSError as exc:
            raise AgentFailure("EXECUTION_ERROR", str(exc), public_summary=execution_failure_summary(request.phase, "process_launch_failure")) from exc
        finally:
            _thread_local.adapter = None
            _thread_local.execution_id = None
            try: os.unlink(path)
            except OSError: pass
