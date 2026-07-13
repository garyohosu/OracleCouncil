import pytest

from oracle_council.classification import classify, is_withheld
from oracle_council.models import Claim, ClaimImportance, ClaimRole, ClaimStatus, ResultClassification


def claim(importance, status, claim_id="c1", role="proposed_answer"):
    return Claim(
        claim_id,
        ClaimImportance(importance),
        ClaimStatus(status),
        claim_role=ClaimRole(role),
    )


# Stage 1: safety gate (SPEC §15.3)
@pytest.mark.parametrize(
    "importance,status",
    [
        ("critical", "unverified"),
        ("critical", "contradicted"),
        ("major", "contradicted"),
    ],
)
def test_stage1_withholds(importance, status):
    assert is_withheld([claim(importance, status)]) is True
    assert classify([claim(importance, status)]) is ResultClassification.WITHHELD


# Stage 2: decision table, first matching row wins
@pytest.mark.parametrize(
    "claims,expected",
    [
        # major conflicting -> conflicting
        ([claim("major", "conflicting"), claim("major", "verified", "c2")], ResultClassification.CONFLICTING),
        # critical conflicting matches the principal-conflicting row (SPEC v0.3.6)
        ([claim("critical", "conflicting")], ResultClassification.CONFLICTING),
        # all principals unverified -> unverified
        ([claim("major", "unverified"), claim("major", "unverified", "c2")], ResultClassification.UNVERIFIED),
        # some major unverified -> partially_verified
        ([claim("major", "verified"), claim("major", "unverified", "c2")], ResultClassification.PARTIALLY_VERIFIED),
        # minors degrade to partially_verified
        ([claim("major", "verified"), claim("minor", "unverified", "c2")], ResultClassification.PARTIALLY_VERIFIED),
        ([claim("major", "verified"), claim("minor", "contradicted", "c2")], ResultClassification.PARTIALLY_VERIFIED),
        # all principals verified/supported -> verified
        ([claim("critical", "verified"), claim("major", "supported", "c2")], ResultClassification.VERIFIED),
        # minors-only, all confirmed -> verified (SPEC row: all verifiable confirmed)
        ([claim("minor", "verified"), claim("minor", "supported", "c2")], ResultClassification.VERIFIED),
        # nothing verifiable -> unverified
        ([], ResultClassification.UNVERIFIED),
        ([claim("major", "not_applicable")], ResultClassification.UNVERIFIED),
    ],
)
def test_stage2_table(claims, expected):
    assert classify(claims) is expected


def test_priority_conflicting_beats_partially_verified():
    claims = [
        claim("major", "conflicting"),
        claim("major", "unverified", "c2"),
        claim("minor", "unverified", "c3"),
    ]
    assert classify(claims) is ResultClassification.CONFLICTING


def test_false_premise_contradiction_does_not_withhold_supported_correction():
    claims = [
        claim("critical", "contradicted", "premise", role="user_premise"),
        claim("critical", "verified", "correction"),
        claim("major", "supported", "context"),
    ]

    assert is_withheld(claims) is False
    assert classify(claims) is ResultClassification.VERIFIED


def test_false_premise_without_supported_correction_still_withholds():
    claims = [
        claim("critical", "contradicted", "premise", role="user_premise"),
        claim("critical", "unverified", "correction"),
    ]

    assert is_withheld(claims) is True
    assert classify(claims) is ResultClassification.WITHHELD


def test_user_premise_conflict_without_unique_correction_stays_conflicting():
    claims = [
        claim("critical", "contradicted", "premise", role="user_premise"),
        claim("critical", "conflicting", "correction"),
    ]

    assert classify(claims) is ResultClassification.CONFLICTING


def test_only_contradicted_user_premise_still_withholds():
    claims = [claim("critical", "contradicted", "premise", role="user_premise")]

    assert is_withheld(claims) is True
    assert classify(claims) is ResultClassification.WITHHELD
