import json

import pytest

from oracle_council.adapters.base import validate_phase_output
from oracle_council.phase_schema import get_phase_schema, validate_phase_schema


def test_all_phase_resources_are_loadable_and_closed():
    for phase in ("respond", "claim_extract", "verify", "criticize", "synthesize", "audit"):
        schema = get_phase_schema(phase)
        assert schema["additionalProperties"] is False
        assert json.dumps(schema)


def test_schema_is_deep_copied_and_unknown_phase_fails_closed():
    schema = get_phase_schema("respond")
    schema["properties"]["answer"]["maxLength"] = 1
    assert get_phase_schema("respond")["properties"]["answer"]["maxLength"] == 6000
    with pytest.raises(ValueError):
        get_phase_schema("unknown")


def test_formal_bounds_and_unexpected_fields_are_rejected():
    with pytest.raises(Exception):
        validate_phase_output("respond", {"answer": "", "secret": "hidden"})
    with pytest.raises(Exception):
        validate_phase_schema("claim_extract", {"claims": [{"claim_id": "x", "importance": "major", "status": "unverified", "claim_role": "proposed_answer", "text": "x"} for _ in range(21)]})
