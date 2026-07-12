from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from ..models import AgentFailure, AgentRequest, AgentResult, Usage
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
