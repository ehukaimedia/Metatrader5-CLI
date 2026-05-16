# Safety Review

## Future leakage

The indicator uses shift `i` and older bars `i+1, i+2, ...` only. It does not use bars newer than the candidate, and the current forming bar `0` is deliberately cleared.

The EA reads shift `1` only for decisions. Forward-return labels are delayed until the future bars have actually closed; they are diagnostic labels, not execution inputs.

## Repainting

Closed historical signal calculations are deterministic from closed OHLC, spread, and volume arrays. Because no future bars are needed to confirm a pivot or fractal, a closed signal should not repaint. The current bar has no signal output.

## Pivot/fractal leakage

The pivot context is prior support/resistance from older bars only. It is not a confirmed fractal pivot that waits for right-side bars.

## Tick-by-tick retraining

There is no model fitting, retraining, or parameter adaptation on ticks. Inputs are static for each run.

## Performance

The indicator recalculates only the initial history and a small closed-bar window on subsequent ticks. Calculations are capped by visible input lookbacks and should be suitable for multi-year M5 testing. The EA performs work on new bars only.

## Broker/execution constraints

The EA defaults to observe-only mode. If trading is enabled, it still enforces:

- demo-account-only guard when `InpDemoAccountsOnly=true`;
- one position per symbol/magic;
- optional one-position-per-symbol guard;
- fixed lot input, default `0.01`;
- hard research lot cap, default `0.01`, and no auto-scaling upward to a larger broker minimum lot;
- current spread filter;
- daily max-trade guard reconstructed from account history on initialization/new day;
- daily realized-loss guard;
- optional FOK preference with fallback to broker symbol filling;
- exact-ticket position close for owned positions;
- no hedging assumptions and no same-bar reversal after opposite-signal close.

CSV folders are created before file open when a subfolder such as `WaveletResearch\` is used. Missing historical spread values are treated as unknown/pass-through in the indicator instead of falling back to current market spread, so historical signal gates do not change with the live spread at recalculation time.

## Operational risks

- Real ticks may differ materially from 1-minute OHLC discovery.
- Trading.com symbol specifications, filling modes, and spread behavior should be checked in the terminal before demo execution.
- MT5 Strategy Tester reports must be saved for every candidate setting.
- Do not infer profitability from CSV forward labels alone; use them to decide what deserves proper tester validation.
