# Ehukai / Photon SMC EA Backtesting Plan

Date: 2026-05-09
Status: Active

## Current Baseline

- Repo branch: `master`
- Green baseline from operator: `365 passed, 1 skipped`
- Key strategy commits:
  - `d461636` Harden VP confluence scoring coverage
  - `ae767b8` Add VP/POC confluence to Ehukai TDA
  - `1a639e7` Improve Ehukai liquidity sweep detection
- Current 11-pair set comes from `adaptive-forex-mt5/config.example.json`.

## Phase 0: Architecture Artifacts

Status: complete

- Created this plan.
- Created `docs/specs/2026-05-09-ehukai-tda-ea-backtesting.md`.
- Updated `docs/playgrounds/mt5-codebase.html` with the standalone EA and tester harness architecture.

## Phase 1: EA Skeleton And Local Tester Automation

Status: complete with environmental smoke blocker documented

Implementation targets:

- `metatrader5_cli/mt5/mql5/Experts/EhukaiTDAEA.mq5` created.
- `metatrader5_cli/mt5/core/tester.py` created.
- CLI command group under `mt5 tester` created.

EA first slice:

- Self-contained closed-bar MQL5 planner.
- D1/H4/M15/M5/M1 structure reads.
- FVG midpoint entry candidate.
- Liquidity sweep/trap context.
- VP/POC confluence.
- Demo-first risk sizing.
- BE and Chandelier management in the same EA.
- CSV journaling for setup, entry, exit, and failure reason.
- Pair-specific magic number mapping.

Tester first slice:

- Generate MT5 Strategy Tester `.ini` files.
- Stage `.set` files in `MQL5/Profiles/Tester` because MT5 command-line tester expects `ExpertParameters` there.
- Compile with MetaEditor when available.
- Run one symbol/timeframe/date-range test.
- Collect reports and journals under `docs/backtests/<run-id>/`.

Smoke target:

- Symbol: `USDJPY`
- Timeframe: `M5`
- Date range: `2026-04-01` to `2026-04-30`
- Goal: prove the EA loads, evaluates bars, journals decisions, and either trades or truthfully reports no READY setups.
- Current status: command-line smoke is blocked by `TESTER_NO_ARTIFACTS`; `terminal64.exe /config:<ini>` exits `0` in less than one second with no report/journals and no new terminal log lines while the same MT5 installation is already running live charts.

## Phase 2: Review And Coherent Commit

Status: complete

- Claude review completed in `docs/code-reviews/Claude1-d461636-ehukai-tda-ea-milestone1-review-2026-05-09.md`.
- Focused tests: `226 passed`.
- Full suite: `368 passed, 1 skipped`.
- EA compile: `0 errors, 0 warnings`.
- One-pair smoke command attempted and documented as `TESTER_NO_ARTIFACTS` due MT5 same-installation single-instance behavior.
- Coherent milestone commit is the next action after this plan update.

## Phase 3: 11-Pair Evidence Backtest

Status: pending

Run the same fixed range/timeframe across:

`USDJPY, EURUSD, GBPUSD, AUDUSD, USDCAD, NZDUSD, USDCHF, EURJPY, GBPJPY, AUDJPY, EURGBP`

Collect:

- Net profit and gross profit/loss
- Win rate
- Profit factor
- Expectancy per trade and per R
- Maximum drawdown
- R distribution
- Pair/session breakdown
- Failure modes from setup journals

No parameter changes happen until this evidence exists.

## Phase 4: Evidence-Only Iteration

Status: pending

Candidate iteration lanes:

- FVG age and distance filters
- VP hard-gate versus score-only behavior
- Liquidity sweep recency and trap tolerance
- Fixed RR versus target liquidity TP
- BE trigger and Chandelier multiplier
- Pair/session filters

Every iteration must cite a result table and preserve the previous settings.

## Non-Goals

- No live trading enablement in this pass.
- No optimization curve-fitting before the 11-pair baseline.
- No chart-object scraping from `EhukaiTDAOverlay`.
- No replacing the Python `sniper_poc` contract without parity notes.
