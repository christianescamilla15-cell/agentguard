"""agentguard — safety guardrails for autonomous agents.

The agent never executes directly. It proposes ProposedAction objects; the
PolicyEngine evaluates each against 8 hard rules and returns a Verdict. Only
ALLOW verdicts reach the executor. The policy never trusts the agent.

Quickstart:
    from agentguard import PolicyConfig, PolicyEngine, ProposedAction

    cfg = PolicyConfig(
        allowed_tools=frozenset({"web_search", "read_file"}),
        max_cost_per_call=0.50,
        max_calls_per_window=10,
        window_seconds=60.0,
        max_cost_burn=20.0,
    )
    engine = PolicyEngine(cfg)

    verdict = engine.evaluate(
        ProposedAction(tool="web_search", args={"q": "x"}, cost=0.05)
    )
    if verdict.allow:
        result = run_tool(...)
        engine.register_action(now_s=time.time(), cost=0.05)
    else:
        log.warning("policy denied: %s", verdict.reason)
"""

from .policy import PolicyConfig, PolicyEngine
from .types import ProposedAction, Verdict

__all__ = ["PolicyConfig", "PolicyEngine", "ProposedAction", "Verdict"]
__version__ = "0.1.0"
