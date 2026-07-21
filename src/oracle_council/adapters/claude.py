from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from ..models import AgentCapabilities, AgentFailure, AgentRequest, AgentResult, ProbeResult, SearchError, SearchResult, Usage, utc_now
from ..phase_schema import get_phase_schema
from .base import build_phase_input, classify_cli_error, execution_failure_summary, validate_phase_output, extract_json_object

# Claude Code has no --output-schema flag (unlike Codex). The model must be
# told in the prompt what shape to answer in, and `--output-format json`
# wraps whatever text it produces in a CLI metadata envelope
# (`{"type":"result","result":"<answer text>",...}`) rather than emitting
# the phase JSON at the top level. Found via live testing (QandA W-5
# follow-up): parsing the envelope itself against the phase schema failed
# with "missing field: answer" even on a successful call.
_PHASE_SCHEMA_HINT = {
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

# Extra constraint lines for fields the model has been observed to drift on
# (e.g. returning importance="high" instead of a schema member). The "|"
# notation in _PHASE_SCHEMA_HINT reads as an example placeholder to a model
# rather than a strict enum, so phases with an `importance` field get a
# blunt, unambiguous restatement of the allowed values.
_EXTRA_CONSTRAINTS = {
    "claim_extract": (
        'The "importance" field must be EXACTLY one of these three strings, nothing else: '
        '"critical", "major", "minor". The "claim_role" field must be EXACTLY one of '
        '"user_premise", "proposed_answer", "contextual". Use "user_premise" only for a '
        "claim that represents a premise in the user's question rather than a proposed answer."
    ),
    "verify": 'The "importance" field must be EXACTLY one of these three strings, nothing else: "critical", "major", "minor".',
}


def _build_prompt(phase: str, question: str, output_schema: dict[str, Any] | None = None) -> str:
    hint = _PHASE_SCHEMA_HINT.get(phase)
    if not hint:
        return question
    schema_text = json.dumps(output_schema or get_phase_schema(phase), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    parts = [
        question,
        "",
        "Respond with ONLY one JSON object that validates against this JSON Schema.\n" + schema_text,
    ]
    constraint = _EXTRA_CONSTRAINTS.get(phase)
    if constraint:
        parts.append(constraint)
    return "\n".join(parts)




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


class ClaudeAdapter:
    # SPEC §8.4 per-agent-per-call timeout. `verify` is the only mode
    # Orchestrator implements today (`quick`/`strict` are blocked on J-3), so
    # this defaults to verify's 180s rather than being mode-aware yet.
    # Found via live metrics collection: the adapter previously hardcoded
    # 45s, well under SPEC's budget, and a single slow real response was
    # enough to trip TIMEOUT, burn both of the run-level retry budget (W-3),
    # and fail an otherwise-healthy run.
    def __init__(self, agent_id: str, model: str | None = None, timeout_s: int = 180) -> None:
        self.agent_id = agent_id
        self.model = model
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()
        self._probe_cache: ProbeResult | None = None

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
        if self._probe_cache is not None:
            return self._probe_cache
        cmd = ["claude", "--version"]
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
                self._probe_cache = ProbeResult("QUOTA_EXCEEDED")
                return self._probe_cache
            if res.returncode != 0:
                self._probe_cache = ProbeResult("EXECUTION_ERROR")
                return self._probe_cache
            cli_version = res.stdout.strip() or res.stderr.strip() or "unknown"
            caps = AgentCapabilities(
                adapter_family="claude-code",
                adapter_version="1.0",
                cli_version=cli_version,
                supported_phases=("respond", "claim_extract", "verify", "criticize", "synthesize", "audit"),
                supports_read_only=True,
                supports_no_tools=True,
            )
            self._probe_cache = ProbeResult("OK", caps)
            return self._probe_cache
        except FileNotFoundError:
            self._probe_cache = ProbeResult("COMMAND_NOT_FOUND")
            return self._probe_cache
        except subprocess.TimeoutExpired:
            self._probe_cache = ProbeResult("TIMEOUT")
            return self._probe_cache
        except Exception:
            self._probe_cache = ProbeResult("EXECUTION_ERROR")
            return self._probe_cache

    def execute(self, request: AgentRequest) -> AgentResult:
        # Probe first to ensure fail-closed logic
        probe_res = self.probe()
        if probe_res.status != "OK":
            raise AgentFailure(probe_res.status, f"Claude Agent {self.agent_id} is unavailable: {probe_res.status}")

        prompt = _build_prompt(request.phase, build_phase_input(request), request.output_schema)

        cmd = [
            "claude",
            "-p",
            "--tools",
            "",
            "--output-format",
            "json",
            "--no-session-persistence",
            "--safe-mode",
        ]
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
                input=prompt,
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
                    public_summary=execution_failure_summary(
                        request.phase, "subprocess_nonzero_exit"
                    ),
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
            # --output-format json always wraps the model's text in a CLI
            # metadata envelope; the phase JSON is inside envelope["result"].
            result_text = envelope.get("result", "") if isinstance(envelope, dict) else res.stdout
            try:
                output = validate_phase_output(request.phase, extract_json_object(result_text))
                return AgentResult(output, Usage(100, 20), process_exit_code=res.returncode)
            except AgentFailure as failure:
                # Schema validation raised in base.py has no access to the
                # subprocess result; the process itself exited 0 (S-8 §1.1).
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
            raise AgentFailure("COMMAND_NOT_FOUND", "claude command not found")
        except subprocess.TimeoutExpired as exc:
            raise AgentFailure("TIMEOUT", "claude command timed out") from exc
        except OSError as exc:
            raise AgentFailure(
                "EXECUTION_ERROR",
                str(exc),
                public_summary=execution_failure_summary(request.phase, "process_launch_failure"),
            ) from exc
        finally:
            _thread_local.adapter = None
            _thread_local.execution_id = None


# SPEC §10.2 X-1 SearchProvider Contract, X-2/X-3: confirmed live 2026-07-13
# that "WebSearch" is accepted as a --tools value, the empty temp cwd stays
# empty (no file writes / shell execution), the model can return structured
# url/title/snippet JSON, and every returned URL was independently
# fetchable via SafeHttpFetcher. Reuses AgentFailure's error_code vocabulary
# (classify_cli_error) rather than duplicating detection logic, then maps
# onto the SearchError codes X-1 defines.
_SEARCH_ERROR_MAP = {
    "AUTH_REQUIRED": "SEARCH_AUTH_REQUIRED",
    "QUOTA_EXCEEDED": "SEARCH_QUOTA_EXCEEDED",
    "RATE_LIMITED": "SEARCH_RATE_LIMITED",
    "COMMAND_NOT_FOUND": "SEARCH_UNAVAILABLE",
    "UNSUPPORTED_VERSION": "SEARCH_UNAVAILABLE",
    "UNSAFE_CAPABILITY": "SEARCH_UNAVAILABLE",
    "EXECUTION_ERROR": "SEARCH_UNAVAILABLE",
}

_SEARCH_PROMPT_TEMPLATE = (
    "Search the web for sources relevant to this query: {query!r}\n\n"
    "Respond with ONLY a single valid JSON object, no markdown code fences, "
    "no other text, matching this shape: "
    '{{"sources": [{{"url": "<string>", "title": "<string>", "snippet": "<string>"}}]}}. '
    "Include up to {limit} sources with real URLs found via search."
)


class CliSearchProvider:
    """SearchProvider (SPEC §10.2 X-1) backed by Claude Code's built-in
    WebSearch tool. Returns candidate URLs only — it never fetches document
    bodies itself. SafeHttpFetcher remains the sole component that opens an
    HTTP connection (S-1); Oracle Council must independently retrieve and
    verify each URL this returns before it counts as evidence (§10.1)."""

    def __init__(self, timeout_s: int = 180) -> None:
        self.timeout_s = timeout_s

    def search(self, query: str, limit: int) -> list[SearchResult]:
        prompt = _SEARCH_PROMPT_TEMPLATE.format(query=query, limit=limit)
        cmd = [
            "claude",
            "-p",
            "--tools",
            "WebSearch",
            "--output-format",
            "json",
            "--no-session-persistence",
            "--safe-mode",
        ]
        env = dict(os.environ)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                env=env,
                input=prompt,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise SearchError("SEARCH_UNAVAILABLE", "claude command not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise SearchError("SEARCH_TIMEOUT", "claude command timed out") from exc

        err_text = res.stderr + "\n" + res.stdout
        error_code = classify_cli_error(res.stdout, res.stderr)
        if error_code:
            raise SearchError(_SEARCH_ERROR_MAP.get(error_code, "SEARCH_UNAVAILABLE"), err_text)
        if res.returncode != 0:
            raise SearchError("SEARCH_UNAVAILABLE", err_text)

        try:
            envelope = json.loads(res.stdout.strip())
        except json.JSONDecodeError as exc:
            raise SearchError(
                "INVALID_SEARCH_RESPONSE", f"failed to parse CLI envelope: {res.stdout}"
            ) from exc
        result_text = envelope.get("result", "") if isinstance(envelope, dict) else res.stdout

        try:
            payload = extract_json_object(result_text)
        except json.JSONDecodeError as exc:
            raise SearchError(
                "INVALID_SEARCH_RESPONSE", f"no JSON object in model text: {result_text}"
            ) from exc

        raw_sources = payload.get("sources") if isinstance(payload, dict) else None
        if not isinstance(raw_sources, list):
            raise SearchError("INVALID_SEARCH_RESPONSE", "missing or invalid 'sources' array")

        retrieved_at = utc_now().isoformat()
        results: list[SearchResult] = []
        for rank, item in enumerate(raw_sources, start=1):
            if len(results) >= limit:
                break
            if not isinstance(item, dict) or not item.get("url"):
                continue  # skip a malformed entry rather than failing the whole search
            results.append(
                SearchResult(
                    url=item["url"],
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    rank=rank,
                    source="claude-code-websearch",
                    retrieved_at=retrieved_at,
                )
            )
        return results
