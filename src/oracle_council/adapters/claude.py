from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..models import AgentFailure, AgentRequest, AgentResult, Usage


class ClaudeAdapter:
    def __init__(self, agent_id: str, model: str | None = None) -> None:
        self.agent_id = agent_id
        self.model = model

    def probe(self) -> str:
        cmd = ["claude", "--version"]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
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

        cmd = [
            "claude",
            "-p",
            question,
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
                timeout=45,
                env=env,
                stdin=subprocess.DEVNULL,
                shell=False,
            )
            err_text = res.stderr + "\n" + res.stdout
            if "session limit" in err_text.lower() or "quota" in err_text.lower():
                raise AgentFailure("QUOTA_EXCEEDED", err_text)
            if "auth" in err_text.lower() or "login" in err_text.lower():
                raise AgentFailure("AUTH_REQUIRED", err_text)
            if res.returncode != 0:
                raise AgentFailure("EXECUTION_ERROR", err_text)

            try:
                output = json.loads(res.stdout.strip())
                return AgentResult(output, Usage(100, 20))
            except json.JSONDecodeError as exc:
                raise AgentFailure(
                    "INVALID_OUTPUT",
                    f"Failed to parse JSON: {res.stdout}",
                ) from exc

        except FileNotFoundError:
            raise AgentFailure("COMMAND_NOT_FOUND", "claude command not found")
        except subprocess.TimeoutExpired as exc:
            raise AgentFailure("TIMEOUT", "claude command timed out") from exc
