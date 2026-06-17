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
that was missing, modeled on `tester ea stress` (many native runs → one graded
`*.v1` envelope).

The boundary is the whole point. The video's other half — a Python research
engine (EDA heatmaps, autocorrelation), a Python vectorized backtester, and
Python→MQL5 translation — is **out of scope**, because the charter is "no
strategy logic, no indicator math, no pandas … not a separate Python
backtester" (`README.md:18-19`). The user's compiled EA stays the only source
of alpha; the harness never computes a signal.

To make an AI agent able to *operate* this loop as a quant — not just call the
commands — the spec also ships a quant agent playbook
(`mt5_cli/skills/QUANT_WORKFLOW.md`), drafted in full in
[Quant agent playbook](#quant-agent-playbook) below. The agent supplies the
hypotheses and authors the EA (its own native capabilities); the playbook wires
that reasoning to the commands and carries the judgment the video earns the hard
way — the asset-drift trap, trade-count sufficiency, multiple-testing
discipline, and execution stress. The tool stays hands; the agent is the brain.

## How MT5 forward optimization actually behaves

This shaped the per-cell contract, so it is stated up front (verified against
the code and MetaQuotes docs, 2026-06-16):

- `ForwardMode` is `1` (last ½), `2` (last ⅓), `3` (last ¼), or `4` (custom —
  split at `ForwardDate`); `ForwardDate` is honored **only** under
  `ForwardMode=4`. Today `build_ea_ini()` emits `ForwardMode=1` *and*
  `ForwardDate` together (`mt5_cli/tester/ini_builder.py:107-109`) — so a custom
  date is silently ignored and the split is always ½. This feature fixes that:
  any `--split` maps to `ForwardMode=4` + a computed `ForwardDate`. MT5 then
  optimizes on the in-sample (back) segment and **forward-tests only the
  selected best passes** on the out-of-sample segment.
- MT5 writes forward results to a **separate report** with a `.forward` suffix,
  not as extra columns on the back-result rows. The current
  `parse_optimization_xml()` (`mt5_cli/tester/results.py:285`) is a flat
  `<pass>` reader with no back/forward model, and `assemble()` parses only the
  one optimization file. There is no `.forward` handling anywhere today.

Consequences the earlier draft got wrong, now fixed in this spec: a single pass
row does **not** contain both IS and OOS; not every pass is forward-tested; and
reconstructing the winner's `.set` depends on the optimization report exposing
its input-parameter columns. The per-cell flow and launch-count claim are
rewritten accordingly, and the risky assumptions are fixture-gated (see
[Implementation risks](#implementation-risks-fixtures-required-before-build)).

## Source Anchors

- Orchestration template: `mt5_cli/tester/ea.py:304` — `stress()` runs many
  `single()` passes serially (the launcher forbids parallel terminals),
  aggregates per-scenario envelopes, and attaches a graded block.
- Per-cell primitives: `mt5_cli/tester/ea.py:152` (`optimize()`), which threads
  `forward` (`ea.py:160` signature, `ea.py:221` into `build_ea_ini`) and points
  at one `optimization.xml`; `mt5_cli/tester/ea.py:45` (`single()`), whose
  `set_file` parameter (`ea.py:59`) is staged at `ea.py:92`.
- Forward INI emission: `mt5_cli/tester/ini_builder.py:107-109` emits
  `ForwardMode=1` + `ForwardDate` — but MT5 honors `ForwardDate` only under
  `ForwardMode=4`, so this feature changes it to mode 4 for custom splits.
- `.set` rendering already exists: `mt5_cli/tester/ini_builder.py:181-212`
  (`render_set` / `write_set`), including the `value||start||step||stop||Y`
  optimization-range form.
- Genetic mode code: `mt5_cli/tester/ea.py:18` — `_OPT_MODES["genetic"] = 2`.
- Multi-symbol precedent (raw, no optimization): `mt5_cli/tester/ea.py:273`
  (`scanner()`).
- Stress today has no `set_file`: CLI `tester_ea_stress` (`mt5/cli.py:1526`)
  exposes no `--set-file`, and `ea.stress()` (`mt5_cli/tester/ea.py:304`) calls
  `single()` without one — so a winning parameter set cannot be stressed yet.
- Pure-module precedent for scoring: `mt5_cli/tester/stress.py` — stdlib-only,
  no filesystem, no launcher.
- Stats source: `mt5_cli/tester/results.py:184-256` — `parse_html_report()`
  yields `net_profit`, `profit_factor`, `max_drawdown_pct`, `total_trades`,
  `win_rate`, `sharpe`, `expectancy`, and an `equity_curve`.
- Bridge isolation: `mt5_cli/tester/__init__.py:15-17` — the tester package must
  not import MetaTrader5; `terminal64.exe` produces artifacts on disk. `quant`
  inherits this rule (see Architecture).
- Run cache: `mt5_cli/tester/cache.py:17-38` (`make_run_id`, `run_dir`) and
  `:41-63` (`list_recent`, `get_run`).
- Envelope contract: `mt5_cli/reports/envelope.py` — `ok` / `fail`; failure
  detail lives under `error.data`, frozen by the envelope-contract test.
- Error registry: `mt5_cli/errors.py` — new codes must be registered
  (test-enforced).
- CLI wiring: `mt5/cli.py` — thin click wrapper (`pyproject.toml:69`,
  `mt5 = "mt5.cli:main"`); `--json` is hoisted before Click parsing so it is
  position-independent.
- Lean-deps charter: `pyproject.toml:38-48` — no pandas/numpy stack.
- Agent-doc precedent: `mt5_cli/skills/USER_WORKSPACE.md` ships static markdown
  for agents to introspect, packaged via `pyproject.toml:107-111`
  (`"mt5_cli.skills" = ["*.md"]`). The quant playbook ships the same way.

## Durable Wedge

Six-month thesis: multi-asset genetic optimization with a forward split is
native MT5 — the platform owns the simulation and the split. This repo owns what
the platform does not ship: matrix orchestration across cells, a deterministic
selection/ranking contract, and a machine-readable ranked envelope an agent
gates on without a human reading eight HTML reports. Better agents make a
deterministic campaign more valuable, not less.

## Goals

- Expand a `symbols × timeframes` matrix and drive each cell through the hybrid
  validation (forward-split genetic optimize → pick winner → re-run winner over
  FULL), with an explicit-rerun fallback when the forward artifact does not
  cover the winner.
- Apply deterministic selection gates (min FULL trades, min in-sample PF) and a
  configurable ranking metric; record rejects with reasons.
- Mark each survivor `validated` against an out-of-sample PF floor, without
  letting OOS metrics be the default ranking key.
- Return one `quant.v1` envelope, a dependency-free HTML report, and a
  re-loadable `manifest.json`; keep child runs cached under `results/`.
- Add `set_file` support to `tester ea stress` so the playbook's "stress the
  winner" step can test the winning parameter set (small, well-scoped extension
  to the existing stress contract).
- Ship a quant agent playbook (`mt5_cli/skills/QUANT_WORKFLOW.md`) that turns the
  agent's own reasoning into the quant role.

## Non-Goals

- No Python EDA engine; no Python vectorized backtester; no Python→MQL5
  translation. MT5 stays the only engine; the EA stays the only alpha.
- No campaign-internal benchmark computation. The asset-drift check is an agent
  step using the existing `rates` command (see playbook) — pulling the rates
  module into `quant` would import the MetaTrader5 SDK and break bridge
  isolation.
- No walk-forward beyond the single native forward split; no multi-data-feed or
  news testing; no campaign resume in v1.
- No MCP exposure for `quant run` (long-running, launches a terminal);
  `quant list` / `show` are read-only and MCP-safe.
- No trading strategy, signal generation, indicator math, or market opinion.

## Architecture

A new package `mt5_cli/quant/`, same layering as the tester stack (pure modules
below, orchestration above, the CLI a thin wrapper). **Bridge isolation:** like
`mt5_cli/tester`, `quant` must not import MetaTrader5 — it drives the tester
through the filesystem only. An import-boundary test enforces this.

1. `matrix.py` — pure: expand/validate `symbols × timeframes`; parse `--split`
   into a `ForwardDate` — a `0<f<1` fraction becomes `from + f×(to−from)`
   (stdlib date math), an explicit `YYYY-MM-DD` is used as-is, and both drive
   `ForwardMode=4`; parse `--param NAME=value,start,step,stop` ranges (reusing
   `ini_builder.render_set`
   grammar). Rejects an empty matrix (`EMPTY_MATRIX`), a malformed split
   (`INVALID_SPLIT`), or a malformed range (`INVALID_PARAM`) through one shared
   gate, so the typed library path is held to the same contract as the CLI.
2. `passes.py` — pure: read the optimization back-result file and the
   `.forward` file, normalize each `<pass>` to a metric+parameter record, and
   **join back↔forward by pass id**. Extends/wraps
   `results.parse_optimization_xml` with the back/forward awareness it lacks
   today.
3. `selection.py` — pure: `pick_winner(joined_passes, *, min_pf, rank_by)`
   chooses, among passes whose in-sample clears `min_pf`, the best by the
   ranking metric and returns its parameter set; `gate_and_rank(cells,
   selection)` applies the FULL-trades gate, ranks survivors, caps per asset,
   and records rejects. The `tester/stress.py` analog.
4. `report.py` — pure: render the HTML from assembled cells — a ranked table, a
   per-strategy IS/OOS/FULL card, and an inline-SVG equity curve with the split
   marker, linking to each child run's native `report.html`. No matplotlib, no
   pandas; the SVG is a generated polyline over the parsed `equity_curve`.
5. `campaign.py` — orchestration: expand the matrix, run each cell's hybrid
   serially, assemble cells, call `selection`, write artifacts, return
   `quant.v1`. The `ea.stress()` analog.
6. `store.py` — `make_campaign_id()` and `manifest.json` read/write, plus
   `list_campaigns()` / `get_campaign(id)`, reusing `tester/cache.py`.
7. `mt5/cli.py` — a new `quant` click group (`run`, `list`, `show`); also adds
   `--set-file` to the existing `tester ea stress` command. No business logic.
8. `mt5_cli/skills/QUANT_WORKFLOW.md` — a static agent playbook shipped with the
   package (the `USER_WORKSPACE.md` precedent), drafted in
   [Quant agent playbook](#quant-agent-playbook). It ships in the same phase as
   the `quant` CLI so the doc never references a command the build lacks.

Cross-cutting changes to the tester layer: (a) `build_ea_ini()` emits
`ForwardMode=4` — not `1` — whenever a forward date is supplied, so the custom
`ForwardDate` is actually used; (b) `stress()` and CLI `tester ea stress` gain
an optional `set_file` / `--set-file` threaded into the `single()` calls they
already make.

### Per-cell hybrid (with fallback)

Each cell is one `(symbol, timeframe)`. Steps run serially.

1. `ea.optimize(mode="genetic", forward=split, params=…, from=FULL, to=FULL)` →
   the back-result `optimization.xml` (all passes, in-sample) plus MT5's
   `.forward` report (the selected passes, out-of-sample). **1 launch.**
2. `passes.join()` pairs back↔forward rows by pass id.
   `selection.pick_winner()` takes the best forward-covered pass clearing the
   in-sample `min_pf`, by `rank_by`, and reads its parameter columns → `.set`.
3. `ea.single(set_file=winner.set, from=FULL, to=FULL)` → the continuous FULL
   `report.html` (merged equity curve + FULL stats). **1 launch.**
4. Assemble the cell: IS from the back row, OOS from the forward row, FULL from
   the re-run; equity curve split at `ForwardDate`.

**Launches: 2 per cell** in the common path. **Fallback (+1 launch):** if the
winner was not forward-tested (so no `.forward` row), or the optimization report
lacks the metric columns needed for IS/OOS, run an explicit
`ea.single(set_file=winner.set, from=split, to=FULL)` over the held-out window to
produce OOS directly. The fallback is the same shape as the explicit two-pass
mechanism, scoped to the cells that need it.

> **Open mechanism choice for the maintainer.** The review exposed enough
> forward-artifact complexity (separate file, partial forward coverage, join by
> pass id) that the *explicit two-pass* mechanism — optimize IS-window → pick
> winner → `single` OOS-window → `single` FULL, a flat 3 launches/cell, no
> `.forward` parsing — may be the simpler, more robust default. This spec keeps
> the hybrid as the chosen default (per the brainstorm decision) with the
> explicit rerun already specced as the fallback, so switching the default is a
> one-line contract change if preferred.

### Selection & ranking contract

- **Gates (hard):** winner's FULL `total_trades` ≥ `--min-trades` (default 300);
  in-sample `profit_factor` ≥ `--min-pf` (default 1.0), enforced inside
  `pick_winner` (a cell whose best pass clears neither yields no winner).
- **`validated` flag:** OOS `profit_factor` ≥ `--oos-min-pf` (default 1.0). This
  is an honesty check, **not** a hard gate and **not** the ranking key — a
  `validated: false` survivor still ranks.
- **Ranking metric — `--rank-by`:** default **`full_net`** (whole-period
  realized net profit of the in-sample-selected parameters). Options:
  `full_net`, `oos_sharpe`, `oos_pf`. Choosing an `oos_*` key sets a top-level
  `rank_caveat` in the envelope, because out-of-sample metrics over-reward a
  trending asset (the GOLD case). Ranking only **orders candidates for review**;
  it never certifies edge — the `validated` flag and the agent's asset-drift
  check do. (IS-based rank keys are deferred until the optimization artifact's
  IS columns are fixture-proven.)
- **`--per-asset`** (default 2): keep the top N per asset, matching the video's
  rank-1/rank-2 layout.

### Reject reasons vs error codes

These were ambiguous in the earlier draft; resolved here.

- **Per-cell reject reasons** (entries in `rejected[]`, campaign continues):
  - `NO_WINNER` — optimization produced no pass clearing the in-sample gates.
  - `MIN_TRADES` — the winner's FULL trade count is below `--min-trades`.
  - `CELL_FAILED` — a native launch failed; the fail envelope is embedded.
- **Root command errors** (`ok: false`, frozen `{ok,error}` shape): input
  validation only — `EMPTY_MATRIX`, `INVALID_SPLIT`, `INVALID_PARAM`,
  `INVALID_RANK_BY` — plus the degenerate case where no cell yields any ranked
  or rejected record. `NO_WINNER` is **not** a root error; it is a per-cell
  reject reason.

### Envelope: `quant.v1`

Every `ranked[]` entry carries `full`, `is`, and `oos` blocks (the FULL block is
always present from the re-run; `is`/`oos` are present once the cell's
back/forward rows are read or the fallback OOS rerun runs).

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
                   "rank_by": "full_net", "per_asset": 2 },
    "rank_caveat": null,
    "ranked": [
      { "rank": 1, "symbol": "XAUUSD", "timeframe": "H1", "side": "long",
        "validated": true,
        "set_file": "results/<child>/alpha.XAUUSD.H1.set",
        "run_id": "2026-06-16T19-41-10_alpha_XAUUSD_H1",
        "full": { "trades": 804, "net_profit": 55198.59, "profit_factor": 2.02 },
        "is":   { "trades": 609, "profit_factor": 2.10, "sharpe": 1.91 },
        "oos":  { "trades": 195, "profit_factor": 2.02, "sharpe": 1.79 } },
      { "rank": 2, "symbol": "EURUSD", "timeframe": "H1", "side": "long",
        "validated": true,
        "set_file": "results/<child>/alpha.EURUSD.H1.set",
        "run_id": "2026-06-16T19-42-30_alpha_EURUSD_H1",
        "full": { "trades": 977, "net_profit": 13486.76, "profit_factor": 1.66 },
        "is":   { "trades": 743, "profit_factor": 1.68, "sharpe": 1.48 },
        "oos":  { "trades": 234, "profit_factor": 1.56, "sharpe": 1.01 } }
    ],
    "rejected": [
      { "symbol": "UKOIL", "timeframe": "H1", "reason": "MIN_TRADES",
        "full": { "trades": 142 } },
      { "symbol": "USDJPY", "timeframe": "H1", "reason": "NO_WINNER" }
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
  [--param NAME=value,start,step,stop ...] [--mode genetic|complete] \
  [--min-trades 300] [--min-pf 1.0] [--oos-min-pf 1.0] \
  [--rank-by full_net|oos_sharpe|oos_pf] [--per-asset 2] \
  [--modelling ohlc-1m] [--no-html] [--dry-run] [--timeout 1800]

mt5 quant list
mt5 quant show <campaign-id>

mt5 tester ea stress --expert <EA> --symbol <SYM> --tf <TF> \
  --from ... --to ... [--set-file results/<child>/<winner>.set] \
  [--delays 0,100,500,random]
```

- Exit code stays 0; callers parse the envelope's `ok` boolean.
- `--dry-run` returns the expanded matrix, cell count, and launch estimate (2
  per cell, noting the +1 fallback), and launches nothing.
- `--timeout` is per native launch.
- `--modelling` defaults to `ohlc-1m` for the optimization sweep; the FULL
  re-run inherits `single()`'s `real-ticks` default unless overridden.
- `tester ea stress --set-file` is the new flag this feature adds so a winner's
  parameter set can be stressed.

## Quant agent playbook

Full draft of `mt5_cli/skills/QUANT_WORKFLOW.md` — static markdown shipped with
the tool for any AI agent to introspect (the `USER_WORKSPACE.md` precedent). It
ships in the implementation phase, not this spec PR, so it never documents a
command the build lacks. The agent brings the hypotheses and writes the EA; this
playbook turns that into the quant role.

---

### The loop

1. **Frame the hypothesis.** State the edge in one or two sentences: what
   inefficiency, on which assets and timeframes, and why it should persist.
   Predeclare the asset universe *before* seeing results — choosing symbols
   after the fact manufactures a false out-of-sample. Keep the rule simple;
   complex rules curve-fit. You own this step; the tool never invents a strategy.
2. **Author and compile the EA.** Write the rule as an MQL5 Expert Advisor in
   `./ea/`, exposing the parameters to search as `input`s. Compile it:
   `mt5 --json ea compile <name>`. (Where files live: `USER_WORKSPACE.md`.)
3. **Plan the campaign.** Dry-run first to see the cost:
   `mt5 --json quant run --expert <name> --symbols ... --tf ... --from ... --to ... --split 0.70 --param ... --dry-run`.
4. **Run it.** Drop `--dry-run`. Defaults encode the discipline:
   `--min-trades 300 --min-pf 1.0 --rank-by full_net`.
5. **Read `quant.v1`.** Each `data.ranked[]` entry carries FULL / IS / OOS
   blocks and a `validated` flag. Rank only orders candidates — start at the top,
   then judge.
6. **Apply the judgment (this is the quant part):**
   - *Asset-drift trap.* A long-only winner on a trending asset posts a gorgeous
     OOS curve that is the asset, not the edge (canonical case: gold up
     ~150–200%). Make it actionable: fetch the asset's own move with
     `mt5 --json rates fetch <symbol> <tf> --bars <N>`, compute the buy-and-hold
     return from the first vs last close, and
     compare it to the strategy's return. If the edge disappears once you
     subtract the asset's drift, it is not an edge. (The campaign does not embed
     a benchmark — computing it from `rates` is your step, which keeps `quant`
     free of the MT5 SDK.)
   - *Multiple testing / data snooping.* A `symbols × timeframes × params` matrix
     plus genetic search creates many chances at a lucky survivor. Report how
     many cells and roughly how many parameter combinations you tried; do not
     treat the rank-1 survivor as validated just because it ranks first.
   - *Statistical weight.* Treat ~300 trades as a floor, not proof — trade
     clustering, correlated positions, a single market regime, and near-identical
     parameter variants all shrink the effective sample.
   - *IS↔OOS consistency.* Profit factor and Sharpe should not collapse from
     in-sample to out-of-sample. A `validated: true` entry whose OOS roughly
     tracks its IS beats a higher-ranked entry that only shines OOS.
   - *Overfitting.* Wide grids plus genetic search find lucky corners; fewer,
     economically meaningful parameters win.
7. **Stress the winner.** Test execution realism on the winner's actual set:
   `mt5 --json tester ea stress --expert <name> --symbol <sym> --tf <tf> --from ... --to ... --set-file <winner.set>`.
   Require `robustness.verdict` of `robust` (or at least `degraded`) — a backtest
   edge that evaporates under 100–500 ms fills was borrowed from execution
   conditions a retail account never gets.
8. **Iterate.** Refine the hypothesis or narrow the parameters and re-run. Keep a
   short log of what you tried and why each candidate lived or died, including
   whether the OOS window has been reused across iterations (reuse erodes its
   out-of-sample meaning).

### Honesty rules

- You author the alpha; the tool runs the native MT5 tester. Never ask the tool
  for a strategy, and never report a result the tester did not produce.
- A single-asset, single-broker result is not validated edge. Name the caveats
  an honest quant names: broker clock / session boundaries, spread and slippage,
  and cost sensitivity (an edge that survives 1× cost can die at 4×).
- Use `real-ticks` modelling for the final read; `ohlc-1m` is fine for the
  optimization sweep but understates execution cost.
- Out-of-sample numbers are a check, not a trophy. If you cannot explain *why*
  the edge exists, treat a great OOS curve as unexplained until proven.

### Pointers

- `mt5 --json describe` — machine catalog of every command and error code.
- `USER_WORKSPACE.md` — where EAs, presets, and results live.
- Full contract: this spec and the `quant.v1` envelope.

---

## Error Codes

Register in `mt5_cli/errors.py` (test-enforced):

- `EMPTY_MATRIX` — "A quant campaign needs at least one symbol and one timeframe."
- `INVALID_SPLIT` — "--split must be a 0<f<1 fraction or a YYYY-MM-DD date."
- `INVALID_PARAM` — "--param must be NAME=value or NAME=value,start,step,stop."
- `INVALID_RANK_BY` — "--rank-by must be one of full_net, oos_sharpe, oos_pf."

`NO_WINNER`, `MIN_TRADES`, and `CELL_FAILED` are per-cell **reject reasons**, not
root error codes (see [Reject reasons vs error codes](#reject-reasons-vs-error-codes)).

## Implementation risks (fixtures required before build)

The plan must close these against real MT5 artifacts before code is frozen:

1. **Optimization input columns.** `pick_winner` can only write the winner's
   `.set` if the optimization report exposes its input-parameter columns. Commit
   a real `optimization.xml` fixture proving the columns are present and map to
   `render_set` names. If they are not, v1 uses MT5's selected-pass `.set` export
   instead — decide in the plan, do not assume.
2. **Forward artifact shape.** Commit a `.forward` fixture and prove the
   back↔forward join key (pass id) and which passes are forward-tested. Define
   behavior when the winner has no forward row (→ the explicit OOS rerun
   fallback).
3. **IS/OOS metric availability.** Confirm which metrics (`profit_factor`,
   `sharpe`) the optimization/forward reports actually expose; the gate and the
   `oos_*` rank keys depend on them. Anything unavailable comes from an explicit
   rerun, not an assumed column.

## Acceptance Tests

Matrix (pure):

1. `EURUSD,XAUUSD × H1,H2` expands to 4 ordered cells; duplicates dedupe.
2. `--split 0.70` and `--split 2024-06-01` parse; `1.5`, `0`, `abc`, empty raise
   `INVALID_SPLIT`. A fraction converts to a calendar `ForwardDate`
   (`from + f×(to−from)`), and the built INI emits `ForwardMode=4` + that
   `ForwardDate` — never `ForwardMode=1` (which would force MT5's ½ split and
   ignore the date).
3. Empty symbol or timeframe set raises `EMPTY_MATRIX` on the library path.
4. `--param Risk=1.0,0.5,0.5,3.0` parses to the range form; a malformed range
   raises `INVALID_PARAM`. Bad `--rank-by` raises `INVALID_RANK_BY`.

Pass join (pure, fixtures — risk 1, 2, 3):

5. A back `optimization.xml` + `.forward` fixture join by pass id into records
   carrying both IS and OOS metric blocks.
6. The winner's input-parameter columns round-trip through `render_set` into a
   `.set` MT5 would accept.
7. A winner with no forward row triggers the explicit OOS-rerun fallback path
   (asserted via the fake launcher: one extra `single()` over `split..to`).

Selection (pure):

8. `pick_winner` ignores passes failing the in-sample `min_pf` and returns the
   best remaining by `rank_by`; no qualifying pass → the cell is rejected
   `NO_WINNER`.
9. FULL trades < `min_trades` → reject `MIN_TRADES`.
10. `validated` is true only when OOS PF ≥ `oos_min_pf`, and a `validated: false`
    survivor still ranks (validated is not a gate).
11. Default `rank_by` is `full_net` and `rank_caveat` is null; selecting an
    `oos_*` key sets `rank_caveat`. Ranking respects `--per-asset`.

Orchestration (fake launcher, no terminal):

12. Common path issues exactly two native launches per cell (optimize, FULL
    single); the fallback adds exactly one.
13. A cell whose optimize or re-run fails ships `reason: "CELL_FAILED"` with the
    embedded fail envelope and does not stop later cells.
14. Empty matrix → root `EMPTY_MATRIX`, zero launches. No cell yielding any
    ranked or rejected record → root failure.
15. Child run ids are unique and registered under `results/`; the campaign
    `manifest.json` lists them and `get_campaign(id)` reloads it.
16. `--dry-run` returns the plan (matrix, cells, launch estimate) and zero
    launches.

Report + boundaries (pure):

17. `report.render` produces self-contained HTML — no external `src`/`href` to a
    CDN, an inline-SVG `<polyline>` per equity curve, a link to each child
    `report.html` — and imports/render-runs with no matplotlib/pandas present.
18. Import-boundary test: nothing under `mt5_cli/quant` imports `MetaTrader5`
    (mirrors the tester rule).

Stress extension:

19. `single(set_file=...)` already stages the set; `stress(set_file=...)` and
    `tester ea stress --set-file` thread it into every rung, asserted via the
    written INI's `ExpertParameters` line.

CLI + playbook:

20. `quant run` happy path emits `quant.v1`; `quant list` / `show` read back a
    written campaign; new error codes are registered.
21. `mt5_cli/skills/QUANT_WORKFLOW.md` ships in the built wheel as package data.
22. Anti-drift guard: a test extracts each `mt5 ...` example from the playbook,
    **normalizes it** (strip the `mt5` binary, the global `--json`, placeholders
    like `<name>`, `...`, and option values), and asserts both the command path
    **and every `--option`** resolve in the `describe` catalog
    (`describe.commands[].command` and its option list). The playbook can never
    drift ahead of the implemented CLI — including referencing an option a
    command does not have (e.g. `rates fetch --from`).

## Verification

Before merge: `ruff check .`, `pytest -m "not integration"`,
`mypy mt5_cli mt5 mt5_mcp`, `git diff --check`.

Live check (manual, optional, needs a closed terminal and a compiled demo EA):
run a 2-symbol × 1-timeframe campaign with a tiny param range; confirm the child
run dirs per cell, a `manifest.json`, a `report.html` whose ranked table matches
the child runs' parsed stats, and that `tester ea stress --set-file <winner.set>`
writes that set into each rung's INI.
