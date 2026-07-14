from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any

from ..models import AgentFailure, AgentRequest, AgentResult, Usage
from ..phase_schema import get_phase_schema
from .base import build_phase_input, classify_cli_error, execution_failure_summary, validate_phase_output


class CodexAdapter:
    def __init__(self, agent_id: str, model: str | None = None, timeout_s: int = 180) -> None:
        self.agent_id, self.model, self.timeout_s = agent_id, model, timeout_s

    def probe(self) -> str:
        try:
            res = subprocess.run(["codex.cmd" if os.name == "nt" else "codex", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, shell=False, stdin=subprocess.DEVNULL)
            text = res.stderr + "\n" + res.stdout
            if "session limit" in text.lower() or "limit" in text.lower(): return "QUOTA_EXCEEDED"
            return "OK" if res.returncode == 0 else "EXECUTION_ERROR"
        except FileNotFoundError: return "COMMAND_NOT_FOUND"
        except subprocess.TimeoutExpired: return "TIMEOUT"
        except Exception: return "EXECUTION_ERROR"

    def capabilities(self) -> dict[str, Any]:
        return {"supported_models": [self.model or "gpt-4"], "supports_read_only": True, "supports_no_tools": True}

    def execute(self, request: AgentRequest) -> AgentResult:
        status = self.probe()
        if status != "OK": raise AgentFailure(status, f"Codex Agent {self.agent_id} is unavailable: {status}")
        schema = request.output_schema or get_phase_schema(request.phase)
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream: json.dump(schema, stream)
            cmd = ["codex.cmd" if os.name == "nt" else "codex", "exec", "-s", "read-only", "--ephemeral", "--output-schema", path]
            if self.model: cmd.extend(["--model", self.model])
            cmd.append("-")
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout_s, env=dict(os.environ), input=build_phase_input(request), shell=False)
            err_text = res.stderr + "\n" + res.stdout
            error_code = classify_cli_error(res.stdout, res.stderr)
            if error_code: raise AgentFailure(error_code, err_text)
            if res.returncode != 0: raise AgentFailure("EXECUTION_ERROR", err_text, public_summary=execution_failure_summary(request.phase, "subprocess_nonzero_exit"))
            output = None
            for line in reversed(res.stdout.strip().splitlines()):
                if line.strip().startswith("{") and line.strip().endswith("}"):
                    try: output = json.loads(line); break
                    except json.JSONDecodeError: pass
            if output is None:
                try: output = json.loads(res.stdout.strip())
                except json.JSONDecodeError as exc: raise AgentFailure("INVALID_OUTPUT", "Failed to extract JSON", public_summary="malformed JSON") from exc
            return AgentResult(validate_phase_output(request.phase, output), Usage(100, 20))
        except OSError as exc:
            raise AgentFailure("EXECUTION_ERROR", str(exc), public_summary=execution_failure_summary(request.phase, "process_launch_failure")) from exc
        finally:
            try: os.unlink(path)
            except OSError: pass
