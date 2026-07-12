import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from collect_metrics import read_questions, summarize  # noqa: E402


def test_read_questions_skips_blanks_and_comments(tmp_path):
    path = tmp_path / "q.txt"
    path.write_text("質問1\n\n# comment\n質問2\n", encoding="utf-8")
    assert read_questions(path) == ["質問1", "質問2"]


def test_summarize_aggregates_classification_and_status_counts():
    records = [
        {
            "status": "completed",
            "answer": {"result_classification": "verified"},
            "agent_call_count": 7,
            "_wall_elapsed_ms": 90000,
            "executions": [{"error_code": None}],
            "phases": [{"phase": "respond", "elapsed_ms": 12000}],
        },
        {
            "status": "completed",
            "answer": {"result_classification": "withheld"},
            "agent_call_count": 4,
            "_wall_elapsed_ms": 60000,
            "executions": [{"error_code": "QUOTA_EXCEEDED"}],
            "phases": [{"phase": "respond", "elapsed_ms": 8000}],
        },
    ]
    summary = summarize(records)
    assert summary["run_count"] == 2
    assert summary["result_classification_counts"] == {"verified": 1, "withheld": 1}
    assert summary["run_status_counts"] == {"completed": 2}
    assert summary["avg_call_count"] == 5.5
    assert summary["avg_wall_elapsed_ms"] == 75000.0
    assert summary["avg_phase_elapsed_ms"]["respond"] == 10000.0
    assert summary["agent_error_code_counts"] == {"QUOTA_EXCEEDED": 1}
    assert summary["quota_occurrences"] == 1


def test_summarize_handles_missing_optional_fields():
    summary = summarize([{"status": "failed"}])
    assert summary["run_count"] == 1
    assert summary["avg_call_count"] is None
    assert summary["avg_wall_elapsed_ms"] is None
    assert summary["avg_phase_elapsed_ms"] == {}
    assert summary["quota_occurrences"] == 0
