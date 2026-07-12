"""Formal Phase / AgentExecution / RunMetadataRecord tests (SPEC §15.8, O-5)."""

import itertools
from datetime import datetime, timedelta, timezone

import oracle_council.orchestrator as orchestrator_module
from oracle_council.models import AgentFailure, PhaseStatus, ResultClassification
from oracle_council.storage import InMemoryStorageBackend

from test_orchestrator import build, build_raw, claims_output

FULL_PHASES = [
    "respond", "claim_extract", "evidence_collect", "verify", "criticize", "synthesize", "audit",
]


def phase_by_name(result):
    return {p.phase: p for p in result.phases}


def test_happy_path_phase_and_execution_counts_match():
    orchestrator, _, _ = build()
    result = orchestrator.run_verify("q")

    assert [p.phase for p in result.phases] == FULL_PHASES
    assert len(result.executions) == 7  # evidence_collect creates no execution (M-4)
    phases = phase_by_name(result)
    assert all(p.status is PhaseStatus.SUCCEEDED for p in result.phases)
    assert (phases["respond"].success_count, phases["respond"].minimum_success_count) == (2, 2)
    assert phases["evidence_collect"].outcome == "evidence_found"
    assert all(p.started_at is not None and p.finished_at is not None for p in result.phases)
    assert all(e.elapsed_ms >= 0 for e in result.executions)


def test_phase_finished_at_reflects_the_phase_own_completion_not_run_end(monkeypatch):
    """Regression (found reviewing real metrics 2026-07-13): finished_at was
    only ever set on success via _finish()'s catch-all, which backfilled the
    Run's single overall end time onto every phase — so an early phase like
    `respond` showed an elapsed_ms that silently included every phase after
    it. Uses a deterministic fake clock (one tick per utc_now() call, no
    real sleep) so the fix can be verified without timing flakiness."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ticks = (base + timedelta(seconds=i) for i in itertools.count())
    monkeypatch.setattr(orchestrator_module, "utc_now", lambda: next(ticks))

    orchestrator, _, _ = build()
    result = orchestrator.run_verify("q")

    phases = phase_by_name(result)
    ordered = [phases[name].finished_at for name in
               ("respond", "claim_extract", "verify", "criticize", "synthesize", "audit")]
    assert ordered == sorted(ordered)  # each phase finishes no later than the next
    assert len(set(ordered)) == len(ordered)  # none collapsed onto a shared Run-end timestamp


def test_retry_adds_execution_but_not_phase():
    orchestrator, _, _ = build_raw(
        [
            AgentFailure("TIMEOUT"),
            {"answer": "A"},
            claims_output("unverified"),
            claims_output("verified"),
            {"critique": "ok"},
            {"answer": "final"},
        ],
        [{"answer": "B"}, {"status": "approved"}],
    )
    result = orchestrator.run_verify("q")

    assert [p.phase for p in result.phases] == FULL_PHASES  # no extra phase instance
    assert len(result.executions) == 8
    failed = [e for e in result.executions if e.error_code == "TIMEOUT"]
    assert len(failed) == 1
    assert failed[0].status.value == "timed_out"
    retried = [e for e in result.executions if e.retry_of == failed[0].execution_id]
    assert len(retried) == 1 and retried[0].status.value == "succeeded"
    assert phase_by_name(result)["respond"].success_count == 2
    assert result.metadata.error_codes == ("TIMEOUT",)


def test_withheld_marks_publish_phases_skipped():
    orchestrator, _, _ = build(verify_status="unverified", importance="critical")
    result = orchestrator.run_verify("q")

    phases = phase_by_name(result)
    for name in ("criticize", "synthesize", "audit"):
        assert phases[name].status is PhaseStatus.SKIPPED
        assert phases[name].success_count == 0
    assert phases["verify"].status is PhaseStatus.SUCCEEDED  # U-1: claim results exist


def test_reaudit_extends_same_phase_instance():
    orchestrator, _, _ = build(
        audits=[
            {"status": "changes_required", "issues": [{"issue_id": "i1"}]},
            {"status": "approved"},
        ]
    )
    result = orchestrator.run_verify("q")

    assert [p.phase for p in result.phases] == FULL_PHASES  # still one audit phase
    phases = phase_by_name(result)
    assert phases["synthesize"].success_count == 2  # revision joins the same phase
    assert phases["audit"].success_count == 2
    assert len(result.executions) == 9


def test_error_summary_is_templated_and_bounded():
    secret_question = "SECRET-QUESTION with credentials"
    orchestrator, _, _ = build_raw(
        [AgentFailure("AUTH_REQUIRED", "raw stderr with SECRET-TOKEN")],
        [{"answer": "B"}],
    )
    result = orchestrator.run_verify(secret_question)

    failed = [e for e in result.executions if e.error_code == "AUTH_REQUIRED"]
    assert failed[0].status.value == "unavailable"
    for record in list(result.executions) + list(result.phases):
        summary = record.error_summary
        if summary:
            assert len(summary) <= 200
            assert "SECRET" not in summary  # template only: no raw text leaks
    assert failed[0].raw_diagnostic is None  # store_content off by default


def test_raw_diagnostic_kept_only_with_store_content():
    orchestrator, _, _ = build_raw(
        [AgentFailure("AUTH_REQUIRED", "raw stderr detail")],
        [{"answer": "B"}],
        store_content=True,
    )
    result = orchestrator.run_verify("q")
    failed = [e for e in result.executions if e.error_code == "AUTH_REQUIRED"]
    assert failed[0].raw_diagnostic == "raw stderr detail"
    assert result.metadata.content_saved is True


def test_run_completed_snapshot_matches_result_and_aggregation():
    storage = InMemoryStorageBackend()
    orchestrator, _, _ = build(storage=storage)
    result = orchestrator.run_verify("q")

    metadata = result.metadata
    assert metadata.status.value == "completed"
    assert metadata.result_classification is ResultClassification.VERIFIED
    assert metadata.consensus_status == "not_applicable"
    assert metadata.participant_count == 2
    assert metadata.claim_count == len(result.claims) == 1
    assert metadata.evidence_count == 1
    assert metadata.error_codes == ()
    assert metadata.elapsed_ms >= 0
    assert metadata.content_saved is False

    events = storage.load(result.run_id).events
    final = events[-1]
    assert final.event_type == "run_completed"
    assert final.payload["metadata"] == metadata.to_dict()  # snapshot is the source of truth
