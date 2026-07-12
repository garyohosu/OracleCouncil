"""CliSearchProvider (SPEC §10.2 X-1, X-3): SearchProvider backed by Claude
Code's WebSearch tool. subprocess.run is mocked throughout — CI never
invokes the real `claude` binary (SPEC §18.2); the real capability itself
was confirmed live on 2026-07-13 (QandA X-3)."""

import json
import subprocess
from unittest.mock import patch

import pytest

from oracle_council.adapters.claude import CliSearchProvider
from oracle_council.models import SearchError, SearchResult


def envelope(result_text: str, is_error: bool = False, api_error_status=None) -> str:
    payload = {"type": "result", "is_error": is_error, "result": result_text}
    if api_error_status is not None:
        payload["api_error_status"] = api_error_status
    return json.dumps(payload)


def completed(stdout: str, stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


def sources_json(*urls: str) -> str:
    return json.dumps(
        {"sources": [{"url": u, "title": f"Title {i}", "snippet": f"Snippet {i}"} for i, u in enumerate(urls)]}
    )


class TestSuccessfulSearch:
    def test_returns_ranked_search_results_from_claude_websearch(self):
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(envelope(sources_json("https://a.example", "https://b.example")))
            results = CliSearchProvider().search("python list vs dict", limit=5)

        assert results == [
            SearchResult("https://a.example", "Title 0", "Snippet 0", 1, "claude-code-websearch", results[0].retrieved_at),
            SearchResult("https://b.example", "Title 1", "Snippet 1", 2, "claude-code-websearch", results[1].retrieved_at),
        ]

    def test_invokes_claude_with_websearch_only_not_full_tool_access(self):
        """The whole point of X-3 is that only WebSearch is allowed — never
        the unrestricted `--tools ""` (disable-all, i.e. no tools) or a
        broader allowlist that could write files or run shell commands."""
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(envelope(sources_json("https://a.example")))
            CliSearchProvider().search("q", limit=3)

        cmd = run.call_args.args[0]
        assert "--tools" in cmd
        assert cmd[cmd.index("--tools") + 1] == "WebSearch"
        assert "--safe-mode" in cmd
        assert "--no-session-persistence" in cmd

    def test_limit_truncates_even_when_model_returns_more(self):
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(
                envelope(sources_json(*[f"https://{i}.example" for i in range(5)]))
            )
            results = CliSearchProvider().search("q", limit=2)
        assert len(results) == 2
        assert [r.rank for r in results] == [1, 2]

    def test_malformed_entries_are_skipped_not_fatal(self):
        payload = json.dumps({"sources": [{"title": "no url"}, {"url": "https://ok.example"}]})
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(envelope(payload))
            results = CliSearchProvider().search("q", limit=5)
        assert [r.url for r in results] == ["https://ok.example"]


class TestSearchErrors:
    def test_quota_exceeded_maps_to_search_quota_exceeded(self):
        body = envelope("out of usage credits", is_error=True, api_error_status=429)
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(body)
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "SEARCH_QUOTA_EXCEEDED"

    def test_auth_required_maps_to_search_auth_required(self):
        body = envelope("unauthorized", is_error=True, api_error_status=401)
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(body)
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "SEARCH_AUTH_REQUIRED"

    def test_unparseable_envelope_is_invalid_search_response(self):
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed("not json at all")
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "INVALID_SEARCH_RESPONSE"

    def test_missing_sources_key_is_invalid_search_response(self):
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed(envelope(json.dumps({"not_sources": []})))
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "INVALID_SEARCH_RESPONSE"

    def test_nonzero_exit_without_classified_error_is_search_unavailable(self):
        with patch("oracle_council.adapters.claude.subprocess.run") as run:
            run.return_value = completed("", stderr="boom", returncode=1)
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "SEARCH_UNAVAILABLE"

    def test_command_not_found_is_search_unavailable(self):
        with patch("oracle_council.adapters.claude.subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "SEARCH_UNAVAILABLE"

    def test_timeout_is_search_timeout(self):
        with patch(
            "oracle_council.adapters.claude.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=180),
        ):
            with pytest.raises(SearchError) as excinfo:
                CliSearchProvider().search("q", limit=3)
        assert excinfo.value.code == "SEARCH_TIMEOUT"
