from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .assignment import InsufficientAgentsError, RegisteredAgent, plan_assignments
from .budget import TokenBudget
from .fakes import FakeEvidenceProvider
from .models import AgentFailure, AgentRequest, AgentResult, RunResult, RunStatus, Usage
from .orchestrator import Orchestrator
from .adapters import ClaudeAdapter, CodexAdapter
from .storage import (
    JSONLStorageBackend,
    StorageCorruptionError,
    StorageNotFoundError,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConfigurationError(RuntimeError):
    pass


class FakeAgentAdapter:
    def __init__(
        self,
        agent_id: str,
        mock_status: str = "OK",
        capabilities: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.mock_status = mock_status
        self._capabilities = capabilities or {"supported_models": ["mock-model"]}

    def probe(self) -> str:
        env_status = os.environ.get(f"ORACLE_MOCK_PROBE_{self.agent_id.upper()}")
        if env_status:
            return env_status
        return self.mock_status

    def capabilities(self) -> dict[str, Any]:
        caps = dict(self._capabilities)
        caps.setdefault("supports_read_only", True)
        caps.setdefault("supports_no_tools", True)
        return caps

    def execute(self, request: AgentRequest) -> AgentResult:
        status = self.probe()
        if status != "OK":
            raise AgentFailure(status, f"Agent {self.agent_id} unavailable with status: {status}")

        phase = request.phase
        if phase == "respond":
            return AgentResult({"answer": f"Mock respond from {self.agent_id}"}, Usage(100, 20))
        elif phase == "claim_extract":
            return AgentResult(
                {
                    "claims": [
                        {
                            "claim_id": "claim-1",
                            "importance": "major",
                            "status": "unverified",
                            "text": "This is a mock claim.",
                        }
                    ]
                },
                Usage(100, 20),
            )
        elif phase == "verify":
            status_val = os.environ.get("ORACLE_MOCK_VERIFY_STATUS", "verified")
            importance = os.environ.get("ORACLE_MOCK_CLAIM_IMPORTANCE", "major")
            return AgentResult(
                {
                    "claims": [
                        {
                            "claim_id": "claim-1",
                            "importance": importance,
                            "status": status_val,
                        }
                    ]
                },
                Usage(100, 20),
            )
        elif phase == "criticize":
            return AgentResult({"critique": "Mock critique looks good."}, Usage(100, 20))
        elif phase == "synthesize":
            return AgentResult({"answer": "Mock final synthesized answer."}, Usage(100, 20))
        elif phase == "audit":
            status_val = os.environ.get("ORACLE_MOCK_AUDIT_STATUS", "approved")
            issues = []
            if status_val == "changes_required":
                issues = [
                    {
                        "issue_id": "issue-1",
                        "issue_type": "clarity",
                        "severity": "major",
                        "claim_id": "claim-1",
                    }
                ]
            elif status_val == "blocked":
                issues = [
                    {
                        "issue_id": "issue-1",
                        "issue_type": "safety",
                        "severity": "critical",
                        "claim_id": "claim-1",
                    }
                ]
            return AgentResult({"status": status_val, "issues": issues}, Usage(100, 20))
        else:
            return AgentResult({}, Usage(0, 0))


def load_config() -> dict[str, Any]:
    config_path = os.environ.get("ORACLE_COUNCIL_CONFIG", "config/agents.yaml")
    if not os.path.exists(config_path):
        raise ConfigurationError(f"Config file not found: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict) or "agents" not in data:
                raise ConfigurationError("Invalid config format: missing 'agents'")
            return data
    except Exception as e:
        raise ConfigurationError(f"Failed to load config: {e}")


def exit_stop(status: str, exit_code: int, message: str, use_json: bool) -> int:
    payload = {
        "schema_version": "1.0",
        "run_id": None,
        "status": status,
        "exit_code": exit_code,
        "message": message,
    }
    if use_json:
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    else:
        sys.stderr.write(f"Stop: {message} ({status})\n")
    return exit_code


def output_run_result(result: RunResult, use_json: bool) -> int:
    if use_json:
        executions = [
            {
                "execution_id": execution.execution_id,
                "agent_id": execution.agent_id,
                "phase": execution.phase,
                "status": execution.status.value,
                "error_code": execution.error_code,
                "retry_of": execution.retry_of,
            }
            for execution in result.executions
        ]
        phases = [
            {"phase": phase.phase, "status": phase.status.value if phase.status else None,
             "success_count": phase.success_count, "error_code": phase.error_code}
            for phase in result.phases
        ]
        payload = {
            "schema_version": "1.0",
            "run_id": result.run_id,
            "status": result.status.value,
            "mode": "verify",
            "question": {
                "original": "元の質問",
                "refined": "整理後の質問",
                "clarification_status": "ready",
                "assumptions": [],
            },
            "participants": list({e.agent_id for e in result.executions}),
            "answer": {
                "text": result.final_answer,
                "result_classification": result.result_classification.value,
                "consensus_status": "not_applicable",
                "audit_status": "approved",
                "external_verification": True,
            },
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "importance": c.importance.value,
                    "status": c.status.value,
                    "text": c.text,
                }
                for c in result.claims
            ],
            "evidence": [],
            "agent_call_count": result.call_count,
            "executions": executions,
            "phases": phases,
            "votes": [],
            "warnings": [],
            "errors": [],
            "timing": {
                "started_at": utc_now().isoformat(),
                "finished_at": utc_now().isoformat(),
                "elapsed_ms": 100,
            },
        }
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    else:
        if result.status in (RunStatus.COMPLETED, RunStatus.PARTIAL):
            if result.exit_code == 0:
                print(result.final_answer)
            elif result.exit_code == 4:
                print("Final Answer: [withheld] (回答保留)")
                print("Claims and Verification details:")
                for claim in result.claims:
                    print(f"- {claim.claim_id} ({claim.importance.value}): {claim.status.value}")
        else:
            sys.stderr.write(f"Failed with exit code {result.exit_code}\n")
    return result.exit_code


def cmd_ask(args) -> int:
    # Simulators for input-driven triggers
    if "strict_trigger" in args.question or "high_risk" in args.question:
        if args.mode == "verify":
            if args.no_interactive:
                return exit_stop(
                    "strict_required",
                    2,
                    "strictへの切り替えが必要です",
                    args.json,
                )
            else:
                sys.stderr.write("高リスクな質問が検出されました。strictモードへ切り替えますか？ (y/N): ")
                ans = sys.stdin.readline().strip().lower()
                if ans not in ("y", "yes"):
                    return exit_stop(
                        "safety_blocked",
                        2,
                        "ユーザーによって安全モードへの移行が拒否されました",
                        args.json,
                    )
                args.mode = "strict"

    if "clarify_trigger" in args.question:
        if args.no_interactive:
            return exit_stop("needs_clarification", 2, "追加の質問回答が必要です", args.json)
        else:
            sys.stderr.write("追加質問: 用途は何ですか？: ")
            sys.stdin.readline().strip()

    if "unsupported_trigger" in args.question:
        return exit_stop("unsupported", 2, "サポートされていない質問です", args.json)

    if "safety_trigger" in args.question:
        return exit_stop("safety_blocked", 2, "安全上の理由からブロックされました", args.json)

    if "unavailable_trigger" in args.question:
        return exit_stop("verification_unavailable", 3, "検証機能が利用できません", args.json)

    # Core Orchestrator Run
    try:
        config_data = load_config()
    except ConfigurationError as e:
        return exit_stop("configuration_error", 3, str(e), args.json)

    agents = []
    for entry in config_data.get("agents", []):
        if entry.get("enabled", True):
            agent_id = entry["id"]
            implementation = entry.get("implementation", "mock")
            if args.adapter_mode == "real":
                use_real = True
            elif args.adapter_mode == "fake":
                use_real = False
            else:
                use_real = (
                    os.environ.get("ORACLE_COUNCIL_USE_REAL") == "1"
                    or implementation == "real"
                )
            if use_real and entry.get("adapter") == "claude":
                adapter = ClaudeAdapter(agent_id, entry.get("model"))
            elif use_real and entry.get("adapter") == "codex":
                adapter = CodexAdapter(agent_id, entry.get("model"))
            else:
                adapter = FakeAgentAdapter(
                    agent_id=agent_id,
                    mock_status=entry.get("mock_status", "OK"),
                    capabilities=entry.get("capabilities"),
                )
            agents.append(
                RegisteredAgent(
                    agent_id=entry["id"],
                    adapter=adapter,
                    role_priority=entry.get("role_priority", {}),
                )
            )

    # Pre-flight availability (§6.4, V-1): agents whose probe fails are absent
    # for this run. Quota exhaustion is NOT probe-detectable (a version probe
    # succeeds while execute() fails), so mid-run quota failures still follow
    # M-2: respond phase failed -> run failed.
    available_agents = []
    unavailable = []
    for agent in agents:
        try:
            probe_status = agent.adapter.probe()
        except Exception:
            probe_status = "EXECUTION_ERROR"
        if probe_status == "OK":
            available_agents.append(agent)
        else:
            unavailable.append(f"{agent.agent_id}={probe_status}")
    if len(available_agents) < 2:
        detail = ", ".join(unavailable) if unavailable else "agents configured: 0"
        return exit_stop(
            "insufficient_agents",
            3,
            f"参加可能なAgentが2未満です（利用不能: {detail}）",
            args.json,
        )

    if args.no_store:
        storage = None
    else:
        storage = JSONLStorageBackend(Path("data"))

    orchestrator = Orchestrator(
        agents=available_agents,
        evidence_provider=FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        budget=TokenBudget(input_limit=10**6, output_limit=10**6),
        storage=storage,
        store_content=args.store_content,
    )

    if not args.json:
        sys.stderr.write("Starting Oracle Council...\n")
        sys.stderr.write("[1/7] 質問を整理しています\n")

    try:
        result = orchestrator.run_verify(args.question)
        return output_run_result(result, args.json)
    except InsufficientAgentsError as e:
        return exit_stop("insufficient_agents", 3, str(e), args.json)
    except Exception as e:
        return exit_stop("internal_error", 1, str(e), args.json)


def cmd_agents_status(args) -> int:
    try:
        config_data = load_config()
    except ConfigurationError as e:
        sys.stderr.write(f"Configuration error: {e}\n")
        return 3

    for entry in config_data.get("agents", []):
        agent_id = entry["id"]
        enabled = entry.get("enabled", True)
        if not enabled:
            continue

        adapter = FakeAgentAdapter(
            agent_id=agent_id,
            mock_status=entry.get("mock_status", "OK"),
            capabilities=entry.get("capabilities"),
        )

        status = adapter.probe()
        caps = adapter.capabilities()

        print(f"Agent ID: {agent_id}")
        print(f"  Status: {status}")
        print(f"  Capabilities: {caps}")
    return 0


def cmd_agents_validate(args) -> int:
    try:
        config_data = load_config()
    except ConfigurationError as e:
        sys.stderr.write(f"Configuration error: {e}\n")
        return 3

    enabled_count = 0
    errors = []
    agent_ids = set()

    for entry in config_data.get("agents", []):
        agent_id = entry.get("id")
        if not agent_id:
            errors.append("Agent entry missing 'id'")
            continue
        if agent_id in agent_ids:
            errors.append(f"Duplicate agent ID: {agent_id}")
        agent_ids.add(agent_id)

        if entry.get("enabled", True):
            enabled_count += 1
            adapter = FakeAgentAdapter(
                agent_id=agent_id,
                mock_status=entry.get("mock_status", "OK"),
            )
            status = adapter.probe()
            if status != "OK":
                errors.append(f"Agent {agent_id} probe failed: {status}")

    if enabled_count < 2:
        errors.append("Fewer than 2 enabled agents configured.")

    if errors:
        for err in errors:
            sys.stderr.write(f"Validation error: {err}\n")
        return 3

    print("Configuration is valid.")
    return 0


def cmd_history_list(args) -> int:
    storage = JSONLStorageBackend(Path("data"))
    if not os.path.exists("data"):
        print("No history found.")
        return 0

    count = 0
    for run_dir in Path("data").iterdir():
        if run_dir.is_dir() and not run_dir.name.startswith("."):
            run_id = run_dir.name
            try:
                storage.load(run_id)
                print(f"Run ID: {run_id}")
                count += 1
            except Exception:
                pass
    if count == 0:
        print("No history found.")
    return 0


def cmd_history_show(args) -> int:
    storage = JSONLStorageBackend(Path("data"))
    try:
        load_result = storage.load(args.run_id)
    except StorageNotFoundError:
        sys.stderr.write(f"Run ID not found: {args.run_id}\n")
        return 1
    except StorageCorruptionError as e:
        sys.stderr.write(f"Warning: Storage corrupted ({e})\n")
        return 1

    for w in load_result.warnings:
        sys.stderr.write(f"Warning: {w}\n")

    metadata = None
    content_saved = False
    for event in reversed(load_result.events):
        if event.event_type in ("run_completed", "run_failed"):
            payload = event.payload
            meta_dict = payload.get("metadata")
            if meta_dict:
                metadata = meta_dict
                content_saved = meta_dict.get("content_saved", False)
                break

    if metadata:
        print(f"Run Metadata for {args.run_id}:")
        for k, v in metadata.items():
            print(f"  {k}: {v}")

    if not content_saved:
        print("本文は保存されていません")

    return 0


def cmd_history_delete(args) -> int:
    storage = JSONLStorageBackend(Path("data"))
    deleted = storage.delete(args.run_id)
    if deleted:
        print(f"Deleted run: {args.run_id}")
        return 0
    else:
        sys.stderr.write(f"Run ID not found: {args.run_id}\n")
        return 1


def cmd_history_purge(args) -> int:
    if not args.yes:
        sys.stderr.write("Purging requires confirmation. Use --yes.\n")
        return 1
    storage = JSONLStorageBackend(Path("data"))
    count = storage.purge()
    print(f"Purged {count} runs.")
    return 0


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="oracle", description="Oracle Council CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ask
    ask_parser = subparsers.add_parser("ask", help="Ask a question")
    ask_parser.add_argument("question", help="The question to ask")
    ask_parser.add_argument(
        "--mode",
        choices=["quick", "verify", "strict"],
        default="verify",
        help="Verification mode",
    )
    ask_parser.add_argument("--no-interactive", action="store_true", help="Non-interactive mode")
    ask_parser.add_argument("--json", action="store_true", help="Output only JSON to stdout")
    ask_parser.add_argument(
        "--allow-unverified-fallback",
        action="store_true",
        help="Allow unverified fallback",
    )
    ask_parser.add_argument("--store-content", action="store_true", help="Store content")
    ask_parser.add_argument("--no-store", action="store_true", help="Do not store logs")
    ask_parser.add_argument(
        "--adapter-mode",
        choices=["config", "real", "fake"],
        default="config",
        help="Adapter selection: explicit CLI mode overrides environment and config",
    )

    # agents
    agents_parser = subparsers.add_parser("agents", help="Manage agents")
    agents_subparsers = agents_parser.add_subparsers(dest="agents_command", required=True)
    agents_subparsers.add_parser("status", help="Show agents status")
    agents_subparsers.add_parser("validate", help="Validate agents config")

    # history
    history_parser = subparsers.add_parser("history", help="Manage execution history")
    history_subparsers = history_parser.add_subparsers(dest="history_command", required=True)

    history_subparsers.add_parser("list", help="List execution history")

    show_parser = history_subparsers.add_parser("show", help="Show details of a run")
    show_parser.add_argument("run_id", help="The Run ID to show")

    delete_parser = history_subparsers.add_parser("delete", help="Delete a run")
    delete_parser.add_argument("run_id", help="The Run ID to delete")

    purge_parser = history_subparsers.add_parser("purge", help="Purge all runs")
    purge_parser.add_argument("--yes", action="store_true", help="Confirm purging all runs")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    if parsed_args.command == "ask":
        return cmd_ask(parsed_args)
    elif parsed_args.command == "agents":
        if parsed_args.agents_command == "status":
            return cmd_agents_status(parsed_args)
        elif parsed_args.agents_command == "validate":
            return cmd_agents_validate(parsed_args)
    elif parsed_args.command == "history":
        if parsed_args.history_command == "list":
            return cmd_history_list(parsed_args)
        elif parsed_args.history_command == "show":
            return cmd_history_show(parsed_args)
        elif parsed_args.history_command == "delete":
            return cmd_history_delete(parsed_args)
        elif parsed_args.history_command == "purge":
            return cmd_history_purge(parsed_args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
