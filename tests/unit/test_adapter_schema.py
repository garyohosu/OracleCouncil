import pytest

from oracle_council.adapters.base import validate_phase_output, extract_json_object
from oracle_council.models import AgentFailure, safe_error_summary, safe_public_summary


def test_phase_schema_accepts_required_fields():
    assert validate_phase_output("respond", {"answer": "ok"})["answer"] == "ok"
    assert validate_phase_output("audit", {"status": "approved", "issues": []})["status"] == "approved"


@pytest.mark.parametrize(
    ("phase", "output"),
    [("respond", {}), ("claim_extract", {"claims": "not-array"}), ("audit", {"status": "maybe"})],
)
def test_phase_schema_rejects_invalid_output(phase, output):
    with pytest.raises(AgentFailure) as error:
        validate_phase_output(phase, output)
    assert error.value.error_code == "INVALID_OUTPUT"
    assert error.value.public_summary is not None


def test_phase_schema_reports_safe_structural_detail_without_raw_value():
    with pytest.raises(AgentFailure) as error:
        validate_phase_output(
            "claim_extract",
            {"claims": [{"claim_id": "c1", "importance": "SECRET-IMPORTANCE", "status": "unverified", "claim_role": "proposed_answer", "text": "claim"}]},
        )

    assert error.value.error_code == "INVALID_OUTPUT"
    assert error.value.public_summary == "invalid enum for field: importance"
    assert "SECRET-IMPORTANCE" in str(error.value)
    assert "SECRET-IMPORTANCE" not in error.value.public_summary


def test_public_summary_allowlist_rejects_arbitrary_strings():
    assert AgentFailure(
        "INVALID_OUTPUT",
        "raw value",
        public_summary="parse failed: SECRET-TOKEN",
    ).public_summary is None
    assert AgentFailure(
        "INVALID_OUTPUT",
        "raw value",
        public_summary="unexpected field: attacker_key",
    ).public_summary is None
    assert AgentFailure(
        "INVALID_OUTPUT",
        "raw value",
        public_summary="output was: https://example.com/token/abc",
    ).public_summary is None


def test_public_summary_rejects_control_characters_and_long_values():
    assert safe_public_summary("missing field: critique\n") is None
    assert safe_public_summary("missing field: critique\x01") is None
    assert safe_public_summary("missing field: " + "a" * 220) is None


def test_public_summary_allows_only_known_schema_fields():
    assert safe_public_summary("missing field: critique") == "missing field: critique"
    assert safe_public_summary("missing fields: critique, severity") == (
        "missing fields: critique, severity"
    )
    assert safe_public_summary("missing field: attacker_key") is None
    assert safe_public_summary("invalid type for field: critique; expected string; actual object") == (
        "invalid type for field: critique; expected string; actual object"
    )
    assert safe_public_summary("invalid type for field: attacker_key; expected string; actual object") is None


def test_safe_error_summary_uses_same_allowlist():
    assert safe_error_summary("criticize invalid output: missing field: critique.") == (
        "criticize invalid output: missing field: critique."
    )
    assert safe_error_summary("criticize invalid output: parse failed: SECRET-TOKEN.") is None
    assert safe_error_summary("criticize invalid output: missing field: critique\n.") is None
    assert safe_error_summary("criticize invalid output: output was: https://example.com.") is None


@pytest.mark.parametrize(
    "summary",
    [
        "verify process exited with a non-zero status.",
        "verify process could not be started.",
        "verify execution failed without a recognized error pattern.",
        "verify execution failed unexpectedly.",
    ],
)
def test_safe_error_summary_allows_fixed_execution_diagnostics(summary):
    assert safe_error_summary(summary) == summary


def test_safe_error_summary_rejects_execution_diagnostic_injection():
    assert safe_error_summary("verify process exited with a non-zero status: SECRET.") is None


def test_extract_json_object_success():
    # Plain JSON
    assert extract_json_object('{"answer": "ok"}') == {"answer": "ok"}

    # JSON with spaces and newlines
    assert extract_json_object('   \n  {"answer": "ok"}  \n ') == {"answer": "ok"}

    # Markdown fenced JSON
    assert extract_json_object('```json\n{"answer": "ok"}\n```') == {"answer": "ok"}
    assert extract_json_object('```\n{"answer": "ok"}\n```') == {"answer": "ok"}

    # Prose before and after
    assert extract_json_object('Here is the result:\n{"answer": "ok"}\nHope this helps!') == {"answer": "ok"}
    assert extract_json_object('```\n{"answer": "ok"}\n```\nSome trailing text.') == {"answer": "ok"}


def test_extract_json_object_failure():
    import json

    # No JSON object at all
    with pytest.raises(json.JSONDecodeError):
        extract_json_object('There is no JSON here.')

    # Malformed JSON (incomplete)
    with pytest.raises(json.JSONDecodeError):
        extract_json_object('{"answer": ')
