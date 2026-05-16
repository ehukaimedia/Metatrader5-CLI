# Code Review - Advanced Order-Flow Proxy Indicator

Date: 2026-05-11
Reviewer: Codex
Scope: `Advanced_OrderFlow_Proxy_Confluence.mq5`

## Findings

No blocking issues found in the initial companion indicator implementation.

## Review Notes

- The indicator is standalone and does not modify the existing `Advanced_Wavelet_Entry_Signal.mq5` 16-buffer contract.
- All public outputs use `OFProxy*` naming and avoid true-footprint or true-delta claims.
- Buffer `0` through `8` match the order documented in the spec and README.
- Bar `0` is cleared to neutral values, preserving closed-bar-only usage.
- Calculations for shift `i` use `i`, `i+1`, and older bars only.
- Divergence uses rolling past extremes, not future-confirmed pivots.
- Stacked pressure uses the current closed bar and older closed bars only.
- Tick enrichment is not implemented in v1, avoiding 5-year M5 performance risk.

## Validation

- Repo-package MetaEditor compile: 0 errors, 0 warnings.
- MT5 terminal-data MetaEditor compile: 0 errors, 0 warnings.
- Full package compile helper: order-flow proxy indicator, base wavelet indicator, and research EA all compiled with 0 errors and 0 warnings.

## Residual Risk

The indicator is diagnostic infrastructure only until the EA exports proxy CSV columns and bucket analysis proves the features add stable separation. The next code review should focus on the second `iCustom` handle, CSV schema migration, and shift-1-only EA reads.
