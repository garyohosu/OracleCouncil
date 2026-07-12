from __future__ import annotations

from collections import deque
from typing import Iterable

from .models import AgentRequest, AgentResult, Usage


class ScriptedAgentAdapter:
    def __init__(self, outputs: Iterable[dict]) -> None:
        self._outputs = deque(outputs)
        self.requests: list[AgentRequest] = []

    def execute(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        if not self._outputs:
            raise RuntimeError("script exhausted")
        item = self._outputs.popleft()
        if isinstance(item, BaseException):
            raise item
        return AgentResult(item, Usage(100, 20))


class FakeEvidenceProvider:
    def __init__(self, evidence: list[dict] | None = None) -> None:
        self.evidence = evidence or []
        self.calls = 0

    def collect(self, claims: list[dict]) -> list[dict]:
        self.calls += 1
        return list(self.evidence)

