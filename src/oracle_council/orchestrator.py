from __future__ import annotations

from itertools import count
from typing import Sequence
from uuid import uuid4

from .assignment import AssignmentPlan, RegisteredAgent, plan_assignments
from .budget import BudgetExceededError, TokenBudget
from .classification import classify, is_withheld
from .models import (
    AgentFailure,
    AgentRequest,
    AuditIssue,
    AuditIssueStatus,
    BudgetRequest,
    Claim,
    ResultClassification,
    RunEvent,
    RunResult,
    RunStatus,
)
from .storage import StorageBackend, StorageWriteError

# oracleExitCode (SPEC §13.4). Only the codes reachable from the phase-0
# flow are mapped here; the remaining input/environment stops and cancel
# join once the CLI layer exists.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INSUFFICIENT_AGENTS = 3
EXIT_WITHHELD = 4

_VERIFY_PHASES = ("respond", "respond", "claim_extract", "verify")
_PUBLISH_PHASES = ("criticize", "synthesize", "audit")

# SPEC §8.3: only transient timeouts and rate limits are retried, at most
# once per execution and twice per run. INVALID_OUTPUT recovery is pending
# QandA L-3 and substitute-agent selection is pending M-5, so every other
# failure terminates the run deterministically.
_RETRYABLE_ERROR_CODES = frozenset({"TIMEOUT", "RATE_LIMITED"})
_MAX_RUN_RETRIES = 2


class Orchestrator:
    PHASES = _VERIFY_PHASES + _PUBLISH_PHASES

    def __init__(
        self,
        agents: Sequence[RegisteredAgent],
        evidence_provider,
        budget: TokenBudget,
        storage: StorageBackend | None,
    ) -> None:
        self._agents = tuple(agents)
        self._evidence_provider = evidence_provider
        self._budget = budget
        self._storage = storage

    def run_verify(self, question: str) -> RunResult:
        # Pre-flight (V-1): assignment failures such as insufficient_agents
        # stop before a Run exists, so nothing is persisted and the error
        # propagates to the CLI layer with its own status and exit code.
        plan = plan_assignments(self._agents)

        run_id = str(uuid4())
        sequence = count(1)
        state = _RunState(question)
        try:
            self._append(
                run_id,
                "run_created",
                {"mode": "verify", "participants": [a.agent_id for a in self._agents]},
            )
            respond_index = 0
            for phase in _VERIFY_PHASES:
                agent = plan.adapter_for(phase, respond_index)
                if phase == "respond":
                    respond_index += 1
                failure = self._execute_phase(run_id, phase, agent, sequence, state)
                if failure is not None:
                    return failure

            # Stage 1 of §15.3: a withheld run terminates here. The remaining
            # phases are skipped, no synthesized answer ever exists, and the
            # run still counts as completed (withheld is not a failure).
            if is_withheld(state.claims):
                for phase in _PUBLISH_PHASES:
                    self._append(run_id, "phase_skipped", {"phase": phase, "reason": "withheld"})
                return self._finish(
                    run_id,
                    RunStatus.COMPLETED,
                    ResultClassification.WITHHELD,
                    None,
                    state,
                    EXIT_WITHHELD,
                )

            for phase in ("criticize", "synthesize", "audit"):
                failure = self._execute_phase(
                    run_id, phase, plan.adapter_for(phase), sequence, state
                )
                if failure is not None:
                    return failure
            state.issues = [
                AuditIssue(
                    issue_id=raw.get("issue_id", f"issue-{index}"),
                    issue_type=raw.get("issue_type", ""),
                    severity=raw.get("severity", ""),
                    claim_id=raw.get("claim_id"),
                )
                for index, raw in enumerate(state.last_audit_issues, start=1)
            ]

            # Audit gate (§11.1, W-2): approved publishes, an initial blocked
            # withholds immediately, changes_required earns exactly one
            # revision cycle with the same synthesizer and auditor.
            if state.audit_status == "approved":
                return self._publish(run_id, state)
            if state.audit_status != "changes_required":
                return self._withheld_by_audit(run_id, state)

            self._append(
                run_id,
                "revision_started",
                {"reason": "changes_required", "open_issues": [i.issue_id for i in state.issues]},
            )
            failure = self._execute_phase(
                run_id, "synthesize", plan.adapter_for("synthesize"), sequence, state
            )
            if failure is not None:
                return failure
            self._append(run_id, "synthesis_revised", {})
            self._append(run_id, "reaudit_started", {})
            failure = self._execute_phase(
                run_id, "audit", plan.adapter_for("audit"), sequence, state
            )
            if failure is not None:
                return failure
            self._append(run_id, "reaudit_completed", {"status": state.audit_status})

            reported = {raw.get("issue_id") for raw in state.last_audit_issues}
            for issue in state.issues:
                if state.audit_status == "approved" or issue.issue_id not in reported:
                    issue.status = AuditIssueStatus.RESOLVED

            if state.audit_status == "approved":
                return self._publish(run_id, state)
            return self._withheld_by_audit(run_id, state)
        except StorageWriteError:
            return RunResult(
                run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state.calls, EXIT_FAILED
            )
        finally:
            self._budget.assert_settled()

    def _execute_phase(
        self, run_id: str, phase: str, agent: RegisteredAgent, sequence, state: _RunState
    ) -> RunResult | None:
        """Run one phase with at most one retry (SPEC §8.3). Returns a terminal
        RunResult on failure, or None when the phase succeeded."""
        retry_of: str | None = None
        while True:
            execution_id = f"exec-{next(sequence)}"
            try:
                result = self._attempt(run_id, phase, agent, execution_id, retry_of, state)
            except BudgetExceededError:
                return self._budget_failure(run_id, state)
            except AgentFailure as failure:
                self._append(
                    run_id,
                    "agent_execution_failed",
                    {
                        "phase": phase,
                        "execution_id": execution_id,
                        "agent_id": agent.agent_id,
                        "error_code": failure.error_code,
                        **({"retry_of": retry_of} if retry_of else {}),
                    },
                )
                can_retry = (
                    failure.error_code in _RETRYABLE_ERROR_CODES
                    and retry_of is None  # at most one retry per execution
                    and state.run_retries_used < _MAX_RUN_RETRIES
                )
                if can_retry:
                    state.run_retries_used += 1
                    retry_of = execution_id
                    continue
                return self._finish(
                    run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state, EXIT_FAILED
                )
            self._apply_output(phase, result.output, state)
            self._append(
                run_id,
                "agent_execution_succeeded",
                {
                    "phase": phase,
                    "execution_id": execution_id,
                    "agent_id": agent.agent_id,
                    **({"retry_of": retry_of} if retry_of else {}),
                },
            )
            return None

    def _attempt(self, run_id, phase, agent, execution_id, retry_of, state: _RunState):
        # A retry is a new execution with its own reservation (S-7).
        reservation = self._budget.reserve(BudgetRequest(run_id, execution_id, phase, 100, 20))
        started = False
        try:
            started = True
            payload = {
                "question": state.question,
                "responses": state.responses,
                "claims": [c.__dict__ for c in state.claims],
                "evidence": state.evidence,
            }
            result = agent.adapter.execute(AgentRequest(run_id, execution_id, phase, payload))
            state.calls += 1
            self._budget.commit(reservation.reservation_id, result.usage)
            return result
        except Exception:
            if started:
                # The call may have consumed provider resources: commit on the
                # safe side so the attempt still counts against the limits.
                state.calls += 1
                self._budget.commit(reservation.reservation_id, None)
            else:
                self._budget.release(reservation.reservation_id)
            raise

    def _apply_output(self, phase: str, output: dict, state: _RunState) -> None:
        if phase == "respond":
            state.responses.append(output)
        elif phase == "claim_extract":
            state.claims = tuple(Claim.from_dict(c) for c in output.get("claims", []))
            state.evidence = self._evidence_provider.collect([c.__dict__ for c in state.claims])
        elif phase == "verify":
            state.claims = tuple(Claim.from_dict(c) for c in output.get("claims", []))
        elif phase == "synthesize":
            state.final_answer = output["answer"]
        elif phase == "audit":
            state.audit_status = output.get("status")
            state.auditor_approved = state.audit_status == "approved"
            state.last_audit_issues = output.get("issues", [])

    def _budget_failure(self, run_id: str, state: _RunState) -> RunResult:
        self._append(run_id, "budget_exceeded", {"error_code": "BUDGET_EXCEEDED"})
        if state.auditor_approved and state.final_answer is not None:
            return self._finish(
                run_id,
                RunStatus.PARTIAL,
                ResultClassification.PARTIALLY_VERIFIED,
                state.final_answer,
                state,
                EXIT_OK,
            )
        return self._finish(
            run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state, EXIT_FAILED
        )

    def _publish(self, run_id: str, state: _RunState) -> RunResult:
        if state.final_answer is None:
            return self._finish(
                run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state, EXIT_FAILED
            )
        for issue in state.issues:
            issue.status = AuditIssueStatus.RESOLVED
        return self._finish(
            run_id,
            RunStatus.COMPLETED,
            classify(state.claims),
            state.final_answer,
            state,
            EXIT_OK,
        )

    def _withheld_by_audit(self, run_id: str, state: _RunState) -> RunResult:
        # W-2: an unapproved answer is withheld, not failed. The synthesized
        # text stays unpublished; only claim results (§11.5) are disclosed.
        return self._finish(
            run_id,
            RunStatus.COMPLETED,
            ResultClassification.WITHHELD,
            None,
            state,
            EXIT_WITHHELD,
        )

    def _finish(self, run_id, status, classification, answer, state: _RunState, exit_code) -> RunResult:
        result = RunResult(
            run_id, status, classification, answer, state.calls, exit_code, state.claims, tuple(state.issues)
        )
        self._append(
            run_id,
            f"run_{status.value}",
            {"status": status.value, "result_classification": classification.value},
        )
        return result

    def _append(self, run_id: str, event_type: str, payload: dict) -> None:
        if self._storage is not None:
            self._storage.append(run_id, RunEvent(run_id, event_type, payload))


class _RunState:
    def __init__(self, question: str) -> None:
        self.question = question
        self.responses: list[dict] = []
        self.claims: tuple[Claim, ...] = ()
        self.evidence: list[dict] = []
        self.final_answer: str | None = None
        self.auditor_approved = False
        self.audit_status: str | None = None
        self.last_audit_issues: list[dict] = []
        self.issues: list[AuditIssue] = []
        self.calls = 0
        self.run_retries_used = 0


__all__ = [
    "AssignmentPlan",
    "EXIT_FAILED",
    "EXIT_INSUFFICIENT_AGENTS",
    "EXIT_OK",
    "EXIT_WITHHELD",
    "Orchestrator",
    "RegisteredAgent",
]
