# Operating as a quant with `metatrader5-cli`

Static guidance shipped with the tool so any AI agent can introspect it. The
commands are hands; this loop is the role. **You** bring the hypotheses and
author the EA — the tool never invents a strategy and never holds the alpha.

## The loop

1. **Frame the hypothesis.** State the edge in one or two sentences: what
   inefficiency, on which assets and timeframes, and why it should persist.
   Predeclare the asset universe *before* seeing results — choosing symbols after
   the fact manufactures a false out-of-sample. Keep the rule simple; complex
   rules curve-fit.
2. **Author and compile the EA.** Write the rule as an MQL5 Expert Advisor in
   `./ea/`, exposing the parameters to search as `input`s, then compile it:
   `mt5 --json ea compile <name>`. (Where files live: `USER_WORKSPACE.md`.)
3. **Plan the campaign.** Dry-run first to see the launch cost:
   `mt5 --json quant run --expert <name> --symbols <list> --tf <list> --from <date> --to <date> --split 0.70 --param <range> --dry-run`.
4. **Run it.** Drop `--dry-run`. The defaults encode the discipline:
   `--min-trades 300`, `--min-pf 1.0`, `--rank-by full_net`, and
   `--min-is-trades` (the in-sample trade floor for winner selection, defaulting
   to `--min-trades`) so a sparse, overfit pass can't be crowned. Rank only
   *orders* candidates — it never certifies edge.
5. **Read `quant.v1`.** Each `data.ranked[]` entry carries FULL / IS / OOS blocks
   and a `validated` flag. Start at the top, then judge.
6. **Apply the judgment (this is the quant part):**
   - **Asset-drift trap.** A long-only winner on a trending asset posts a gorgeous
     OOS curve that is the asset, not the edge (canonical case: gold up
     ~150–200%). Make it actionable: fetch the asset's own move with
     `mt5 --json rates fetch <symbol> <tf> --bars <N>`, compute the buy-and-hold
     return from the first vs last close, and compare it to the strategy's return.
     If the edge disappears once you subtract the drift, it is not an edge.
   - **Multiple testing.** A symbols × timeframes × params matrix plus genetic
     search invites a lucky survivor. Report how many cells and roughly how many
     parameter combinations you tried; do not treat the rank-1 survivor as
     validated just because it ranks first.
   - **Statistical weight.** Treat ~300 trades as a floor, not proof — clustering,
     a single regime, and near-identical parameter variants shrink the effective
     sample.
   - **IS↔OOS consistency.** Profit factor and Sharpe should not collapse from
     in-sample to out-of-sample. A `validated: true` entry whose OOS roughly
     tracks its IS beats a higher-ranked entry that only shines OOS.
   - **Correlation to your book.** If you already run strategies, a high-Sharpe
     candidate that duplicates one you hold adds little — prefer low-correlation
     additions ("frozen alpha"), not the standalone rank alone.
   - **Overfitting.** Wide grids plus genetic search find lucky corners; fewer,
     economically meaningful parameters win.
7. **Stress the winner.** Test execution realism on the winner's actual set:
   `mt5 --json tester ea stress --expert <name> --symbol <sym> --tf <tf> --from <date> --to <date> --set-file <winner.set>`.
   Require `robustness.verdict` of `robust` (or at least `degraded`) — a backtest
   edge that evaporates under 100–500 ms fills was borrowed from execution
   conditions a retail account never gets.
8. **Iterate.** Refine the hypothesis or narrow the parameters and re-run. Log
   what you tried and why each candidate lived or died, including whether the OOS
   window has been reused across iterations (reuse erodes its meaning).

## Honesty rules

- You author the alpha; the tool runs the native MT5 tester. Never ask the tool
  for a strategy, and never report a result the tester did not produce.
- A single-asset, single-broker result is not validated edge. Name the caveats an
  honest quant names: broker clock / session boundaries, spread and slippage, and
  cost sensitivity (an edge that survives 1× cost can die at 4×).
- Use `real-ticks` modelling for the final read; `ohlc-1m` understates execution
  cost (it is fine for the optimization sweep).
- Out-of-sample numbers are a check, not a trophy. If you cannot explain *why* the
  edge exists, treat a great OOS curve as unexplained until proven.

## Pointers

- `mt5 --json describe` — machine catalog of every command and error code.
- `USER_WORKSPACE.md` — where EAs, presets, and results live.
