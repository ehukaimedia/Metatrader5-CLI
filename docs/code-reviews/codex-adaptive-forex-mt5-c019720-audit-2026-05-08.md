# adaptive-forex-mt5 `c019720` Final Review

## Production-Risk

1. `adaptive-forex-mt5/agent.py:236` - The global `max_concurrent_positions` gate still does not count existing pending orders across scan loops. `active_strategies()` prevents another order on the same `(symbol, magic)`, but the global cap uses `len(list_positions(cfg))` plus only `placed_this_cycle`. With `max_concurrent_positions=2`, two pending limits can be placed in one loop while positions remain zero; on the next loop the cap resets to `0 + placed_this_cycle`, so different pairs can continue accumulating pending orders beyond the cap. Count all active same-strategy pending orders plus open positions in the global cap, not just positions. Confidence: high.

2. `adaptive-forex-mt5/agent.py:149` - `find_close_deal()` requires `(profit != 0)`, so breakeven exits, broker-zero-profit exits, or cost-only outcomes can remain unresolved forever in the journal. This is especially likely because AdaptiveTrailEA has breakeven behavior. Once an open journal record is no longer a pending order and no longer an open position, the resolver should classify a zero-profit close too, preferably using deal entry type/position id from the CLI; if those are unavailable, use the latest same-symbol/same-magic deal after placement as a fallback and mark attribution confidence. Confidence: high.

## Strategy-Validation Gaps

1. `adaptive-forex-mt5/journal.py:76` - `drift_points` is recorded but `mt5 order ready-limit` does not currently return it in `metatrader5_cli/mt5/core/analyze.py`, so this field is always `null`. The field is useful evidence for whether the final placed setup materially moved after the first scan. Return `drift_points` from `place_ready_limit()` or remove the field until implemented. Confidence: medium.

2. `adaptive-forex-mt5/agent.py:255` - The active-strategy check still derives auto magics locally. This is safe with the current unconfigured `strategy_ids`, and placement/outcome records now store broker-used magic, but if the CLI config pins `strategy_ids`, active pending orders with mapped magics will not match the locally derived auto magic and duplicate same-pair placements can resume. Resolve strategy magic through the same CLI config path or read the magic from `order list` by `strategy_id`/comment where available. Confidence: medium.

## Operational Fragility

- `adaptive-forex-mt5/agent.py:260` - Sequential 11-pair scan timeout and crash-recovery replay remain acknowledged carry-forward. They do not invalidate the current safety fixes, but they still limit 24/7 robustness evidence.

## Verified

- `adaptive-forex-mt5/journal.py:80` now records skip rows with full reasoning blocks: structure, POI, liquidity, entry, gates passed/failed, quote, bias counts, quality, and explain. Live tail records confirm the new shape.
- `adaptive-forex-mt5/journal.py:46` now records final setup reasoning as canonical and preserves initial reasoning for comparison.
- `adaptive-forex-mt5/agent.py:278` stores placement magic from `placement.data.placement.magic`, closing the outcome-magic mismatch for new records.
- `adaptive-forex-mt5/config.json:23` is localhost-bound, and the visible `AdaptiveTrailEA.set` contains the expected 11 magics.
- `python -m py_compile adaptive-forex-mt5\agent.py adaptive-forex-mt5\journal.py adaptive-forex-mt5\dashboard.py` passed.

## Verdict

`c019720` materially upgrades the journal into a much better evidence stream: full skip contracts, final placement reasoning, stored magic, and realized R are now present. However, I would not yet call the autonomous POC fully green for live-capable evidence collection because the global exposure cap can still be exceeded by pending orders across loops, and breakeven/zero-profit closures can remain unresolved. Fix those two items before treating `logs/trades.jsonl` as conclusive for either strategy edge or 24/7 runtime reliability.
