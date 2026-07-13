"""Regression coverage for the live-testing finding (QandA W-5 follow-up):
Claude Code's --output-format json wraps the model's text in a CLI metadata
envelope; the phase JSON lives in envelope["result"], not at the top level."""

import json

from oracle_council.adapters.base import build_phase_input
from oracle_council.adapters.claude import _build_prompt, _extract_json_object
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


def test_extract_plain_json_object():
    assert _extract_json_object('{"answer": "hi"}') == {"answer": "hi"}


def test_extract_json_from_markdown_fence():
    text = '```json\n{"answer": "hi"}\n```'
    assert _extract_json_object(text) == {"answer": "hi"}


def test_extract_json_surrounded_by_prose():
    text = 'Sure, here you go:\n{"answer": "hi"}\nHope that helps!'
    assert _extract_json_object(text) == {"answer": "hi"}


def test_extract_raises_when_no_json_present():
    import pytest

    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("just plain text, no braces here")
