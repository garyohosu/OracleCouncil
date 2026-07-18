from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .assignment import InsufficientAgentsError, RegisteredAgent, plan_assignments
from .budget import TokenBudget
from .evidence import ManualEvidenceProvider, SafeHttpFetcher, WebEvidenceProvider
from .fakes import FakeEvidenceProvider
from .models import (
    AgentCapabilities,
    AgentFailure,
    AgentRequest,
    AgentResult,
    ProbeResult,
    RunResult,
    RunStatus,
    SearchError,
    Usage,
    safe_error_summary,
)
from .clarification import ClarificationEngine, ClarificationStopError
from .orchestrator import Orchestrator
from .adapters import AgyAdapter, CliSearchProvider, ClaudeAdapter, CodexAdapter, GrokAdapter
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

    def probe(self) -> ProbeResult:
        env_status = os.environ.get(f"ORACLE_MOCK_PROBE_{self.agent_id.upper()}")
        status = env_status or self.mock_status
        if status != "OK":
            return ProbeResult(status)
        caps = AgentCapabilities(
            adapter_family=self._capabilities.get("adapter_family", "fake-family"),
            adapter_version=self._capabilities.get("adapter_version", "1.0"),
            cli_version=self._capabilities.get("cli_version", "1.0"),
            supported_phases=tuple(self._capabilities.get("supported_phases", (
                "clarify", "respond", "claim_extract", "verify", "criticize", "synthesize", "audit"
            ))),
            supports_read_only=self._capabilities.get("supports_read_only", True),
            supports_no_tools=self._capabilities.get("supports_no_tools", True),
        )
        return ProbeResult("OK", caps)

    def execute(self, request: AgentRequest) -> AgentResult:
        probe_res = self.probe()
        if probe_res.status != "OK":
            raise AgentFailure(probe_res.status, f"Agent {self.agent_id} unavailable with status: {probe_res.status}")

        phase = request.phase
        if phase == "clarify":
            question = request.payload.get("question", "")
            status_val = os.environ.get("ORACLE_MOCK_CLARIFY_STATUS", "ready")
            return AgentResult(
                {
                    "status": status_val,
                    "refined_question": question,
                    "assumptions": [],
                    "questions": [],
                    "note": "mock clarification note" if status_val != "ready" else "",
                },
                Usage(100, 20),
            )
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
                            "claim_role": "proposed_answer",
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


def exit_stop(status: str, oracle_exit_code: int, message: str, use_json: bool) -> int:
    payload = {
        "schema_version": "1.0",
        "run_id": None,
        "status": status,
        "oracle_exit_code": oracle_exit_code,
        # Compatibility alias (S-8): schema 1.x keeps the old top-level name;
        # it is always identical to oracle_exit_code.
        "exit_code": oracle_exit_code,
        "message": message,
    }
    if use_json:
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    else:
        sys.stderr.write(f"Stop: {message} ({status})\n")
    return oracle_exit_code


_EVIDENCE_SUMMARY_KEYS = (
    "evidence_id",
    "claim_id",
    "url",
    "title",
    "source",
    "rank",
    "content_type",
    "retrieved_at",
    "excerpt",
)


_EVIDENCE_TEXT_SUMMARY_KEYS = set(_EVIDENCE_SUMMARY_KEYS) - {"rank"}

_PHASE_METRIC_KEYS = {
    "search_count",
    "candidate_count",
    "fetch_attempt_count",
    "fetch_success_count",
    "fetch_failure_count",
    "evidence_count",
    "target_claim_count",
    "claims_with_evidence_count",
    "search_error_codes",
    "fetch_error_codes",
}


def evidence_summary(item: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in _EVIDENCE_SUMMARY_KEYS:
        if key not in item:
            continue
        value = item[key]
        if key == "rank":
            if type(value) in (int, float):
                summary[key] = value
            continue
        if key == "excerpt":
            summary[key] = value[:400] if isinstance(value, str) else ""
        elif key in _EVIDENCE_TEXT_SUMMARY_KEYS:
            summary[key] = value if isinstance(value, str) else ""
        else:  # pragma: no cover - defensive for future summary keys.
            summary[key] = value
    return summary


def phase_metrics_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in metrics.items():
        if key not in _PHASE_METRIC_KEYS:
            continue
        if type(value) is int and value >= 0:
            summary[key] = value
        elif isinstance(value, dict):
            summary[key] = {
                str(code): count
                for code, count in value.items()
                if isinstance(code, str) and type(count) is int and count >= 0
            }
    return summary


def _web_evidence_error_code(result: RunResult) -> str | None:
    for phase in result.phases:
        if phase.phase == "evidence_collect" and phase.status and phase.status.value == "failed" and phase.error_code:
            return phase.error_code
    return None


def output_run_result(result: RunResult, use_json: bool) -> int:
    web_error_code = _web_evidence_error_code(result)
    if use_json:
        executions = [
            {
                "execution_id": execution.execution_id,
                "agent_id": execution.agent_id,
                "phase": execution.phase,
                "status": execution.status.value,
                # S-8: the child CLI's own OS exit code (null when no child
                # process ran); never Oracle Council's exit code, which only
                # appears at the top level as oracle_exit_code.
                "process_exit_code": execution.process_exit_code,
                "error_code": execution.error_code,
                "error_summary": safe_error_summary(execution.error_summary),
                "retry_of": execution.retry_of,
                "substitute_for": execution.substitute_for,
                "elapsed_ms": execution.elapsed_ms,
            }
            for execution in result.executions
        ]
        phases = [
            {
                "phase": phase.phase,
                "status": phase.status.value if phase.status else None,
                "success_count": phase.success_count,
                "error_code": phase.error_code,
                "error_summary": safe_error_summary(phase.error_summary),
                "outcome": phase.outcome,
                # Metrics collection (P-4 experiment plan): per-phase wall time,
                # not just pass/fail, so a slow phase can be told apart from a
                # failed one when comparing runs.
                "started_at": phase.started_at.isoformat() if phase.started_at else None,
                "finished_at": phase.finished_at.isoformat() if phase.finished_at else None,
                "elapsed_ms": (
                    int((phase.finished_at - phase.started_at).total_seconds() * 1000)
                    if phase.started_at and phase.finished_at
                    else None
                ),
                "metrics": phase_metrics_summary(phase.metrics),
            }
            for phase in result.phases
        ]
        status = "verification_unavailable" if web_error_code else result.status.value
        payload = {
            "schema_version": "1.0",
            "run_id": result.run_id,
            "status": status,
            "oracle_exit_code": result.oracle_exit_code,
            # Compatibility alias (S-8): schema 1.x keeps the old top-level
            # name; it is always identical to oracle_exit_code.
            "exit_code": result.oracle_exit_code,
            "mode": result.mode,
            "question": {
                "original": result.original_question,
                "refined": result.refined_question,
                "clarification_status": result.clarification_status,
                "assumptions": list(result.clarification_assumptions),
            },
            "participants": list(result.participants),
            "answer": {
                "text": result.final_answer,
                "result_classification": result.result_classification.value,
                "consensus_status": "not_applicable",
                "audit_status": result.audit_status,
                "external_verification": result.external_verification,
            },
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "importance": c.importance.value,
                    "status": c.status.value,
                    "claim_role": c.claim_role.value,
                    "text": c.text,
                }
                for c in result.claims
            ],
            "evidence": [evidence_summary(item) for item in result.evidence],
            "agent_call_count": result.call_count,
            "executions": executions,
            "phases": phases,
            "votes": [],
            "warnings": [],
            "errors": [],
            # O-5: the run metadata snapshot is the source of truth; timing
            # comes from it instead of being recomputed here.
            "metadata": result.metadata.to_dict() if result.metadata else None,
            "timing": {
                "started_at": result.metadata.created_at.isoformat() if result.metadata else None,
                "finished_at": (
                    (result.metadata.created_at + timedelta(milliseconds=result.metadata.elapsed_ms)).isoformat()
                    if result.metadata
                    else None
                ),
                "elapsed_ms": result.metadata.elapsed_ms if result.metadata else None,
            },
        }
        if web_error_code:
            payload["message"] = f"web evidence unavailable: {web_error_code}"
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    else:
        if web_error_code:
            sys.stderr.write(f"Stop: web evidence unavailable: {web_error_code} (verification_unavailable)\n")
            return result.oracle_exit_code
        if result.status in (RunStatus.COMPLETED, RunStatus.PARTIAL):
            if result.oracle_exit_code == 0:
                print(result.final_answer)
            elif result.oracle_exit_code == 4:
                print("Final Answer: [withheld] (回答保留)")
                print("Claims and Verification details:")
                for claim in result.claims:
                    print(f"- {claim.claim_id} ({claim.importance.value}): {claim.status.value}")
        else:
            sys.stderr.write(f"Failed with exit code {result.oracle_exit_code}\n")
    return result.oracle_exit_code


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

    if "unsupported_trigger" in args.question:
        return exit_stop("unsupported", 2, "サポートされていない質問です", args.json)

    if "safety_trigger" in args.question:
        return exit_stop("safety_blocked", 2, "安全上の理由からブロックされました", args.json)

    if "unavailable_trigger" in args.question:
        return exit_stop("verification_unavailable", 3, "検証機能が利用できません", args.json)

    if args.evidence_file and args.evidence_provider:
        return exit_stop(
            "configuration_error",
            3,
            "--evidence-file and --evidence-provider cannot be used together",
            args.json,
        )

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
            elif use_real and entry.get("adapter") == "grok":
                adapter = GrokAdapter(agent_id, entry.get("model"))
            elif use_real and entry.get("adapter") == "agy":
                adapter = AgyAdapter(agent_id, entry.get("model"))
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
            probe_res = agent.adapter.probe()
            probe_status = probe_res.status
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

    # Evidence provider selection. The historical behavior is preserved:
    # no option -> FakeEvidenceProvider, --evidence-file -> ManualEvidenceProvider.
    # cli-search is an explicit experimental path only.
    if args.evidence_file:
        try:
            with open(args.evidence_file, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
        except (OSError, json.JSONDecodeError) as e:
            return exit_stop("configuration_error", 3, f"evidence file unreadable: {e}", args.json)
        if isinstance(loaded, dict):
            evidence_provider = ManualEvidenceProvider(documents=loaded)
        elif isinstance(loaded, list):
            evidence_provider = ManualEvidenceProvider(default=loaded)
        else:
            return exit_stop(
                "configuration_error", 3, "evidence file must be a JSON object or array", args.json
            )
    elif args.evidence_provider == "cli-search":
        evidence_provider = WebEvidenceProvider(
            fetcher=SafeHttpFetcher(),
            searcher=CliSearchProvider(),
        )
    else:
        evidence_provider = FakeEvidenceProvider([{"evidence_id": "ev-1"}])

    orchestrator = Orchestrator(
        agents=available_agents,
        evidence_provider=evidence_provider,
        budget=TokenBudget(input_limit=10**6, output_limit=10**6),
        storage=storage,
        store_content=args.store_content,
    )

    if not args.json:
        sys.stderr.write("Starting Oracle Council...\n")
        if args.mode == "quick":
            sys.stderr.write("[1/4] 2 Agentが独立回答中...\n")
        else:
            # S-4.4: the total is computed from the same deterministic
            # pre-check Orchestrator itself runs, not a hardcoded guess -
            # it only becomes 8 when a critical ambiguity actually requires
            # the Clarifier Agent (QandA S-4.3); otherwise it stays 7,
            # unchanged from before S-4 existed.
            precheck = ClarificationEngine().inspect(args.question)
            total_calls = 8 if precheck.agent_required else 7
            sys.stderr.write(f"[1/{total_calls}] 質問を整理しています\n")

    try:
        result = orchestrator.run_verify(args.question, mode=args.mode)
        return output_run_result(result, args.json)
    except SearchError as e:
        return exit_stop(
            "verification_unavailable",
            3,
            f"web evidence unavailable: {e.code}",
            args.json,
        )
    except InsufficientAgentsError as e:
        return exit_stop("insufficient_agents", 3, str(e), args.json)
    except ClarificationStopError as e:
        return exit_stop(e.status, e.exit_code, str(e), args.json)
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

        probe_res = adapter.probe()
        status = probe_res.status
        caps = probe_res.capabilities

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
            probe_res = adapter.probe()
            status = probe_res.status
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
    # W-11: on Windows, stdout/stderr default to the system codepage (e.g.
    # cp932) instead of UTF-8 once redirected to a file/pipe, silently
    # corrupting every non-ASCII character in --json output. reconfigure()
    # is a no-op where streams are already UTF-8 (most non-Windows setups).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
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
    ask_parser.add_argument(
        "--evidence-file",
        default=None,
        help="JSON file with manual evidence (claim_id -> documents mapping, or a list)",
    )
    ask_parser.add_argument(
        "--evidence-provider",
        choices=["fake", "cli-search"],
        default=None,
        help=(
            "Evidence provider to use: fake, or experimental cli-search "
            "(uses Claude Code WebSearch)"
        ),
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
