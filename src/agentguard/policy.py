"""Policy engine — the guardrail. This is the only module that matters.

The agent (LLM, strategy, planner) can hallucinate, be prompt-injected via tool
results, or simply be wrong. The PolicyEngine is the layer of HARD, non-negotiable
rules that sits between a proposed action and any execution. It DOES NOT TRUST
THE AGENT.

Rules enforced, in order:
  1. kill_switch              — global stop, denies everything
  2. circuit_breaker          — if cumulative cost spent >= max_cost_burn, trip and stay tripped
  3. staleness_gate           — deny if context_age_s > max_staleness_s (fail-closed when supplied)
  4. tool_allowlist           — only approved tool names
  5. per_call_cost_cap        — no single action above max_cost_per_call
  6. rate_limit               — at most max_calls_per_window actions per rolling window
  7. spend_budget             — at most max_cost_per_window of cumulative cost per window
  8. budget_solvency          — never approve what would exceed remaining_budget

State is latched (breaker, windows) and crash-safe via snapshot()/restore() —
ported from TreasuryForge's policy.py, generalized for agentic AI systems.

Pattern origin: github.com/christianescamilla15-cell/treasuryforge — same author.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .types import ProposedAction, Verdict


@dataclass(frozen=True)
class PolicyConfig:
    """Immutable policy. The agent cannot mutate its own limits."""

    allowed_tools: frozenset[str]
    max_cost_per_call: float
    max_calls_per_window: int
    window_seconds: float
    max_cost_burn: float  # circuit breaker: total cost over lifetime
    kill_switch: bool = False
    min_cost_per_call: float | None = None
    max_cost_per_window: float | None = None  # cumulative spend budget (value, not count)
    spend_window_seconds: float | None = None
    max_staleness_s: float | None = None  # context freshness; None or no age supplied → inert

    @property
    def _spend_window(self) -> float:
        return self.spend_window_seconds if self.spend_window_seconds is not None else self.window_seconds


@dataclass
class PolicyEngine:
    """Enforces PolicyConfig over a stream of proposed actions.

    Usage:
        cfg = PolicyConfig(allowed_tools=frozenset({"web_search", "read_file"}),
                           max_cost_per_call=0.50, max_calls_per_window=10,
                           window_seconds=60.0, max_cost_burn=20.0)
        engine = PolicyEngine(cfg)
        verdict = engine.evaluate(ProposedAction(tool="web_search", args={...}, cost=0.05))
        if verdict.allow:
            result = run_tool(...)
            engine.register_action(now_s=time.time(), cost=0.05)
    """

    config: PolicyConfig
    remaining_budget: float = float("inf")  # caller-managed; pass through evaluate() if dynamic
    _spent_total: float = 0.0
    _tripped: bool = False
    _recent_ts: deque[float] = field(default_factory=deque)
    _spend: deque[tuple[float, float]] = field(default_factory=deque)

    @property
    def tripped(self) -> bool:
        return self._tripped

    def evaluate(  # noqa: C901 - one flat, auditable rule sequence; splitting hurts review
        self,
        action: ProposedAction,
        now_s: float | None = None,
        context_age_s: float | None = None,
        remaining_budget: float | None = None,
    ) -> Verdict:
        cfg = self.config
        now = now_s if now_s is not None else time.time()
        budget = remaining_budget if remaining_budget is not None else self.remaining_budget

        # 1. kill switch ----------------------------------------------------
        if cfg.kill_switch:
            return Verdict(False, "DENY:kill_switch active")

        # 2. circuit breaker (cumulative cost over lifetime) ----------------
        if self._tripped or self._spent_total >= cfg.max_cost_burn:
            self._tripped = True
            return Verdict(
                False,
                f"DENY:circuit_breaker spent={self._spent_total:.4f} >= burn={cfg.max_cost_burn:.4f}",
            )

        # 3. staleness gate (fail-closed; inert without both budget and age)
        if cfg.max_staleness_s is not None and context_age_s is not None:
            if context_age_s > cfg.max_staleness_s:
                return Verdict(
                    False,
                    f"DENY:stale_context age={context_age_s:.2f}s > {cfg.max_staleness_s:.2f}s",
                )

        # 4. tool allowlist -------------------------------------------------
        if action.tool not in cfg.allowed_tools:
            return Verdict(False, f"DENY:tool '{action.tool}' not in allowlist")

        # 5. per-call cost cap (and exchange-style min floor) ---------------
        if action.cost > cfg.max_cost_per_call:
            return Verdict(
                False,
                f"DENY:cost {action.cost:.4f} > cap {cfg.max_cost_per_call:.4f}",
            )
        if cfg.min_cost_per_call is not None and action.cost < cfg.min_cost_per_call - 1e-9:
            return Verdict(
                False,
                f"DENY:min_cost {action.cost:.4f} < floor {cfg.min_cost_per_call:.4f}",
            )

        # 6. rate limit (call count) ----------------------------------------
        self._prune_ts(self._recent_ts, now, cfg.window_seconds)
        if len(self._recent_ts) >= cfg.max_calls_per_window:
            return Verdict(
                False,
                f"DENY:rate_limit {cfg.max_calls_per_window}/{cfg.window_seconds}s",
            )

        # 7. spend budget (cumulative cost per window) ----------------------
        if cfg.max_cost_per_window is not None:
            self._prune_spend(self._spend, now, cfg._spend_window)
            spent_in_window = sum(c for _, c in self._spend)
            if spent_in_window + action.cost > cfg.max_cost_per_window + 1e-9:
                return Verdict(
                    False,
                    f"DENY:spend_budget {spent_in_window + action.cost:.4f} > "
                    f"{cfg.max_cost_per_window:.4f}/{cfg._spend_window}s",
                )

        # 8. budget solvency -----------------------------------------------
        if action.cost > budget + 1e-9:
            return Verdict(
                False,
                f"DENY:insufficient_budget need={action.cost:.4f} have={budget:.4f}",
            )

        return Verdict(True, "ALLOW")

    def register_action(self, now_s: float, cost: float) -> None:
        """Record an EXECUTED action so rate limiter, spend budget, and breaker count it.

        Debited on execution only (never at evaluate-time) so denied/aborted actions
        never consume budget.
        """
        self._recent_ts.append(now_s)
        self._spend.append((now_s, cost))
        self._spent_total += cost
        self.remaining_budget -= cost

    # -- crash-safe latched state -----------------------------------------
    def snapshot(self) -> dict:
        """Serializable latched state — persist so a restart cannot reset
        the breaker or zero the rolling-window counters."""
        return {
            "spent_total": self._spent_total,
            "tripped": self._tripped,
            "recent_ts": list(self._recent_ts),
            "spend": [[ts, c] for ts, c in self._spend],
            "remaining_budget": self.remaining_budget,
        }

    def restore(self, state: dict) -> None:
        self._spent_total = float(state.get("spent_total", 0.0))
        self._tripped = bool(state.get("tripped", False))
        self._recent_ts = deque(float(t) for t in state.get("recent_ts", []))
        self._spend = deque((float(ts), float(c)) for ts, c in state.get("spend", []))
        self.remaining_budget = float(state.get("remaining_budget", float("inf")))

    @staticmethod
    def _prune_ts(dq: deque, now: float, window: float) -> None:
        cutoff = now - window
        while dq and dq[0] <= cutoff:
            dq.popleft()

    @staticmethod
    def _prune_spend(dq: deque, now: float, window: float) -> None:
        cutoff = now - window
        while dq and dq[0][0] <= cutoff:
            dq.popleft()
