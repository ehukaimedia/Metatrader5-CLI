# Tester Stress & Delays Spec

Status: Implemented (PR #7)
Date: 2026-06-10
Owner: metatrader5-cli maintainers
Related playground: [Tester Stress & Delays](../playgrounds/specs/tester-stress-delays.html)
Related plan: [Tester Stress & Delays Plan](../plans/tester-stress-delays-plan.md)

## Purpose

`mt5 tester ea stress` currently runs an ideal-execution backtest and stamps
`stress_delay_ms` onto the envelope — the one field that claims stress is the
one thing the run does not apply. This spec wires MT5's native `ExecutionMode`
tester key into the INI layer, turns `stress` into a delay-ladder matrix
(ideal → fixed latencies → random), and adds a deterministic robustness score
with verdict bands an agent can gate on.

The point of the slice: the gap between backtest ROI and live ROI is mostly
execution quality. A strategy whose profit survives 100–500 ms and
random-delay fills has an edge that exists at a retail broker; one that
collapses was curve-fit to execution conditions the trader will never get.

## Source Anchors

- INI layer: `mt5_cli/tester/ini_builder.py:70-96` — `build_ea_ini()` emits no
  `ExecutionMode` key, so every run executes at the tester default (instant).
- Stress stub: `mt5_cli/tester/ea.py:285-306` — `stress()` delegates to
  `single()` unmodified and tags `stress_delay_ms` metadata only.
- CLI: `mt5/cli.py:1455-1465` — `mt5 tester ea stress --delays-ms` exposes the
  stub.
- Test locking in the stub: `tests/test_tester_ea.py:332-348`
  (`test_stress_adds_delay_metadata`).
- Stats source for scoring: `mt5_cli/tester/results.py:184-256` —
  `parse_html_report()` yields `net_profit`, `profit_factor`,
  `max_drawdown_pct`, `total_trades`, `win_rate`.
- Error registry: `mt5_cli/errors.py` — new codes must be registered
  (test-enforced).
- Layering precedent: `mt5_cli/tester/ea.py:17` (`_OPT_MODES`) maps
  trader-facing mode names to raw INI codes; the delay surface follows the
  same split.
- MT5 startup-configuration docs
  (metatrader5.com/en/terminal/help/start_advanced/start, verified
  2026-06-10): `ExecutionMode` — `0` normal, `-1` random delay in order
  execution, `>0` fixed delay in milliseconds, maximum `600000`.
- MT5 Strategy Tester help (metatrader5.com/en/terminal/help/algotrading/testing,
  verified 2026-06-10): the matching UI control emulates network delays with
  No Delay, Random Delay (a 0–9 second value picked per order), and Fixed
  Delay options.
- Envelope contract: `mt5_cli/reports/envelope.py:12-16` — failure detail
  lives under `error.data`, frozen by `tests/test_envelope_contract.py`.
- Run-id source: `mt5_cli/tester/cache.py:17-38` — second-resolution UTC
  timestamps, and `run_dir()` reuses an existing directory of the same name.

## Durable Wedge

Six-month thesis: delay emulation is native MT5 — the platform owns the
simulation, and that does not change if MetaQuotes or agent platforms improve.
This repo owns what the platform does not ship: scenario orchestration across
a ladder, a deterministic scoring contract, and a machine-readable verdict an
agent loop gates on without a human reading a chart. Better agents make a
deterministic robustness gate more valuable, not less.

Specific workflow: a trader (or their agent) optimizes an EA, then runs
`mt5 tester ea stress` on the surviving parameter set before risking capital.
The verdict is a banded number, so `jq '.data.robustness.verdict'` is enough
to decide the next step.

## Goals

- Emit a validated `ExecutionMode` key from the INI builder.
- Run a delay ladder serially as full tester runs, each cached under its own
  run id like any other run.
- Compute a deterministic robustness score (worst-case profit retention) with
  fixed verdict bands.
- Return one `stress.v1` envelope an agent consumes without parsing prose.
- Remove the misleading metadata-only stress path entirely.

## Non-Goals

- No stressed-optimization ranking — `optimize()` keeps default execution in
  this slice (future work).
- No spread, slippage, or requote modeling beyond MT5's native delay
  emulation.
- No multi-symbol stress matrix (compose with `scanner` later).
- No change to indicator testing or `build_indicator_ini()`.
- No custom backtester; MT5 remains the simulation engine.
- No trading strategy, signal generation, or market opinion.

## Architecture

Five parts, same layering as the existing tester stack:

1. `ini_builder.build_ea_ini(..., execution_mode: int = 0)` renders
   `ExecutionMode=<n>` in the `[Tester]` block; raises `ValueError` unless the
   value is `-1` or `0..600000`. The INI layer mirrors raw MT5 codes exactly
   (the `optimization` parameter is the precedent).
2. New module `mt5_cli/tester/stress.py` — pure and stdlib-only: delay-token
   parsing, ladder normalization, and robustness scoring. No filesystem, no
   launcher, no MT5 SDK.
3. `ea.single(..., delay_ms: int = 0)` threads the trader-facing value into
   the INI layer and records `delay_ms` in run metadata. The metadata reports
   the value actually written to the INI, never an unapplied request.
4. `ea.stress(..., delays: list[int] | None = None)` normalizes the ladder,
   runs one `single()` per delay serially (the launcher contract forbids
   parallel terminals), aggregates per-scenario envelopes, and attaches the
   robustness block. Each rung gets a collision-safe run id by folding the
   delay token into the expert component —
   `make_run_id(f"stress-{token}-{expert}", symbol, timeframe)` with token
   `0`, `100`, `random`, etc. — following the `opt-{mode}-` prefix precedent
   (`mt5_cli/tester/ea.py:173`). Run ids are otherwise second-resolution and
   `run_dir()` reuses an existing directory (`mt5_cli/tester/cache.py:17-38`),
   so without the token two same-second rungs would share `tester.ini` and
   report paths and corrupt the scenario evidence.
5. CLI `mt5 tester ea stress --delays 0,100,500,random` parses tokens and
   emits the envelope. `--delays-ms` is removed.

### Ladder contract

- Tokens: non-negative integers (milliseconds) or `random` (maps to `-1`).
- Validation: each value must be `-1` or `0..600000`; anything else fails with
  `INVALID_DELAYS`.
- Normalization: dedupe; the ideal-execution baseline `0` is always included
  (prepended when missing); order is `0` first, fixed delays ascending,
  `random` last. Deterministic order, deterministic envelope.
- Default ladder: `0,100,500,random`.

### Robustness scoring contract

With baseline = the `delay_ms=0` scenario:

- For each successful stressed scenario `i`:
  `retention_i = net_profit_i / net_profit_baseline`.
- `score = clamp(min(retention_i), 0.0, 1.0)`, rounded to 4 decimal places.
- Verdict bands: `robust` at score ≥ 0.85, `degraded` at ≥ 0.50, `fragile`
  below 0.50.
- `ungraded` (score is `null`): baseline `net_profit` is missing or ≤ 0, or no
  stressed scenario succeeded. A losing baseline cannot anchor retention; the
  envelope says so instead of inventing a number.
- Worst case (`min`), not mean: the score is a gate, and gates must fail on
  the worst path — a catastrophic 500 ms collapse must not be averaged away.
  Runner-up rejected: trade-count-weighted mean retention.
- Per-scenario detail rows: `delay_ms`, `net_profit`, `retention`,
  `profit_factor`, `max_drawdown_pct`, `total_trades`, `win_rate`.

Failure semantics:

- Baseline run fails → the whole command fails with `STRESS_BASELINE_FAILED`;
  the failed baseline envelope ships under `error.data.baseline`, matching the
  frozen failure shape `{"ok": false, "error": {"code", "message", "data"}}`
  (`mt5_cli/reports/envelope.py:12-16`, locked by
  `tests/test_envelope_contract.py`). No stressed scenarios run.
- A stressed scenario fails → remaining scenarios still run; the failed
  envelope ships in `scenarios`; scoring uses the successes;
  `robustness.incomplete = true`.

### Envelope: `stress.v1`

```json
{
  "ok": true,
  "data": {
    "schema": "stress.v1",
    "expert": "alpha",
    "symbol": "AUDUSD",
    "timeframe": "M5",
    "from": "2024-01-01",
    "to": "2024-06-30",
    "modelling": "real-ticks",
    "delays": [0, 100, 500, -1],
    "scenarios": [
      {"delay_ms": 0,
       "envelope": {"ok": true, "data": {"run_id": "2026-06-10T07-00-00_stress-0-alpha_AUDUSD_M5", "stats": {}}}},
      {"delay_ms": 100, "envelope": {}},
      {"delay_ms": 500, "envelope": {}},
      {"delay_ms": -1, "envelope": {}}
    ],
    "robustness": {
      "score": 0.9103,
      "verdict": "robust",
      "baseline_net_profit": 4180.0,
      "incomplete": false,
      "per_delay": [
        {"delay_ms": 100, "net_profit": 3990.5, "retention": 0.9547,
         "profit_factor": 1.71, "max_drawdown_pct": 8.2,
         "total_trades": 212, "win_rate": 0.56},
        {"delay_ms": 500, "net_profit": 3920.3, "retention": 0.9379,
         "profit_factor": 1.66, "max_drawdown_pct": 8.9,
         "total_trades": 209, "win_rate": 0.55},
        {"delay_ms": -1, "net_profit": 3804.9, "retention": 0.9103,
         "profit_factor": 1.62, "max_drawdown_pct": 9.4,
         "total_trades": 205, "win_rate": 0.54}
      ]
    }
  }
}
```

## Command Contract

```
mt5 tester ea stress --expert <EA> --symbol <SYM> --tf <TF> \
  --from YYYY-MM-DD --to YYYY-MM-DD \
  [--delays 0,100,500,random] [--modelling real-ticks] [--timeout 600]
```

- Exit code stays 0; callers parse the envelope's `ok` boolean (repo-wide
  rule).
- `--timeout` is per scenario, defaulting to the `single()` default.
- `--modelling` defaults to `real-ticks` — delay emulation against synthetic
  OHLC bars understates execution risk.

## Error Codes

Register in `mt5_cli/errors.py` (test-enforced):

- `INVALID_DELAYS` — "A delay must be 'random' or an integer 0..600000 ms."
- `STRESS_BASELINE_FAILED` — "The ideal-execution baseline run failed; no
  robustness score is possible."

## Breaking Changes

- `ea.stress(delays_ms=...)` becomes `ea.stress(delays=[...])`; CLI
  `--delays-ms` becomes `--delays`. The removed surface recorded stress
  metadata it never applied; carrying it forward as an alias would preserve
  the lie. Pre-1.0; recorded under CHANGELOG `Changed`.
- `build_ea_ini()` now always emits `ExecutionMode=0` by default. `0` is the
  tester's existing default behavior, so run results are unchanged; only the
  INI bytes differ.

## Acceptance Tests

INI layer:

1. `build_ea_ini()` default emits `ExecutionMode=0`.
2. `execution_mode=-1` and `execution_mode=250` emit those exact lines.
3. Boundaries: `execution_mode=600000` is accepted; `execution_mode=-2` and
   `execution_mode=600001` raise `ValueError` (negative/corruption path).

Pure stress module:

4. Token parsing: `"0,100,500,random"` → `[0, 100, 500, -1]`; `"junk"` and
   `700000` are rejected.
5. Normalization: dedupes, auto-includes the `0` baseline, deterministic order
   with `random` last.
6. Scoring: worst-case retention drives the score; clamps at both ends;
   rounds to 4 decimal places.
7. Ungraded when baseline `net_profit` ≤ 0 or missing; ungraded when no
   stressed scenario exists or succeeded — including a ladder of only `0`,
   which still runs the baseline and returns `score: null`,
   `verdict: "ungraded"`.
8. Partial failure: `incomplete=true` when a stressed scenario fails but
   others score. All stressed scenarios failing yields `score: null`,
   `verdict: "ungraded"`, `incomplete: true`.

Orchestration:

9. `single(delay_ms=...)` writes `ExecutionMode` into the run INI and
   `delay_ms` into run metadata.
10. `stress()` runs exactly one `single()` per normalized delay, serially, and
    assembles `stress.v1`.
11. Per-rung run ids are unique even when rungs start within the same
    second-resolution timestamp: the delay token appears in each run id
    (`stress-{token}-{expert}`), and no two rungs of one ladder share a run
    dir.
12. Baseline failure returns the exact frozen failure shape:
    `ok: false`, `error.code: "STRESS_BASELINE_FAILED"`, the failed baseline
    envelope under `error.data.baseline` — and runs no stressed scenarios.
13. `timeout` applies per scenario, not across the ladder: each `single()`
    call receives the full configured timeout.

CLI:

14. `--delays` happy-path parsing, and an `INVALID_DELAYS` fail envelope on a
    bad token.
15. New error codes are registered (the existing registry test covers this
    once they are added).

Removes `tests/test_tester_ea.py:332-348` (`test_stress_adds_delay_metadata`)
— it locks in the stub behavior this spec deletes.

## Verification

Before merge: `ruff check .`, `pytest -m "not integration"`,
`mypy mt5_cli mt5 mt5_mcp`, `git diff --check`.

Live check (manual, optional, needs a closed terminal and a demo EA): run a
two-rung ladder and confirm the two run dirs' `tester.ini` files differ only
in `ExecutionMode`, and the stressed journal shows delayed order execution.
