"""Deterministic agent-to-phase assignment (SPEC §6.2-§6.4).

Selection is never random: agents are ranked per phase by role_priority
(higher wins) and ties fall back to configuration order. The same set of
available agents therefore always yields the same plan, including the
substitute chosen after an agent drops out (callers re-plan with the
reduced agent list).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


class InsufficientAgentsError(RuntimeError):
    """Fewer than two usable agents: pre-flight stop, no Run is created (V-1)."""

    status = "insufficient_agents"
    exit_code = 3


@dataclass(frozen=True)
class RegisteredAgent:
    agent_id: str
    adapter: Any
    role_priority: dict[str, int] = field(default_factory=dict)


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


def plan_assignments(agents: Sequence[RegisteredAgent]) -> AssignmentPlan:
    if len({agent.agent_id for agent in agents}) != len(agents):
        raise ValueError("agent_id must be unique")
    if len(agents) < 2:
        raise InsufficientAgentsError(
            "verify requires two distinct responders and a separate auditor"
        )

    responder_ranking = rank(agents, "respond")
    responders = (responder_ranking[0], responder_ranking[1])

    synthesize = rank(agents, "synthesize")[0]
    audit_ranking = rank(agents, "audit", exclude=frozenset({synthesize.agent_id}))
    if not audit_ranking:
        raise InsufficientAgentsError("auditor distinct from synthesizer is unavailable")

    return AssignmentPlan(
        responders=responders,
        claim_extract=rank(agents, "claim_extract")[0],
        verify=rank(agents, "verify")[0],
        criticize=rank(agents, "criticize")[0],
        synthesize=synthesize,
        audit=audit_ranking[0],
    )
