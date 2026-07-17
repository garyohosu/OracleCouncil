from datetime import datetime, timedelta, timezone
import itertools

import pytest

from oracle_council.assignment import InsufficientAgentsError, RegisteredAgent
from oracle_council.clarification import ClarificationStopError
from oracle_council.budget import TokenBudget
from oracle_council.fakes import FakeEvidenceProvider, ScriptedAgentAdapter
from oracle_council.models import AgentFailure, EvidenceCollectionResult, PhaseStatus, ResultClassification, RunStatus, SearchError
import oracle_council.orchestrator as orchestrator_module
from oracle_council.orchestrator import EXIT_FAILED, EXIT_OK, EXIT_WITHHELD, Orchestrator
from oracle_council.storage import InMemoryStorageBackend, StorageWriteError


def build_raw(a_script, b_script, budget=None, storage=None, store_content=False, evidence_provider=None):
    adapter_a = ScriptedAgentAdapter(a_script)
    adapter_b = ScriptedAgentAdapter(b_script)
    orchestrator = Orchestrator(
        [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)],
        evidence_provider or FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        budget or TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
        store_content=store_content,
    )
    return orchestrator, adapter_a, adapter_b


def claims_output(status, importance="major"):
    return {"claims": [{"claim_id": "claim-1", "importance": importance, "status": status}]}


def claims_with_text(*claims):
    return {"claims": list(claims)}


def phase_by_name(result):
    return {phase.phase: phase for phase in result.phases}


def build(
    verify_status="verified",
    importance="major",
    audits=None,
    verify_claims=None,
    budget=None,
    storage=None,
    evidence_provider=None,
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
        evidence_provider or FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
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


def test_run_result_contains_collected_evidence_after_happy_path():
    orchestrator, _, _ = build(
        evidence_provider=FakeEvidenceProvider(
            [{"evidence_id": "ev-1", "claim_id": "claim-1", "url": "https://example.com"}]
        )
    )
    result = orchestrator.run_verify("q")

    assert result.evidence == (
        {"evidence_id": "ev-1", "claim_id": "claim-1", "url": "https://example.com"},
    )
    assert result.metadata.evidence_count == len(result.evidence) == 1


def test_evidence_collect_timing_wraps_collection_with_fake_clock(monkeypatch):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ticks = (base + timedelta(seconds=i) for i in itertools.count())
    observed = {}

    monkeypatch.setattr(orchestrator_module, "utc_now", lambda: next(ticks))

    class TimedEvidenceProvider:
        def collect(self, claims):
            observed["during_collect"] = orchestrator_module.utc_now()
            return [{"evidence_id": "ev-1"}]

    orchestrator, _, _ = build(evidence_provider=TimedEvidenceProvider())
    result = orchestrator.run_verify("q")
    phase = phase_by_name(result)["evidence_collect"]

    assert phase.started_at < observed["during_collect"] < phase.finished_at
    assert int((phase.finished_at - phase.started_at).total_seconds() * 1000) > 0
    assert phase.success_count == 1


def test_evidence_collect_no_evidence_still_counts_success():
    orchestrator, _, _ = build(evidence_provider=FakeEvidenceProvider([]))
    result = orchestrator.run_verify("q")
    phase = phase_by_name(result)["evidence_collect"]

    assert phase.status is PhaseStatus.SUCCEEDED
    assert phase.success_count == 1
    assert phase.outcome == "no_evidence"
    assert phase.metrics["evidence_count"] == 0


def test_evidence_collect_search_error_records_failed_phase_and_run(monkeypatch):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ticks = (base + timedelta(seconds=i) for i in itertools.count())
    monkeypatch.setattr(orchestrator_module, "utc_now", lambda: next(ticks))

    class FailingEvidenceProvider:
        def collect(self, claims):
            raise SearchError("SEARCH_QUOTA_EXCEEDED", "raw stderr must not leak")

    orchestrator, _, _ = build(evidence_provider=FailingEvidenceProvider())
    result = orchestrator.run_verify("q")
    phase = phase_by_name(result)["evidence_collect"]

    assert result.status is RunStatus.FAILED
    assert result.exit_code == 3
    assert result.result_classification is ResultClassification.UNVERIFIED
    assert result.evidence == ()
    assert phase.status is PhaseStatus.FAILED
    assert phase.success_count == 0
    assert phase.error_code == "SEARCH_QUOTA_EXCEEDED"
    assert phase.error_summary == "evidence_collect execution ended with SEARCH_QUOTA_EXCEEDED."
    assert phase.finished_at is not None
    assert phase.metrics["search_error_codes"] == {"SEARCH_QUOTA_EXCEEDED": 1}
    assert "raw stderr" not in phase.error_summary


def test_evidence_collect_search_error_keeps_partial_evidence_and_metrics():
    class PartiallyFailingEvidenceProvider:
        def collect_with_metrics(self, claims):
            error = SearchError("SEARCH_QUOTA_EXCEEDED", "raw stderr must not leak")
            error.partial_evidence = (
                {"evidence_id": "web-claim-a-1", "claim_id": "claim-a", "nested": {"value": "original"}},
                {"evidence_id": "web-claim-a-2", "claim_id": "claim-a"},
            )
            error.evidence_metrics = {
                "search_count": 2,
                "candidate_count": 2,
                "fetch_attempt_count": 2,
                "fetch_success_count": 2,
                "fetch_failure_count": 0,
                "evidence_count": 2,
                "target_claim_count": 2,
                "claims_with_evidence_count": 1,
                "search_error_codes": {"SEARCH_QUOTA_EXCEEDED": 1},
                "fetch_error_codes": {},
            }
            raise error

    orchestrator, _, _ = build(
        evidence_provider=PartiallyFailingEvidenceProvider(),
        verify_claims=claims_output("verified"),
    )
    result = orchestrator.run_verify("q")
    phase = phase_by_name(result)["evidence_collect"]

    assert result.status is RunStatus.FAILED
    assert result.exit_code == 3
    assert result.evidence == (
        {"evidence_id": "web-claim-a-1", "claim_id": "claim-a", "nested": {"value": "original"}},
        {"evidence_id": "web-claim-a-2", "claim_id": "claim-a"},
    )
    assert phase.status is PhaseStatus.FAILED
    assert phase.success_count == 0
    assert phase.finished_at is not None
    assert phase.metrics == {
        "search_count": 2,
        "candidate_count": 2,
        "fetch_attempt_count": 2,
        "fetch_success_count": 2,
        "fetch_failure_count": 0,
        "evidence_count": 2,
        "target_claim_count": 2,
        "claims_with_evidence_count": 1,
        "search_error_codes": {"SEARCH_QUOTA_EXCEEDED": 1},
        "fetch_error_codes": {},
    }


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        (
            {
                "evidence_count": 1,
                "target_claim_count": 1,
                "claims_with_evidence_count": 1,
                "fetch_failure_count": 0,
            },
            "evidence_found",
        ),
        (
            {
                "evidence_count": 1,
                "target_claim_count": 1,
                "claims_with_evidence_count": 1,
                "fetch_failure_count": 1,
            },
            "partial_evidence",
        ),
        (
            {
                "evidence_count": 1,
                "target_claim_count": 2,
                "claims_with_evidence_count": 1,
                "fetch_failure_count": 0,
            },
            "partial_evidence",
        ),
        (
            {
                "evidence_count": 0,
                "target_claim_count": 1,
                "claims_with_evidence_count": 0,
                "fetch_failure_count": 0,
            },
            "no_evidence",
        ),
    ],
)
def test_evidence_collect_outcome_uses_detailed_metrics(metrics, expected):
    class MetricsEvidenceProvider:
        def collect_with_metrics(self, claims):
            evidence = [{"evidence_id": "ev-1"}] if metrics["evidence_count"] else []
            return EvidenceCollectionResult(evidence=tuple(evidence), metrics=metrics)

    orchestrator, _, _ = build(evidence_provider=MetricsEvidenceProvider())
    result = orchestrator.run_verify("q")

    assert phase_by_name(result)["evidence_collect"].outcome == expected


def test_evidence_collect_fallback_provider_does_not_infer_partial():
    class FallbackProvider:
        def collect(self, claims):
            return [{"evidence_id": "ev-1"}]

    orchestrator, _, _ = build(evidence_provider=FallbackProvider())
    result = orchestrator.run_verify("q")
    phase = phase_by_name(result)["evidence_collect"]

    assert phase.outcome == "evidence_found"
    assert phase.metrics["evidence_count"] == 1
    assert phase.metrics["fetch_failure_count"] == 0


def test_run_result_evidence_is_empty_when_run_fails_before_collection():
    budget = TokenBudget(input_limit=10**6, output_limit=10**6, call_limit=1)
    orchestrator, _, _ = build(budget=budget)
    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.evidence == ()
    assert result.metadata.evidence_count == 0


def test_run_result_keeps_evidence_when_later_phase_fails():
    orchestrator, _, _ = build_raw(
        [
            {"answer": "A"},
            claims_output("unverified"),
            AgentFailure("AUTH_REQUIRED"),
        ],
        [{"answer": "B"}, AgentFailure("AUTH_REQUIRED")],
        evidence_provider=FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
    )
    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.evidence == ({"evidence_id": "ev-1"},)
    assert result.metadata.evidence_count == 1


def test_withheld_run_result_keeps_collected_evidence():
    orchestrator, _, _ = build(
        verify_status="unverified",
        importance="critical",
        evidence_provider=FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
    )
    result = orchestrator.run_verify("q")

    assert result.result_classification is ResultClassification.WITHHELD
    assert result.evidence == ({"evidence_id": "ev-1"},)
    assert result.metadata.evidence_count == 1


def test_run_result_evidence_is_snapshot_not_provider_list_alias():
    class MutableEvidenceProvider:
        def __init__(self):
            self.evidence = [{"evidence_id": "ev-1", "nested": {"value": "original"}}]

        def collect(self, claims):
            return self.evidence

    provider = MutableEvidenceProvider()
    orchestrator, _, _ = build(evidence_provider=provider)
    result = orchestrator.run_verify("q")

    provider.evidence[0]["evidence_id"] = "changed"
    provider.evidence[0]["nested"]["value"] = "changed"
    provider.evidence.append({"evidence_id": "ev-2"})
    assert result.evidence == ({"evidence_id": "ev-1", "nested": {"value": "original"}},)
    assert result.evidence[0] is not provider.evidence[0]
    assert result.evidence[0]["nested"] is not provider.evidence[0]["nested"]


def test_storage_failure_after_evidence_collection_keeps_evidence_snapshot():
    class FailsAfterEvidenceCollection:
        def append(self, run_id, event):
            if event.event_type == "agent_execution_succeeded" and event.payload["phase"] == "claim_extract":
                raise StorageWriteError("simulated storage failure")
            return event

    orchestrator, _, _ = build(
        storage=FailsAfterEvidenceCollection(),
        evidence_provider=FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
    )
    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.exit_code == EXIT_FAILED
    assert result.evidence == ({"evidence_id": "ev-1"},)


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


def test_verify_merges_status_without_losing_claim_text_or_ids():
    orchestrator, _, _ = build_raw(
        [
            {"answer": "A"},
            {
                "claims": [
                    {
                        "claim_id": "premise",
                        "importance": "critical",
                        "status": "unverified",
                        "claim_role": "user_premise",
                        "text": "The legal adult age is still 20.",
                    },
                    {
                        "claim_id": "correction",
                        "importance": "critical",
                        "status": "unverified",
                        "claim_role": "proposed_answer",
                        "text": "The legal adult age is 18.",
                    },
                ]
            },
            {
                "claims": [
                    {"claim_id": "renamed-by-verifier", "importance": "critical", "status": "contradicted"},
                    {"claim_id": "also-renamed", "importance": "critical", "status": "verified"},
                ]
            },
            {"critique": "correctable false premise"},
            {"answer": "The premise is wrong; the legal adult age is 18."},
        ],
        [{"answer": "B"}, {"status": "approved"}],
    )

    result = orchestrator.run_verify("q")

    assert [(claim.claim_id, claim.text, claim.claim_role.value, claim.status.value) for claim in result.claims] == [
        ("premise", "The legal adult age is still 20.", "user_premise", "contradicted"),
        ("correction", "The legal adult age is 18.", "proposed_answer", "verified"),
    ]
    assert result.result_classification is ResultClassification.VERIFIED
    assert result.exit_code == EXIT_OK


def test_false_premise_correction_with_supported_context_is_publishable():
    orchestrator, _, _ = build_raw(
        [
            {"answer": "A"},
            {
                "claims": [
                    {
                        "claim_id": "premise",
                        "importance": "critical",
                        "status": "unverified",
                        "claim_role": "user_premise",
                        "text": "The premise is wrong.",
                    },
                    {
                        "claim_id": "correction",
                        "importance": "critical",
                        "status": "unverified",
                        "claim_role": "proposed_answer",
                        "text": "The correction is supported.",
                    },
                    {
                        "claim_id": "context",
                        "importance": "major",
                        "status": "unverified",
                        "claim_role": "contextual",
                        "text": "A related limit remains unchanged.",
                    },
                ]
            },
            {
                "claims": [
                    {"claim_id": "premise", "importance": "critical", "status": "contradicted"},
                    {"claim_id": "correction", "importance": "critical", "status": "verified"},
                    {"claim_id": "context", "importance": "major", "status": "supported"},
                ]
            },
            {"critique": "publish correction"},
            {"answer": "The premise is wrong; the correction is supported."},
        ],
        [{"answer": "B"}, {"status": "approved"}],
    )

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.COMPLETED
    assert result.result_classification is ResultClassification.VERIFIED
    assert result.final_answer == "The premise is wrong; the correction is supported."
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
        [{"answer": "B"}, AgentFailure("TIMEOUT")],
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
        [{"answer": "B"}, AgentFailure("TIMEOUT")],
    )

    result = orchestrator.run_verify("q")

    assert result.status is RunStatus.FAILED
    assert result.exit_code == EXIT_FAILED
    phases = [r.phase for r in adapter_a.requests]
    assert phases == ["respond", "respond", "claim_extract", "claim_extract", "verify"]
    assert result.call_count == 7  # attempts: 2 + 1 + 2 + 1 + one substitution


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


def test_execution_error_keeps_fixed_summary_without_invalid_output_wrapper():
    fixed = "verify process exited with a non-zero status."
    orchestrator, _, _ = build_raw(
        [
            {"answer": "A"},
            claims_output("unverified"),
            AgentFailure("EXECUTION_ERROR", "raw stderr SECRET-TOKEN", public_summary=fixed),
        ],
        [{"answer": "B"}, AgentFailure("EXECUTION_ERROR", public_summary=fixed)],
    )

    result = orchestrator.run_verify("private question")

    phase = phase_by_name(result)["verify"]
    failed = [e for e in result.executions if e.phase == "verify"]
    assert phase.error_code == "EXECUTION_ERROR"
    assert phase.error_summary == fixed
    assert failed[0].error_summary == fixed
    assert "invalid output" not in phase.error_summary
    assert ".." not in phase.error_summary
    assert "SECRET-TOKEN" not in phase.error_summary


def test_execution_error_phase_mismatch_falls_back_to_fixed_code_summary():
    orchestrator, _, _ = build_raw(
        [
            {"answer": "A"},
            claims_output("unverified"),
            AgentFailure(
                "EXECUTION_ERROR",
                "raw stderr",
                public_summary="criticize process exited with a non-zero status.",
            ),
        ],
        [{"answer": "B"}, AgentFailure("EXECUTION_ERROR")],
    )

    result = orchestrator.run_verify("q")

    assert phase_by_name(result)["verify"].error_summary == (
        "verify execution ended with EXECUTION_ERROR."
    )


def _build_three_agent(a_script, b_script, c_script, storage=None):
    adapters = [
        ScriptedAgentAdapter(a_script),
        ScriptedAgentAdapter(b_script),
        ScriptedAgentAdapter(c_script),
    ]
    agents = [
        RegisteredAgent("agent-a", adapters[0], {"verify": 100, "synthesize": 100}),
        RegisteredAgent("agent-b", adapters[1], {"audit": 100}),
        RegisteredAgent("agent-c", adapters[2], {"verify": 90, "synthesize": 90}),
    ]
    return Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
    ), adapters


def test_timeout_retry_failure_then_three_agent_substitution_succeeds():
    storage = InMemoryStorageBackend()
    orchestrator, adapters = _build_three_agent(
        [{"answer": "A"}, claims_output("verified"), AgentFailure("TIMEOUT"), AgentFailure("TIMEOUT"), {"critique": "ok"}, {"answer": "final"}],
        [{"answer": "B"}, {"status": "approved"}],
        [{"claims": [{"claim_id": "claim-1", "importance": "major", "status": "verified"}]}],
        storage=storage,
    )
    result = orchestrator.run_verify("q")
    verify_execs = [item for item in result.executions if item.phase == "verify"]
    assert result.status is RunStatus.COMPLETED
    assert [item.agent_id for item in verify_execs] == ["agent-a", "agent-a", "agent-c"]
    assert verify_execs[1].retry_of == verify_execs[0].execution_id
    assert verify_execs[2].substitute_for == verify_execs[1].execution_id
    assert result.call_count == 9


def test_two_agent_synth_quota_does_not_break_auditor_separation():
    storage = InMemoryStorageBackend()
    orchestrator, _, _ = build_raw(
        [{"answer": "A"}, claims_output("verified"), {"claims": [{"claim_id": "claim-1", "importance": "major", "status": "verified"}]}, {"critique": "ok"}, AgentFailure("QUOTA_EXCEEDED")],
        [{"answer": "B"}, {"status": "approved"}],
        storage=storage,
    )
    result = orchestrator.run_verify("q")
    assert result.status is RunStatus.FAILED
    assert result.final_answer is None
    assert not any(item.substitute_for for item in result.executions)
    events = storage.load(result.run_id).events
    unavailable = [event for event in events if event.event_type == "agent_substitution_unavailable"]
    assert unavailable and unavailable[0].payload["original_agent_id"] == "agent-a"


def test_three_agent_synth_quota_substitutes_and_keeps_distinct_auditor():
    orchestrator, _ = _build_three_agent(
        [{"answer": "A"}, claims_output("verified"), {"claims": [{"claim_id": "claim-1", "importance": "major", "status": "verified"}]}, {"critique": "ok"}, AgentFailure("QUOTA_EXCEEDED")],
        [{"answer": "B"}, {"status": "approved"}],
        [{"answer": "substituted"}],
    )
    result = orchestrator.run_verify("q")
    assert result.status is RunStatus.COMPLETED
    synth = [item for item in result.executions if item.phase == "synthesize"]
    audit = [item for item in result.executions if item.phase == "audit"]
    assert synth[-1].agent_id == "agent-c"
    assert synth[-1].substitute_for == synth[0].execution_id
    assert audit[-1].agent_id == "agent-b"
    assert synth[-1].agent_id != audit[-1].agent_id


def test_substitution_event_contains_metadata_only():
    storage = InMemoryStorageBackend()
    orchestrator, _ = _build_three_agent(
        [{"answer": "A"}, claims_output("verified"), AgentFailure("QUOTA_EXCEEDED"), {"critique": "ok"}, {"critique": "ok-2"}, {"answer": "final"}],
        [{"answer": "B"}, {"critique": "ok"}, {"status": "approved"}],
        [{"claims": [{"claim_id": "claim-1", "importance": "major", "status": "verified"}]}, {"answer": "final"}],
        storage=storage,
    )
    result = orchestrator.run_verify("secret question")
    events = storage.load(result.run_id).events
    selected = [event for event in events if event.event_type == "agent_substitute_selected"]
    assert selected
    assert "secret question" not in str(selected[0].payload)
    assert set(selected[0].payload) == {
        "phase", "slot_index", "failed_execution_id", "original_agent_id", "substitute_agent_id"
    }


def test_s9_participant_integration_with_five_agents():
    storage = InMemoryStorageBackend()
    adapters = [
        ScriptedAgentAdapter([]),
        ScriptedAgentAdapter([
            {"answer": "B-respond"},
            {"claims": [{"claim_id": "c1", "importance": "critical", "status": "unverified"}]},
        ]),
        ScriptedAgentAdapter([
            {"answer": "C-respond"},
        ]),
        ScriptedAgentAdapter([
            {"claims": [{"claim_id": "c1", "importance": "critical", "status": "unverified"}]},
        ]),
        ScriptedAgentAdapter([]),
    ]
    agents = [
        RegisteredAgent("agent-a", adapters[0], {"respond": 0}),
        RegisteredAgent("agent-b", adapters[1], {"synthesize": 90}),
        RegisteredAgent("agent-c", adapters[2], {"audit": 80}),
        RegisteredAgent("agent-d", adapters[3], {"verify": 70}),
        RegisteredAgent("agent-e", adapters[4], {"criticize": 100}),
    ]
    orchestrator = Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
    )

    result = orchestrator.run_verify("test question")
    assert result.status is RunStatus.COMPLETED
    assert result.result_classification is ResultClassification.WITHHELD
    assert result.participants == ("agent-b", "agent-c", "agent-d", "agent-e")
    assert result.metadata.participants == ("agent-b", "agent-c", "agent-d", "agent-e")

    events = storage.load(result.run_id).events
    assert events[0].event_type == "run_created"
    assert events[0].payload["participants"] == ["agent-b", "agent-c", "agent-d", "agent-e"]

    # agent-e is not executed, but participants remain the full selected council
    assert len(adapters[4].requests) == 0
    assert not any(e.agent_id == "agent-e" for e in result.executions)
    assert result.participants == ("agent-b", "agent-c", "agent-d", "agent-e")


def test_quick_mode_flow_success():
    # In quick mode:
    # 1. respond #1 (agent-a) -> {"answer": "A"}
    # 2. respond #2 (agent-b) -> {"answer": "B"}
    # 3. compare (agent-a) -> {"comparison": "compared"}
    # 4. synthesize (agent-a) -> {"answer": "quick-final"}
    script_a = [
        {"answer": "A"},
        {"comparison": "compared"},
        {"answer": "quick-final"},
    ]
    script_b = [
        {"answer": "B"},
    ]
    orchestrator, adapter_a, adapter_b = build_raw(script_a, script_b)
    result = orchestrator.run_verify("test question", mode="quick")
    assert result.status == RunStatus.COMPLETED
    assert result.result_classification == ResultClassification.UNVERIFIED
    assert result.final_answer == "quick-final"
    assert result.oracle_exit_code == 0
    assert result.mode == "quick"
    assert result.external_verification is False

    phases = [p.phase for p in result.phases]
    assert phases == ["respond", "compare", "synthesize"]
    for p in result.phases:
        assert p.status == PhaseStatus.SUCCEEDED
# ---------------------------------------------------------------------------
# S-4: ClarificationEngine -> Clarifier Agent wiring (QandA S-4.1-S-4.4)
# ---------------------------------------------------------------------------

_AMBIGUOUS_QUESTION = "どちらのプランが良いですか？"

_READY_CLARIFY_OUTPUT = {
    "status": "ready",
    "refined_question": _AMBIGUOUS_QUESTION,
    "assumptions": [],
    "questions": [],
}

_NORMAL_FLOW_SCRIPT_A = [
    {"answer": "A"},
    {"claims": [{"claim_id": "c1", "importance": "major", "status": "unverified"}]},
    {"claims": [{"claim_id": "c1", "importance": "major", "status": "verified"}]},
    {"critique": "ok"},
    {"answer": "final"},
]
_NORMAL_FLOW_SCRIPT_B = [{"answer": "B"}, {"status": "approved"}]


def test_clarify_not_invoked_for_template_matching_question_call_count_seven():
    orchestrator, adapter_a, adapter_b = build_raw(_NORMAL_FLOW_SCRIPT_A, _NORMAL_FLOW_SCRIPT_B)
    result = orchestrator.run_verify("この記事を要約してください")
    assert result.call_count == 7
    assert "clarify" not in [p.phase for p in result.phases]
    assert [r.phase for r in adapter_a.requests][0] != "clarify"


def test_clarify_invoked_for_critical_ambiguity_call_count_eight():
    orchestrator, adapter_a, adapter_b = build_raw(
        [_READY_CLARIFY_OUTPUT] + _NORMAL_FLOW_SCRIPT_A, _NORMAL_FLOW_SCRIPT_B
    )
    result = orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert result.call_count == 8
    assert [r.phase for r in adapter_a.requests][0] == "clarify"
    assert [p.phase for p in result.phases][0] == "clarify"
    assert result.status is RunStatus.COMPLETED
    assert result.oracle_exit_code == EXIT_OK


def test_clarify_agent_selected_by_role_priority():
    adapter_a = ScriptedAgentAdapter(_NORMAL_FLOW_SCRIPT_A)
    adapter_b = ScriptedAgentAdapter([_READY_CLARIFY_OUTPUT] + _NORMAL_FLOW_SCRIPT_B)
    agents = [
        RegisteredAgent("agent-a", adapter_a, role_priority={"clarify": 10}),
        RegisteredAgent("agent-b", adapter_b, role_priority={"clarify": 100}),
    ]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None,
    )
    orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert [r.phase for r in adapter_a.requests][0] != "clarify"
    assert [r.phase for r in adapter_b.requests][0] == "clarify"


def test_clarify_agent_request_contains_the_question():
    orchestrator, adapter_a, adapter_b = build_raw(
        [_READY_CLARIFY_OUTPUT] + _NORMAL_FLOW_SCRIPT_A, _NORMAL_FLOW_SCRIPT_B
    )
    orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    clarify_request = adapter_a.requests[0]
    assert clarify_request.phase == "clarify"
    assert clarify_request.payload["question"] == _AMBIGUOUS_QUESTION


def test_clarify_ready_with_assumptions_proceeds_to_normal_run():
    output = dict(_READY_CLARIFY_OUTPUT)
    output.update(status="ready_with_assumptions", assumptions=["region: Tokyo"])
    orchestrator, adapter_a, adapter_b = build_raw([output] + _NORMAL_FLOW_SCRIPT_A, _NORMAL_FLOW_SCRIPT_B)
    result = orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert result.status is RunStatus.COMPLETED
    assert result.final_answer == "final"


def _stop_status_output(status, note="stop"):
    return {
        "status": status,
        "refined_question": _AMBIGUOUS_QUESTION,
        "assumptions": [],
        "questions": [],
        "note": note,
    }


@pytest.mark.parametrize(
    "status",
    ["needs_clarification", "premise_issue", "unsupported", "safety_blocked"],
)
def test_clarify_stop_status_raises_clarification_stop_error_no_run_persisted(status):
    storage = InMemoryStorageBackend()
    adapter_a = ScriptedAgentAdapter([_stop_status_output(status)])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        storage,
    )
    with pytest.raises(ClarificationStopError) as exc_info:
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert exc_info.value.status == status
    assert exc_info.value.exit_code == 2
    assert storage._events == {}


def test_clarify_critical_question_upgrades_to_needs_clarification_stop():
    output = {
        "status": "ready_with_assumptions",
        "refined_question": _AMBIGUOUS_QUESTION,
        "assumptions": [],
        "questions": [{"text": "target?", "importance": "critical"}],
    }
    adapter_a = ScriptedAgentAdapter([output])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None,
    )
    with pytest.raises(ClarificationStopError) as exc_info:
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert exc_info.value.status == "needs_clarification"


def test_clarify_agent_failure_raises_clarification_unavailable():
    adapter_a = ScriptedAgentAdapter([AgentFailure("EXECUTION_ERROR", "boom")])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None,
    )
    with pytest.raises(ClarificationStopError) as exc_info:
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert exc_info.value.status == "clarification_unavailable"
    assert exc_info.value.exit_code == 3


def test_clarify_agent_timeout_raises_clarification_unavailable():
    adapter_a = ScriptedAgentAdapter([AgentFailure("TIMEOUT", "timed out")])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None,
    )
    with pytest.raises(ClarificationStopError) as exc_info:
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert exc_info.value.status == "clarification_unavailable"
    assert exc_info.value.exit_code == 3


def test_clarify_agent_invalid_output_raises_clarification_unavailable():
    # Simulates the adapter's own schema validation failure (empty response,
    # malformed JSON, or a schema mismatch all surface as INVALID_OUTPUT
    # before Orchestrator ever sees a dict) - the existing failure
    # classification, unchanged for this new phase.
    adapter_a = ScriptedAgentAdapter([AgentFailure("INVALID_OUTPUT", "missing field: status")])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None,
    )
    with pytest.raises(ClarificationStopError) as exc_info:
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert exc_info.value.status == "clarification_unavailable"


def test_clarify_auth_required_maps_to_auth_required_status():
    adapter_a = ScriptedAgentAdapter([AgentFailure("AUTH_REQUIRED", "login required")])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    orchestrator = orchestrator_module.Orchestrator(
        agents,
        FakeEvidenceProvider([{"evidence_id": "ev-1"}]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None,
    )
    with pytest.raises(ClarificationStopError) as exc_info:
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    assert exc_info.value.status == "auth_required"
    assert exc_info.value.exit_code == 3


def test_clarify_skipped_entirely_in_quick_mode():
    # J-3's quick-mode call graph (respond*2 -> compare -> synthesize) must
    # stay untouched; quick mode has no clarify slot in its ExecutionPlan.
    script_a = [{"answer": "A"}, {"comparison": "compared"}, {"answer": "quick-final"}]
    script_b = [{"answer": "B"}]
    orchestrator, adapter_a, adapter_b = build_raw(script_a, script_b)
    result = orchestrator.run_verify(_AMBIGUOUS_QUESTION, mode="quick")
    assert result.status is RunStatus.COMPLETED
    assert [p.phase for p in result.phases] == ["respond", "compare", "synthesize"]


def test_clarify_budget_settled_after_stop_error():
    # The clarify pre-flight now runs inside run_verify's try/finally, so
    # assert_settled() must still run (and not raise) even when clarify
    # stops before a Run is created.
    adapter_a = ScriptedAgentAdapter([_stop_status_output("needs_clarification")])
    adapter_b = ScriptedAgentAdapter([])
    agents = [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)]
    budget = TokenBudget(input_limit=10**6, output_limit=10**6)
    orchestrator = orchestrator_module.Orchestrator(
        agents, FakeEvidenceProvider([{"evidence_id": "ev-1"}]), budget, None
    )
    with pytest.raises(ClarificationStopError):
        orchestrator.run_verify(_AMBIGUOUS_QUESTION)
    budget.assert_settled()  # must not raise
