import pytest

from oracle_council.assignment import InsufficientAgentsError, RegisteredAgent
from oracle_council.budget import TokenBudget
from oracle_council.fakes import FakeEvidenceProvider, ScriptedAgentAdapter
from oracle_council.models import AgentFailure, ResultClassification, RunStatus
from oracle_council.orchestrator import EXIT_FAILED, EXIT_OK, EXIT_WITHHELD, Orchestrator
from oracle_council.storage import InMemoryStorageBackend


def build_raw(a_script, b_script, budget=None, storage=None, store_content=False):
    adapter_a = ScriptedAgentAdapter(a_script)
    adapter_b = ScriptedAgentAdapter(b_script)
    orchestrator = Orchestrator(
        [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)],
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        budget or TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
        store_content=store_content,
    )
    return orchestrator, adapter_a, adapter_b


def claims_output(status, importance="major"):
    return {"claims": [{"claim_id": "claim-1", "importance": importance, "status": status}]}


def build(
    verify_status="verified",
    importance="major",
    audits=None,
    verify_claims=None,
    budget=None,
    storage=None,
):
    """Two agents: config order assigns agent-a everything except audit (agent-b).

    `audits` is the sequence of audit outputs; a second entry feeds the re-audit.
    """
    adapter_a = ScriptedAgentAdapter(
        [
            {"answer": "A"},  # respond #1
            claims_output("unverified", importance),  # claim_extract
            verify_claims or claims_output(verify_status, importance),  # verify
            {"critique": "ok"},  # criticize
            {"answer": "final"},  # synthesize
            {"answer": "final-v2"},  # synthesize (revision, if reached)
        ]
    )
    adapter_b = ScriptedAgentAdapter(
        [{"answer": "B"}] + list(audits or [{"status": "approved"}])  # respond #2, audit(s)
    )
    orchestrator = Orchestrator(
        [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)],
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        budget or TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
    )
    return orchestrator, adapter_a, adapter_b


def test_verify_happy_path_makes_seven_calls_across_two_agents():
    storage = InMemoryStorageBackend()
    orchestrator, adapter_a, adapter_b = build(storage=storage)

    result = orchestrator.run_verify("富士山の標高は？")

    assert [r.phase for r in adapter_a.requests] == [
        "respond", "claim_extract", "verify", "criticize", "synthesize",
    ]
    assert [r.phase for r in adapter_b.requests] == ["respond", "audit"]
    assert result.call_count == 7
    assert result.status is RunStatus.COMPLETED
    assert result.result_classification is ResultClassification.VERIFIED
    assert result.final_answer == "final"
    assert result.exit_code == EXIT_OK

    events = storage.load(result.run_id).events
    assert events[0].event_type == "run_created"
    assert events[0].payload["participants"] == ["agent-a", "agent-b"]
    assert events[-1].event_type == "run_completed"
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))

    by_phase = {
        e.payload["phase"]: e.payload["agent_id"]
        for e in events
        if e.event_type == "agent_execution_succeeded" and e.payload["phase"] != "respond"
    }
    assert by_phase["synthesize"] != by_phase["audit"]  # §6.3: separate auditor
    responders = [
        e.payload["agent_id"]
        for e in events
        if e.event_type == "agent_execution_succeeded" and e.payload["phase"] == "respond"
    ]
    assert len(set(responders)) == 2  # §6.3: two distinct responders


def test_critical_unverified_withholds_after_four_calls():
    storage = InMemoryStorageBackend()
    orchestrator, adapter_a, adapter_b = build(
        verify_status="unverified", importance="critical", storage=storage
    )

    result = orchestrator.run_verify("この薬の服用量は？")

    assert result.call_count == 4  # respond x2, claim_extract, verify
    assert [r.phase for r in adapter_a.requests] == ["respond", "claim_extract", "verify"]
    assert [r.phase for r in adapter_b.requests] == ["respond"]
    assert result.status is RunStatus.COMPLETED  # withheld is not a failure
    assert result.result_classification is ResultClassification.WITHHELD
    assert result.final_answer is None  # no synthesized answer ever exists
    assert result.exit_code == EXIT_WITHHELD
    assert result.claims[0].status.value == "unverified"  # U-1: claim results stay disclosable

    events = storage.load(result.run_id).events
    skipped = [e.payload["phase"] for e in events if e.event_type == "phase_skipped"]
    assert skipped == ["criticize", "synthesize", "audit"]
    assert events[-1].event_type == "run_completed"


def test_major_contradicted_also_withholds():
    orchestrator, _, _ = build(verify_status="contradicted", importance="major")
    result = orchestrator.run_verify("q")
    assert result.result_classification is ResultClassification.WITHHELD
    assert result.exit_code == EXIT_WITHHELD


def test_major_conflicting_publishes_as_conflicting():
    orchestrator, _, _ = build(verify_status="conflicting")
    result = orchestrator.run_verify("q")
    assert result.call_count == 7
    assert result.status is RunStatus.COMPLETED
    assert result.result_classification is ResultClassification.CONFLICTING
    assert result.exit_code == EXIT_OK


def test_major_unverified_publishes_as_partially_verified_when_others_verified():
    orchestrator, _, _ = build(
        verify_claims={
            "claims": [
                {"claim_id": "claim-1", "importance": "major", "status": "verified"},
                {"claim_id": "claim-2", "importance": "major", "status": "unverified"},
            ]
        }
    )
    result = orchestrator.run_verify("q")
    assert result.result_classification is ResultClassification.PARTIALLY_VERIFIED
    assert result.exit_code == EXIT_OK


def test_changes_required_then_approved_publishes_revised_answer():
    storage = InMemoryStorageBackend()
    orchestrator, adapter_a, adapter_b = build(
        audits=[
            {"status": "changes_required", "issues": [{"issue_id": "i1", "issue_type": "logic"}]},
            {"status": "approved"},
        ],
        storage=storage,
    )

    result = orchestrator.run_verify("q")

    assert result.call_count == 9  # 7 + revision synthesize + re-audit
    assert [r.phase for r in adapter_a.requests][-2:] == ["synthesize", "synthesize"]
    assert [r.phase for r in adapter_b.requests] == ["respond", "audit", "audit"]
    assert result.status is RunStatus.COMPLETED
    assert result.final_answer == "final-v2"  # revised answer is published
    assert result.exit_code == EXIT_OK
    assert [i.status.value for i in result.audit_issues] == ["resolved"]

    events = [e.event_type for e in storage.load(result.run_id).events]
    revision = [t for t in events if t in (
        "revision_started", "synthesis_revised", "reaudit_started", "reaudit_completed",
    )]
    assert revision == ["revision_started", "synthesis_revised", "reaudit_started", "reaudit_completed"]


def test_reaudit_rejection_withholds_instead_of_failing():
    orchestrator, _, _ = build(
        audits=[
            {"status": "changes_required", "issues": [{"issue_id": "i1"}, {"issue_id": "i2"}]},
            {"status": "changes_required", "issues": [{"issue_id": "i1"}]},
        ]
    )

    result = orchestrator.run_verify("q")

    assert result.call_count == 9
    assert result.status is RunStatus.COMPLETED  # W-2: withheld is not a failure
    assert result.result_classification is ResultClassification.WITHHELD
    assert result.final_answer is None  # unapproved answer stays unpublished
    assert result.exit_code == EXIT_WITHHELD
    by_id = {i.issue_id: i.status.value for i in result.audit_issues}
    assert by_id == {"i1": "open", "i2": "resolved"}  # only the re-reported issue stays open


def test_initial_blocked_withholds_without_revision():
    storage = InMemoryStorageBackend()
    orchestrator, adapter_a, adapter_b = build(
        audits=[{"status": "blocked", "issues": [{"issue_id": "i1"}]}], storage=storage
    )

    result = orchestrator.run_verify("q")

    assert result.call_count == 7  # no revision cycle
    assert [r.phase for r in adapter_b.requests] == ["respond", "audit"]
    assert result.result_classification is ResultClassification.WITHHELD
    assert result.exit_code == EXIT_WITHHELD
    assert result.audit_issues[0].status.value == "open"
    events = [e.event_type for e in storage.load(result.run_id).events]
    assert "revision_started" not in events


def test_budget_exhaustion_during_revision_fails_run():
    # 7 normal calls + revision synthesize = 8; the re-audit reservation is
    # rejected and no auditor-approved answer exists, so the run fails.
    budget = TokenBudget(input_limit=10**6, output_limit=10**6, call_limit=8)
    orchestrator, _, _ = build(
        audits=[{"status": "changes_required", "issues": [{"issue_id": "i1"}]}], budget=budget
    )

    result = orchestrator.run_verify("q")

    assert result.call_count == 8
    assert result.status is RunStatus.FAILED
    assert result.exit_code == EXIT_FAILED
    assert budget.snapshot().reserved_call_count == 0


def test_budget_exhaustion_before_first_call_fails_run():
    budget = TokenBudget(input_limit=10**6, output_limit=10**6, call_limit=3)
    storage = InMemoryStorageBackend()
    orchestrator, _, _ = build(budget=budget, storage=storage)

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.exit_code == EXIT_FAILED
    assert result.call_count == 3  # fourth reservation was rejected
    assert budget.snapshot().reserved_call_count == 0  # nothing left dangling
    events = storage.load(result.run_id).events
    assert any(e.event_type == "budget_exceeded" for e in events)
    assert events[-1].event_type == "run_failed"


def test_single_agent_stops_preflight_without_creating_a_run():
    storage = InMemoryStorageBackend()
    budget = TokenBudget(input_limit=10**6, output_limit=10**6)
    orchestrator = Orchestrator(
        [RegisteredAgent("agent-a", ScriptedAgentAdapter([]))],
        FakeEvidenceProvider(),
        budget,
        storage,
    )
    with pytest.raises(InsufficientAgentsError):
        orchestrator.run_verify("q")
    assert storage.purge() == 0  # V-1: no Run, nothing persisted
    assert budget.snapshot().committed_call_count == 0


def test_timeout_is_retried_once_with_new_execution_and_history_kept():
    storage = InMemoryStorageBackend()
    orchestrator, adapter_a, _ = build_raw(
        [
            AgentFailure("TIMEOUT"),  # respond #1, first attempt
            {"answer": "A"},  # respond #1, retry
            claims_output("unverified"),
            claims_output("verified"),
            {"critique": "ok"},
            {"answer": "final"},
        ],
        [{"answer": "B"}, {"status": "approved"}],
        storage=storage,
    )

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.COMPLETED
    assert result.exit_code == EXIT_OK
    assert result.call_count == 8  # 7 phases + 1 failed attempt (safe-side commit)
    assert [r.phase for r in adapter_a.requests][:2] == ["respond", "respond"]  # same agent, same phase

    events = storage.load(result.run_id).events
    failed = [e for e in events if e.event_type == "agent_execution_failed"]
    assert len(failed) == 1  # original failure stays in history
    assert failed[0].payload["error_code"] == "TIMEOUT"
    retried = [
        e for e in events
        if e.event_type == "agent_execution_succeeded" and "retry_of" in e.payload
    ]
    assert len(retried) == 1
    assert retried[0].payload["retry_of"] == failed[0].payload["execution_id"]
    assert retried[0].payload["execution_id"] != failed[0].payload["execution_id"]  # new execution


def test_second_timeout_of_same_execution_terminates_run():
    orchestrator, adapter_a, _ = build_raw(
        [AgentFailure("TIMEOUT"), AgentFailure("TIMEOUT")],
        [{"answer": "B"}],
    )
    budget = orchestrator._budget

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.exit_code == EXIT_FAILED
    assert len(adapter_a.requests) == 2  # one retry only
    assert result.call_count == 2
    assert budget.snapshot().reserved_call_count == 0


def test_auth_required_is_not_retried():
    storage = InMemoryStorageBackend()
    orchestrator, adapter_a, _ = build_raw(
        [AgentFailure("AUTH_REQUIRED")], [{"answer": "B"}], storage=storage
    )

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert len(adapter_a.requests) == 1  # no retry for non-transient errors
    events = storage.load(result.run_id).events
    failed = [e for e in events if e.event_type == "agent_execution_failed"]
    assert failed[0].payload["error_code"] == "AUTH_REQUIRED"


def test_run_level_retry_budget_is_two():
    orchestrator, adapter_a, _ = build_raw(
        [
            AgentFailure("TIMEOUT"),  # respond #1 -> retry 1
            {"answer": "A"},
            AgentFailure("RATE_LIMITED"),  # claim_extract -> retry 2
            claims_output("unverified"),
            AgentFailure("TIMEOUT"),  # verify -> run retry budget exhausted
        ],
        [{"answer": "B"}],
    )

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.exit_code == EXIT_FAILED
    phases = [r.phase for r in adapter_a.requests]
    assert phases == ["respond", "respond", "claim_extract", "claim_extract", "verify"]
    assert result.call_count == 6  # attempts: 2 + 1 + 2 + 1


def test_no_store_run_touches_no_storage():
    orchestrator, _, _ = build(storage=None)
    result = orchestrator.run_verify("q")
    assert result.status is RunStatus.COMPLETED


def test_adapter_failure_settles_budget_and_propagates():
    class ExplodingAdapter:
        def execute(self, request):
            raise RuntimeError("boom")

    budget = TokenBudget(input_limit=10**6, output_limit=10**6)
    orchestrator = Orchestrator(
        [
            RegisteredAgent("agent-a", ExplodingAdapter()),
            RegisteredAgent("agent-b", ExplodingAdapter()),
        ],
        FakeEvidenceProvider(),
        budget,
        None,
    )
    with pytest.raises(RuntimeError):
        orchestrator.run_verify("q")
    assert budget.snapshot().reserved_call_count == 0
