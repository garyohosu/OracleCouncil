from __future__ import annotations

import ipaddress
import socket
from dataclasses import asdict, dataclass
from typing import Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

from .models import SearchResult


class EvidenceFetchError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


@dataclass(frozen=True)
class FetchedEvidence:
    url: str
    title: str
    content: str
    content_type: str
    fetched_at: str


class _NoRedirect:
    def http_error_301(self, req, fp, code, msg, headers):
        return fp
    http_error_302 = http_error_303 = http_error_307 = http_error_308 = http_error_301


class SafeHttpFetcher:
    ALLOWED_TYPES = ("text/", "application/json", "application/xml")

    def __init__(self, *, timeout: float = 10.0, max_bytes: int = 2 * 1024 * 1024,
                 resolver: Callable[[str], Iterable[str]] | None = None, opener=None) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._resolver = resolver or self._resolve
        self._opener = opener or build_opener(_NoRedirect())

    def fetch(self, url: str, *, max_redirects: int = 3) -> FetchedEvidence:
        current = url
        for _ in range(max_redirects + 1):
            self._validate_url(current)
            request = Request(current, headers={"User-Agent": "OracleCouncil/0.1"}, method="GET")
            try:
                response = self._opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("Location")
                    if not location:
                        raise EvidenceFetchError("FETCH_FAILED", "redirect without location") from exc
                    current = urljoin(current, location)
                    continue
                raise EvidenceFetchError("FETCH_FAILED", f"HTTP {exc.code}") from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise EvidenceFetchError("FETCH_FAILED", "HTTP fetch failed") from exc
            status = getattr(response, "status", getattr(response, "code", 200))
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise EvidenceFetchError("FETCH_FAILED", "redirect without location")
                current = urljoin(current, location)
                continue
            content_type = response.headers.get_content_type()
            if not any(content_type.startswith(prefix) for prefix in self.ALLOWED_TYPES):
                raise EvidenceFetchError("UNSUPPORTED_CONTENT_TYPE", content_type)
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > self.max_bytes:
                raise EvidenceFetchError("DOCUMENT_TOO_LARGE", "content length exceeds limit")
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise EvidenceFetchError("DOCUMENT_TOO_LARGE", "body exceeds limit")
            try:
                text = body.decode(response.headers.get_content_charset() or "utf-8")
            except UnicodeDecodeError as exc:
                raise EvidenceFetchError("FETCH_FAILED", "unsupported encoding") from exc
            return FetchedEvidence(current, "", text, content_type, "")
        raise EvidenceFetchError("TOO_MANY_REDIRECTS")

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
            raise EvidenceFetchError("UNSAFE_URL", "only http(s) URLs without credentials are allowed")
        for address in self._resolver(parsed.hostname):
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise EvidenceFetchError("UNSAFE_URL", "private or local destination")

    @staticmethod
    def _resolve(host: str) -> Iterable[str]:
        return {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}


class ManualEvidenceProvider:
    """SPEC §10.2 `manual`: fixed evidence for tests and E2E runs, no network.

    `documents` maps claim_id to its evidence entries; `default` is returned
    for claims without an entry. Order is deterministic (input order)."""

    def __init__(
        self,
        documents: dict[str, list[dict]] | None = None,
        default: list[dict] | None = None,
    ) -> None:
        self._documents = documents or {}
        self._default = default or []
        self.calls = 0

    def collect(self, claims: list[dict]) -> list[dict]:
        self.calls += 1
        collected: list[dict] = []
        for claim in claims:
            claim_id = claim.get("claim_id", "")
            for document in self._documents.get(claim_id, []):
                collected.append({**document, "claim_id": claim_id})
        if not collected:
            collected = [dict(document) for document in self._default]
        return collected


class SearchProvider(Protocol):
    """SPEC §10.2 SearchProvider Contract (X-1). Returns candidate URLs only;
    it must never fetch document bodies itself — that responsibility stays
    with SafeHttpFetcher (S-1: Orchestrator/WebEvidenceProvider never talk to
    a raw HTTP client directly). A search implementation that also fetches
    content blurs the SSRF boundary S-1 exists to enforce."""

    def search(self, query: str, limit: int) -> list[SearchResult]: ...


class WebEvidenceProvider:
    def __init__(self, fetcher: SafeHttpFetcher, searcher: SearchProvider):
        self._fetcher = fetcher
        self._searcher = searcher

    def search(self, query: str, limit: int = 5) -> list[dict]:
        results = self._searcher.search(query, limit)[:limit]
        return [asdict(result) for result in results]

    def fetch(self, result: dict) -> dict:
        document = self._fetcher.fetch(result["url"])
        return {"url": document.url, "title": result.get("title", ""),
                "excerpt": document.content[:1200], "content_type": document.content_type,
                "fetched_at": document.fetched_at}
