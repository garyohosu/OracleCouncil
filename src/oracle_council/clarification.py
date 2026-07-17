"""ClarificationEngine (S-4, QandA S-4.1-S-4.4).

Two-stage design (QandA S-4.1): `inspect()` applies deterministic defaults
and template rules (SPEC Sec7.5 tier 1/2, QandA S-4.2) and, only when a
critical ambiguity remains (QandA S-4.3), signals that the Clarifier Agent
must be consulted. `evaluate_agent_output()` validates the Agent's
structured response against the clarify phase schema and applies the SPEC
Sec7.2/Sec7.5 decision rules to produce the final ClarificationResult. The
two methods are kept separate so the "decide deterministically" and
"validate what the Agent said" responsibilities never blur together.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any

from .phase_schema import validate_phase_schema

STATUSES = (
    "ready",
    "ready_with_assumptions",
    "needs_clarification",
    "premise_issue",
    "unsupported",
    "safety_blocked",
)

# Statuses that stop before a Run is created (SPEC Sec7.5, Sec13.4 exit code 2).
STOP_STATUSES = frozenset({"needs_clarification", "premise_issue", "unsupported", "safety_blocked"})


class ClarificationStopError(RuntimeError):
    """Raised when clarification determines the question cannot proceed to a
    Run. No Run is created for this call; the caller (CLI) maps `status` and
    `exit_code` to a pre-flight stop result (SPEC Sec13.4), the same way
    InsufficientAgentsError is handled today.
    """

    def __init__(self, status: str, message: str = "", exit_code: int = 2) -> None:
        super().__init__(message or status)
        self.status = status
        self.exit_code = exit_code


@dataclass
class ClarificationResult:
    """The final clarification verdict, however it was reached."""

    status: str
    refined_question: str
    assumptions: list[str] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown clarification status: {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "refined_question": self.refined_question,
            "assumptions": list(self.assumptions),
            "questions": [dict(item) for item in self.questions],
            "note": self.note,
        }


@dataclass
class ClarificationPreCheck:
    """Result of `ClarificationEngine.inspect()`.

    `agent_required=False` means tier 1/2 fully resolved the question;
    `result` carries the final ClarificationResult and the Clarifier Agent
    is never consulted. `agent_required=True` means a critical ambiguity
    (QandA S-4.3) survived tiers 1/2; `result` is None, and `status` carries
    the provisional value ("needs_clarification") that would apply if the
    Agent could not be consulted at all.
    """

    agent_required: bool
    result: ClarificationResult | None
    assumptions: list[str]
    ambiguities: list[str]
    status: str


# ---------------------------------------------------------------------------
# Tier 1: deterministic defaults (QandA S-4.2). These only ever fill in
# assumptions; they never by themselves require the Clarifier Agent.
# ---------------------------------------------------------------------------

_TIME_SENSITIVE_RE = re.compile(
    r"(最新|現在|今日|今年|今の|直近|現行|"
    r"\bnow\b|\bcurrent(ly)?\b|\btoday\b|\blatest\b|\bthis year\b)",
    re.IGNORECASE,
)


def default_assumptions(question: str, context: dict[str, Any] | None) -> list[str]:
    ctx = context or {}
    assumptions = [
        "出力形式の指定なし: 通常のテキスト回答とします",
        "対象読者の指定なし: 一般読者向けとします",
        "長さの指定なし: 簡潔な回答とします",
        "言語の指定なし: 質問文の主要言語で回答します",
    ]
    tz_name = ctx.get("timezone", "実行環境のタイムゾーン")
    assumptions.append(f"タイムゾーンの指定なし: {tz_name}を使用します")
    if _TIME_SENSITIVE_RE.search(question):
        now = ctx.get("now") or datetime.now(timezone.utc).isoformat()
        assumptions.append(
            f"時点の指定なし: 時事性のある質問のため現在時点（{now}）とします"
        )
    else:
        assumptions.append(
            "時点の指定なし: 時事性のない質問のため時点は指定しません"
        )
    return assumptions


# ---------------------------------------------------------------------------
# Tier 2: template rules (QandA S-4.2). A match means the question is
# handled by one of the seven fixed templates without the Clarifier Agent.
# ---------------------------------------------------------------------------

_TEMPLATE_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("summarize", re.compile("要約|まとめて|サマリ")),
    ("explain", re.compile("なぜ|どうして|理由|仕組み|とは|説明して")),
    ("compare", re.compile("比較|違い|vs\\.?|対　")),
    ("list", re.compile("一覧|ランキング|リストアップ|列挙")),
    ("code", re.compile("コード|実装して|プログラム|関数を書いて|スクリプト")),
    ("proofread", re.compile("校正|添削|直して|自然な文章")),
    ("research", re.compile("調べて|調査して|リサーチ")),
)


def match_template(question: str) -> str | None:
    for name, pattern in _TEMPLATE_PATTERNS:
        if pattern.search(question):
            return name
    return None


# ---------------------------------------------------------------------------
# Tier 3 trigger: critical ambiguity detection (QandA S-4.3). Deliberately
# conservative - only explicit, high-confidence signals escalate to the
# Clarifier Agent; anything not clearly matching one of these six
# categories defaults to resolved (no agent call), so ordinary questions
# ("q", "富士山の標高は？") are never affected.
# ---------------------------------------------------------------------------

_UNCLEAR_CHOICE_RE = re.compile("どちら|どっち")
_UNSPECIFIED_REFERENT_RE = re.compile(r"^(これ|それ|あれ)(は|を|が)")
_CONTRADICTION_RE = re.compile(
    "(だが|しかし|一方で|でも).{0,15}(しないで|するな|やめて|禁止)"
)
_IRREVERSIBLE_UNCLEAR_RE = re.compile(
    "(これ|それ|あれ|全部|すべて)?を?"
    "(削除|送信|購入|公開|投稿|消去)して"
)


def detect_critical_ambiguities(question: str) -> list[str]:
    """Tier 3 trigger (QandA S-4.3): returns a non-empty list only when the
    question clearly matches one of the six critical-ambiguity categories.
    """
    found: list[str] = []
    if _UNCLEAR_CHOICE_RE.search(question):
        found.append("比較対象または指示対象が特定できません")
    if _UNSPECIFIED_REFERENT_RE.match(question.strip()):
        found.append("指示対象が特定できません")
    if _CONTRADICTION_RE.search(question):
        found.append("指示同士が矛盾しています")
    if _IRREVERSIBLE_UNCLEAR_RE.search(question):
        found.append("取り返しのつきにくい操作の対象または範囲が不明です")
    return found


class ClarificationEngine:
    """See module docstring: `inspect()` is the deterministic pre-check
    (tiers 1/2 + the tier-3 trigger check); `evaluate_agent_output()`
    validates and interprets the Clarifier Agent's structured response.
    """

    def inspect(self, question: str, context: dict[str, Any] | None = None) -> ClarificationPreCheck:
        assumptions = default_assumptions(question, context)
        ambiguities = detect_critical_ambiguities(question)
        if ambiguities:
            return ClarificationPreCheck(
                agent_required=True,
                result=None,
                assumptions=assumptions,
                ambiguities=ambiguities,
                status="needs_clarification",
            )
        # Either a template resolved it, or no template matched but no
        # critical ambiguity was found either: SPEC Sec7.5 tier 1/2 default
        # to a usable answer, recording whatever defaults were assumed.
        status = "ready_with_assumptions" if assumptions else "ready"
        result = ClarificationResult(
            status=status,
            refined_question=question,
            assumptions=assumptions,
        )
        return ClarificationPreCheck(
            agent_required=False,
            result=result,
            assumptions=assumptions,
            ambiguities=[],
            status=status,
        )

    def evaluate_agent_output(
        self,
        question: str,
        context: dict[str, Any] | None,
        output: dict[str, Any],
    ) -> ClarificationResult:
        validated = validate_phase_schema("clarify", output)
        status = validated["status"]
        refined_question = validated.get("refined_question") or question
        assumptions = list(validated.get("assumptions", []))
        questions = list(validated.get("questions", []))
        note = validated.get("note", "")
        # SPEC Sec7.2/Sec7.5: a critical open question always forces
        # needs_clarification, except when the Agent already reported a
        # more specific stop condition (premise_issue/unsupported/
        # safety_blocked), which must not be downgraded to a generic one.
        has_critical = any(item.get("importance") == "critical" for item in questions)
        if has_critical and status not in ("unsupported", "safety_blocked", "premise_issue"):
            status = "needs_clarification"
        return ClarificationResult(
            status=status,
            refined_question=refined_question,
            assumptions=assumptions,
            questions=questions,
            note=note,
        )
