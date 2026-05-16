# Safety / Code Review Notes - Order-Flow Proxy Confluence

Date: 2026-05-11
Status: Pre-implementation review

## Findings

### P1 - Terminology must stay proxy-only

The primary safety risk is presenting spot FX quote/tick-volume diagnostics as true exchange footprint data. Any implementation must use `OFProxy*` names for buffers, CSV columns, presets, UI labels, and docs.

Allowed:

- order-flow proxy
- `OFProxyDelta`
- `OFProxyAggression`
- `OFProxyStackedPressure`
- `OFProxyAbsorption`
- quote-movement pressure
- tick-volume pressure

Disallowed unless the data source changes:

- true delta
- executed bid/ask volume
- volume at each price
- guaranteed buyer/seller aggression
- confirmed institutional absorption

### P1 - Companion indicator cannot hide wavelet-dependent decisions

The proposed companion indicator should not read or duplicate `Advanced_Wavelet_Entry_Signal`. It should export raw proxy features only. The EA must derive the signal-specific `OFProxyDecisionState` from:

- base wavelet direction
- base wavelet score
- proxy confluence score
- proxy divergence/absorption conflicts
- spread/session gates
- existing structure context

This preserves the current base indicator contract and makes the integration auditable.

### P2 - CSV schema migration is required

The current EA writes fixed headers and supports append mode. Adding proxy columns to existing filenames would produce mixed-schema CSV files. Proxy-enabled CSV output must use:

- new `ofproxy_v1` run tags or filenames,
- `InpAppendCSV=false`, or
- a new `schema_version` column in a new file.

Do not append proxy rows to baseline CSV files with old headers.

## No-Leak / Non-Repaint Controls

Review checks:

1. Indicator calculations for shift `i` only read `i`, `i+1`, `i+2`, and older bars.
2. EA uses `CopyBuffer` shift `1` only for decisions.
3. Divergence does not use future-confirmed pivots.
4. Stacked pressure does not wait for future bars to confirm the current bar.
5. Absorption does not use future failure movement.
6. Forward returns remain delayed EA labels only.
7. Tick-enriched mode requests only already-closed bar intervals.
8. No closed bar buffer values are changed after closure.

## Strategy Tester Controls

Risks:

- tick-enriched mode may be slow for 5-year M5 tests
- `CopyTicksRange` behavior depends on modeling mode and broker history
- generated tick modes are not equivalent to real ticks
- optimization file writes can be expensive or restricted

Controls:

- bar-only proxy default
- tick enrichment optional and diagnostic
- cap tick requests per bar
- export data-quality flags
- avoid broad parameter optimization
- avoid Cloud optimization CSV file writes unless explicitly tested

## Trading.com / US-Style Execution Controls

The proxy layer must not weaken existing controls:

- no hedging assumptions
- one position per symbol/magic
- demo-only guard
- 0.01 lot default
- hard `InpMaxSafetyLots=0.01` research cap
- spread-aware filtering
- daily max-trade guard
- daily loss guard
- no silent live trading
- `InpAllowTrading=false` default

## Score-Combination Risk

Score adjustment and hard filtering can overfit quickly.

Controls:

- CSV diagnostics first
- score adjustment disabled by default
- hard filter disabled by default
- small bonus/penalty ranges only
- analyze by year and symbol before enabling
- keep a baseline run for comparison

## Exit-Management Risk

An exit overlay can accidentally overfit around the current USDJPY result. Current evidence is only a smoke-test baseline:

- HC80 no-TP 24-bar: 113 trades, +$10.21, profit factor 1.13.
- ATR TP 1.5 / SL 3.0: 113 trades, +$5.58, profit factor 1.10.

Controls:

- test proxy exits as diagnostics first
- compare against the no-TP 24-bar baseline
- validate beyond USDJPY
- use forward splits
- avoid optimizing many exit thresholds at once
- do not claim improved profitability without MT5 reports and out-of-sample evidence

## Code Review Checklist After Implementation

- [ ] Existing Advanced Wavelet indicator buffer indexes remain unchanged.
- [ ] Companion indicator buffer order matches EA constants exactly.
- [ ] All new `iCustom` inputs are passed in exact order.
- [ ] All new buffers initialize on every calculated bar.
- [ ] `EMPTY_VALUE` is used only where intentional.
- [ ] Reason-code bits are documented in README and CSV schema.
- [ ] No calls read future shifts.
- [ ] Tick-enrichment handles unavailable data without blocking.
- [ ] Proxy-enabled CSV files use a new schema or append-disabled writes.
- [ ] Default `.set` files remain observe-only.
- [ ] Trading mode still requires explicit opt-in and demo guard.

## Final Safety Conclusion

The framework is useful research material if implemented as a diagnostic order-flow proxy layer. It should not change execution until CSV evidence supports it, and it must not present proxy features as true executed-volume order flow.
