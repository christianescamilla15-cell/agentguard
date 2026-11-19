"""One test per business rule that was not pinned yet (docs/reglas.md maps every rule to its tests).

- The 8 rules are evaluated IN ORDER: violate all of them, fix one at a time, and the next
  rule must surface — a reordering of evaluate() fails here.
- Every rule's exact DENY prefix, boundaries (at the limit = allowed) and inert defaults.
- The breaker is a latch: armed -> tripped is the only transition; tripped -> armed is invalid
  (no API, no restart, no lower-cost action brings it back).
- Denied actions never consume the rate limit, the spend budget, the breaker or the budget.
- snapshot()/restore() keep every counter a crash could otherwise zero.
- Seeded fuzz over arbitrary histories: an ALLOW never breaks a cap the config promises.
"""

from __future__ import annotations

import dataclasses
import json
import random

import pytest

from agentguard import PolicyConfig, PolicyEngine, ProposedAction


def _cfg(**overrides) -> PolicyConfig:
    base = {
        "allowed_tools": frozenset({"web_search", "read_file"}),
        "max_cost_per_call": 1.00,
        "max_calls_per_window": 3,
        "window_seconds": 60.0,
        "max_cost_burn": 10.0,
    }
    base.update(overrides)
    return PolicyConfig(**base)


def _act(tool: str = "web_search", cost: float = 0.10) -> ProposedAction:
    return ProposedAction(tool=tool, args={}, cost=cost)


# --------------------------------------------------------------------------- rule order


@dataclasses.dataclass
class Scenario:
    """Every flag True = that rule is violated; each violation is independent of the others."""

    kill: bool = True
    tripped: bool = True
    stale: bool = True
    unknown_tool: bool = True
    over_cap: bool = True
    rate_full: bool = True
    spend_full: bool = True
    broke: bool = True

    def run(self) -> str:
        cfg = _cfg(kill_switch=self.kill, max_staleness_s=5.0, max_calls_per_window=1,
                   max_cost_per_window=1.0, max_cost_burn=10.0)
        e = PolicyEngine(cfg)
        e.restore({
            "spent_total": 10.0 if self.tripped else 0.0,
            "tripped": self.tripped,
            "recent_ts": [999.0] if self.rate_full else [],
            "spend": [[999.0, 0.9]] if self.spend_full else [],
            "remaining_budget": 0.1 if self.broke else 100.0,
        })
        action = _act(tool="rm_rf_root" if self.unknown_tool else "web_search",
                      cost=5.0 if self.over_cap else 0.5)
        return e.evaluate(action, now_s=1000.0, context_age_s=10.0 if self.stale else 1.0).reason


EXPECTED_ORDER = [
    ("kill", "DENY:kill_switch"),
    ("tripped", "DENY:circuit_breaker"),
    ("stale", "DENY:stale_context"),
    ("unknown_tool", "DENY:tool"),
    ("over_cap", "DENY:cost"),
    ("rate_full", "DENY:rate_limit"),
    ("spend_full", "DENY:spend_budget"),
    ("broke", "DENY:insufficient_budget"),
]


def test_the_8_rules_fire_in_their_documented_order():
    s = Scenario()
    for flag, prefix in EXPECTED_ORDER:
        reason = s.run()
        assert reason.startswith(prefix), f"with {flag} still violated expected {prefix}, got {reason}"
        setattr(s, flag, False)                     # fix this one; the next rule must surface
    assert s.run() == "ALLOW"


@pytest.mark.parametrize(("flag", "prefix"), EXPECTED_ORDER)
def test_each_rule_alone_denies_with_its_exact_prefix(flag, prefix):
    s = Scenario(**{f.name: False for f in dataclasses.fields(Scenario)})
    setattr(s, flag, True)
    assert s.run().startswith(prefix + " ")


# --------------------------------------------------------------------------- per-rule edges


def test_config_is_immutable():
    cfg = _cfg()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_cost_per_call = 1e9                  # the agent cannot raise its own limits


def test_staleness_gate_is_inert_without_budget_or_age_and_allows_at_the_budget():
    assert PolicyEngine(_cfg()).evaluate(_act(), now_s=0.0, context_age_s=1e9).allow       # no budget
    assert PolicyEngine(_cfg(max_staleness_s=5.0)).evaluate(_act(), now_s=0.0).allow        # no age
    assert PolicyEngine(_cfg(max_staleness_s=5.0)).evaluate(_act(), now_s=0.0, context_age_s=5.0).allow


def test_cost_exactly_at_the_cap_is_allowed():
    assert PolicyEngine(_cfg(max_cost_per_call=0.5)).evaluate(_act(cost=0.5), now_s=0.0).allow


def test_min_cost_floor_rejects_dust_and_allows_at_the_floor():
    e = PolicyEngine(_cfg(min_cost_per_call=0.10))
    dust = e.evaluate(_act(cost=0.01), now_s=0.0)
    assert not dust.allow and dust.reason.startswith("DENY:min_cost")
    assert e.evaluate(_act(cost=0.10), now_s=0.0).allow


def test_rate_window_evicts_a_call_exactly_at_the_cutoff():
    e = PolicyEngine(_cfg(max_calls_per_window=1, window_seconds=10.0))
    e.register_action(now_s=1000.0, cost=0.1)
    assert not e.evaluate(_act(), now_s=1009.9).allow                 # still inside the window
    assert e.evaluate(_act(), now_s=1010.0).allow                     # ts == now - window -> evicted


def test_spend_budget_allows_exactly_the_budget_and_recovers_after_its_window():
    e = PolicyEngine(_cfg(max_cost_per_window=1.0, max_calls_per_window=100, window_seconds=10.0))
    e.register_action(now_s=1000.0, cost=0.6)
    assert e.evaluate(_act(cost=0.4), now_s=1001.0).allow             # 0.6 + 0.4 == 1.0 -> allowed
    assert not e.evaluate(_act(cost=0.41), now_s=1001.0).allow
    assert e.evaluate(_act(cost=0.9), now_s=1011.0).allow             # the 0.6 left the window


def test_spend_window_can_differ_from_the_rate_window():
    e = PolicyEngine(_cfg(max_cost_per_window=1.0, spend_window_seconds=100.0,
                          max_calls_per_window=100, window_seconds=10.0))
    e.register_action(now_s=1000.0, cost=0.9)
    v = e.evaluate(_act(cost=0.5), now_s=1050.0)                      # past 10 s, inside 100 s
    assert not v.allow and v.reason.endswith("/100.0s")


def test_solvency_uses_the_per_call_budget_and_allows_exactly_the_budget():
    e = PolicyEngine(_cfg(), remaining_budget=100.0)
    assert not e.evaluate(_act(cost=0.5), now_s=0.0, remaining_budget=0.4).allow   # override wins
    assert e.evaluate(_act(cost=0.5), now_s=0.0, remaining_budget=0.5).allow


def test_executed_actions_debit_the_remaining_budget():
    e = PolicyEngine(_cfg(max_calls_per_window=100), remaining_budget=0.25)
    for t in range(2):
        assert e.evaluate(_act(cost=0.10), now_s=float(t)).allow
        e.register_action(now_s=float(t), cost=0.10)
    v = e.evaluate(_act(cost=0.10), now_s=2.0)                        # 0.05 left < 0.10
    assert not v.allow and v.reason.startswith("DENY:insufficient_budget")


# --------------------------------------------------------------------------- breaker latch


def test_breaker_trips_exactly_at_the_burn_limit():
    e = PolicyEngine(_cfg(max_cost_burn=1.0, max_calls_per_window=100))
    e.register_action(now_s=0.0, cost=0.5)
    assert e.evaluate(_act(), now_s=1.0).allow and not e.tripped       # 0.5 < 1.0
    e.register_action(now_s=1.0, cost=0.5)
    assert not e.evaluate(_act(cost=0.0), now_s=2.0).allow and e.tripped   # 1.0 >= 1.0


def test_tripped_to_armed_is_an_invalid_transition():
    e = PolicyEngine(_cfg(max_cost_burn=0.5, max_calls_per_window=100))
    e.register_action(now_s=0.0, cost=0.5)
    assert not e.evaluate(_act(), now_s=1.0).allow
    # nothing the agent can do re-arms it: zero cost, other tool, far future, fresh context
    for action, now in [(_act(cost=0.0), 2.0), (_act(tool="read_file"), 10_000.0), (_act(), 1e9)]:
        v = e.evaluate(action, now_s=now, context_age_s=0.0, remaining_budget=1e9)
        assert not v.allow and v.reason.startswith("DENY:circuit_breaker")
    assert e.tripped


def test_breaker_rederives_from_spend_even_if_the_flag_was_lost():
    # crash between register_action() and the snapshot of the flag: spent >= burn must still trip
    e = PolicyEngine(_cfg(max_cost_burn=1.0))
    e.restore({"spent_total": 1.0, "tripped": False})
    assert not e.evaluate(_act(cost=0.0), now_s=0.0).allow and e.tripped


# --------------------------------------------------------------------------- no debit on deny


def test_denied_actions_never_consume_anything():
    e = PolicyEngine(_cfg(max_calls_per_window=1, max_cost_per_window=0.5, max_cost_burn=0.5),
                     remaining_budget=0.5)
    for t in range(20):                                # 20 denials of every kind
        e.evaluate(_act(tool="unknown"), now_s=float(t))
        e.evaluate(_act(cost=5.0), now_s=float(t))
        e.evaluate(_act(cost=0.6), now_s=float(t))
    assert e.snapshot() == PolicyEngine(_cfg(), remaining_budget=0.5).snapshot()
    assert e.evaluate(_act(cost=0.5), now_s=30.0).allow    # one full-size call still fits


# --------------------------------------------------------------------------- crash safety


def test_snapshot_survives_json_and_restores_every_counter():
    cfg = _cfg(max_calls_per_window=2, max_cost_per_window=1.0)
    e = PolicyEngine(cfg, remaining_budget=5.0)
    for t in (100.0, 101.0):
        e.register_action(now_s=t, cost=0.4)
    state = json.loads(json.dumps(e.snapshot()))           # what a real restart reads from disk

    e2 = PolicyEngine(cfg)
    e2.restore(state)
    assert e2.snapshot() == e.snapshot()
    assert e2.evaluate(_act(), now_s=102.0).reason.startswith("DENY:rate_limit")   # window not zeroed
    assert e2.remaining_budget == pytest.approx(4.2)


def test_restore_of_an_empty_state_is_a_fresh_engine():
    e = PolicyEngine(_cfg())
    e.restore({})
    assert e.snapshot() == PolicyEngine(_cfg()).snapshot()


# --------------------------------------------------------------------------- fuzz


@pytest.mark.parametrize("seed", range(200))
def test_an_allow_never_breaks_a_promised_limit(seed):
    rng = random.Random(seed)
    cfg = _cfg(max_cost_per_call=1.0, max_calls_per_window=4, window_seconds=10.0,
               max_cost_burn=6.0, max_cost_per_window=2.5, min_cost_per_call=0.01)
    e = PolicyEngine(cfg, remaining_budget=8.0)
    now, executed = 0.0, []
    for _ in range(60):
        now += rng.choice([0.5, 1.0, 3.0, 11.0])
        action = _act(tool=rng.choice(["web_search", "read_file", "shell"]),
                      cost=rng.choice([0.0, 0.005, 0.3, 0.9, 1.0, 1.5]))
        was_tripped = e.tripped
        v = e.evaluate(action, now_s=now)
        if not v.allow:
            continue
        assert not was_tripped                                          # never allowed while tripped
        assert action.tool in cfg.allowed_tools
        assert 0.01 - 1e-9 <= action.cost <= cfg.max_cost_per_call
        assert action.cost <= e.remaining_budget + 1e-9
        in_window = [(t, c) for t, c in executed if t > now - cfg.window_seconds]
        assert len(in_window) < cfg.max_calls_per_window
        assert sum(c for _, c in in_window) + action.cost <= cfg.max_cost_per_window + 1e-9
        e.register_action(now_s=now, cost=action.cost)
        executed.append((now, action.cost))
    # lifetime spend can exceed the burn by at most the action that crossed it
    assert e._spent_total < cfg.max_cost_burn + cfg.max_cost_per_call
