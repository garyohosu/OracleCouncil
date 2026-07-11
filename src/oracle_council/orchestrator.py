from __future__ import annotations

from itertools import count
from uuid import uuid4

from .budget import BudgetExceededError, TokenBudget
from .classification import classify, is_withheld
from .models import (
    AgentRequest,
    BudgetRequest,
    Claim,
    ResultClassification,
    RunEvent,
    RunResult,
    RunStatus,
)
from .storage import StorageBackend, StorageWriteError

# oracleExitCode (SPEC §13.4). Only the codes reachable from the phase-0
# flow are mapped here; input/environment stops (2/3) and cancel (130)
# join once the CLI layer exists.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WITHHELD = 4

_VERIFY_PHASES = ("respond", "respond", "claim_extract", "verify")
_PUBLISH_PHASES = ("criticize", "synthesize", "audit")


class Orchestrator:
    PHASES = _VERIFY_PHASES + _PUBLISH_PHASES

    def __init__(self, adapter, evidence_provider, budget: TokenBudget, storage: StorageBackend | None) -> None:
        self._adapter = adapter
        self._evidence_provider = evidence_provider
        self._budget = budget
        self._storage = storage

    def run_verify(self, question: str) -> RunResult:
        run_id = str(uuid4())
        sequence = count(1)
        state = _RunState(question)
        try:
            self._append(run_id, "run_created", {"mode": "verify"})
            for phase in _VERIFY_PHASES:
                failure = self._execute_phase(run_id, phase, sequence, state)
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

            for phase in _PUBLISH_PHASES:
                failure = self._execute_phase(run_id, phase, sequence, state)
                if failure is not None:
                    return failure

            if not state.auditor_approved or state.final_answer is None:
                return self._finish(
                    run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state, EXIT_FAILED
                )
            return self._finish(
                run_id,
                RunStatus.COMPLETED,
                classify(state.claims),
                state.final_answer,
                state,
                EXIT_OK,
            )
        except StorageWriteError:
            return RunResult(
                run_id, RunStatus.FAILED, ResultClassification.UNVERIFIED, None, state.calls, EXIT_FAILED
            )
        finally:
            self._budget.assert_settled()

    def _execute_phase(self, run_id: str, phase: str, sequence, state: _RunState) -> RunResult | None:
        execution_id = f"exec-{next(sequence)}"
        try:
            reservation = self._budget.reserve(BudgetRequest(run_id, execution_id, phase, 100, 20))
        except BudgetExceededError:
            return self._budget_failure(run_id, state)
        started = False
        try:
            started = True
            payload = {
                "question": state.question,
                "responses": state.responses,
                "claims": [c.__dict__ for c in state.claims],
                "evidence": state.evidence,
            }
            result = self._adapter.execute(AgentRequest(run_id, execution_id, phase, payload))
            state.calls += 1
            self._budget.commit(reservation.reservation_id, result.usage)
        except Exception:
            if started:
                self._budget.commit(reservation.reservation_id, None)
            else:
                self._budget.release(reservation.reservation_id)
            raise
        output = result.output
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
            state.auditor_approved = output.get("status") == "approved"
        self._append(run_id, "agent_execution_succeeded", {"phase": phase, "execution_id": execution_id})
        return None

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

    def _finish(self, run_id, status, classification, answer, state: _RunState, exit_code) -> RunResult:
        result = RunResult(run_id, status, classification, answer, state.calls, exit_code, state.claims)
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
        self.calls = 0
