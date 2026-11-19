"""Example: wrap an LLM agent's tool calls with agentguard.

Run with: python examples/llm_tool_call_guard.py
"""

import time

from agentguard import PolicyConfig, PolicyEngine, ProposedAction

# Fake "agent" that proposes a sequence of tool calls.
PROPOSED_CALLS = [
    ("web_search", {"q": "AI safety papers 2026"}, 0.05),
    ("read_file", {"path": "notes.md"}, 0.00),
    ("rm_rf_root", {"path": "/"}, 0.01),                  # 4. allowlist DENY
    ("web_search", {"q": "x"}, 0.05),                     # 3rd executed call: fills the window
    ("web_search", {"q": "y"}, 0.05),                     # 6. rate_limit DENY (cfg=3/window)
    ("web_search", {"q": "z"}, 0.05),                     # 6. rate_limit DENY (still in window)
    ("expensive_api", {"q": "x"}, 0.05),                  # 4. allowlist DENY
    ("web_search", {"q": "huge"}, 50.0),                  # 5. per_call_cap DENY
]


def fake_tool(tool: str, args: dict) -> str:
    return f"[tool {tool} returned a result for {args}]"


def main() -> None:
    cfg = PolicyConfig(
        allowed_tools=frozenset({"web_search", "read_file"}),
        max_cost_per_call=1.00,        # $1.00 per call max
        max_calls_per_window=3,        # 3 calls per window
        window_seconds=60.0,           # ...per minute
        max_cost_burn=10.00,           # global lifetime cost cap
        max_cost_per_window=2.00,      # $2.00 cumulative per window
    )
    engine = PolicyEngine(cfg, remaining_budget=20.00)

    print("agentguard demo — wrapping a hypothetical LLM agent's tool calls\n")
    print(f"Policy: {cfg}\n")

    for tool, args, cost in PROPOSED_CALLS:
        action = ProposedAction(tool=tool, args=args, cost=cost, actor="demo-agent")
        v = engine.evaluate(action, now_s=time.time())
        status = "✓ ALLOW" if v.allow else "✗ DENY "
        print(f"  {status}  {tool:<14} cost={cost:>6.2f}  →  {v.reason}")
        if v.allow:
            _ = fake_tool(tool, args)
            engine.register_action(now_s=time.time(), cost=cost)

    print(f"\nBreaker tripped: {engine.tripped}")
    print(f"Total spent:     {engine._spent_total:.4f}")
    print(f"Budget left:     {engine.remaining_budget:.4f}")


if __name__ == "__main__":
    main()
