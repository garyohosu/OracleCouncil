"""Regression coverage for the live-testing finding in QandA W-5: a 429
"out of usage credits" response contains neither "quota" nor "session
limit", so naive substring checks misclassified it as EXECUTION_ERROR."""

import json

from oracle_council.adapters.base import classify_cli_error


def test_structured_429_usage_credits_is_quota_exceeded():
    stdout = json.dumps(
        {
            "type": "result",
            "is_error": True,
            "api_error_status": 429,
            "result": "You're out of usage credits. Run /usage-credits to keep using Fable 5.",
        }
    )
    assert classify_cli_error(stdout, "") == "QUOTA_EXCEEDED"


def test_structured_429_rate_limit_text_is_rate_limited():
    stdout = json.dumps(
        {"is_error": True, "api_error_status": 429, "result": "You have hit the rate limit, retry later."}
    )
    assert classify_cli_error(stdout, "") == "RATE_LIMITED"


def test_structured_401_is_auth_required():
    stdout = json.dumps({"is_error": True, "api_error_status": 401, "result": "unauthorized"})
    assert classify_cli_error(stdout, "") == "AUTH_REQUIRED"


def test_plain_text_quota_message_still_detected():
    assert classify_cli_error("", "session limit reached") == "QUOTA_EXCEEDED"
    assert classify_cli_error("", "quota exceeded for this key") == "QUOTA_EXCEEDED"


def test_plain_text_auth_message_still_detected():
    assert classify_cli_error("please login again", "") == "AUTH_REQUIRED"


def test_unmatched_error_returns_none_and_falls_back_to_execution_error():
    assert classify_cli_error("", "some unrelated crash trace") is None


def test_non_json_stdout_does_not_raise():
    assert classify_cli_error("not json at all {{{", "") is None
