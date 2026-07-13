"""Run-level result classification (SPEC v0.3.6 §15.3).

The final classification is derived by the Orchestrator with a two-stage
deterministic rule, never by an agent:

Stage 1 (safety gate): decide whether the answer may be published at all.
Stage 2 (classification): pick the classification for a publishable answer,
first matching row wins.

The SPEC v0.3.6 table is exhaustive after stage 1, so the trailing default
is unreachable; it stays as a defensive fallback that avoids overstating
certainty (QandA W-1).
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import Claim, ClaimImportance, ClaimRole, ClaimStatus, ResultClassification

_PRINCIPAL = (ClaimImportance.CRITICAL, ClaimImportance.MAJOR)
_CONFIRMED = (ClaimStatus.VERIFIED, ClaimStatus.SUPPORTED)


def is_withheld(claims: Iterable[Claim]) -> bool:
    """Stage 1: return True when the answer must not be published."""
    claims = tuple(claims)
    has_publish_claim = any(c.claim_role is not ClaimRole.USER_PREMISE for c in claims)
    for claim in claims:
        if has_publish_claim and claim.claim_role is ClaimRole.USER_PREMISE:
            continue
        if claim.importance is ClaimImportance.CRITICAL and claim.status in (
            ClaimStatus.UNVERIFIED,
            ClaimStatus.CONTRADICTED,
        ):
            return True
        if claim.importance is ClaimImportance.MAJOR and claim.status is ClaimStatus.CONTRADICTED:
            return True
    return False


def classify(claims: Iterable[Claim]) -> ResultClassification:
    """Two-stage classification. Returns WITHHELD when stage 1 blocks."""
    claims = tuple(claims)
    if is_withheld(claims):
        return ResultClassification.WITHHELD
    non_user_premise = [c for c in claims if c.claim_role is not ClaimRole.USER_PREMISE]
    if non_user_premise:
        claims = tuple(non_user_premise)

    verifiable = [c for c in claims if c.status is not ClaimStatus.NOT_APPLICABLE]
    principals = [c for c in verifiable if c.importance in _PRINCIPAL]
    minors = [c for c in verifiable if c.importance is ClaimImportance.MINOR]

    if not verifiable:
        return ResultClassification.UNVERIFIED
    if any(c.status is ClaimStatus.CONFLICTING for c in principals):
        return ResultClassification.CONFLICTING
    if principals and all(c.status is ClaimStatus.UNVERIFIED for c in principals):
        return ResultClassification.UNVERIFIED
    if any(c.status is ClaimStatus.UNVERIFIED for c in principals):
        return ResultClassification.PARTIALLY_VERIFIED
    if any(
        c.status in (ClaimStatus.UNVERIFIED, ClaimStatus.CONFLICTING, ClaimStatus.CONTRADICTED)
        for c in minors
    ):
        return ResultClassification.PARTIALLY_VERIFIED
    if all(c.status in _CONFIRMED for c in verifiable):
        return ResultClassification.VERIFIED
    return ResultClassification.PARTIALLY_VERIFIED
