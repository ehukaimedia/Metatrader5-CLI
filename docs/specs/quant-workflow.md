# Quant Workflow Spec

Status: Implemented — PR #10 (under review)
Date: 2026-06-16
Owner: metatrader5-cli maintainers
Related playground: [Quant Workflow](../playgrounds/specs/quant-workflow.html)
Related plan: [Quant Workflow Implementation Plan](../plans/quant-workflow-plan.md)

> Implementation note: shipped v1 is explicit two-pass (the chosen default).
> **Task 0 is closed** — dog-fooding a live optimization confirmed MT5 writes a
> SpreadsheetML report (`Workbook/Worksheet/Table/Row/Cell`), so
> `results.parse_optimization_xml` parses that shape (via `defusedxml`) and
> `passes.py` reads the real column headers `Profit Factor`, `Sharpe Ratio`,
> `Trades`, `Profit`. `tests/fixtures/sample_optimization.xml` is a trimmed real
> capture; the parsed-passes path was validated live (0 → 20 passes).

## Purpose

`mt5 quant` turns the research pipeline from the "AI quant workflow" into one
tool-true command. `quant run` drives the **native** MT5 Strategy Tester across
a symbol × timeframe matrix: genetic optimization on an in-sample window,
out-of-sample validation, configurable selection gates, a ranking metric, and a
consolidated `quant.v1` envelope plus a dependency-free HTML report.

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
[Quant agent playbook](#quant-agent-playbook). The agent supplies the
hypotheses and authors the EA (its own native capabilities); the playbook wires
that reasoning to the commands and carries the judgment the video earns the hard
way — the asset-drift trap, trade-count sufficiency, multiple-testing
discipline, and execution stress. The tool stays hands; the agent is the brain.

## Validation mechanism: explicit two-pass (v1)

v1 splits each cell into a flat, explicit sequence — **no MT5 forward mode, no
`.forward` artifact, no back↔forward join**:

1. **Optimize the in-sample window** `[from, split−1 day]` (genetic) →
   `optimization.xml` (one row per pass, with that pass's input parameters and
   in-sample metrics).
2. **Pick the winner** from the in-sample passes (below).
3. **`single` on the out-of-sample window** `[split, to]` with the winner's set → OOS metrics.
4. **`single` on the FULL window** `[from, to]` with the winner's set → FULL metrics + the
   continuous equity curve crossing the split.

**Split boundary (no leakage):** `split` is the first out-of-sample day. A
fraction `f` resolves to `split = from + floor(f×(to−from))` days. Because MT5
treats `FromDate`/`ToDate` inclusively, the in-sample optimize runs
`[from, split−1 day]` and the OOS `single` runs `[split, to]` — disjoint, no
boundary double-count.

**Three native launches per cell, flat.** This was chosen over the
forward-optimization "hybrid" (2 launches) on review: MT5's forward mode writes
a *separate* `.forward` report, forward-tests only the *selected* passes, and
needs a back↔forward join — and `build_ea_ini()` today emits the wrong
`ForwardMode` for a custom split (see [Deferred: hybrid](#deferred-hybrid-forward-path)).
Two-pass removes all of that from v1; the hybrid returns later, behind fixtures,
purely as a launch-count optimization.

### Winner selection vs cell ranking (these are different operations)

The review caught a circularity: you cannot select the winning optimization pass
by `full_net`, because `full_net` does not exist until the FULL re-run. So the
two concepts are split:

- **Winner selection** (step 2, in-sample, pre-FULL): among passes whose
  in-sample `profit_factor` clears `--min-pf` **and** whose in-sample trade count
  clears `--min-is-trades` (default `--min-trades`), `pick_winner` takes the best
  by an **in-sample** selector — default in-sample `profit_factor`. The in-sample
  trade floor stops a sparse, overfit pass from being crowned; and because the
  FULL window contains the in-sample window, a floor equal to `--min-trades` also
  keeps the winner from later tripping the FULL `MIN_TRADES` gate. (A configurable
  `--winner-by` is deliberately deferred; YAGNI.)
- **Cell ranking** (after all cells assemble, post-FULL): `--rank-by` orders the
  finished cells by a metric that now exists — default `full_net`; `oos_sharpe`
  / `oos_pf` are opt-in and set `rank_caveat`.

## Source Anchors

- Orchestration template: `mt5_cli/tester/ea.py:304` — `stress()` runs many
  `single()` passes serially (the launcher forbids parallel terminals),
  aggregates per-scenario envelopes, attaches a graded block.
- Per-cell primitives: `mt5_cli/tester/ea.py:152` (`optimize()`, used here on the
  in-sample window — v1 passes **no** `forward`); `mt5_cli/tester/ea.py:45`
  (`single()`, used for OOS and FULL), whose `set_file` parameter (`ea.py:59`) is
  staged at `ea.py:92`.
- `.set` rendering already exists: `mt5_cli/tester/ini_builder.py:181-212`
  (`render_set` / `write_set`), including the `value||start||step||stop||Y`
  optimization-range form.
- Genetic mode code: `mt5_cli/tester/ea.py:18` — `_OPT_MODES["genetic"] = 2`.
- Multi-symbol precedent (raw): `mt5_cli/tester/ea.py:273` (`scanner()`).
- Stress today has no `set_file`: CLI `tester_ea_stress` (`mt5/cli.py:1526`)
  exposes no `--set-file`, and `ea.stress()` calls `single()` without one — this
  feature adds it.
- Forward INI emission (relevant only to the deferred hybrid):
  `mt5_cli/tester/ini_builder.py:107-109` emits `ForwardMode=1` + `ForwardDate`,
  but MT5 honors `ForwardDate` only under `ForwardMode=4` — a latent bug the
  hybrid must fix; v1 two-pass never sets a forward mode.
- `rates fetch` shape (for the playbook's asset-drift step): `mt5/cli.py:569-574`
  — accepts `symbol`, `timeframe`, `--bars` only (no `--from`/`--to`; those are
  on `history`).
- Pure-module precedent for scoring: `mt5_cli/tester/stress.py`.
- Stats source: `mt5_cli/tester/results.py:184-256` — `parse_html_report()`
  yields `net_profit`, `profit_factor`, `max_drawdown_pct`, `total_trades`,
  `win_rate`, `sharpe`, `expectancy`, `equity_curve`. Optimization passes:
  `results.py:285` (`parse_optimization_xml`, parses MT5 SpreadsheetML via
  `defusedxml` — confirmed by dog-fooding).
- Bridge isolation: `mt5_cli/tester/__init__.py:15-17` — the tester package must
  not import MetaTrader5; `quant` inherits this (import-boundary test).
- Run cache: `mt5_cli/tester/cache.py:17-63`.
- Envelope contract: `mt5_cli/reports/envelope.py`. Error registry:
  `mt5_cli/errors.py` (test-enforced). CLI: `mt5/cli.py` (`pyproject.toml:69`).
- Lean-deps charter: `pyproject.toml:38-48` (no pandas/numpy). Agent-doc
  precedent: `mt5_cli/skills/USER_WORKSPACE.md`, packaged via
  `pyproject.toml:107-111`.

## Durable Wedge

Six-month thesis: multi-asset optimization with an in/out-of-sample split is
native MT5 — the platform owns the simulation. This repo owns what the platform
does not ship: matrix orchestration across cells, a deterministic
selection/ranking contract, and a machine-readable ranked envelope an agent
gates on without reading eight HTML reports. Better agents make a deterministic
campaign more valuable, not less.

## Goals

- Expand a `symbols × timeframes` matrix and drive each cell through the explicit
  two-pass validation (optimize IS → pick winner → `single` OOS → `single` FULL).
- Separate winner selection (in-sample selector) from cell ranking (`--rank-by`).
- Apply deterministic gates (min in-sample PF and trades at selection, min FULL
  trades after) and a ranking metric; record rejects with reasons; mark survivors
  `validated` against an OOS PF floor without letting OOS be the default rank key.
- Return one `quant.v1` envelope, a dependency-free HTML report, and a re-loadable
  `manifest.json`; keep child runs cached under `results/`.
- Add `set_file` support to `tester ea stress` so the playbook can stress the
  winning set.
- Ship the quant agent playbook (`mt5_cli/skills/QUANT_WORKFLOW.md`).

## Non-Goals

- **The forward-optimization hybrid is deferred** (see below) — not v1.
- **Portfolio / cross-strategy correlation selection is deferred** (see below) —
  v1 ranks each strategy standalone, not by marginal contribution to a book.
- No Python EDA engine; no Python backtester; no Python→MQL5 translation. MT5 is
  the only engine; the EA is the only alpha.
- No campaign-internal benchmark. The asset-drift check is an agent step using
  `rates` (playbook); importing the rates module into `quant` would pull in the
  MT5 SDK and break bridge isolation.
- No walk-forward beyond the single split; no multi-data-feed/news testing; no
  campaign resume in v1.
- No MCP exposure for `quant run` (long-running, launches a terminal);
  `quant list` / `show` are read-only and MCP-safe.
- No trading strategy, signal generation, indicator math, or market opinion.

## Architecture

A new package `mt5_cli/quant/`, same layering as the tester stack. **Bridge
isolation:** like `mt5_cli/tester`, `quant` must not import MetaTrader5 — it
drives the tester through the filesystem only (import-boundary test).

1. `matrix.py` — pure: expand/validate `symbols × timeframes`; parse `--split`
   into the IS/OOS boundary date — a `0<f<1` fraction becomes
   `from + floor(f×(to−from))` days (stdlib date math), an explicit `YYYY-MM-DD`
   is used as-is; `split` is the first OOS day, so the IS optimize ends
   `split−1`; parse
   `--param NAME=value,start,step,stop` ranges (reusing `ini_builder.render_set`
   grammar). Rejects via one shared gate: `EMPTY_MATRIX`, `INVALID_SPLIT`,
   `INVALID_PARAM`.
2. `passes.py` — pure: read the in-sample `optimization.xml` into one record per
   pass carrying its **input parameters** and **in-sample metrics** (via
   `results.parse_optimization_xml`, which parses MT5's SpreadsheetML report).
   No forward join in v1.
3. `selection.py` — pure: `pick_winner(passes, *, min_pf, min_is_trades)` returns
   the in-sample pass clearing `min_pf` and the in-sample trade floor, with the
   best in-sample selector (default IS `profit_factor`); `gate_and_rank(cells,
   selection)` applies the FULL-trades gate, ranks by `--rank-by`, caps per asset,
   records rejects.
4. `report.py` — pure: render HTML from assembled cells — ranked table,
   per-strategy IS/OOS/FULL card, inline-SVG equity curve with the split marker,
   links to each child `report.html`. No matplotlib, no pandas.
5. `campaign.py` — orchestration: expand the matrix, run each cell's two-pass
   sequence serially, assemble cells, call `selection`, write artifacts, return
   `quant.v1`.
6. `store.py` — `make_campaign_id()`, `manifest.json` read/write,
   `list_campaigns()` / `get_campaign(id)` (reuses `tester/cache.py`).
7. `mt5/cli.py` — a new `quant` click group (`run`, `list`, `show`); adds
   `--set-file` to `tester ea stress`. No business logic.
8. `mt5_cli/skills/QUANT_WORKFLOW.md` — the static agent playbook, shipped with
   the package, drafted in [Quant agent playbook](#quant-agent-playbook). Ships
   in the same phase as the `quant` CLI so it never references a missing command.

Cross-cutting: `stress()` and CLI `tester ea stress` gain an optional `set_file`
/ `--set-file` threaded into the `single()` calls they already make. (The
`ForwardMode=4` fix is **not** v1 — it belongs to the deferred hybrid.)

### Per-cell two-pass flow

For each `(symbol, timeframe)` cell, serially (launcher forbids parallel
terminals):

1. `ea.optimize(mode="genetic", params=…, from=FROM, to=SPLIT−1d)` → in-sample
   `optimization.xml`. **launch 1.**
2. `passes.read()` + `selection.pick_winner(passes, min_pf=…, min_is_trades=…)` →
   the winning parameter set → `.set`. (pure)
3. `ea.single(set_file=winner.set, from=SPLIT, to=TO)` → OOS metrics. **launch 2.**
4. `ea.single(set_file=winner.set, from=FROM, to=TO)` → FULL metrics + continuous
   equity. **launch 3.**
5. Assemble: IS from the winner's optimization row, OOS from launch 2, FULL from
   launch 3; equity split at `SPLIT`. (pure)

### Selection & ranking contract

- **Winner selector** (step 2): among in-sample passes with `profit_factor` ≥
  `--min-pf` (default 1.0) **and** in-sample trades ≥ `--min-is-trades` (default
  `--min-trades`), the best by in-sample `profit_factor`. No qualifying pass → the
  cell is rejected `NO_WINNER`. The in-sample trade floor stops a sparse, overfit
  pass winning; defaulting it to `--min-trades` means the winner already clears
  the FULL-trades gate (FULL ⊇ IS), so `MIN_TRADES` only fires if the two floors
  are deliberately decoupled.
- **FULL-trades gate:** winner's FULL `total_trades` ≥ `--min-trades` (default
  300), else reject `MIN_TRADES`.
- **`validated` flag:** OOS `profit_factor` ≥ `--oos-min-pf` (default 1.0). Not a
  gate, not the rank key — a `validated: false` survivor still ranks.
- **`--rank-by`** (over assembled cells): default `full_net`; `oos_sharpe` /
  `oos_pf` are opt-in and set `rank_caveat`. Ranking orders candidates; it never
  certifies edge — the `validated` flag and the agent's asset-drift check do.
- **`--per-asset`** (default 2, clamped to ≥ 1): keep the top N per asset.
  Survivors beyond the cap are surfaced in `data.capped` (they passed the gates,
  just trimmed) rather than dropped. When every cell is `NO_WINNER`, `data.hint`
  flags the likely cause (a too-strict `--min-pf` / `--min-is-trades`, or the EA's
  passes don't clear them).

### Reject reasons vs error codes

- **Per-cell reject reasons** (entries in `rejected[]`, campaign continues):
  `NO_WINNER` (no in-sample pass cleared the PF + in-sample-trades gates),
  `MIN_TRADES` (winner's FULL trades below floor), `CELL_FAILED` (a native launch
  failed; fail envelope embedded).
- **Root command errors** (`ok:false`, frozen `{ok,error}` shape): input
  validation only — `EMPTY_MATRIX`, `INVALID_SPLIT`, `INVALID_PARAM`,
  `INVALID_RANK_BY` — plus the degenerate "no cell yielded any record" case.

### Envelope: `quant.v1`

Every `ranked[]` entry carries `full`, `is`, and `oos` blocks.

```json
{
  "ok": true,
  "data": {
    "schema": "quant.v1",
    "campaign_id": "2026-06-16T19-40-00_quant_alpha",
    "expert": "alpha",
    "matrix": { "symbols": ["EURUSD", "XAUUSD"], "timeframes": ["H1"] },
    "from": "2022-01-01", "to": "2024-12-31",
    "split": "2024-02-06",
    "selection": { "min_trades": 300, "min_pf": 1.0, "min_is_trades": 300,
                   "oos_min_pf": 1.0, "rank_by": "full_net", "per_asset": 2 },
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
  [--min-trades 300] [--min-pf 1.0] [--min-is-trades <n>] [--oos-min-pf 1.0] \
  [--rank-by full_net|oos_sharpe|oos_pf] [--per-asset 2] \
  [--modelling ohlc-1m] [--no-html] [--dry-run] [--timeout 1800]

mt5 quant list
mt5 quant show <campaign-id>

mt5 tester ea stress --expert <EA> --symbol <SYM> --tf <TF> \
  --from ... --to ... [--set-file results/<child>/<winner>.set] \
  [--delays 0,100,500,random]
```

- Exit code stays 0; callers parse the envelope's `ok` boolean.
- `--split` is the IS/OOS boundary date (a fraction is converted against
  `from`/`to`); `split` is the first OOS day, so the in-sample optimize runs
  `[from, split−1]` and the OOS `single` runs `[split, to]` (disjoint).
- `--dry-run` returns the expanded matrix, cell count, and launch estimate (3 per
  cell), and launches nothing.
- `--timeout` is per native launch. `--modelling` defaults to `ohlc-1m` for the
  optimization pass; the OOS/FULL re-runs inherit `single()`'s `real-ticks`
  default unless overridden.

## Quant agent playbook

Full draft of `mt5_cli/skills/QUANT_WORKFLOW.md` — static markdown shipped with
the tool for any AI agent to introspect (the `USER_WORKSPACE.md` precedent). It
ships in the implementation phase, not this spec PR, so it never documents a
command the build lacks.

---

### The loop

1. **Frame the hypothesis.** State the edge in one or two sentences: what
   inefficiency, on which assets and timeframes, why it should persist.
   Predeclare the asset universe *before* seeing results — choosing symbols after
   the fact manufactures a false out-of-sample. Keep the rule simple. You own
   this step; the tool never invents a strategy.
2. **Author and compile the EA.** Write the rule as an MQL5 Expert Advisor in
   `./ea/`, exposing the parameters to search as `input`s. Compile it:
   `mt5 --json ea compile <name>`. (Where files live: `USER_WORKSPACE.md`.)
3. **Plan the campaign.** Dry-run first to see the cost:
   `mt5 --json quant run --expert <name> --symbols ... --tf ... --from ... --to ... --split 0.70 --param ... --dry-run`.
4. **Run it.** Drop `--dry-run`. Defaults encode the discipline:
   `--min-trades 300 --min-pf 1.0 --rank-by full_net`.
5. **Read `quant.v1`.** Each `data.ranked[]` entry carries FULL / IS / OOS blocks
   and a `validated` flag. Rank only orders candidates — start at the top, then
   judge.
6. **Apply the judgment (this is the quant part):**
   - *Asset-drift trap.* A long-only winner on a trending asset posts a gorgeous
     OOS curve that is the asset, not the edge (canonical case: gold up
     ~150–200%). Make it actionable: fetch the asset's own move with
     `mt5 --json rates fetch <symbol> <tf> --bars <N>`, compute the buy-and-hold
     return from the first vs last close, and compare it to the strategy's
     return. If the edge disappears once you subtract the asset's drift, it is not
     an edge. (The campaign does not embed a benchmark — computing it from `rates`
     is your step, which keeps `quant` free of the MT5 SDK.)
   - *Multiple testing / data snooping.* A `symbols × timeframes × params` matrix
     plus genetic search creates many chances at a lucky survivor. Report how many
     cells and roughly how many parameter combinations you tried; do not treat the
     rank-1 survivor as validated just because it ranks first.
   - *Statistical weight.* Treat ~300 trades as a floor, not proof — clustering, a
     single regime, and near-identical parameter variants shrink the effective
     sample.
   - *IS↔OOS consistency.* Profit factor and Sharpe should not collapse from
     in-sample to out-of-sample. A `validated: true` entry whose OOS roughly
     tracks its IS beats a higher-ranked entry that only shines OOS.
   - *Overfitting.* Wide grids plus genetic search find lucky corners; fewer,
     economically meaningful parameters win.
   - *Correlation to your book.* If you already run strategies, a high-Sharpe
     candidate that duplicates one you hold adds little — judge by marginal
     contribution and prefer low-correlation additions ("frozen alpha"), not the
     standalone rank alone.
7. **Stress the winner.** Test execution realism on the winner's actual set:
   `mt5 --json tester ea stress --expert <name> --symbol <sym> --tf <tf> --from ... --to ... --set-file <winner.set>`.
   Require `robustness.verdict` of `robust` (or at least `degraded`).
8. **Iterate.** Refine the hypothesis or narrow the parameters and re-run. Log
   what you tried and why each candidate lived or died, including whether the OOS
   window has been reused across iterations (reuse erodes its meaning).

### Honesty rules

- You author the alpha; the tool runs the native MT5 tester. Never ask the tool
  for a strategy, and never report a result the tester did not produce.
- A single-asset, single-broker result is not validated edge. Name the caveats:
  broker clock / session boundaries, spread and slippage, and cost sensitivity
  (an edge that survives 1× cost can die at 4×).
- Use `real-ticks` modelling for the final read; `ohlc-1m` understates execution
  cost.
- Out-of-sample numbers are a check, not a trophy. If you cannot explain *why* the
  edge exists, treat a great OOS curve as unexplained until proven.

### Pointers

- `mt5 --json describe` — machine catalog of every command and error code.
- `USER_WORKSPACE.md` — where EAs, presets, and results live.
- Full contract: this spec and the `quant.v1` envelope.

---

## Deferred: hybrid forward path

A later enhancement, **not v1**, kept here so the decision is recorded. MT5's
forward optimization could collapse the two-pass three launches into two: one
`optimize(forward=split)` does in-sample optimization *and* forward-tests the
selected passes in a single launch, then only the FULL re-run remains. It is
deferred because it is materially more complex and rests on unproven artifact
shapes:

- MT5 writes forward results to a **separate** report with a `.forward` suffix
  and forward-tests **only the selected** passes — so `passes.py` would need a
  back↔forward join by pass id and a rule for winners with no forward row.
- `build_ea_ini()` must emit `ForwardMode=4` + a computed `ForwardDate` (today it
  emits `ForwardMode=1`, which forces MT5's ½ split and ignores the date).
- `ForwardMode` is `1` (last ½), `2` (last ⅓), `3` (last ¼), `4` (custom date).

Promote the hybrid only once the `.forward` shape, join key, partial-coverage
behavior, and `ForwardMode=4` emission are proven by committed fixtures.

## Deferred: portfolio / marginal-alpha selection

A later, separate feature — **not v1**, recorded so the idea is not lost
(source: "Leverage Points: The Real Edge in Quant Trading"). Once a trader runs a
*library* of validated strategies, the highest-leverage move is not another
standalone backtest but choosing which strategies to run *together*:

- Compute a cross-strategy **correlation matrix** (Pearson/Spearman) over the
  per-run trade-return series the tester already emits.
- Rank candidates by their **marginal Sharpe contribution** to an existing live
  book given that correlation — a strategy that is strong *and* low-correlation
  to what you already run ("frozen alpha") improves the book with no new logic.
- Emit a before/after portfolio comparison and a ranked selection log.

This is **heavy-numeric** (correlation, covariance, bootstrap) — the same
territory as the excluded EDA engine — so it ships behind the optional `[quant]`
extra or stays an agent-side computation over `quant.v1` outputs, never in the
tool-only core. `quant.v1` is the upstream that produces its inputs (validated
standalone strategies); this is the downstream that assembles them into a book.

## Error Codes

Register in `mt5_cli/errors.py` (test-enforced):

- `EMPTY_MATRIX` — "A quant campaign needs at least one symbol and one timeframe."
- `INVALID_SPLIT` — "--split must be a 0<f<1 fraction or a YYYY-MM-DD date."
- `INVALID_PARAM` — "--param must be NAME=value or NAME=value,start,step,stop."
- `INVALID_RANK_BY` — "--rank-by must be one of full_net, oos_sharpe, oos_pf."
- `NO_RESULTS` — "No cell produced a ranked or rejected record." (the degenerate
  case named in *Reject reasons vs error codes*).

`NO_WINNER`, `MIN_TRADES`, `CELL_FAILED` are per-cell **reject reasons**, not root
error codes.

## Implementation risks (status)

1. **Optimization report shape — CLOSED (dog-fooded).** A live optimization
   confirmed MT5 writes a **SpreadsheetML** report whose columns include
   `Profit Factor`, `Sharpe Ratio`, `Trades`, `Profit`, and the EA input
   parameters. `results.parse_optimization_xml` parses that shape (via
   `defusedxml`) and `pick_winner` reconstructs the winner `.set` from the
   parameter columns. `tests/fixtures/sample_optimization.xml` is a trimmed real
   capture, and the parsed-passes path was validated live (0 → 20 passes).
   In-sample `profit_factor` is present, so the IS-`single` fallback is not needed.
2. **Deferred-hybrid artifacts.** The `.forward` shape, back↔forward join key, and
   partial-forward coverage remain unverified — they gate the deferred hybrid
   only, not v1.

## Acceptance Tests

Matrix (pure):

1. `EURUSD,XAUUSD × H1,H2` expands to 4 ordered cells; duplicates dedupe.
2. `--split 0.70` over `2022-01-01..2024-12-31` (1095 days) converts to
   `split = from + floor(0.70×1095) = +766d = 2024-02-06` (the first OOS day; the
   IS optimize ends 2024-02-05); `--split 2024-06-01` is used as-is; `1.5`, `0`,
   `abc`, empty raise `INVALID_SPLIT`.
3. Empty symbol or timeframe set raises `EMPTY_MATRIX` on the library path.
4. `--param Risk=1.0,0.5,0.5,3.0` parses to the range form; malformed raises
   `INVALID_PARAM`. Bad `--rank-by` raises `INVALID_RANK_BY`.

Passes + selection (pure, fixtures — risk 1):

5. `passes.read()` yields one record per pass with input parameters and in-sample
   metrics; the winner's parameters round-trip through `render_set` into a `.set`
   MT5 would accept.
6. `pick_winner` ignores passes failing in-sample `min_pf` or the in-sample trade
   floor (`min_is_trades`, default `min_trades`) and returns the best remaining by
   **in-sample** `profit_factor`; no qualifying pass → `NO_WINNER`. It does **not**
   consult `full_net` (which does not exist at selection time).
7. `gate_and_rank`: FULL trades < `min_trades` → `MIN_TRADES`; default `rank_by`
   is `full_net` with `rank_caveat` null; an `oos_*` key sets `rank_caveat`;
   `--per-asset` caps; `validated` follows OOS PF and a `validated: false`
   survivor still ranks.

Orchestration (fake launcher, no terminal):

8. Each cell issues exactly three launches in order — optimize `[from, split−1]`,
   single `[split, to]`, single `[from, to]` — disjoint IS/OOS with no boundary
   overlap, and assembles IS/OOS/FULL.
9. A cell whose any launch fails ships `reason: "CELL_FAILED"` with the embedded
   fail envelope and does not stop later cells.
10. Empty matrix → root `EMPTY_MATRIX`, zero launches; no cell yielding any record
    → root failure.
11. Child run ids are unique and registered under `results/`; `manifest.json`
    lists them and `get_campaign(id)` reloads it.
12. `--dry-run` returns the plan and zero launches.

Report + boundaries (pure):

13. `report.render` produces self-contained HTML — no external `src`/`href`, an
    inline-SVG `<polyline>` per equity curve, a link to each child `report.html`
    — and imports/render-runs with no matplotlib/pandas present.
14. Import-boundary test: nothing under `mt5_cli/quant` imports `MetaTrader5`.

Stress extension:

15. `stress(set_file=...)` and `tester ea stress --set-file` thread the set into
    every rung, asserted via the written INI's `ExpertParameters` line.

CLI + playbook:

16. `quant run` happy path emits `quant.v1`; `quant list` / `show` read back a
    written campaign; new error codes are registered.
17. `mt5_cli/skills/QUANT_WORKFLOW.md` ships in the built wheel as package data.
18. Anti-drift guard: a test extracts each `mt5 ...` example from the playbook,
    **normalizes it** (strip the `mt5` binary, the global `--json`, placeholders
    like `<name>`, `...`, and option values), and asserts both the command path
    **and every `--option`** resolve in the `describe` catalog
    (`describe.commands[].command` and its option list) — so a stale option like
    `rates fetch --from` fails, not just a stale command.

## Verification

Before merge: `ruff check .`, `pytest -m "not integration"`,
`mypy mt5_cli mt5 mt5_mcp`, `git diff --check`.

Live check (manual, optional, needs a closed terminal and a compiled demo EA):
run a 2-symbol × 1-timeframe campaign with a tiny param range; confirm three
child runs per cell (IS optimize, OOS single, FULL single), a `manifest.json`, a
`report.html` whose ranked table matches the child runs' parsed stats, and that
`tester ea stress --set-file <winner.set>` writes that set into each rung's INI.
