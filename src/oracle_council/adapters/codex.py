from __future__ import annotations

import json
import os
import subprocess
import tempfile
import os
from typing import Any

from ..models import AgentFailure, AgentRequest, AgentResult, Usage
from .base import classify_cli_error, validate_phase_output

# SPEC §10.4 / §10.5 enums. Must match adapters/base.py's
# _CLAIM_IMPORTANCE_VALUES / _CLAIM_STATUS_VALUES exactly: a schema that
# omits the enum still produces syntactically valid JSON that Adapter-layer
# validation must then reject, but constraining it here means the model
# self-corrects instead of burning a call on a doomed response.
_CLAIM_IMPORTANCE_ENUM = ["critical", "major", "minor"]
_CLAIM_STATUS_ENUM = [
    "verified", "supported", "contradicted", "conflicting", "unverified", "not_applicable",
]


class CodexAdapter:
    def __init__(self, agent_id: str, model: str | None = None) -> None:
        self.agent_id = agent_id
        self.model = model

    def probe(self) -> str:
        cmd = ["codex.cmd" if os.name == "nt" else "codex", "--version"]
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
            "supported_models": [self.model or "gpt-4"],
            "supports_read_only": True,
            "supports_no_tools": True,
        }

    def execute(self, request: AgentRequest) -> AgentResult:
        # Probe first to ensure fail-closed logic
        status = self.probe()
        if status != "OK":
            raise AgentFailure(status, f"Codex Agent {self.agent_id} is unavailable: {status}")

        question = request.payload.get("question", "")
        if not question:
            question = json.dumps(request.payload)

        # Build schema to stabilize and strictly validate response structure
        schema = {}
        phase = request.phase
        if phase == "respond":
            schema = {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            }
        elif phase == "claim_extract":
            schema = {
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim_id": {"type": "string"},
                                "importance": {
                                    "type": "string",
                                    "enum": _CLAIM_IMPORTANCE_ENUM,
                                },
                                "status": {
                                    "type": "string",
                                    "enum": _CLAIM_STATUS_ENUM,
                                },
                                "text": {"type": "string"},
                            },
                            "required": ["claim_id", "importance", "status", "text"],
                        },
                    }
                },
                "required": ["claims"],
            }
        elif phase == "verify":
            schema = {
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim_id": {"type": "string"},
                                "importance": {
                                    "type": "string",
                                    "enum": _CLAIM_IMPORTANCE_ENUM,
                                },
                                "status": {
                                    "type": "string",
                                    "enum": _CLAIM_STATUS_ENUM,
                                },
                            },
                            "required": ["claim_id", "importance", "status"],
                        },
                    }
                },
                "required": ["claims"],
            }
        elif phase == "criticize":
            schema = {
                "type": "object",
                "properties": {"critique": {"type": "string"}},
                "required": ["critique"],
            }
        elif phase == "synthesize":
            schema = {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            }
        elif phase == "audit":
            schema = {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["approved", "changes_required", "blocked"],
                    },
                    "issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "issue_id": {"type": "string"},
                                "issue_type": {"type": "string"},
                                "severity": {"type": "string"},
                                # Not every issue references one specific claim,
                                # but OpenAI's strict structured-output mode
                                # requires every property to be listed in
                                # `required` once additionalProperties=false is
                                # set (added by _strict_schema below) — an
                                # optional field must be nullable instead of
                                # merely absent from `required`. Found live:
                                # omitting non-issue_id keys from `required`
                                # made every audit call fail with
                                # invalid_json_schema before the model ever ran.
                                "claim_id": {"type": ["string", "null"]},
                            },
                            "required": ["issue_id", "issue_type", "severity", "claim_id"],
                        },
                    },
                },
                "required": ["status", "issues"],
            }

        temp_schema_fd, temp_schema_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(temp_schema_fd, "w", encoding="utf-8") as f:
                json.dump(_strict_schema(schema), f)

            cmd = [
                "codex.cmd" if os.name == "nt" else "codex",
                "exec",
                question,
                "-s",
                "read-only",
                "--ephemeral",
                "--output-schema",
                temp_schema_path,
            ]
            if self.model:
                cmd.extend(["--model", self.model])

            env = dict(os.environ)

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
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

            stdout_text = res.stdout.strip()
            output = None
            lines = stdout_text.splitlines()
            for line in reversed(lines):
                line_str = line.strip()
                if line_str.startswith("{") and line_str.endswith("}"):
                    try:
                        output = json.loads(line_str)
                        break
                    except json.JSONDecodeError:
                        pass

            if output is None:
                try:
                    output = json.loads(stdout_text)
                except json.JSONDecodeError as exc:
                    raise AgentFailure(
                        "INVALID_OUTPUT",
                        f"Failed to extract JSON from: {stdout_text}",
                    ) from exc

            return AgentResult(validate_phase_output(request.phase, output), Usage(100, 20))

        finally:
            try:
                os.unlink(temp_schema_path)
            except OSError:
                pass


def _strict_schema(schema: dict) -> dict:
    """Codex response schemas require closed object shapes at every level."""
    if isinstance(schema, dict):
        result = {key: _strict_schema(value) for key, value in schema.items()}
        if result.get("type") == "object":
            result["additionalProperties"] = False
        return result
    if isinstance(schema, list):
        return [_strict_schema(value) for value in schema]
    return schema
