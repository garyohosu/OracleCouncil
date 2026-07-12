from __future__ import annotations

import json
from typing import Any

from ..models import AgentFailure


def classify_cli_error(stdout: str, stderr: str) -> str | None:
    """Map a failed CLI invocation to a SPEC §8.2 error code, or None if no
    known pattern matched (the caller falls back to EXECUTION_ERROR).

    Claude Code's `--output-format json` wraps API errors as structured JSON
    with an explicit `api_error_status` (e.g. 429 for "out of usage
    credits"); that is checked first since it is unambiguous. Free-text
    stdout/stderr is the fallback for CLIs that emit plain error text.
    Found via live testing (QandA W-5 follow-up): a 429 "out of usage
    credits" response contained neither "quota" nor "session limit", so the
    original substring checks misclassified it as EXECUTION_ERROR and the
    adapter's own retry/skip logic never engaged.
    """
    combined = f"{stderr}\n{stdout}"
    lowered = combined.lower()

    parsed = None
    for candidate in (stdout, stderr):
        try:
            parsed = json.loads(candidate.strip())
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if isinstance(parsed, dict) and parsed.get("is_error"):
        status = parsed.get("api_error_status")
        result_text = str(parsed.get("result", "")).lower()
        if status in (401, 403) or "unauthorized" in result_text:
            return "AUTH_REQUIRED"
        if status == 429:
            return "RATE_LIMITED" if "rate limit" in result_text else "QUOTA_EXCEEDED"

    if (
        "session limit" in lowered
        or "usage credit" in lowered
        or "out of usage" in lowered
        or "quota" in lowered
    ):
        return "QUOTA_EXCEEDED"
    if "rate limit" in lowered:
        return "RATE_LIMITED"
    if "auth" in lowered or "login" in lowered:
        return "AUTH_REQUIRED"
    return None


# SPEC §10.4 / §10.5 enums. Found via live testing (QandA W-5 follow-up):
# a real model returned importance="high", which is not a member of this
# set. The old check only verified `claims` was a list, so the malformed
# value reached Claim.from_dict() and crashed there as an unhandled
# ValueError ("internal_error", not a controlled AgentFailure). SPEC §8.5
# requires schema validation to happen in the Adapter before the
# Orchestrator ever sees the output, so it belongs here, not downstream.
_CLAIM_IMPORTANCE_VALUES = {"critical", "major", "minor"}
_CLAIM_STATUS_VALUES = {
    "verified", "supported", "contradicted", "conflicting", "unverified", "not_applicable",
}


def _validate_claims(claims: Any) -> None:
    if not isinstance(claims, list):
        raise AgentFailure("INVALID_OUTPUT", "claims must be an array")
    for item in claims:
        if not isinstance(item, dict):
            raise AgentFailure("INVALID_OUTPUT", "each claim must be an object")
        if "claim_id" not in item:
            raise AgentFailure("INVALID_OUTPUT", "claim missing claim_id")
        importance = item.get("importance")
        if importance not in _CLAIM_IMPORTANCE_VALUES:
            raise AgentFailure("INVALID_OUTPUT", f"invalid claim importance: {importance!r}")
        # Missing status defaults to UNVERIFIED downstream (Claim.from_dict);
        # a present-but-invalid value (including explicit null) is rejected.
        if "status" in item and item["status"] not in _CLAIM_STATUS_VALUES:
            raise AgentFailure("INVALID_OUTPUT", f"invalid claim status: {item['status']!r}")


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
    if phase in ("claim_extract", "verify"):
        _validate_claims(output["claims"])
    if phase == "audit" and output["status"] not in {"approved", "changes_required", "blocked"}:
        raise AgentFailure("INVALID_OUTPUT", "invalid audit status")
    return output
