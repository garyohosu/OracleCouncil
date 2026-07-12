from __future__ import annotations

from typing import Any

from ..models import AgentFailure


def validate_phase_output(phase: str, output: Any) -> dict[str, Any]:
    """Validate the phase envelope before it reaches Orchestrator state."""
    if not isinstance(output, dict):
        raise AgentFailure("INVALID_OUTPUT", "structured output must be an object")
    required: dict[str, tuple[str, ...]] = {
        "respond": ("answer",),
        "claim_extract": ("claims",),
        "verify": ("claims",),
        "criticize": ("critique",),
        "synthesize": ("answer",),
        "audit": ("status",),
    }
    for key in required.get(phase, ()):
        if key not in output:
            raise AgentFailure("INVALID_OUTPUT", f"missing field: {key}")
    if phase in ("respond", "criticize", "synthesize") and not isinstance(
        output[required[phase][0]], str
    ):
        raise AgentFailure("INVALID_OUTPUT", "text field must be a string")
    if phase in ("claim_extract", "verify") and not isinstance(output["claims"], list):
        raise AgentFailure("INVALID_OUTPUT", "claims must be an array")
    if phase == "audit" and output["status"] not in {"approved", "changes_required", "blocked"}:
        raise AgentFailure("INVALID_OUTPUT", "invalid audit status")
    return output
