# Code Review - Advanced Order-Flow Proxy EA Integration

Date: 2026-05-11
Reviewer: Codex
Scope: `Advanced_Wavelet_Entry_ResearchEA.mq5`

## Findings

No blocking issues found after the first CSV-only order-flow proxy integration.

## Review Notes

- The EA registers `Advanced_OrderFlow_Proxy_Confluence.ex5` for Strategy Tester use.
- `InpUseOrderFlowProxy=false` remains the default, so existing presets keep baseline behavior unless explicitly enabled.
- The second `iCustom` handle is created only when the proxy input is enabled.
- Proxy `CopyBuffer` reads use shift `1`, matching the existing closed-bar signal contract.
- Proxy read failures do not make `ReadSignalAtShift()` fail; base signal frequency and trading decisions remain unchanged.
- Default filenames add an `ofproxy_v1` suffix when proxy CSV is enabled, avoiding mixed-schema append files.
- `of_proxy_adjusted_score` is exported as a reserved diagnostic field and currently equals the base score.

## Validation

- Full package MetaEditor compile: 0 errors, 0 warnings.
- MT5 terminal-data compile for the proxy indicator and EA: 0 errors, 0 warnings.
- Updated `.set` files include explicit proxy inputs; only `Advanced_Wavelet_USDJPY_M5_HC80_OFProxy_Diagnostic.set` enables the proxy.

## Residual Risk

The next validation step is an observe-only USDJPY M5 Strategy Tester run. The proxy fields should be analyzed as buckets before any score adjustment, hard filter, or exit overlay is implemented.
