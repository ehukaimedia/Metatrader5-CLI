# Autopilot Consensus (Phase 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict-2-of-2 consensus auto-trade lane on top of phase-1's review pipeline. Reviewers vote `take` / `skip` / `adjust` on the deterministic READY setup; both must vote `take` with `accepted_levels=true` and confidence >= threshold for the autopilot executor to place at the bot's original levels. Master flag defaults OFF; shadow consensus_verdict records run unconditionally so the operator can calibrate before flipping it on.

**Architecture:** Adds a second persistent reviewer agent (`CodexReviewer`). On each READY, agent.py creates TWO `trade_review-*` tasks in parallel. The verdict poller joins both verdicts by `alert_id`, computes consensus, and journals `kind=consensus_verdict`. When `autopilot.enabled=true` and consensus is `take`, the autopilot executor receives the EXACT original `ready_alert` payload (looked up by `alert_id`) and runs a 12-gate parity check (alert age, fingerprint match or bounded drift, kill-switch, news blackout, per-pair allowlist, micro-lot, daily caps, etc.). On full pass it calls `mt5 order limit` at `alert['setup'].entry/sl/tp` — the bot's original levels. `sniper_poc()` is only re-run inside the fingerprint/drift gate to verify the current market still matches; it is never used to build placement levels.

**Tech Stack:** Same as phase 1 — Python 3.13, sqlite3, pytest, ehukaiconnect, MT5 CLI.

**Spec reference:** `docs/superpowers/specs/2026-05-08-bot-managed-trades-and-llm-review-design.md` § "Phase 2: Autopilot mode" (commit 1e1786f).

**Phase-1 dependency:** Requires phase-1 (HEAD `4c2eb04`) merged. State.db, fingerprint, dispatch wrapper, ClaudeReviewer, and agent.poll_verdicts are pre-existing.

---

## File Structure

**New files:**

| Path | Responsibility |
|---|---|
| `adaptive-forex-mt5/consensus.py` | Compute 2-of-2 consensus from a pair of phase-1 verdicts. Pure function. |
| `adaptive-forex-mt5/autopilot.py` | The 12-gate executor + place call. Reads state.db, journal, original ready_alert (by alert_id). Re-runs sniper_poc only inside the fingerprint/drift gate. |
| `adaptive-forex-mt5/news.py` | News-blackout helper — `is_blackout_active(cfg, pair)`. Fails closed when `autopilot.news_source` is null. |
| `.ehukaiconnect/skills/CodexReviewer/SKILL.md` | Second reviewer agent skill (mirrors ClaudeReviewer but writes `<alert_id>-codex.json`). |
| `adaptive-forex-mt5/tests/test_consensus.py` | Strict-2-of-2 unit tests. |
| `adaptive-forex-mt5/tests/test_autopilot_gates.py` | 12 gates, each tested independently. |
| `adaptive-forex-mt5/tests/test_kill_switch.py` | Kill-switch flip via cursor + bus listener. |
| `adaptive-forex-mt5/tests/test_news_blackout.py` | Null source fails closed, in-window blocks, out-of-window allows. |

**Modified files:**

| Path | Changes |
|---|---|
| `adaptive-forex-mt5/agent.py` | Dual dispatch (one task per reviewer). Verdict poller invokes consensus + autopilot executor. New `bus_listener` thread for `AUTOPILOT ABORT`. |
| `adaptive-forex-mt5/journal.py` | Add `log_consensus_verdict`, `log_autopilot_placement`, `log_autopilot_skip`, `log_autopilot_kill`. |
| `adaptive-forex-mt5/dashboard.py` | New "Autopilot" panel: kill-switch state, shadow consensus stats (take vs no_consensus by pair), would-have P/L, daily caps used. |
| `adaptive-forex-mt5/config.example.json` | Add `autopilot` block per spec defaults. |
| `adaptive-forex-mt5/test_e2e.py` | Add `--autopilot` scenario (live-gated, requires master flag on). |
| `adaptive-forex-mt5/README.md` | Document the second reviewer launch + shadow phase. |

---

## Conventions

- TDD throughout. Every task: failing test → minimum impl → passing test → commit.
- Run `pytest adaptive-forex-mt5/tests -v` after each task.
- Imperative-mood commits ≤72 chars subject. Co-Authored-By line per Claude Code convention.
- Phase-2 ehukaiconnect tasks prefixed `p2-tNN-<short>` so `task list --mine` separates them from phase-1.

---

## Task 1: New journal kinds for autopilot

**Files:**
- Modify: `adaptive-forex-mt5/journal.py`
- Create: `adaptive-forex-mt5/tests/test_journal_kinds_phase2.py`

- [ ] **Step 1: Write the failing test**

```python
"""Phase-2 journal kinds: consensus_verdict, autopilot_placement, autopilot_skip, autopilot_kill."""
from __future__ import annotations
import json
import journal


def _kinds(log):
    return [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]


def test_log_consensus_verdict(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_consensus_verdict({
        "alert_id": "x", "setup_fingerprint": "deadbeef",
        "consensus": "take", "consensus_reason": "2-of-2",
        "votes": [], "reviewers": ["A", "B"],
    })
    assert _kinds(log) == ["consensus_verdict"]


def test_log_autopilot_placement(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_autopilot_placement(
        pair="USDJPY", placement={"data": {"placement": {"ticket": 99, "magic": 128461}}},
        consensus_alert_id="abc", reviewer_confidences=[0.84, 0.79],
    )
    assert _kinds(log) == ["autopilot_placement"]


def test_log_autopilot_skip(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_autopilot_skip(alert_id="abc", gate="news_blackout", reason="event_within_window")
    assert _kinds(log) == ["autopilot_skip"]


def test_log_autopilot_kill(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_autopilot_kill(prev="off", new="on", source="bus")
    assert _kinds(log) == ["autopilot_kill"]
```

- [ ] **Step 2: Implement in journal.py** — append four new functions mirroring the phase-1 pattern.

- [ ] **Step 3: Run tests, expect 4 passed.** **Step 4: Commit.**

---

## Task 2: CodexReviewer skill

**Files:**
- Create: `.ehukaiconnect/skills/CodexReviewer/SKILL.md`

Mirror `ClaudeReviewer/SKILL.md` exactly except:
- Verdict path: `.ehukaiconnect/shared/files/verdicts/<alert_id>-codex.json`
- `model` field in verdict: whatever Codex CLI is configured with on this workspace (e.g. `gpt-5-codex` or similar)

The advisory-only invariant and the `accepted_levels` rule are identical. Same `reviewed_fingerprint` requirement.

Commit with `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`.

---

## Task 3: Dual dispatch in agent.py

**Files:**
- Modify: `adaptive-forex-mt5/agent.py`
- Create: `adaptive-forex-mt5/tests/test_dual_dispatch.py`

- [ ] **Step 1: Failing test** — patch `agent.dispatch` and assert `create_review_task` is called twice per READY (once per `cfg.autopilot.reviewer_agents` entry), each with the SAME alert payload.

- [ ] **Step 2: Update agent.py alerts-only branch** — replace the single `dispatch.create_review_task(...)` call with a loop:

```python
# autopilot is a TOP-LEVEL cfg block, NOT under cfg.agent (per spec).
# Reading from a.get("autopilot") would silently fall back to the
# single-reviewer phase-1 path — Codex1 caught this in the plan
# orientation review.
reviewers = (cfg.get("autopilot") or {}).get("reviewer_agents") \
    or [a.get("reviewer_agent", "ClaudeReviewer")]
task_ids = []
for reviewer in reviewers:
    task_id = dispatch.create_review_task(payload, alerts_dir=..., reviewer=reviewer)
    if task_id:
        task_ids.append((reviewer, task_id))
        journal.log_review_request(alert_id=alert_id, task_id=task_id, pair=pair)
```

- [ ] **Step 3: Tests pass. Step 4: Commit.**

---

## Task 4: consensus.py — 2-of-2 strict logic

**Files:**
- Create: `adaptive-forex-mt5/consensus.py`
- Create: `adaptive-forex-mt5/tests/test_consensus.py`

- [ ] **Step 1: Failing tests** covering:
  - Both `take` + same direction + both confidence>=threshold + both `accepted_levels=true` + same `reviewed_fingerprint`=alert.fingerprint → consensus=take.
  - One `skip` → no_consensus reason=`one_skipped`.
  - Direction mismatch → no_consensus reason=`direction_mismatch`.
  - Confidence below threshold (one of them) → no_consensus reason=`confidence_below_threshold`.
  - One has `accepted_levels=false` (adjusted_*) → no_consensus reason=`levels_not_accepted`.
  - `reviewed_fingerprint` doesn't match alert → no_consensus reason=`fingerprint_mismatch`.

```python
def test_strict_take_passes_all_invariants():
    alert_fp = "deadbeef"
    votes = [
        {"reviewer": "A", "decision": "take", "direction": "buy",
         "confidence": 0.84, "accepted_levels": True, "reviewed_fingerprint": alert_fp},
        {"reviewer": "B", "decision": "take", "direction": "buy",
         "confidence": 0.79, "accepted_levels": True, "reviewed_fingerprint": alert_fp},
    ]
    out = consensus.evaluate(votes, alert_fingerprint=alert_fp, min_confidence=0.75)
    assert out["consensus"] == "take"


def test_one_skip_blocks():
    alert_fp = "deadbeef"
    votes = [
        {"reviewer": "A", "decision": "take", "direction": "buy",
         "confidence": 0.84, "accepted_levels": True, "reviewed_fingerprint": alert_fp},
        {"reviewer": "B", "decision": "skip",  "direction": "buy",
         "confidence": 0.50, "accepted_levels": False, "reviewed_fingerprint": alert_fp},
    ]
    out = consensus.evaluate(votes, alert_fingerprint=alert_fp, min_confidence=0.75)
    assert out["consensus"] == "no_consensus"
    assert "one_skipped" in out["consensus_reason"]
```

- [ ] **Step 2: Implement consensus.py** as a pure function:

```python
def evaluate(votes: list[dict], *, alert_fingerprint: str, min_confidence: float) -> dict:
    if len(votes) != 2:
        return {"consensus": "no_consensus", "consensus_reason": "wrong_vote_count"}
    a, b = votes
    if a["decision"] != "take" or b["decision"] != "take":
        return {"consensus": "no_consensus", "consensus_reason": "one_skipped" if "skip" in (a["decision"], b["decision"]) else "not_both_take"}
    if a["direction"] != b["direction"]:
        return {"consensus": "no_consensus", "consensus_reason": "direction_mismatch"}
    if not (a.get("accepted_levels") and b.get("accepted_levels")):
        return {"consensus": "no_consensus", "consensus_reason": "levels_not_accepted"}
    if a["reviewed_fingerprint"] != alert_fingerprint or b["reviewed_fingerprint"] != alert_fingerprint:
        return {"consensus": "no_consensus", "consensus_reason": "fingerprint_mismatch"}
    if min(a["confidence"], b["confidence"]) < min_confidence:
        return {"consensus": "no_consensus", "consensus_reason": "confidence_below_threshold"}
    return {"consensus": "take", "consensus_reason": f"2-of-2 take, conf min={min(a['confidence'], b['confidence'])} >= {min_confidence}"}
```

- [ ] **Step 3: Run, commit.**

---

## Task 5: agent.py — consensus evaluator + journal record

**Files:**
- Modify: `adaptive-forex-mt5/agent.py`
- Create: `adaptive-forex-mt5/tests/test_consensus_join.py`

- [ ] **Step 1: Failing test** — `agent.evaluate_pending_consensus(cfg, db_path)` reads recent llm_verdict records from journal, groups by `alert_id`, when both reviewers' verdicts are present computes consensus via `consensus.evaluate`, journals `kind=consensus_verdict`, and de-dupes via state.db cursor.

- [ ] **Step 2: Implement evaluate_pending_consensus.**

The poll_verdicts loop in agent.py already journals individual `llm_verdict` records. After each loop, scan recent journal records, group by alert_id, and compute consensus when 2 verdicts exist. Cursor `last_consensus_seen` (alert_id last processed) prevents re-processing.

- [ ] **Step 3: Run, commit.**

---

## Task 6: news.py — blackout helper, fails closed when source null

**Files:**
- Create: `adaptive-forex-mt5/news.py`
- Create: `adaptive-forex-mt5/tests/test_news_blackout.py`

- [ ] **Step 1: Failing tests:**
  - `is_blackout_active(cfg, pair)` returns True when `cfg.autopilot.news_source` is None (fail-closed).
  - With a fake source registered (mocked), returns True when an event is within `[-minutes_before, +minutes_after]`.
  - Returns False when no event in window.

- [ ] **Step 2: Implement** with a pluggable `_SOURCES = {}` registry; default empty so null-source fails closed:

```python
_SOURCES: dict = {}


def register_source(name: str, fetcher) -> None:
    _SOURCES[name] = fetcher


def is_blackout_active(cfg: dict, pair: str) -> bool:
    source = (cfg.get("autopilot") or {}).get("news_source")
    if source is None:
        return True  # fail closed
    fetcher = _SOURCES.get(source)
    if fetcher is None:
        return True
    before = float(cfg["autopilot"]["news_blackout_minutes_before"]) * 60
    after = float(cfg["autopilot"]["news_blackout_minutes_after"]) * 60
    now = datetime.now(timezone.utc)
    for event_ts in fetcher(pair):
        delta = (event_ts - now).total_seconds()
        if -after <= delta <= before:
            return True
    return False
```

- [ ] **Step 3: Run, commit.**

---

## Task 7: autopilot.py — kill-switch helpers

**Files:**
- Create: `adaptive-forex-mt5/autopilot.py` (start with kill-switch only; gates added in T9)
- Create: `adaptive-forex-mt5/tests/test_kill_switch.py`

- [ ] **Step 1: Failing tests** — `autopilot.kill_switch_get(db)` returns "off" by default, `kill_switch_set(db, "on", source="bus")` flips it and journals `autopilot_kill`, get returns "on" after.

- [ ] **Step 2: Implement** using `state_db.cursor_get/set` with name `autopilot_kill`. On flip, call `journal.log_autopilot_kill`.

- [ ] **Step 3: Run, commit.**

---

## Task 8: agent.py — bus listener for AUTOPILOT ABORT

**Files:**
- Modify: `adaptive-forex-mt5/agent.py`
- Create: `adaptive-forex-mt5/tests/test_bus_listener.py`

- [ ] **Step 1: Failing test** — patch `subprocess.run` (the `ehukaiconnect read` call), simulate a bus message containing `AUTOPILOT ABORT` from operator. Verify `kill_switch_set` is called with `"on"` and source `"bus"`.

- [ ] **Step 2: Implement** a small polling helper that calls `ehukaiconnect read 20 --json` (probe the actual flag at impl time) each scan, scans for the abort string, flips kill-switch on first match (idempotent — second match is a no-op since already on).

- [ ] **Step 3: Run, commit.**

---

## Task 9: autopilot.py — 12-gate executor

**Files:**
- Modify: `adaptive-forex-mt5/autopilot.py`
- Create: `adaptive-forex-mt5/tests/test_autopilot_gates.py`

- [ ] **Step 1: Failing tests, one per gate** (12 tests):

1. `enabled=false` blocks
2. `kill_switch=on` blocks
3. `consensus != take` blocks
4. pair not in allowlist blocks
5. alert age > max_alert_age_seconds blocks (`reason=stale_setup`)
6. fingerprint mismatch + drift > max_entry_drift_points blocks (`reason=stale_setup`)
7. `cfg.mt5_cli.live=false` blocks (`reason=not_live`)
8. spread > max blocks
9. news_source null → blackout active blocks
10. lot != autopilot.lot_size blocks
11. daily_trade_cap exceeded blocks; daily_loss_cap exceeded blocks
12. `(pair, magic)` already in `active_strategies` blocks

Each gate test: set up state to make ONLY that gate fail, assert `attempt_autopilot_place` returns failure with the right `gate` reason in `autopilot_skip`, no `mt5 order limit` call.

- [ ] **Step 2: Implement** `attempt_autopilot_place(cfg, db_path, alert, consensus)`.

**Codex1 BLOCKER #1 (must-have):** placement MUST use `mt5 order limit
SYMBOL DIR --price <ENTRY> --sl <SL> --tp <TP> --volume <V> --magic <M>`
with the EXACT levels stored on the alert (`alert['setup']['entry'/'sl'/'tp']`).
The phase-1 path `mt5 order ready-limit` re-runs `sniper_poc()` and uses
its own `final_entry/final_sl/final_tp` — that re-evaluation step
violates the autopilot invariant "place only the deterministic levels
the reviewers approved." `order limit` exists and accepts explicit
levels (verified against `mt5 order limit --help`).

Skeleton:

```python
def attempt_autopilot_place(cfg, db_path, alert, consensus):
    ap = cfg["autopilot"]
    aid = alert["alert_id"]

    # Gates 1-3 (config / kill / consensus)
    if not ap.get("enabled"):
        journal.log_autopilot_skip(aid, "enabled", "off"); return None
    if kill_switch_get(db_path) == "on":
        journal.log_autopilot_skip(aid, "kill_switch", "on"); return None
    if consensus.get("consensus") != "take":
        journal.log_autopilot_skip(aid, "consensus", consensus.get("consensus_reason")); return None

    # Gate 4 — pair allowlist
    if alert["pair"] not in (ap.get("pair_allowlist") or []):
        journal.log_autopilot_skip(aid, "pair_allowlist", alert["pair"]); return None

    # Gate 5 — alert age
    if _alert_age_seconds(alert) > float(ap["max_alert_age_seconds"]):
        journal.log_autopilot_skip(aid, "alert_age", "stale_setup"); return None

    # Gate 6 — fingerprint or bounded drift against current setup
    if not _fingerprint_or_drift_ok(cfg, alert, ap):
        journal.log_autopilot_skip(aid, "fingerprint_or_drift", "stale_setup"); return None

    # Gate 7 — live-intent (NEVER call broker without it)
    if not cfg["mt5_cli"].get("live"):
        journal.log_autopilot_skip(aid, "live", "not_live"); return None

    # Gate 8 — spread cap (current quote)
    spread = _current_spread(cfg, alert["pair"])
    if spread is None or spread > float(cfg["manager"]["max_spread_points"]):
        journal.log_autopilot_skip(aid, "spread_cap", f"spread={spread}"); return None

    # Gate 9 — news blackout (fails closed when news_source is null)
    if news.is_blackout_active(cfg, alert["pair"]):
        journal.log_autopilot_skip(aid, "news_blackout", "active_or_unavailable"); return None

    # Gate 10 — micro-lot only
    if float(ap.get("lot_size", 0)) <= 0:
        journal.log_autopilot_skip(aid, "lot_size", "invalid"); return None

    # Gate 11 — daily caps (autopilot-only counts)
    if not _within_caps(db_path, ap):
        journal.log_autopilot_skip(aid, "daily_caps", "exceeded"); return None

    # Gate 12 — one active strategy per (pair, magic)
    if _already_active(cfg, alert):
        journal.log_autopilot_skip(aid, "active_strategy", "already_open"); return None

    # All 12 gates pass → place at the bot's ORIGINAL setup levels via
    # `mt5 order limit` (NOT ready-limit which re-runs sniper_poc).
    setup = alert["setup"]
    magic = _derive_magic(f"{cfg['agent']['strategy_id_prefix']}-{alert['pair']}")
    cmd = [
        cfg["mt5_cli"]["command"], "--live", "--json",
        "order", "limit", alert["pair"], alert["direction"],
        "--price",  f"{setup['entry']}",
        "--sl",     f"{setup['sl']}",
        "--tp",     f"{setup['tp']}",
        "--volume", f"{ap['lot_size']}",
        "--magic",  str(magic),
        "--strategy-id", f"{cfg['agent']['strategy_id_prefix']}-{alert['pair']}",
    ]
    placement = _run_cli_capture(cmd)
    if placement and placement.get("ok"):
        journal.log_autopilot_placement(
            pair=alert["pair"], placement=placement,
            consensus_alert_id=aid,
            reviewer_confidences=[float(v["confidence"]) for v in consensus["votes"]],
        )
    return placement
```

Tests must verify:
- The all-pass test asserts `cmd` includes `alert['setup']['entry'/'sl'/'tp']`
  EXACTLY, even when a mocked current `sniper_poc` returns different levels.
- A `decision="adjust"` verdict from one reviewer cannot reach this path
  (consensus.evaluate already short-circuits) — but T9 itself must NEVER
  read `verdict.adjusted_*` fields.
- Each gate has its own fail-fast test that asserts NO `order limit` call
  is made and `autopilot_skip` is journaled with the right `gate`/`reason`.
- The live-intent gate (#7) is exercised BEFORE any broker call so a
  `live=false` config never even touches the wire.

Helper specs:
- `_fingerprint_or_drift_ok(cfg, alert, ap)`: run `sniper_poc(pair)`. If
  `current.setup_fingerprint == alert.setup_fingerprint` → True. Else if
  same direction + same POI id + same structure event AND each of
  `entry/sl/tp` differs from alert by ≤ `max_entry_drift_points` → True.
  Else False.
- `_within_caps(db_path, ap)`: count today's `kind=autopilot_placement`
  rows joined to `kind=outcome` rows for autopilot_realized_loss_today
  (autopilot-only — manual placements do NOT count).
- `_already_active(cfg, alert)`: reuse `agent.active_strategies(cfg)`
  which already includes pending orders + open positions.

- [ ] **Step 3: Run, commit.**

---

## Task 10: agent.py — wire executor into verdict poller

**Files:**
- Modify: `adaptive-forex-mt5/agent.py`
- Create: `adaptive-forex-mt5/tests/test_autopilot_pipeline.py`

- [ ] **Step 1: Failing test** — full happy path: 2 reviewer verdicts arrive, consensus=take, all 12 gates pass, autopilot.attempt_autopilot_place is called and journals `autopilot_placement`.

- [ ] **Step 2: Implement** in `agent.evaluate_pending_consensus` (or a sibling function): after each `consensus_verdict` is journaled, if `autopilot.enabled` and `consensus=take`, look up the ORIGINAL `ready_alert` record by `alert_id` (it carries `setup.entry/sl/tp`, `setup_fingerprint`, `pair`, `direction`), then call `autopilot.attempt_autopilot_place(cfg, db_path, original_alert, consensus)`. **Do not re-run `sniper_poc()` here to construct levels.** The autopilot executor's gate #6 will run `sniper_poc()` itself for fingerprint/drift verification — that's the only place re-evaluation is allowed.

- [ ] **Step 3: Run, commit.**

---

## Task 11: Config additions

**Files:**
- Modify: `adaptive-forex-mt5/config.example.json`
- Modify: `adaptive-forex-mt5/config.json`

Add the `autopilot` block per the spec:

```json
"autopilot": {
  "enabled": false,
  "reviewer_agents": ["ClaudeReviewer", "CodexReviewer"],
  "min_confidence": 0.75,
  "pair_allowlist": ["USDJPY"],
  "lot_size": 0.001,
  "daily_trade_cap": 5,
  "daily_loss_cap_usd": 5.00,
  "news_blackout_minutes_before": 15,
  "news_blackout_minutes_after": 30,
  "news_source": null,
  "decision_timeout_seconds": 90,
  "max_alert_age_seconds": 180,
  "max_entry_drift_points": 30
}
```

Commit.

---

## Task 12: Dashboard autopilot panel

**Files:**
- Modify: `adaptive-forex-mt5/dashboard.py`

Add to `_state_payload()`:
- `kill_switch` state
- Shadow consensus stats: count of `consensus=take` vs `no_consensus` per pair, last 24h, from `kind=consensus_verdict` records
- Daily caps used: `autopilot_trades_today`, `autopilot_realized_loss_today` (computed from `kind=autopilot_placement` + `kind=outcome` joined)

Render a new section under "Process heartbeat" with a kill-switch status pill (red OFF / amber ON / green DISABLED) and the shadow stats grid.

Commit.

---

## Task 13: README + e2e

**Files:**
- Modify: `adaptive-forex-mt5/README.md` — document the second reviewer launch and the shadow phase.
- Modify: `adaptive-forex-mt5/test_e2e.py` — add `--autopilot` scenario (live-gated, requires `autopilot.enabled=true`).

Commit.

---

## Self-Review

After all 13 tasks:

- Run `pytest -q` — expect ~85+ passed (59 phase-1 + ~25 phase-2 new).
- Spec coverage: cross-check each invariant in spec § "Invariants (additive)" against a task that enforces it.
- Confirm the spec's 12 gate parity items each have a passing test under `test_autopilot_gates.py`.
- Manually inspect that `autopilot.enabled=false` shipping default holds in `config.example.json` AND that `news_source: null` is the default fail-closed setting.

---

## Plan complete

Saved to `docs/superpowers/plans/2026-05-08-autopilot-consensus.md`. Recommended execution: subagent-driven for the 12 gate tests (each is independent), inline for the rest.
