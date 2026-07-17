from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any

from ..models import AgentCapabilities, AgentFailure, AgentRequest, AgentResult, ProbeResult, Usage
from ..phase_schema import get_phase_schema
from .base import build_phase_input, classify_cli_error, execution_failure_summary, validate_phase_output, extract_json_object

# grok CLI invocation confirmed live (2026-07-18) and cross-checked against
# garyohosu/werewolf-game's config/agents.json (command "grok", args ["-p"],
# prompt_mode "arg"): `grok -p "<prompt>" --output-format json` wraps the
# model's text in a CLI metadata envelope
# `{"text": "<answer text>", "stopReason": ..., "usage": {...}, ...}` - the
# phase JSON is inside envelope["text"], the same shape ClaudeAdapter already
# handles for its own envelope["result"]. grok has a `--json-schema` flag
# that constrains output further, but a plain-text schema hint in the prompt
# (this adapter's approach) avoids a second, less-tested code path and
# matches werewolf-game's proven approach of describing the schema in the
# prompt itself.
_PHASE_SCHEMA_HINT = {
    "clarify": (
        '{"status": "ready|ready_with_assumptions|needs_clarification|premise_issue|unsupported|safety_blocked", '
        '"refined_question": "<string>", "assumptions": ["<string>"], '
        '"questions": [{"text": "<string>", "importance": "critical|major|minor"}]}'
    ),
    "respond": '{"answer": "<your answer as a string>"}',
    "claim_extract": (
        '{"claims": [{"claim_id": "<string>", '
        '"importance": "critical|major|minor", "status": "unverified", '
        '"claim_role": "user_premise|proposed_answer|contextual", "text": "<string>"}]}'
    ),
    "verify": (
        '{"claims": [{"claim_id": "<string>", "importance": "critical|major|minor", '
        '"status": "verified|supported|contradicted|conflicting|unverified|not_applicable"}]}'
    ),
    "criticize": '{"critique": "<string>"}',
    "synthesize": '{"answer": "<string>"}',
    "audit": (
        '{"status": "approved|changes_required|blocked", '
        '"issues": [{"issue_id": "<string>", "issue_type": "<string>", '
        '"severity": "<string>", "claim_id": "<string>"}]}'
    ),
}


def _build_prompt(phase: str, question: str, output_schema: dict[str, Any] | None = None) -> str:
    hint = _PHASE_SCHEMA_HINT.get(phase)
    if not hint:
        return question
    schema_text = json.dumps(output_schema or get_phase_schema(phase), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "\n".join(
        [
            question,
            "",
            "Respond with ONLY one JSON object that validates against this JSON Schema.\n" + schema_text,
        ]
    )


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

    return subprocess.CompletedProcess(args=cmd, returncode=proc.returncode, stdout=stdout, stderr=stderr)


_orig_subprocess_run = subprocess.run
subprocess.run = _custom_run


class GrokAdapter:
    """xAI Grok CLI (`grok -p ... --output-format json`).

    Real invocation shape confirmed live 2026-07-18 (not guessed): prompt is
    passed as a trailing positional argument (matching garyohosu/werewolf-game's
    config/agents.json, which uses the same "grok -p <prompt>" + prompt_mode
    "arg" combination this project has already exercised in real games).
    `--output-format json` wraps the response as
    `{"text": "<model text>", "stopReason": ..., "usage": {...}, ...}`; the
    phase JSON lives inside `envelope["text"]`, unwrapped the same way
    ClaudeAdapter unwraps `envelope["result"]`. Grok has been observed to
    respond noticeably slower than Claude/Codex (garyohosu/werewolf-game
    QandA: a 60s timeout was insufficient in one real game, 120s worked);
    this adapter keeps the same SPEC Sec8.4 180s default as the other
    Adapters, which already exceeds the demonstrated-working value with
    margin, rather than inventing a Grok-specific number.
    """

    def __init__(self, agent_id: str, model: str | None = None, timeout_s: int = 180) -> None:
        self.agent_id = agent_id
        self.model = model
        self.timeout_s = timeout_s
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
        cmd = ["grok", "--version"]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                shell=False,
                stdin=subprocess.DEVNULL,
            )
            err_text = res.stderr + "\n" + res.stdout
            if "session limit" in err_text.lower() or "limit" in err_text.lower():
                return ProbeResult("QUOTA_EXCEEDED")
            if res.returncode != 0:
                return ProbeResult("EXECUTION_ERROR")
            cli_version = res.stdout.strip() or res.stderr.strip() or "unknown"
            caps = AgentCapabilities(
                adapter_family="grok-cli",
                adapter_version="1.0",
                cli_version=cli_version,
                supported_phases=(
                    "clarify", "respond", "claim_extract", "verify", "criticize", "synthesize", "audit",
                ),
                supports_read_only=True,
                supports_no_tools=True,
            )
            return ProbeResult("OK", caps)
        except FileNotFoundError:
            return ProbeResult("COMMAND_NOT_FOUND")
        except subprocess.TimeoutExpired:
            return ProbeResult("TIMEOUT")
        except Exception:
            return ProbeResult("EXECUTION_ERROR")

    def execute(self, request: AgentRequest) -> AgentResult:
        probe_res = self.probe()
        if probe_res.status != "OK":
            raise AgentFailure(probe_res.status, f"Grok Agent {self.agent_id} is unavailable: {probe_res.status}")

        prompt = _build_prompt(request.phase, build_phase_input(request), request.output_schema)

        cmd = ["grok", "-p", prompt, "--output-format", "json"]
        if self.model:
            cmd.extend(["--model", self.model])

        env = dict(os.environ)

        _thread_local.adapter = self
        _thread_local.execution_id = request.execution_id
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                env=env,
                shell=False,
            )
            err_text = res.stderr + "\n" + res.stdout
            error_code = classify_cli_error(res.stdout, res.stderr)
            if error_code:
                raise AgentFailure(error_code, err_text, process_exit_code=res.returncode)
            if res.returncode != 0:
                raise AgentFailure(
                    "EXECUTION_ERROR",
                    err_text,
                    public_summary=execution_failure_summary(request.phase, "subprocess_nonzero_exit"),
                    process_exit_code=res.returncode,
                )

            try:
                envelope = json.loads(res.stdout.strip())
            except json.JSONDecodeError as exc:
                raise AgentFailure(
                    "INVALID_OUTPUT",
                    f"Failed to parse CLI envelope: {res.stdout}",
                    public_summary="malformed JSON",
                    process_exit_code=res.returncode,
                ) from exc
            # --output-format json wraps the model's text in a CLI metadata
            # envelope; the phase JSON is inside envelope["text"] (confirmed
            # live 2026-07-18), analogous to Claude's envelope["result"].
            result_text = envelope.get("text", "") if isinstance(envelope, dict) else res.stdout
            try:
                output = validate_phase_output(request.phase, extract_json_object(result_text))
                return AgentResult(output, Usage(100, 20), process_exit_code=res.returncode)
            except AgentFailure as failure:
                if failure.process_exit_code is None:
                    failure.process_exit_code = res.returncode
                raise
            except json.JSONDecodeError as exc:
                raise AgentFailure(
                    "INVALID_OUTPUT",
                    f"Failed to parse phase JSON from model text: {result_text}",
                    public_summary="malformed JSON",
                    process_exit_code=res.returncode,
                ) from exc

        except FileNotFoundError:
            raise AgentFailure("COMMAND_NOT_FOUND", "grok command not found")
        except subprocess.TimeoutExpired as exc:
            raise AgentFailure("TIMEOUT", "grok command timed out") from exc
        except OSError as exc:
            raise AgentFailure(
                "EXECUTION_ERROR",
                str(exc),
                public_summary=execution_failure_summary(request.phase, "process_launch_failure"),
            ) from exc
        finally:
            _thread_local.adapter = None
            _thread_local.execution_id = None
