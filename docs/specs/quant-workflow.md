# Quant Workflow Spec

Status: Proposed
Date: 2026-06-16
Owner: metatrader5-cli maintainers
Related playground: [Quant Workflow](../playgrounds/specs/quant-workflow.html)
Related plan: to be written after this spec is reviewed

## Purpose

`mt5 quant` turns the research pipeline from the "AI quant workflow" into one
tool-true command. `quant run` drives the **native** MT5 Strategy Tester across
a symbol × timeframe matrix: genetic optimization on an in-sample window,
out-of-sample forward validation, configurable selection gates, a ranking
metric, and a consolidated `quant.v1` envelope plus a dependency-free HTML
report.

The point of the slice: a trader's real cost is not running one backtest — it
is running the same logic across many assets and timeframes, splitting each into
in/out-of-sample, gating on trade count and profit factor, and ranking the
survivors. The video calls this "500 clicks, 5 hours" done by hand. This repo
already ships every native primitive needed; `quant` is the orchestration layer
that was missing, modeled exactly on `tester ea stress` (many native runs → one
graded `*.v1` envelope).

The boundary is the whole point. The video's other half — a Python research
engine (EDA heatmaps, autocorrelation), a Python vectorized backtester, and
Python→MQL5 translation — is **out of scope**, because the charter is "no
strategy logic, no indicator math, no pandas … not a separate Python
backtester" (`README.md:18-19`). The user's compiled EA stays the only source
of alpha; the harness never computes a signal.

## Source Anchors

- Orchestration template: `mt5_cli/tester/ea.py:304` — `stress()` runs many
  `single()` passes serially (the launcher forbids parallel terminals),
  aggregates per-scenario envelopes, and attaches a graded block. `quant`
  reuses this shape one altitude up.
- Per-cell primitives: `mt5_cli/tester/ea.py:152` (`optimize()`, already
  threads `forward`, `mode`, and `params`), `mt5_cli/tester/ea.py:45`
  (`single()`, accepts a `set_file`).
- Genetic mode code: `mt5_cli/tester/ea.py:18` — `_OPT_MODES["genetic"] = 2`.
- Multi-symbol precedent (raw, no optimization): `mt5_cli/tester/ea.py:273`
  (`scanner()`).
- Pure-module precedent for scoring: `mt5_cli/tester/stress.py` — stdlib-only,
  no filesystem, no launcher; `ea.py` feeds it already-parsed numbers.
- Stats source: `mt5_cli/tester/results.py:184-256` — `parse_html_report()`
  yields `net_profit`, `profit_factor`, `max_drawdown_pct`, `total_trades`,
  `win_rate`, `sharpe`, `expectancy`, and an `equity_curve`.
- Optimization parsing to extend: `mt5_cli/tester/results.py:285` —
  `parse_optimization_xml()` reads each `<pass>` generically; it must gain
  back-result (in-sample) vs forward-result (out-of-sample) awareness when
  `forward` is set.
- Run cache: `mt5_cli/tester/cache.py:17-38` (`make_run_id`, `run_dir`) and
  `:41-63` (`list_recent`, `get_run`) — child runs register here so
  `tester list` / `tester show` keep seeing them.
- Envelope contract: `mt5_cli/reports/envelope.py` — `ok` / `fail`; failure
  detail lives under `error.data`, frozen by the envelope-contract test.
- Error registry: `mt5_cli/errors.py` — new codes must be registered
  (test-enforced).
- CLI wiring: `mt5/cli.py` — thin click wrapper over the library
  (`pyproject.toml:69`, `mt5 = "mt5.cli:main"`).
- Lean-deps charter: `pyproject.toml:38-48` — "carries no pandas / pandas-ta /
  indicator-math stack." The report renderer stays pure-Python + inline SVG.

## Durable Wedge

Six-month thesis: multi-asset genetic optimization with a forward split is
native MT5 — the platform owns the simulation and the split. This repo owns what
the platform does not ship: matrix orchestration across cells, a deterministic
selection/ranking contract, and a machine-readable ranked envelope an agent
gates on without a human reading eight HTML reports. Better agents make a
deterministic campaign more valuable, not less — the agent fans out the matrix,
parses `quant.v1`, and decides the next research loop.

Specific workflow: a trader (or their agent) writes one EA, then runs
`mt5 quant run` across their watchlist and a couple of timeframes. The ranked
survivors come back as data; `jq '.data.ranked[0]'` is enough to pick the
winner to forward to `tester ea stress` before risking capital.

## Goals

- Expand a `symbols × timeframes` matrix and drive each cell through the hybrid
  validation (forward-split genetic optimize → pick winner → re-run winner over
  FULL).
- Apply deterministic selection gates (min FULL trades, min in-sample PF) and a
  configurable ranking metric; record rejects with reasons.
- Mark each survivor `validated` against an out-of-sample PF floor, without
  letting OOS alone drive the ranking.
- Return one `quant.v1` envelope an agent consumes without parsing prose, plus a
  dependency-free HTML report and a re-loadable `manifest.json`.
- Keep child runs cached under `results/` so the existing tester listing and
  show commands work unchanged.

## Non-Goals

- No Python EDA engine (return distribution, weekday × hour heatmap,
  autocorrelation) — needs numpy/pandas the charter excludes.
- No Python vectorized backtester and no Python→MQL5 translation; MT5 remains
  the only simulation engine and the EA remains the only alpha.
- No walk-forward beyond the single native forward split.
- No multi-data-feed or news (CPI/FOMC/NFP) testing.
- No campaign resume in v1 (child runs are cached; resume can come later).
- No new live-trade surface and no MCP exposure for `quant run` (long-running,
  launches a terminal); `quant list` / `show` are read-only and MCP-safe.
- No trading strategy, signal generation, indicator math, or market opinion.

## Architecture

A new package `mt5_cli/quant/`, same layering discipline as the tester stack
(pure modules below, orchestration above, the CLI a thin wrapper). It imports
`mt5_cli.tester.ea` and writes no strategy logic.

1. `matrix.py` — pure, stdlib-only: expand and validate `symbols × timeframes`,
   parse `--split` (a `0..1` fraction or a `YYYY-MM-DD` date) into the MT5
   `forward` value, parse `--param NAME=start,step,stop` ranges. Rejects an
   empty matrix (`EMPTY_MATRIX`) and a malformed split (`INVALID_SPLIT`) through
   one shared gate, so the typed library path is held to the same contract as
   the CLI string path (the same rule as core-layer risk and the stress ladder).
2. `selection.py` — pure, stdlib-only: `pick_winner(passes, rank_by)` chooses
   the optimization pass whose in-sample clears the gates, best by the ranking
   metric; `gate_and_rank(cells, selection)` applies the gates, ranks survivors,
   caps per asset, and records rejects with reasons. The `tester/stress.py`
   analog.
3. `report.py` — pure, stdlib-only: render the consolidated HTML from assembled
   cells — a ranked summary table, a per-strategy IS/OOS/FULL card, and an
   inline-SVG equity curve with the in/out-of-sample split marker, linking to
   each child run's native MT5 `report.html`. No matplotlib, no pandas; the SVG
   is a generated polyline over the parsed `equity_curve`.
4. `campaign.py` — orchestration: expand the matrix, run each cell's hybrid
   serially, assemble cell records, call `selection`, write artifacts, and
   return `quant.v1`. The `ea.stress()` analog.
5. `store.py` — campaign id (`make_campaign_id()` → a `quant`-prefixed
   `make_run_id`-style stamp) and `manifest.json` read/write, plus
   `list_campaigns()` / `get_campaign(id)`, reusing `tester/cache.py`
   conventions.
6. `mt5/cli.py` — a new `quant` click group (`run`, `list`, `show`) that parses
   flags and calls the library. No business logic.

One cross-cutting change: `results.parse_optimization_xml()` gains back-vs-forward
awareness so a winner's in-sample and out-of-sample metrics are read from the
same pass row.

### Per-cell hybrid

For each `(symbol, timeframe)` cell, serially:

1. `ea.optimize(mode="genetic", forward=split, params=…, from=FULL, to=FULL)` →
   `optimization.xml` with a back (IS) and forward (OOS) result per pass.
2. `selection.pick_winner(passes, rank_by)` → the winning parameter set → write
   a `.set`.
3. `ea.single(set_file=winner.set, from=FULL, to=FULL)` → a continuous
   `report.html`: the merged equity curve crossing the split + FULL stats.
4. Assemble the cell: IS & OOS from the winner's XML row, FULL from the re-run,
   the equity curve split at the forward date. ~2 native launches per cell.

### Selection & ranking contract

- Hard gates: `total_trades` (FULL) ≥ `--min-trades` (default 300) and
  `profit_factor` (in-sample) ≥ `--min-pf` (default 1.0).
- Validation flag: `oos_profit_factor ≥ --oos-min-pf` (default 1.0) sets
  `validated: true/false`. OOS is an honesty check, **not** the ranking key — a
  strongly-trending long-only asset (the video's GOLD, up ~150–200%) posts a
  flattering OOS curve that is the asset, not the edge.
- Ranking metric: `--rank-by` (default `oos_sharpe`; also `full_net`,
  `is_sharpe`, `profit_factor`). Keep the top `--per-asset` (default 2) per
  asset, matching the video's rank-1/rank-2 summary layout.
- Rejected entries carry a reason code: `MIN_TRADES`, `MIN_PF`, or
  `CELL_FAILED`.

### Envelope: `quant.v1`

```json
{
  "ok": true,
  "data": {
    "schema": "quant.v1",
    "campaign_id": "2026-06-16T19-40-00_quant_alpha",
    "expert": "alpha",
    "matrix": { "symbols": ["EURUSD", "XAUUSD"], "timeframes": ["H1"] },
    "from": "2022-01-01", "to": "2024-12-31",
    "split": "0.70",
    "selection": { "min_trades": 300, "min_pf": 1.0, "oos_min_pf": 1.0,
                   "rank_by": "oos_sharpe", "per_asset": 2 },
    "ranked": [
      { "rank": 1, "symbol": "XAUUSD", "timeframe": "H1", "side": "long",
        "validated": true,
        "set_file": "results/<child>/alpha.XAUUSD.H1.set",
        "run_id": "2026-06-16T19-41-10_alpha_XAUUSD_H1",
        "full": { "trades": 804, "net_profit": 55198.59, "profit_factor": 2.02 },
        "is":   { "trades": 609, "profit_factor": 2.10, "sharpe": 1.91 },
        "oos":  { "trades": 195, "profit_factor": 2.02, "sharpe": 1.79 } }
    ],
    "rejected": [
      { "symbol": "UKOIL", "timeframe": "H1", "reason": "MIN_TRADES",
        "full": { "trades": 142 } }
    ],
    "artifacts": {
      "report_html": "results/2026-06-16T19-40-00_quant_alpha/report.html",
      "manifest":    "results/2026-06-16T19-40-00_quant_alpha/manifest.json"
    }
  }
}
```

## Command Contract

```
mt5 quant run --expert <EA> --symbols A,B,C --tf H1,H2 \
  --from YYYY-MM-DD --to YYYY-MM-DD --split <fraction|YYYY-MM-DD> \
  [--param NAME=start,step,stop ...] [--mode genetic|complete] \
  [--min-trades 300] [--min-pf 1.0] [--oos-min-pf 1.0] \
  [--rank-by oos_sharpe] [--per-asset 2] \
  [--modelling ohlc-1m] [--no-html] [--dry-run] [--timeout 1800]

mt5 quant list
mt5 quant show <campaign-id>
```

- Exit code stays 0; callers parse the envelope's `ok` boolean (repo-wide rule).
- `--dry-run` returns the expanded matrix, cell count, and launch count, and
  launches nothing.
- `--timeout` is per native launch, threaded into `optimize()` and `single()`.
- `--modelling` defaults to `ohlc-1m` for the optimization sweep (speed); the
  FULL re-run inherits `single()`'s default unless overridden.

## Error Codes

Register in `mt5_cli/errors.py` (test-enforced):

- `EMPTY_MATRIX` — "A quant campaign needs at least one symbol and one timeframe."
- `INVALID_SPLIT` — "--split must be a 0..1 fraction or a YYYY-MM-DD date."
- `NO_WINNER` — "Optimization produced no pass clearing the selection gates."

A cell whose optimize or re-run fails does not abort the campaign: its fail
envelope ships in `rejected` with `reason: "CELL_FAILED"`, and the run continues.
The command fails outright only when no cell yields a ranked or rejected record.

## Acceptance Tests

Matrix (pure):

1. `EURUSD,XAUUSD × H1,H2` expands to 4 ordered cells; duplicates dedupe.
2. `--split 0.70` and `--split 2024-06-01` both parse; `1.5`, `abc`, and an
   empty value raise `INVALID_SPLIT`.
3. An empty symbol or timeframe set raises `EMPTY_MATRIX` on the library path,
   not just the CLI.
4. `--param Risk=0.5,0.5,3.0` parses to the MT5 range triple; a malformed range
   is rejected.

Optimization parsing (pure, fixtures):

5. A forward-enabled `optimization.xml` fixture yields, per pass, distinct
   back (IS) and forward (OOS) metric blocks.

Selection (pure):

6. `pick_winner` ignores passes failing the in-sample gates and returns the best
   remaining by `rank_by`; `NO_WINNER` when none clear the gates.
7. Gates: a cell with FULL trades < `min_trades` rejects `MIN_TRADES`; in-sample
   PF < `min_pf` rejects `MIN_PF`.
8. `validated` is true only when OOS PF ≥ `oos_min_pf`, and a `validated: false`
   survivor still ranks (OOS is not a hard gate).
9. Ranking respects `rank_by` and caps at `per_asset` per asset; rejects are
   ordered after survivors with reasons.

Orchestration (fake launcher, no terminal):

10. `campaign.run` issues exactly two native launches per cell (optimize then
    single), serially, and assembles `quant.v1`.
11. A cell whose optimize fails ships `reason: "CELL_FAILED"` in `rejected` and
    does not stop later cells.
12. An empty matrix returns `EMPTY_MATRIX` and launches nothing.
13. Child run ids are unique and registered under `results/`; the campaign
    `manifest.json` lists them and `get_campaign(id)` reloads it.
14. `--dry-run` returns the plan and issues zero launches.

Report (pure):

15. `report.render` produces self-contained HTML (no external `src`/`href` to a
    CDN), an inline-SVG `<polyline>` per equity curve, and a link to each child
    run's `report.html`.

CLI:

16. `quant run` happy path emits `quant.v1`; `quant list` / `quant show` read
    back a written campaign; new error codes are registered.

## Verification

Before merge: `ruff check .`, `pytest -m "not integration"`,
`mypy mt5_cli mt5 mt5_mcp`, `git diff --check`.

Live check (manual, optional, needs a closed terminal and a compiled demo EA):
run a 2-symbol × 1-timeframe campaign with a tiny param range and confirm two
child run dirs per cell, a `manifest.json`, and a `report.html` whose ranked
table matches the child runs' parsed stats.
