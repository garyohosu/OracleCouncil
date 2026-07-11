"""Run-level result classification (SPEC v0.3.6 §15.3).

The final classification is derived by the Orchestrator with a two-stage
deterministic rule, never by an agent:

Stage 1 (safety gate): decide whether the answer may be published at all.
Stage 2 (classification): pick the classification for a publishable answer.

Fall-through cases not covered verbatim by the SPEC table are resolved on
the safe side (see hikitsugi.md §5): a `conflicting` critical claim is
treated like a conflicting major claim, a `contradicted` minor claim
degrades the run to partially_verified, and anything else unmatched
defaults to partially_verified rather than verified.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import Claim, ClaimImportance, ClaimStatus, ResultClassification

_PRINCIPAL = (ClaimImportance.CRITICAL, ClaimImportance.MAJOR)
_CONFIRMED = (ClaimStatus.VERIFIED, ClaimStatus.SUPPORTED)


def is_withheld(claims: Iterable[Claim]) -> bool:
    """Stage 1: return True when the answer must not be published."""
    for claim in claims:
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
    if principals and all(c.status in _CONFIRMED for c in principals):
        return ResultClassification.VERIFIED
    return ResultClassification.PARTIALLY_VERIFIED
