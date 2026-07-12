from email.message import Message

import pytest

from oracle_council.evidence import EvidenceFetchError, ManualEvidenceProvider, SafeHttpFetcher


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
