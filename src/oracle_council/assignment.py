from __future__ import annotations

"""Deterministic agent-to-phase assignment (SPEC §6.2-§6.4).

Selection is never random: agents are ranked per phase by role_priority
(higher wins) and ties fall back to configuration order. The same set of
available agents therefore always yields the same plan. The plan's candidate
order is retained for the lifetime of a Run; substitution filters that
immutable order by Run-local availability and slot constraints.
"""

from dataclasses import dataclass, field
from typing import Any, Sequence


class InsufficientAgentsError(RuntimeError):
    """Fewer than two usable agents: pre-flight stop, no Run is created (V-1)."""

    status = "insufficient_agents"
    exit_code = 3


MAX_RUN_PARTICIPANTS = 4


def select_run_participants(agents: Sequence["RegisteredAgent"]) -> tuple["RegisteredAgent", ...]:
    """Select the deterministic 2..4 participant set for one Run."""
    return tuple(agents[:MAX_RUN_PARTICIPANTS])


@dataclass(frozen=True)
class RegisteredAgent:
    agent_id: str
    adapter: Any
    role_priority: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseAssignment:
    phase: str
    slot_index: int
    required_success_count: int
    candidate_agent_ids: tuple[str, ...]
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunAgentAvailability:
    agent_id: str
    status: str = "available"
    reason_code: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    run_id: str
    participants: tuple[str, ...]
    phase_assignments: tuple[PhaseAssignment, ...]
    agent_availability: tuple[RunAgentAvailability, ...]
    agent_snapshots: tuple[Any, ...] = ()
    max_run_retries: int = 2
    max_run_substitutions: int = 1
    max_agent_calls: int = 12

    def assignment_for(self, phase: str, slot_index: int = 0) -> PhaseAssignment:
        for assignment in self.phase_assignments:
            if assignment.phase == phase and assignment.slot_index == slot_index:
                return assignment
        raise KeyError((phase, slot_index))


@dataclass(frozen=True)
class AssignmentPlan:
    responders: tuple[RegisteredAgent, RegisteredAgent]
    claim_extract: RegisteredAgent
    verify: RegisteredAgent
    criticize: RegisteredAgent
    synthesize: RegisteredAgent
    audit: RegisteredAgent

    def adapter_for(self, phase: str, respond_index: int = 0) -> RegisteredAgent:
        if phase == "respond":
            return self.responders[respond_index]
        return getattr(self, phase)


def rank(agents: Sequence[RegisteredAgent], phase: str, exclude: frozenset[str] = frozenset()) -> list[RegisteredAgent]:
    candidates = [
        (index, agent)
        for index, agent in enumerate(agents)
        if agent.agent_id not in exclude
    ]
    candidates.sort(key=lambda pair: (-pair[1].role_priority.get(phase, 0), pair[0]))
    return [agent for _, agent in candidates]


_PLAN_ASSIGNMENTS = (
    ("respond", 0, 2, ("distinct_responder",)),
    ("respond", 1, 2, ("distinct_responder",)),
    ("claim_extract", 0, 1, ()),
    ("verify", 0, 1, ()),
    ("criticize", 0, 1, ()),
    ("synthesize", 0, 1, ("auditor_must_remain_distinct",)),
    ("audit", 0, 1, ("synthesizer_must_be_distinct",)),
)


def build_execution_plan(
    run_id: str,
    agents: Sequence[RegisteredAgent],
    snapshots: Sequence[Any] = ()
) -> ExecutionPlan:
    if len({agent.agent_id for agent in agents}) != len(agents):
        raise ValueError("agent_id must be unique")
    selected_agents = select_run_participants(agents)
    if len(selected_agents) < 2:
        raise InsufficientAgentsError(
            "verify requires two distinct responders and a separate auditor"
        )

    # For compatibility, if no snapshots provided, dynamically create from agents
    if not snapshots:
        from .models import AgentProbeSnapshot
        from datetime import datetime, timezone
        dummy_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        temp_snapshots = []
        for agent in selected_agents:
            try:
                status = agent.adapter.probe()
            except AttributeError:
                status = "OK"
            try:
                caps = agent.adapter.capabilities()
            except AttributeError:
                caps = {"supported_models": ["mock-model"]}
            temp_snapshots.append(
                AgentProbeSnapshot(
                    agent_id=agent.agent_id,
                    status=status,
                    capabilities=caps,
                    probed_at=dummy_time
                )
            )
        snapshots = temp_snapshots

    rankings = {phase: tuple(agent.agent_id for agent in rank(selected_agents, phase))
                for phase in {item[0] for item in _PLAN_ASSIGNMENTS}}
    synth_id = rankings["synthesize"][0]
    if not any(agent_id != synth_id for agent_id in rankings["audit"]):
        raise InsufficientAgentsError("auditor distinct from synthesizer is unavailable")

    assignments = tuple(
        PhaseAssignment(phase, slot, required, rankings[phase], constraints)
        for phase, slot, required, constraints in _PLAN_ASSIGNMENTS
    )

    availability_list = []
    for agent in selected_agents:
        snap = next((s for s in snapshots if s.agent_id == agent.agent_id), None)
        if snap:
            availability_list.append(
                RunAgentAvailability(
                    agent_id=agent.agent_id,
                    status="available" if snap.status == "OK" else "unavailable",
                    reason_code=snap.error_code
                )
            )
        else:
            availability_list.append(RunAgentAvailability(agent.agent_id))

    return ExecutionPlan(
        run_id=run_id,
        participants=tuple(agent.agent_id for agent in selected_agents),
        phase_assignments=assignments,
        agent_availability=tuple(availability_list),
        agent_snapshots=tuple(snapshots),
    )


def plan_assignments(agents: Sequence[RegisteredAgent]) -> AssignmentPlan:
    plan = build_execution_plan("compat-plan", agents)
    by_id = {agent.agent_id: agent for agent in agents}
    responders = tuple(by_id[agent_id] for agent_id in plan.assignment_for("respond", 0).candidate_agent_ids[:2])
    synthesize = by_id[plan.assignment_for("synthesize").candidate_agent_ids[0]]
    audit_id = next(
        agent_id for agent_id in plan.assignment_for("audit").candidate_agent_ids
        if agent_id != synthesize.agent_id
    )

    return AssignmentPlan(
        responders=responders,
        claim_extract=by_id[plan.assignment_for("claim_extract").candidate_agent_ids[0]],
        verify=by_id[plan.assignment_for("verify").candidate_agent_ids[0]],
        criticize=by_id[plan.assignment_for("criticize").candidate_agent_ids[0]],
        synthesize=synthesize,
        audit=by_id[audit_id],
    )
