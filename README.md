# agentguard

> **Safety guardrails for autonomous agents.** 8 hard rules + crash-safe state + tamper-evident pattern. Zero dependencies. The policy engine NEVER trusts the agent.

[![ci](https://github.com/christianescamilla15-cell/agentguard/actions/workflows/ci.yml/badge.svg)](https://github.com/christianescamilla15-cell/agentguard/actions/workflows/ci.yml)
[![seguridad](https://github.com/christianescamilla15-cell/agentguard/actions/workflows/seguridad.yml/badge.svg)](https://github.com/christianescamilla15-cell/agentguard/actions/workflows/seguridad.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-237-green.svg)](#tests)
[![Deps](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Why this exists

LLM-driven agents take real actions: call APIs, spend money, send messages, modify files. The model can be wrong, prompt-injected via tool results, or genuinely confused. **You cannot trust the agent to enforce its own limits.**

agentguard is a tiny, dependency-free Python library that sits between an agent's *proposed* actions and the executor that runs them. Every action goes through 8 hard rules and either gets ALLOW or a structured DENY reason.

This is the same architecture used in [TreasuryForge](https://github.com/christianescamilla15-cell/treasuryforge) (autonomous crypto treasury agent), extracted into a generic library.

---

## The pattern

```
  AGENT  (LLM, strategy, planner)        can hallucinate, can be wrong
     │   proposes a ProposedAction
     │   (never executes anything directly)
     ▼
  POLICY ENGINE   8 hard rules         DOES NOT TRUST THE AGENT
     │   ALLOW or DENY:<rule>
     ▼
  EXECUTOR        runs only approved actions
```

The agent never touches the executor. It only *proposes*. The policy layer is the source of truth for what's allowed.

## The 8 rules (in evaluation order)

1. **kill_switch** — global stop, denies everything
2. **circuit_breaker** — if total cost spent ≥ `max_cost_burn`, trip and **stay tripped** (survives restart via `snapshot()/restore()`)
3. **staleness_gate** — deny if context older than `max_staleness_s` (fail-closed)
4. **tool_allowlist** — only approved tool names
5. **per_call_cost_cap** — no single action above `max_cost_per_call`
6. **rate_limit** — at most `max_calls_per_window` actions per rolling window
7. **spend_budget** — at most `max_cost_per_window` cumulative cost per window
8. **budget_solvency** — never approve what would exceed remaining budget

Denials are *structured*: every DENY message starts with `DENY:<rule>` for easy log filtering.

## Install

Not published on PyPI yet: `pip install agentguard` fails today, and would install someone else's code if a third
party ever registered the name. Install from GitHub:

```bash
pip install git+https://github.com/christianescamilla15-cell/agentguard
```

Or from source:

```bash
git clone https://github.com/christianescamilla15-cell/agentguard
cd agentguard
pip install -e ".[dev]"
pytest
```

## 30-second example

```python
import time
from agentguard import PolicyConfig, PolicyEngine, ProposedAction

cfg = PolicyConfig(
    allowed_tools=frozenset({"web_search", "read_file"}),
    max_cost_per_call=1.00,
    max_calls_per_window=3,
    window_seconds=60.0,
    max_cost_burn=10.00,
    max_cost_per_window=2.00,
)
engine = PolicyEngine(cfg, remaining_budget=20.00)

# 1. Agent proposes an action
action = ProposedAction(
    tool="web_search",
    args={"q": "AI safety papers 2026"},
    cost=0.05,
)

# 2. Policy evaluates
verdict = engine.evaluate(action, now_s=time.time())

if verdict.allow:
    result = your_executor.run(action.tool, action.args)
    engine.register_action(now_s=time.time(), cost=0.05)  # debit on execute
else:
    log.warning("policy denied: %s", verdict.reason)
    # verdict.reason -> "DENY:rate_limit 3/60.0s" or "DENY:tool 'rm_rf_root' not in allowlist" etc.
```

Run the included demo:

```bash
python examples/llm_tool_call_guard.py
```

Output:
```
✓ ALLOW  web_search     cost=  0.05  →  ALLOW
✓ ALLOW  read_file      cost=  0.00  →  ALLOW
✗ DENY   rm_rf_root     cost=  0.01  →  DENY:tool 'rm_rf_root' not in allowlist
✓ ALLOW  web_search     cost=  0.05  →  ALLOW
✗ DENY   web_search     cost=  0.05  →  DENY:rate_limit 3/60.0s
✗ DENY   web_search     cost=  0.05  →  DENY:rate_limit 3/60.0s
✗ DENY   expensive_api  cost=  0.05  →  DENY:tool 'expensive_api' not in allowlist
✗ DENY   web_search     cost= 50.00  →  DENY:cost 50.0000 > cap 1.0000
```

---

## Crash-safe state

Latched state (breaker, rolling windows, cumulative spend) survives a hard kill:

```python
# Periodically (or on every register_action):
state = engine.snapshot()
write_atomic("policy.state.json", json.dumps(state))

# On restart:
state = json.loads(read("policy.state.json"))
engine.restore(state)
assert engine.tripped == True_if_was_tripped_before_crash
```

A subprocess `os._exit(1)` test in TreasuryForge proves the breaker survives `SIGKILL` (see [treasuryforge/journal.py](https://github.com/christianescamilla15-cell/treasuryforge/blob/main/treasuryforge/journal.py)).

## What this prevents

- **Tool whitelist bypass** — even if the LLM hallucinates a tool name, allowlist denies it
- **Cost runaway** — circuit breaker trips when cumulative spend ≥ burn limit, and stays tripped
- **Rate-limit drift** — rolling window counter prevents burst calls even if individual calls look fine
- **Drip-drain attack** — spend budget catches many-small-calls patterns that count-only rate limits miss
- **Stale-context decisions** — staleness gate denies if the agent's view of the world is too old
- **Silent-recover bug** — without snapshot/restore, a process crash would un-trip the breaker and resume spending. agentguard prevents this

## What this does NOT do

- **Does not validate `args`** — the policy treats `ProposedAction.args` as opaque. Tool implementations are responsible for input validation
- **Does not enforce identity / auth** — pair with your auth layer; `actor` is recorded for future scoping
- **Does not provide an executor** — that's intentional. You bring the executor (any tool framework, any AgentKit). agentguard is the layer between
- **Is not async-only** — the API is sync because evaluation must be fast and deterministic. Wrap in async if your executor is async

---

## Tests

```bash
pytest -v
```

237 tests (11 original + 26 rule tests + 200 seeded fuzz histories) cover every rule (allow, kill switch, breaker trip + stay-tripped, allowlist, per-call cap, rate limit, spend budget, staleness, solvency, snapshot/restore, denied-actions-don't-consume-budget), the **order** in which the 8 rules fire, every boundary, the breaker's invalid `tripped → armed` transition, and a golden file that keeps the example's output in this README honest. [`docs/reglas.md`](docs/reglas.md) maps each rule to its tests — that map is the gate; coverage (100 % lines and branches) is reported.

CI runs ruff, `mypy --strict` and the suite on Python 3.10–3.13, and builds the wheel and runs the example from a clean install.

## Architecture

C4 model (context → containers → components) in [`docs/arquitectura/`](docs/arquitectura/README.md); decisions in [`docs/adr/`](docs/adr/): a zero-dependency library extracted from TreasuryForge, latched state that the integrator persists, and the browser playground as a JS port.

## How to run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r ci/requirements.txt -e .   # the exact toolchain CI uses
ruff check . && mypy && pytest
python examples/llm_tool_call_guard.py
```

Live playground: **https://agentguard-amber.vercel.app** (deployment, rollback and troubleshooting in [`RUNBOOK.md`](RUNBOOK.md)).

## Security

See [`SECURITY.md`](SECURITY.md): CodeQL + Semgrep, `mypy --strict`, Trivy, gitleaks over the whole history, a confidentiality filter and an SBOM on every change; every scan must prove it analyzed something. A way to get an action ALLOWed that a rule should DENY is the highest-priority report.

## Roadmap

- [x] 8 rules, frozen config, latched state
- [x] snapshot/restore for crash safety
- [x] Pure stdlib — zero dependencies
- [ ] HMAC hash-chained audit log (port from TreasuryForge)
- [ ] Async-native evaluate() variant
- [ ] Hypothesis property-based test suite (port from TreasuryForge)
- [ ] Per-actor scoping (multi-tenant policies)
- [ ] OpenTelemetry span/metric integration

---

## Pattern origin

This library is the generalization of the policy engine in [**TreasuryForge**](https://github.com/christianescamilla15-cell/treasuryforge) — a local-first autonomous crypto treasury sandbox where the same 4-layer (Agent → Policy → Executor → Wallet) architecture was originally validated. See the [TreasuryForge transferability table](https://github.com/christianescamilla15-cell/treasuryforge#transferability-to-ai-agents) for the design rationale.

## Author

**Christian Hernández Escamilla** — AI Engineer · Multi-Agent Orchestration · Production Reliability
[GitHub](https://github.com/christianescamilla15-cell) · christianescamilla15@gmail.com

## License

MIT — see [LICENSE](LICENSE).
