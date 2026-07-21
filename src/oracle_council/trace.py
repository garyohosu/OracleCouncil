"""X-9: opt-in per-phase raw response visibility (--trace / --trace-output).

Normal `oracle ask` runs never expose raw Agent output anywhere (SPEC §15.8 /
§11.5): CLI JSON, storage, and history show all pass through allowlisted
fixed-template summaries only. This module exists solely for the explicit,
user-requested trace path, and never touches the Storage Contract - trace
entries are held in memory for the run and only ever written to stdout/
stderr or a caller-specified file, never to `data/` JSONL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Best-effort, not exhaustive: this is a defense-in-depth scrub of an Agent's
# free-form natural-language output before it is ever displayed or written,
# not a guarantee that no secret-shaped text can appear in a model response.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|passwd)\b\s*[:=]\s*\S+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"/Users/[^/\s]+"),
]

REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> str:
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


@dataclass(frozen=True)
class TraceEntry:
    """One Agent call, for --trace display only (never persisted to storage)."""

    phase: str
    agent_id: str
    attempt: int
    status: str
    process_exit_code: int | None
    started_at: datetime
    finished_at: datetime
    output: dict[str, Any] | None
    redacted: bool = True

    @property
    def elapsed_ms(self) -> int:
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "agent_id": self.agent_id,
            "attempt": self.attempt,
            "status": self.status,
            "process_exit_code": self.process_exit_code,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "elapsed_ms": self.elapsed_ms,
            "output": _redact_value(self.output) if self.output is not None else None,
            "redacted": self.redacted,
        }


@dataclass
class TraceRecorder:
    """Collects TraceEntry records in memory only, for one Run."""

    entries: list[TraceEntry] = field(default_factory=list)

    def record(self, entry: TraceEntry) -> None:
        self.entries.append(entry)

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]
