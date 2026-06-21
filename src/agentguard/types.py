"""Shared types — kept dependency-free on purpose.

agentguard works with PROPOSED actions, not executed ones. The agent (the LLM
or strategy) produces a ProposedAction; the PolicyEngine returns a Verdict. If
ALLOW, the executor runs it. The policy never trusts the agent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProposedAction:
    """An action the agent wants to take. Fully untrusted.

    Attributes:
        tool: identifier of the tool / action (must be in the allowlist).
        args: opaque payload — not inspected by the policy engine.
            Validate inside the tool implementation if needed.
        cost: estimated cost of running this action, in caller-defined units
            (USD, tokens, calls, etc.). The same unit is used for caps and
            budgets in PolicyConfig.
        actor: optional identifier of who/what is proposing (agent name,
            tenant id, session id). Useful for per-actor scoping in the
            future; not yet enforced.
    """

    tool: str
    args: dict
    cost: float
    actor: str = ""


@dataclass(frozen=True)
class Verdict:
    """Decision returned by PolicyEngine.evaluate()."""

    allow: bool
    reason: str  # human-readable; includes a stable DENY:<rule> prefix on denies
