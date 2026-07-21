from datetime import datetime, timezone

from oracle_council.trace import TraceEntry, TraceRecorder, redact_secrets


def _ts(offset_s: int = 0) -> datetime:
    return datetime(2026, 7, 20, 0, 0, offset_s, tzinfo=timezone.utc)


def test_redact_secrets_scrubs_common_credential_shapes():
    assert redact_secrets("here is sk-abcdefghijklmnopqrstuvwx for you") == "here is [REDACTED] for you"
    assert redact_secrets("token AKIAABCDEFGHIJKLMNOP leaked") == "token [REDACTED] leaked"
    assert redact_secrets("Authorization: Bearer abc123.def456-ghi") == "Authorization: [REDACTED]"
    assert redact_secrets("api_key: super-secret-value") == "[REDACTED]"
    assert redact_secrets(r"path C:\Users\alice\secrets.txt") == "path [REDACTED]\\secrets.txt"


def test_redact_secrets_leaves_ordinary_text_untouched():
    text = "富士山の標高は3776メートルです。"
    assert redact_secrets(text) == text


def test_trace_entry_to_dict_applies_redaction_to_nested_output():
    entry = TraceEntry(
        phase="respond",
        agent_id="claude-code",
        attempt=1,
        status="succeeded",
        process_exit_code=0,
        started_at=_ts(0),
        finished_at=_ts(1),
        output={"answer": "my key is sk-abcdefghijklmnopqrstuvwx, do not share"},
    )
    data = entry.to_dict()
    assert "sk-abcdefghijklmnopqrstuvwx" not in data["output"]["answer"]
    assert data["redacted"] is True
    assert data["elapsed_ms"] == 1000


def test_trace_recorder_collects_entries_in_order():
    recorder = TraceRecorder()
    recorder.record(TraceEntry("respond", "a", 1, "succeeded", 0, _ts(0), _ts(1), {"answer": "A"}))
    recorder.record(TraceEntry("respond", "b", 2, "succeeded", 0, _ts(1), _ts(2), {"answer": "B"}))
    entries = recorder.to_list()
    assert [e["agent_id"] for e in entries] == ["a", "b"]
