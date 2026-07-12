import pytest

from oracle_council.adapters.base import validate_phase_output
from oracle_council.models import AgentFailure


def test_phase_schema_accepts_required_fields():
    assert validate_phase_output("respond", {"answer": "ok"})["answer"] == "ok"
    assert validate_phase_output("audit", {"status": "approved"})["status"] == "approved"


@pytest.mark.parametrize(
    ("phase", "output"),
    [("respond", {}), ("claim_extract", {"claims": "not-array"}), ("audit", {"status": "maybe"})],
)
def test_phase_schema_rejects_invalid_output(phase, output):
    with pytest.raises(AgentFailure) as error:
        validate_phase_output(phase, output)
    assert error.value.error_code == "INVALID_OUTPUT"
