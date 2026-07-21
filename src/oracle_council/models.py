from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import re
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


class ClaimRole(StrEnum):
    USER_PREMISE = "user_premise"
    PROPOSED_ANSWER = "proposed_answer"
    CONTEXTUAL = "contextual"


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
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    output: dict[str, Any]
    usage: Usage | None = None
    # S-8: OS exit code of the child CLI process that produced this result.
    # None when no child process exists (Fake agents) or the code could not
    # be observed. 0 does not imply semantic success on its own.
    process_exit_code: int | None = None


class AgentExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class PhaseStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AgentFailure(RuntimeError):
    """A structured agent-execution failure carrying the SPEC §8.2 error code."""

    def __init__(
        self,
        error_code: str,
        message: str = "",
        public_summary: str | None = None,
        process_exit_code: int | None = None,
    ) -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.public_summary = safe_public_summary(public_summary)
        # S-8: OS exit code of the failed child process, when one ran and its
        # code was observable (command-not-found, timeout, and launch
        # failures stay None). Never used to derive the public error_code.
        self.process_exit_code = process_exit_code


_PHASE_NAMES = {
    "respond",
    "claim_extract",
    "evidence_collect",
    "verify",
    "criticize",
    "synthesize",
    "audit",
    "clarify",
}
_SCHEMA_FIELD_NAMES = {
    "answer",
    "claims",
    "claim_id",
    "importance",
    "status",
    "claim_role",
    "text",
    "critique",
    "issues",
    "issue_id",
    "issue_type",
    "severity",
    "refined_question",
    "assumptions",
    "questions",
    "options",
    "note",
}
_JSON_TYPE_NAMES = {"array", "object", "string", "number", "boolean", "null"}
_SIMPLE_PUBLIC_SUMMARIES = {
    "malformed JSON",
    "code fence detected",
    "leading text detected",
    "trailing text detected",
}
_EXECUTION_SUMMARIES = {
    "process exited with a non-zero status",
    "process could not be started",
    "execution failed without a recognized error pattern",
    "execution failed unexpectedly",
}
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,80}$")


def _contains_control_or_surrogate(value: str) -> bool:
    return any(
        ord(ch) < 32
        or 0x7F <= ord(ch) <= 0x9F
        or 0xD800 <= ord(ch) <= 0xDFFF
        for ch in value
    )


def safe_public_summary(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 200:
        return None
    if _contains_control_or_surrogate(value):
        return None
    if value in _SIMPLE_PUBLIC_SUMMARIES:
        return value
    if value in _EXECUTION_SUMMARIES:
        return value
    if re.fullmatch(
        r"[a-z_]+ (process exited with a non-zero status|process could not be started|execution failed without a recognized error pattern|execution failed unexpectedly)\.",
        value,
    ):
        return value if value.split(" ", 1)[0] in _PHASE_NAMES else None
    if value.startswith("missing field: "):
        field = value.removeprefix("missing field: ")
        return value if field in _SCHEMA_FIELD_NAMES else None
    for prefix in ("unexpected field: ", "string too short for field: ", "string too long for field: ", "too few items for field: ", "too many items for field: "):
        if value.startswith(prefix):
            field = value.removeprefix(prefix)
            return value if field in _SCHEMA_FIELD_NAMES else None
    if value.startswith("missing fields: "):
        fields = value.removeprefix("missing fields: ").split(", ")
        return value if fields and all(field in _SCHEMA_FIELD_NAMES for field in fields) else None
    match = re.fullmatch(
        r"invalid type for field: ([a-z_]+); expected ([a-z]+); actual ([a-z]+)",
        value,
    )
    if match:
        field, expected, actual = match.groups()
        if (
            field in _SCHEMA_FIELD_NAMES
            and expected in _JSON_TYPE_NAMES
            and actual in _JSON_TYPE_NAMES
        ):
            return value
    if value.startswith("invalid enum for field: "):
        field = value.removeprefix("invalid enum for field: ")
        return value if field in _SCHEMA_FIELD_NAMES else None
    return None


def safe_error_summary(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 200:
        return None
    if _contains_control_or_surrogate(value):
        return None
    match = re.fullmatch(r"([a-z_]+) invalid output: (.+)\.", value)
    if match:
        phase, detail = match.groups()
        return value if phase in _PHASE_NAMES and safe_public_summary(detail) else None
    match = re.fullmatch(r"([a-z_]+) execution ended with ([A-Z][A-Z0-9_]{1,80})\.", value)
    if match:
        phase, code = match.groups()
        return value if phase in _PHASE_NAMES and _ERROR_CODE_RE.fullmatch(code) else None
    match = re.fullmatch(r"([a-z_]+) (process exited with a non-zero status|process could not be started|execution failed without a recognized error pattern|execution failed unexpectedly)\.", value)
    if match:
        return value if match.group(1) in _PHASE_NAMES else None
    return None


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


class SearchError(RuntimeError):
    """SearchProvider Contract error (K-2/X-1). Distinct from EvidenceFetchError:
    a search failure means no candidate URLs were even found, whereas a fetch
    failure means a specific URL could not be retrieved."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class SearchResult:
    """SPEC §10.2 SearchProvider Contract (X-1)."""

    url: str
    title: str
    snippet: str
    rank: int
    source: str
    retrieved_at: str


@dataclass(frozen=True)
class Claim:
    claim_id: str
    importance: ClaimImportance
    status: ClaimStatus
    text: str = ""
    claim_role: ClaimRole = ClaimRole.PROPOSED_ANSWER

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Claim:
        return cls(
            claim_id=value["claim_id"],
            importance=ClaimImportance(value["importance"]),
            status=ClaimStatus(value.get("status", ClaimStatus.UNVERIFIED)),
            text=value.get("text", ""),
            claim_role=ClaimRole(value.get("claim_role", ClaimRole.PROPOSED_ANSWER)),
        )


@dataclass(frozen=True)
class AgentExecutionRecord:
    """One attempt of one agent call (SPEC §15.8). Retries never replace the
    failed record; they reference it via retry_of."""

    execution_id: str
    run_id: str
    agent_id: str
    phase: str
    status: AgentExecutionStatus
    started_at: datetime
    finished_at: datetime
    elapsed_ms: int
    # S-8: the child CLI process's own OS exit code; never the Oracle exit
    # code. None for Fake agents and whenever the code was unobservable.
    process_exit_code: int | None = None
    error_code: str | None = None
    error_summary: str | None = None
    raw_diagnostic: str | None = None
    retry_of: str | None = None
    substitute_for: str | None = None

    def __post_init__(self) -> None:
        if self.retry_of is not None and self.substitute_for is not None:
            raise ValueError("retry_of and substitute_for are mutually exclusive")


@dataclass
class PhaseRecord:
    """One phase of one run (SPEC §15.8). Re-audit and revision add executions
    to the existing synthesize/audit phase; they never create a second
    instance (minimum success counts are per phase name, STATE §5)."""

    phase_id: str
    run_id: str
    phase: str
    minimum_success_count: int
    status: PhaseStatus | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    success_count: int = 0
    error_code: str | None = None
    error_summary: str | None = None
    outcome: str | None = None  # EvidenceOutcome; evidence_collect only
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceCollectionResult:
    evidence: tuple[dict[str, Any], ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(deepcopy(item) for item in self.evidence))
        object.__setattr__(self, "metrics", deepcopy(self.metrics))


@dataclass(frozen=True)
class RunMetadataRecord:
    """The metadata snapshot fixed at run termination (SPEC §15.8, O-5).
    This snapshot is the source of truth; consumers must not re-aggregate
    it from the event log."""

    run_id: str
    created_at: datetime
    mode: str
    status: RunStatus
    result_classification: ResultClassification
    consensus_status: str
    participant_count: int
    claim_count: int
    evidence_count: int
    error_codes: tuple[str, ...]
    elapsed_ms: int
    content_saved: bool
    # S-8: the Oracle Council CLI's own exit code (SPEC §13.4), snapshotted
    # at run termination. Child process codes are never aggregated here.
    oracle_exit_code: int
    participants: tuple[str, ...] = ()
    # W-11/W-12: the real, final audit status (e.g. "changes_required" for a
    # withheld run), not the "approved" placeholder cli.py used to hardcode -
    # this makes "why was this withheld" reconstructible from the persisted
    # metadata snapshot alone.
    audit_status: str | None = None
    agent_snapshots: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["created_at"] = self.created_at.isoformat()
        value["error_codes"] = list(self.error_codes)
        value["participants"] = list(self.participants)
        value["agent_snapshots"] = list(self.agent_snapshots)
        return value


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: RunStatus
    result_classification: ResultClassification
    final_answer: str | None
    call_count: int
    # S-8: the Oracle Council CLI's own exit code (SPEC §13.4). The child
    # process codes live on each AgentExecutionRecord.process_exit_code.
    oracle_exit_code: int
    mode: str = "verify"
    claims: tuple[Claim, ...] = ()
    audit_issues: tuple[AuditIssue, ...] = ()
    phases: tuple[PhaseRecord, ...] = ()
    executions: tuple[AgentExecutionRecord, ...] = ()
    metadata: RunMetadataRecord | None = None
    evidence: tuple[dict[str, Any], ...] = ()
    participants: tuple[str, ...] = ()
    # W-11: the CLI's --json "question"/"answer" blocks previously hardcoded
    # the SPEC Sec14 illustrative example text ("元の質問" etc.) instead of the
    # real values; these fields carry the real per-Run data through to cli.py.
    original_question: str | None = None
    refined_question: str | None = None
    clarification_status: str = "ready"
    clarification_assumptions: tuple[str, ...] = ()
    audit_status: str | None = None
    agent_snapshots: tuple["AgentProbeSnapshot", ...] = ()

    @property
    def exit_code(self) -> int:
        """Read-only compatibility alias for pre-S-8 callers; the stored
        field of record is oracle_exit_code. New code must not use this."""
        return self.oracle_exit_code

    @property
    def external_verification(self) -> bool:
        return self.mode != "quick"


@dataclass(frozen=True)
class AgentCapabilities:
    adapter_family: str
    adapter_version: str
    cli_version: str
    supported_phases: tuple[str, ...]
    supports_read_only: bool = True
    supports_no_tools: bool = True


@dataclass(frozen=True)
class ProbeResult:
    status: str
    capabilities: AgentCapabilities | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.status == other
        return super().__eq__(other)


@dataclass(frozen=True)
class AgentProbeSnapshot:
    agent_id: str
    status: str
    capabilities: dict[str, Any]
    probed_at: datetime
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "capabilities": dict(self.capabilities),
            "probed_at": self.probed_at.isoformat(),
            "error_code": self.error_code,
        }
