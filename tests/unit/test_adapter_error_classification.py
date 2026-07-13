"""Regression coverage for the live-testing finding in QandA W-5: a 429
"out of usage credits" response contains neither "quota" nor "session
limit", so naive substring checks misclassified it as EXECUTION_ERROR."""

import json
from types import SimpleNamespace

import pytest

from oracle_council.adapters.base import classify_cli_error, execution_failure_summary
from oracle_council.models import AgentRequest, AgentFailure


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


@pytest.mark.parametrize(
    "message",
    [
        "Not logged in",
        "Please log in again",
        "Authentication required",
        "Invalid API key",
        "missing api key",
        "api key is missing",
        "access token expired",
        "refresh token has expired. Please log out and sign in again.",
        "refresh token was revoked",
        "refresh token was already used",
    ],
)
def test_explicit_auth_failure_phrases_are_auth_required(message):
    assert classify_cli_error("", message) == "AUTH_REQUIRED"


@pytest.mark.parametrize(
    "message",
    [
        "authoritative source unavailable",
        "authority lookup failed",
        "authentic response could not be parsed",
        "author field was missing",
        "OAuth documentation was not found",
        "login page documentation could not be fetched",
        "authorization policy rejected the request",
    ],
)
def test_unrelated_auth_words_are_not_auth_required(message):
    assert classify_cli_error("", message) is None


def test_unmatched_error_returns_none_and_falls_back_to_execution_error():
    assert classify_cli_error("", "some unrelated crash trace") is None


def test_non_json_stdout_does_not_raise():
    assert classify_cli_error("not json at all {{{", "") is None


def test_execution_summary_is_fixed_and_does_not_include_diagnostics():
    summary = execution_failure_summary("verify", "subprocess_nonzero_exit")
    assert summary == "verify process exited with a non-zero status."
    assert "SECRET" not in summary
    assert AgentFailure("EXECUTION_ERROR", "stderr SECRET", public_summary=summary).public_summary == summary


@pytest.mark.parametrize(
    ("module_name", "adapter_name"),
    [("oracle_council.adapters.claude", "ClaudeAdapter"), ("oracle_council.adapters.codex", "CodexAdapter")],
)
def test_adapters_sanitize_unrecognized_nonzero_exit(monkeypatch, module_name, adapter_name):
    module = __import__(module_name, fromlist=[adapter_name])
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:  # probe
            return SimpleNamespace(returncode=0, stdout="1.0", stderr="")
        return SimpleNamespace(
            returncode=17,
            stdout="model output SECRET-PROMPT",
            stderr="opaque failure API-KEY-123",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    adapter = getattr(module, adapter_name)("test-agent")
    request = AgentRequest("run-1", "exec-1", "verify", {"question": "private question"})
    with pytest.raises(AgentFailure) as error:
        adapter.execute(request)
    assert error.value.error_code == "EXECUTION_ERROR"
    assert error.value.public_summary == "verify process exited with a non-zero status."
    assert "SECRET" not in error.value.public_summary
    assert "API-KEY" not in error.value.public_summary


@pytest.mark.parametrize(
    ("module_name", "adapter_name"),
    [("oracle_council.adapters.claude", "ClaudeAdapter"), ("oracle_council.adapters.codex", "CodexAdapter")],
)
def test_adapters_sanitize_process_launch_failure(monkeypatch, module_name, adapter_name):
    module = __import__(module_name, fromlist=[adapter_name])
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(returncode=0, stdout="1.0", stderr="")
        raise PermissionError("C:\\Users\\secret\\api-key.txt")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    adapter = getattr(module, adapter_name)("test-agent")
    request = AgentRequest("run-1", "exec-1", "verify", {"question": "private question"})
    with pytest.raises(AgentFailure) as error:
        adapter.execute(request)
    assert error.value.error_code == "EXECUTION_ERROR"
    assert error.value.public_summary == "verify process could not be started."
