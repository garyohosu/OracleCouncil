from __future__ import annotations

import contextlib
import ipaddress
import socket
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import BaseHandler, Request, build_opener

from .models import EvidenceCollectionResult, SearchError, SearchResult


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


class _NoRedirect(BaseHandler):
    """urllib.request.OpenerDirector.add_handler() requires a BaseHandler
    instance (`isinstance` check) — this class previously had no base class
    at all, so `SafeHttpFetcher()` with its default opener crashed on
    construction with TypeError. Every unit test injected a mock `opener`
    directly, so this path was never actually exercised until a real
    end-to-end fetch attempt (found running the CliSearchProvider spike)."""

    def http_error_301(self, req, fp, code, msg, headers):
        return fp
    http_error_302 = http_error_303 = http_error_307 = http_error_308 = http_error_301


@contextlib.contextmanager
def _pinned_dns(host: str, ip: str):
    orig_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(h, port, *args, **kwargs):
        if h == host:
            return orig_getaddrinfo(ip, port, *args, **kwargs)
        return orig_getaddrinfo(h, port, *args, **kwargs)

    socket.getaddrinfo = patched_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = orig_getaddrinfo


from urllib.request import HTTPHandler, HTTPSHandler

class _PinnedHTTPHandler(HTTPHandler):
    def __init__(self, host: str, ip: str):
        super().__init__()
        self.host = host
        self.ip = ip

    def http_open(self, req):
        with _pinned_dns(self.host, self.ip):
            return super().http_open(req)


class _PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, host: str, ip: str):
        super().__init__()
        self.host = host
        self.ip = ip

    def https_open(self, req):
        with _pinned_dns(self.host, self.ip):
            return super().https_open(req)


class SafeHttpFetcher:
    ALLOWED_TYPES = ("text/", "application/json", "application/xml")

    def __init__(self, *, timeout: float = 10.0, max_bytes: int = 2 * 1024 * 1024,
                 resolver: Callable[[str], Iterable[str]] | None = None, opener=None) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._resolver = resolver or self._resolve
        self._opener = opener or build_opener(_NoRedirect())

    def fetch(self, url: str, *, max_redirects: int = 3) -> FetchedEvidence:
        current = self._iri_to_uri(url)
        for _ in range(max_redirects + 1):
            parsed = urlparse(current)
            pinned_ip = self._resolve_and_pin(current)
            try:
                request = Request(current, headers={"User-Agent": "OracleCouncil/0.1"}, method="GET")
            except UnicodeError as exc:
                raise EvidenceFetchError("INVALID_URL_ENCODING", "URL must be a valid URI") from exc

            from urllib.request import OpenerDirector
            if isinstance(self._opener, OpenerDirector):
                opener = build_opener(
                    _NoRedirect(),
                    _PinnedHTTPHandler(parsed.hostname, pinned_ip),
                    _PinnedHTTPSHandler(parsed.hostname, pinned_ip)
                )
            else:
                opener = self._opener

            try:
                response = opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("Location")
                    if not location:
                        raise EvidenceFetchError("FETCH_FAILED", "redirect without location") from exc
                    current = self._iri_to_uri(urljoin(current, location))
                    continue
                raise EvidenceFetchError("FETCH_FAILED", f"HTTP {exc.code}") from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise EvidenceFetchError("FETCH_FAILED", "HTTP fetch failed") from exc
            status = getattr(response, "status", getattr(response, "code", 200))
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise EvidenceFetchError("FETCH_FAILED", "redirect without location")
                current = self._iri_to_uri(urljoin(current, location))
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

    def _resolve_and_pin(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
            raise EvidenceFetchError("UNSAFE_URL", "only http(s) URLs without credentials are allowed")
        try:
            addresses = list(self._resolver(parsed.hostname))
        except socket.gaierror as exc:
            raise EvidenceFetchError("FETCH_FAILED", "DNS resolution failed") from exc
        if not addresses:
            raise EvidenceFetchError("FETCH_FAILED", "DNS resolution returned no addresses")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise EvidenceFetchError("UNSAFE_URL", "private or local destination")
        return addresses[0]

    def _validate_url(self, url: str) -> None:
        self._resolve_and_pin(url)

    @staticmethod
    def _resolve(host: str) -> Iterable[str]:
        return {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}

    @staticmethod
    def _iri_to_uri(url: str) -> str:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname.encode("idna").decode("ascii") if parsed.hostname else ""
        except (UnicodeError, ValueError) as exc:
            raise EvidenceFetchError("INVALID_URL_ENCODING", "URL must be encodable as URI") from exc
        try:
            netloc = hostname
            if parsed.port is not None:
                netloc = f"{netloc}:{parsed.port}"
            if parsed.username:
                userinfo = quote(parsed.username, safe="%")
                if parsed.password:
                    userinfo += ":" + quote(parsed.password, safe="%")
                netloc = f"{userinfo}@{netloc}"
            path = quote(parsed.path, safe="/%:@!$&'()*+,;=")
            query = quote(parsed.query, safe="/?:@!$&'()*+,;=%")
            fragment = quote(parsed.fragment, safe="/?:@!$&'()*+,;=%")
        except (UnicodeError, ValueError) as exc:
            raise EvidenceFetchError("INVALID_URL_ENCODING", "URL must be encodable as URI") from exc
        return urlunsplit((parsed.scheme, netloc, path, query, fragment))


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

    def collect(self, claims: list[dict]) -> list[dict]:
        return list(self.collect_with_metrics(claims).evidence)

    def collect_with_metrics(self, claims: list[dict]) -> EvidenceCollectionResult:
        """Phase-0 compatibility bridge for Orchestrator.collect(claims).

        This is intentionally narrower than the full SPEC §10.2 collection
        engine: no counter-search, authority scoring, independence analysis,
        90s run budget, or document-volume budget. It only lets the
        experimental CLI search path feed conservative evidence candidates
        into the existing verify flow.
        """
        selected = sorted(
            (
                claim
                for claim in claims
                if _importance_value(claim.get("importance")) in ("critical", "major")
            ),
            key=lambda claim: (
                0 if _importance_value(claim.get("importance")) == "critical" else 1,
                str(claim.get("claim_id", "")),
            ),
        )[:5]

        evidence: list[dict] = []
        metrics = _empty_evidence_metrics()
        metrics["target_claim_count"] = len(selected)
        for claim in selected:
            claim_id = str(claim.get("claim_id", ""))
            query = str(claim.get("text", ""))
            metrics["search_count"] += 1
            try:
                results = sorted(
                    self._searcher.search(query, 5)[:5],
                    key=lambda result: result.rank,
                )
            except SearchError as exc:
                metrics["evidence_count"] = len(evidence)
                _increment_code(metrics["search_error_codes"], exc.code)
                setattr(exc, "evidence_metrics", deepcopy(metrics))
                setattr(exc, "partial_evidence", tuple(deepcopy(item) for item in evidence))
                raise
            metrics["candidate_count"] += len(results)
            successes = 0
            for result in results:
                if successes >= 3:
                    break
                metrics["fetch_attempt_count"] += 1
                try:
                    document = self._fetcher.fetch(result.url)
                except EvidenceFetchError as exc:
                    metrics["fetch_failure_count"] += 1
                    _increment_code(metrics["fetch_error_codes"], exc.code)
                    continue
                evidence.append(
                    {
                        "evidence_id": f"web-{claim_id}-{result.rank}",
                        "claim_id": claim_id,
                        "url": document.url,
                        "title": result.title,
                        "excerpt": document.content[:1200],
                        "content_type": document.content_type,
                        "retrieved_at": document.fetched_at or result.retrieved_at,
                        "source": result.source,
                        "rank": result.rank,
                        "authority": "other",
                        "directness": "indirect",
                        "stance": "neutral",
                        "freshness": "unknown",
                        "notes": "experimental cli-search evidence",
                    }
                )
                successes += 1
                metrics["fetch_success_count"] += 1
            if successes > 0:
                metrics["claims_with_evidence_count"] += 1
        metrics["evidence_count"] = len(evidence)
        return EvidenceCollectionResult(evidence=tuple(evidence), metrics=metrics)


def _importance_value(value) -> str:
    return getattr(value, "value", value)


def _empty_evidence_metrics() -> dict:
    return {
        "search_count": 0,
        "candidate_count": 0,
        "fetch_attempt_count": 0,
        "fetch_success_count": 0,
        "fetch_failure_count": 0,
        "evidence_count": 0,
        "target_claim_count": 0,
        "claims_with_evidence_count": 0,
        "search_error_codes": {},
        "fetch_error_codes": {},
    }


def _increment_code(codes: dict, code: str) -> None:
    codes[code] = codes.get(code, 0) + 1
