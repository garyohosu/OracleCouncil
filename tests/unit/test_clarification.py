"""S-4: ClarificationEngine unit tests (QandA S-4.1-S-4.4).

inspect() (tiers 1/2 + the tier-3 trigger check) and evaluate_agent_output()
(schema validation + SPEC Sec7.2/Sec7.5 decision rules) are tested
separately, matching their separated responsibilities (QandA S-4.1).
"""
import pytest

from oracle_council.clarification import (
    ClarificationEngine,
    ClarificationResult,
    STATUSES,
    STOP_STATUSES,
)
from oracle_council.phase_schema import SchemaValidationError


@pytest.fixture
def engine():
    return ClarificationEngine()


# -- inspect(): tier 1 (deterministic defaults) --------------------------


def test_inspect_bare_question_resolves_without_agent(engine):
    result = engine.inspect("q")
    assert result.agent_required is False
    assert result.result is not None
    assert result.result.status in ("ready", "ready_with_assumptions")


def test_inspect_ordinary_factual_question_resolves_without_agent(engine):
    result = engine.inspect("富士山の標高は？")
    assert result.agent_required is False
    assert result.result.status in ("ready", "ready_with_assumptions")


def test_inspect_records_assumptions_for_unspecified_defaults(engine):
    result = engine.inspect("富士山の標高は？")
    assert result.result.status == "ready_with_assumptions"
    assert len(result.result.assumptions) > 0


def test_inspect_time_sensitive_question_assumes_current_time(engine):
    result = engine.inspect("最新のニュースは？")
    joined = " ".join(result.result.assumptions)
    assert "現在時点" in joined


def test_inspect_non_time_sensitive_question_does_not_assume_current_time(engine):
    result = engine.inspect("富士山の標高は？")
    joined = " ".join(result.result.assumptions)
    assert "時点は指定しません" in joined


# -- inspect(): tier 2 (template rules) -----------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "この記事を要約して",
        "この薬の服用量は？",  # existing orchestrator fixture question; must resolve, not ambiguous
        "AとBの違いを比較して",
        "おすすめの本を一覧にして",
        "Pythonでソートするコードを書いて",
        "この文章を校正して",
        "最新の為替レートを調べて",
    ],
)
def test_inspect_template_matching_questions_resolve_without_agent(engine, question):
    result = engine.inspect(question)
    assert result.agent_required is False
    assert result.result.status in ("ready", "ready_with_assumptions")


# -- inspect(): tier 3 trigger (critical ambiguity) -----------------------


def test_inspect_unclear_choice_requires_agent(engine):
    result = engine.inspect("どちらのプランが良いですか？")
    assert result.agent_required is True
    assert result.result is None
    assert result.status == "needs_clarification"
    assert len(result.ambiguities) > 0


def test_inspect_unspecified_referent_requires_agent(engine):
    result = engine.inspect("これを削除して")
    assert result.agent_required is True


def test_inspect_conflicting_instructions_requires_agent(engine):
    result = engine.inspect("公開してください。しかし公開しないでください。")
    assert result.agent_required is True


def test_inspect_irreversible_unclear_scope_requires_agent(engine):
    result = engine.inspect("全部消去して")
    assert result.agent_required is True


def test_inspect_precheck_carries_assumptions_even_when_agent_required(engine):
    result = engine.inspect("どちらのプランが良いですか？")
    assert isinstance(result.assumptions, list)
    assert len(result.assumptions) > 0


# -- evaluate_agent_output(): schema validation ---------------------------


@pytest.mark.parametrize("status", list(STATUSES))
def test_evaluate_agent_output_accepts_all_six_statuses(engine, status):
    output = {
        "status": status,
        "refined_question": "q",
        "assumptions": [],
        "questions": [],
    }
    result = engine.evaluate_agent_output("q", None, output)
    assert result.status == status


def test_premise_issue_is_not_dropped_from_schema(engine):
    # Regression guard: the aborted 2026-07-16 attempt's schema enum was
    # missing premise_issue (SPEC Sec7.2's sixth status); this pins it down.
    assert "premise_issue" in STATUSES


def test_evaluate_agent_output_missing_field_raises_schema_error(engine):
    output = {"status": "ready", "assumptions": [], "questions": []}
    with pytest.raises(SchemaValidationError):
        engine.evaluate_agent_output("q", None, output)


def test_evaluate_agent_output_invalid_enum_raises_schema_error(engine):
    output = {
        "status": "not_a_real_status",
        "refined_question": "q",
        "assumptions": [],
        "questions": [],
    }
    with pytest.raises(SchemaValidationError):
        engine.evaluate_agent_output("q", None, output)


def test_evaluate_agent_output_rejects_unexpected_field(engine):
    output = {
        "status": "ready",
        "refined_question": "q",
        "assumptions": [],
        "questions": [],
        "unexpected_field": "x",
    }
    with pytest.raises(SchemaValidationError):
        engine.evaluate_agent_output("q", None, output)


# -- evaluate_agent_output(): SPEC Sec7.2/Sec7.5 decision rules -----------


def test_critical_question_upgrades_ready_with_assumptions_to_needs_clarification(engine):
    output = {
        "status": "ready_with_assumptions",
        "refined_question": "q",
        "assumptions": [],
        "questions": [{"text": "target?", "importance": "critical"}],
    }
    result = engine.evaluate_agent_output("q", None, output)
    assert result.status == "needs_clarification"


def test_non_critical_question_does_not_upgrade_status(engine):
    output = {
        "status": "ready_with_assumptions",
        "refined_question": "q",
        "assumptions": ["region: Tokyo"],
        "questions": [{"text": "preference?", "importance": "minor"}],
    }
    result = engine.evaluate_agent_output("q", None, output)
    assert result.status == "ready_with_assumptions"


@pytest.mark.parametrize("protected_status", ["unsupported", "safety_blocked", "premise_issue"])
def test_critical_question_does_not_downgrade_more_specific_stop_status(engine, protected_status):
    output = {
        "status": protected_status,
        "refined_question": "q",
        "assumptions": [],
        "questions": [{"text": "target?", "importance": "critical"}],
    }
    result = engine.evaluate_agent_output("q", None, output)
    assert result.status == protected_status


def test_stop_statuses_exclude_ready_variants():
    assert "ready" not in STOP_STATUSES
    assert "ready_with_assumptions" not in STOP_STATUSES
    assert STOP_STATUSES == {"needs_clarification", "premise_issue", "unsupported", "safety_blocked"}


def test_clarification_result_rejects_unknown_status():
    with pytest.raises(ValueError):
        ClarificationResult(status="not_a_status", refined_question="q")


def test_clarification_result_to_dict_round_trip():
    result = ClarificationResult(
        status="ready_with_assumptions",
        refined_question="q",
        assumptions=["a"],
        questions=[],
        note="",
    )
    data = result.to_dict()
    assert data["status"] == "ready_with_assumptions"
    assert data["assumptions"] == ["a"]
