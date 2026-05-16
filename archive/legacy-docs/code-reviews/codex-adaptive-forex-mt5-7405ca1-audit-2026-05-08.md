# adaptive-forex-mt5 `7405ca1` Audit

## Production-Risk

1. `%APPDATA%\MetaQuotes\Terminal\<TERMINAL_ID>\MQL5\Experts\AdaptiveTrailEA.set:1` and `metatrader5_cli/mt5/core/risk.py:56` - The CLI magic derivation matches the stated SHA-256 formula byte-for-byte, but the visible terminal preset contains `113054,162538`, not the current `ehukai-poc-{PAIR}` magics (`176879,172432,140360,128648,128461,146145,171860,159469,174473,137163,143861`). If that is the preset loaded by the running EA, agent-placed positions will not be managed. Add an agent startup preflight that derives every configured strategy magic using `risk.resolve_magic()` and refuses to run unless `AdaptiveTrailEA.set` or `mt5 ea adaptive-trail magics show` contains all of them. Confidence: high.

2. `adaptive-forex-mt5/agent.py:101` and `metatrader5_cli/mt5/core/history.py:65` - Outcome attribution matches `deal.order == placement_ticket`, but closing deals normally have their own close-order ticket; the stable join key is position/deal metadata, not necessarily the original pending order. The CLI also drops fields such as `position_id` and deal entry type, so the agent can log the opening deal as `even`, miss partial closes, or keep trades open forever. Return `position_id`/entry type from history, store it at fill/open time, and match/sum closing `DEAL_ENTRY_OUT` deals by position id + symbol + magic. Confidence: high.

3. `adaptive-forex-mt5/agent.py:163` - The concurrency cap counts open positions only. Because entries are pending limits, the agent can place multiple pending orders while `position list` is still empty; those can later fill and exceed the intended cap. Count same-strategy pending orders plus open positions, and preferably enforce one active pending/position per pair. Confidence: high.

## Strategy-Validation Gaps

1. `adaptive-forex-mt5/journal.py:28` and `adaptive-forex-mt5/agent.py:191` - Placement reasoning is taken from the pre-placement scan (`data`), while `order ready-limit` performs its own final refresh. The journal uses final entry/SL/TP but initial structure/POI/liquidity/gates, so the evidence record can describe a different setup than the one actually placed. Log `placement.data.initial_setup` and `placement.data.final_setup` in full, and use final setup as the canonical reasoning snapshot. Confidence: high.

2. `adaptive-forex-mt5/journal.py:57` - Skip records retain only `status`, `reason`, and `explain`. That is not enough to distinguish a correct refusal from a too-strict false negative, nor to ask which skipped setups would have won. Store the same setup contract on skips, at least gates with reasons, quote, structure, POI, liquidity, and entry candidate. Confidence: high.

3. `adaptive-forex-mt5/agent.py:152` and `adaptive-forex-mt5/journal.py:118` - Outcomes classify `tp/sl/even` from net `profit`, but the journal drops swap/commission and does not record gross direction correctness, target hit, R-multiple, or whether close was EA trail/manual/SL/TP. That can conflate framework edge with execution costs. Log profit, swap, commission, close reason/type, planned R, realized R, and price-relative outcome against planned SL/TP. Confidence: medium-high.

## Operational Fragility

1. `adaptive-forex-mt5/agent.py:41` and `adaptive-forex-mt5/agent.py:170` - A subprocess timeout is caught and the pair is skipped, but scanning is sequential. With 11 pairs and a 60s timeout, one bad loop can run about 11 minutes while outcome polling and new scans stall. Lower hot-path timeout, record loop duration, or run pair scans with bounded concurrency. Confidence: high.

2. `adaptive-forex-mt5/agent.py:126` and `adaptive-forex-mt5/agent.py:86` - Crash recovery only folds journal entries and looks back three days of deals. It does not reconcile pending orders, canceled/expired orders, or older open tickets, and it cannot repair outcomes that were missed before restart. On startup, replay open placements from their placement timestamps, query pending orders and positions, and backfill outcomes from history until every ticket is resolved. Confidence: high.

3. `adaptive-forex-mt5/dashboard.py:210` and `adaptive-forex-mt5/config.json:23` - The committed example binds `127.0.0.1`, but the live config currently binds `0.0.0.0` with no auth. `tailscale serve` is fine when the app binds localhost; binding all interfaces exposes journal data on LAN interfaces too. Force localhost by default, require an explicit unsafe flag for `0.0.0.0`, or add a bearer token. Confidence: high.

## Design Debt

- `adaptive-forex-mt5/agent.py:55` - The runtime is purely deterministic/hot-path today; no `prompt_version` or LLM review snapshot is recorded. This is acceptable for now, but add a nullable model-review block before comparing deterministic vs deep-review decisions.
- `adaptive-forex-mt5/agent.py:55` - Current entries are whatever `sniper-poc` exposes; the full entry-model enum, news filter, and M5-swept-high path remain out of scope.

## Confirmed

- `adaptive-forex-mt5/agent.py:34` correctly appends `--live` when `mt5_cli.live` is true, so live intent propagates into `order ready-limit`.
- `adaptive-forex-mt5/agent.py:41` catches subprocess failures/timeouts and logs them, so a single hung subprocess does not crash the process.
- `metatrader5_cli/mt5/core/risk.py:56` matches the stated magic formula exactly.

## Verdict

As committed, this is not yet sufficient evidence-collection infrastructure for either proof. The placement gate itself is strong, but the POC can run with an EA magic mismatch, can exceed intended exposure through pending-order accumulation, and can misattribute or miss outcomes. The journal also loses enough final setup and skip context that tomorrow's `logs/trades.jsonl` could answer "what happened" only partially and may not conclusively answer "does the Photon SMC framework work" or "can the live agent run safely 24/7." Fix the three production-risk items and enrich journal placement/skip/outcome records before treating the data as decisive.
