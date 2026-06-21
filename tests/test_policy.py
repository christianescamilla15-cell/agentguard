"""Validate every guardrail provably fires + crash-safe state survives."""

import pytest

from agentguard import PolicyConfig, PolicyEngine, ProposedAction


def _cfg(**overrides) -> PolicyConfig:
    base = dict(
        allowed_tools=frozenset({"web_search", "read_file"}),
        max_cost_per_call=1.00,
        max_calls_per_window=3,
        window_seconds=60.0,
        max_cost_burn=10.0,
    )
    base.update(overrides)
    return PolicyConfig(**base)


def _act(tool="web_search", cost=0.10) -> ProposedAction:
    return ProposedAction(tool=tool, args={}, cost=cost)


def test_allow_within_limits():
    e = PolicyEngine(_cfg())
    v = e.evaluate(_act(), now_s=1000.0)
    assert v.allow is True
    assert v.reason == "ALLOW"


def test_kill_switch_denies_everything():
    e = PolicyEngine(_cfg(kill_switch=True))
    v = e.evaluate(_act(), now_s=1000.0)
    assert v.allow is False
    assert "kill_switch" in v.reason


def test_circuit_breaker_trips_and_stays_tripped():
    # high rate-limit ceiling so the breaker (not the rate limiter) is what trips
    e = PolicyEngine(_cfg(max_cost_burn=1.0, max_calls_per_window=100))
    for i in range(10):
        v = e.evaluate(_act(cost=0.20), now_s=1000.0 + i)
        if v.allow:
            e.register_action(now_s=1000.0 + i, cost=0.20)
    assert e.tripped is True
    # Even a fresh action with cost=0 stays denied
    v2 = e.evaluate(_act(cost=0.0), now_s=2000.0)
    assert v2.allow is False
    assert "circuit_breaker" in v2.reason


def test_allowlist_denies_unknown_tool():
    e = PolicyEngine(_cfg())
    v = e.evaluate(_act(tool="rm_rf_root"), now_s=1000.0)
    assert v.allow is False
    assert "allowlist" in v.reason


def test_per_call_cap():
    e = PolicyEngine(_cfg(max_cost_per_call=0.50))
    v = e.evaluate(_act(cost=0.99), now_s=1000.0)
    assert v.allow is False
    assert "cap" in v.reason


def test_rate_limit():
    e = PolicyEngine(_cfg(max_calls_per_window=2, window_seconds=10.0))
    # Two ok, third denied within window
    for i in range(2):
        v = e.evaluate(_act(), now_s=1000.0 + i)
        assert v.allow
        e.register_action(now_s=1000.0 + i, cost=0.10)
    v3 = e.evaluate(_act(), now_s=1002.0)
    assert v3.allow is False
    assert "rate_limit" in v3.reason
    # After window expires, allowed again
    v4 = e.evaluate(_act(), now_s=1020.0)
    assert v4.allow is True


def test_spend_budget():
    e = PolicyEngine(_cfg(max_cost_per_window=1.00, max_calls_per_window=100, window_seconds=10.0))
    for i in range(3):
        v = e.evaluate(_act(cost=0.30), now_s=1000.0 + i)
        assert v.allow
        e.register_action(now_s=1000.0 + i, cost=0.30)
    # 4th would push spend to 1.20 > 1.00
    v4 = e.evaluate(_act(cost=0.30), now_s=1003.0)
    assert v4.allow is False
    assert "spend_budget" in v4.reason


def test_staleness_gate():
    e = PolicyEngine(_cfg(max_staleness_s=5.0))
    fresh = e.evaluate(_act(), now_s=1000.0, context_age_s=2.0)
    assert fresh.allow
    stale = e.evaluate(_act(), now_s=1000.0, context_age_s=10.0)
    assert stale.allow is False
    assert "stale_context" in stale.reason


def test_budget_solvency():
    e = PolicyEngine(_cfg(), remaining_budget=0.05)
    v = e.evaluate(_act(cost=0.10), now_s=1000.0)
    assert v.allow is False
    assert "insufficient_budget" in v.reason


def test_snapshot_restore_preserves_tripped_breaker():
    e = PolicyEngine(_cfg(max_cost_burn=0.50))
    for i in range(5):
        v = e.evaluate(_act(cost=0.20), now_s=1000.0 + i)
        if v.allow:
            e.register_action(now_s=1000.0 + i, cost=0.20)
    assert e.tripped is True
    state = e.snapshot()

    # New engine, restore — breaker stays tripped (the bug the snapshot test prevents)
    e2 = PolicyEngine(_cfg(max_cost_burn=0.50))
    assert e2.tripped is False
    e2.restore(state)
    assert e2.tripped is True
    v = e2.evaluate(_act(cost=0.01), now_s=2000.0)
    assert v.allow is False
    assert "circuit_breaker" in v.reason


def test_denied_action_does_not_consume_budget():
    """A denied evaluate() must NOT debit rate limit or spend budget."""
    e = PolicyEngine(_cfg(max_calls_per_window=1, window_seconds=10.0))
    e.evaluate(_act(tool="unknown"), now_s=1000.0)  # denied
    e.evaluate(_act(tool="unknown"), now_s=1001.0)  # denied
    v = e.evaluate(_act(), now_s=1002.0)
    assert v.allow is True  # rate-limit window still has 1 slot free
