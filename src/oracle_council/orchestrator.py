from __future__ import annotations

from copy import deepcopy
from itertools import count
from typing import Any, Sequence
from uuid import uuid4

from .assignment import (
    AssignmentPlan,
    ExecutionPlan,
    InsufficientAgentsError,
    RegisteredAgent,
    build_execution_plan,
)
from .budget import BudgetExceededError, TokenBudget
from .classification import classify, is_withheld
from .models import (
    AgentExecutionRecord,
    AgentExecutionStatus,
    AgentFailure,
    AgentRequest,
    AuditIssue,
    AuditIssueStatus,
    BudgetRequest,
    Claim,
    EvidenceCollectionResult,
    PhaseRecord,
    PhaseStatus,
    ResultClassification,
    RunEvent,
    RunMetadataRecord,
    RunResult,
    RunStatus,
    SearchError,
    safe_error_summary,
    safe_public_summary,
    utc_now,
)
from .storage import StorageBackend, StorageWriteError
from .phase_schema import get_phase_schema

# oracleExitCode (SPEC §13.4). Only the codes reachable from the phase-0
# flow are mapped here; the remaining input/environment stops and cancel
# join once the CLI layer exists.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INSUFFICIENT_AGENTS = 3
EXIT_VERIFICATION_UNAVAILABLE = 3
EXIT_WITHHELD = 4

_VERIFY_PHASES = ("respond", "respond", "claim_extract", "verify")
_PUBLISH_PHASES = ("criticize", "synthesize", "audit")

# SPEC §8.3: only transient timeouts and rate limits are retried, at most
# once per logical slot and twice per run. INVALID_OUTPUT recovery remains
# pending QandA L-3; substitution follows the immutable ExecutionPlan.
_RETRYABLE_ERROR_CODES = frozenset({"TIMEOUT", "RATE_LIMITED"})
_MAX_RUN_RETRIES = 2
_MAX_RUN_SUBSTITUTIONS = 1

_UNAVAILABLE_ERROR_CODES = frozenset(
    {"AUTH_REQUIRED", "QUOTA_EXCEEDED", "COMMAND_NOT_FOUND", "UNSUPPORTED_VERSION", "UNSAFE_CAPABILITY"}
)
_SUBSTITUTION_ERROR_CODES = _RETRYABLE_ERROR_CODES | _UNAVAILABLE_ERROR_CODES | frozenset({"EXECUTION_ERROR"})

_MINIMUM_SUCCESS = {
    "respond": 2,
    "claim_extract": 1,
    "evidence_collect": 1,
    "verify": 1,
    "criticize": 1,
    "synthesize": 1,
    "audit": 1,
}


def _execution_status(error_code: str) -> AgentExecutionStatus:
    if error_code == "TIMEOUT":
        return AgentExecutionStatus.TIMED_OUT
    if error_code in _UNAVAILABLE_ERROR_CODES:
        return AgentExecutionStatus.UNAVAILABLE
    return AgentExecutionStatus.FAILED


class Orchestrator:
    PHASES = _VERIFY_PHASES + _PUBLISH_PHASES

    def __init__(
        self,
        agents: Sequence[RegisteredAgent],
        evidence_provider,
        budget: TokenBudget,
        storage: StorageBackend | None,
        store_content: bool = False,
    ) -> None:
        self._agents = tuple(agents)
        self._evidence_provider = evidence_provider
        self._budget = budget
        self._storage = storage
        self._store_content = store_content

    def run_verify(self, question: str) -> RunResult:
        # Pre-flight (V-1): assignment failures such as insufficient_agents
        # stop before a Run exists, so nothing is persisted and the error
        # propagates to the CLI layer with its own status and exit code.
        run_id = str(uuid4())
        plan = build_execution_plan(run_id, self._agents)
        sequence = count(1)
        state = _RunState(question, plan)
        try:
            self._append(
                run_id,
                "run_created",
                {"mode": "verify", "participants": list(plan.participants)},
            )
            respond_index = 0
            for phase in _VERIFY_PHASES:
                slot_index = respond_index if phase == "respond" else 0
                if phase == "respond":
                    respond_index += 1
                failure = self._execute_phase(run_id, phase, slot_index, sequence, state)
                if failure is not None:
                    return failure

            # Stage 1 of §15.3: a withheld run terminates here. The remaining
            # phases are skipped, no synthesized answer ever exists, and the
            # run still counts as completed (withheld is not a failure).
            if is_withheld(state.claims):
                for phase in _PUBLISH_PHASES:
                    record = state.phase(run_id, phase)
                    record.status = PhaseStatus.SKIPPED
                    record.finished_at = utc_now()
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
                failure = self._execute_phase(run_id, phase, 0, sequence, state)
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
            failure = self._execute_phase(run_id, "synthesize", 0, sequence, state)
            if failure is not None:
                return failure
            self._append(run_id, "synthesis_revised", {})
            self._append(run_id, "reaudit_started", {})
            failure = self._execute_phase(run_id, "audit", 0, sequence, state)
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
                run_id=run_id,
                status=RunStatus.FAILED,
                result_classification=ResultClassification.UNVERIFIED,
                final_answer=None,
                call_count=state.calls,
                oracle_exit_code=EXIT_FAILED,
                evidence=_evidence_snapshot(state),
                participants=plan.participants,
            )
        finally:
            self._budget.assert_settled()

    def _execute_phase(
        self, run_id: str, phase: str, slot_index: int, sequence, state: _RunState
    ) -> RunResult | None:
        """Execute one logical slot using the immutable plan candidate order."""
        record = state.phase(run_id, phase)
        assignment = state.plan.assignment_for(phase, slot_index)
        agents_by_id = {agent.agent_id: agent for agent in self._agents}
        failed_slot_agents: set[str] = set()
        try:
            agent = self._select_initial_agent(phase, slot_index, assignment, state, agents_by_id)
        except InsufficientAgentsError:
            record.status = PhaseStatus.FAILED
            record.error_code = "MINIMUM_SUCCESS_NOT_MET"
            record.error_summary = _summary(phase, "MINIMUM_SUCCESS_NOT_MET")
            record.finished_at = utc_now()
            return self._finish(
                run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state, EXIT_FAILED
            )
        retry_of: str | None = None
        substitute_for: str | None = None
        slot_retry_used = False
        substitution_started = False
        while True:
            execution_id = f"exec-{next(sequence)}"
            try:
                result = self._attempt(
                    run_id, phase, agent, execution_id, retry_of, substitute_for, state
                )
            except BudgetExceededError:
                record.status = PhaseStatus.FAILED
                record.error_code = "BUDGET_EXCEEDED"
                record.error_summary = _summary(phase, "BUDGET_EXCEEDED")
                record.finished_at = utc_now()
                return self._budget_failure(run_id, state)
            except AgentFailure as failure:
                error_summary = _failure_summary(phase, failure)
                self._append(
                    run_id,
                    "agent_execution_failed",
                    {
                        "phase": phase,
                        "execution_id": execution_id,
                        "agent_id": agent.agent_id,
                        "error_code": failure.error_code,
                        "process_exit_code": getattr(failure, "process_exit_code", None),
                        **({"retry_of": retry_of} if retry_of else {}),
                        **({"substitute_for": substitute_for} if substitute_for else {}),
                    },
                )
                failed_slot_agents.add(agent.agent_id)
                if failure.error_code in _UNAVAILABLE_ERROR_CODES:
                    state.mark_run_unavailable(agent.agent_id, failure.error_code)
                can_retry = (
                    failure.error_code in _RETRYABLE_ERROR_CODES
                    and not slot_retry_used
                    and not substitution_started
                    and state.run_retries_used < _MAX_RUN_RETRIES
                )
                if can_retry:
                    state.run_retries_used += 1
                    slot_retry_used = True
                    retry_of = execution_id
                    substitute_for = None
                    continue
                substitute = None
                if failure.error_code in _SUBSTITUTION_ERROR_CODES:
                    substitute = self._select_substitute(
                        phase, slot_index, assignment, state, agents_by_id, failed_slot_agents
                    )
                if substitute is not None and not substitution_started:
                    state.run_substitutions_used += 1
                    substitution_started = True
                    self._append(
                        run_id,
                        "agent_substitute_selected",
                        {
                            "phase": phase,
                            "slot_index": slot_index,
                            "failed_execution_id": execution_id,
                            "original_agent_id": agent.agent_id,
                            "substitute_agent_id": substitute.agent_id,
                        },
                    )
                    agent = substitute
                    substitute_for = execution_id
                    retry_of = None
                    continue
                if failure.error_code in _SUBSTITUTION_ERROR_CODES:
                    self._append(
                        run_id,
                        "agent_substitution_unavailable",
                        {
                            "phase": phase,
                            "slot_index": slot_index,
                            "failed_execution_id": execution_id,
                            "original_agent_id": agent.agent_id,
                            "reason": "no_eligible_candidate_or_limit_used",
                        },
                    )
                record.status = PhaseStatus.FAILED
                record.error_code = failure.error_code
                record.error_summary = error_summary
                record.finished_at = utc_now()
                return self._finish(
                    run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state, EXIT_FAILED
                )
            record.success_count += 1
            # Set on every successful call, not just once: for multi-call
            # phases (respond needs 2; audit gets a second call on revision,
            # W-2) this naturally ends up as the *last* success's timestamp,
            # so elapsed_ms = this phase's own span, not "start of this
            # phase to end of the whole run." Found reviewing real metrics
            # (2026-07-13): every phase but the last showed a duration that
            # included every phase after it, because _finish()'s fallback
            # was the only place finished_at ever got set on success.
            record.finished_at = utc_now()
            try:
                self._apply_output(run_id, phase, result.output, state)
            except SearchError:
                self._append(
                    run_id,
                    "agent_execution_succeeded",
                    {
                        "phase": phase,
                        "execution_id": execution_id,
                        "agent_id": agent.agent_id,
                        "process_exit_code": getattr(result, "process_exit_code", None),
                        **({"retry_of": retry_of} if retry_of else {}),
                        **({"substitute_for": substitute_for} if substitute_for else {}),
                    },
                )
                return self._finish(
                    run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state,
                    EXIT_VERIFICATION_UNAVAILABLE,
                )
            self._append(
                run_id,
                "agent_execution_succeeded",
                {
                    "phase": phase,
                    "execution_id": execution_id,
                    "agent_id": agent.agent_id,
                    "process_exit_code": getattr(result, "process_exit_code", None),
                    **({"retry_of": retry_of} if retry_of else {}),
                    **({"substitute_for": substitute_for} if substitute_for else {}),
                },
            )
            if phase == "respond":
                state.successful_responder_ids.add(agent.agent_id)
            elif phase == "synthesize":
                state.current_synthesizer_agent_id = agent.agent_id
            elif phase == "audit":
                state.current_auditor_agent_id = agent.agent_id
            return None

    def _select_initial_agent(self, phase, slot_index, assignment, state, agents_by_id):
        candidates = [
            agents_by_id[agent_id]
            for agent_id in assignment.candidate_agent_ids
            if state.agent_status(agent_id) == "available"
        ]
        if phase == "respond" and slot_index == 1:
            candidates = [a for a in candidates if a.agent_id not in state.successful_responder_ids]
        if phase == "audit" and state.current_synthesizer_agent_id:
            candidates = [a for a in candidates if a.agent_id != state.current_synthesizer_agent_id]
        if phase == "synthesize" and state.current_synthesizer_agent_id:
            candidates.sort(key=lambda item: item.agent_id != state.current_synthesizer_agent_id)
        if phase == "audit" and state.current_auditor_agent_id:
            candidates.sort(key=lambda item: item.agent_id != state.current_auditor_agent_id)
        if phase == "synthesize":
            candidates = [
                a for a in candidates
                if any(
                    auditor.agent_id != a.agent_id and state.agent_status(auditor.agent_id) == "available"
                    for auditor in (agents_by_id[aid] for aid in state.plan.assignment_for("audit").candidate_agent_ids)
                )
            ]
        if not candidates:
            raise InsufficientAgentsError(f"no eligible agent for {phase} slot {slot_index}")
        return candidates[0]

    def _select_substitute(self, phase, slot_index, assignment, state, agents_by_id, failed_slot_agents):
        if state.run_substitutions_used >= _MAX_RUN_SUBSTITUTIONS:
            return None
        candidates = [
            agents_by_id[agent_id]
            for agent_id in assignment.candidate_agent_ids
            if agent_id not in failed_slot_agents
            and state.agent_status(agent_id) == "available"
        ]
        if phase == "respond":
            reserved = set(state.plan.assignment_for("respond", 0).candidate_agent_ids[:2])
            candidates = [
                a for a in candidates
                if a.agent_id not in state.successful_responder_ids
                and a.agent_id not in reserved
            ]
        if phase == "audit" and state.current_synthesizer_agent_id:
            candidates = [a for a in candidates if a.agent_id != state.current_synthesizer_agent_id]
        if phase == "synthesize":
            audit_ids = state.plan.assignment_for("audit").candidate_agent_ids
            candidates = [
                a for a in candidates
                if any(
                    aid != a.agent_id and state.agent_status(aid) == "available"
                    and aid not in failed_slot_agents
                    for aid in audit_ids
                )
            ]
        return candidates[0] if candidates else None

    def _attempt(self, run_id, phase, agent, execution_id, retry_of, substitute_for, state: _RunState):
        # Retry and substitution are separate executions and reservations (S-7).
        reservation = self._budget.reserve(BudgetRequest(run_id, execution_id, phase, 100, 20))
        started_at = utc_now()
        started = False
        try:
            started = True
            payload = {
                "question": state.question,
                "responses": state.responses,
                "claims": [c.__dict__ for c in state.claims],
                "evidence": state.evidence,
                "critique": state.critique,
                "final_answer": state.final_answer,
            }
            result = agent.adapter.execute(AgentRequest(run_id, execution_id, phase, payload, get_phase_schema(phase)))
            state.calls += 1
            self._budget.commit(reservation.reservation_id, result.usage)
            state.executions.append(
                self._execution_record(
                    run_id, phase, agent, execution_id, retry_of, substitute_for, started_at,
                    AgentExecutionStatus.SUCCEEDED,
                    process_exit_code=getattr(result, "process_exit_code", None),
                )
            )
            return result
        except AgentFailure as failure:
            # The call may have consumed provider resources: commit on the
            # safe side so the attempt still counts against the limits.
            state.calls += 1
            self._budget.commit(reservation.reservation_id, None)
            state.executions.append(
                self._execution_record(
                    run_id, phase, agent, execution_id, retry_of, substitute_for, started_at,
                    _execution_status(failure.error_code),
                    process_exit_code=getattr(failure, "process_exit_code", None),
                    error_code=failure.error_code,
                    error_summary=_failure_summary(phase, failure),
                    raw_diagnostic=str(failure) if self._store_content else None,
                )
            )
            raise
        except Exception:
            if started:
                state.calls += 1
                self._budget.commit(reservation.reservation_id, None)
            else:
                self._budget.release(reservation.reservation_id)
            raise

    def _execution_record(
        self, run_id, phase, agent, execution_id, retry_of, substitute_for, started_at, status,
        process_exit_code=None, error_code=None, error_summary=None, raw_diagnostic=None,
    ) -> AgentExecutionRecord:
        finished_at = utc_now()
        return AgentExecutionRecord(
            execution_id=execution_id,
            run_id=run_id,
            agent_id=agent.agent_id,
            phase=phase,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=_elapsed_ms(started_at, finished_at),
            process_exit_code=process_exit_code,
            error_code=error_code,
            error_summary=error_summary or (_summary(phase, error_code) if error_code else None),
            raw_diagnostic=raw_diagnostic,
            retry_of=retry_of,
            substitute_for=substitute_for,
        )

    def _apply_output(self, run_id: str, phase: str, output: dict, state: _RunState) -> None:
        if phase == "respond":
            state.responses.append(output)
        elif phase == "claim_extract":
            state.claims = tuple(Claim.from_dict(c) for c in output.get("claims", []))
            self._collect_evidence(run_id, state)
        elif phase == "verify":
            state.claims = _merge_verified_claims(state.claims, output.get("claims", []))
        elif phase == "criticize":
            state.critique = output.get("critique", "")
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

    def _finish(self, run_id, status, classification, answer, state: _RunState, oracle_exit_code) -> RunResult:
        finished_at = utc_now()
        for record in state.phases.values():
            if record.status is None:
                record.status = (
                    PhaseStatus.SUCCEEDED
                    if record.success_count >= record.minimum_success_count
                    else PhaseStatus.FAILED
                )
            if record.finished_at is None:
                record.finished_at = finished_at

        error_codes: list[str] = []
        for execution in state.executions:
            if execution.error_code and execution.error_code not in error_codes:
                error_codes.append(execution.error_code)
        for record in state.phases.values():
            if record.error_code and record.error_code not in error_codes:
                error_codes.append(record.error_code)

        # O-5: the snapshot fixed here is the source of truth; it is never
        # re-aggregated from the event log afterwards.
        metadata = RunMetadataRecord(
            run_id=run_id,
            created_at=state.created_at,
            mode="verify",
            status=status,
            result_classification=classification,
            consensus_status="not_applicable",
            participant_count=len(state.plan.participants),
            claim_count=len(state.claims),
            evidence_count=len(state.evidence),
            error_codes=tuple(error_codes),
            elapsed_ms=_elapsed_ms(state.created_at, finished_at),
            content_saved=self._store_content,
            oracle_exit_code=oracle_exit_code,
            participants=state.plan.participants,
        )
        result = RunResult(
            run_id=run_id,
            status=status,
            result_classification=classification,
            final_answer=answer,
            call_count=state.calls,
            oracle_exit_code=oracle_exit_code,
            claims=state.claims,
            audit_issues=tuple(state.issues),
            phases=tuple(state.phases.values()),
            executions=tuple(state.executions),
            metadata=metadata,
            evidence=_evidence_snapshot(state),
            participants=state.plan.participants,
        )
        self._append(
            run_id,
            f"run_{status.value}",
            {
                "status": status.value,
                "result_classification": classification.value,
                "metadata": metadata.to_dict(),
            },
        )
        return result

    def _append(self, run_id: str, event_type: str, payload: dict) -> None:
        if self._storage is not None:
            self._storage.append(run_id, RunEvent(run_id, event_type, payload))

    def _collect_evidence(self, run_id: str, state: "_RunState") -> None:
        record = state.phase(run_id, "evidence_collect")
        record.started_at = utc_now()
        try:
            claims = [c.__dict__ for c in state.claims]
            collect_with_metrics = getattr(self._evidence_provider, "collect_with_metrics", None)
            if callable(collect_with_metrics):
                result = collect_with_metrics(claims)
                detailed = True
            else:
                evidence = self._evidence_provider.collect(claims)
                result = EvidenceCollectionResult(
                    evidence=tuple(evidence),
                    metrics=_evidence_metrics(evidence_count=len(evidence)),
                )
                detailed = False
        except SearchError as error:
            metrics = _metrics_from_search_error(error)
            partial = getattr(error, "partial_evidence", ())
            state.evidence = [deepcopy(item) for item in partial]
            record.status = PhaseStatus.FAILED
            record.success_count = 0
            record.error_code = error.code
            record.error_summary = _summary("evidence_collect", error.code)
            record.metrics = metrics
            record.finished_at = utc_now()
            raise

        state.evidence = [dict(item) for item in result.evidence]
        metrics = _normalized_evidence_metrics(result.metrics, len(state.evidence))
        record.status = PhaseStatus.SUCCEEDED
        record.success_count = 1
        record.error_code = None
        record.error_summary = None
        record.metrics = metrics
        record.outcome = _evidence_outcome(metrics, detailed)
        record.finished_at = utc_now()


def _elapsed_ms(started_at, finished_at) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


def _summary(phase: str, error_code: str) -> str:
    """Fixed template only (SPEC §15.8): never raw stderr, exception text,
    question fragments, or paths. Bounded well under the 200-char limit."""
    return f"{phase} execution ended with {error_code}."[:200]


def _failure_summary(phase: str, failure: AgentFailure) -> str:
    public_summary = getattr(failure, "public_summary", None)
    if failure.error_code == "EXECUTION_ERROR":
        if (
            isinstance(public_summary, str)
            and public_summary.startswith(f"{phase} ")
            and safe_error_summary(public_summary) == public_summary
        ):
            return public_summary
        return _summary(phase, failure.error_code)
    if failure.error_code == "INVALID_OUTPUT" and public_summary:
        detail = safe_public_summary(public_summary)
        if detail:
            return f"{phase} invalid output: {detail}."[:200]
    return _summary(phase, failure.error_code)


def _evidence_snapshot(state: "_RunState") -> tuple[dict, ...]:
    return tuple(deepcopy(item) for item in state.evidence)


def _merge_verified_claims(existing: tuple[Claim, ...], verified: list[dict]) -> tuple[Claim, ...]:
    if not existing:
        return tuple(Claim.from_dict(item) for item in verified)
    by_id = {
        item.get("claim_id"): item
        for item in verified
        if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
    }
    consumed: set[int] = set()
    merged: list[Claim] = []
    for index, claim in enumerate(existing):
        raw = by_id.get(claim.claim_id)
        if raw is not None:
            consumed.add(verified.index(raw))
        if raw is None and index < len(verified) and isinstance(verified[index], dict):
            raw = verified[index]
            consumed.add(index)
        if raw is None:
            merged.append(claim)
            continue
        merged.append(
            Claim.from_dict(
                {
                    "claim_id": claim.claim_id,
                    "importance": raw.get("importance", claim.importance.value),
                    "status": raw.get("status", claim.status.value),
                    "text": raw.get("text") if raw.get("text") else claim.text,
                    "claim_role": raw.get("claim_role", claim.claim_role.value),
                }
            )
        )
    for index, raw in enumerate(verified):
        if index not in consumed and isinstance(raw, dict):
            merged.append(Claim.from_dict(raw))
    return tuple(merged)


def _evidence_metrics(evidence_count: int = 0) -> dict[str, Any]:
    return {
        "search_count": 0,
        "candidate_count": 0,
        "fetch_attempt_count": 0,
        "fetch_success_count": 0,
        "fetch_failure_count": 0,
        "evidence_count": evidence_count,
        "target_claim_count": 0,
        "claims_with_evidence_count": 0,
        "search_error_codes": {},
        "fetch_error_codes": {},
    }


def _normalized_evidence_metrics(metrics: dict[str, Any], evidence_count: int) -> dict[str, Any]:
    normalized = _evidence_metrics(evidence_count=evidence_count)
    for key in (
        "search_count",
        "candidate_count",
        "fetch_attempt_count",
        "fetch_success_count",
        "fetch_failure_count",
        "evidence_count",
        "target_claim_count",
        "claims_with_evidence_count",
    ):
        value = metrics.get(key, normalized[key])
        normalized[key] = value if type(value) is int and value >= 0 else normalized[key]
    for key in ("search_error_codes", "fetch_error_codes"):
        value = metrics.get(key, {})
        if isinstance(value, dict):
            normalized[key] = {
                str(code): count
                for code, count in value.items()
                if isinstance(code, str) and type(count) is int and count >= 0
            }
    normalized["evidence_count"] = evidence_count
    return normalized


def _metrics_from_search_error(error: SearchError) -> dict[str, Any]:
    partial = getattr(error, "partial_evidence", ())
    metrics = _normalized_evidence_metrics(getattr(error, "evidence_metrics", {}), len(partial))
    codes = metrics["search_error_codes"]
    if not codes.get(error.code):
        codes[error.code] = 1
    return metrics


def _evidence_outcome(metrics: dict[str, Any], detailed: bool) -> str:
    evidence_count = metrics["evidence_count"]
    if evidence_count == 0:
        return "no_evidence"
    if not detailed:
        return "evidence_found"
    if (
        metrics["fetch_failure_count"] > 0
        or metrics["claims_with_evidence_count"] < metrics["target_claim_count"]
    ):
        return "partial_evidence"
    return "evidence_found"


class _RunState:
    def __init__(self, question: str, plan: ExecutionPlan) -> None:
        self.question = question
        self.plan = plan
        self.created_at = utc_now()
        self.responses: list[dict] = []
        self.claims: tuple[Claim, ...] = ()
        self.evidence: list[dict] = []
        self.critique = ""
        self.final_answer: str | None = None
        self.auditor_approved = False
        self.audit_status: str | None = None
        self.last_audit_issues: list[dict] = []
        self.issues: list[AuditIssue] = []
        self.calls = 0
        self.run_retries_used = 0
        self.run_substitutions_used = 0
        self.agent_availability = {item.agent_id: item for item in plan.agent_availability}
        self.successful_responder_ids: set[str] = set()
        self.current_synthesizer_agent_id: str | None = None
        self.current_auditor_agent_id: str | None = None
        self.phases: dict[str, PhaseRecord] = {}
        self.executions: list[AgentExecutionRecord] = []

    def phase(self, run_id: str, name: str) -> PhaseRecord:
        if name not in self.phases:
            self.phases[name] = PhaseRecord(
                phase_id=f"phase-{len(self.phases) + 1}",
                run_id=run_id,
                phase=name,
                minimum_success_count=_MINIMUM_SUCCESS.get(name, 1),
                started_at=utc_now(),
            )
        return self.phases[name]

    def agent_status(self, agent_id: str) -> str:
        return self.agent_availability[agent_id].status

    def mark_run_unavailable(self, agent_id: str, reason_code: str) -> None:
        from .assignment import RunAgentAvailability

        self.agent_availability[agent_id] = RunAgentAvailability(
            agent_id=agent_id, status="run_unavailable", reason_code=reason_code
        )


__all__ = [
    "AssignmentPlan",
    "EXIT_FAILED",
    "EXIT_INSUFFICIENT_AGENTS",
    "EXIT_OK",
    "EXIT_WITHHELD",
    "Orchestrator",
    "RegisteredAgent",
]
