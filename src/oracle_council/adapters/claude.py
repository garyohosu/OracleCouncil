from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from ..models import AgentFailure, AgentRequest, AgentResult, SearchError, SearchResult, Usage, utc_now
from .base import classify_cli_error, validate_phase_output

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
        '"importance": "critical|major|minor", "status": "unverified", "text": "<string>"}]}'
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
    "claim_extract": 'The "importance" field must be EXACTLY one of these three strings, nothing else: "critical", "major", "minor".',
    "verify": 'The "importance" field must be EXACTLY one of these three strings, nothing else: "critical", "major", "minor".',
}


def _build_prompt(phase: str, question: str) -> str:
    hint = _PHASE_SCHEMA_HINT.get(phase)
    if not hint:
        return question
    parts = [
        question,
        "",
        "Respond with ONLY a single valid JSON object matching this shape, "
        f"no markdown code fences and no other text: {hint}",
    ]
    constraint = _EXTRA_CONSTRAINTS.get(phase)
    if constraint:
        parts.append(constraint)
    return "\n".join(parts)


def _extract_json_object(text: str) -> Any:
    """Parse a JSON object out of model text that may be wrapped in markdown
    fences or preceded/followed by prose despite the prompt instruction."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    brace_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(0))
    raise json.JSONDecodeError("no JSON object found", stripped, 0)


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

    def probe(self) -> str:
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
                return "QUOTA_EXCEEDED"
            if res.returncode != 0:
                return "EXECUTION_ERROR"
            return "OK"
        except FileNotFoundError:
            return "COMMAND_NOT_FOUND"
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        except Exception:
            return "EXECUTION_ERROR"

    def capabilities(self) -> dict[str, Any]:
        return {
            "supported_models": [self.model or "claude-3-5-sonnet"],
            "supports_read_only": True,
            "supports_no_tools": True,
        }

    def execute(self, request: AgentRequest) -> AgentResult:
        # Probe first to ensure fail-closed logic
        status = self.probe()
        if status != "OK":
            raise AgentFailure(status, f"Claude Agent {self.agent_id} is unavailable: {status}")

        question = request.payload.get("question", "")
        if not question:
            question = json.dumps(request.payload)
        prompt = _build_prompt(request.phase, question)

        cmd = [
            "claude",
            "-p",
            prompt,
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

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                env=env,
                stdin=subprocess.DEVNULL,
                shell=False,
            )
            err_text = res.stderr + "\n" + res.stdout
            error_code = classify_cli_error(res.stdout, res.stderr)
            if error_code:
                raise AgentFailure(error_code, err_text)
            if res.returncode != 0:
                raise AgentFailure("EXECUTION_ERROR", err_text)

            try:
                envelope = json.loads(res.stdout.strip())
            except json.JSONDecodeError as exc:
                raise AgentFailure(
                    "INVALID_OUTPUT", f"Failed to parse CLI envelope: {res.stdout}"
                ) from exc
            # --output-format json always wraps the model's text in a CLI
            # metadata envelope; the phase JSON is inside envelope["result"].
            result_text = envelope.get("result", "") if isinstance(envelope, dict) else res.stdout
            try:
                output = validate_phase_output(request.phase, _extract_json_object(result_text))
                return AgentResult(output, Usage(100, 20))
            except json.JSONDecodeError as exc:
                raise AgentFailure(
                    "INVALID_OUTPUT",
                    f"Failed to parse phase JSON from model text: {result_text}",
                ) from exc

        except FileNotFoundError:
            raise AgentFailure("COMMAND_NOT_FOUND", "claude command not found")
        except subprocess.TimeoutExpired as exc:
            raise AgentFailure("TIMEOUT", "claude command timed out") from exc


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
            prompt,
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
                stdin=subprocess.DEVNULL,
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
            payload = _extract_json_object(result_text)
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
