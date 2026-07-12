from email.message import Message

import pytest

from oracle_council.evidence import (
    EvidenceFetchError,
    ManualEvidenceProvider,
    SafeHttpFetcher,
    WebEvidenceProvider,
)
from oracle_council.fakes import FakeSearchProvider
from oracle_council.models import SearchError, SearchResult


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
