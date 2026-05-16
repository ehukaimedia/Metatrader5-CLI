# Codex Review: mt5-universal Phase 2.3 checkpoint

Review target: `mt5-universal` at `140fabb`
Compared against: `master` at `4d26992`

## Findings

1. **P1 [Critical]** - Invalid order sides silently become sell orders

   `mt5_universal/orders/orders.py:367`, `mt5_universal/orders/orders.py:384`, `mt5_universal/orders/orders.py:465`, `mt5_universal/orders/orders.py:571`, `mt5_universal/orders/orders.py:575`, `mt5_universal/orders/orders.py:583` - `place_market()`, `place_limit()`, and `dryrun()` never validate `side`; every non-`"buy"` value falls through to the sell branch. A typo such as `side="long"` can pass the risk gate and submit or dry-run a sell request instead of failing closed, which is a production safety issue for an agent-facing trading API. Add one shared side normalizer before price/type resolution and before `check_order()`, and add tests that assert invalid sides return `MT5_INVALID_PARAMS` without calling `order_send` / `order_check`:

   ```python
   def _normalize_side(side: str) -> tuple[str | None, dict | None]:
       side_lower = side.lower()
       if side_lower not in {"buy", "sell"}:
           return None, fail("MT5_INVALID_PARAMS", "side must be one of: buy, sell.")
       return side_lower, None
   ```

   Then use `side_lower` for the buy/sell branches instead of repeating `side.lower() == "buy"`.

2. **P2 [Important]** - Default `cfg["magic"]` can collide with the auto-derived agent range

   `mt5_universal/risk/risk.py:112` - `resolve_magic()` enforces the `< 100000` collision guard for `cfg["strategy_ids"]` mapped values, but returns `cfg["magic"]` unchecked when `strategy_id` is missing or empty. That lets a configured default magic such as `150000` overlap the auto-derived `[100000, 180000)` range, while `orders._is_agent_magic()` will classify it as agent-derived metadata. Extend the same guard to the fallback path:

   ```python
   default_magic = int(cfg["magic"])
   if default_magic >= 100000:
       raise ValueError(
           f"Configured default magic {default_magic} must be < 100000 "
           "to avoid collision with auto-derived range [100000, 180000)."
       )
   return default_magic
   ```

   Add tests for both `resolve_magic(None, cfg)` and `resolve_magic("", cfg)` with `cfg["magic"] >= 100000`.

3. **P2 [Important]** - Playground advertises a non-existent orders API

   `docs/playgrounds/mt5-universal-refactor-playground.html:575` - the Phase 2 capability text points agents at `.orders.market()`, but the implemented package exports `place_market()` from `mt5_universal/orders/__init__.py`. Future agents copying the playground guidance will get an `AttributeError`. Update the text to `mt5_universal.orders.place_market()` or add a deliberate alias.

4. **P2 [Important]** - Phase 2.9 indicator scope drifts between spec and plan

   `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:84` and `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:227` still list quicklook indicators as `ema/atr/rsi/sma/bbands/fvg/swing_pivots`, while `docs/plans/2026-05-15-mt5-universal-agent-native.md:1015` says FVG/swing-pivot stay archived and Task 2.9 ships only `ema`, `atr`, `rsi`, `sma`, `bbands`. Resolve this before Task 2.9 so agents do not reintroduce strategy-flavored indicator semantics into the agnostic layer.

5. **P3 [Minor]** - Playground still shows the old positional `check_order()` form

   `docs/playgrounds/mt5-universal-refactor-playground.html:331` - the visual companion shows `risk.check_order(symbol, side, volume, sl, ..., is_live_intent=False)`, but `mt5_universal/risk/risk.py:220` is keyword-only. Update the snippet to the actual call shape, e.g. `risk.check_order(symbol=symbol, side=side, volume=volume, sl=sl, cfg=cfg, is_live_intent=False)`.

6. **P3 [Minor]** - Bridge singleton smoke command has a docstring false positive

   `mt5_universal/bridge/__init__.py:1` - the requested bridge grep catches this docstring in addition to the real importer because it contains the literal text `import MetaTrader5`. This is not a runtime bridge violation, but it makes the smoke check noisier than the expected "only `mt5_backend.py`" result. Reword to avoid the grep pattern, for example: `"""Bridge layer; direct MetaTrader5 access lives only in mt5_backend."""`

## Validation

- `python -m pytest -q` -> `131 passed in 0.47s`
- `git diff --check master...HEAD` -> exit 0, no output
- `grep -rn "import MetaTrader5\|from MetaTrader5" mt5_universal/ tests/` -> `grep` is not installed in this PowerShell environment; equivalent `git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_universal tests` returned:

  ```text
  mt5_universal/bridge/__init__.py:1:"""Bridge layer — the ONLY module in the codebase allowed to import MetaTrader5."""
  mt5_universal/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
  mt5_universal/bridge/mt5_backend.py:20:# Re-exported MT5 constants (so no other module needs to import MetaTrader5)
  ```

- `git diff --stat master...HEAD` -> `241 files changed, 20833 insertions(+), 1797 deletions(-)`. The size is expected for this branch range because it includes the Phase 1 archive/document sweep plus the Phase 2 `mt5_universal/` and `tests/` additions.

## Open Questions / Assumptions

- I treated config (Task 2.4), broker profiles and filling abstraction (Tasks 2.5-2.8), indicators implementation (Task 2.9), bridge singleton CI (Task 2.11), and Phase 2 tag/acceptance (Task 2.12) as deferred unless there was artifact drift that would mislead those tasks.
- I did not flag `positions.close()` avoiding `check_order()` because the checkpoint prompt explicitly states positions manage existing exposure and should only use `_live_gate_check`.
- I did not flag the temporary hardcoded FOK filling behavior because the checkpoint prompt calls that out as expected until broker profile wiring in Task 2.8.
- I treated the `risk_pct` removal from `orders` as an intentional Phase 2.3 API shape because the current code/tests and MCP plan pass explicit `volume`; `compute_volume_from_risk_pct()` itself returns the required `ok({"volume": ...})` envelope and has no production consumer in this slice.
- I skipped the `account.trade_mode` contest collapse as a finding because commit `140fabb` intentionally restricts the display field to `demo|real`, and the risk live gate still checks the raw `ACCOUNT_TRADE_MODE_REAL` constant.
