"""Regression coverage for the live-testing finding (QandA W-5 follow-up):
Claude Code's --output-format json wraps the model's text in a CLI metadata
envelope; the phase JSON lives in envelope["result"], not at the top level."""

import json

from oracle_council.adapters.base import build_phase_input, extract_json_object
from oracle_council.adapters.claude import _build_prompt
from oracle_council.models import AgentRequest


def test_prompt_includes_schema_hint_for_known_phase():
    prompt = _build_prompt("respond", "Say hello")
    assert prompt.startswith("Say hello")
    assert '"answer"' in prompt


def test_prompt_passes_through_for_unknown_phase():
    assert _build_prompt("unknown_phase", "raw question") == "raw question"


def test_phase_input_includes_claims_evidence_and_false_premise_guidance():
    request = AgentRequest(
        "run-1",
        "exec-1",
        "audit",
        {
            "question": "q",
            "claims": [{"claim_id": "c1", "text": "correction", "status": "verified"}],
            "evidence": [{"evidence_id": "ev-1", "claim_id": "c1", "title": "source"}],
            "final_answer": "corrected answer",
        },
    )

    prompt = build_phase_input(request)

    assert "Phase: audit" in prompt
    assert '"claims"' in prompt
    assert '"evidence"' in prompt
    assert "correction opportunity" in prompt


def test_synthesize_prompt_requires_single_verdict_structure():
    """2026-07-18 user decision: the user-facing final answer must lead with
    one oracle verdict, not a menu of positions - a real 4-agent run on "Does
    God exist?" produced a hedged, no-conclusion answer before this guidance
    existed. This only governs presentation; SPEC Sec2.2's evidence
    classification (verified/partially_verified/unverified/conflicting/
    withheld) is untouched."""
    request = AgentRequest(
        "run-1", "exec-1", "synthesize",
        {"question": "q", "responses": [], "claims": [], "evidence": [], "critique": ""},
    )

    prompt = build_phase_input(request)

    assert "oracle verdict" in prompt
    assert "single verdict" in prompt
    assert "never" in prompt and "leave the choice to the reader" in prompt
    # "cannot currently be determined" must be explicitly valid as a complete
    # verdict - the guidance must not push the model toward forcing an
    # unsupported true/false claim.
    assert "cannot currently be determined" in prompt
    assert "Do not assert unsupported certainty" in prompt
    # Must not touch evidence classification wording.
    assert "does not change the underlying evidence classification" in prompt


def test_audit_prompt_checks_verdict_structure_without_dictating_conclusion():
    request = AgentRequest(
        "run-1", "exec-1", "audit",
        {"question": "q", "claims": [], "evidence": [], "final_answer": "answer text"},
    )

    prompt = build_phase_input(request)

    assert "oracle verdict" in prompt
    assert "final_answer" in prompt  # placeholder claim_id convention for structure-only issues
    assert "must not be treated as a missing conclusion" in prompt
    assert "Do not require any particular verdict" in prompt
    assert "do not require unsupported certainty" in prompt


def test_oracle_verdict_guidance_is_scoped_to_synthesize_and_audit_only():
    for phase, payload in (
        ("respond", {"question": "q"}),
        ("claim_extract", {"question": "q", "responses": []}),
        ("verify", {"question": "q", "claims": [], "evidence": []}),
        ("criticize", {"question": "q", "responses": [], "claims": [], "evidence": []}),
    ):
        request = AgentRequest("run-1", "exec-1", phase, payload)
        prompt = build_phase_input(request)
        assert "oracle verdict" not in prompt, f"unexpected oracle verdict guidance leaked into phase={phase}"


def test_result_classification_enum_unchanged_by_oracle_verdict_decision():
    """Canary for the user's explicit instruction: SPEC Sec2.2's 5-value
    evidence classification must not be weakened or replaced by the
    user-facing verdict structure change."""
    from oracle_council.models import ResultClassification

    assert {member.value for member in ResultClassification} == {
        "verified", "partially_verified", "unverified", "conflicting", "withheld",
    }


def test_claim_extract_prompt_excludes_ai_self_commentary():
    """W-12: a real 4-agent run extracted "the AI avoids giving a definitive
    view" as a claim about the *answer*, which verify then marked
    contradicted and which (correctly, per unchanged evidence rules)
    triggered a Stage 1 withhold - even though it had nothing to do with
    the question being asked."""
    request = AgentRequest(
        "run-1", "exec-1", "claim_extract",
        {"question": "Does God exist?", "responses": [{"answer": "..."}]},
    )

    prompt = build_phase_input(request)

    assert "avoids being definitive" in prompt
    assert "response behavior, wording, structure, or generation process" in prompt
    assert "Exception: if the question itself asks about an AI's nature" in prompt
    assert 'mark its importance as "minor"' in prompt


def test_oracle_verdict_guidance_recognizes_inconclusive_verdict_in_audit():
    request = AgentRequest(
        "run-1", "exec-1", "audit",
        {"question": "q", "claims": [], "evidence": [], "final_answer": "answer text"},
    )

    prompt = build_phase_input(request)

    assert "cannot currently be determined" in prompt
    assert "is a valid, complete verdict" in prompt


def test_extract_plain_json_object():
    assert extract_json_object('{"answer": "hi"}') == {"answer": "hi"}


def test_extract_json_from_markdown_fence():
    text = '```json\n{"answer": "hi"}\n```'
    assert extract_json_object(text) == {"answer": "hi"}


def test_extract_json_surrounded_by_prose():
    text = 'Sure, here you go:\n{"answer": "hi"}\nHope that helps!'
    assert extract_json_object(text) == {"answer": "hi"}


def test_extract_raises_when_no_json_present():
    import pytest

    with pytest.raises(json.JSONDecodeError):
        extract_json_object("just plain text, no braces here")
