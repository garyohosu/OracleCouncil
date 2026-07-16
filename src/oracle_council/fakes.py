from __future__ import annotations

from collections import deque
from typing import Iterable

from .models import AgentRequest, AgentResult, SearchError, SearchResult, Usage


class ScriptedAgentAdapter:
    def __init__(self, outputs: Iterable[dict]) -> None:
        self._outputs = deque(outputs)
        self.requests: list[AgentRequest] = []
        self._cancelled: set[str] = set()

    def execute(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        if request.execution_id in self._cancelled:
            from .models import AgentFailure
            raise AgentFailure("CANCELLED", "execution cancelled")
        if not self._outputs:
            raise RuntimeError("script exhausted")
        item = self._outputs.popleft()
        if isinstance(item, BaseException):
            raise item
        return AgentResult(item, Usage(100, 20))

    def cancel(self, execution_id: str) -> None:
        self._cancelled.add(execution_id)


class FakeEvidenceProvider:
    def __init__(self, evidence: list[dict] | None = None) -> None:
        self.evidence = evidence or []
        self.calls = 0

    def collect(self, claims: list[dict]) -> list[dict]:
        self.calls += 1
        return list(self.evidence)


class FakeSearchProvider:
    """SearchProvider Contract (X-1) fake: deterministic results or a
    scripted failure, no network."""

    def __init__(
        self, results: list[SearchResult] | None = None, failure: SearchError | None = None
    ) -> None:
        self._results = results or []
        self._failure = failure
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int) -> list[SearchResult]:
        self.calls.append((query, limit))
        if self._failure is not None:
            raise self._failure
        return list(self._results)[:limit]

