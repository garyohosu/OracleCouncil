from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResultClassification(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    WITHHELD = "withheld"


class ClaimImportance(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ClaimStatus(StrEnum):
    VERIFIED = "verified"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class BudgetRequest:
    run_id: str
    execution_id: str
    phase: str
    estimated_input_tokens: int
    estimated_output_tokens: int


@dataclass
class BudgetReservation:
    reservation_id: str
    run_id: str
    execution_id: str
    phase: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    reserved_call_count: int = 1
    status: ReservationStatus = ReservationStatus.RESERVED
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None


@dataclass(frozen=True)
class BudgetSnapshot:
    reserved_input_tokens: int
    committed_input_tokens: int
    reserved_output_tokens: int
    committed_output_tokens: int
    reserved_call_count: int
    committed_call_count: int


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    event_type: str
    payload: dict[str, Any]
    sequence: int | None = None
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["created_at"] = self.created_at.isoformat()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunEvent:
        return cls(
            run_id=value["run_id"],
            event_type=value["event_type"],
            payload=value["payload"],
            sequence=value["sequence"],
            created_at=datetime.fromisoformat(value["created_at"]),
        )


@dataclass(frozen=True)
class StorageLoadResult:
    events: tuple[RunEvent, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRequest:
    run_id: str
    execution_id: str
    phase: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class AgentResult:
    output: dict[str, Any]
    usage: Usage | None = None


class AgentFailure(RuntimeError):
    """A structured agent-execution failure carrying the SPEC §8.2 error code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code


class AuditIssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


@dataclass
class AuditIssue:
    issue_id: str
    issue_type: str = ""
    severity: str = ""
    claim_id: str | None = None
    status: AuditIssueStatus = AuditIssueStatus.OPEN


@dataclass(frozen=True)
class Claim:
    claim_id: str
    importance: ClaimImportance
    status: ClaimStatus
    text: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Claim:
        return cls(
            claim_id=value["claim_id"],
            importance=ClaimImportance(value["importance"]),
            status=ClaimStatus(value.get("status", ClaimStatus.UNVERIFIED)),
            text=value.get("text", ""),
        )


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: RunStatus
    result_classification: ResultClassification
    final_answer: str | None
    call_count: int
    exit_code: int
    claims: tuple[Claim, ...] = ()
    audit_issues: tuple[AuditIssue, ...] = ()

