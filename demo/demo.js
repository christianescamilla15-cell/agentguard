/**
 * agentguard — Live Playground (JavaScript port of agentguard.PolicyEngine)
 *
 * Faithful port of agentguard/src/agentguard/policy.py for browser execution.
 * Same 8 rules in the same order. Same DENY:<rule> reason format.
 *
 * The Python implementation is the source of truth:
 *   github.com/christianescamilla15-cell/agentguard/blob/main/src/agentguard/policy.py
 */

// ──────────────────────────────────────────────────────────────────────
// PolicyConfig (mirror of the Python dataclass)
// ──────────────────────────────────────────────────────────────────────
let CFG = {
  allowed_tools: new Set(['web_search', 'read_file', 'write_note']),
  max_cost_per_call: 1.00,
  max_calls_per_window: 5,
  window_seconds: 60,
  max_cost_burn: 10.00,
  max_cost_per_window: 3.00,
  spend_window_seconds: null,
  max_staleness_s: null,
  min_cost_per_call: null,
  kill_switch: false,
}

let STATE = {
  spent_total: 0,
  tripped: false,
  recent_ts: [],          // timestamps of executed actions
  spend: [],              // [[ts, cost], …]
  remaining_budget: 20.00,
  stats: { exec: 0, allow: 0, deny: 0 },
}

// snapshot/restore demo state holder
let SNAPSHOT = null

const $ = (id) => document.getElementById(id)
const nowSec = () => Date.now() / 1000

// ──────────────────────────────────────────────────────────────────────
// PolicyEngine.evaluate — same logic as Python
// ──────────────────────────────────────────────────────────────────────
function pruneTs(arr, now, window) {
  const cutoff = now - window
  while (arr.length && arr[0] <= cutoff) arr.shift()
}
function pruneSpend(arr, now, window) {
  const cutoff = now - window
  while (arr.length && arr[0][0] <= cutoff) arr.shift()
}

function evaluate(action, now, context_age_s) {
  // 1. kill_switch
  if (CFG.kill_switch) return { allow: false, rule: 'kill_switch', reason: 'DENY:kill_switch active' }

  // 2. circuit_breaker
  if (STATE.tripped || STATE.spent_total >= CFG.max_cost_burn) {
    STATE.tripped = true
    return { allow: false, rule: 'circuit_breaker', reason: `DENY:circuit_breaker spent=${STATE.spent_total.toFixed(4)} >= burn=${CFG.max_cost_burn.toFixed(4)}` }
  }

  // 3. staleness
  if (CFG.max_staleness_s != null && context_age_s != null) {
    if (context_age_s > CFG.max_staleness_s) {
      return { allow: false, rule: 'staleness', reason: `DENY:stale_context age=${context_age_s.toFixed(2)}s > ${CFG.max_staleness_s.toFixed(2)}s` }
    }
  }

  // 4. allowlist
  if (!CFG.allowed_tools.has(action.tool)) {
    return { allow: false, rule: 'allowlist', reason: `DENY:tool '${action.tool}' not in allowlist` }
  }

  // 5. per_call_cap
  if (action.cost > CFG.max_cost_per_call) {
    return { allow: false, rule: 'per_call_cap', reason: `DENY:cost ${action.cost.toFixed(4)} > cap ${CFG.max_cost_per_call.toFixed(4)}` }
  }
  if (CFG.min_cost_per_call != null && action.cost < CFG.min_cost_per_call - 1e-9) {
    return { allow: false, rule: 'per_call_cap', reason: `DENY:min_cost ${action.cost.toFixed(4)} < floor ${CFG.min_cost_per_call.toFixed(4)}` }
  }

  // 6. rate_limit
  pruneTs(STATE.recent_ts, now, CFG.window_seconds)
  if (STATE.recent_ts.length >= CFG.max_calls_per_window) {
    return { allow: false, rule: 'rate_limit', reason: `DENY:rate_limit ${CFG.max_calls_per_window}/${CFG.window_seconds}s` }
  }

  // 7. spend_budget
  if (CFG.max_cost_per_window != null) {
    const spendWindow = CFG.spend_window_seconds ?? CFG.window_seconds
    pruneSpend(STATE.spend, now, spendWindow)
    const spentInWindow = STATE.spend.reduce((s, x) => s + x[1], 0)
    if (spentInWindow + action.cost > CFG.max_cost_per_window + 1e-9) {
      return { allow: false, rule: 'spend_budget', reason: `DENY:spend_budget ${(spentInWindow + action.cost).toFixed(4)} > ${CFG.max_cost_per_window.toFixed(4)}/${spendWindow}s` }
    }
  }

  // 8. solvency
  if (action.cost > STATE.remaining_budget + 1e-9) {
    return { allow: false, rule: 'solvency', reason: `DENY:insufficient_budget need=${action.cost.toFixed(4)} have=${STATE.remaining_budget.toFixed(4)}` }
  }

  return { allow: true, rule: null, reason: 'ALLOW' }
}

function registerAction(now, cost) {
  STATE.recent_ts.push(now)
  STATE.spend.push([now, cost])
  STATE.spent_total += cost
  STATE.remaining_budget -= cost
}

// ──────────────────────────────────────────────────────────────────────
// UI plumbing
// ──────────────────────────────────────────────────────────────────────
function applyCfgFromUI() {
  const tools = $('cfg-tools').value.split(',').map(s => s.trim()).filter(Boolean)
  CFG.allowed_tools = new Set(tools)
  CFG.max_cost_per_call = parseFloat($('cfg-cap').value)
  CFG.max_calls_per_window = parseInt($('cfg-rate').value, 10)
  CFG.window_seconds = parseFloat($('cfg-window').value)
  CFG.max_cost_burn = parseFloat($('cfg-burn').value)
  CFG.max_cost_per_window = parseFloat($('cfg-spend').value) || null
  CFG.kill_switch = $('cfg-kill').checked
  STATE.remaining_budget = parseFloat($('cfg-budget').value)
  appendLog('cfg', 'policy applied — kill=' + CFG.kill_switch + ', cap=$' + CFG.max_cost_per_call + ', rate=' + CFG.max_calls_per_window + '/' + CFG.window_seconds + 's, spend=$' + CFG.max_cost_per_window + ', burn=$' + CFG.max_cost_burn, 'system')
  renderState()
}

function flashRule(rule, kind) {
  if (!rule) return
  document.querySelectorAll('.rule').forEach(r => r.classList.remove('is-firing', 'is-pass'))
  if (rule === 'ALL_PASS') {
    document.querySelectorAll('.rule').forEach(r => r.classList.add('is-pass'))
    setTimeout(() => document.querySelectorAll('.rule').forEach(r => r.classList.remove('is-pass')), 1200)
    return
  }
  const el = document.querySelector(`.rule[data-rule="${rule}"]`)
  if (el) {
    void el.offsetWidth
    el.classList.add(kind === 'deny' ? 'is-firing' : 'is-pass')
    setTimeout(() => el.classList.remove('is-firing', 'is-pass'), 1500)
  }
}

function renderVerdict(verdict, action) {
  const v = $('verdict')
  v.classList.remove('is-allow', 'is-deny')
  if (verdict.allow) {
    v.classList.add('is-allow')
    $('verdict-icon').textContent = '✓'
    $('verdict-label').textContent = `ALLOW · ${action.tool} · $${action.cost.toFixed(2)}`
    $('verdict-reason').textContent = 'all 8 rules passed → action executed'
  } else {
    v.classList.add('is-deny')
    $('verdict-icon').textContent = '✗'
    $('verdict-label').textContent = `DENY · rule ${verdict.rule}`
    $('verdict-reason').textContent = verdict.reason
  }
}

function renderState() {
  $('st-exec').textContent = STATE.stats.exec
  $('st-spent').textContent = '$' + STATE.spent_total.toFixed(2)
  $('st-budget').textContent = '$' + STATE.remaining_budget.toFixed(2)
  $('st-breaker').textContent = STATE.tripped ? '● TRIPPED' : '○ OK'
  $('st-breaker').style.color = STATE.tripped ? 'var(--red)' : 'var(--green)'
  pruneTs(STATE.recent_ts, nowSec(), CFG.window_seconds)
  pruneSpend(STATE.spend, nowSec(), CFG.spend_window_seconds ?? CFG.window_seconds)
  $('st-windowcount').textContent = STATE.recent_ts.length
  $('st-windowspent').textContent = '$' + STATE.spend.reduce((s, x) => s + x[1], 0).toFixed(2)
}

function appendLog(t, m, kind = 'allow') {
  const log = $('log')
  const row = document.createElement('div')
  row.className = 'log__entry'
  row.innerHTML = `<span class="log__t">${t}</span><span class="log__m ${kind}">${m}</span>`
  log.prepend(row)
}

// ──────────────────────────────────────────────────────────────────────
// Actions
// ──────────────────────────────────────────────────────────────────────
function submitAction(tool, cost) {
  const action = { tool, cost: parseFloat(cost), args: {} }
  const now = nowSec()
  const verdict = evaluate(action, now, null)
  renderVerdict(verdict, action)
  if (verdict.allow) {
    registerAction(now, action.cost)
    STATE.stats.exec++
    STATE.stats.allow++
    appendLog(action.tool, `ALLOW $${action.cost.toFixed(2)}`, 'allow')
    flashRule('ALL_PASS', 'allow')
  } else {
    STATE.stats.deny++
    appendLog(action.tool, verdict.reason, 'deny')
    flashRule(verdict.rule, 'deny')
  }
  renderState()
}

function reset() {
  STATE = {
    spent_total: 0, tripped: false, recent_ts: [], spend: [],
    remaining_budget: parseFloat($('cfg-budget').value), stats: { exec: 0, allow: 0, deny: 0 },
  }
  SNAPSHOT = null
  $('log').innerHTML = ''
  appendLog('reset', 'state cleared · policy preserved', 'system')
  $('verdict').classList.remove('is-allow', 'is-deny')
  $('verdict-icon').textContent = '○'
  $('verdict-label').textContent = 'No decision yet'
  $('verdict-reason').textContent = 'Submit an action to evaluate.'
  renderState()
}

// ──────────────────────────────────────────────────────────────────────
// Presets
// ──────────────────────────────────────────────────────────────────────
const PRESETS = {
  benign: [
    ['web_search', 0.05], ['read_file', 0.00], ['write_note', 0.02],
    ['web_search', 0.08], ['read_file', 0.01],
  ],
  attack: [
    ['rm_rf_root', 0.01],              // 4 allowlist
    ['charge_card', 0.99],             // 4 allowlist
    ['web_search', 50.00],             // 5 per_call_cap
    ['web_search', 0.05], ['web_search', 0.05], ['web_search', 0.05],
    ['web_search', 0.05], ['web_search', 0.05], ['web_search', 0.05],   // 6 rate_limit
    ['write_note', 5.00],              // 7 spend_budget after rate_limit pruned
  ],
}

async function runPreset(name) {
  const list = PRESETS[name]
  if (!list) return
  for (const [tool, cost] of list) {
    submitAction(tool, cost)
    await new Promise(r => setTimeout(r, 400))
  }
}

function doSnapshotKillRestore() {
  // 1) snapshot
  SNAPSHOT = JSON.parse(JSON.stringify({ ...STATE, recent_ts: [...STATE.recent_ts], spend: STATE.spend.map(x => [...x]) }))
  appendLog('snapshot', 'state journaled (snapshot taken)', 'system')
  // 2) simulate kill: zero ONLY the breaker visualization (state object stays)
  setTimeout(() => {
    appendLog('SIGKILL', 'process killed mid-loop — state remains on disk', 'system')
    setTimeout(() => {
      // 3) restore: prove tripped breaker survives
      STATE = SNAPSHOT
      STATE.recent_ts = [...SNAPSHOT.recent_ts]
      STATE.spend = SNAPSHOT.spend.map(x => [...x])
      appendLog('restart', `process restarted → breaker=${STATE.tripped ? 'TRIPPED (preserved)' : 'OK'}, exec=${STATE.stats.exec}, spent=$${STATE.spent_total.toFixed(2)}`, 'system')
      renderState()
    }, 900)
  }, 700)
}

// ──────────────────────────────────────────────────────────────────────
// Wire up
// ──────────────────────────────────────────────────────────────────────
$('btn-apply').onclick = applyCfgFromUI
$('btn-evaluate').onclick = () => submitAction($('act-tool').value, $('act-cost').value)
$('btn-reset').onclick = reset
document.querySelectorAll('[data-preset]').forEach(btn => {
  btn.onclick = () => {
    const p = btn.dataset.preset
    if (p === 'snapshot') doSnapshotKillRestore()
    else runPreset(p)
  }
})

renderState()
