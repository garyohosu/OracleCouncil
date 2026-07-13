from email.message import Message

import pytest

from oracle_council.evidence import (
    EvidenceFetchError,
    FetchedEvidence,
    ManualEvidenceProvider,
    SafeHttpFetcher,
    WebEvidenceProvider,
)
from oracle_council.fakes import FakeSearchProvider
from oracle_council.models import SearchError, SearchResult


def test_safe_http_fetcher_constructs_with_default_opener():
    """Regression: `_NoRedirect` previously had no base class, so
    `urllib.request.build_opener()` rejected it with TypeError and
    `SafeHttpFetcher()` crashed on construction whenever the default opener
    was used. Every other test in this file injects a mock `opener`
    directly, so this path went unexercised until a real end-to-end fetch
    attempt (found running the CliSearchProvider spike, 2026-07-13)."""
    SafeHttpFetcher()  # must not raise


def test_manual_provider_maps_documents_per_claim():
    provider = ManualEvidenceProvider(
        documents={"claim-1": [{"evidence_id": "ev-1"}], "claim-2": [{"evidence_id": "ev-2"}]}
    )
    collected = provider.collect([{"claim_id": "claim-1"}, {"claim_id": "claim-2"}])
    assert [e["evidence_id"] for e in collected] == ["ev-1", "ev-2"]  # deterministic order
    assert all(e["claim_id"] for e in collected)
    assert provider.calls == 1


def test_manual_provider_falls_back_to_default():
    provider = ManualEvidenceProvider(default=[{"evidence_id": "ev-default"}])
    collected = provider.collect([{"claim_id": "claim-x"}])
    assert [e["evidence_id"] for e in collected] == ["ev-default"]
    # same input, same output: manual evidence is repeatable
    assert provider.collect([{"claim_id": "claim-x"}]) == collected


class TestSearchProviderContract:
    """SPEC §10.2 X-1: WebEvidenceProvider only talks to SearchProvider for
    candidates and SafeHttpFetcher for bodies (S-1 responsibility split)."""

    def test_search_returns_dicts_with_all_search_result_fields(self):
        fake = FakeSearchProvider(
            [SearchResult("https://example.com/a", "Title A", "snippet", 1, "fake", "2026-07-12")]
        )
        provider = WebEvidenceProvider(fetcher=object(), searcher=fake)
        results = provider.search("query", limit=5)
        assert results == [
            {
                "url": "https://example.com/a",
                "title": "Title A",
                "snippet": "snippet",
                "rank": 1,
                "source": "fake",
                "retrieved_at": "2026-07-12",
            }
        ]
        assert fake.calls == [("query", 5)]

    def test_search_result_count_is_capped_at_limit(self):
        fake = FakeSearchProvider(
            [SearchResult(f"https://example.com/{i}", "T", "s", i, "fake", "") for i in range(10)]
        )
        provider = WebEvidenceProvider(fetcher=object(), searcher=fake)
        assert len(provider.search("q", limit=3)) == 3

    def test_search_failure_propagates_as_search_error(self):
        fake = FakeSearchProvider(failure=SearchError("SEARCH_QUOTA_EXCEEDED"))
        provider = WebEvidenceProvider(fetcher=object(), searcher=fake)
        with pytest.raises(SearchError) as excinfo:
            provider.search("q", limit=5)
        assert excinfo.value.code == "SEARCH_QUOTA_EXCEEDED"

    @pytest.mark.parametrize(
        "code",
        [
            "SEARCH_AUTH_REQUIRED",
            "SEARCH_QUOTA_EXCEEDED",
            "SEARCH_RATE_LIMITED",
            "SEARCH_TIMEOUT",
            "SEARCH_UNAVAILABLE",
            "INVALID_SEARCH_RESPONSE",
        ],
    )
    def test_all_contract_error_codes_are_constructible(self, code):
        error = SearchError(code)
        assert error.code == code

    def test_fetch_still_goes_through_safe_http_fetcher(self):
        """search() must never fetch bodies itself; only fetch() touches the
        fetcher, and only for one URL at a time (SSRF boundary, S-1)."""

        class RecordingFetcher:
            def __init__(self):
                self.calls = []

            def fetch(self, url):
                self.calls.append(url)
                return FetchedEvidence(url, "T", "content", "text/plain", "")

        from oracle_council.evidence import FetchedEvidence

        fetcher = RecordingFetcher()
        provider = WebEvidenceProvider(fetcher=fetcher, searcher=FakeSearchProvider([]))
        provider.fetch({"url": "https://example.com/x", "title": "T"})
        assert fetcher.calls == ["https://example.com/x"]


class RecordingSearchProvider:
    def __init__(self, results_by_query=None, failure=None):
        self.results_by_query = results_by_query or {}
        self.failure = failure
        self.calls = []

    def search(self, query, limit):
        self.calls.append((query, limit))
        if self.failure:
            raise self.failure
        return list(self.results_by_query.get(query, []))


class RecordingCollectFetcher:
    def __init__(self, documents=None, failures=None):
        self.documents = documents or {}
        self.failures = set(failures or [])
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if url in self.failures:
            raise EvidenceFetchError("FETCH_FAILED")
        return self.documents.get(
            url,
            FetchedEvidence(url, "", f"body for {url}", "text/plain", "2026-07-13T00:00:00+00:00"),
        )


def result(url, rank, title=None):
    return SearchResult(url, title or f"Title {rank}", "snippet", rank, "fake-search", "2026-07-13T00:00:00+00:00")


class TestWebEvidenceProviderCollect:
    def test_collect_processes_critical_then_major_by_claim_id_and_skips_minor(self):
        searcher = RecordingSearchProvider(
            {
                "critical b": [result("https://example.com/cb", 1)],
                "critical a": [result("https://example.com/ca", 1)],
                "major a": [result("https://example.com/ma", 1)],
            }
        )
        provider = WebEvidenceProvider(RecordingCollectFetcher(), searcher)
        provider.collect(
            [
                {"claim_id": "claim-b", "importance": "critical", "text": "critical b"},
                {"claim_id": "claim-minor", "importance": "minor", "text": "minor"},
                {"claim_id": "claim-a", "importance": "critical", "text": "critical a"},
                {"claim_id": "claim-c", "importance": "major", "text": "major a"},
            ]
        )
        assert searcher.calls == [("critical a", 5), ("critical b", 5), ("major a", 5)]

    def test_collect_limits_target_claims_to_five(self):
        claims = [
            {"claim_id": f"claim-{i}", "importance": "major", "text": f"q{i}"}
            for i in range(7)
        ]
        searcher = RecordingSearchProvider({f"q{i}": [result(f"https://example.com/{i}", 1)] for i in range(7)})
        WebEvidenceProvider(RecordingCollectFetcher(), searcher).collect(claims)
        assert [query for query, _ in searcher.calls] == ["q0", "q1", "q2", "q3", "q4"]

    def test_collect_fetches_rank_order_and_caps_successes_per_claim_at_three(self):
        searcher = RecordingSearchProvider(
            {
                "q": [
                    result("https://example.com/3", 3),
                    result("https://example.com/1", 1),
                    result("https://example.com/2", 2),
                    result("https://example.com/4", 4),
                ]
            }
        )
        fetcher = RecordingCollectFetcher()
        evidence = WebEvidenceProvider(fetcher, searcher).collect(
            [{"claim_id": "claim-1", "importance": "major", "text": "q"}]
        )
        assert fetcher.calls == ["https://example.com/1", "https://example.com/2", "https://example.com/3"]
        assert [item["rank"] for item in evidence] == [1, 2, 3]

    def test_collect_excerpt_is_capped_and_uses_conservative_fields(self):
        long_text = "x" * 1300
        fetcher = RecordingCollectFetcher(
            {"https://example.com/a": FetchedEvidence("https://example.com/a", "", long_text, "text/html", "2026-07-13T01:00:00+00:00")}
        )
        searcher = RecordingSearchProvider({"q": [result("https://example.com/a", 4, "Title A")]})
        evidence = WebEvidenceProvider(fetcher, searcher).collect(
            [{"claim_id": "claim-1", "importance": "critical", "text": "q"}]
        )
        assert evidence == [
            {
                "evidence_id": "web-claim-1-4",
                "claim_id": "claim-1",
                "url": "https://example.com/a",
                "title": "Title A",
                "excerpt": "x" * 1200,
                "content_type": "text/html",
                "retrieved_at": "2026-07-13T01:00:00+00:00",
                "source": "fake-search",
                "rank": 4,
                "authority": "other",
                "directness": "indirect",
                "stance": "neutral",
                "freshness": "unknown",
                "notes": "experimental cli-search evidence",
            }
        ]

    def test_collect_skips_only_failed_fetch_urls_and_continues_claim(self):
        searcher = RecordingSearchProvider(
            {"q": [result("https://example.com/fail", 1), result("https://example.com/ok", 2)]}
        )
        fetcher = RecordingCollectFetcher(failures={"https://example.com/fail"})
        evidence = WebEvidenceProvider(fetcher, searcher).collect(
            [{"claim_id": "claim-1", "importance": "major", "text": "q"}]
        )
        assert fetcher.calls == ["https://example.com/fail", "https://example.com/ok"]
        assert [item["url"] for item in evidence] == ["https://example.com/ok"]

    def test_collect_returns_no_evidence_when_all_fetches_fail_for_claim(self):
        searcher = RecordingSearchProvider({"q": [result("https://example.com/fail", 1)]})
        fetcher = RecordingCollectFetcher(failures={"https://example.com/fail"})
        assert WebEvidenceProvider(fetcher, searcher).collect(
            [{"claim_id": "claim-1", "importance": "major", "text": "q"}]
        ) == []

    def test_collect_propagates_search_error(self):
        provider = WebEvidenceProvider(
            RecordingCollectFetcher(),
            RecordingSearchProvider(failure=SearchError("SEARCH_QUOTA_EXCEEDED")),
        )
        with pytest.raises(SearchError) as excinfo:
            provider.collect([{"claim_id": "claim-1", "importance": "major", "text": "q"}])
        assert excinfo.value.code == "SEARCH_QUOTA_EXCEEDED"

    def test_collect_is_stable_for_same_input_and_results(self):
        claims = [{"claim_id": "claim-1", "importance": "major", "text": "q"}]
        searcher = RecordingSearchProvider({"q": [result("https://example.com/a", 1)]})
        first = WebEvidenceProvider(RecordingCollectFetcher(), searcher).collect(claims)
        second = WebEvidenceProvider(RecordingCollectFetcher(), searcher).collect(claims)
        assert first == second
        assert [item["evidence_id"] for item in first] == ["web-claim-1-1"]


class Response:
    def __init__(self, body=b"hello", content_type="text/plain"):
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self._body = body

    def read(self, size=-1):
        return self._body[:size]


class Opener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout):
        return self.response


class SequenceOpener:
    def __init__(self, *responses):
        self.responses = list(responses)

    def open(self, request, timeout):
        return self.responses.pop(0)


def fetcher(opener, addresses=("93.184.216.34",)):
    return SafeHttpFetcher(opener=opener, resolver=lambda host: addresses)


def test_fetches_allowed_text():
    result = fetcher(Opener(Response())).fetch("https://example.com/a")
    assert result.content == "hello"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_rejects_private_and_local_addresses(address):
    with pytest.raises(EvidenceFetchError, match="private"):
        fetcher(Opener(Response()), (address,)).fetch("https://example.com")


def test_rejects_unsupported_content_type():
    with pytest.raises(EvidenceFetchError, match="UNSUPPORTED_CONTENT_TYPE"):
        fetcher(Opener(Response(content_type="image/png"))).fetch("https://example.com")


def test_rejects_oversized_body():
    with pytest.raises(EvidenceFetchError, match="DOCUMENT_TOO_LARGE"):
        SafeHttpFetcher(opener=Opener(Response(b"12345")), max_bytes=4,
                        resolver=lambda host: ["93.184.216.34"]).fetch("https://example.com")


def test_redirect_destination_is_validated_again():
    redirect = Response()
    redirect.status = 302
    redirect.headers["Location"] = "http://internal.example/"
    opener = SequenceOpener(redirect, Response())
    resolver = lambda host: ["127.0.0.1"] if host == "internal.example" else ["93.184.216.34"]
    with pytest.raises(EvidenceFetchError, match="UNSAFE_URL"):
        SafeHttpFetcher(opener=opener, resolver=resolver).fetch("https://example.com")
