import pytest

from oracle_council.assignment import (
    build_execution_plan,
    InsufficientAgentsError,
    RegisteredAgent,
    plan_assignments,
)


def agent(agent_id, **priority):
    return RegisteredAgent(agent_id, adapter=object(), role_priority=priority)


def test_default_plan_uses_config_order_and_separates_auditor():
    agents = [agent("a"), agent("b")]
    plan = plan_assignments(agents)
    assert [r.agent_id for r in plan.responders] == ["a", "b"]
    assert plan.claim_extract.agent_id == "a"
    assert plan.synthesize.agent_id == "a"
    assert plan.audit.agent_id == "b"  # must differ from synthesizer
    assert plan.synthesize.agent_id != plan.audit.agent_id


def test_same_input_yields_same_plan():
    agents = [agent("a", synthesize=100), agent("b", claim_extract=90), agent("c")]
    assert plan_assignments(agents) == plan_assignments(agents)


def test_role_priority_beats_config_order():
    agents = [agent("a"), agent("b", claim_extract=90, verify=90)]
    plan = plan_assignments(agents)
    assert plan.claim_extract.agent_id == "b"
    assert plan.verify.agent_id == "b"
    assert plan.criticize.agent_id == "a"  # no priority -> config order


def test_auditor_exclusion_is_deterministic_even_when_priorities_collide():
    # b tops both synthesize and audit; auditor must still differ.
    agents = [agent("a"), agent("b", synthesize=100, audit=100)]
    plan = plan_assignments(agents)
    assert plan.synthesize.agent_id == "b"
    assert plan.audit.agent_id == "a"


def test_substitute_selection_after_dropout_is_deterministic():
    full = [agent("a"), agent("b"), agent("c")]
    reduced = [x for x in full if x.agent_id != "a"]  # a dropped out
    plan = plan_assignments(reduced)
    assert [r.agent_id for r in plan.responders] == ["b", "c"]
    assert plan.synthesize.agent_id == "b"
    assert plan.audit.agent_id == "c"
    assert plan == plan_assignments(reduced)


def test_fewer_than_two_agents_is_insufficient():
    with pytest.raises(InsufficientAgentsError) as excinfo:
        plan_assignments([agent("a")])
    assert excinfo.value.exit_code == 3
    assert excinfo.value.status == "insufficient_agents"


def test_duplicate_agent_ids_rejected():
    with pytest.raises(ValueError):
        plan_assignments([agent("a"), agent("a")])


def test_execution_plan_is_deterministic_and_contains_all_slots_and_limits():
    agents = [
        agent("a", respond=100, synthesize=100),
        agent("b", respond=90, audit=100),
        agent("c", verify=100),
    ]
    plans = [build_execution_plan("run-1", agents) for _ in range(10)]
    assert all(plan == plans[0] for plan in plans)
    assert plans[0].configured_agent_ids == ("a", "b", "c")
    assert [(item.phase, item.slot_index) for item in plans[0].phase_assignments] == [
        ("clarify", 0), ("respond", 0), ("respond", 1), ("claim_extract", 0), ("verify", 0),
        ("criticize", 0), ("synthesize", 0), ("audit", 0),
    ]
    assert (plans[0].max_run_retries, plans[0].max_run_substitutions, plans[0].max_agent_calls) == (2, 1, 12)
    assert plans[0].assignment_for("synthesize").candidate_agent_ids[0] != plans[0].assignment_for("audit").candidate_agent_ids[0]


def test_configured_adapters_more_than_five_caps_participants_at_four():
    agents = [
        agent("a", respond=10),
        agent("b", synthesize=90),
        agent("c", audit=50),
        agent("d", verify=30),
        agent("e", criticize=100),
        agent("f", claim_extract=5),
    ]
    plan = build_execution_plan("run-1", agents)
    assert len(plan.participants) == 4
    assert set(plan.participants) == {"b", "c", "d", "e"}
    assert plan.participants == ("b", "c", "d", "e")

    plans = [build_execution_plan("run-1", agents) for _ in range(10)]
    assert all(p.participants == plan.participants for p in plans)


def test_configured_adapters_four_or_fewer_retains_existing_behavior():
    agents = [
        agent("a", respond=100),
        agent("b", synthesize=90),
        agent("c", audit=80),
    ]
    plan = build_execution_plan("run-1", agents)
    assert len(plan.participants) == 3
    assert set(plan.participants) == {"a", "b", "c"}


def test_quick_plan_contains_correct_slots():
    agents = [
        agent("a", respond=100, compare=100),
        agent("b", respond=90, synthesize=100),
    ]
    plan = build_execution_plan("run-1", agents, mode="quick")
    assert plan.mode == "quick"
    assert [(item.phase, item.slot_index) for item in plan.phase_assignments] == [
        ("respond", 0), ("respond", 1), ("compare", 0), ("synthesize", 0)
    ]
    # No distinct auditor constraint exists for quick mode synthesize phase
    assert plan.assignment_for("synthesize").constraints == ()
