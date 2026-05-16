# adaptive-forex-mt5 `f583d88` Follow-Up Audit

## Findings

1. `adaptive-forex-mt5/agent.py:26` - `derive_magic()` duplicates the auto-derived SHA-256 branch but does not honor the CLI config's `strategy_ids` map. `order ready-limit` places through `risk.resolve_magic(strategy_id, cfg)`, which first checks configured strategy IDs before auto-deriving. If the MT5 CLI config ever pins one of these strategy IDs to a mapped magic, placements will use the mapped magic while outcome attribution keeps searching the auto-derived magic and never closes the journal row. Importing the CLI risk module is awkward from this POC folder, but the agent should either call a small CLI helper for magic resolution or implement the same three-tier mapping using the MT5 CLI config file. Confidence: medium-high.

2. `adaptive-forex-mt5/agent.py:107` and `adaptive-forex-mt5/agent.py:194` - The new close-deal match is only deterministic while there is at most one active/pending trade per `(magic, symbol)`. The code still counts only positions, not pending orders, and does not enforce one active order per pair. If the same pair receives multiple pending limits before the first is visible as a position, `find_close_deal()` can attribute the first later profitable/loss deal after placement time to the wrong journal ticket. This is the same pending-order concurrency issue from the first audit, but it now directly affects the new outcome matcher. Count pending orders and open journal placements by pair/magic before placing another setup, or store a broker-stable position/deal identifier once the order fills. Confidence: high.

## Verified

- `metatrader5_cli/mt5/core/risk.py:56` and `adaptive-forex-mt5/agent.py:26` currently produce the same auto-derived magics for the unconfigured `ehukai-poc-{PAIR}` strategy IDs.
- `%APPDATA%\MetaQuotes\Terminal\<TERMINAL_ID>\MQL5\Experts\AdaptiveTrailEA.set:1` now contains the expected 11 magics: `128461,128648,137163,140360,143861,146145,159469,171860,172432,174473,176879`.
- `adaptive-forex-mt5/config.json:23` now binds the dashboard to `127.0.0.1`.
- `python -m py_compile adaptive-forex-mt5\agent.py adaptive-forex-mt5\journal.py adaptive-forex-mt5\dashboard.py` passed.

## Verdict

`f583d88` closes the immediate EA preset mismatch and the dashboard perimeter issue, and it improves outcome attribution materially. I would still not call outcome data conclusive until the agent either enforces one active pending/position per pair/magic or stores a stable fill/position identifier. Without that, the first day of results can still become ambiguous exactly when the agent places repeated same-pair pending limits.
