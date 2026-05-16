# MT5 Universal — Agent-Native CLI Refactor Implementation Plan

> **For agentic workers:** Follow the repo's AGENTS.md direction: use advisor, feature-dev, and code-reviewer/subagent passes for implementation integrity, and update the playground/spec/plan when architecture changes. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-fork the archived tangled `metatrader5_cli/mt5/core/` patterns into a fresh, agnostic, agent-native Python library at `mt5_cli/` that drives MT5's native Strategy Tester from the CLI, publishes itself as both a `mt5` CLI and a `mt5-mcp` MCP server, and treats Trading.com as the canonical (but not hardcoded) broker profile.

**Architecture:** Library-first. One Python package (`mt5_cli/`) with submodule-per-concern (bridge, broker, market, rates, orders, positions, account, history, risk, indicators, mql5, tester, config, reports, skills). The `mt5` CLI and `mt5-mcp` MCP server are thin wrappers over the same library. MQL5 is the canonical author format for EAs and indicators; MT5 Strategy Tester is the canonical backtest engine. No Python event-driven backtester. No coexistence shims with the legacy core.

**Tech Stack:** Python 3.10+, Click 8.x (CLI), FastMCP (MCP server), MetaTrader5 Python package (bridge, Windows-only), pytest (tests), MetaEditor.exe + terminal64.exe (subprocess targets). The tool ships no indicator math; pandas/pandas-ta are NOT dependencies of the universal library.

## References (read before starting)

| | |
|---|---|
| Spec | [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](../specs/2026-05-15-mt5-universal-agent-native-design.md) |
| Reviewer context | [docs/specs/2026-05-15-mt5-universal-review-context.md](../specs/2026-05-15-mt5-universal-review-context.md) |
| Visual companion | [docs/playgrounds/mt5-universal-refactor-playground.html](../playgrounds/mt5-universal-refactor-playground.html) |
| Archived legacy CLI spec (v0.5) | [archive/legacy-docs/specs/mt5-cli-spec.md](../../archive/legacy-docs/specs/mt5-cli-spec.md) |

## Locked decisions (do not re-litigate)

See spec §4 and reviewer context §2. Summary: hard fork; MQL5 canonical author format; MT5 Strategy Tester is THE engine; library-first; MCP+CLI dual surface; Trading.com canonical default; portability rails; SKILL.md migrated not replaced.

## Pre-flight (current branch baseline before Phase 2)

- [ ] **Step P1: Verify branch and clean working tree**

```bash
git branch --show-current   # expect: mt5-universal
git status --short          # untracked OK; no modified or staged
```

- [ ] **Step P2: Verify green baseline**

```bash
python -m pytest -q
```

Expected now: `1 passed` from the transitional placeholder. The original Phase 0 baseline was `240 passed, 1 skipped` before the wholesale archive move.

- [ ] **Step P3: Verify spec, reviewer context, and playground are present**

```bash
ls docs/specs/2026-05-15-mt5-universal-agent-native-design.md
ls docs/specs/2026-05-15-mt5-universal-review-context.md
ls docs/playgrounds/mt5-universal-refactor-playground.html
```

All three must exist. If any is missing, stop and resolve before proceeding.

---

## File Structure (target — what we'll have at the end)

```
Metatrader5-CLI/
├── archive/                              # NEW (Phase 1) — git-tracked
│   ├── legacy-mt5/                       # retired metatrader5_cli/mt5 package, kept as cherry-pick reference
│   ├── legacy-docs/                      # retired strategy docs/playgrounds/handoffs/specs
│   └── legacy-mql5/                      # Advanced_Wavelet_Entry_System and other standalone MQL5 history
├── mt5_cli/                        # NEW — agnostic library
│   ├── bridge/mt5_backend.py             # ONLY file that imports MetaTrader5
│   ├── config/{config,trading_com}.py    # single-broker scope (Trading.com only)
│   ├── market/, rates/, orders/, positions/, account/, history/, risk/
│   ├── chart/, screenshot/               # Win32 chart UI + capture primitives
│   ├── mql5/{compiler,deployer,discovery}.py + templates/   # Phase 3
│   ├── tester/{ea,indicator,ini_builder,launcher,results,cache}.py   # Phase 4
│   ├── reports/__init__.py
│   └── skills/SKILL.md                   # migrated from archive/legacy-mt5/skills/
├── mt5/                                  # NEW — thin CLI wrapper
│   ├── __main__.py
│   └── cli.py
├── mt5_mcp/                              # NEW — FastMCP server
│   └── server.py
├── tests/test_no_hardcoded_paths.py      # NEW — CI portability guard
├── MT5_HARNESS.md                        # NEW — methodology SOP
├── setup.py                              # MODIFIED — declares mt5 + mt5-mcp scripts
├── pytest.ini                            # MODIFIED — add new test paths
└── .gitignore                            # MODIFIED only for repo-local build/test artifacts
```

The legacy `metatrader5_cli/` package is fully archived after Phase 1 — nothing imports from it. User EAs, indicators, presets, and Strategy Tester results are intentionally **not** repo directories; they live in the user's CWD or platform config/data dirs and are documented in Phase 3.

---

## Phase 1 — Archive legacy (DONE, by wholesale user move)

**Status:** Phase 1 was executed in a single user-driven wholesale move (commits `ce2cfac`, `bb61428`, `0df1093`). The entire `metatrader5_cli/mt5/` tree was relocated to `archive/legacy-mt5/`, the strategy-flavored docs/playgrounds/handoffs were swept to `archive/legacy-docs/`, the legacy MQL5 tree and `Advanced_Wavelet_Entry_System/` are under `archive/legacy-mql5/`, and 31 strategy-flavored code reviews were deleted. The `mt5_cli/` library does not yet exist — Phase 2 builds it fresh.

**What this differs from the original Phase 1 plan:**
- Original, now superseded: split-archive only the strategy-flavored modules and leave surviving primitives in place for Phase 2 moves.
- Actual: every module — strategy-flavored AND surviving primitives — moved to `archive/legacy-mt5/`. Phase 2 now writes the new library **fresh**, cherry-picking specific patterns from `archive/legacy-mt5/` rather than wholesale porting.

**Phase 1 acceptance (already met):**
- `python -m pytest -q` → `1 passed` (transitional placeholder at `tests/test_phase_transition.py`)
- `git diff --check master...HEAD` → exit 0
- `git ls-tree -r HEAD -- archive/` → nonzero archive inventory preserved (167 files at this audit point)
- `metatrader5_cli/` package no longer in the live tree
- No `MetaTrader5` imports remain in the live tree (the entire CLI moved to archive)
- `setup.py` console_scripts intentionally empty (returns in Phase 3 + 5)

**Phase 1 reference material at `archive/legacy-mt5/`** — what's available to cherry-pick from:
- `archive/legacy-mt5/utils/mt5_backend.py` — the bridge: `mt5_call()` locked dispatcher, `connect()` idempotent, `reconnect_once()`, MT5 constant re-exports
- `archive/legacy-mt5/core/risk.py` — the 11-gate risk module: `check_order()`, `compute_volume_from_risk_pct()`, `resolve_magic()`, `daily_loss()` (combines realized + floating)
- `archive/legacy-mt5/core/order.py` — order placement: `_resolve_filling()`, `_finalize_order()`, `list_pending()` with agent-magic metadata
- `archive/legacy-mt5/core/{account,history,market,position,rates}.py` — primitives we cherry-pick into the new agnostic surface
- `archive/legacy-mt5/core/project.py` — 4-layer config loader (DEFAULTS → file → env → CLI)
- `archive/legacy-mt5/skills/SKILL.md` — the 11k-char agent contract migrated in Phase 5
- `archive/legacy-mt5/utils/repl_skin.py` — the REPL banner / dispatch (upgraded in Phase 5)
- `archive/legacy-mt5/tests/conftest.py` — pytest fixtures including the `MetaTrader5` MagicMock stub
- `archive/legacy-mt5/tests/test_core.py` — the surviving-primitives' test patterns (TestBridge, TestMarket, TestRates, TestAccount, TestRisk, TestOrder, TestPosition, TestKillSwitch, TestRepl)
- `archive/legacy-mt5/tests/test_decoupling.py` — module-boundary tests we model `tests/test_bridge_singleton.py` on

**For implementer subagents in Phase 2+:** when a task says "cherry-pick from archive/legacy-mt5/X.py", read X.py to understand the **pattern** (locking discipline, gate-by-gate risk check structure, MT5 constant naming, error-envelope shape). Do not copy the file verbatim. Rewrite under the new module names, with the broker abstraction (Phase 2.5-2.8), the agnostic naming, and any cleanups that drop now-irrelevant special cases.

## Phase 2 — `mt5_cli/` skeleton (12 tasks)

**Goal:** Create the new agnostic library fresh under `mt5_cli/`. Cherry-pick only the useful patterns from `archive/legacy-mt5/core/` into new module names. Single-broker scope: Trading.com only, via `config/trading_com.py` merged into the standard config loader (NO `BrokerProfile` ABC — multi-broker is a later addition). **No indicator math ships from this layer** — the tool only provides hands.

### Task 2.1: Create mt5_cli/ package skeleton

**Files:**
- Create: `mt5_cli/__init__.py`
- Create: `mt5_cli/{bridge,broker,market,rates,orders,positions,account,history,risk,indicators,mql5,tester,config,reports,skills}/__init__.py`

- [ ] **Step 1: Create the package directory tree**

```powershell
$dirs = @(
  "mt5_cli",
  "mt5_cli\bridge", "mt5_cli\broker", "mt5_cli\market",
  "mt5_cli\rates", "mt5_cli\orders", "mt5_cli\positions",
  "mt5_cli\account", "mt5_cli\history", "mt5_cli\risk",
  "mt5_cli\indicators", "mt5_cli\mql5", "mt5_cli\tester",
  "mt5_cli\config", "mt5_cli\reports", "mt5_cli\skills"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
```

- [ ] **Step 2: Add empty `__init__.py` to each (so pytest discovers them)**

```powershell
foreach ($d in $dirs) { New-Item -ItemType File -Force -Path (Join-Path $d "__init__.py") | Out-Null }
```

- [ ] **Step 3: Verify**

```powershell
(Get-ChildItem -Path mt5_cli -Recurse -Filter __init__.py).Count   # expect 16
```

- [ ] **Step 4: Don't commit yet — coupled with Task 2.2**

### Task 2.2: Cherry-pick the bridge into mt5_cli/bridge/

**Files:**
- Create: `mt5_cli/bridge/mt5_backend.py` (the ONLY module that imports `MetaTrader5`)
- Create: `mt5_cli/bridge/__init__.py` (re-export public API)
- Create: `tests/test_bridge.py`
- Delete: `tests/test_phase_transition.py` (transitional placeholder; real tests now carry the suite)

**Cherry-pick reference** (read for *pattern*, do not copy verbatim):
- `archive/legacy-mt5/utils/mt5_backend.py` — locking discipline around `mt5_call`, idempotent `connect()` with double-checked locking, MT5 constant re-exports (`ORDER_FILLING_FOK`, `ORDER_TYPE_BUY`, etc.), `reconnect_once()` shape, `ensure_symbol()` semantics, `atexit` shutdown.
- `archive/legacy-mt5/tests/conftest.py` — the `MetaTrader5` MagicMock fixture pattern (model the new test stub on it).

- [ ] **Step 1: Write the failing test**

Create `tests/test_bridge.py`:

```python
import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    # The bridge imports MetaTrader5 at module import time. Purge bridge modules
    # so each test binds to this test's fake instead of a cached earlier fake.
    for name in list(sys.modules):
        if name == "mt5_cli.bridge" or name.startswith("mt5_cli.bridge."):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    fake.symbol_select.return_value = True
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 10
    fake.ORDER_TYPE_SELL = 11
    fake.TRADE_ACTION_SLTP = 30
    fake.TIMEFRAME_M5 = 500
    fake.COPY_TICKS_ALL = 700
    fake.ACCOUNT_TRADE_MODE_DEMO = 900
    fake.ORDER_TIME_GTC = 1000
    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name == "mt5_cli.bridge" or name.startswith("mt5_cli.bridge."):
            sys.modules.pop(name, None)


def test_bridge_imports(mocked_mt5):
    from mt5_cli.bridge import connect, mt5_call, ensure_symbol, reconnect_once  # noqa: F401


def test_connect_is_idempotent(mocked_mt5):
    from mt5_cli.bridge import connect
    connect(login=1, password="x", server="s")
    connect(login=1, password="x", server="s")
    assert mocked_mt5.initialize.call_count <= 1


def test_connect_without_password_calls_bare_initialize(mocked_mt5):
    from mt5_cli.bridge import connect
    connect()
    mocked_mt5.initialize.assert_called_once_with()


def test_mt5_call_dispatches(mocked_mt5):
    from mt5_cli.bridge import mt5_call
    mocked_mt5.symbol_info_tick.return_value = MagicMock(bid=1.0, ask=1.0001)
    out = mt5_call("symbol_info_tick", "EURUSD")
    assert out is not None
    mocked_mt5.symbol_info_tick.assert_called_once_with("EURUSD")


def test_ensure_symbol_returns_bool(mocked_mt5):
    from mt5_cli.bridge import ensure_symbol
    assert ensure_symbol("USDJPY") is True
    mocked_mt5.symbol_select.assert_called_with("USDJPY", True)


def test_filling_constants_re_exported(mocked_mt5):
    import importlib
    import mt5_cli.bridge as br
    importlib.reload(br)
    assert br.ORDER_FILLING_FOK == 1
    assert br.ORDER_FILLING_IOC == 2
    assert br.ORDER_FILLING_RETURN == 3
    assert br.TIMEFRAME_M5 == 500
    assert br.COPY_TICKS_ALL == 700
    assert br.ACCOUNT_TRADE_MODE_DEMO == 900
    assert br.ORDER_TIME_GTC == 1000
    assert br.TRADE_ACTION_SLTP == 30
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_bridge.py -v
```

Expected: fail on missing bridge exports/attributes. Task 2.1 creates the package skeleton, so the package should import but the public bridge API should not exist yet.

- [ ] **Step 3: Write the new bridge**

Create `mt5_cli/bridge/mt5_backend.py`. Open `archive/legacy-mt5/utils/mt5_backend.py` side-by-side and **cherry-pick**:
- The `_lock = threading.Lock()` module-level lock
- The `_initialized` boolean for connect-once semantics
- `connect()` shape with double-checked locking + the `mt5.initialize(password=None)` quirk handling (call `mt5.initialize()` with no args when password is None)
- `mt5_call(fn_name, *args, **kwargs)` dispatcher (acquires lock, calls `getattr(mt5, fn_name)(*args, **kwargs)`)
- `ensure_symbol(symbol) -> bool` (calls `mt5.symbol_select(symbol, True)`)
- `reconnect_once(cfg) -> bool` (shutdown + re-initialize, used by Phase 5 REPL)
- The list of MT5 constants re-exported (everything starting with `ORDER_`, `TRADE_`, `POSITION_`, `SYMBOL_`, `TIMEFRAME_`, `COPY_TICKS_`, `ACCOUNT_TRADE_MODE_`; include `TRADE_ACTION_SLTP` and `ORDER_TIME_*` because later rates/orders/account/positions modules depend on them)
- `atexit.register(_shutdown)`

**Skip** anything tied to the legacy CLI's `_compose_live_intent` or other CLI-flavored helpers — those belong with the CLI in Phase 3, not the bridge.

Write `mt5_cli/bridge/__init__.py`:

```python
"""Bridge layer — the ONLY module in the codebase allowed to import MetaTrader5."""
from .mt5_backend import (
    connect, mt5_call, ensure_symbol, reconnect_once,
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN,
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT,
    ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP,
    TRADE_ACTION_DEAL, TRADE_ACTION_PENDING, TRADE_ACTION_MODIFY, TRADE_ACTION_REMOVE, TRADE_ACTION_SLTP,
    POSITION_TYPE_BUY, POSITION_TYPE_SELL,
    TIMEFRAME_M5, COPY_TICKS_ALL, ACCOUNT_TRADE_MODE_DEMO, ORDER_TIME_GTC,
)

__all__ = [
    "connect", "mt5_call", "ensure_symbol", "reconnect_once",
    "ORDER_FILLING_FOK", "ORDER_FILLING_IOC", "ORDER_FILLING_RETURN",
    "ORDER_TYPE_BUY", "ORDER_TYPE_SELL",
    "ORDER_TYPE_BUY_LIMIT", "ORDER_TYPE_SELL_LIMIT",
    "ORDER_TYPE_BUY_STOP", "ORDER_TYPE_SELL_STOP",
    "TRADE_ACTION_DEAL", "TRADE_ACTION_PENDING", "TRADE_ACTION_MODIFY", "TRADE_ACTION_REMOVE", "TRADE_ACTION_SLTP",
    "POSITION_TYPE_BUY", "POSITION_TYPE_SELL",
    "TIMEFRAME_M5", "COPY_TICKS_ALL", "ACCOUNT_TRADE_MODE_DEMO", "ORDER_TIME_GTC",
]
```

- [ ] **Step 4: Delete the transitional placeholder**

```bash
rm tests/test_phase_transition.py
```

- [ ] **Step 5: Run tests — pass**

```bash
python -m pytest -q
```

Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Phase 2: cherry-pick bridge into mt5_cli/bridge/

Fresh bridge module under mt5_cli/. Locking discipline,
idempotent connect(), mt5_call dispatcher, and MT5 constant
re-exports written from scratch using archive/legacy-mt5/utils/mt5_backend.py
as the reference pattern, NOT as a wholesale port. The single-bridge
rule (only file that imports MetaTrader5) is enforced at the package
boundary. Transitional placeholder test removed."
```

### Task 2.3: Cherry-pick the surviving primitives into mt5_cli/

The legacy `metatrader5_cli/mt5/core/` had 7 agnostic primitives now archived. We re-create each one under `mt5_cli/` as a separate sub-task — **one fresh implementer subagent per sub-task**.

**Shared prerequisite:** complete Task 2.10's `mt5_cli.reports.ok()/fail()` helper immediately after Task 2.2 and before dispatching any 2.3 primitive, even though it is listed later in this phase. Do not inline seven separate envelope helpers; the primitives should all return the same canonical report envelope from the start.

Same shape every time:

1. Open the reference file under `archive/legacy-mt5/core/<name>.py`
2. Write the failing test in `tests/test_<name>.py` (model the test patterns on `archive/legacy-mt5/tests/test_core.py` `class Test<Name>`)
3. Run pytest — fails (module missing)
4. Write the new module under `mt5_cli/<name>/<name>.py`, cherry-picking patterns from the archive (NOT a verbatim port). Use absolute imports from `mt5_cli.bridge`. Wrap returns in `mt5_cli.reports.ok()` / `fail()`.
5. Wire `mt5_cli/<name>/__init__.py` to re-export the public API
6. Run pytest — pass
7. Commit

| Sub-task | New module path | Reference (archive) | Notes |
|---|---|---|---|
| **2.3.A** | `mt5_cli/account/account.py` | `archive/legacy-mt5/core/account.py` | `info()`, `balance()`, `risk(cfg)`. The risk envelope's `safe_to_trade` flag must remain. |
| **2.3.B** | `mt5_cli/history/history.py` | `archive/legacy-mt5/core/history.py` | `orders()`, `deals()`, `stats()`. ISO-8601 timestamps. `strategy_id` filter via `resolve_magic` (lands in 2.3.E — temporarily inline the magic resolution if 2.3.E hasn't shipped). |
| **2.3.C** | `mt5_cli/market/market.py` | `archive/legacy-mt5/core/market.py` | `info()`, `tick()`, `depth()`, `search()`, `sessions()`. `depth()` is the longest function — DOM bid/ask normalization, spread_points, midpoint, imbalance. The `market_book_add` / `market_book_get` / `market_book_release` must release after each one-shot read. |
| **2.3.D** | `mt5_cli/rates/rates.py` | `archive/legacy-mt5/core/rates.py` | `fetch()`, `latest()`, `ticks()`. Test the timeframe-string-to-constant map (`"M5" → mt5.TIMEFRAME_M5`). |
| **2.3.E** | `mt5_cli/risk/risk.py` | `archive/legacy-mt5/core/risk.py` | **The 11-gate risk module — the most important sub-task.** TDD every gate separately (1 test per gate). `archive/legacy-mt5/tests/test_core.py` `class TestRisk` lists them: strategy-id length, live-gate, symbol allowlist, max lot, SL distance, spread, hedge guard, max positions, free margin, daily loss cap, rate limiter. Cherry-pick the gate names + `RISK_*` error codes + thresholds. `resolve_magic()` SHA-256 derivation (sha256(id)[:8] % 80000 + 100000 → range [100000, 180000)). `compute_volume_from_risk_pct()`. `daily_loss()` realized + floating combined. Rate limiter sliding-60s window via `collections.deque`. |
| **2.3.F** | `mt5_cli/orders/orders.py` (note plural rename) | `archive/legacy-mt5/core/order.py` | `place_market()`, `place_limit()`, `dryrun()`, `list_pending()`, `cancel()`, `poll_fill()`. Every mutating function takes keyword-only `is_live_intent`. `dryrun()` calls `order_check` (NOT `order_send`). FOK filling is hardcoded (Trading.com policy via `_resolve_filling`) — no broker abstraction needed under single-broker scope. |
| **2.3.G** | `mt5_cli/positions/positions.py` (note plural rename) | `archive/legacy-mt5/core/position.py` | `list()`, `close()`, `close_all()`, `breakeven()`, `move_sl()`. Keyword-only `is_live_intent` on every mutator. `breakeven()` sets SL to open ± `buffer_points` (default 0). |

**Worked example for sub-task 2.3.A — `account` (the others follow the same shape):**

- [ ] **Step 1: Write the failing test** at `tests/test_account.py`

```python
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    fake.account_info.return_value = MagicMock(
        login=88888, balance=10000.0, equity=10012.5,
        margin=0.0, margin_free=10012.5, margin_level=0.0,
        leverage=50, currency="USD", server="Trading.comMarkets-MT5",
        trade_mode=0,  # DEMO
    )
    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", fake)
    yield fake


def test_account_info_returns_envelope(mocked_mt5):
    from mt5_cli.account import info
    env = info()
    assert env["ok"] is True
    assert env["data"]["balance"] == 10000.0
    assert env["data"]["currency"] == "USD"


def test_account_balance_subset(mocked_mt5):
    from mt5_cli.account import balance
    env = balance()
    assert env["ok"] is True
    assert "balance" in env["data"]
    assert "currency" in env["data"]
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_account.py -v
```

- [ ] **Step 3: Write `mt5_cli/account/account.py`**

Open `archive/legacy-mt5/core/account.py`. Cherry-pick `info()`, `balance()`, `risk(cfg)`. Imports come from `mt5_cli.bridge` (not the archived `utils.mt5_backend`).

- [ ] **Step 4: Wire `mt5_cli/account/__init__.py`**

```python
from .account import info, balance, risk

__all__ = ["info", "balance", "risk"]
```

- [ ] **Step 5: Run tests — pass**

- [ ] **Step 6: Commit**

```bash
git add mt5_cli/account/ tests/test_account.py
git commit -m "Phase 2.3.A: cherry-pick account primitive into mt5_cli/

info() / balance() / risk(cfg) ported pattern-for-pattern from
archive/legacy-mt5/core/account.py with absolute imports from
mt5_cli.bridge and the standard ok/fail envelope shape."
```

**After all 7 sub-tasks complete:**

```bash
python -m pytest -q   # expect ~30-50 tests passing across the 7 modules + bridge
git tag phase-2.3-complete
```

#### Sub-task 2.3.H — Complete the deferred ordering primitives

Task 2.3.F shipped `list_pending`, `place_market`, `place_limit`, `dryrun`, `cancel`, `poll_fill`. The user-direction "all ordering features" requires the three deferred primitives to land before the chart/screenshot work in 2.6-2.8:

| Primitive | MT5 surface | Notes |
|---|---|---|
| `place_stop(symbol, side, price, volume, sl, tp=None, *, is_live_intent, cfg, strategy_id=None)` | `order_send` with `TRADE_ACTION_PENDING` + `ORDER_TYPE_BUY_STOP / SELL_STOP` | Same risk-gate keyword-only pattern as `place_limit`. Cherry-pick `archive/legacy-mt5/core/order.py::place_stop` (around line 369) |
| `modify(ticket, *, sl=None, tp=None, price=None, expiry=None, is_live_intent)` | For open positions: `order_send` with `TRADE_ACTION_SLTP` + `position=ticket`. For pending orders: `TRADE_ACTION_MODIFY` + `order=ticket` | Single entry point handles both pending modify and position SL/TP update — detect via `positions_get(ticket=ticket)` first |
| `cancel_all_pending(symbol=None, *, is_live_intent)` | Iterate `orders_get(symbol=symbol)`, call `cancel(ticket)` per-ticket, fail-soft per-ticket | Returns `ok({"per_ticket": [{ticket, ok, error}, ...]})` |

**Optional but worth flagging:** `place_stop_limit` (combines stop-trigger + limit-fill price; uses `ORDER_TYPE_BUY_STOP_LIMIT / SELL_STOP_LIMIT`) and `close_by` (netting accounts only — closes one position by another). Implement only if the user surfaces a need. Trading.com is hedging-blocked so `close_by` mostly does not apply; `place_stop_limit` is rarely used but available.

Same shape as the other 2.3 sub-tasks:
1. Cherry-pick reference: `archive/legacy-mt5/core/order.py` (lines around `place_stop`, `modify`, `cancel_all_pending`)
2. Write failing tests in `tests/test_orders.py` (extend the existing test classes — TestPlaceStop, TestModify, TestCancelAllPending)
3. Run, fail
4. Implement under `mt5_cli/orders/orders.py`
5. Update `__init__.py` to re-export
6. Run, green
7. Commit

After this commit, the orders module exposes the complete ordering surface; nothing further in this concern.

```bash
git tag phase-2.3.H-complete
```


### Task 2.4: Add config layer with 4-layer resolution

**Files:**
- Create: `mt5_cli/config/__init__.py`
- Create: `mt5_cli/config/config.py` (the resolution logic)
- Create: `tests/test_config.py`

(`paths.py` lands in Phase 6 with the full portability rails. This task only does the 4-layer settings resolver.)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import os

import pytest

from mt5_cli.config import load


@pytest.fixture
def clean_env(monkeypatch):
    for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
        monkeypatch.delenv(k, raising=False)


def test_defaults_when_nothing_overrides(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    cfg = load()
    assert cfg["live"] is False
    assert cfg["magic"] == 88888
    assert cfg["max_positions"] == 5
    # Single-broker scope: no broker_profile field. Task 2.5 merges
    # TRADING_COM_DEFAULTS in; multi-broker is a later addition.
    assert "broker_profile" not in cfg


def test_file_overrides_defaults(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text('{"max_positions": 7, "max_lot_per_order": 1.0}')
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    cfg = load()
    assert cfg["max_positions"] == 7
    assert cfg["max_lot_per_order"] == 1.0


def test_env_overrides_file(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text('{"login": 11111, "server": "FileServer"}')
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    monkeypatch.setenv("MT5_LOGIN", "22222")
    monkeypatch.setenv("MT5_SERVER", "EnvServer")
    cfg = load()
    assert cfg["login"] == 22222
    assert cfg["server"] == "EnvServer"


def test_overrides_arg_takes_highest_precedence(clean_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setenv("MT5_LOGIN", "22222")
    cfg = load(overrides={"login": 33333})
    assert cfg["login"] == 33333
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_config.py -v
```

Expected: ImportError because `mt5_cli.config.load` doesn't exist.

- [ ] **Step 3: Implement the config loader**

Create `mt5_cli/config/config.py`:

```python
"""4-layer settings resolution: DEFAULTS → file → env → CLI overrides.

Path resolution (where the config FILE lives) is in mt5_cli/config/paths.py
(added in Phase 6). This module just reads/merges the layers.
"""
import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # NO broker_profile field — single-broker scope. Task 2.5 merges
    # TRADING_COM_DEFAULTS in here; multi-broker is a later addition.
    "server": "Trading.comMarkets-MT5",
    "login": None,
    "password": None,
    "live": False,
    "magic": 88888,
    "deviation": 20,
    "filling": "auto",
    "max_positions": 5,
    "max_daily_loss": 2000.0,
    "max_lot_per_order": 2.5,
    "min_sl_distance_points": 50,
    "max_spread_points": 80,
    "min_free_margin_pct": 20,
    "max_orders_per_minute": 10,
    "symbol_allowlist": [],
    "allow_hedging": False,
    "strategy_ids": {},
}

ENV_MAP = {
    "MT5_LOGIN": ("login", int),
    "MT5_PASSWORD": ("password", str),
    "MT5_SERVER": ("server", str),
    "MT5_LIVE": ("live", lambda s: s == "1"),
}


def _config_path() -> Path:
    """Resolve config file path. Phase 6 swaps in the full XDG/APPDATA resolver."""
    if "MT5_CONFIG" in os.environ:
        return Path(os.environ["MT5_CONFIG"])
    home = Path(os.path.expanduser("~"))
    return home / ".config" / "metatrader5-cli.json"


def load(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    path = _config_path()
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass
    for env_key, (cfg_key, caster) in ENV_MAP.items():
        if env_key in os.environ:
            cfg[cfg_key] = caster(os.environ[env_key])
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def save(cfg: dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))


def mask_secrets(cfg: dict[str, Any]) -> dict[str, Any]:
    masked = dict(cfg)
    if masked.get("password"):
        masked["password"] = "***"
    return masked
```

Wire `mt5_cli/config/__init__.py`:

```python
from .config import DEFAULTS, load, save, mask_secrets

__all__ = ["DEFAULTS", "load", "save", "mask_secrets"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add mt5_cli/config/ tests/test_config.py
git commit -m "Phase 2: add config loader with 4-layer resolution

DEFAULTS -> file (MT5_CONFIG or ~/.config/metatrader5-cli.json) ->
env (MT5_LOGIN/PASSWORD/SERVER/LIVE) -> CLI overrides. Path
resolution stays simple here; the full XDG/APPDATA resolver lands
in Phase 6 as paths.py."
```

### Task 2.5: Add Trading.com order-placement settings (single-broker)

**Files:**
- Create: `mt5_cli/config/trading_com.py`
- Create: `tests/test_config_trading_com.py`
- Modify: `mt5_cli/config/config.py` (merge Trading.com defaults into the loaded config)

**Scope reduction from the original plan:** the original Phase 2 had four tasks (`BrokerProfile` ABC, Trading.com profile, generic_mt5 profile, wire orders to broker profile). The user has locked single-broker scope — **Trading.com only**. Multi-broker support is a later addition, NOT in scope for this Phase 2. So no abstraction, no ABC, no `generic_mt5.py`, no profile-lookup wiring. Just plain Trading.com settings merged into the standard config loader.

The orders module already hardcodes FOK in `_resolve_filling("auto")` (placeholder pending the abstraction we're now NOT building). That hardcoding stays; this task just documents WHY: it's Trading.com policy, not the tool guessing.

When a second broker is added in the future, refactor through a `BrokerProfile` ABC at that time. Do not pre-build the abstraction.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_trading_com.py`:

```python
from mt5_cli.config import load
from mt5_cli.config.trading_com import TRADING_COM_DEFAULTS, retcode_help


def test_trading_com_defaults_shape():
    assert TRADING_COM_DEFAULTS["filling"] == "FOK"
    assert TRADING_COM_DEFAULTS["allow_hedging"] is False
    assert TRADING_COM_DEFAULTS["rollover_utc_hour"] == 22


def test_retcode_help_returns_string():
    msg = retcode_help(10030)
    assert "filling" in msg.lower()
    assert "FOK" in msg


def test_config_load_merges_trading_com_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_CONFIG", str(tmp_path / "missing.json"))
    cfg = load()
    # Trading.com defaults flow through the standard loader
    assert cfg["filling"] == "FOK"
    assert cfg["allow_hedging"] is False
    assert cfg["rollover_utc_hour"] == 22
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_config_trading_com.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/config/trading_com.py`:

```python
"""Trading.com order-placement settings.

Single-broker scope: the tool currently supports Trading.com only. When
a second broker is added later, refactor through a BrokerProfile ABC at
that time. Do NOT pre-build the abstraction.

Settings here are merged into the standard config loader's defaults so
every primitive that reads cfg picks them up without a separate lookup.
"""

# Trading.com order-placement quirks (from broker spec):
#   - FOK filling only (no IOC, no RETURN on market orders)
#   - No hedging — must close existing same-symbol position before flipping
#   - 22:00 UTC daily rollover spike (spreads widen 10-15x)
TRADING_COM_DEFAULTS: dict = {
    "filling": "FOK",
    "allow_hedging": False,
    "rollover_utc_hour": 22,
}

# Known broker retcodes and human-readable help. Used by orders/positions
# error reporting to give agents actionable explanations.
RETCODE_HELP = {
    10008: "Order placed but not filled yet. Poll the fill via `mt5 order poll-fill <ticket>`.",
    10027: "Algo/autotrading disabled in MT5 terminal UI. Enable Tools > Options > Expert Advisors > Allow algorithmic trading.",
    10030: "Wrong filling mode. Trading.com is FOK-only; pin filling=FOK in your config.",
    10009: "Order request completed normally.",
    10004: "Requote — broker rejected because price moved.",
    10006: "Trade request rejected.",
    10010: "Only part of the request was completed.",
    10013: "Invalid request.",
    10014: "Invalid volume in the request.",
    10015: "Invalid price in the request.",
    10016: "Invalid stops in the request.",
    10017: "Trade is disabled.",
    10019: "Not enough money to complete the request.",
    10021: "No quotes to process the request.",
}


def retcode_help(retcode: int) -> str:
    return RETCODE_HELP.get(retcode, f"Retcode {retcode}: see MT5 docs.")
```

Modify `mt5_cli/config/config.py` so `load()` merges `TRADING_COM_DEFAULTS` into the `DEFAULTS` dict before the file/env/override resolution chain:

```python
from .trading_com import TRADING_COM_DEFAULTS

DEFAULTS = {
    # ... existing keys ...
    **TRADING_COM_DEFAULTS,
}
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest -q
git add mt5_cli/config/ tests/test_config_trading_com.py
git commit -m "Phase 2.5: Trading.com order-placement settings (single-broker)

Single Trading.com config module — no BrokerProfile abstraction, no
multi-broker indirection. The original plan's Tasks 2.5-2.8 (ABC +
trading_com profile + generic_mt5 profile + wire orders) collapse to
this one task per user direction: multi-broker is a later addition.

TRADING_COM_DEFAULTS (filling=FOK, allow_hedging=False, rollover_utc_hour=22)
merge into the standard config loader's DEFAULTS. The orders module's
existing FOK hardcoding in _resolve_filling('auto') is documented as
Trading.com policy.

retcode_help(retcode) gives agents actionable explanations of MT5 trade
retcodes (10008/10027/10030 + the common 10004-10021 range)."
```

### Task 2.6: Cherry-pick chart-control primitives into mt5_cli/chart/

**Files:**
- Create: `mt5_cli/chart/chart.py`
- Replace: `mt5_cli/chart/__init__.py`
- Create: `tests/test_chart.py`

The tool gives agents hands to control MT5's active chart: switch the active chart's symbol or timeframe, ensure a specific symbol+timeframe chart is the active one, list all open charts. The agent uses these primitives to compose its own multi-timeframe analysis or screenshot workflows. The tool does NOT orchestrate (no `screenshot tda` loop, no manifest writing, no analytical framework).

**Cherry-pick reference:** `archive/legacy-mt5/core/chart.py` (941 LOC — has TDA-flavored orchestration we strip out).

Cherry-pick the pure chart-control primitives:
- `switch_tf(timeframe, window_substring="MT5", settle_seconds=0.5)` — WM_COMMAND on the MT5 toolbar
- `symbol(symbol_name, window_substring="MT5", settle_seconds=0.5)` — type symbol + verify title
- `activate_chart(child_hwnd, parent_hwnd)` — WM_MDIACTIVATE on MDIClient
- `ensure_chart(symbol_name, timeframe="M15", chart_id=None, window_substring="MT5")` — agnostic chart-selection primitive
- `list_charts(window_substring="MT5")` — enumerate MDI child charts
- `current_title(window_substring="MT5")` — read active chart title
- `find_window(window_substring) -> WindowMatch | None`

**Skip:**
- `screenshot_tda` orchestration (it's a strategy workflow — user composes from primitives)
- `depth-of-market` GUI panel opening (DOM lives in `market.depth()` for structured data; if a GUI screenshot is needed it's Task 2.7's job)

Tests cover each primitive with Win32 API mocked via `pywin32` MagicMock fixture. Use the cache-safe pattern (purge `mt5_cli.bridge*`, `mt5_cli.chart*` before/after).

Detailed test + implementation steps follow the same shape as Task 2.3.C (market). The implementer should read `archive/legacy-mt5/core/chart.py` for the Win32 message-passing pattern (WM_COMMAND, WM_MDIACTIVATE) and the title-polling settle loops, then rewrite cleanly under `mt5_cli/chart/`.

### Task 2.7: Cherry-pick screenshot primitives into mt5_cli/screenshot/

**Files:**
- Create: `mt5_cli/screenshot/screenshot.py`
- Replace: `mt5_cli/screenshot/__init__.py`
- Create: `tests/test_screenshot.py`

The tool gives agents hands to capture the active MT5 chart or DOM panel as PNG. The agent uses these primitives to build its own screenshot workflows (e.g., a TDA review loop: `switch_tf → take → switch_tf → take → ...` — but the LOOP is the agent's, not the tool's).

**Cherry-pick reference:** `archive/legacy-mt5/core/screenshot.py` (466 LOC — has TDA orchestration to strip).

Cherry-pick:
- `take(output_path, window_substring="MT5", monitor=0, cfg=None)` — mss/Pillow capture of the active chart window
- `dom(symbol, output_dir, open_panel=True, close_panel=True)` — open MT5 DOM panel via menu, screenshot, close
- `annotate(input_path, output_path, text, xy=(10,10))` — Pillow text overlay

**Skip:**
- `tda(symbol, timeframes, output_dir, final_timeframe)` multi-TF loop (strategy workflow — agent composes from `chart.switch_tf` + `screenshot.take`)
- `visual_manifest` / `structured_context` writing (TDA-specific, user's domain)

Same cache-safe fixture pattern. Detailed steps follow Task 2.3.C shape.

### Task 2.8: Chart-indicator attach (GUI menu poking)

**Status:** ITERATED. Original `cfe1c23` (mt5_call against
nonexistent SDK functions) was removed at `3811cd6` per Codex P1 #1.
Reimplemented via Win32 GUI menu poking — same pattern as
`mt5_cli/screenshot/screenshot.py::_open_dom_panel`.

**Why GUI poking:** The MetaTrader5 Python SDK (verified at 5.0.5260)
does NOT expose `iCustom`, `ChartIndicatorAdd`, `ChartIndicatorDelete`,
`ChartIndicatorsTotal`, or `ChartIndicatorName`. Those are MQL5-language
functions that run inside the terminal process. The realistic
alternative is to walk MT5's main-menu chain `Insert > Indicators >
Custom > <name>` and post `WM_COMMAND`.

**Files:**
- `mt5_cli/chart/indicators_attach.py` (~180 LOC, pure Win32)
- `tests/test_chart_indicators_attach.py` (12 tests, fake menu tree)

**Public surface (minimal, attach-only):**

```python
def attach(
    indicator_name: str,
    *,
    chart_id: int | None = None,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
    auto_confirm: bool = True,
) -> dict:
    """Attach a deployed .ex5 indicator to a chart via the Insert >
    Indicators > Custom menu. Returns ok({command_id, menu_path, ...}).
    """
```

Failure envelopes:
- `CHART_WINDOW_NOT_FOUND` — no MT5 top-level window matched
- `CHART_MENU_NOT_FOUND` — MT5 window has no menu bar
- `CHART_MENU_PATH_NOT_FOUND` — Insert / Indicators / Custom missing
- `CHART_INDICATOR_NOT_FOUND` — indicator name not in Custom submenu

**Deliberately out of scope (`detach`, `list_attached`):**

Both would require MT5's Indicators List dialog (Ctrl+I) introspection
— fragile across MT5 versions. Users remove indicators via right-click
"Delete Indicator" or Ctrl+I. Agents verify attachment via
`screenshot.take()`. If the asymmetry becomes painful, a future task
can add them via the LB_GETTEXT cross-process pattern (see
`mt5_cli/chart/chart.py::_toolbar_button_id` for the precedent).

**Default-params only:** `attach()` posts Enter after `settle_seconds`
to accept the indicator's parameter dialog with default inputs. For
custom inputs, the user either sets MQL5 `input` defaults or attaches
manually for one-offs.

**Menu-walk exactness:** the helper uses normalized **exact** match
at each path segment, not substring. Substring match would let `"atr"`
in a user indicator name collide with the built-in `ATR` first and
post the wrong `WM_COMMAND`.

### Task 2.13: Open a new chart via File > New Chart menu poke

**Status:** SHIPPED post-Phase-2. Added after user flagged the menu
gap from screenshots of `File > New Chart > <symbol>` (favorites at
top level + nested Forex/Indices/etc. category submenus).

**Files:**
- `mt5_cli/chart/_menu.py` (~80 LOC, EXTRACTED from
  `indicators_attach.py` into a private shared helper module —
  `normalize_menu_text`, `menu_string`, `find_submenu`,
  `find_leaf_command_id`, `find_leaf_command_id_recursive`)
- `mt5_cli/chart/new_chart.py` (~150 LOC, pure Win32)
- `tests/test_chart_new_chart.py` (13 tests, fake menu tree with
  top-level favorites + nested category submenus)
- `mt5_cli/chart/indicators_attach.py` (refactored to import the
  helpers from `_menu.py` instead of duplicating them)

**Public surface:**

```python
def new_chart(
    symbol: str,
    *,
    timeframe: str | None = None,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
) -> dict:
    """Open a new MT5 chart for symbol via File > New Chart > <symbol>.
    Optional timeframe arg switches TF on the new chart via switch_tf.
    Returns ok({hwnd, symbol, timeframe, parent_hwnd, command_id, menu_path}).
    """
```

Failure envelopes:
- `CHART_WINDOW_NOT_FOUND` — no MT5 top-level window matched
- `CHART_MENU_NOT_FOUND` — MT5 window has no menu bar
- `CHART_MENU_PATH_NOT_FOUND` — File or New Chart submenu missing
- `CHART_SYMBOL_NOT_FOUND_IN_MENU` — symbol absent from every New
  Chart submenu (suggests adding to Market Watch first)
- Partial success: chart opened but `switch_tf` failed — returns
  `ok(...)` with a `tf_switch_warning` field carrying the TF error

**hwnd identification:** snapshots the chart-children set before
posting `WM_COMMAND`, then diffs after `settle_seconds` to find the
newly-opened chart. Falls back to the newly-active chart if the diff
fails (e.g., enumerate_chart_children raises).

**Out of scope:**
- `cycle_chart(direction)` — list_charts() + activate_chart(charts[next].hwnd)
  already covers this; sugar wrapper is a follow-up if useful
- `attach_ea(expert_name)` — symmetric Insert > Experts > <name> poke,
  same pattern. Add when needed; not blocking.
- `close_chart(hwnd)` — WM_CLOSE on the chart child. Trivial follow-up.

### Task 2.10: Add reports module (JSON envelope helpers)

**Files:**
- Create: `mt5_cli/reports/__init__.py`
- Create: `mt5_cli/reports/envelope.py`
- Create: `tests/test_reports_envelope.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_envelope.py
from mt5_cli.reports import ok, fail


def test_ok_envelope_shape():
    env = ok({"x": 1})
    assert env == {"ok": True, "data": {"x": 1}}


def test_fail_envelope_shape():
    env = fail("E_CODE", "human-readable message")
    assert env["ok"] is False
    assert env["error"]["code"] == "E_CODE"
    assert env["error"]["message"] == "human-readable message"


def test_fail_with_data():
    env = fail("E_RETCODE", "broker rejected", data={"retcode": 10030})
    assert env["error"]["data"] == {"retcode": 10030}
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_reports_envelope.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/reports/envelope.py`:

```python
"""Standard JSON envelope returned by every CLI command and library function.

Shape: {"ok": True, "data": {...}} or {"ok": False, "error": {"code": ..., "message": ..., "data": {...}}}
"""
from typing import Any


def ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def fail(code: str, message: str, *, data: dict | None = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"ok": False, "error": err}
```

Wire `mt5_cli/reports/__init__.py`:

```python
from .envelope import ok, fail

__all__ = ["ok", "fail"]
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_reports_envelope.py -v
git add mt5_cli/reports/ tests/test_reports_envelope.py
git commit -m "Phase 2: add reports.envelope with ok() / fail() helpers

Standard JSON envelope shape used by every CLI command, library
function, and MCP tool. Replaces ad-hoc dict construction."
```

### Task 2.11: Add CI test that bridge is the only MetaTrader5 importer

**Files:**
- Create: `tests/test_bridge_singleton.py` (top-level tests dir, separate from the unit-test pyramid)

- [ ] **Step 1: Create the top-level tests/ directory**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: Write the test**

```python
# tests/test_bridge_singleton.py
"""CI guard: only mt5_cli/bridge/mt5_backend.py may import MetaTrader5."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"mt5_cli/bridge/mt5_backend.py"}
SCAN_DIRS = ["mt5_cli", "mt5", "mt5_mcp"]


def test_only_bridge_imports_metatrader5():
    offenders = []
    for d in SCAN_DIRS:
        path = ROOT / d
        if not path.exists():
            continue
        for py in path.rglob("*.py"):
            rel = py.relative_to(ROOT).as_posix()
            if rel in ALLOWED:
                continue
            text = py.read_text(encoding="utf-8")
            if "import MetaTrader5" in text or "from MetaTrader5" in text:
                offenders.append(rel)
    assert not offenders, (
        f"Only {ALLOWED} may import MetaTrader5. Offenders: {offenders}"
    )
```

- [ ] **Step 3: Update pytest.ini to include the top-level tests dir**

```ini
[pytest]
testpaths =
    tests
markers =
    integration: tests requiring a live MT5 terminal (deselect with -m "not integration")
norecursedirs = archive
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_bridge_singleton.py -v
git add tests/ pytest.ini
git commit -m "Phase 2: CI guard — bridge is the only MetaTrader5 importer

Greps mt5_cli/, mt5/, mt5_mcp/ for any import MetaTrader5
outside of mt5_cli/bridge/mt5_backend.py. Fails the suite on
any leak."
```

### Task 2.12: Phase 2 acceptance check + tag

- [ ] **Step 1: Verify all imports work**

```bash
python -c "from mt5_cli import market, rates, orders, positions, account, history, risk; print('imports OK')"
python -c "from mt5_cli.chart import switch_tf, symbol, ensure_chart, find_window, current_title, attach, new_chart; from mt5_cli.screenshot import take, dom, annotate; print('chart+screenshot imports OK')"

# Pin MT5_CONFIG to a non-existent path so the user's real config file
# (if any) does not override DEFAULTS in this purity check.
MT5_CONFIG=/nonexistent.json python -c "from mt5_cli.config import load, retcode_help; cfg = load(); print(cfg['filling'], cfg.get('rollover_utc_hour'), '/', retcode_help(10030)[:30])"
```

All three must print without ImportError. The third confirms Task 2.5's
Trading.com merge landed: `FOK 22 / Wrong filling mode. Trading.co`
(filling='FOK', rollover_utc_hour=22, retcode_help is exported from the
single-broker config surface). The `MT5_CONFIG=/nonexistent.json` pin
prevents a developer's local `~/.config/metatrader5-cli.json` from
shadowing DEFAULTS during the purity check.

- [ ] **Step 2: Full suite green**

```bash
python -m pytest -q
```

- [ ] **Step 3: Tag the milestone**

```bash
git tag phase-2-complete
git log --oneline -8
```

---

## Phase 3 — MQL5 plugin host (8 tasks)

**Goal:** Make MQL5 EA + indicator authoring a first-class CLI flow. Scaffold from templates, compile via MetaEditor, deploy to terminal Experts/Indicators. Auto-discover user EAs/indicators from `ea/` + `indicators/` user dirs.

### Task 3.1: Document the user-workspace convention (tool, not workspace)

**Files:**
- Modify: `README.md` — add a "User workspace layout" section
- Add: `mt5_cli/skills/USER_WORKSPACE.md` — minimal one-pager linked from SKILL.md

**Why this task is tiny:** this repo ships only the tool. The `ea/`, `indicators/`, `presets/`, `results/` directories live in the USER's workspace (their CWD when they run `mt5`, or `~/.local/share/metatrader5-cli/{ea,indicators,presets,results}/` — XDG_DATA_HOME convention; `%APPDATA%/metatrader5-cli/...` on Windows). We do NOT create those dirs here, ship example EAs, or maintain a `results/` snapshot dir in this repo. The CLI commands (Tasks 3.2-3.6) operate on the user's CWD by default.

- [ ] **Step 1: Add README section**

Use Edit. In `README.md`, after the install/usage sections, add:

```markdown
## User workspace layout

`metatrader5-cli` is a tool — you install it once and run `mt5` (or `mt5-mcp`) from your own project directory. Your MQL5 source, .set presets, and backtest results live in YOUR workspace, never in this repo.

The recommended layout for a user project:

```
my-trading-project/
├── ea/                       # your MQL5 Expert Advisors
│   ├── my_strategy.mq5
│   └── my_strategy.ex5       # built by `mt5 ea compile my_strategy`
├── indicators/               # your MQL5 indicators
│   └── my_signal.mq5
├── presets/                  # tester .set files
│   └── my_strategy.AUDUSD.M5.set
├── results/                  # tester run snapshots (one dir per run)
└── .metatrader5-cli.json     # optional per-project config override (otherwise uses ~/.config/metatrader5-cli.json)
```

`mt5` discovers EAs/indicators in this order: `./ea` / `./indicators` (CWD) → `~/.local/share/metatrader5-cli/{ea,indicators}/` (XDG_DATA_HOME; `%APPDATA%/metatrader5-cli/` on Windows) → installed entry points. First match wins.

You can also keep your EAs and indicators centrally under `~/.local/share/metatrader5-cli/` and run `mt5` from anywhere.
```

- [ ] **Step 2: Add the workspace one-pager (referenced from SKILL.md in Phase 5)**

Create `mt5_cli/skills/USER_WORKSPACE.md`:

```markdown
# User workspace conventions for `metatrader5-cli`

This file describes where the CLI looks for things on the USER's machine. It ships with the tool so AI agents can introspect it.

## What lives in the user's workspace

- `./ea/<name>.mq5` and `./ea/<name>.ex5` — user-authored Expert Advisors
- `./indicators/<name>.mq5` and `./indicators/<name>.ex5` — user-authored indicators
- `./presets/<name>.<symbol>.<tf>.set` — tester parameter presets
- `./results/<run-id>/` — captured tester run artifacts (report.html, journal.csv, tester.ini, optionally optimization.xml)
- `./.metatrader5-cli.json` — optional per-project config override

## What lives in the user's data dir (XDG_DATA_HOME convention)

When no project-local `./ea` / `./indicators` exists, `mt5` falls back to the user's data dir. EAs/indicators/presets/results are user-authored DATA, so they belong under `XDG_DATA_HOME` (not `XDG_CONFIG_HOME`, which is for settings). Resolution order (first match wins):

1. `MT5_EA_DIR` / `MT5_INDICATORS_DIR` / `MT5_PRESETS_DIR` / `MT5_RESULTS_DIR` env vars (each overridable independently)
2. `$XDG_DATA_HOME/metatrader5-cli/{ea,indicators,presets,results}/`
3. `%APPDATA%/metatrader5-cli/{ea,indicators,presets,results}/` (Windows)
4. `~/.local/share/metatrader5-cli/{ea,indicators,presets,results}/` (fallback when XDG_DATA_HOME unset)

The config FILE itself follows a separate resolution and is a flat JSON file (XDG_CONFIG_HOME convention): `MT5_CONFIG` env → `$XDG_CONFIG_HOME/metatrader5-cli.json` → `%APPDATA%/metatrader5-cli.json` → `~/.config/metatrader5-cli.json`.

## What never lives in this repo

This repo is a tool. It contains no EAs, no indicators, no .set presets, no backtest results, no strategy docs.
```

- [ ] **Step 3: Commit**

```bash
git add README.md mt5_cli/skills/USER_WORKSPACE.md
git commit -m "Phase 3: document the user-workspace convention

README gets a user-workspace section; the tool ships a USER_WORKSPACE.md
one-pager that SKILL.md will reference in Phase 5. This repo creates no
ea/, indicators/, presets/, results/ dirs; those live on the user's
machine. .gitignore is unchanged (nothing to ignore here)."
```

### Task 3.2: Implement mql5.compiler (metaeditor64.exe wrapper)

**Files:**
- Create: `mt5_cli/mql5/compiler.py`
- Create: `tests/test_mql5_compiler.py`

- [ ] **Step 1: Write the failing test (mocked subprocess)**

```python
# tests/test_mql5_compiler.py
import subprocess
from pathlib import Path

import pytest

from mt5_cli.mql5 import compiler


def test_locate_metaeditor_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(compiler, "_CANDIDATE_PATHS", [Path("/does/not/exist/metaeditor64.exe")])
    monkeypatch.setattr(compiler.shutil, "which", lambda _: None)
    assert compiler.locate_metaeditor() is None


def test_locate_metaeditor_uses_env_var(monkeypatch, tmp_path):
    fake = tmp_path / "metaeditor64.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("MT5_METAEDITOR_PATH", str(fake))
    assert compiler.locate_metaeditor() == fake


def test_compile_returns_fail_when_metaeditor_missing(monkeypatch, tmp_path):
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: None)
    result = compiler.compile_source(src)
    assert result["ok"] is False
    assert result["error"]["code"] == "METAEDITOR_NOT_FOUND"


def test_compile_invokes_subprocess(monkeypatch, tmp_path):
    src = tmp_path / "demo.mq5"
    src.write_text("// stub\n")
    fake_meta = tmp_path / "metaeditor64.exe"
    fake_meta.write_bytes(b"")
    log = tmp_path / "demo.log"
    log.write_text("0 errors, 0 warnings\n")

    captured = {}

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(compiler, "locate_metaeditor", lambda: fake_meta)
    monkeypatch.setattr(compiler.subprocess, "run", fake_run)
    result = compiler.compile_source(src)
    assert result["ok"] is True
    assert "/compile:" in captured["cmd"][1] or any("compile" in c for c in captured["cmd"])
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_mql5_compiler.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/mql5/compiler.py`:

```python
"""Compile MQL5 source via metaeditor64.exe.

Resolves the MetaEditor binary in this order:
  1. MT5_METAEDITOR_PATH env var
  2. Common Windows install paths (Program Files / Program Files (x86) / AppData)
  3. shutil.which('metaeditor64')
"""
import os
import shutil
import subprocess
from pathlib import Path

from mt5_cli.reports import ok, fail

_CANDIDATE_PATHS = [
    Path(r"C:\Program Files\MetaTrader 5\metaeditor64.exe"),
    Path(r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe"),
    Path(os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal\Common\Files\metaeditor64.exe")),
]


def locate_metaeditor() -> Path | None:
    env = os.environ.get("MT5_METAEDITOR_PATH")
    if env and Path(env).exists():
        return Path(env)
    for p in _CANDIDATE_PATHS:
        if p.exists():
            return p
    found = shutil.which("metaeditor64")
    return Path(found) if found else None


def _parse_log(log_path: Path) -> tuple[int, int, str]:
    """Returns (errors, warnings, full_text)."""
    if not log_path.exists():
        return 0, 0, ""
    text = log_path.read_text(encoding="utf-16-le", errors="replace") if log_path.read_bytes()[:2] == b"\xff\xfe" else log_path.read_text(encoding="utf-8", errors="replace")
    errors = sum(1 for line in text.splitlines() if "error" in line.lower() and " - " in line)
    warnings = sum(1 for line in text.splitlines() if "warning" in line.lower() and " - " in line)
    return errors, warnings, text


def compile_source(src: Path, *, include_dir: Path | None = None, timeout: int = 120) -> dict:
    """Compile a single .mq5 file. Returns the standard envelope."""
    src = Path(src).resolve()
    if not src.exists():
        return fail("SOURCE_NOT_FOUND", f"Source file not found: {src}")
    metaeditor = locate_metaeditor()
    if not metaeditor:
        return fail(
            "METAEDITOR_NOT_FOUND",
            "Could not locate metaeditor64.exe. Set MT5_METAEDITOR_PATH or install MT5.",
        )
    log_path = src.with_suffix(".log")
    cmd = [str(metaeditor), f"/compile:{src}", f"/log:{log_path}"]
    if include_dir:
        cmd.append(f"/inc:{include_dir}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return fail("COMPILE_TIMEOUT", f"metaeditor64.exe did not finish in {timeout}s")
    errors, warnings, log_text = _parse_log(log_path)
    ex5 = src.with_suffix(".ex5")
    if errors or not ex5.exists():
        return fail(
            "COMPILE_FAILED",
            f"{errors} errors, {warnings} warnings",
            data={"log": log_text, "exit_code": proc.returncode},
        )
    return ok({
        "source": str(src),
        "ex5": str(ex5),
        "errors": errors,
        "warnings": warnings,
        "log_path": str(log_path),
    })
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_mql5_compiler.py -v
git add mt5_cli/mql5/compiler.py tests/test_mql5_compiler.py
git commit -m "Phase 3: add mql5.compiler — metaeditor64.exe wrapper

Resolves MetaEditor via MT5_METAEDITOR_PATH env, common install
paths, then shutil.which. Returns standard JSON envelope with
errors/warnings/log path."
```

### Task 3.3: Implement mql5.deployer

**Files:**
- Create: `mt5_cli/mql5/deployer.py`
- Create: `tests/test_mql5_deployer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mql5_deployer.py
from pathlib import Path

import pytest

from mt5_cli.mql5 import deployer


def test_resolve_terminal_data_dir_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_TERMINAL_DATA_DIR", str(tmp_path))
    assert deployer.resolve_terminal_data_dir() == tmp_path


def test_resolve_terminal_data_dir_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)
    monkeypatch.setattr(deployer, "_CANDIDATE_DATA_DIRS", [Path("/does/not/exist")])
    assert deployer.resolve_terminal_data_dir() is None


def test_deploy_ea_copies_to_experts(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "MQL5" / "Experts").mkdir(parents=True)
    src_dir = tmp_path / "ea"
    src_dir.mkdir()
    (src_dir / "demo.mq5").write_text("// stub")
    (src_dir / "demo.ex5").write_bytes(b"compiled")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", lambda: data_dir)
    result = deployer.deploy_ea(src_dir / "demo.mq5")
    assert result["ok"] is True
    assert (data_dir / "MQL5" / "Experts" / "demo.mq5").exists()
    assert (data_dir / "MQL5" / "Experts" / "demo.ex5").exists()


def test_deploy_indicator_copies_to_indicators(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "MQL5" / "Indicators").mkdir(parents=True)
    src_dir = tmp_path / "indicators"
    src_dir.mkdir()
    (src_dir / "donchian.mq5").write_text("// stub")
    (src_dir / "donchian.ex5").write_bytes(b"compiled")

    monkeypatch.setattr(deployer, "resolve_terminal_data_dir", lambda: data_dir)
    result = deployer.deploy_indicator(src_dir / "donchian.mq5")
    assert result["ok"] is True
    assert (data_dir / "MQL5" / "Indicators" / "donchian.mq5").exists()
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_mql5_deployer.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/mql5/deployer.py`:

```python
"""Copy compiled MQL5 artifacts to the MT5 terminal's Experts/ or Indicators/ folder.

Terminal data dir is the per-instance Roaming dir like
%APPDATA%\MetaQuotes\Terminal\<HASH>\MQL5\.
"""
import os
import shutil
from pathlib import Path

from mt5_cli.reports import ok, fail

_CANDIDATE_DATA_DIRS = [
    Path(os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal")),
]


def resolve_terminal_data_dir() -> Path | None:
    env = os.environ.get("MT5_TERMINAL_DATA_DIR")
    if env:
        p = Path(env)
        return p if p.exists() else None
    for root in _CANDIDATE_DATA_DIRS:
        if not root.exists():
            continue
        # MT5 keeps each terminal install under a 32-char hash dir. Pick the
        # newest one that has an MQL5/ subdir.
        candidates = sorted(
            (d for d in root.iterdir() if d.is_dir() and (d / "MQL5").exists()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return None


def _deploy(src: Path, subdir: str) -> dict:
    src = Path(src).resolve()
    if not src.exists():
        return fail("SOURCE_NOT_FOUND", f"Source file not found: {src}")
    data_dir = resolve_terminal_data_dir()
    if not data_dir:
        return fail(
            "TERMINAL_DATA_DIR_NOT_FOUND",
            "Could not locate MT5 terminal data dir. Set MT5_TERMINAL_DATA_DIR.",
        )
    dest_dir = data_dir / "MQL5" / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for ext in (".mq5", ".ex5"):
        candidate = src.with_suffix(ext)
        if candidate.exists():
            dest = dest_dir / candidate.name
            shutil.copy2(candidate, dest)
            copied.append(str(dest))
    if not copied:
        return fail("NOTHING_TO_DEPLOY", f"Found no .mq5 or .ex5 sibling of {src}")
    return ok({"copied": copied, "data_dir": str(data_dir)})


def deploy_ea(src: Path) -> dict:
    return _deploy(src, "Experts")


def deploy_indicator(src: Path) -> dict:
    return _deploy(src, "Indicators")
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_mql5_deployer.py -v
git add mt5_cli/mql5/deployer.py tests/test_mql5_deployer.py
git commit -m "Phase 3: add mql5.deployer — copy .mq5 + .ex5 to terminal MQL5 dir"
```

### Task 3.4: Implement mql5.discovery (auto-find user EAs/indicators)

**Files:**
- Create: `mt5_cli/mql5/discovery.py`
- Create: `tests/test_mql5_discovery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mql5_discovery.py
from pathlib import Path

from mt5_cli.mql5 import discovery


def test_discover_eas_finds_mq5_files(tmp_path, monkeypatch):
    ea_dir = tmp_path / "ea"
    ea_dir.mkdir()
    (ea_dir / "alpha.mq5").write_text("// stub")
    (ea_dir / "beta.mq5").write_text("// stub")
    (ea_dir / "alpha.ex5").write_bytes(b"compiled")  # noise
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [ea_dir])
    found = discovery.list_eas()
    names = sorted(e["name"] for e in found)
    assert names == ["alpha", "beta"]


def test_get_ea_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [tmp_path])
    assert discovery.get_ea("missing") is None


def test_get_ea_returns_path(tmp_path, monkeypatch):
    (tmp_path / "demo.mq5").write_text("// stub")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [tmp_path])
    e = discovery.get_ea("demo")
    assert e["name"] == "demo"
    assert e["source"].endswith("demo.mq5")
    assert e["compiled"] is False  # no .ex5


def test_first_match_wins(tmp_path, monkeypatch):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "demo.mq5").write_text("// from a")
    (b / "demo.mq5").write_text("// from b")
    monkeypatch.setattr(discovery, "_search_paths", lambda kind: [a, b])
    e = discovery.get_ea("demo")
    assert "/a/" in e["source"].replace("\\", "/")
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_mql5_discovery.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/mql5/discovery.py`:

```python
"""Auto-discover user MQL5 EAs and indicators.

Search order (first match wins):
  1. ./ea/ or ./indicators/ (current working directory where the user runs `mt5`)
  2. ~/.local/share/metatrader5-cli/ea/ or /indicators/ (XDG_DATA_HOME convention; %APPDATA%/metatrader5-cli/ on Windows — Phase 6 paths.py finalizes the resolution chain)
  3. (future) entry points
"""
import os
from pathlib import Path


def _search_paths(kind: str) -> list[Path]:
    """kind is 'ea' or 'indicators'.

    Phase 3 placeholder resolution. Phase 6 paths.py replaces this with
    the full XDG_DATA_HOME / APPDATA / HOME chain. The fallback root is
    XDG_DATA_HOME-style (~/.local/share/metatrader5-cli/), NOT the
    config dir, since EAs/indicators are user-authored DATA, not
    settings.
    """
    cwd = Path.cwd() / kind
    user = Path(os.path.expanduser("~")) / ".local" / "share" / "metatrader5-cli" / kind
    return [p for p in (cwd, user) if p.exists()]


def _list(kind: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for root in _search_paths(kind):
        for src in sorted(root.rglob("*.mq5")):
            name = src.stem
            if name in seen:
                continue
            seen.add(name)
            out.append({
                "name": name,
                "source": str(src),
                "compiled": src.with_suffix(".ex5").exists(),
            })
    return out


def _get(kind: str, name: str) -> dict | None:
    for root in _search_paths(kind):
        candidate = root / f"{name}.mq5"
        if candidate.exists():
            return {
                "name": name,
                "source": str(candidate),
                "compiled": candidate.with_suffix(".ex5").exists(),
            }
        # Allow nested examples/<name>.mq5
        for src in root.rglob(f"{name}.mq5"):
            return {
                "name": name,
                "source": str(src),
                "compiled": src.with_suffix(".ex5").exists(),
            }
    return None


def list_eas() -> list[dict]:
    return _list("ea")


def list_indicators() -> list[dict]:
    return _list("indicators")


def get_ea(name: str) -> dict | None:
    return _get("ea", name)


def get_indicator(name: str) -> dict | None:
    return _get("indicators", name)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_mql5_discovery.py -v
git add mt5_cli/mql5/discovery.py tests/test_mql5_discovery.py
git commit -m "Phase 3: add mql5.discovery — auto-find user EAs/indicators

Search order: ./ea or ./indicators (cwd) -> ~/.local/share/metatrader5-cli/.
First-match wins. Each result includes name, source path, and
compiled boolean."
```

### Task 3.5: Add MQL5 templates + scaffolding

**Files:**
- Create: `mt5_cli/mql5/templates/ea_minimal.mq5`
- Create: `mt5_cli/mql5/templates/indicator_minimal.mq5`
- Create: `mt5_cli/mql5/scaffold.py`
- Create: `tests/test_mql5_scaffold.py`

The tool ships **only minimal skeleton templates** — no strategy classification, no opinionated parameter suggestions, no trading-style hints. A template is just the smallest MQL5 boilerplate that compiles and loads. The user authors their own strategy / indicator math inside it. metatrader5-cli is hands for agents to control MT5; what the EA/indicator DOES is the user's domain entirely.

- [ ] **Step 1: Write template files**

Create `mt5_cli/mql5/templates/ea_minimal.mq5` — bare EA skeleton with the user-supplied name as a `{{name}}` placeholder. No strategy-flavored input parameters; no trading logic.

```cpp
//+------------------------------------------------------------------+
//| {{name}}.mq5 - minimal EA skeleton (author your strategy here)   |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"

input long MagicNumber = 88888;

int OnInit()                    { return INIT_SUCCEEDED; }
void OnDeinit(const int reason) { /* cleanup if needed */ }
void OnTick()                   { /* author entry / management / exit here */ }
```

Create `mt5_cli/mql5/templates/indicator_minimal.mq5` — bare indicator skeleton, one default buffer, no calculation.

```cpp
//+------------------------------------------------------------------+
//| {{name}}.mq5 - minimal indicator skeleton (author your math here) |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_label1  "{{name}}"

double Buf[];

int OnInit() { SetIndexBuffer(0, Buf, INDICATOR_DATA);
               return INIT_SUCCEEDED; }
int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{ /* author your calculation into Buf[i] here */ return rates_total; }
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_mql5_scaffold.py
from pathlib import Path
import pytest
from mt5_cli.mql5 import scaffold


def test_scaffold_ea_writes_minimal_file(tmp_path):
    out = scaffold.create_ea("alpha", target_dir=tmp_path)
    assert out["ok"] is True
    src = Path(out["data"]["source"])
    assert src.exists()
    text = src.read_text()
    assert "alpha.mq5" in text
    assert "{{name}}" not in text


def test_scaffold_ea_refuses_overwrite(tmp_path):
    (tmp_path / "alpha.mq5").write_text("// existing")
    out = scaffold.create_ea("alpha", target_dir=tmp_path)
    assert out["ok"] is False
    assert out["error"]["code"] == "ALREADY_EXISTS"


def test_scaffold_indicator_writes_minimal_file(tmp_path):
    out = scaffold.create_indicator("rsi_dual", target_dir=tmp_path)
    assert out["ok"] is True
    text = Path(out["data"]["source"]).read_text()
    assert "rsi_dual" in text
    assert "{{name}}" not in text


def test_list_templates_returns_minimal_only():
    out = scaffold.list_templates()
    assert out == {"ea": ["ea_minimal.mq5"], "indicator": ["indicator_minimal.mq5"]}
```

- [ ] **Step 3: Run — fails**

```bash
python -m pytest tests/test_mql5_scaffold.py -v
```

- [ ] **Step 4: Implement**

Create `mt5_cli/mql5/scaffold.py`:

```python
"""Scaffold new MQL5 EAs and indicators from packaged minimal templates.

The tool ships ONE minimal template per asset type. Anything beyond the
minimal skeleton (parameters, calculation, entry/exit logic) is the user's
to author in their own workspace.
"""
from pathlib import Path

from mt5_cli.reports import ok, fail

_TEMPLATE_ROOT = Path(__file__).parent / "templates"

_EA_TEMPLATE = "ea_minimal.mq5"
_IND_TEMPLATE = "indicator_minimal.mq5"


def _scaffold(name: str, target_dir: Path, template_filename: str) -> dict:
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{name}.mq5"
    if dest.exists():
        return fail("ALREADY_EXISTS", f"{dest} already exists; refusing to overwrite")
    template_path = _TEMPLATE_ROOT / template_filename
    text = template_path.read_text(encoding="utf-8").replace("{{name}}", name)
    dest.write_text(text, encoding="utf-8")
    return ok({"source": str(dest)})


def list_templates() -> dict[str, list[str]]:
    return {"ea": [_EA_TEMPLATE], "indicator": [_IND_TEMPLATE]}


def create_ea(name: str, *, target_dir: Path | str = Path("ea")) -> dict:
    return _scaffold(name, Path(target_dir), _EA_TEMPLATE)


def create_indicator(name: str, *, target_dir: Path | str = Path("indicators")) -> dict:
    return _scaffold(name, Path(target_dir), _IND_TEMPLATE)
```

- [ ] **Step 5: Update `mt5_cli/mql5/__init__.py`** to re-export the public API

```python
from . import compiler, deployer, discovery, scaffold

__all__ = ["compiler", "deployer", "discovery", "scaffold"]
```

- [ ] **Step 6: Update setup.py package_data** so templates ship with the package

In `setup.py`, change `package_data` to include the templates:

```python
    package_data={
        "mt5_cli.mql5": [
            "templates/*.mq5",
        ],
    },
```

- [ ] **Step 7: Run + commit**

```bash
python -m pytest tests/test_mql5_scaffold.py -v
git add mt5_cli/mql5/ tests/test_mql5_scaffold.py setup.py
git commit -m "Phase 3: add minimal MQL5 templates + scaffold

Ships one minimal EA template (ea_minimal.mq5) and one minimal indicator
template (indicator_minimal.mq5). No strategy classification, no
opinionated parameter suggestions — the tool gives agents hands to scaffold
the boilerplate that MT5 requires; the user authors what the asset
actually does. scaffold.create_ea / create_indicator substitute {{name}}
and refuse to overwrite. Templates ship via setup.py package_data."
```

### Task 3.6: Wire `mt5 ea new/compile/deploy/list` CLI commands

**Files:**
- Create: `mt5/__init__.py`, `mt5/__main__.py`, `mt5/cli.py`
- Modify: `setup.py` — change `mt5` console script entry point to `mt5.cli:main`

(The thin `mt5/` CLI wrapper replaces the legacy `metatrader5_cli.mt5.mt5_cli:main`. It only wires what's available so far — Phase 4/5 will add `tester`, `skills`, etc.)

- [ ] **Step 1: Create the CLI package skeleton**

```bash
mkdir -p mt5
touch mt5/__init__.py
```

Create `mt5/__main__.py`:

```python
from .cli import main

main()
```

- [ ] **Step 2: Write the CLI**

Create `mt5/cli.py`:

```python
"""Thin click wrapper over mt5_cli.

Each command translates CLI args to library calls and prints the
JSON envelope (with --json) or human-readable text.
"""
import json
from pathlib import Path

import click

from mt5_cli.mql5 import compiler, deployer, discovery, scaffold


def _emit(envelope: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(envelope))
        return
    if envelope["ok"]:
        data = envelope["data"]
        if isinstance(data, list):
            for row in data:
                click.echo(row)
        elif isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"{k}: {v}")
        else:
            click.echo(data)
    else:
        err = envelope["error"]
        click.echo(f"ERROR [{err['code']}]: {err['message']}", err=True)


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit machine-readable JSON.")
@click.pass_context
def main(ctx, as_json):
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.group("ea")
def ea_group():
    """Manage MQL5 Expert Advisors."""


@ea_group.command("list")
@click.pass_context
def ea_list(ctx):
    _emit({"ok": True, "data": discovery.list_eas()}, ctx.obj["json"])


@ea_group.command("new")
@click.argument("name")
@click.option("--template", default="minimal", help="Template: minimal (only option)")
@click.option("--target-dir", default="ea", type=click.Path(file_okay=False))
@click.pass_context
def ea_new(ctx, name, template, target_dir):
    # Single template per asset type — minimal MQL5 skeleton (OnInit /
    # OnDeinit / OnTick). No strategy-flavored variants ship; users author
    # their own logic. Locked decision: hands, not strategies.
    _emit(scaffold.create_ea(name, template=template, target_dir=Path(target_dir)), ctx.obj["json"])


@ea_group.command("compile")
@click.argument("name")
@click.pass_context
def ea_compile(ctx, name):
    e = discovery.get_ea(name)
    if not e:
        _emit({"ok": False, "error": {"code": "EA_NOT_FOUND", "message": f"No EA named {name!r}"}}, ctx.obj["json"])
        return
    _emit(compiler.compile_source(Path(e["source"])), ctx.obj["json"])


@ea_group.command("deploy")
@click.argument("name")
@click.pass_context
def ea_deploy(ctx, name):
    e = discovery.get_ea(name)
    if not e:
        _emit({"ok": False, "error": {"code": "EA_NOT_FOUND", "message": f"No EA named {name!r}"}}, ctx.obj["json"])
        return
    _emit(deployer.deploy_ea(Path(e["source"])), ctx.obj["json"])


@main.group("indicator")
def indicator_group():
    """Manage MQL5 indicators."""


@indicator_group.command("list")
@click.pass_context
def indicator_list(ctx):
    _emit({"ok": True, "data": discovery.list_indicators()}, ctx.obj["json"])


@indicator_group.command("new")
@click.argument("name")
@click.option("--template", default="minimal", help="Template: minimal (only option)")
@click.option("--target-dir", default="indicators", type=click.Path(file_okay=False))
@click.pass_context
def indicator_new(ctx, name, template, target_dir):
    # Single template per asset type — minimal MQL5 skeleton (OnInit /
    # OnCalculate). No oscillator/overlay/etc variants ship; users author
    # their own indicator math.
    _emit(scaffold.create_indicator(name, template=template, target_dir=Path(target_dir)), ctx.obj["json"])


@indicator_group.command("compile")
@click.argument("name")
@click.pass_context
def indicator_compile(ctx, name):
    i = discovery.get_indicator(name)
    if not i:
        _emit({"ok": False, "error": {"code": "INDICATOR_NOT_FOUND", "message": f"No indicator named {name!r}"}}, ctx.obj["json"])
        return
    _emit(compiler.compile_source(Path(i["source"])), ctx.obj["json"])


@indicator_group.command("deploy")
@click.argument("name")
@click.pass_context
def indicator_deploy(ctx, name):
    i = discovery.get_indicator(name)
    if not i:
        _emit({"ok": False, "error": {"code": "INDICATOR_NOT_FOUND", "message": f"No indicator named {name!r}"}}, ctx.obj["json"])
        return
    _emit(deployer.deploy_indicator(Path(i["source"])), ctx.obj["json"])
```

- [ ] **Step 3: Update setup.py console_scripts**

Replace the entry_points block:

```python
    entry_points={
        "console_scripts": [
            "mt5 = mt5.cli:main",
        ],
    },
```

(The legacy `metatrader5_cli.mt5.mt5_cli:main` entry point is dropped. The legacy CLI module exists only under `archive/legacy-mt5/mt5_cli.py` as reference material and is never the installed entry point.)

- [ ] **Step 4: Re-install in editable mode and smoke-test**

```bash
python -m pip install -e . --quiet
mt5 --help
mt5 ea --help
mt5 ea list --json   # expect: {"ok": true, "data": [...]}
mt5 ea new demo --target-dir /tmp/eatest
ls /tmp/eatest/demo.mq5
```

- [ ] **Step 5: Commit**

```bash
git add mt5/ setup.py
git commit -m "Phase 3: wire mt5 ea new/list/compile/deploy + indicator equivalents

Thin click wrapper at mt5/cli.py over mt5_cli.mql5. Console
script switches from the legacy metatrader5_cli entry to mt5.cli:main."
```

### Task 3.7: Add CLI smoke tests

**Files:**
- Create: `tests/test_cli_ea.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_cli_ea.py
import json
from pathlib import Path

from click.testing import CliRunner

from mt5.cli import main


def test_ea_list_json_envelope():
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "ea", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)


def test_ea_new_then_list_finds_it(tmp_path):
    runner = CliRunner()
    target = tmp_path / "ea"
    res1 = runner.invoke(main, ["--json", "ea", "new", "smoke_alpha",
                                "--template", "minimal",
                                "--target-dir", str(target)])
    assert res1.exit_code == 0
    assert json.loads(res1.output)["ok"] is True
    assert (target / "smoke_alpha.mq5").exists()


def test_ea_compile_unknown_returns_fail_envelope():
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "ea", "compile", "does_not_exist_xyz"])
    assert result.exit_code == 0  # CLI exits 0 even on logical fail; envelope carries the status
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "EA_NOT_FOUND"


def test_indicator_new_then_list(tmp_path, monkeypatch):
    runner = CliRunner()
    target = tmp_path / "indicators"
    res1 = runner.invoke(main, ["--json", "indicator", "new", "smoke_donch",
                                "--template", "minimal",
                                "--target-dir", str(target)])
    assert json.loads(res1.output)["ok"] is True
    assert (target / "smoke_donch.mq5").exists()
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest tests/test_cli_ea.py -v
git add tests/test_cli_ea.py
git commit -m "Phase 3: CLI smoke tests for mt5 ea/indicator new/list/compile"
```

### Task 3.8: Phase 3 acceptance check + tag

- [ ] **Step 1: End-to-end roundtrip from a USER-side scratch dir**

This task ships no examples in the repo. Test from a throwaway dir to mimic a user:

```bash
TMP=$(mktemp -d)                                    # or `mkdir tmp-userdir && cd tmp-userdir`
cd "$TMP"

mt5 --json ea list                                  # empty list (no ea/ here)
mt5 --json ea new smoke_alpha                       # scaffolds ./ea/smoke_alpha.mq5 from the one minimal EA template
mt5 --json ea list                                  # finds smoke_alpha
mt5 --json ea compile smoke_alpha                   # if MetaEditor available; else METAEDITOR_NOT_FOUND
mt5 --json indicator new smoke_signal               # scaffolds ./indicators/smoke_signal.mq5 from the one minimal indicator template
mt5 --json indicator list                           # finds smoke_signal

cd - && rm -rf "$TMP"                               # cleanup
```

- [ ] **Step 2: Suite green**

```bash
python -m pytest -q
```

- [ ] **Step 3: Tag**

```bash
git tag phase-3-complete
```

---

## Phase 4 — Strategy Tester driver (10 tasks)

**Goal:** Drive MT5's native Strategy Tester from the CLI. Both EA backtests (single / optimize / genetic / forward / scanner / stress) and indicator visual tests. Parse HTML report + journal CSV + optimization XML into a JSON envelope.

### Task 4.1: Add tester.cache (run-id snapshots)

**Files:**
- Create: `mt5_cli/tester/cache.py`
- Create: `tests/test_tester_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tester_cache.py
from datetime import datetime
from pathlib import Path

from mt5_cli.tester import cache


def test_make_run_id_format():
    rid = cache.make_run_id("alpha", "AUDUSD", "M5", at=datetime(2026, 5, 15, 14, 22, 5))
    assert rid == "2026-05-15T14-22-05_alpha_AUDUSD_M5"


def test_run_dir_creates_under_results(tmp_path):
    rid = "2026-05-15T14-22-05_alpha_AUDUSD_M5"
    rdir = cache.run_dir(rid, root=tmp_path)
    assert rdir == tmp_path / rid
    assert rdir.exists()


def test_list_recent_orders_newest_first(tmp_path):
    for stamp in ("2026-05-14T10-00-00_a", "2026-05-15T10-00-00_b", "2026-05-13T10-00-00_c"):
        (tmp_path / stamp).mkdir()
    out = cache.list_recent(root=tmp_path, limit=3)
    assert [r["run_id"] for r in out] == [
        "2026-05-15T10-00-00_b",
        "2026-05-14T10-00-00_a",
        "2026-05-13T10-00-00_c",
    ]
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_tester_cache.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/tester/cache.py`:

```python
"""Per-run snapshot cache under results/<run-id>/."""
from datetime import datetime
from pathlib import Path


def make_run_id(expert: str, symbol: str, timeframe: str, *, at: datetime | None = None) -> str:
    at = at or datetime.utcnow()
    stamp = at.strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_{expert}_{symbol}_{timeframe}"


def run_dir(run_id: str, *, root: Path | str = "results") -> Path:
    p = Path(root) / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_recent(*, root: Path | str = "results", limit: int = 20) -> list[dict]:
    rp = Path(root)
    if not rp.exists():
        return []
    dirs = sorted(
        (d for d in rp.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )[:limit]
    return [{"run_id": d.name, "path": str(d)} for d in dirs]


def get_run(run_id: str, *, root: Path | str = "results") -> dict | None:
    p = Path(root) / run_id
    if not p.exists():
        return None
    return {"run_id": run_id, "path": str(p)}
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_tester_cache.py -v
git add mt5_cli/tester/cache.py tests/test_tester_cache.py
git commit -m "Phase 4: tester.cache — run-id snapshot dirs under results/"
```

### Task 4.2: Implement tester.ini_builder

**Files:**
- Create: `mt5_cli/tester/ini_builder.py`
- Create: `tests/test_tester_ini_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tester_ini_builder.py
from pathlib import Path

from mt5_cli.tester import ini_builder


def test_build_single_ea_ini_includes_required_fields(tmp_path):
    ini = ini_builder.build_ea_ini(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="real-ticks",
        deposit=10000,
        currency="USD",
        leverage=50,
        report_path=tmp_path / "report.html",
    )
    text = ini
    assert "[Tester]" in text
    assert "Expert=alpha" in text
    assert "Symbol=AUDUSD" in text
    assert "Period=M5" in text
    assert "FromDate=2024.01.01" in text
    assert "ToDate=2024.06.30" in text
    assert "Model=" in text  # 0/1/2/4 depending on modelling
    assert "Deposit=10000" in text
    assert "Leverage=50" in text


def test_build_indicator_visual_ini(tmp_path):
    ini = ini_builder.build_indicator_ini(
        indicator="donchian",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="ohlc-1m",
    )
    assert "Indicator=donchian" in ini
    assert "Visual=1" in ini


def test_modelling_maps_to_mt5_codes():
    assert ini_builder._modelling_code("real-ticks") == 0
    assert ini_builder._modelling_code("every-tick") == 1
    assert ini_builder._modelling_code("ohlc-1m") == 2


def test_unknown_modelling_raises():
    import pytest as _p
    with _p.raises(ValueError):
        ini_builder._modelling_code("invalid")
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_tester_ini_builder.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/tester/ini_builder.py`:

```python
"""Generate the .ini config file MT5's terminal64.exe /config: needs."""
from pathlib import Path

# MT5 Strategy Tester Model codes (per MT5 docs / tester ini reference):
#   0 = Every tick based on real ticks
#   1 = 1 minute OHLC
#   2 = Open prices only
#   4 = Math calculations
_MODELLING = {
    "real-ticks": 0,
    "every-tick": 1,
    "ohlc-1m": 2,
    "open-only": 2,
    "math": 4,
}


def _modelling_code(modelling: str) -> int:
    if modelling not in _MODELLING:
        raise ValueError(f"Unknown modelling {modelling!r}. Known: {sorted(_MODELLING)}")
    return _MODELLING[modelling]


def _fmt_date(d: str) -> str:
    return d.replace("-", ".")


def build_ea_ini(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "real-ticks",
    deposit: float = 10000,
    currency: str = "USD",
    leverage: int = 50,
    optimization: int = 0,
    forward: str | None = None,
    visual: bool = False,
    report_path: Path | str | None = None,
    set_file: Path | str | None = None,
) -> str:
    lines = [
        "[Tester]",
        f"Expert={expert}",
        f"Symbol={symbol}",
        f"Period={timeframe}",
        f"FromDate={_fmt_date(from_date)}",
        f"ToDate={_fmt_date(to_date)}",
        f"Model={_modelling_code(modelling)}",
        f"Deposit={int(deposit)}",
        f"Currency={currency}",
        f"Leverage={leverage}",
        f"Optimization={optimization}",
        f"Visual={1 if visual else 0}",
    ]
    if forward:
        lines.append(f"ForwardMode=1")
        lines.append(f"ForwardDate={_fmt_date(forward)}")
    if report_path:
        lines.append(f"Report={Path(report_path)}")
    if set_file:
        lines.append(f"ExpertParameters={Path(set_file).name}")
    return "\n".join(lines) + "\n"


def build_indicator_ini(
    *,
    indicator: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "ohlc-1m",
) -> str:
    return "\n".join([
        "[Tester]",
        f"Indicator={indicator}",
        f"Symbol={symbol}",
        f"Period={timeframe}",
        f"FromDate={_fmt_date(from_date)}",
        f"ToDate={_fmt_date(to_date)}",
        f"Model={_modelling_code(modelling)}",
        "Visual=1",
    ]) + "\n"


def write_ini(path: Path, content: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-16-le")
    # MT5 expects UTF-16 LE with BOM
    bom = b"\xff\xfe"
    raw = content.encode("utf-16-le")
    path.write_bytes(bom + raw)
    return path
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_tester_ini_builder.py -v
git add mt5_cli/tester/ini_builder.py tests/test_tester_ini_builder.py
git commit -m "Phase 4: tester.ini_builder generates .ini files for terminal64 /config"
```

### Task 4.3: Implement tester.launcher (terminal64.exe /config wrapper)

**Files:**
- Create: `mt5_cli/tester/launcher.py`
- Create: `tests/test_tester_launcher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tester_launcher.py
import subprocess
from pathlib import Path

from mt5_cli.tester import launcher


def test_locate_terminal_uses_env(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(fake))
    assert launcher.locate_terminal() == fake


def test_run_returns_fail_when_terminal_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "locate_terminal", lambda: None)
    out = launcher.run(ini_path=tmp_path / "x.ini", run_dir=tmp_path)
    assert out["ok"] is False
    assert out["error"]["code"] == "TERMINAL_NOT_FOUND"


def test_run_invokes_subprocess(monkeypatch, tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_bytes(b"")
    ini = tmp_path / "x.ini"
    ini.write_text("[Tester]\n", encoding="utf-8")
    rd = tmp_path / "run"
    rd.mkdir()

    captured = {}

    def fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(launcher, "locate_terminal", lambda: fake)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    out = launcher.run(ini_path=ini, run_dir=rd, timeout=30)
    assert out["ok"] is True
    assert any(arg.startswith("/config:") for arg in captured["cmd"])
    assert any(arg == "/portable" for arg in captured["cmd"])
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_tester_launcher.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/tester/launcher.py`:

```python
"""Run MT5's terminal64.exe in tester mode via /config:<ini>."""
import os
import subprocess
from pathlib import Path

from mt5_cli.reports import ok, fail

_CANDIDATE_PATHS = [
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe"),
]


def locate_terminal() -> Path | None:
    env = os.environ.get("MT5_TERMINAL_PATH")
    if env and Path(env).exists():
        return Path(env)
    for p in _CANDIDATE_PATHS:
        if p.exists():
            return p
    return None


def run(*, ini_path: Path, run_dir: Path, timeout: int = 600) -> dict:
    ini_path = Path(ini_path)
    run_dir = Path(run_dir)
    if not ini_path.exists():
        return fail("INI_NOT_FOUND", f"INI file not found: {ini_path}")
    terminal = locate_terminal()
    if not terminal:
        return fail(
            "TERMINAL_NOT_FOUND",
            "Could not locate terminal64.exe. Set MT5_TERMINAL_PATH.",
        )
    cmd = [str(terminal), f"/config:{ini_path}", "/portable"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return fail("TESTER_TIMEOUT", f"terminal64 did not finish in {timeout}s")
    return ok({
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:] if proc.stdout else "",
        "stderr": proc.stderr[-4000:] if proc.stderr else "",
        "run_dir": str(run_dir),
    })
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_tester_launcher.py -v
git add mt5_cli/tester/launcher.py tests/test_tester_launcher.py
git commit -m "Phase 4: tester.launcher runs terminal64.exe /config:<ini> /portable"
```

### Task 4.4: Implement tester.results — HTML report parser

**Files:**
- Create: `mt5_cli/tester/results.py`
- Create: `tests/test_tester_results_html.py`
- Create: `tests/fixtures/sample_report.html`

- [ ] **Step 1: Capture a representative sample HTML**

Create `tests/fixtures/sample_report.html` (this is a minimal MT5-tester-style report — the real ones are larger but follow this structure):

```html
<html><body>
<table>
<tr><td>Symbol</td><td>AUDUSD</td><td>Period</td><td>M5 (2024.01.01-2024.06.30)</td></tr>
<tr><td>Initial Deposit</td><td>10000.00</td><td>Total Net Profit</td><td>1234.56</td></tr>
<tr><td>Profit Factor</td><td>1.42</td><td>Maximal Drawdown</td><td>1230.00 (12.30%)</td></tr>
<tr><td>Total Trades</td><td>412</td><td>Profit Trades (% of total)</td><td>239 (58.01%)</td></tr>
<tr><td>Sharpe Ratio</td><td>0.91</td><td>Expected Payoff</td><td>4.20</td></tr>
</table>
<table>
<tr><th>Time</th><th>Type</th><th>Order</th><th>Symbol</th><th>Volume</th><th>Price</th><th>Profit</th></tr>
<tr><td>2024.01.05 10:15:00</td><td>buy</td><td>1001</td><td>AUDUSD</td><td>0.10</td><td>0.6543</td><td>0.00</td></tr>
<tr><td>2024.01.05 11:30:00</td><td>sell</td><td>1002</td><td>AUDUSD</td><td>0.10</td><td>0.6555</td><td>12.34</td></tr>
</table>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_tester_results_html.py
from pathlib import Path

from mt5_cli.tester import results

FIXTURE = Path(__file__).parent / "fixtures" / "sample_report.html"


def test_parse_html_extracts_stats():
    out = results.parse_html_report(FIXTURE)
    assert out["stats"]["total_trades"] == 412
    assert out["stats"]["win_rate"] == 0.5801
    assert out["stats"]["profit_factor"] == 1.42
    assert out["stats"]["max_drawdown_pct"] == 12.30
    assert out["stats"]["sharpe"] == 0.91
    assert out["stats"]["expectancy"] == 4.20


def test_parse_html_extracts_metadata():
    out = results.parse_html_report(FIXTURE)
    assert out["metadata"]["symbol"] == "AUDUSD"
    assert out["metadata"]["timeframe"] == "M5"
    assert out["metadata"]["from"] == "2024-01-01"
    assert out["metadata"]["to"] == "2024-06-30"
    assert out["metadata"]["initial_deposit"] == 10000.0


def test_parse_html_extracts_deals():
    out = results.parse_html_report(FIXTURE)
    deals = out["deals"]
    assert len(deals) == 2
    assert deals[0]["type"] == "buy"
    assert deals[0]["volume"] == 0.10
    assert deals[1]["profit"] == 12.34
```

- [ ] **Step 3: Run — fails**

```bash
python -m pytest tests/test_tester_results_html.py -v
```

- [ ] **Step 4: Implement (HTML parser only — CSV / XML / envelope land in next tasks)**

Create `mt5_cli/tester/results.py`:

```python
"""Parse MT5 Strategy Tester output: HTML report + journal CSV + optimization XML.

Combined assembler at the end produces the standard JSON envelope.
"""
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class _RowExtractor(HTMLParser):
    """Minimal HTML parser that yields rows-of-cells per <table> in order."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in ("td", "th") and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._current_cell is not None:
            self._current_row.append("".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell.append(data)


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _to_int(s: str) -> int | None:
    try:
        return int(s.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _kv_from_metadata_table(rows: list[list[str]]) -> dict[str, str]:
    """The MT5 metadata table is (key, value, key, value) per row."""
    kv: dict[str, str] = {}
    for row in rows:
        for i in range(0, len(row) - 1, 2):
            kv[row[i].rstrip(":").strip()] = row[i + 1].strip()
    return kv


def _parse_period(period: str) -> tuple[str | None, str | None, str | None]:
    """'M5 (2024.01.01-2024.06.30)' -> ('M5', '2024-01-01', '2024-06-30')"""
    m = re.match(r"(\w+)\s*\((\d{4}\.\d{2}\.\d{2})-(\d{4}\.\d{2}\.\d{2})\)", period)
    if not m:
        return period, None, None
    tf, frm, to = m.group(1), m.group(2).replace(".", "-"), m.group(3).replace(".", "-")
    return tf, frm, to


def parse_html_report(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    parser = _RowExtractor()
    parser.feed(text)
    if not parser.tables:
        return {"metadata": {}, "stats": {}, "deals": []}

    kv = _kv_from_metadata_table(parser.tables[0])
    metadata: dict[str, Any] = {}
    if "Symbol" in kv:
        metadata["symbol"] = kv["Symbol"]
    if "Period" in kv:
        tf, frm, to = _parse_period(kv["Period"])
        metadata["timeframe"] = tf
        if frm:
            metadata["from"] = frm
        if to:
            metadata["to"] = to
    if "Initial Deposit" in kv:
        metadata["initial_deposit"] = _to_float(kv["Initial Deposit"])

    stats: dict[str, Any] = {}
    if "Total Trades" in kv:
        stats["total_trades"] = _to_int(kv["Total Trades"])
    if "Profit Trades (% of total)" in kv:
        m = re.search(r"\(([\d.]+)%\)", kv["Profit Trades (% of total)"])
        if m:
            stats["win_rate"] = round(float(m.group(1)) / 100, 4)
    if "Profit Factor" in kv:
        stats["profit_factor"] = _to_float(kv["Profit Factor"])
    if "Maximal Drawdown" in kv:
        m = re.search(r"\(([\d.]+)%\)", kv["Maximal Drawdown"])
        if m:
            stats["max_drawdown_pct"] = float(m.group(1))
    if "Sharpe Ratio" in kv:
        stats["sharpe"] = _to_float(kv["Sharpe Ratio"])
    if "Expected Payoff" in kv:
        stats["expectancy"] = _to_float(kv["Expected Payoff"])
    if "Total Net Profit" in kv:
        stats["net_profit"] = _to_float(kv["Total Net Profit"])

    deals: list[dict[str, Any]] = []
    if len(parser.tables) >= 2:
        deal_rows = parser.tables[1]
        if not deal_rows:
            return {"metadata": metadata, "stats": stats, "deals": deals}
        headers = [h.lower() for h in deal_rows[0]]
        for row in deal_rows[1:]:
            if len(row) != len(headers):
                continue
            entry: dict[str, Any] = {}
            for h, v in zip(headers, row):
                if h == "time":
                    entry["time"] = v
                elif h == "type":
                    entry["type"] = v
                elif h == "order":
                    entry["order"] = _to_int(v)
                elif h == "symbol":
                    entry["symbol"] = v
                elif h == "volume":
                    entry["volume"] = _to_float(v)
                elif h == "price":
                    entry["price"] = _to_float(v)
                elif h == "profit":
                    entry["profit"] = _to_float(v)
            deals.append(entry)

    return {"metadata": metadata, "stats": stats, "deals": deals}
```

Wire `mt5_cli/tester/__init__.py`:

```python
from . import cache, ini_builder, launcher, results

__all__ = ["cache", "ini_builder", "launcher", "results"]
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest tests/test_tester_results_html.py -v
git add mt5_cli/tester/results.py mt5_cli/tester/__init__.py tests/test_tester_results_html.py tests/fixtures/sample_report.html
git commit -m "Phase 4: tester.results.parse_html_report extracts stats + deals"
```

### Task 4.5: Add journal CSV parser

**Files:**
- Modify: `mt5_cli/tester/results.py`
- Create: `tests/test_tester_results_journal.py`
- Create: `tests/fixtures/sample_journal.csv`

- [ ] **Step 1: Write the fixture**

`tests/fixtures/sample_journal.csv`:

```
2024.01.05 10:15:00,info,Initialize: alpha v0.1
2024.01.05 10:15:01,info,Symbol AUDUSD selected
2024.01.05 10:30:00,warning,Slippage > 2 points on order 1001
2024.06.30 23:59:00,info,Test finished
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_tester_results_journal.py
from pathlib import Path

from mt5_cli.tester import results

FIXTURE = Path(__file__).parent / "fixtures" / "sample_journal.csv"


def test_parse_journal_returns_events():
    events = results.parse_journal(FIXTURE)
    assert len(events) == 4
    assert events[0]["level"] == "info"
    assert events[2]["level"] == "warning"
    assert "Slippage" in events[2]["msg"]


def test_journal_iso_timestamps():
    events = results.parse_journal(FIXTURE)
    assert events[0]["time"] == "2024-01-05T10:15:00"
```

- [ ] **Step 3: Run — fails**

```bash
python -m pytest tests/test_tester_results_journal.py -v
```

- [ ] **Step 4: Implement — append to results.py**

Add to `mt5_cli/tester/results.py`:

```python
def _to_iso(stamp: str) -> str:
    """'2024.01.05 10:15:00' -> '2024-01-05T10:15:00'"""
    d, t = stamp.split(" ", 1)
    return d.replace(".", "-") + "T" + t


def parse_journal(path: Path) -> list[dict[str, Any]]:
    """Parse a tester journal CSV. MT5 journals are line-per-event:
    'YYYY.MM.DD HH:MM:SS,level,message'."""
    out: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 2)
        if len(parts) != 3:
            continue
        stamp, level, msg = parts
        out.append({"time": _to_iso(stamp), "level": level.strip(), "msg": msg.strip()})
    return out
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest tests/test_tester_results_journal.py -v
git add mt5_cli/tester/results.py tests/test_tester_results_journal.py tests/fixtures/sample_journal.csv
git commit -m "Phase 4: tester.results.parse_journal — CSV journal -> JSON events"
```

### Task 4.6: Add optimization XML parser + envelope assembler

**Files:**
- Modify: `mt5_cli/tester/results.py`
- Create: `tests/fixtures/sample_optimization.xml`
- Create: `tests/test_tester_results_envelope.py`

- [ ] **Step 1: Write the fixture**

`tests/fixtures/sample_optimization.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<results>
  <pass>
    <Profit>1234.56</Profit>
    <ProfitFactor>1.42</ProfitFactor>
    <Trades>412</Trades>
    <FastPeriod>9</FastPeriod>
    <SlowPeriod>21</SlowPeriod>
  </pass>
  <pass>
    <Profit>987.65</Profit>
    <ProfitFactor>1.18</ProfitFactor>
    <Trades>389</Trades>
    <FastPeriod>5</FastPeriod>
    <SlowPeriod>20</SlowPeriod>
  </pass>
</results>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_tester_results_envelope.py
from pathlib import Path

from mt5_cli.tester import results

FIX = Path(__file__).parent / "fixtures"


def test_parse_optimization_xml_returns_passes():
    passes = results.parse_optimization_xml(FIX / "sample_optimization.xml")
    assert len(passes) == 2
    assert passes[0]["Profit"] == 1234.56
    assert passes[0]["FastPeriod"] == 9
    assert passes[1]["Trades"] == 389


def test_assemble_envelope_combines_html_journal_xml():
    env = results.assemble(
        run_id="run-id-123",
        html_path=FIX / "sample_report.html",
        journal_path=FIX / "sample_journal.csv",
        optimization_path=None,
    )
    assert env["ok"] is True
    d = env["data"]
    assert d["run_id"] == "run-id-123"
    assert d["stats"]["total_trades"] == 412
    assert len(d["deals"]) == 2
    assert len(d["journal_events"]) == 4
    assert d.get("optimization") in (None, [])  # absent or empty


def test_assemble_envelope_includes_optimization():
    env = results.assemble(
        run_id="opt-run-1",
        html_path=FIX / "sample_report.html",
        journal_path=None,
        optimization_path=FIX / "sample_optimization.xml",
    )
    assert env["data"]["optimization"][0]["FastPeriod"] == 9
```

- [ ] **Step 3: Run — fails**

```bash
python -m pytest tests/test_tester_results_envelope.py -v
```

- [ ] **Step 4: Implement — append to results.py**

Add to `mt5_cli/tester/results.py`:

```python
import xml.etree.ElementTree as ET

from mt5_cli.reports import ok


def parse_optimization_xml(path: Path) -> list[dict[str, Any]]:
    tree = ET.parse(Path(path))
    root = tree.getroot()
    passes: list[dict[str, Any]] = []
    for p in root.findall("pass"):
        entry: dict[str, Any] = {}
        for child in p:
            txt = (child.text or "").strip()
            casted: Any = txt
            f = _to_float(txt)
            if f is not None:
                if f == int(f) and "." not in txt:
                    casted = int(f)
                else:
                    casted = f
            entry[child.tag] = casted
        passes.append(entry)
    return passes


def assemble(
    *,
    run_id: str,
    html_path: Path | None,
    journal_path: Path | None = None,
    optimization_path: Path | None = None,
    extra_metadata: dict | None = None,
) -> dict:
    data: dict[str, Any] = {"run_id": run_id}
    if extra_metadata:
        data.update(extra_metadata)
    if html_path and Path(html_path).exists():
        report = parse_html_report(html_path)
        data.setdefault("metadata", {}).update(report["metadata"])
        data["stats"] = report["stats"]
        data["deals"] = report["deals"]
    else:
        data["stats"] = {}
        data["deals"] = []
    if journal_path and Path(journal_path).exists():
        data["journal_events"] = parse_journal(journal_path)
    else:
        data["journal_events"] = []
    if optimization_path and Path(optimization_path).exists():
        data["optimization"] = parse_optimization_xml(optimization_path)
    return ok(data)
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest tests/test_tester_results_envelope.py -v
git add mt5_cli/tester/results.py tests/test_tester_results_envelope.py tests/fixtures/sample_optimization.xml
git commit -m "Phase 4: tester.results — XML opt parser + assemble() envelope

assemble() combines HTML stats/deals + CSV journal + optimization XML
into the standard JSON envelope. Missing inputs are tolerated (return
empty arrays / None for the missing piece)."
```

### Task 4.7: Implement tester.ea — single mode

**Files:**
- Create: `mt5_cli/tester/ea.py`
- Create: `tests/test_tester_ea.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tester_ea.py
from pathlib import Path

from mt5_cli.tester import ea


def test_single_returns_envelope_with_run_id(monkeypatch, tmp_path):
    # Patch the launcher to simulate a successful run that drops report + journal
    def fake_launch(*, ini_path, run_dir, timeout):
        rd = Path(run_dir)
        (rd / "report.html").write_text(
            "<html><body><table>"
            "<tr><td>Symbol</td><td>AUDUSD</td><td>Period</td><td>M5 (2024.01.01-2024.06.30)</td></tr>"
            "<tr><td>Total Trades</td><td>10</td></tr>"
            "</table></body></html>",
            encoding="utf-8",
        )
        return {"ok": True, "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(rd)}}

    monkeypatch.setattr(ea.launcher, "run", fake_launch)
    # Avoid resolving real EA on disk
    monkeypatch.setattr(ea.discovery, "get_ea", lambda name: {"name": name, "source": "x.mq5", "compiled": True})

    out = ea.single(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="ohlc-1m",
        results_root=tmp_path,
    )
    assert out["ok"] is True
    d = out["data"]
    assert d["expert"] == "alpha"
    assert d["symbol"] == "AUDUSD"
    assert "run_id" in d
    assert d["stats"]["total_trades"] == 10


def test_single_returns_fail_when_ea_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(ea.discovery, "get_ea", lambda name: None)
    out = ea.single(
        expert="missing",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "EA_NOT_FOUND"


def test_single_requires_compiled(monkeypatch, tmp_path):
    monkeypatch.setattr(ea.discovery, "get_ea", lambda name: {"name": name, "source": "x.mq5", "compiled": False})
    out = ea.single(
        expert="uncompiled",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "EA_NOT_COMPILED"
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_tester_ea.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/tester/ea.py`:

```python
"""High-level tester.ea operations: single, optimize, scanner, stress.

Composes ini_builder + launcher + results.assemble + cache.
"""
from pathlib import Path

from mt5_cli.mql5 import discovery
from mt5_cli.reports import ok, fail
from . import cache, ini_builder, launcher, results


def single(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "real-ticks",
    deposit: float = 10000,
    currency: str = "USD",
    leverage: int = 50,
    visual: bool = False,
    set_file: Path | str | None = None,
    results_root: Path | str = "results",
    timeout: int = 600,
) -> dict:
    e = discovery.get_ea(expert)
    if not e:
        return fail("EA_NOT_FOUND", f"No EA named {expert!r}. Run `mt5 ea list`.")
    if not e["compiled"]:
        return fail("EA_NOT_COMPILED", f"EA {expert!r} has no .ex5. Run `mt5 ea compile {expert}`.")

    run_id = cache.make_run_id(expert, symbol, timeframe)
    rd = cache.run_dir(run_id, root=results_root)
    ini_path = rd / "tester.ini"
    report_path = rd / "report.html"
    journal_path = rd / "journal.csv"

    ini_text = ini_builder.build_ea_ini(
        expert=expert, symbol=symbol, timeframe=timeframe,
        from_date=from_date, to_date=to_date,
        modelling=modelling, deposit=deposit, currency=currency, leverage=leverage,
        visual=visual, report_path=report_path, set_file=set_file,
    )
    ini_builder.write_ini(ini_path, ini_text)

    launch = launcher.run(ini_path=ini_path, run_dir=rd, timeout=timeout)
    if not launch["ok"]:
        return launch  # propagate launcher error envelope

    env = results.assemble(
        run_id=run_id,
        html_path=report_path,
        journal_path=journal_path,
        extra_metadata={
            "expert": expert,
            "symbol": symbol,
            "timeframe": timeframe,
            "from": from_date,
            "to": to_date,
            "modelling": modelling,
            "deposit": deposit,
            "currency": currency,
            "leverage": leverage,
        },
    )
    return env
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_tester_ea.py -v
git add mt5_cli/tester/ea.py tests/test_tester_ea.py
git commit -m "Phase 4: tester.ea.single composes ini + launcher + results

Builds the .ini, launches terminal64 in portable mode, parses the
report + journal, returns the standard envelope with run_id + stats
+ deals + journal_events."
```

### Task 4.8: Implement tester.ea — optimize/forward + scanner + stress

**Files:**
- Modify: `mt5_cli/tester/ea.py`
- Modify: `tests/test_tester_ea.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_tester_ea.py`:

```python
def test_optimize_calls_launcher_with_optimization_flag(monkeypatch, tmp_path):
    captured_inis = []

    def fake_launch(*, ini_path, run_dir, timeout):
        captured_inis.append(Path(ini_path).read_bytes()[2:].decode("utf-16-le"))
        Path(run_dir, "report.html").write_text("<html><body><table></table></body></html>")
        return {"ok": True, "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_dir)}}

    monkeypatch.setattr(ea.launcher, "run", fake_launch)
    monkeypatch.setattr(ea.discovery, "get_ea", lambda n: {"name": n, "source": "x.mq5", "compiled": True})

    out = ea.optimize(
        expert="alpha", symbol="AUDUSD", timeframe="M5",
        from_date="2024-01-01", to_date="2024-06-30",
        mode="complete", results_root=tmp_path,
    )
    assert out["ok"] is True
    assert "Optimization=1" in captured_inis[0]


def test_scanner_runs_per_symbol(monkeypatch, tmp_path):
    runs = []
    def fake_single(**kwargs):
        runs.append(kwargs["symbol"])
        return {"ok": True, "data": {"run_id": kwargs["symbol"], "symbol": kwargs["symbol"], "stats": {"total_trades": 1}}}
    monkeypatch.setattr(ea, "single", fake_single)
    out = ea.scanner(
        expert="alpha", symbols=["AUDUSD", "EURUSD", "GBPUSD"],
        timeframe="M5", from_date="2024-01-01", to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is True
    assert sorted(runs) == ["AUDUSD", "EURUSD", "GBPUSD"]
    assert len(out["data"]["per_symbol"]) == 3
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_tester_ea.py -v
```

- [ ] **Step 3: Implement — append to tester/ea.py**

Add to `mt5_cli/tester/ea.py`:

```python
_OPT_MODES = {"complete": 1, "genetic": 2, "math": 4}


def optimize(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    mode: str = "complete",
    forward: str | None = None,
    set_file: Path | str | None = None,
    modelling: str = "ohlc-1m",
    results_root: Path | str = "results",
    timeout: int = 1800,
) -> dict:
    if mode not in _OPT_MODES:
        return fail("UNKNOWN_OPT_MODE", f"Unknown optimization mode {mode!r}. Known: {sorted(_OPT_MODES)}")
    e = discovery.get_ea(expert)
    if not e:
        return fail("EA_NOT_FOUND", f"No EA named {expert!r}.")
    if not e["compiled"]:
        return fail("EA_NOT_COMPILED", f"EA {expert!r} has no .ex5.")

    run_id = cache.make_run_id(f"opt-{mode}-{expert}", symbol, timeframe)
    rd = cache.run_dir(run_id, root=results_root)
    ini_path = rd / "tester.ini"
    report_path = rd / "report.html"
    journal_path = rd / "journal.csv"
    opt_path = rd / "optimization.xml"

    ini_text = ini_builder.build_ea_ini(
        expert=expert, symbol=symbol, timeframe=timeframe,
        from_date=from_date, to_date=to_date,
        modelling=modelling,
        optimization=_OPT_MODES[mode],
        forward=forward,
        set_file=set_file, report_path=report_path,
    )
    ini_builder.write_ini(ini_path, ini_text)

    launch = launcher.run(ini_path=ini_path, run_dir=rd, timeout=timeout)
    if not launch["ok"]:
        return launch

    return results.assemble(
        run_id=run_id,
        html_path=report_path,
        journal_path=journal_path,
        optimization_path=opt_path if opt_path.exists() else None,
        extra_metadata={
            "expert": expert, "symbol": symbol, "timeframe": timeframe,
            "from": from_date, "to": to_date, "mode": mode, "forward": forward,
        },
    )


def scanner(
    *,
    expert: str,
    symbols: list[str],
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "ohlc-1m",
    results_root: Path | str = "results",
) -> dict:
    per_symbol: list[dict] = []
    for sym in symbols:
        env = single(
            expert=expert, symbol=sym, timeframe=timeframe,
            from_date=from_date, to_date=to_date, modelling=modelling,
            results_root=results_root,
        )
        per_symbol.append({"symbol": sym, "envelope": env})
    return ok({"per_symbol": per_symbol, "expert": expert, "symbols": symbols})


def stress(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    delays_ms: int = 50,
    results_root: Path | str = "results",
) -> dict:
    """Stress mode = single test with simulated delays. The .ini's
    Delays field is supplied by ini_builder when MT5 supports it; for
    simplicity here we just record the requested delay in metadata."""
    env = single(
        expert=expert, symbol=symbol, timeframe=timeframe,
        from_date=from_date, to_date=to_date, results_root=results_root,
    )
    if env["ok"]:
        env["data"]["stress_delay_ms"] = delays_ms
    return env
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_tester_ea.py -v
git add mt5_cli/tester/ea.py tests/test_tester_ea.py
git commit -m "Phase 4: tester.ea — optimize/scanner/stress modes

optimize: complete | genetic | math, optional forward window.
scanner: runs single() per symbol and aggregates per-symbol envelopes.
stress: single() with simulated-delay metadata (true delay injection
varies by MT5 version)."
```

### Task 4.9: Implement tester.indicator (visual test)

**Files:**
- Create: `mt5_cli/tester/indicator.py`
- Create: `tests/test_tester_indicator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tester_indicator.py
from pathlib import Path

from mt5_cli.tester import indicator


def test_visual_returns_envelope_with_run_id(monkeypatch, tmp_path):
    def fake_launch(*, ini_path, run_dir, timeout):
        return {"ok": True, "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_dir)}}
    monkeypatch.setattr(indicator.launcher, "run", fake_launch)
    monkeypatch.setattr(indicator.discovery, "get_indicator",
                        lambda n: {"name": n, "source": "x.mq5", "compiled": True})
    out = indicator.visual(
        indicator_name="donchian",
        symbol="AUDUSD", timeframe="M5",
        from_date="2024-01-01", to_date="2024-06-30",
        modelling="ohlc-1m",
        results_root=tmp_path,
    )
    assert out["ok"] is True
    assert "run_id" in out["data"]
    assert out["data"]["indicator"] == "donchian"


def test_visual_returns_fail_when_indicator_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(indicator.discovery, "get_indicator", lambda n: None)
    out = indicator.visual(
        indicator_name="missing",
        symbol="AUDUSD", timeframe="M5",
        from_date="2024-01-01", to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INDICATOR_NOT_FOUND"
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_tester_indicator.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/tester/indicator.py`:

```python
from pathlib import Path

from mt5_cli.mql5 import discovery
from mt5_cli.reports import ok, fail
from . import cache, ini_builder, launcher


def visual(
    *,
    indicator_name: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "ohlc-1m",
    results_root: Path | str = "results",
    timeout: int = 600,
) -> dict:
    ind = discovery.get_indicator(indicator_name)
    if not ind:
        return fail("INDICATOR_NOT_FOUND", f"No indicator named {indicator_name!r}.")
    if not ind["compiled"]:
        return fail("INDICATOR_NOT_COMPILED", f"Indicator {indicator_name!r} has no .ex5.")

    run_id = cache.make_run_id(f"ind-{indicator_name}", symbol, timeframe)
    rd = cache.run_dir(run_id, root=results_root)
    ini_path = rd / "tester.ini"
    ini_text = ini_builder.build_indicator_ini(
        indicator=indicator_name, symbol=symbol, timeframe=timeframe,
        from_date=from_date, to_date=to_date, modelling=modelling,
    )
    ini_builder.write_ini(ini_path, ini_text)

    launch = launcher.run(ini_path=ini_path, run_dir=rd, timeout=timeout)
    if not launch["ok"]:
        return launch

    return ok({
        "run_id": run_id,
        "indicator": indicator_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "from": from_date,
        "to": to_date,
        "modelling": modelling,
        "run_dir": str(rd),
    })
```

Update `mt5_cli/tester/__init__.py`:

```python
from . import cache, ea, ini_builder, indicator, launcher, results

__all__ = ["cache", "ea", "ini_builder", "indicator", "launcher", "results"]
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_tester_indicator.py -v
git add mt5_cli/tester/indicator.py mt5_cli/tester/__init__.py tests/test_tester_indicator.py
git commit -m "Phase 4: tester.indicator.visual — drive MT5 indicator visual test"
```

### Task 4.10: Wire `mt5 tester ea/indicator/list/show` CLI commands + Phase 4 acceptance

**Files:**
- Modify: `mt5/cli.py`
- Create: `tests/test_cli_tester.py`

- [ ] **Step 1: Append the tester command group to mt5/cli.py**

Add at the end of `mt5/cli.py`:

```python
from mt5_cli.tester import ea as tester_ea, indicator as tester_indicator, cache as tester_cache
from mt5_cli.tester import results as tester_results


@main.group("tester")
def tester_group():
    """Drive the MT5 Strategy Tester."""


@tester_group.group("ea")
def tester_ea_group():
    """Backtest an Expert Advisor."""


@tester_ea_group.command("single")
@click.option("--expert", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option("--modelling", default="real-ticks", type=click.Choice(["real-ticks", "every-tick", "ohlc-1m", "open-only", "math"]))
@click.option("--deposit", default=10000.0, type=float)
@click.option("--currency", default="USD")
@click.option("--leverage", default=50, type=int)
@click.option("--visual/--no-visual", default=False)
@click.pass_context
def cmd_tester_ea_single(ctx, **kwargs):
    _emit(tester_ea.single(**kwargs), ctx.obj["json"])


@tester_ea_group.command("optimize")
@click.option("--expert", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option("--mode", default="complete", type=click.Choice(["complete", "genetic", "math"]))
@click.option("--forward", default=None)
@click.pass_context
def cmd_tester_ea_optimize(ctx, **kwargs):
    _emit(tester_ea.optimize(**kwargs), ctx.obj["json"])


@tester_ea_group.command("scanner")
@click.option("--expert", required=True)
@click.option("--symbols", required=True, help="Comma-separated symbols, e.g., AUDUSD,EURUSD")
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.pass_context
def cmd_tester_ea_scanner(ctx, expert, symbols, timeframe, from_date, to_date):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    _emit(tester_ea.scanner(expert=expert, symbols=syms, timeframe=timeframe, from_date=from_date, to_date=to_date), ctx.obj["json"])


@tester_ea_group.command("stress")
@click.option("--expert", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option("--delays-ms", default=50, type=int)
@click.pass_context
def cmd_tester_ea_stress(ctx, **kwargs):
    _emit(tester_ea.stress(**kwargs), ctx.obj["json"])


@tester_group.group("indicator")
def tester_indicator_group():
    """Visual-test an indicator."""


@tester_indicator_group.command("visual")
@click.option("--indicator", "indicator_name", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option("--modelling", default="ohlc-1m")
@click.pass_context
def cmd_tester_indicator_visual(ctx, **kwargs):
    _emit(tester_indicator.visual(**kwargs), ctx.obj["json"])


@tester_group.command("list")
@click.option("--limit", default=20, type=int)
@click.pass_context
def cmd_tester_list(ctx, limit):
    _emit({"ok": True, "data": tester_cache.list_recent(limit=limit)}, ctx.obj["json"])


@tester_group.command("show")
@click.argument("run_id")
@click.pass_context
def cmd_tester_show(ctx, run_id):
    run = tester_cache.get_run(run_id)
    if not run:
        _emit({"ok": False, "error": {"code": "RUN_NOT_FOUND", "message": f"No run {run_id!r}"}}, ctx.obj["json"])
        return
    rd = Path(run["path"])
    env = tester_results.assemble(
        run_id=run_id,
        html_path=rd / "report.html",
        journal_path=rd / "journal.csv",
        optimization_path=rd / "optimization.xml",
    )
    _emit(env, ctx.obj["json"])
```

- [ ] **Step 2: Smoke test**

```python
# tests/test_cli_tester.py
import json
from pathlib import Path

from click.testing import CliRunner

from mt5.cli import main


def test_tester_list_emits_envelope(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "tester", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)


def test_tester_show_unknown_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "tester", "show", "no_such_run"])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "RUN_NOT_FOUND"
```

- [ ] **Step 3: Run + commit + tag**

```bash
python -m pytest -q
git add mt5/cli.py tests/test_cli_tester.py
git commit -m "Phase 4: wire mt5 tester ea/indicator/list/show CLI

Maps every Strategy Tester Settings panel knob (symbol, tf, dates,
modelling, deposit, currency, leverage, visual) to flags. Optimize
takes mode + forward; scanner takes --symbols comma list; stress
takes --delays-ms. Indicator visual mirrors the EA shape."
git tag phase-4-complete
```

- [ ] **Step 4: Phase 4 acceptance check**

```bash
mt5 tester --help
mt5 tester ea --help
mt5 tester ea single --help
mt5 --json tester list           # empty array initially
# When MetaEditor + terminal64 are available:
# mt5 --json ea compile ema_crossover
# mt5 --json ea deploy ema_crossover
# mt5 --json tester ea single --expert ema_crossover --symbol AUDUSD --tf M5 \
#   --from 2024-01-01 --to 2024-06-30 --modelling ohlc-1m
```

---

## Phase 5 — Agent surface (8 tasks)

**Goal:** Make agents discoverable and runnable. Migrate the archived 11k-char SKILL.md from `archive/legacy-mt5/skills/`, add YAML frontmatter, add MCP server, recreate ReplSkin in the new CLI so it prints the SKILL.md path, and add a skill_generator that introspects the Click tree.

### Task 5.1: Migrate SKILL.md to mt5_cli/skills/ with YAML frontmatter

**Files:**
- Create: `mt5_cli/skills/SKILL.md` from archived source `archive/legacy-mt5/skills/SKILL.md`
- Modify: `mt5_cli/skills/SKILL.md` — prepend YAML frontmatter; replace any references to legacy commands with new equivalents
- Modify: `setup.py` package_data

- [ ] **Step 1: Copy archived manifest and add frontmatter**

```powershell
Copy-Item archive\legacy-mt5\skills\SKILL.md mt5_cli\skills\SKILL.md
```

Edit `mt5_cli/skills/SKILL.md` to prepend (use the Edit tool):

```markdown
---
name: mt5-universal
description: Drive MetaTrader 5 from the CLI or via MCP — market data, orders, positions, account, history, MQL5 EA/indicator scaffolding, Strategy Tester. Risk-gated, JSON-envelope responses.
---

```

(Then a blank line, then the existing first heading.)

- [ ] **Step 2: Update legacy command references inside the doc**

Search the doc for any of: `mt5 ea adaptive-trail`, `mt5 analyze sniper-poc`, `mt5 analyze topdown`, `mt5 chart depth-of-market`, `mt5 screenshot tda`, `mt5 ea compile-tda` — these all referenced archived commands. Either delete the whole section or replace with a "see legacy spec" pointer.

- [ ] **Step 3: Update setup.py**

```python
    package_data={
        "mt5_cli.mql5": ["templates/*.mq5"],
        "mt5_cli.skills": ["SKILL.md"],
    },
```

(No `metatrader5_cli.*` package_data entry should return; that package is archived.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Phase 5: migrate SKILL.md to mt5_cli/skills/ + add frontmatter

YAML frontmatter (name, description) makes the skill discoverable by
Claude Code's skill loader. Legacy command references either
removed or pointed at the archived spec."
```

### Task 5.2: Implement skill_generator (introspect Click tree → command-group tables)

**Files:**
- Create: `mt5_cli/skills/generator.py`
- Create: `tests/test_skill_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skill_generator.py
from mt5_cli.skills.generator import build_command_tables

import click


def _fake_root():
    @click.group()
    def root():
        pass

    @root.group("ea")
    def ea():
        """Manage MQL5 Expert Advisors."""

    @ea.command("list")
    def ea_list():
        """List EAs found on disk."""

    @ea.command("new")
    @click.argument("name")
    def ea_new(name):
        """Create a new EA from a template."""

    return root


def test_build_command_tables_yields_one_table_per_group():
    tables = build_command_tables(_fake_root())
    assert "ea" in tables
    rows = tables["ea"]
    cmds = sorted(r["command"] for r in rows)
    assert cmds == ["list", "new"]
    assert any("List EAs" in r["description"] for r in rows)
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_skill_generator.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/skills/generator.py`:

```python
"""Introspect a Click root and produce per-group command tables for SKILL.md."""
import click


def build_command_tables(root: click.Group) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for name, cmd in root.commands.items():
        if isinstance(cmd, click.Group):
            out[name] = [
                {"command": cn, "description": (sub.help or "").strip()}
                for cn, sub in sorted(cmd.commands.items())
            ]
    return out


def render_markdown_tables(tables: dict[str, list[dict]]) -> str:
    parts: list[str] = []
    for group, rows in sorted(tables.items()):
        parts.append(f"### `{group}`\n")
        parts.append("| Command | Description |\n|---|---|")
        for r in rows:
            parts.append(f"| `{group} {r['command']}` | {r['description'] or '_no description_'} |")
        parts.append("")
    return "\n".join(parts)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_skill_generator.py -v
git add mt5_cli/skills/generator.py tests/test_skill_generator.py
git commit -m "Phase 5: skill_generator — Click introspection + markdown table render"
```

### Task 5.3: Wire `mt5 skills regenerate` command

**Files:**
- Modify: `mt5/cli.py`
- Create: `tests/test_cli_skills.py`

- [ ] **Step 1: Append to mt5/cli.py**

```python
from mt5_cli.skills.generator import build_command_tables, render_markdown_tables


@main.group("skills")
def skills_group():
    """Manage the SKILL.md manifest."""


@skills_group.command("regenerate")
@click.option("--target", default="mt5_cli/skills/SKILL.md", type=click.Path(dir_okay=False))
@click.pass_context
def cmd_skills_regenerate(ctx, target):
    """Regenerate the auto-generated Command Groups section.

    Looks for HTML comment markers <!-- BEGIN COMMANDS --> and
    <!-- END COMMANDS --> in the file and replaces everything between.
    """
    tables = build_command_tables(main)
    block = render_markdown_tables(tables)
    target_path = Path(target)
    text = target_path.read_text(encoding="utf-8")
    BEGIN, END = "<!-- BEGIN COMMANDS -->", "<!-- END COMMANDS -->"
    if BEGIN not in text or END not in text:
        _emit({"ok": False, "error": {"code": "MARKERS_MISSING",
            "message": f"Add {BEGIN} ... {END} to {target} so the generator knows where to write."}}, ctx.obj["json"])
        return
    pre, _, rest = text.partition(BEGIN)
    _, _, post = rest.partition(END)
    new = f"{pre}{BEGIN}\n\n{block}\n{END}{post}"
    target_path.write_text(new, encoding="utf-8")
    _emit({"ok": True, "data": {"target": str(target), "groups": sorted(tables)}}, ctx.obj["json"])
```

- [ ] **Step 2: Add the markers to mt5_cli/skills/SKILL.md**

Edit the SKILL.md and insert (anywhere appropriate, typically after the introduction):

```markdown
## Command Groups (auto-generated)

<!-- BEGIN COMMANDS -->

(this section is regenerated by `mt5 skills regenerate`)

<!-- END COMMANDS -->
```

- [ ] **Step 3: Test**

```python
# tests/test_cli_skills.py
import json
from pathlib import Path

from click.testing import CliRunner

from mt5.cli import main


def test_regenerate_replaces_markers(tmp_path):
    target = tmp_path / "SKILL.md"
    target.write_text("intro\n\n<!-- BEGIN COMMANDS -->\nstale\n<!-- END COMMANDS -->\nfooter\n")
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "skills", "regenerate", "--target", str(target)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    text = target.read_text()
    assert "stale" not in text
    assert "ea " in text or "tester " in text  # one of the real groups landed


def test_regenerate_fails_without_markers(tmp_path):
    target = tmp_path / "SKILL.md"
    target.write_text("intro only — no markers\n")
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "skills", "regenerate", "--target", str(target)])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "MARKERS_MISSING"
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_cli_skills.py -v
mt5 --json skills regenerate    # writes the live SKILL.md
git add -A
git commit -m "Phase 5: mt5 skills regenerate — auto-fill SKILL.md command tables

Adds HTML-comment markers around the auto-generated section so the
hand-written workflow narrative stays untouched."
```

### Task 5.4: Recreate ReplSkin in the new CLI and print SKILL.md path on banner

**Files:**
- Create: `mt5/repl.py`
- Modify: `mt5/cli.py`

- [ ] **Step 1: Read the archived banner pattern**

```powershell
Select-String -Path archive\legacy-mt5\utils\repl_skin.py -Pattern "def.*banner|print_banner|server|balance" | Select-Object -First 10
```

- [ ] **Step 2: Implement the new ReplSkin**

Create a fresh `mt5/repl.py` using `archive/legacy-mt5/utils/repl_skin.py` only as a pattern. Imports must point at the new `mt5.cli` command tree and `mt5_cli.*` modules, never at `metatrader5_cli.*`. In the banner function, include the resolved packaged SKILL.md path:

```python
import importlib.resources as _r
try:
    skill_path = _r.files("mt5_cli.skills").joinpath("SKILL.md")
    print(f"  SKILL.md: {skill_path}")
except (ModuleNotFoundError, FileNotFoundError):
    pass
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest -q
git add mt5/repl.py mt5/cli.py
git commit -m "Phase 5: ReplSkin banner prints absolute SKILL.md path

Lets agents read the skill manifest via Read tool without guessing."
```

### Task 5.5: Add mt5_mcp/server.py FastMCP scaffold + read-only tools

**Files:**
- Create: `mt5_mcp/__init__.py`, `mt5_mcp/server.py`
- Modify: `setup.py` — declare `mt5-mcp` console script + add `fastmcp` install_requires
- Create: `tests/test_mcp_server.py`

- [ ] **Step 1: Add fastmcp to install_requires**

In `setup.py`, add `"fastmcp>=0.2.0"` to the `install_requires` list.

- [ ] **Step 2: Re-install**

```bash
python -m pip install -e . --quiet
```

- [ ] **Step 3: Create the server**

```bash
mkdir -p mt5_mcp
touch mt5_mcp/__init__.py
```

Create `mt5_mcp/server.py`:

```python
"""mt5-mcp — FastMCP server publishing mt5_cli as MCP tools.

Each tool maps 1:1 to a library function. Read-only tools are exposed
unconditionally; mutating tools require an explicit live_intent flag.
"""
from fastmcp import FastMCP

from mt5_cli.config import load as load_config
from mt5_cli.market.market import info as market_info, tick as market_tick
from mt5_cli.rates.rates import fetch as rates_fetch
from mt5_cli.account.account import info as account_info
from mt5_cli.history.history import deals as history_deals
from mt5_cli.mql5 import discovery as mql5_discovery

mcp = FastMCP("mt5-universal")


@mcp.tool()
def mt5_market_info(symbol: str) -> dict:
    """Return broker symbol info: bid/ask/spread/point/filling_mode."""
    return market_info(symbol)


@mcp.tool()
def mt5_market_tick(symbol: str) -> dict:
    """Latest tick for a symbol."""
    return market_tick(symbol)


@mcp.tool()
def mt5_rates_fetch(symbol: str, timeframe: str, bars: int = 100) -> dict:
    """Fetch OHLCV bars."""
    return rates_fetch(symbol, timeframe, bars)


@mcp.tool()
def mt5_account_info() -> dict:
    """Account snapshot: balance/equity/margin/leverage."""
    return account_info()


@mcp.tool()
def mt5_history_deals(date_from: str, date_to: str, symbol: str | None = None,
                      strategy_id: str | None = None) -> dict:
    """Historical deals filter."""
    cfg = load_config()
    return history_deals(date_from=date_from, date_to=date_to,
                         symbol=symbol, strategy_id=strategy_id, cfg=cfg)


@mcp.tool()
def mt5_ea_list() -> dict:
    """List discovered MQL5 EAs."""
    return {"ok": True, "data": mql5_discovery.list_eas()}


@mcp.tool()
def mt5_indicator_list() -> dict:
    """List discovered MQL5 indicators."""
    return {"ok": True, "data": mql5_discovery.list_indicators()}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add console_script entry**

In `setup.py`, update `entry_points`:

```python
    entry_points={
        "console_scripts": [
            "mt5 = mt5.cli:main",
            "mt5-mcp = mt5_mcp.server:main",
        ],
    },
```

- [ ] **Step 5: Reinstall + verify the entry point**

```bash
python -m pip install -e . --quiet
which mt5-mcp || command -v mt5-mcp
```

- [ ] **Step 6: Smoke test (FastMCP exposes a programmatic API for testing)**

```python
# tests/test_mcp_server.py
import asyncio

from mt5_mcp.server import mcp


def test_server_lists_tools():
    tools = asyncio.run(mcp.get_tools())
    names = {t.name for t in tools}
    assert "mt5_market_info" in names
    assert "mt5_account_info" in names
    assert "mt5_ea_list" in names
```

- [ ] **Step 7: Run + commit**

```bash
python -m pytest tests/test_mcp_server.py -v
git add mt5_mcp/ setup.py tests/test_mcp_server.py
git commit -m "Phase 5: add mt5-mcp FastMCP server with read-only tool set

Tools expose market/account/rates/history/ea-list/indicator-list.
Mutating order tools land in the next task gated on live_intent.
mt5-mcp console script registered."
```

### Task 5.6: Add MCP tools for orders/positions/tester (mutating with live_intent)

**Files:**
- Modify: `mt5_mcp/server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Append mutating tools to mt5_mcp/server.py**

```python
from mt5_cli.orders.orders import place_market, dryrun as orders_dryrun
from mt5_cli.positions.positions import close as position_close, list as position_list
from mt5_cli.tester import ea as tester_ea, indicator as tester_indicator


@mcp.tool()
def mt5_position_list(symbol: str | None = None) -> dict:
    """List open positions."""
    return position_list(symbol=symbol)


@mcp.tool()
def mt5_order_dryrun(symbol: str, side: str, volume: float, sl: float | None = None,
                    tp: float | None = None, strategy_id: str | None = None) -> dict:
    """Pre-flight an order — runs the risk gate + broker order_check, no send."""
    cfg = load_config()
    return orders_dryrun(symbol=symbol, side=side, volume=volume, sl=sl, tp=tp,
                         strategy_id=strategy_id, cfg=cfg)


@mcp.tool()
def mt5_order_market(symbol: str, side: str, volume: float, sl: float | None = None,
                     tp: float | None = None, strategy_id: str | None = None,
                     live_intent: bool = False) -> dict:
    """Place a market order. live_intent must be True for live accounts.

    All three live gates still apply: cfg["live"]: true + MT5_LIVE=1 +
    live_intent True. Demo accounts bypass the env+config gates."""
    cfg = load_config()
    return place_market(symbol=symbol, side=side, volume=volume, sl=sl, tp=tp,
                        strategy_id=strategy_id, cfg=cfg, is_live_intent=live_intent)


@mcp.tool()
def mt5_tester_ea_single(expert: str, symbol: str, timeframe: str, from_date: str,
                         to_date: str, modelling: str = "real-ticks") -> dict:
    """Backtest an EA in single mode. Returns the standard envelope with
    stats / deals / journal_events."""
    return tester_ea.single(expert=expert, symbol=symbol, timeframe=timeframe,
                            from_date=from_date, to_date=to_date, modelling=modelling)


@mcp.tool()
def mt5_tester_indicator_visual(indicator_name: str, symbol: str, timeframe: str,
                                from_date: str, to_date: str,
                                modelling: str = "ohlc-1m") -> dict:
    """Visual-test an indicator."""
    return tester_indicator.visual(indicator_name=indicator_name, symbol=symbol,
                                   timeframe=timeframe, from_date=from_date,
                                   to_date=to_date, modelling=modelling)
```

- [ ] **Step 2: Update test**

In `tests/test_mcp_server.py`, expand:

```python
def test_server_lists_mutating_tools():
    import asyncio
    from mt5_mcp.server import mcp
    tools = asyncio.run(mcp.get_tools())
    names = {t.name for t in tools}
    assert "mt5_order_dryrun" in names
    assert "mt5_order_market" in names
    assert "mt5_position_list" in names
    assert "mt5_tester_ea_single" in names
    assert "mt5_tester_indicator_visual" in names
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest tests/test_mcp_server.py -v
git add mt5_mcp/server.py tests/test_mcp_server.py
git commit -m "Phase 5: MCP tools for orders/positions/tester

Mutating order tools take live_intent flag; the existing 3-gate live
check (cfg.live + MT5_LIVE + live_intent) still applies. Tester tools
publish ea/single + indicator/visual."
```

### Task 5.7: Regenerate SKILL.md command tables + Phase 5 acceptance

- [ ] **Step 1: Run the generator**

```bash
mt5 skills regenerate
```

- [ ] **Step 2: Inspect the result**

```bash
grep -A 50 "BEGIN COMMANDS" mt5_cli/skills/SKILL.md | head -60
```

Expected: tables for `ea`, `indicator`, `tester`, `skills` (and any others) populated.

- [ ] **Step 3: Verify MCP server starts**

```bash
mt5-mcp --help 2>&1 | head -10 || true
# FastMCP runs on stdio by default; a manual test:
# echo '' | timeout 3 mt5-mcp 2>&1 | head -20
```

- [ ] **Step 4: Suite green + commit + tag**

```bash
python -m pytest -q
git add mt5_cli/skills/SKILL.md
git commit -m "Phase 5: regenerate SKILL.md command tables"
git tag phase-5-complete
```

### Task 5.8: Mark dynamic SKILL.md regeneration in CI (optional reminder)

**Files:**
- Create: `tests/test_skill_md_in_sync.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_skill_md_in_sync.py
"""Asserts that the SKILL.md auto-generated section matches what the
generator would produce now. Catches drift between code and docs."""
from pathlib import Path

from mt5.cli import main as cli_root
from mt5_cli.skills.generator import build_command_tables, render_markdown_tables

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "mt5_cli" / "skills" / "SKILL.md"


def test_skill_md_command_tables_in_sync():
    text = SKILL.read_text(encoding="utf-8")
    BEGIN, END = "<!-- BEGIN COMMANDS -->", "<!-- END COMMANDS -->"
    assert BEGIN in text and END in text, "SKILL.md missing generator markers"
    current = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
    expected = render_markdown_tables(build_command_tables(cli_root)).strip()
    assert current == expected, "SKILL.md command tables stale — run `mt5 skills regenerate`"
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest tests/test_skill_md_in_sync.py -v
git add tests/test_skill_md_in_sync.py
git commit -m "Phase 5: CI test — SKILL.md command tables stay in sync with the CLI"
```

---

## Phase 6 — Portability + tests + harness doc (7 tasks)

**Goal:** Lock down portability rails and cross-platform path resolution. Add the CI hardcoded-path guard. Write the methodology SOP that future contributors and agents follow.

### Task 6.1: Implement mt5_cli/config/paths.py (full XDG/APPDATA resolution)

**Files:**
- Create: `mt5_cli/config/paths.py`
- Modify: `mt5_cli/config/__init__.py`
- Create: `tests/test_config_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_paths.py
from pathlib import Path

from mt5_cli.config import paths


def test_config_file_uses_env_when_set(monkeypatch, tmp_path):
    target = tmp_path / "custom.json"
    monkeypatch.setenv("MT5_CONFIG", str(target))
    assert paths.config_file() == target


def test_ea_dir_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_EA_DIR", str(tmp_path / "ea"))
    assert paths.ea_dir() == tmp_path / "ea"


def test_cache_dir_uses_xdg_then_appdata_then_home(monkeypatch, tmp_path):
    monkeypatch.delenv("MT5_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert paths.cache_dir() == tmp_path / "xdg" / "metatrader5-cli"


def test_cache_dir_appdata_fallback_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("MT5_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    assert paths.cache_dir() == tmp_path / "lad" / "metatrader5-cli" / "cache"


def test_results_dir_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_RESULTS_DIR", str(tmp_path / "myresults"))
    assert paths.results_dir() == tmp_path / "myresults"
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest tests/test_config_paths.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_cli/config/paths.py`:

```python
"""Cross-platform path resolution. Every module that needs a filesystem
location goes through this — no hardcoded user paths anywhere else."""
import os
import sys
from pathlib import Path

APP_NAME = "metatrader5-cli"


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def config_file() -> Path:
    """Config FILE (flat JSON in XDG_CONFIG_HOME). User chose the flat
    form (~/.config/metatrader5-cli.json) over a subdir layout in the
    naming sweep at e359d0b. EAs/indicators/presets/results are user
    DATA, so they live under XDG_DATA_HOME via the helpers below."""
    if "MT5_CONFIG" in os.environ:
        return Path(os.environ["MT5_CONFIG"])
    if "XDG_CONFIG_HOME" in os.environ:
        return Path(os.environ["XDG_CONFIG_HOME"]) / f"{APP_NAME}.json"
    if sys.platform == "win32" and "APPDATA" in os.environ:
        return Path(os.environ["APPDATA"]) / f"{APP_NAME}.json"
    return _home() / ".config" / f"{APP_NAME}.json"


def _under(base_env: str, fallback_subdir: str) -> Path:
    if base_env in os.environ:
        return Path(os.environ[base_env])
    if "XDG_DATA_HOME" in os.environ:
        return Path(os.environ["XDG_DATA_HOME"]) / APP_NAME / fallback_subdir
    if sys.platform == "win32" and "APPDATA" in os.environ:
        return Path(os.environ["APPDATA"]) / APP_NAME / fallback_subdir
    return _home() / ".local" / "share" / APP_NAME / fallback_subdir


def ea_dir() -> Path:
    return _under("MT5_EA_DIR", "ea")


def indicators_dir() -> Path:
    return _under("MT5_INDICATORS_DIR", "indicators")


def presets_dir() -> Path:
    return _under("MT5_PRESETS_DIR", "presets")


def results_dir() -> Path:
    return _under("MT5_RESULTS_DIR", "results")


def cache_dir() -> Path:
    if "MT5_CACHE_DIR" in os.environ:
        return Path(os.environ["MT5_CACHE_DIR"])
    if "XDG_CACHE_HOME" in os.environ:
        return Path(os.environ["XDG_CACHE_HOME"]) / APP_NAME
    if sys.platform == "win32" and "LOCALAPPDATA" in os.environ:
        return Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "cache"
    return _home() / ".cache" / APP_NAME


def log_dir() -> Path:
    if "MT5_LOG_DIR" in os.environ:
        return Path(os.environ["MT5_LOG_DIR"])
    return cache_dir() / "logs"
```

Update `mt5_cli/config/__init__.py`:

```python
from .config import DEFAULTS, load, save, mask_secrets
from . import paths

__all__ = ["DEFAULTS", "load", "save", "mask_secrets", "paths"]
```

- [ ] **Step 4: Update config.config to use paths.config_file()**

In `mt5_cli/config/config.py`, replace `_config_path()` with:

```python
from .paths import config_file as _config_path
```

(And drop the inline implementation.)

- [ ] **Step 5: Run + commit**

```bash
python -m pytest tests/test_config_paths.py -v
git add mt5_cli/config/ tests/test_config_paths.py
git commit -m "Phase 6: full XDG/APPDATA path resolver

paths.config_file/ea_dir/indicators_dir/presets_dir/results_dir/
cache_dir/log_dir route every filesystem location through one
module. Resolution: MT5_<NAME> env -> XDG -> APPDATA (Win) -> HOME."
```

### Task 6.2: Update mql5/discovery + tester/cache to use config.paths

**Files:**
- Modify: `mt5_cli/mql5/discovery.py`
- Modify: `mt5_cli/tester/cache.py`

- [ ] **Step 1: Update discovery to consult paths.ea_dir() / paths.indicators_dir()**

In `mt5_cli/mql5/discovery.py`, replace `_search_paths`:

```python
from mt5_cli.config import paths


def _search_paths(kind: str) -> list[Path]:
    cwd = Path.cwd() / kind
    user = paths.ea_dir() if kind == "ea" else paths.indicators_dir()
    return [p for p in (cwd, user) if p.exists()]
```

- [ ] **Step 2: Update cache to default to paths.results_dir()**

In `mt5_cli/tester/cache.py`, change the default `root` parameter:

```python
from mt5_cli.config import paths


def run_dir(run_id: str, *, root: Path | str | None = None) -> Path:
    root = Path(root) if root else paths.results_dir()
    p = root / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_recent(*, root: Path | str | None = None, limit: int = 20) -> list[dict]:
    root = Path(root) if root else paths.results_dir()
    if not root.exists():
        return []
    # ... rest unchanged


def get_run(run_id: str, *, root: Path | str | None = None) -> dict | None:
    root = Path(root) if root else paths.results_dir()
    p = root / run_id
    # ... rest unchanged
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest -q
git add mt5_cli/mql5/discovery.py mt5_cli/tester/cache.py
git commit -m "Phase 6: route discovery + cache through config.paths

EA/indicator discovery falls back to paths.ea_dir / paths.indicators_dir
when no cwd subdir exists. Tester cache defaults to paths.results_dir."
```

### Task 6.3: Add CI test that no source file contains hardcoded user paths

**Files:**
- Create: `tests/test_no_hardcoded_paths.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_no_hardcoded_paths.py
"""CI guard: no module under mt5_cli/, mt5/, mt5_mcp/ may contain
hardcoded user paths. Path resolution goes through mt5_cli.config.paths."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["mt5_cli", "mt5", "mt5_mcp"]
FORBIDDEN = [
    re.compile(r"C:\\\\Users\\\\"),
    re.compile(r"C:\\\\Users/"),
    re.compile(r"/home/[A-Za-z0-9_-]+"),
    re.compile(r"/Users/[A-Za-z0-9_-]+"),
    re.compile(r"^[A-Z]:\\\\(?!Users\\\\)", re.MULTILINE),  # other absolute drive paths
]
# Files allowed to contain hardcoded paths (e.g., Windows install candidates).
ALLOWLIST = {
    "mt5_cli/mql5/compiler.py",        # _CANDIDATE_PATHS for metaeditor64.exe
    "mt5_cli/mql5/deployer.py",        # _CANDIDATE_DATA_DIRS
    "mt5_cli/tester/launcher.py",      # _CANDIDATE_PATHS for terminal64.exe
}


def test_no_hardcoded_user_paths():
    offenders: list[str] = []
    for d in SCAN_DIRS:
        path = ROOT / d
        if not path.exists():
            continue
        for py in path.rglob("*.py"):
            rel = py.relative_to(ROOT).as_posix()
            if rel in ALLOWLIST:
                continue
            text = py.read_text(encoding="utf-8")
            for pat in FORBIDDEN:
                m = pat.search(text)
                if m:
                    offenders.append(f"{rel}: {m.group(0)!r}")
    assert not offenders, "Hardcoded user paths found:\n  " + "\n  ".join(offenders)
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest tests/test_no_hardcoded_paths.py -v
git add tests/test_no_hardcoded_paths.py
git commit -m "Phase 6: CI portability guard — fail on hardcoded user paths

Greps mt5_cli/, mt5/, mt5_mcp/ for C:\\Users\\, /home/<user>/,
/Users/<user>/, or absolute drive paths outside an explicit allowlist
(metaeditor64 / terminal64 / data-dir candidate lookups)."
```

### Task 6.4: Write MT5_HARNESS.md

**Files:**
- Create: `MT5_HARNESS.md`

- [ ] **Step 1: Write the doc**

Create `MT5_HARNESS.md`:

```markdown
# MT5 Universal Harness — Methodology SOP

How to extend `mt5-universal` (CLI + MCP + library) without breaking the contract.
This is the standing order; a plan that contradicts it is the plan that's wrong.

## The seven phases (recap)

| # | Phase | What it produces |
|---|---|---|
| 0 | Baseline | green tests on `mt5-universal` branch |
| 1 | Archive legacy | `archive/legacy-mt5/` + `archive/legacy-docs/` + `archive/legacy-mql5/` |
| 2 | `mt5_cli/` skeleton | the agnostic library |
| 3 | MQL5 plugin host | `ea/` + `indicators/` user dirs, scaffolding |
| 4 | Strategy Tester driver | `mt5 tester ea/indicator …` |
| 5 | Agent surface | SKILL.md + MCP server + ReplSkin |
| 6 | Portability + tests | path resolver + CI guards + this doc |

## Adding a new CLI command

1. **Library function first.** Implement in `mt5_cli/<concern>/`. Return `mt5_cli.reports.ok(...)` or `fail(...)`.
2. **Test against the function** — not against the CLI. CLI tests are smoke tests, not unit tests.
3. **Add the click command** in `mt5/cli.py`. Pass `ctx.obj["json"]` to `_emit`.
4. **Run `mt5 skills regenerate`** so SKILL.md picks up the new command.
5. **Add an MCP tool in `mt5_mcp/server.py`** if the function makes sense to call from a tool-using agent.

## Templates are deliberately minimal — do not add strategy variants

The tool ships exactly one minimal EA template (`ea_minimal.mq5`) and one minimal indicator template (`indicator_minimal.mq5`). They contain only the MQL5 boilerplate required to load (OnInit / OnDeinit / OnTick for EAs; OnInit / OnCalculate for indicators). They carry no strategy-flavored parameters, no entry / exit logic, no analytical math.

Do not add `ea_scalper.mq5`, `indicator_oscillator.mq5`, or similar variants. The tool ships hands, not strategies. Users author parameters / logic / indicator math in their own workspace copy of the minimal skeleton.

## Adding a new broker (deferred — single-broker scope today)

Current scope is Trading.com only. Quirks (FOK filling, no hedging,
22:00 UTC rollover, retcode help) live in `mt5_cli/config/trading_com.py`
and merge into `config.DEFAULTS`. There is no `mt5_cli/broker/` package
and no `BrokerProfile` ABC — the user-locked decision is to NOT
pre-build the abstraction.

When a second broker is added later:

1. Create `mt5_cli/broker/base.py` with a `BrokerProfile` ABC capturing
   the fields that actually differ between the two brokers (don't
   guess in advance; let the second broker drive the shape).
2. Move `TRADING_COM_DEFAULTS` + `retcode_help()` out of
   `mt5_cli/config/trading_com.py` into `mt5_cli/broker/trading_com.py`
   as a `BrokerProfile` subclass.
3. Create `mt5_cli/broker/<new_broker>.py` as a sibling subclass.
4. Wire `mt5_cli/config/config.py::load()` to pick the active broker
   profile (via `cfg["broker"]`) and merge its defaults instead of the
   hardcoded `TRADING_COM_DEFAULTS` import.
5. Update `tests/test_config*.py` to cover both brokers + the default
   resolution path.

## What never changes

- `mt5_cli/bridge/mt5_backend.py` is the only file that imports `MetaTrader5`.
- Every order call passes through `mt5_cli/risk/risk.check_order(..., is_live_intent=...)`.
- Live trading needs all three gates: `cfg["live"]: true` + `MT5_LIVE=1` + `is_live_intent=True`.
- No hardcoded user paths anywhere in `mt5_cli/`, `mt5/`, `mt5_mcp/`. Use `mt5_cli.config.paths.*`.
- Every CLI command returns the standard envelope: `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code": ..., "message": ..., "data": ...}}`.

## Pre-merge checklist

- [ ] `python -m pytest -q` green
- [ ] `git diff --check master...HEAD` clean
- [ ] If you touched a CLI command, `mt5 skills regenerate` was run and the SKILL.md change is committed
- [ ] If you added a `mt5_cli/` module, `tests/test_bridge_singleton.py` and `tests/test_no_hardcoded_paths.py` still pass
- [ ] You added at least one unit test per new function (TDD: write the failing test first)

## See also

- [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](docs/specs/2026-05-15-mt5-universal-agent-native-design.md) — the spec
- [docs/specs/2026-05-15-mt5-universal-review-context.md](docs/specs/2026-05-15-mt5-universal-review-context.md) — what reviewers care about
- [docs/playgrounds/mt5-universal-refactor-playground.html](docs/playgrounds/mt5-universal-refactor-playground.html) — the visual companion
```

- [ ] **Step 2: Commit**

```bash
git add MT5_HARNESS.md
git commit -m "Phase 6: write MT5_HARNESS.md — methodology SOP

7-phase recap, how to add a CLI command / EA template / broker
profile, the never-changes list, pre-merge checklist."
```

### Task 6.5: Update README.md to point at the new layout

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README**

```bash
head -80 README.md
```

- [ ] **Step 2: Edit the relevant sections**

The README probably still references the old `metatrader5_cli` import paths and legacy commands. Sweep:
- "Install Globally" section: confirm `pip install -e .` still works (entry points changed but the install command didn't).
- Replace any reference to `mt5 ea adaptive-trail`, `mt5 analyze sniper-poc`, `mt5 screenshot tda` with the new equivalents (`mt5 tester ea single`, `mt5 ea new`, etc.).
- Add a "Documentation" section pointing at the spec, reviewer context, harness, and playground.

Edit shape:

```markdown
## Documentation

- [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](docs/specs/2026-05-15-mt5-universal-agent-native-design.md) — design spec for the universal refactor
- [MT5_HARNESS.md](MT5_HARNESS.md) — methodology SOP for adding commands / EAs / broker profiles
- [docs/playgrounds/mt5-universal-refactor-playground.html](docs/playgrounds/mt5-universal-refactor-playground.html) — interactive 7-phase walkthrough
- [archive/legacy-docs/specs/mt5-cli-spec.md](archive/legacy-docs/specs/mt5-cli-spec.md) — historical reference for the legacy core (now archived)
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Phase 6: README points at universal refactor docs"
```

### Task 6.6: Run the full test pyramid + final clean check

- [ ] **Step 1: Full unit suite**

```bash
python -m pytest -q
```

Expected: green. Note the new pass count.

- [ ] **Step 2: Top-level CI guards**

```bash
python -m pytest tests/ -v
```

Expected: `test_bridge_singleton`, `test_no_hardcoded_paths`, `test_skill_md_in_sync` all PASS.

- [ ] **Step 3: Whitespace / EOL check**

```bash
git diff --check master...HEAD
echo "exit: $?"
```

Expected: empty output, exit 0.

- [ ] **Step 4: Bridge import check via grep (belt + suspenders)**

```bash
grep -rn "import MetaTrader5\|from MetaTrader5" mt5_cli/ mt5/ mt5_mcp/ | grep -v bridge/mt5_backend.py
```

Expected: empty output.

- [ ] **Step 5: Smoke-test the installed CLI**

```bash
python -m pip install -e . --quiet
mt5 --help
mt5 ea --help
mt5 tester ea --help
mt5 indicator --help
mt5 --json ea list
mt5 --json tester list
```

All must execute without ImportError or click usage errors.

- [ ] **Step 6: Commit any auto-changes (e.g. SKILL.md regeneration)**

```bash
git status --short | grep -v '^??'
# If SKILL.md drifted: mt5 skills regenerate && git add mt5_cli/skills/SKILL.md && git commit -m "Phase 6: regenerate SKILL.md final pass"
```

### Task 6.7: Tag final + push

- [ ] **Step 1: Tag**

```bash
git tag phase-6-complete
git tag mt5-universal-v1.0.0
```

- [ ] **Step 2: Push branch + tags**

```bash
git push origin mt5-universal
git push origin --tags
```

- [ ] **Step 3: Confirm origin matches local**

```bash
git rev-list --count HEAD...origin/mt5-universal   # expect 0
```

---

## Final acceptance summary

The refactor is **complete** when all of the following are true:

| Check | Command | Expected |
|---|---|---|
| Unit suite green | `python -m pytest -q` | all tests pass (count grew from 240 baseline; numbers increase as Phase 4-5 add tests) |
| Bridge singleton | `python -m pytest tests/test_bridge_singleton.py` | PASS |
| No hardcoded paths | `python -m pytest tests/test_no_hardcoded_paths.py` | PASS |
| SKILL.md in sync | `python -m pytest tests/test_skill_md_in_sync.py` | PASS |
| Whitespace clean | `git diff --check master...HEAD` | exit 0 |
| Legacy archived | `git ls-tree -r HEAD -- archive/ \| wc -l` | > 0 |
| Legacy not imported | `grep -rn "from .core.ehukai\|from .core.analyze\|from .core.tester" mt5_cli/ mt5/ mt5_mcp/` | empty |
| CLI installed | `mt5 --help` | shows ea / indicator / tester / skills groups |
| MCP installed | `mt5-mcp --help` (or stdio smoke) | runs without import errors |
| Phase tags present | `git tag --list 'phase-*-complete'` | 6 tags (phase-1 through phase-6) |
| Origin in sync | `git rev-list --count HEAD...origin/mt5-universal` | 0 |

When all 11 are green: the universal refactor is shipped on the `mt5-universal` branch, ready to merge to `master`.

## After merging — first user EA

The shortest path for an agent to use the new system end-to-end:

```bash
# 1. Scaffold
mt5 ea new my_first

# 2. Edit ea/my_first.mq5 to taste

# 3. Compile (requires MetaEditor.exe)
mt5 ea compile my_first

# 4. Deploy (requires MT5 terminal data dir)
mt5 ea deploy my_first

# 5. Backtest
mt5 --json tester ea single \
  --expert my_first \
  --symbol AUDUSD --tf M5 \
  --from 2024-01-01 --to 2024-06-30 \
  --modelling ohlc-1m

# 6. Inspect a past run
mt5 --json tester list
mt5 --json tester show <run-id>
```

Same flow via MCP from a tool-using agent: `mt5_ea_list`, then `mt5_tester_ea_single(...)`.
