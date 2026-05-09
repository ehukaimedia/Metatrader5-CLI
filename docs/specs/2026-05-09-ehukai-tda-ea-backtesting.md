# Ehukai / Photon SMC MT5 EA Backtesting Spec

Date: 2026-05-09
Status: Milestone 1 implementation spec

## Goal

Create a MetaTrader 5 Expert Advisor that can backtest the Ehukai / Photon SMC strategy inside MT5 Strategy Tester across the current 11 FX pairs:

`USDJPY, EURUSD, GBPUSD, AUDUSD, USDCAD, NZDUSD, USDCHF, EURJPY, GBPJPY, AUDJPY, EURGBP`

The first objective is reliable Strategy Tester execution and truthful metrics. Live trading optimization is explicitly out of scope for this milestone.

## Source Of Truth

The EA must mirror the current TDA contract instead of reading chart objects:

- Python contract: `metatrader5_cli/mt5/core/analyze.py::sniper_poc`
- Structured mirrors: `metatrader5_cli/mt5/core/ehukai.py`
- Visual reference: `metatrader5_cli/mt5/mql5/Indicators/EhukaiTDAOverlay.mq5`
- Archival manager reference only: `metatrader5_cli/mt5/mql5/Experts/AdaptiveTrailEA.mq5`

The chart overlay stays visual. The EA owns its own deterministic MQL5 setup planner for tester parity.

The EA must be Strategy-Tester-runnable standalone:

- No dependency on `EhukaiTDAOverlay` chart objects.
- No `iCustom()` calls into the overlay or primitive indicators.
- Internal recomputation uses `CopyRates`, `SymbolInfo*`, and native indicator handles only.
- Reserved future debug object prefix: `EHKEA_`. The EA must never draw with `ETDA_`, because the overlay owns and cleans that prefix.

## Strategy Contract

Each evaluated setup has:

- `status`: `NO_TRADE`, `WATCH`, or `READY`
- `direction`: `BUY`, `SELL`, or none
- D1/H4 directional permission
- M15 setup POI context
- M5/M1 entry structure context
- FVG candidate, state, midpoint entry, age, and distance
- Liquidity sweep/trap context
- VP/POC confluence score and block flags
- SL, TP, risk, expected reward, and RR
- Gates with pass/fail reason

READY requires:

- D1/H4 directional majority or configured relaxed majority
- Fresh aligned FVG entry candidate within age/distance limits
- Recent opposing liquidity sweep using wick-through plus close-back semantics
- M1/M5 CHoCH, BOS, or iBOS closes in the setup direction after the sweep
- No deeper unswept liquidity pool within the configured ATR multiple on the trade side
- No behind-zone trap blocker
- VP/POC does not hard-block the side when VP hard gate is enabled
- Spread, minimum stop, and minimum RR pass

FVG-only entries are not allowed in v1. A clean FVG can define the POI and entry refinement, but it cannot replace the liquidity sweep.

## Risk Model

Backtesting defaults are demo-first:

- Fixed fractional risk by default: `InpRiskPercent = 0.25`
- Optional fixed lots override
- Per-trade risk is based on entry-to-SL distance and symbol tick value
- Minimum and maximum lot are clamped to symbol volume constraints
- One open/pending trade per symbol/magic by default
- Market entry may be enabled for smoke tests, but the strategy default is limit entry at the selected FVG midpoint

Stop survival is a first-class strategy rule. The reference failure mode is a directionally correct GBPJPY buy with a 5.2 pip structural SL that was stopped by spread/noise in 11 seconds before price moved 36 pips in the intended direction. The EA deliberately accepts fewer trades and lower headline R per winner to avoid repeating that failure.

Primary entry gates:

- D1/H4 phase matches M15 setup bias.
- Liquidity sweep occurred: wick-through plus close-back. A close-through is structure break context, not a sweep entry.
- M1/M5 CHoCH/BOS/iBOS closes in the setup direction.
- No deeper unswept same-side liquidity pool sits within `InpDeeperPoolXATR` of entry.

SL anchoring:

- Long SL anchors below the swept low minus a buffer.
- Short SL anchors above the swept high plus a buffer.
- The buffer defaults to the greater of `0.3 * ATR(M5,14)` and the pair-class point floor converted to price.
- This is the Photon rule: stop behind the strong structure that defined the trade. The FVG edge is not allowed to create a tighter stop than the swept strong point.

Secondary safety gates use configurable empirical defaults. The structure of the gates is fixed for v1; the numeric values are adjusted only from backtest evidence:

- ATR floor: entry-to-SL distance must be at least `InpSLATRFloorMultiplier * ATR(M5,14)`, default `1.5`.
- Spread-adjusted floor: `(entry-to-SL - current_spread) / ATR(M5,14)` must remain above `InpSpreadAdjustedATRThreshold`, default `1.0`.
- Pair-class point floor: JPY pairs default to `150` points; majors default to `80` points; exotics can be configured higher later.
- ATR and pair-class floors may widen the SL outward from the swept-extreme anchor. They must never move the SL inward toward entry.

Skip rules:

- No visible sweep: skip.
- Deeper pool too close: skip.
- A widened stop fails the risk plan, minimum RR, lot sizing, or spread-adjusted survival check: skip.
- A future max-widen guard can be added after the first evidence run if R-distribution shows widened stops weaken the thesis.
- Spread consumes too much of the planned stop distance: skip.

Tuning methodology:

1. Run the unchanged baseline across all 11 pairs.
2. Review R distribution by pair, especially stopped trades that later moved in the intended direction.
3. Adjust only the per-pair stop floors, ATR multiplier, or spread-adjusted threshold that the evidence implicates.
4. Re-run the same date range and compare expectancy, drawdown, win rate, and average R.
5. Keep skipped-setup count visible. Do not reduce skipped setups by allowing FVG-only entries or removing the sweep gate.

News guard:

- The EA includes a structural `InpUseNewsWindowGuard` stub plus minutes-before/after inputs. It defaults off until a trusted calendar source is wired. The gate exists so future implementation does not have to reshape the setup contract.

## Trade Management

The EA fully replaces `AdaptiveTrailEA` assumptions by managing entries and exits in one EA. `AdaptiveTrailEA` is not a peer manager or fallback:

- Initial SL from swept extreme plus stop buffer, ATR floor, spread-adjusted survival check, and pair-class minimum stop floor
- Initial TP from nearest target liquidity/structure when available, otherwise fixed RR target
- Breakeven after configurable R
- Chandelier trailing after breakeven
- Optional TP removal for runner tests, disabled by default

## Magic Numbers

Each pair receives the same stable strategy-id-derived magic used by the CLI contract:

`magic = sha256("ehukai-poc-<PAIR>")[:8] % 80000 + 100000`

Default pair magics:

1. USDJPY: `176879`
2. EURUSD: `172432`
3. GBPUSD: `140360`
4. AUDUSD: `128648`
5. USDCAD: `128461`
6. NZDUSD: `146145`
7. USDCHF: `171860`
8. EURJPY: `159469`
9. GBPJPY: `174473`
10. AUDJPY: `137163`
11. EURGBP: `143861`

The Strategy Tester EA hardcodes these known defaults because MQL5 does not provide a native SHA-256 helper equivalent to Python's `hashlib` in the project baseline. Any future symbol outside the current set must either pass `InpMagicOverride` or add a documented mapping.

## Journaling

The EA writes tester-friendly CSV rows to `MQL5/Files/EhukaiTDAEA/`:

- Setup rows: timestamp, symbol, timeframe, status, direction, score, gates, POI, liquidity, VP, entry, SL, TP, RR, failure reason
- Entry rows: order ticket, position ticket, magic, direction, lots, entry, SL, TP, planned R
- Exit rows: position ticket, exit reason, gross/net profit, realized R, bars held, final SL/TP

The Strategy Tester wrapper collects the EA journal plus terminal report artifacts into `docs/backtests/`.

## Strategy Tester Automation

Add a local wrapper that:

- Locates `terminal64.exe` and `MetaEditor64.exe`
- Copies/compiles the EA into the configured MT5 terminal Experts folder
- Generates `.ini` tester configs for a symbol/timeframe/date range
- Stages `.set` input files into `MQL5/Profiles/Tester` and references only the `.set` filename in `ExpertParameters`, matching MT5 command-line tester requirements
- Runs `terminal64.exe /config:<ini>`
- Writes `Report=reports\<run-id>_<symbol>_<timeframe>_report` and collects HTML/XML reports plus EA CSV journals
- Summarizes trades, win rate, expectancy, drawdown, R distribution, pair/session breakdown, and failure modes where source data exists

The wrapper must treat a zero process exit with no reports and no EA journals as `TESTER_NO_ARTIFACTS`, not as a passed backtest. MT5 cannot run two copies from the same installation directory, so if the live terminal is already open the command-line smoke may require operator-approved terminal restart or a separate MT5 installation.

## Acceptance Criteria

Milestone 1 is acceptable when:

- Spec and plan exist under `docs/specs/` and `docs/plans/`
- EA source exists in the repo MQL5 Experts folder
- Tester wrapper exists and prints its exact command/config paths
- EA compiles with MetaEditor or the compile failure is captured with the exact log
- One-pair smoke backtest is attempted through MT5 Strategy Tester
- Smoke artifacts are collected or the blocker is documented with the command that failed

Later milestones expand to all 11 pairs and evidence-driven iteration only.
