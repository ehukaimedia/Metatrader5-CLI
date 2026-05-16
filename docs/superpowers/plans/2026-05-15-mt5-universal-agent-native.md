# MT5 Universal — Agent-Native CLI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-fork the existing tangled `metatrader5_cli/mt5/core/` into an agnostic, agent-native Python library at `mt5_universal/` that drives MT5's native Strategy Tester from the CLI, publishes itself as both a `mt5` CLI and a `mt5-mcp` MCP server, and treats Trading.com as the canonical (but not hardcoded) broker profile.

**Architecture:** Library-first. One Python package (`mt5_universal/`) with submodule-per-concern (bridge, broker, market, rates, orders, positions, account, history, risk, indicators, mql5, tester, config, reports, skills). The `mt5` CLI and `mt5-mcp` MCP server are thin wrappers over the same library. MQL5 is the canonical author format for EAs and indicators; MT5 Strategy Tester is the canonical backtest engine. No Python event-driven backtester. No coexistence shims with the legacy core.

**Tech Stack:** Python 3.10+, Click 8.x (CLI), FastMCP (MCP server), MetaTrader5 Python package (bridge, Windows-only), pandas + pandas-ta (indicators quicklook), pytest (tests), MetaEditor.exe + terminal64.exe (subprocess targets).

## References (read before starting)

| | |
|---|---|
| Spec | [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](../../specs/2026-05-15-mt5-universal-agent-native-design.md) |
| Reviewer context | [docs/specs/2026-05-15-mt5-universal-review-context.md](../../specs/2026-05-15-mt5-universal-review-context.md) |
| Visual companion | [docs/playgrounds/mt5-universal-refactor-playground.html](../../playgrounds/mt5-universal-refactor-playground.html) |
| Current canonical CLI spec (v0.5) | [docs/specs/mt5-cli-spec.md](../../specs/mt5-cli-spec.md) |
| CLI-Anything cherry-pick source | https://github.com/HKUDS/CLI-Anything |

## Locked decisions (do not re-litigate)

See spec §4 and reviewer context §2. Summary: hard fork; MQL5 canonical author format; MT5 Strategy Tester is THE engine; library-first; MCP+CLI dual surface; Trading.com canonical default; portability rails; SKILL.md migrated not replaced.

## Pre-flight (one-time setup before Phase 1)

- [ ] **Step P1: Verify branch and clean working tree**

```bash
git branch --show-current   # expect: mt5-universal
git status --short          # untracked OK; no modified or staged
```

- [ ] **Step P2: Verify green baseline**

```bash
python -m pytest -q
```

Expected: `240 passed, 1 skipped`.

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
│   ├── legacy-core/                      # everything moved out of metatrader5_cli/mt5/core/
│   └── legacy-mql5/                      # full MQL5 tree
├── mt5_universal/                        # NEW — agnostic library
│   ├── bridge/mt5_backend.py             # ONLY file that imports MetaTrader5
│   ├── broker/{base,trading_com,generic_mt5}.py
│   ├── market/, rates/, orders/, positions/, account/, history/, risk/
│   ├── indicators/builtins.py            # python quicklook only
│   ├── mql5/{compiler,deployer,discovery}.py + templates/
│   ├── tester/{ea,indicator,ini_builder,launcher,results,cache}.py
│   ├── config/{__init__,paths}.py
│   ├── reports/__init__.py
│   └── skills/SKILL.md                   # migrated from metatrader5_cli/mt5/skills/
├── mt5/                                  # NEW — thin CLI wrapper
│   ├── __main__.py
│   └── cli.py
├── mt5_mcp/                              # NEW — FastMCP server
│   └── server.py
├── ea/                                   # NEW — user MQL5 EAs (auto-discovered)
│   ├── .gitkeep
│   └── examples/ema_crossover.mq5
├── indicators/                           # NEW — user MQL5 indicators
│   ├── .gitkeep
│   └── examples/donchian.mq5
├── presets/.gitkeep                      # NEW — tester .set files per strategy
├── results/                              # NEW — tester run snapshots (.gitignore)
├── tests/test_no_hardcoded_paths.py      # NEW — CI portability guard
├── MT5_HARNESS.md                        # NEW — methodology SOP
├── setup.py                              # MODIFIED — declares mt5 + mt5-mcp scripts
├── pytest.ini                            # MODIFIED — add new test paths
└── .gitignore                            # MODIFIED — remove archive/, add results/
```

The legacy `metatrader5_cli/` package is fully archived after Phase 1 — nothing imports from it.

---

## Phase 1 — Archive legacy (5 tasks)

**Goal:** Move all Ehukai/TDA-specific code and the full MQL5 tree to `archive/`. Strip imports from the legacy CLI. Tests still pass for surviving modules. No compat shims.

### Task 1.1: Commit untracked Advanced Wavelet sources

**Files:**
- Stage: `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/`
- Skip: `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System.zip` (gitignored by `*.zip`)

- [ ] **Step 1: Confirm source is on disk**

```bash
ls metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/ | head
```

- [ ] **Step 2: Stage and commit so the move in Task 1.4 is captured in history**

```bash
git add metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/
git commit -m "Capture Advanced_Wavelet_Entry_System sources before archive

Per spec Phase 1 prerequisite: untracked MQL5 source must be in git
history before the archive move so the move is recoverable."
```

- [ ] **Step 3: Verify**

```bash
git ls-files metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/ | wc -l   # expect > 0
```

### Task 1.2: Remove `archive/` exclusion from .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Read current .gitignore**

```bash
grep -n '^archive/' .gitignore   # confirm the line exists, note line number
```

- [ ] **Step 2: Remove the `archive/` line**

Use Edit tool. Find:
```
.ehukaiconnect/
archive/
```
Replace with:
```
.ehukaiconnect/
```

- [ ] **Step 3: Verify exclusion is gone**

```bash
grep -n '^archive/' .gitignore && echo "STILL THERE" || echo "REMOVED"
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "Remove archive/ exclusion so Phase 1 archive move is git-tracked"
```

### Task 1.3: Move legacy core modules to archive/legacy-core/

**Files:**
- Move: `metatrader5_cli/mt5/core/{ehukai,analyze,tda_manifest,mfe,tester,ea,chart,screenshot,project,playground_data,indicator}.py` → `archive/legacy-core/`
- Keep in place: `metatrader5_cli/mt5/core/{account,history,market,order,position,rates,risk}.py` (these survive — they're the agnostic primitives that get re-homed in Phase 2)

- [ ] **Step 1: Create archive target directory**

```bash
mkdir -p archive/legacy-core
```

- [ ] **Step 2: Move the domain-coupled modules with `git mv` (preserves history)**

```bash
git mv metatrader5_cli/mt5/core/ehukai.py         archive/legacy-core/ehukai.py
git mv metatrader5_cli/mt5/core/analyze.py        archive/legacy-core/analyze.py
git mv metatrader5_cli/mt5/core/tda_manifest.py   archive/legacy-core/tda_manifest.py
git mv metatrader5_cli/mt5/core/mfe.py            archive/legacy-core/mfe.py
git mv metatrader5_cli/mt5/core/tester.py         archive/legacy-core/tester.py
git mv metatrader5_cli/mt5/core/ea.py             archive/legacy-core/ea.py
git mv metatrader5_cli/mt5/core/chart.py          archive/legacy-core/chart.py
git mv metatrader5_cli/mt5/core/screenshot.py     archive/legacy-core/screenshot.py
git mv metatrader5_cli/mt5/core/project.py        archive/legacy-core/project.py
git mv metatrader5_cli/mt5/core/playground_data.py archive/legacy-core/playground_data.py
git mv metatrader5_cli/mt5/core/indicator.py      archive/legacy-core/indicator.py
```

- [ ] **Step 3: Confirm only the agnostic primitives remain in core/**

```bash
ls metatrader5_cli/mt5/core/
```

Expected (besides `__init__.py`, `__pycache__/`):
`account.py history.py market.py order.py position.py rates.py risk.py`

- [ ] **Step 4: Don't commit yet — coupled with Task 1.4 + 1.5**

### Task 1.4: Move full MQL5 tree to archive/legacy-mql5/

**Files:**
- Move: `metatrader5_cli/mt5/mql5/` → `archive/legacy-mql5/`
- Drop: the three `.zip` snapshots (recoverable from the directories; not in git history)

- [ ] **Step 1: Create archive target**

```bash
mkdir -p archive/legacy-mql5
```

- [ ] **Step 2: Move tracked MQL5 contents (Experts, Hybrid_WPVS_MT5_Bundle, Indicators, Advanced_Wavelet_Entry_System)**

```bash
git mv metatrader5_cli/mt5/mql5/Experts                  archive/legacy-mql5/Experts
git mv metatrader5_cli/mt5/mql5/Hybrid_WPVS_MT5_Bundle   archive/legacy-mql5/Hybrid_WPVS_MT5_Bundle
git mv metatrader5_cli/mt5/mql5/Indicators               archive/legacy-mql5/Indicators
git mv metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System archive/legacy-mql5/Advanced_Wavelet_Entry_System
```

- [ ] **Step 3: Drop the on-disk-only zip snapshots**

```bash
rm metatrader5_cli/mt5/mql5/Hybrid_WPVS_MT5_Bundle.zip
rm metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System.zip
rm metatrader5_cli/mt5/mql5/WF_FractalPredictor_MQ5_v1_10.zip
```

- [ ] **Step 4: Remove the now-empty mql5 directory**

```bash
rmdir metatrader5_cli/mt5/mql5
```

- [ ] **Step 5: Verify**

```bash
ls metatrader5_cli/mt5/ | grep mql5 && echo "STILL THERE" || echo "REMOVED"
ls archive/legacy-mql5/   # expect: Experts Hybrid_WPVS_MT5_Bundle Indicators Advanced_Wavelet_Entry_System
```

### Task 1.5: Strip legacy imports from mt5_cli.py and prune orphaned commands

**Files:**
- Modify: `metatrader5_cli/mt5/mt5_cli.py`
- Modify: `metatrader5_cli/mt5/utils/repl_skin.py` if it imports any archived module
- Modify: `setup.py` — `package_data` references `mql5/Indicators/*.mq5` and `mql5/Experts/*.mq5` which no longer exist in that location
- Modify: `metatrader5_cli/mt5/tests/test_core.py` — remove tests for archived modules
- Modify: `metatrader5_cli/mt5/tests/test_decoupling.py` — same
- Move: `metatrader5_cli/mt5/tests/` tests for archived modules → `archive/legacy-core/tests/` (kept as historical reference, not run by default)

- [ ] **Step 1: Find all imports of archived modules**

```bash
grep -rn "from .core.ehukai\|from .core.analyze\|from .core.tda_manifest\|from .core.mfe\|from .core.tester\|from .core.ea\|from .core.chart\|from .core.screenshot\|from .core.project\|from .core.indicator\|from .core.playground_data" metatrader5_cli/
```

Note every hit. These are the imports to delete or relocate.

- [ ] **Step 2: Remove those imports from mt5_cli.py**

Open `metatrader5_cli/mt5/mt5_cli.py`. For each import found in Step 1:
1. Delete the import line.
2. Find every Click command that uses that import (search for the function name).
3. Delete the entire `@main.command(...)` or `@<group>.command(...)` block, including its decorators and body.

After this, `mt5_cli.py` should only contain commands that use:
`account, history, market, order, position, rates, risk` (the surviving primitives) plus `config`, `repl`.

- [ ] **Step 3: Update setup.py package_data**

Edit `setup.py`. Replace:

```python
    package_data={
        "metatrader5_cli.mt5": [
            "mql5/Indicators/*.mq5",
            "mql5/Experts/*.mq5",
        ],
    },
```

With:

```python
    package_data={
        "metatrader5_cli.mt5": [
            "skills/SKILL.md",
        ],
    },
```

- [ ] **Step 4: Move tests for archived modules to archive/legacy-core/tests/**

```bash
mkdir -p archive/legacy-core/tests
```

Then: identify test classes/functions in `metatrader5_cli/mt5/tests/test_core.py` that test the archived modules (TestAnalyze, TestChart, TestScreenshot, TestEhukai, TestTester, TestEa, TestTdaManifest, TestMfe, TestIndicator, TestProject — anything whose subject was archived). Move each to a per-module file under `archive/legacy-core/tests/`, e.g., `archive/legacy-core/tests/test_analyze.py`.

If splitting is too granular, a single `archive/legacy-core/tests/test_legacy.py` with all relocated classes is acceptable.

The current `metatrader5_cli/mt5/tests/test_core.py` keeps only test classes for surviving modules: `TestBridge, TestMarket, TestRates, TestAccount, TestRisk, TestOrder, TestPosition, TestHistory, TestKillSwitch, TestRepl`.

- [ ] **Step 5: Update pytest.ini to exclude archive/**

Add to `pytest.ini`:

```ini
[pytest]
testpaths =
    metatrader5_cli/mt5/tests
markers =
    integration: tests requiring a live MT5 terminal (deselect with -m "not integration")
norecursedirs = archive
```

- [ ] **Step 6: Run tests — expect significantly fewer to remain green**

```bash
python -m pytest -q
```

Some tests will fail because their imports reference now-archived modules. For each failure: either (a) the test belongs in `archive/legacy-core/tests/` (move it) or (b) the test exercises a surviving module and just needs an import path update (fix it).

Iterate until: green on the surviving suite. Note the new pass count — it WILL be lower than 240 because the archived test classes are excluded.

- [ ] **Step 7: Commit Phase 1 in one atomic move-commit**

```bash
git add -A
git commit -m "Phase 1: archive legacy core + MQL5 tree

Moved the Ehukai/TDA/wavelet/Hybrid-WPVS-flavored modules and the
full mql5/ tree under archive/. Stripped legacy imports from
mt5_cli.py and pruned orphaned commands. No mt5-legacy compat shim,
no quarantine entry point — per locked hard-fork rule.

Surviving primitives stay in metatrader5_cli/mt5/core/ until Phase 2
re-homes them under mt5_universal/.

Tests for archived modules moved to archive/legacy-core/tests/ as
historical reference, excluded from the live suite via pytest.ini
norecursedirs."
```

- [ ] **Step 8: Phase 1 acceptance check**

```bash
python -m pytest -q                                    # green on surviving suite
git ls-tree -r HEAD -- archive/ | wc -l                # > 0 (legacy code in git history)
grep -r "from .core.ehukai\|from .core.analyze\|from .core.tester" metatrader5_cli/ && echo "STILL IMPORTING ARCHIVED" || echo "CLEAN"
ls metatrader5_cli/mt5/core/                           # only agnostic primitives
```

All four must pass. **Tag this commit:** `git tag phase-1-complete`.

---

## Phase 2 — `mt5_universal/` skeleton (12 tasks)

**Goal:** Create the new agnostic library. Move surviving primitives from `metatrader5_cli/mt5/core/` to `mt5_universal/<concern>/`. Add `broker/` abstraction with Trading.com as default. Add `config/` and `indicators/` (python quicklook).

### Task 2.1: Create mt5_universal/ package skeleton

**Files:**
- Create: `mt5_universal/__init__.py`
- Create: `mt5_universal/{bridge,broker,market,rates,orders,positions,account,history,risk,indicators,mql5,tester,config,reports,skills}/__init__.py`

- [ ] **Step 1: Create the package directory tree**

```bash
mkdir -p mt5_universal/{bridge,broker,market,rates,orders,positions,account,history,risk,indicators,mql5,tester,config,reports,skills}
```

- [ ] **Step 2: Add empty `__init__.py` to each (so pytest discovers them)**

```bash
for d in mt5_universal mt5_universal/bridge mt5_universal/broker mt5_universal/market mt5_universal/rates mt5_universal/orders mt5_universal/positions mt5_universal/account mt5_universal/history mt5_universal/risk mt5_universal/indicators mt5_universal/mql5 mt5_universal/tester mt5_universal/config mt5_universal/reports mt5_universal/skills; do touch "$d/__init__.py"; done
```

- [ ] **Step 3: Verify**

```bash
find mt5_universal -name __init__.py | wc -l   # expect 16
```

- [ ] **Step 4: Don't commit yet — coupled with Task 2.2**

### Task 2.2: Move bridge from utils/mt5_backend.py to mt5_universal/bridge/

**Files:**
- Move: `metatrader5_cli/mt5/utils/mt5_backend.py` → `mt5_universal/bridge/mt5_backend.py`
- Update: `mt5_universal/bridge/__init__.py` to re-export the public API
- Update: any callers in surviving primitives (`metatrader5_cli/mt5/core/{account,history,market,order,position,rates,risk}.py`)

- [ ] **Step 1: Find all callers of the bridge**

```bash
grep -rn "from ..utils.mt5_backend\|from .utils.mt5_backend\|mt5_backend" metatrader5_cli/ | grep -v __pycache__
```

- [ ] **Step 2: Move the bridge file**

```bash
git mv metatrader5_cli/mt5/utils/mt5_backend.py mt5_universal/bridge/mt5_backend.py
```

- [ ] **Step 3: Set up the package re-export**

Write `mt5_universal/bridge/__init__.py`:

```python
"""Bridge layer — the ONLY module in the codebase allowed to import MetaTrader5.

Public re-exports keep callers from reaching into mt5_backend directly.
"""
from .mt5_backend import (
    connect,
    mt5_call,
    ensure_symbol,
    reconnect_once,
)

__all__ = ["connect", "mt5_call", "ensure_symbol", "reconnect_once"]
```

- [ ] **Step 4: Update each caller's import**

For every hit from Step 1, change the import to:

```python
from mt5_universal.bridge import mt5_call, connect, ensure_symbol, reconnect_once
```

(Drop only the names that file actually uses.)

- [ ] **Step 5: Run tests**

```bash
python -m pytest -q
```

Expected: same number of passing tests as end of Phase 1 (the bridge moved but its API is unchanged).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Phase 2: move bridge to mt5_universal/bridge/

The single-bridge rule (only file that imports MetaTrader5) is now
enforced at the package boundary. Callers import from mt5_universal.bridge."
```

### Task 2.3: Move surviving primitives to mt5_universal/

**Files:**
- Move: `metatrader5_cli/mt5/core/{account,history,market,order,position,rates,risk}.py` → `mt5_universal/{account,history,market,orders,positions,rates,risk}/<file>.py`
  - Note rename: `core/order.py` → `mt5_universal/orders/orders.py`, `core/position.py` → `mt5_universal/positions/positions.py` (singular file → plural folder match)
- Update: each file's internal imports (bridge already done in 2.2; just risk-chain inter-imports remain)
- Update: `mt5_universal/<each>/__init__.py` to re-export the public API
- Update: tests' import paths

- [ ] **Step 1: Move each primitive (one git mv per file)**

```bash
git mv metatrader5_cli/mt5/core/account.py  mt5_universal/account/account.py
git mv metatrader5_cli/mt5/core/history.py  mt5_universal/history/history.py
git mv metatrader5_cli/mt5/core/market.py   mt5_universal/market/market.py
git mv metatrader5_cli/mt5/core/rates.py    mt5_universal/rates/rates.py
git mv metatrader5_cli/mt5/core/risk.py     mt5_universal/risk/risk.py
git mv metatrader5_cli/mt5/core/order.py    mt5_universal/orders/orders.py
git mv metatrader5_cli/mt5/core/position.py mt5_universal/positions/positions.py
```

- [ ] **Step 2: Wire each package's `__init__.py`**

For each of `account, history, market, rates, risk`, write `mt5_universal/<name>/__init__.py`:

```python
from .<name> import *  # noqa: F401,F403
```

For `orders` and `positions` (where the file is named differently from the package), write `mt5_universal/orders/__init__.py`:

```python
from .orders import *  # noqa: F401,F403
```

And `mt5_universal/positions/__init__.py`:

```python
from .positions import *  # noqa: F401,F403
```

- [ ] **Step 3: Fix risk-chain inter-imports**

`mt5_universal/orders/orders.py` likely has `from .risk import check_order` (or `from ..risk import...`). Replace with absolute imports:

```python
from mt5_universal.risk import check_order, compute_volume_from_risk_pct, resolve_magic
```

`mt5_universal/account/account.py` and `mt5_universal/history/history.py` have similar references — convert all to absolute `mt5_universal.*` imports.

- [ ] **Step 4: Update test imports**

In `metatrader5_cli/mt5/tests/test_core.py`, change every:

```python
from ..core.account import ...
from metatrader5_cli.mt5.core.risk import ...
```

to:

```python
from mt5_universal.account import ...
from mt5_universal.risk import ...
```

Similarly for `conftest.py` if it imports from old paths.

- [ ] **Step 5: Run tests**

```bash
python -m pytest -q
```

Expected: same green count as before.

- [ ] **Step 6: Confirm legacy core dir is now empty (besides __init__.py and __pycache__)**

```bash
ls metatrader5_cli/mt5/core/
```

Expected: just `__init__.py` and `__pycache__`. If so, delete the empty package:

```bash
rm metatrader5_cli/mt5/core/__init__.py
rmdir metatrader5_cli/mt5/core
```

If `mt5_cli.py` still imports from `.core`, fix those imports to point at `mt5_universal.*` first.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Phase 2: re-home surviving primitives under mt5_universal/

account, history, market, rates, risk move to mt5_universal/<name>/.
orders (was order) and positions (was position) move with package
rename. All risk-chain and bridge imports use absolute paths.
Legacy metatrader5_cli/mt5/core/ removed."
```

### Task 2.4: Add config layer with 4-layer resolution

**Files:**
- Create: `mt5_universal/config/__init__.py`
- Create: `mt5_universal/config/config.py` (the resolution logic)
- Create: `metatrader5_cli/mt5/tests/test_config.py`

(`paths.py` lands in Phase 6 with the full portability rails. This task only does the 4-layer settings resolver.)

- [ ] **Step 1: Write the failing test**

Create `metatrader5_cli/mt5/tests/test_config.py`:

```python
import os

import pytest

from mt5_universal.config import load


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
    assert cfg["broker_profile"] == "trading_com"


def test_file_overrides_defaults(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text('{"max_positions": 7, "broker_profile": "generic_mt5"}')
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    cfg = load()
    assert cfg["max_positions"] == 7
    assert cfg["broker_profile"] == "generic_mt5"


def test_env_overrides_file(clean_env, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text('{"login": 11111, "server": "FileServer"}')
    monkeypatch.setenv("MT5_CONFIG", str(cfg_path))
    monkeypatch.setenv("MT5_LOGIN", "22222")
    monkeypatch.setenv("MT5_SERVER", "EnvServer")
    cfg = load()
    assert cfg["login"] == 22222
    assert cfg["server"] == "EnvServer"


def test_overrides_arg_overrides_env(clean_env, monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "22222")
    cfg = load(overrides={"login": 33333})
    assert cfg["login"] == 33333
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_config.py -v
```

Expected: ImportError because `mt5_universal.config.load` doesn't exist.

- [ ] **Step 3: Implement the config loader**

Create `mt5_universal/config/config.py`:

```python
"""4-layer settings resolution: DEFAULTS → file → env → CLI overrides.

Path resolution (where the config FILE lives) is in mt5_universal/config/paths.py
(added in Phase 6). This module just reads/merges the layers.
"""
import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "broker_profile": "trading_com",
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
    return home / ".config" / "cli-anything-mt5.json"


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

Wire `mt5_universal/config/__init__.py`:

```python
from .config import DEFAULTS, load, save, mask_secrets

__all__ = ["DEFAULTS", "load", "save", "mask_secrets"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_config.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add mt5_universal/config/ metatrader5_cli/mt5/tests/test_config.py
git commit -m "Phase 2: add config loader with 4-layer resolution

DEFAULTS -> file (MT5_CONFIG or ~/.config/cli-anything-mt5.json) ->
env (MT5_LOGIN/PASSWORD/SERVER/LIVE) -> CLI overrides. Path
resolution stays simple here; the full XDG/APPDATA resolver lands
in Phase 6 as paths.py."
```

### Task 2.5: Add BrokerProfile ABC

**Files:**
- Create: `mt5_universal/broker/base.py`
- Update: `mt5_universal/broker/__init__.py`
- Create: `metatrader5_cli/mt5/tests/test_broker_base.py`

- [ ] **Step 1: Write the failing test**

Create `metatrader5_cli/mt5/tests/test_broker_base.py`:

```python
import pytest

from mt5_universal.broker import BrokerProfile, get_profile


def test_broker_profile_is_abstract():
    with pytest.raises(TypeError):
        BrokerProfile()


def test_get_profile_returns_trading_com_by_default():
    profile = get_profile("trading_com")
    assert profile.name == "trading_com"
    assert profile.allows_hedging is False
    assert profile.preferred_filling == "FOK"


def test_get_profile_unknown_raises():
    with pytest.raises(ValueError):
        get_profile("does-not-exist")


def test_profile_retcode_help_returns_string():
    p = get_profile("trading_com")
    assert isinstance(p.retcode_help(10030), str)
    assert "filling" in p.retcode_help(10030).lower()
```

- [ ] **Step 2: Run test — fails (broker module empty)**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_broker_base.py -v
```

- [ ] **Step 3: Implement BrokerProfile ABC**

Create `mt5_universal/broker/base.py`:

```python
from abc import ABC, abstractmethod


class BrokerProfile(ABC):
    """Captures broker-specific quirks: filling mode, hedging policy,
    rollover window, retcode help text. Concrete profiles live in
    sibling modules (trading_com.py, generic_mt5.py)."""

    name: str = ""
    allows_hedging: bool = True
    preferred_filling: str = "auto"
    rollover_utc_hour: int | None = None

    @abstractmethod
    def retcode_help(self, retcode: int) -> str:
        """Human-readable explanation for a broker retcode."""

    def is_rollover(self, utc_hour: int) -> bool:
        return self.rollover_utc_hour is not None and utc_hour == self.rollover_utc_hour


# Profile registry — populated by sibling modules at import time.
_REGISTRY: dict[str, BrokerProfile] = {}


def register(profile: BrokerProfile) -> None:
    _REGISTRY[profile.name] = profile


def get_profile(name: str) -> BrokerProfile:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown broker profile: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]
```

Wire `mt5_universal/broker/__init__.py`:

```python
from .base import BrokerProfile, register, get_profile
from . import trading_com  # noqa: F401 (registers on import)
from . import generic_mt5  # noqa: F401 (registers on import)

__all__ = ["BrokerProfile", "register", "get_profile"]
```

- [ ] **Step 4: Tests fail because trading_com / generic_mt5 don't exist yet**

That's expected — Tasks 2.6 and 2.7 will satisfy them. For now, comment out the two `from . import ...` lines and leave a note. The first two tests (ABC + unknown raises) should pass; the trading_com test fails.

- [ ] **Step 5: Commit (intermediate state — full broker registry lands in Task 2.7)**

```bash
git add mt5_universal/broker/ metatrader5_cli/mt5/tests/test_broker_base.py
git commit -m "Phase 2: add BrokerProfile ABC + registry

Concrete profiles (trading_com, generic_mt5) land in the next two
tasks. The ABC defines the contract: name, allows_hedging,
preferred_filling, rollover_utc_hour, retcode_help."
```

### Task 2.6: Implement Trading.com broker profile

**Files:**
- Create: `mt5_universal/broker/trading_com.py`
- Create: `metatrader5_cli/mt5/tests/test_broker_trading_com.py`

- [ ] **Step 1: Write the failing test**

Create `metatrader5_cli/mt5/tests/test_broker_trading_com.py`:

```python
from mt5_universal.broker import get_profile


def test_trading_com_quirks():
    p = get_profile("trading_com")
    assert p.name == "trading_com"
    assert p.allows_hedging is False
    assert p.preferred_filling == "FOK"
    assert p.rollover_utc_hour == 22


def test_trading_com_rollover_only_at_22():
    p = get_profile("trading_com")
    assert p.is_rollover(22) is True
    assert p.is_rollover(21) is False
    assert p.is_rollover(23) is False


def test_trading_com_retcode_10030_filling():
    p = get_profile("trading_com")
    msg = p.retcode_help(10030)
    assert "filling" in msg.lower()
    assert "FOK" in msg


def test_trading_com_retcode_10027_algotrading():
    p = get_profile("trading_com")
    msg = p.retcode_help(10027)
    assert "algo" in msg.lower() or "autotrading" in msg.lower()
```

- [ ] **Step 2: Run test — fails**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_broker_trading_com.py -v
```

- [ ] **Step 3: Implement the profile**

Create `mt5_universal/broker/trading_com.py`:

```python
from .base import BrokerProfile, register

RETCODE_HELP = {
    10008: "Order placed but not filled — poll fill status with `mt5 order poll-fill <ticket>`.",
    10027: "Algo/autotrading is disabled in the MT5 terminal UI. Enable it in Tools > Options > Expert Advisors.",
    10030: "Wrong filling mode. Trading.com is FOK-only — pin `filling: FOK` in your config.",
    10009: "Order request completed normally.",
    10004: "Requote — broker rejected because price changed.",
    10006: "Trade request rejected.",
    10010: "Only part of the request was completed.",
    10013: "Invalid request.",
    10014: "Invalid volume in the request.",
    10015: "Invalid price in the request.",
    10016: "Invalid stops in the request.",
    10017: "Trade is disabled.",
    10019: "There is not enough money to complete the request.",
    10021: "There are no quotes to process the request.",
}


class TradingComProfile(BrokerProfile):
    name = "trading_com"
    allows_hedging = False
    preferred_filling = "FOK"
    rollover_utc_hour = 22  # spreads spike 10-15x

    def retcode_help(self, retcode: int) -> str:
        return RETCODE_HELP.get(retcode, f"Retcode {retcode}: see MT5 docs.")


register(TradingComProfile())
```

- [ ] **Step 4: Re-enable the import in `mt5_universal/broker/__init__.py`** (was commented out in Task 2.5)

```python
from . import trading_com  # noqa: F401 (registers on import)
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_broker_trading_com.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add mt5_universal/broker/trading_com.py mt5_universal/broker/__init__.py metatrader5_cli/mt5/tests/test_broker_trading_com.py
git commit -m "Phase 2: Trading.com is the canonical default broker profile

FOK filling, no hedging, 22:00 UTC rollover, retcode help table
covering 10008/10027/10030 and the common trade-server codes."
```

### Task 2.7: Implement generic MT5 broker profile

**Files:**
- Create: `mt5_universal/broker/generic_mt5.py`
- Create: `metatrader5_cli/mt5/tests/test_broker_generic.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_broker_generic.py
from mt5_universal.broker import get_profile


def test_generic_mt5_is_permissive():
    p = get_profile("generic_mt5")
    assert p.name == "generic_mt5"
    assert p.allows_hedging is True
    assert p.preferred_filling == "auto"
    assert p.rollover_utc_hour is None


def test_generic_mt5_retcode_help_returns_string():
    p = get_profile("generic_mt5")
    assert isinstance(p.retcode_help(10009), str)
```

- [ ] **Step 2: Run test — fails**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_broker_generic.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/broker/generic_mt5.py`:

```python
from .base import BrokerProfile, register
from .trading_com import RETCODE_HELP  # share the standard MT5 retcode table


class GenericMt5Profile(BrokerProfile):
    name = "generic_mt5"
    allows_hedging = True
    preferred_filling = "auto"
    rollover_utc_hour = None  # broker-specific; not assumed

    def retcode_help(self, retcode: int) -> str:
        return RETCODE_HELP.get(retcode, f"Retcode {retcode}: see MT5 docs.")


register(GenericMt5Profile())
```

- [ ] **Step 4: Re-enable the import in `mt5_universal/broker/__init__.py`**

```python
from . import generic_mt5  # noqa: F401 (registers on import)
```

- [ ] **Step 5: Run tests + full broker suite**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_broker_generic.py metatrader5_cli/mt5/tests/test_broker_trading_com.py metatrader5_cli/mt5/tests/test_broker_base.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add mt5_universal/broker/generic_mt5.py mt5_universal/broker/__init__.py metatrader5_cli/mt5/tests/test_broker_generic.py
git commit -m "Phase 2: add generic_mt5 broker profile (permissive default)

Hedging allowed, auto filling, no assumed rollover. Used as the
fallback when the user's broker isn't Trading.com and doesn't have
a dedicated profile."
```

### Task 2.8: Wire orders to broker profile (filling mode + hedging guard)

**Files:**
- Modify: `mt5_universal/orders/orders.py`
- Modify: `mt5_universal/risk/risk.py` (hedging guard reads broker profile)

- [ ] **Step 1: Add a fixture-side test that verifies the broker profile is consulted**

Add to `metatrader5_cli/mt5/tests/test_core.py` (or a new `test_broker_integration.py`):

```python
def test_orders_resolve_filling_via_broker_profile(monkeypatch, cfg):
    cfg["broker_profile"] = "trading_com"
    cfg["filling"] = "auto"  # force the resolver to consult the profile
    from mt5_universal.orders.orders import _resolve_filling
    # Trading.com profile says preferred_filling=FOK, so auto resolves to FOK
    code = _resolve_filling("USDJPY", "auto", cfg=cfg)
    # Bridge constants — FOK is mt5.ORDER_FILLING_FOK; we just check it's not the default IOC
    import mt5_universal.bridge.mt5_backend as bk
    assert code == bk.ORDER_FILLING_FOK


def test_orders_filling_explicit_overrides_profile(cfg):
    cfg["broker_profile"] = "generic_mt5"
    cfg["filling"] = "IOC"
    from mt5_universal.orders.orders import _resolve_filling
    import mt5_universal.bridge.mt5_backend as bk
    code = _resolve_filling("USDJPY", "IOC", cfg=cfg)
    assert code == bk.ORDER_FILLING_IOC
```

- [ ] **Step 2: Run — fails because `_resolve_filling` doesn't take `cfg`**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_core.py -k filling -v
```

- [ ] **Step 3: Update `_resolve_filling` to consult the broker profile**

In `mt5_universal/orders/orders.py`, change `_resolve_filling(symbol, filling_str)` to accept `cfg` and consult the profile when `filling_str == "auto"`:

```python
from mt5_universal.broker import get_profile

def _resolve_filling(symbol: str, filling_str: str, *, cfg: dict) -> int:
    """Resolve string filling spec to MT5 constant. 'auto' consults the
    broker profile's preferred_filling."""
    import mt5_universal.bridge.mt5_backend as bk

    if filling_str == "auto":
        profile = get_profile(cfg.get("broker_profile", "trading_com"))
        filling_str = profile.preferred_filling

    return {
        "FOK": bk.ORDER_FILLING_FOK,
        "IOC": bk.ORDER_FILLING_IOC,
        "RETURN": bk.ORDER_FILLING_RETURN,
    }[filling_str.upper()]
```

Update every call site in `orders.py` to pass `cfg=cfg`.

- [ ] **Step 4: Update `risk.check_order` hedging guard to consult the profile**

In `mt5_universal/risk/risk.py`, find the `RISK_HEDGE_BLOCKED` gate. Replace the static `cfg.get("allow_hedging", False)` check with:

```python
from mt5_universal.broker import get_profile

profile = get_profile(cfg.get("broker_profile", "trading_com"))
if not profile.allows_hedging and not cfg.get("allow_hedging", False):
    # ... existing hedge-block logic
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest -q
```

Expected: green. The two new filling tests pass, existing risk-gate tests pass.

- [ ] **Step 6: Commit**

```bash
git add mt5_universal/orders/orders.py mt5_universal/risk/risk.py metatrader5_cli/mt5/tests/test_core.py
git commit -m "Phase 2: wire orders + risk to broker profile

_resolve_filling now consults profile.preferred_filling on 'auto'.
Hedging guard checks profile.allows_hedging in addition to the
config flag. Trading.com profile makes both FOK-only and no-hedge
the defaults without hardcoding them in the order/risk code."
```

### Task 2.9: Add python-quicklook indicators

**Files:**
- Create: `mt5_universal/indicators/builtins.py`
- Create: `mt5_universal/indicators/__init__.py`
- Create: `metatrader5_cli/mt5/tests/test_indicators_builtins.py`

(Domain-specific FVG/swing-pivot indicators stay archived. This task ships only the universal small-set: ema, atr, rsi, sma, bbands.)

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_indicators_builtins.py
import pandas as pd
import pytest

from mt5_universal.indicators import ema, atr, rsi, sma, bbands


@pytest.fixture
def bars():
    return pd.DataFrame({
        "open":  [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9],
        "high":  [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0],
        "low":   [0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8],
        "close": [1.05, 1.15, 1.25, 1.35, 1.45, 1.55, 1.65, 1.75, 1.85, 1.95],
    })


def test_ema_returns_series(bars):
    out = ema(bars["close"], period=3)
    assert len(out) == len(bars)
    assert out.iloc[-1] > out.iloc[0]


def test_sma_known_value(bars):
    out = sma(bars["close"], period=3)
    assert out.iloc[-1] == pytest.approx((1.75 + 1.85 + 1.95) / 3)


def test_atr_positive(bars):
    out = atr(bars, period=3)
    assert (out.dropna() > 0).all()


def test_rsi_in_range(bars):
    out = rsi(bars["close"], period=3)
    valid = out.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_bbands_returns_three_series(bars):
    upper, middle, lower = bbands(bars["close"], period=3, std=2.0)
    assert (upper >= middle).all().all() if hasattr(upper, "all") else (upper.dropna() >= middle.dropna()).all()
    assert (lower.dropna() <= middle.dropna()).all()
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_indicators_builtins.py -v
```

- [ ] **Step 3: Implement using pandas-ta**

Create `mt5_universal/indicators/builtins.py`:

```python
"""Python quicklook indicators — for ad-hoc agent queries over recent bars.

For real strategy logic, write an MQL5 indicator under indicators/ and run
visual tests via `mt5 tester indicator visual`.
"""
import pandas as pd
import pandas_ta as ta


def ema(series: pd.Series, period: int) -> pd.Series:
    return ta.ema(series, length=period)


def sma(series: pd.Series, period: int) -> pd.Series:
    return ta.sma(series, length=period)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    return ta.rsi(series, length=period)


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    return ta.atr(bars["high"], bars["low"], bars["close"], length=period)


def bbands(series: pd.Series, period: int = 20, std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    df = ta.bbands(series, length=period, std=std)
    upper = df.iloc[:, 0]
    middle = df.iloc[:, 1]
    lower = df.iloc[:, 2]
    return upper, middle, lower


def list_available() -> list[str]:
    return ["ema", "sma", "rsi", "atr", "bbands"]
```

Wire `mt5_universal/indicators/__init__.py`:

```python
from .builtins import ema, sma, rsi, atr, bbands, list_available

__all__ = ["ema", "sma", "rsi", "atr", "bbands", "list_available"]
```

- [ ] **Step 4: Run test**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_indicators_builtins.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add mt5_universal/indicators/ metatrader5_cli/mt5/tests/test_indicators_builtins.py
git commit -m "Phase 2: add python quicklook indicators

ema/sma/rsi/atr/bbands via pandas-ta. For ad-hoc agent queries only;
strategy-grade indicators are MQL5 (Phase 3+)."
```

### Task 2.10: Add reports module (JSON envelope helpers)

**Files:**
- Create: `mt5_universal/reports/__init__.py`
- Create: `mt5_universal/reports/envelope.py`
- Create: `metatrader5_cli/mt5/tests/test_reports_envelope.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_reports_envelope.py
from mt5_universal.reports import ok, fail


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
python -m pytest metatrader5_cli/mt5/tests/test_reports_envelope.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/reports/envelope.py`:

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

Wire `mt5_universal/reports/__init__.py`:

```python
from .envelope import ok, fail

__all__ = ["ok", "fail"]
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_reports_envelope.py -v
git add mt5_universal/reports/ metatrader5_cli/mt5/tests/test_reports_envelope.py
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
"""CI guard: only mt5_universal/bridge/mt5_backend.py may import MetaTrader5."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"mt5_universal/bridge/mt5_backend.py"}
SCAN_DIRS = ["mt5_universal", "mt5", "mt5_mcp"]


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
    metatrader5_cli/mt5/tests
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

Greps mt5_universal/, mt5/, mt5_mcp/ for any import MetaTrader5
outside of mt5_universal/bridge/mt5_backend.py. Fails the suite on
any leak."
```

### Task 2.12: Phase 2 acceptance check + tag

- [ ] **Step 1: Verify all imports work**

```bash
python -c "from mt5_universal import market, rates, orders, positions, account, history, risk; print('imports OK')"
python -c "from mt5_universal.broker import get_profile; p = get_profile('trading_com'); print(p.name, p.preferred_filling)"
python -c "from mt5_universal.config import load; cfg = load(); print(cfg['broker_profile'])"
```

All three must print without ImportError.

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

### Task 3.1: Add user-dir scaffolding (ea/, indicators/, presets/)

**Files:**
- Create: `ea/.gitkeep`, `ea/examples/ema_crossover.mq5`
- Create: `indicators/.gitkeep`, `indicators/examples/donchian.mq5`
- Create: `presets/.gitkeep`
- Modify: `.gitignore` — add `results/` and `*.ex5` exclusions

- [ ] **Step 1: Create directories**

```bash
mkdir -p ea/examples indicators/examples presets results
touch ea/.gitkeep indicators/.gitkeep presets/.gitkeep
```

- [ ] **Step 2: Add minimal example EA**

Create `ea/examples/ema_crossover.mq5`:

```cpp
//+------------------------------------------------------------------+
//| ema_crossover.mq5 - Example EA scaffold                          |
//| Generated by `mt5 ea new ema_crossover --template scalper`       |
//+------------------------------------------------------------------+
#property strict
#property version "1.00"

input int    FastPeriod   = 9;
input int    SlowPeriod   = 21;
input double LotSize      = 0.01;
input long   MagicNumber  = 88888;

int handleFast = INVALID_HANDLE;
int handleSlow = INVALID_HANDLE;

int OnInit()
{
   handleFast = iMA(_Symbol, _Period, FastPeriod, 0, MODE_EMA, PRICE_CLOSE);
   handleSlow = iMA(_Symbol, _Period, SlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(handleFast == INVALID_HANDLE || handleSlow == INVALID_HANDLE) return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(handleFast != INVALID_HANDLE) IndicatorRelease(handleFast);
   if(handleSlow != INVALID_HANDLE) IndicatorRelease(handleSlow);
}

void OnTick()
{
   double fast[2], slow[2];
   if(CopyBuffer(handleFast, 0, 0, 2, fast) <= 0) return;
   if(CopyBuffer(handleSlow, 0, 0, 2, slow) <= 0) return;
   // Example: long when fast crosses above slow on the most recent closed bar.
   bool crossUp   = (fast[1] > slow[1]) && (fast[0] <= slow[0]);
   bool crossDown = (fast[1] < slow[1]) && (fast[0] >= slow[0]);
   // (Order placement omitted — this scaffold is for tester wiring only.)
}
```

- [ ] **Step 3: Add minimal example indicator**

Create `indicators/examples/donchian.mq5`:

```cpp
//+------------------------------------------------------------------+
//| donchian.mq5 - Example indicator scaffold                        |
//+------------------------------------------------------------------+
#property strict
#property version "1.00"
#property indicator_chart_window
#property indicator_buffers 2
#property indicator_plots   2
#property indicator_label1  "Upper"
#property indicator_label2  "Lower"

input int Period = 20;

double UpperBuffer[];
double LowerBuffer[];

int OnInit()
{
   SetIndexBuffer(0, UpperBuffer, INDICATOR_DATA);
   SetIndexBuffer(1, LowerBuffer, INDICATOR_DATA);
   IndicatorSetString(INDICATOR_SHORTNAME, "Donchian(" + IntegerToString(Period) + ")");
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[],
                const double &close[], const long &tick_volume[], const long &volume[],
                const int &spread[])
{
   int start = MathMax(prev_calculated - 1, Period);
   for(int i = start; i < rates_total; i++)
   {
      UpperBuffer[i] = high[ArrayMaximum(high, i - Period + 1, Period)];
      LowerBuffer[i] = low[ArrayMinimum(low, i - Period + 1, Period)];
   }
   return rates_total;
}
```

- [ ] **Step 4: Update .gitignore**

Use Edit. Find the line `# Build artifacts (compiled MQL5 binaries — sources are tracked, builds aren't)` and below it find `*.ex5`. Below that section add:

```
# Tester run snapshots (per-run artifacts; keep the dir, ignore contents)
results/*
!results/.gitkeep
```

Create the keepfile:

```bash
touch results/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add ea/ indicators/ presets/ results/.gitkeep .gitignore
git commit -m "Phase 3: scaffold ea/, indicators/, presets/, results/ user dirs

Two minimal examples (ema_crossover EA, donchian indicator) seed
the discovery + compile flow. results/ dir kept; per-run files
ignored."
```

### Task 3.2: Implement mql5.compiler (metaeditor64.exe wrapper)

**Files:**
- Create: `mt5_universal/mql5/compiler.py`
- Create: `metatrader5_cli/mt5/tests/test_mql5_compiler.py`

- [ ] **Step 1: Write the failing test (mocked subprocess)**

```python
# metatrader5_cli/mt5/tests/test_mql5_compiler.py
import subprocess
from pathlib import Path

import pytest

from mt5_universal.mql5 import compiler


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
python -m pytest metatrader5_cli/mt5/tests/test_mql5_compiler.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/mql5/compiler.py`:

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

from mt5_universal.reports import ok, fail

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
python -m pytest metatrader5_cli/mt5/tests/test_mql5_compiler.py -v
git add mt5_universal/mql5/compiler.py metatrader5_cli/mt5/tests/test_mql5_compiler.py
git commit -m "Phase 3: add mql5.compiler — metaeditor64.exe wrapper

Resolves MetaEditor via MT5_METAEDITOR_PATH env, common install
paths, then shutil.which. Returns standard JSON envelope with
errors/warnings/log path."
```

### Task 3.3: Implement mql5.deployer

**Files:**
- Create: `mt5_universal/mql5/deployer.py`
- Create: `metatrader5_cli/mt5/tests/test_mql5_deployer.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_mql5_deployer.py
from pathlib import Path

import pytest

from mt5_universal.mql5 import deployer


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
python -m pytest metatrader5_cli/mt5/tests/test_mql5_deployer.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/mql5/deployer.py`:

```python
"""Copy compiled MQL5 artifacts to the MT5 terminal's Experts/ or Indicators/ folder.

Terminal data dir is the per-instance Roaming dir like
%APPDATA%\MetaQuotes\Terminal\<HASH>\MQL5\.
"""
import os
import shutil
from pathlib import Path

from mt5_universal.reports import ok, fail

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
python -m pytest metatrader5_cli/mt5/tests/test_mql5_deployer.py -v
git add mt5_universal/mql5/deployer.py metatrader5_cli/mt5/tests/test_mql5_deployer.py
git commit -m "Phase 3: add mql5.deployer — copy .mq5 + .ex5 to terminal MQL5 dir"
```

### Task 3.4: Implement mql5.discovery (auto-find user EAs/indicators)

**Files:**
- Create: `mt5_universal/mql5/discovery.py`
- Create: `metatrader5_cli/mt5/tests/test_mql5_discovery.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_mql5_discovery.py
from pathlib import Path

from mt5_universal.mql5 import discovery


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
python -m pytest metatrader5_cli/mt5/tests/test_mql5_discovery.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/mql5/discovery.py`:

```python
"""Auto-discover user MQL5 EAs and indicators.

Search order (first match wins):
  1. ./ea/ or ./indicators/ (repo root, current working directory)
  2. ~/.config/mt5-universal/ea/ or /indicators/ (or platform equivalents — Phase 6 paths.py refines)
  3. (future) entry points
"""
import os
from pathlib import Path


def _search_paths(kind: str) -> list[Path]:
    """kind is 'ea' or 'indicators'."""
    cwd = Path.cwd() / kind
    user = Path(os.path.expanduser("~")) / ".config" / "mt5-universal" / kind
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
python -m pytest metatrader5_cli/mt5/tests/test_mql5_discovery.py -v
git add mt5_universal/mql5/discovery.py metatrader5_cli/mt5/tests/test_mql5_discovery.py
git commit -m "Phase 3: add mql5.discovery — auto-find user EAs/indicators

Search order: ./ea or ./indicators (cwd) -> ~/.config/mt5-universal/.
First-match wins. Each result includes name, source path, and
compiled boolean."
```

### Task 3.5: Add MQL5 templates + scaffolding

**Files:**
- Create: `mt5_universal/mql5/templates/ea_scalper.mq5`
- Create: `mt5_universal/mql5/templates/ea_swing.mq5`
- Create: `mt5_universal/mql5/templates/indicator_oscillator.mq5`
- Create: `mt5_universal/mql5/templates/indicator_overlay.mq5`
- Create: `mt5_universal/mql5/scaffold.py`
- Create: `metatrader5_cli/mt5/tests/test_mql5_scaffold.py`

- [ ] **Step 1: Write template files**

Create `mt5_universal/mql5/templates/ea_scalper.mq5` — same content as `ea/examples/ema_crossover.mq5` from Task 3.1 but with the strategy name as a placeholder `{{name}}` in the property version line and file header.

```cpp
//+------------------------------------------------------------------+
//| {{name}}.mq5 - scalper EA scaffold                                |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"

input int    FastPeriod   = 9;
input int    SlowPeriod   = 21;
input double LotSize      = 0.01;
input long   MagicNumber  = 88888;

int handleFast = INVALID_HANDLE;
int handleSlow = INVALID_HANDLE;

int OnInit()  { handleFast = iMA(_Symbol, _Period, FastPeriod, 0, MODE_EMA, PRICE_CLOSE);
                handleSlow = iMA(_Symbol, _Period, SlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
                return (handleFast == INVALID_HANDLE || handleSlow == INVALID_HANDLE) ? INIT_FAILED : INIT_SUCCEEDED; }
void OnDeinit(const int reason) { if(handleFast != INVALID_HANDLE) IndicatorRelease(handleFast);
                                   if(handleSlow != INVALID_HANDLE) IndicatorRelease(handleSlow); }
void OnTick() { /* Implement entry / exit / risk in this body. */ }
```

Create `mt5_universal/mql5/templates/ea_swing.mq5`:

```cpp
//+------------------------------------------------------------------+
//| {{name}}.mq5 - swing EA scaffold                                  |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"

input int    AtrPeriod    = 14;
input double RiskPercent  = 0.5;
input long   MagicNumber  = 88888;

int handleAtr = INVALID_HANDLE;

int OnInit() { handleAtr = iATR(_Symbol, _Period, AtrPeriod);
               return handleAtr == INVALID_HANDLE ? INIT_FAILED : INIT_SUCCEEDED; }
void OnDeinit(const int reason) { if(handleAtr != INVALID_HANDLE) IndicatorRelease(handleAtr); }
void OnTick() { /* Implement bar-close entry on the new bar. */ }
```

Create `mt5_universal/mql5/templates/indicator_oscillator.mq5`:

```cpp
//+------------------------------------------------------------------+
//| {{name}}.mq5 - oscillator indicator scaffold                      |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"
#property indicator_separate_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_label1  "{{name}}"

input int Period = 14;
double Buf[];

int OnInit() { SetIndexBuffer(0, Buf, INDICATOR_DATA);
               IndicatorSetString(INDICATOR_SHORTNAME, "{{name}}(" + IntegerToString(Period) + ")");
               return INIT_SUCCEEDED; }
int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{ /* Compute Buf[i] for i in [prev_calculated, rates_total). */ return rates_total; }
```

Create `mt5_universal/mql5/templates/indicator_overlay.mq5`:

```cpp
//+------------------------------------------------------------------+
//| {{name}}.mq5 - chart-overlay indicator scaffold                   |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_label1  "{{name}}"

input int Period = 20;
double Buf[];

int OnInit() { SetIndexBuffer(0, Buf, INDICATOR_DATA);
               return INIT_SUCCEEDED; }
int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{ /* Compute Buf[i]. */ return rates_total; }
```

- [ ] **Step 2: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_mql5_scaffold.py
from pathlib import Path

import pytest

from mt5_universal.mql5 import scaffold


def test_scaffold_ea_writes_file(tmp_path):
    out = scaffold.create_ea("alpha", template="scalper", target_dir=tmp_path)
    assert out["ok"] is True
    src = Path(out["data"]["source"])
    assert src.exists()
    text = src.read_text()
    assert "alpha.mq5" in text
    assert "{{name}}" not in text


def test_scaffold_ea_unknown_template(tmp_path):
    out = scaffold.create_ea("alpha", template="nonexistent", target_dir=tmp_path)
    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_TEMPLATE"


def test_scaffold_ea_refuses_overwrite(tmp_path):
    (tmp_path / "alpha.mq5").write_text("// existing")
    out = scaffold.create_ea("alpha", template="scalper", target_dir=tmp_path)
    assert out["ok"] is False
    assert out["error"]["code"] == "ALREADY_EXISTS"


def test_scaffold_indicator_writes_file(tmp_path):
    out = scaffold.create_indicator("rsi_dual", template="oscillator", target_dir=tmp_path)
    assert out["ok"] is True
    text = Path(out["data"]["source"]).read_text()
    assert "rsi_dual" in text
    assert "{{name}}" not in text
```

- [ ] **Step 3: Run — fails**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_mql5_scaffold.py -v
```

- [ ] **Step 4: Implement**

Create `mt5_universal/mql5/scaffold.py`:

```python
"""Scaffold new MQL5 EAs and indicators from packaged templates."""
from pathlib import Path

from mt5_universal.reports import ok, fail

_TEMPLATE_ROOT = Path(__file__).parent / "templates"

_EA_TEMPLATES = {"scalper": "ea_scalper.mq5", "swing": "ea_swing.mq5"}
_IND_TEMPLATES = {"oscillator": "indicator_oscillator.mq5", "overlay": "indicator_overlay.mq5"}


def _scaffold(name: str, template: str, target_dir: Path, registry: dict[str, str]) -> dict:
    if template not in registry:
        return fail("UNKNOWN_TEMPLATE", f"Unknown template {template!r}. Known: {sorted(registry)}")
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{name}.mq5"
    if dest.exists():
        return fail("ALREADY_EXISTS", f"{dest} already exists; refusing to overwrite")
    template_path = _TEMPLATE_ROOT / registry[template]
    text = template_path.read_text(encoding="utf-8").replace("{{name}}", name)
    dest.write_text(text, encoding="utf-8")
    return ok({"source": str(dest), "template": template})


def list_templates() -> dict[str, list[str]]:
    return {"ea": sorted(_EA_TEMPLATES), "indicator": sorted(_IND_TEMPLATES)}


def create_ea(name: str, *, template: str = "scalper", target_dir: Path | str = Path("ea")) -> dict:
    return _scaffold(name, template, Path(target_dir), _EA_TEMPLATES)


def create_indicator(name: str, *, template: str = "overlay", target_dir: Path | str = Path("indicators")) -> dict:
    return _scaffold(name, template, Path(target_dir), _IND_TEMPLATES)
```

- [ ] **Step 5: Update `mt5_universal/mql5/__init__.py` to re-export the public API**

```python
from . import compiler, deployer, discovery, scaffold

__all__ = ["compiler", "deployer", "discovery", "scaffold"]
```

- [ ] **Step 6: Update setup.py package_data so templates ship with the package**

In `setup.py`, change `package_data` to also include the templates:

```python
    package_data={
        "metatrader5_cli.mt5": [
            "skills/SKILL.md",
        ],
        "mt5_universal.mql5": [
            "templates/*.mq5",
        ],
    },
```

- [ ] **Step 7: Run + commit**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_mql5_scaffold.py -v
git add mt5_universal/mql5/ metatrader5_cli/mt5/tests/test_mql5_scaffold.py setup.py
git commit -m "Phase 3: add mql5 templates + scaffold

Two EA templates (scalper, swing) + two indicator templates
(oscillator, overlay). scaffold.create_ea/create_indicator
substitutes {{name}} and refuses to overwrite. Templates ship via
setup.py package_data."
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
"""Thin click wrapper over mt5_universal.

Each command translates CLI args to library calls and prints the
JSON envelope (with --json) or human-readable text.
"""
import json
from pathlib import Path

import click

from mt5_universal.mql5 import compiler, deployer, discovery, scaffold


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
@click.option("--template", default="scalper", help="Template: scalper | swing")
@click.option("--target-dir", default="ea", type=click.Path(file_okay=False))
@click.pass_context
def ea_new(ctx, name, template, target_dir):
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
@click.option("--template", default="overlay", help="Template: overlay | oscillator")
@click.option("--target-dir", default="indicators", type=click.Path(file_okay=False))
@click.pass_context
def indicator_new(ctx, name, template, target_dir):
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

(The legacy `metatrader5_cli.mt5.mt5_cli:main` entry point is dropped. The legacy CLI module continues to exist on disk through Phase 1/2 transition but is no longer the installed entry point.)

- [ ] **Step 4: Re-install in editable mode and smoke-test**

```bash
python -m pip install -e . --quiet
mt5 --help
mt5 ea --help
mt5 ea list --json   # expect: {"ok": true, "data": [...]}
mt5 ea new demo --template scalper --target-dir /tmp/eatest
ls /tmp/eatest/demo.mq5
```

- [ ] **Step 5: Commit**

```bash
git add mt5/ setup.py
git commit -m "Phase 3: wire mt5 ea new/list/compile/deploy + indicator equivalents

Thin click wrapper at mt5/cli.py over mt5_universal.mql5. Console
script switches from the legacy metatrader5_cli entry to mt5.cli:main."
```

### Task 3.7: Add CLI smoke tests

**Files:**
- Create: `metatrader5_cli/mt5/tests/test_cli_ea.py`

- [ ] **Step 1: Write the test**

```python
# metatrader5_cli/mt5/tests/test_cli_ea.py
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
                                "--template", "scalper",
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
                                "--template", "overlay",
                                "--target-dir", str(target)])
    assert json.loads(res1.output)["ok"] is True
    assert (target / "smoke_donch.mq5").exists()
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_cli_ea.py -v
git add metatrader5_cli/mt5/tests/test_cli_ea.py
git commit -m "Phase 3: CLI smoke tests for mt5 ea/indicator new/list/compile"
```

### Task 3.8: Phase 3 acceptance check + tag

- [ ] **Step 1: End-to-end roundtrip with the included example**

```bash
mt5 --json ea list                          # expect to find ema_crossover under examples/
mt5 --json ea compile ema_crossover         # if MetaEditor available; else expect METAEDITOR_NOT_FOUND
mt5 --json indicator new my_test --template oscillator --target-dir indicators
mt5 --json indicator list                   # finds my_test
rm indicators/my_test.mq5
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
- Create: `mt5_universal/tester/cache.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_tester_cache.py
from datetime import datetime
from pathlib import Path

from mt5_universal.tester import cache


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
python -m pytest metatrader5_cli/mt5/tests/test_tester_cache.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/tester/cache.py`:

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_cache.py -v
git add mt5_universal/tester/cache.py metatrader5_cli/mt5/tests/test_tester_cache.py
git commit -m "Phase 4: tester.cache — run-id snapshot dirs under results/"
```

### Task 4.2: Implement tester.ini_builder

**Files:**
- Create: `mt5_universal/tester/ini_builder.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_ini_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_tester_ini_builder.py
from pathlib import Path

from mt5_universal.tester import ini_builder


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
python -m pytest metatrader5_cli/mt5/tests/test_tester_ini_builder.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/tester/ini_builder.py`:

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_ini_builder.py -v
git add mt5_universal/tester/ini_builder.py metatrader5_cli/mt5/tests/test_tester_ini_builder.py
git commit -m "Phase 4: tester.ini_builder generates .ini files for terminal64 /config"
```

### Task 4.3: Implement tester.launcher (terminal64.exe /config wrapper)

**Files:**
- Create: `mt5_universal/tester/launcher.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_launcher.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_tester_launcher.py
import subprocess
from pathlib import Path

from mt5_universal.tester import launcher


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
python -m pytest metatrader5_cli/mt5/tests/test_tester_launcher.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/tester/launcher.py`:

```python
"""Run MT5's terminal64.exe in tester mode via /config:<ini>."""
import os
import subprocess
from pathlib import Path

from mt5_universal.reports import ok, fail

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_launcher.py -v
git add mt5_universal/tester/launcher.py metatrader5_cli/mt5/tests/test_tester_launcher.py
git commit -m "Phase 4: tester.launcher runs terminal64.exe /config:<ini> /portable"
```

### Task 4.4: Implement tester.results — HTML report parser

**Files:**
- Create: `mt5_universal/tester/results.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_results_html.py`
- Create: `metatrader5_cli/mt5/tests/fixtures/sample_report.html`

- [ ] **Step 1: Capture a representative sample HTML**

Create `metatrader5_cli/mt5/tests/fixtures/sample_report.html` (this is a minimal MT5-tester-style report — the real ones are larger but follow this structure):

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
# metatrader5_cli/mt5/tests/test_tester_results_html.py
from pathlib import Path

from mt5_universal.tester import results

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_results_html.py -v
```

- [ ] **Step 4: Implement (HTML parser only — CSV / XML / envelope land in next tasks)**

Create `mt5_universal/tester/results.py`:

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

Wire `mt5_universal/tester/__init__.py`:

```python
from . import cache, ini_builder, launcher, results

__all__ = ["cache", "ini_builder", "launcher", "results"]
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_tester_results_html.py -v
git add mt5_universal/tester/results.py mt5_universal/tester/__init__.py metatrader5_cli/mt5/tests/test_tester_results_html.py metatrader5_cli/mt5/tests/fixtures/sample_report.html
git commit -m "Phase 4: tester.results.parse_html_report extracts stats + deals"
```

### Task 4.5: Add journal CSV parser

**Files:**
- Modify: `mt5_universal/tester/results.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_results_journal.py`
- Create: `metatrader5_cli/mt5/tests/fixtures/sample_journal.csv`

- [ ] **Step 1: Write the fixture**

`metatrader5_cli/mt5/tests/fixtures/sample_journal.csv`:

```
2024.01.05 10:15:00,info,Initialize: alpha v0.1
2024.01.05 10:15:01,info,Symbol AUDUSD selected
2024.01.05 10:30:00,warning,Slippage > 2 points on order 1001
2024.06.30 23:59:00,info,Test finished
```

- [ ] **Step 2: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_tester_results_journal.py
from pathlib import Path

from mt5_universal.tester import results

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_results_journal.py -v
```

- [ ] **Step 4: Implement — append to results.py**

Add to `mt5_universal/tester/results.py`:

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_results_journal.py -v
git add mt5_universal/tester/results.py metatrader5_cli/mt5/tests/test_tester_results_journal.py metatrader5_cli/mt5/tests/fixtures/sample_journal.csv
git commit -m "Phase 4: tester.results.parse_journal — CSV journal -> JSON events"
```

### Task 4.6: Add optimization XML parser + envelope assembler

**Files:**
- Modify: `mt5_universal/tester/results.py`
- Create: `metatrader5_cli/mt5/tests/fixtures/sample_optimization.xml`
- Create: `metatrader5_cli/mt5/tests/test_tester_results_envelope.py`

- [ ] **Step 1: Write the fixture**

`metatrader5_cli/mt5/tests/fixtures/sample_optimization.xml`:

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
# metatrader5_cli/mt5/tests/test_tester_results_envelope.py
from pathlib import Path

from mt5_universal.tester import results

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_results_envelope.py -v
```

- [ ] **Step 4: Implement — append to results.py**

Add to `mt5_universal/tester/results.py`:

```python
import xml.etree.ElementTree as ET

from mt5_universal.reports import ok


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
python -m pytest metatrader5_cli/mt5/tests/test_tester_results_envelope.py -v
git add mt5_universal/tester/results.py metatrader5_cli/mt5/tests/test_tester_results_envelope.py metatrader5_cli/mt5/tests/fixtures/sample_optimization.xml
git commit -m "Phase 4: tester.results — XML opt parser + assemble() envelope

assemble() combines HTML stats/deals + CSV journal + optimization XML
into the standard JSON envelope. Missing inputs are tolerated (return
empty arrays / None for the missing piece)."
```

### Task 4.7: Implement tester.ea — single mode

**Files:**
- Create: `mt5_universal/tester/ea.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_ea.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_tester_ea.py
from pathlib import Path

from mt5_universal.tester import ea


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
python -m pytest metatrader5_cli/mt5/tests/test_tester_ea.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/tester/ea.py`:

```python
"""High-level tester.ea operations: single, optimize, scanner, stress.

Composes ini_builder + launcher + results.assemble + cache.
"""
from pathlib import Path

from mt5_universal.mql5 import discovery
from mt5_universal.reports import ok, fail
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
python -m pytest metatrader5_cli/mt5/tests/test_tester_ea.py -v
git add mt5_universal/tester/ea.py metatrader5_cli/mt5/tests/test_tester_ea.py
git commit -m "Phase 4: tester.ea.single composes ini + launcher + results

Builds the .ini, launches terminal64 in portable mode, parses the
report + journal, returns the standard envelope with run_id + stats
+ deals + journal_events."
```

### Task 4.8: Implement tester.ea — optimize/forward + scanner + stress

**Files:**
- Modify: `mt5_universal/tester/ea.py`
- Modify: `metatrader5_cli/mt5/tests/test_tester_ea.py`

- [ ] **Step 1: Add tests**

Append to `metatrader5_cli/mt5/tests/test_tester_ea.py`:

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_ea.py -v
```

- [ ] **Step 3: Implement — append to tester/ea.py**

Add to `mt5_universal/tester/ea.py`:

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
python -m pytest metatrader5_cli/mt5/tests/test_tester_ea.py -v
git add mt5_universal/tester/ea.py metatrader5_cli/mt5/tests/test_tester_ea.py
git commit -m "Phase 4: tester.ea — optimize/scanner/stress modes

optimize: complete | genetic | math, optional forward window.
scanner: runs single() per symbol and aggregates per-symbol envelopes.
stress: single() with simulated-delay metadata (true delay injection
varies by MT5 version)."
```

### Task 4.9: Implement tester.indicator (visual test)

**Files:**
- Create: `mt5_universal/tester/indicator.py`
- Create: `metatrader5_cli/mt5/tests/test_tester_indicator.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_tester_indicator.py
from pathlib import Path

from mt5_universal.tester import indicator


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
python -m pytest metatrader5_cli/mt5/tests/test_tester_indicator.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/tester/indicator.py`:

```python
from pathlib import Path

from mt5_universal.mql5 import discovery
from mt5_universal.reports import ok, fail
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

Update `mt5_universal/tester/__init__.py`:

```python
from . import cache, ea, ini_builder, indicator, launcher, results

__all__ = ["cache", "ea", "ini_builder", "indicator", "launcher", "results"]
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_tester_indicator.py -v
git add mt5_universal/tester/indicator.py mt5_universal/tester/__init__.py metatrader5_cli/mt5/tests/test_tester_indicator.py
git commit -m "Phase 4: tester.indicator.visual — drive MT5 indicator visual test"
```

### Task 4.10: Wire `mt5 tester ea/indicator/list/show` CLI commands + Phase 4 acceptance

**Files:**
- Modify: `mt5/cli.py`
- Create: `metatrader5_cli/mt5/tests/test_cli_tester.py`

- [ ] **Step 1: Append the tester command group to mt5/cli.py**

Add at the end of `mt5/cli.py`:

```python
from mt5_universal.tester import ea as tester_ea, indicator as tester_indicator, cache as tester_cache
from mt5_universal.tester import results as tester_results


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
# metatrader5_cli/mt5/tests/test_cli_tester.py
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
git add mt5/cli.py metatrader5_cli/mt5/tests/test_cli_tester.py
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

**Goal:** Make agents discoverable and runnable. Migrate the existing 11k-char SKILL.md, add YAML frontmatter, add MCP server, upgrade ReplSkin to print SKILL.md path, add skill_generator that introspects the Click tree.

### Task 5.1: Migrate SKILL.md to mt5_universal/skills/ with YAML frontmatter

**Files:**
- Move: `metatrader5_cli/mt5/skills/SKILL.md` → `mt5_universal/skills/SKILL.md`
- Modify: `mt5_universal/skills/SKILL.md` — prepend YAML frontmatter; replace any references to legacy commands with new equivalents
- Modify: `setup.py` package_data

- [ ] **Step 1: Move and add frontmatter**

```bash
git mv metatrader5_cli/mt5/skills/SKILL.md mt5_universal/skills/SKILL.md
```

Edit `mt5_universal/skills/SKILL.md` to prepend (use the Edit tool):

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
        "mt5_universal.mql5": ["templates/*.mq5"],
        "mt5_universal.skills": ["SKILL.md"],
    },
```

(Drop the `metatrader5_cli.mt5: ['skills/SKILL.md']` entry — it's empty now.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Phase 5: migrate SKILL.md to mt5_universal/skills/ + add frontmatter

YAML frontmatter (name, description) makes the skill discoverable by
Claude Code / cli-anything-hub. Legacy command references either
removed or pointed at the archived spec."
```

### Task 5.2: Implement skill_generator (introspect Click tree → command-group tables)

**Files:**
- Create: `mt5_universal/skills/generator.py`
- Create: `metatrader5_cli/mt5/tests/test_skill_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_skill_generator.py
from mt5_universal.skills.generator import build_command_tables

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
python -m pytest metatrader5_cli/mt5/tests/test_skill_generator.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/skills/generator.py`:

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
python -m pytest metatrader5_cli/mt5/tests/test_skill_generator.py -v
git add mt5_universal/skills/generator.py metatrader5_cli/mt5/tests/test_skill_generator.py
git commit -m "Phase 5: skill_generator — Click introspection + markdown table render"
```

### Task 5.3: Wire `mt5 skills regenerate` command

**Files:**
- Modify: `mt5/cli.py`
- Create: `metatrader5_cli/mt5/tests/test_cli_skills.py`

- [ ] **Step 1: Append to mt5/cli.py**

```python
from mt5_universal.skills.generator import build_command_tables, render_markdown_tables


@main.group("skills")
def skills_group():
    """Manage the SKILL.md manifest."""


@skills_group.command("regenerate")
@click.option("--target", default="mt5_universal/skills/SKILL.md", type=click.Path(dir_okay=False))
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

- [ ] **Step 2: Add the markers to mt5_universal/skills/SKILL.md**

Edit the SKILL.md and insert (anywhere appropriate, typically after the introduction):

```markdown
## Command Groups (auto-generated)

<!-- BEGIN COMMANDS -->

(this section is regenerated by `mt5 skills regenerate`)

<!-- END COMMANDS -->
```

- [ ] **Step 3: Test**

```python
# metatrader5_cli/mt5/tests/test_cli_skills.py
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
python -m pytest metatrader5_cli/mt5/tests/test_cli_skills.py -v
mt5 --json skills regenerate    # writes the live SKILL.md
git add -A
git commit -m "Phase 5: mt5 skills regenerate — auto-fill SKILL.md command tables

Adds HTML-comment markers around the auto-generated section so the
hand-written workflow narrative stays untouched."
```

### Task 5.4: Upgrade utils/repl_skin.py to print SKILL.md path on banner

**Files:**
- Modify: `metatrader5_cli/mt5/utils/repl_skin.py` (still in legacy package; will move later)

- [ ] **Step 1: Find the banner function**

```bash
grep -n "def.*banner\|print_banner\|server\|balance" metatrader5_cli/mt5/utils/repl_skin.py | head
```

- [ ] **Step 2: Edit so the banner includes the resolved SKILL.md path**

In the banner function (likely `_banner` or `print_banner`), after the existing server/balance line, append:

```python
import importlib.resources as _r
try:
    skill_path = _r.files("mt5_universal.skills").joinpath("SKILL.md")
    print(f"  SKILL.md: {skill_path}")
except (ModuleNotFoundError, FileNotFoundError):
    pass
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest -q
git add metatrader5_cli/mt5/utils/repl_skin.py
git commit -m "Phase 5: ReplSkin banner prints absolute SKILL.md path

Lets agents read the skill manifest via Read tool without guessing."
```

### Task 5.5: Add mt5_mcp/server.py FastMCP scaffold + read-only tools

**Files:**
- Create: `mt5_mcp/__init__.py`, `mt5_mcp/server.py`
- Modify: `setup.py` — declare `mt5-mcp` console script + add `fastmcp` install_requires
- Create: `metatrader5_cli/mt5/tests/test_mcp_server.py`

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
"""mt5-mcp — FastMCP server publishing mt5_universal as MCP tools.

Each tool maps 1:1 to a library function. Read-only tools are exposed
unconditionally; mutating tools require an explicit live_intent flag.
"""
from fastmcp import FastMCP

from mt5_universal.config import load as load_config
from mt5_universal.market.market import info as market_info, tick as market_tick
from mt5_universal.rates.rates import fetch as rates_fetch
from mt5_universal.account.account import info as account_info
from mt5_universal.history.history import deals as history_deals
from mt5_universal.mql5 import discovery as mql5_discovery

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
# metatrader5_cli/mt5/tests/test_mcp_server.py
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
python -m pytest metatrader5_cli/mt5/tests/test_mcp_server.py -v
git add mt5_mcp/ setup.py metatrader5_cli/mt5/tests/test_mcp_server.py
git commit -m "Phase 5: add mt5-mcp FastMCP server with read-only tool set

Tools expose market/account/rates/history/ea-list/indicator-list.
Mutating order tools land in the next task gated on live_intent.
mt5-mcp console script registered."
```

### Task 5.6: Add MCP tools for orders/positions/tester (mutating with live_intent)

**Files:**
- Modify: `mt5_mcp/server.py`
- Modify: `metatrader5_cli/mt5/tests/test_mcp_server.py`

- [ ] **Step 1: Append mutating tools to mt5_mcp/server.py**

```python
from mt5_universal.orders.orders import place_market, dryrun as orders_dryrun
from mt5_universal.positions.positions import close as position_close, list as position_list
from mt5_universal.tester import ea as tester_ea, indicator as tester_indicator


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

In `metatrader5_cli/mt5/tests/test_mcp_server.py`, expand:

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
python -m pytest metatrader5_cli/mt5/tests/test_mcp_server.py -v
git add mt5_mcp/server.py metatrader5_cli/mt5/tests/test_mcp_server.py
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
grep -A 50 "BEGIN COMMANDS" mt5_universal/skills/SKILL.md | head -60
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
git add mt5_universal/skills/SKILL.md
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
from mt5_universal.skills.generator import build_command_tables, render_markdown_tables

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "mt5_universal" / "skills" / "SKILL.md"


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

### Task 6.1: Implement mt5_universal/config/paths.py (full XDG/APPDATA resolution)

**Files:**
- Create: `mt5_universal/config/paths.py`
- Modify: `mt5_universal/config/__init__.py`
- Create: `metatrader5_cli/mt5/tests/test_config_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# metatrader5_cli/mt5/tests/test_config_paths.py
from pathlib import Path

from mt5_universal.config import paths


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
    assert paths.cache_dir() == tmp_path / "xdg" / "mt5-universal"


def test_cache_dir_appdata_fallback_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("MT5_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    assert paths.cache_dir() == tmp_path / "lad" / "mt5-universal" / "cache"


def test_results_dir_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_RESULTS_DIR", str(tmp_path / "myresults"))
    assert paths.results_dir() == tmp_path / "myresults"
```

- [ ] **Step 2: Run — fails**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_config_paths.py -v
```

- [ ] **Step 3: Implement**

Create `mt5_universal/config/paths.py`:

```python
"""Cross-platform path resolution. Every module that needs a filesystem
location goes through this — no hardcoded user paths anywhere else."""
import os
import sys
from pathlib import Path

APP_NAME = "mt5-universal"


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def config_file() -> Path:
    if "MT5_CONFIG" in os.environ:
        return Path(os.environ["MT5_CONFIG"])
    if "XDG_CONFIG_HOME" in os.environ:
        return Path(os.environ["XDG_CONFIG_HOME"]) / APP_NAME / "config.json"
    if sys.platform == "win32" and "APPDATA" in os.environ:
        return Path(os.environ["APPDATA"]) / APP_NAME / "config.json"
    return _home() / ".config" / APP_NAME / "config.json"


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

Update `mt5_universal/config/__init__.py`:

```python
from .config import DEFAULTS, load, save, mask_secrets
from . import paths

__all__ = ["DEFAULTS", "load", "save", "mask_secrets", "paths"]
```

- [ ] **Step 4: Update config.config to use paths.config_file()**

In `mt5_universal/config/config.py`, replace `_config_path()` with:

```python
from .paths import config_file as _config_path
```

(And drop the inline implementation.)

- [ ] **Step 5: Run + commit**

```bash
python -m pytest metatrader5_cli/mt5/tests/test_config_paths.py -v
git add mt5_universal/config/ metatrader5_cli/mt5/tests/test_config_paths.py
git commit -m "Phase 6: full XDG/APPDATA path resolver

paths.config_file/ea_dir/indicators_dir/presets_dir/results_dir/
cache_dir/log_dir route every filesystem location through one
module. Resolution: MT5_<NAME> env -> XDG -> APPDATA (Win) -> HOME."
```

### Task 6.2: Update mql5/discovery + tester/cache to use config.paths

**Files:**
- Modify: `mt5_universal/mql5/discovery.py`
- Modify: `mt5_universal/tester/cache.py`

- [ ] **Step 1: Update discovery to consult paths.ea_dir() / paths.indicators_dir()**

In `mt5_universal/mql5/discovery.py`, replace `_search_paths`:

```python
from mt5_universal.config import paths


def _search_paths(kind: str) -> list[Path]:
    cwd = Path.cwd() / kind
    user = paths.ea_dir() if kind == "ea" else paths.indicators_dir()
    return [p for p in (cwd, user) if p.exists()]
```

- [ ] **Step 2: Update cache to default to paths.results_dir()**

In `mt5_universal/tester/cache.py`, change the default `root` parameter:

```python
from mt5_universal.config import paths


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
git add mt5_universal/mql5/discovery.py mt5_universal/tester/cache.py
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
"""CI guard: no module under mt5_universal/, mt5/, mt5_mcp/ may contain
hardcoded user paths. Path resolution goes through mt5_universal.config.paths."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["mt5_universal", "mt5", "mt5_mcp"]
FORBIDDEN = [
    re.compile(r"C:\\\\Users\\\\"),
    re.compile(r"C:\\\\Users/"),
    re.compile(r"/home/[A-Za-z0-9_-]+"),
    re.compile(r"/Users/[A-Za-z0-9_-]+"),
    re.compile(r"^[A-Z]:\\\\(?!Users\\\\)", re.MULTILINE),  # other absolute drive paths
]
# Files allowed to contain hardcoded paths (e.g., Windows install candidates).
ALLOWLIST = {
    "mt5_universal/mql5/compiler.py",        # _CANDIDATE_PATHS for metaeditor64.exe
    "mt5_universal/mql5/deployer.py",        # _CANDIDATE_DATA_DIRS
    "mt5_universal/tester/launcher.py",      # _CANDIDATE_PATHS for terminal64.exe
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

Greps mt5_universal/, mt5/, mt5_mcp/ for C:\\Users\\, /home/<user>/,
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
| 1 | Archive legacy | `archive/legacy-core/` + `archive/legacy-mql5/` |
| 2 | `mt5_universal/` skeleton | the agnostic library |
| 3 | MQL5 plugin host | `ea/` + `indicators/` user dirs, scaffolding |
| 4 | Strategy Tester driver | `mt5 tester ea/indicator …` |
| 5 | Agent surface | SKILL.md + MCP server + ReplSkin |
| 6 | Portability + tests | path resolver + CI guards + this doc |

## Adding a new CLI command

1. **Library function first.** Implement in `mt5_universal/<concern>/`. Return `mt5_universal.reports.ok(...)` or `fail(...)`.
2. **Test against the function** — not against the CLI. CLI tests are smoke tests, not unit tests.
3. **Add the click command** in `mt5/cli.py`. Pass `ctx.obj["json"]` to `_emit`.
4. **Run `mt5 skills regenerate`** so SKILL.md picks up the new command.
5. **Add an MCP tool in `mt5_mcp/server.py`** if the function makes sense to call from a tool-using agent.

## Adding a new MQL5 EA template

1. Drop `mt5_universal/mql5/templates/ea_<style>.mq5`. Use `{{name}}` as the placeholder.
2. Add the entry to `_EA_TEMPLATES` in `mt5_universal/mql5/scaffold.py`.
3. Add a test in `metatrader5_cli/mt5/tests/test_mql5_scaffold.py`.

## Adding a new broker profile

1. Create `mt5_universal/broker/<name>.py`.
2. Subclass `BrokerProfile`. Set `name`, `allows_hedging`, `preferred_filling`, `rollover_utc_hour`. Implement `retcode_help`.
3. Call `register(YourProfile())` at module bottom.
4. Add `from . import <name>  # noqa: F401` to `mt5_universal/broker/__init__.py`.
5. Add a test in `metatrader5_cli/mt5/tests/`.

## What never changes

- `mt5_universal/bridge/mt5_backend.py` is the only file that imports `MetaTrader5`.
- Every order call passes through `mt5_universal/risk/risk.check_order(..., is_live_intent=...)`.
- Live trading needs all three gates: `cfg["live"]: true` + `MT5_LIVE=1` + `is_live_intent=True`.
- No hardcoded user paths anywhere in `mt5_universal/`, `mt5/`, `mt5_mcp/`. Use `mt5_universal.config.paths.*`.
- Every CLI command returns the standard envelope: `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code": ..., "message": ..., "data": ...}}`.

## Pre-merge checklist

- [ ] `python -m pytest -q` green
- [ ] `git diff --check master...HEAD` clean
- [ ] If you touched a CLI command, `mt5 skills regenerate` was run and the SKILL.md change is committed
- [ ] If you added a `mt5_universal/` module, `tests/test_bridge_singleton.py` and `tests/test_no_hardcoded_paths.py` still pass
- [ ] You added at least one unit test per new function (TDD: write the failing test first)

## See also

- [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](docs/specs/2026-05-15-mt5-universal-agent-native-design.md) — the spec
- [docs/specs/2026-05-15-mt5-universal-review-context.md](docs/specs/2026-05-15-mt5-universal-review-context.md) — what reviewers care about
- [docs/playgrounds/mt5-universal-refactor-playground.html](docs/playgrounds/mt5-universal-refactor-playground.html) — the visual companion
- [CLI-Anything HARNESS.md](https://github.com/HKUDS/CLI-Anything/blob/main/cli-anything-plugin/HARNESS.md) — the SOP we cherry-picked from
```

- [ ] **Step 2: Commit**

```bash
git add MT5_HARNESS.md
git commit -m "Phase 6: write MT5_HARNESS.md — methodology SOP

7-phase recap, how to add a CLI command / EA template / broker
profile, the never-changes list, pre-merge checklist. Models
CLI-Anything's HARNESS.md."
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
- [docs/specs/mt5-cli-spec.md](docs/specs/mt5-cli-spec.md) — historical reference for the legacy core (now archived)
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
grep -rn "import MetaTrader5\|from MetaTrader5" mt5_universal/ mt5/ mt5_mcp/ | grep -v bridge/mt5_backend.py
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
# If SKILL.md drifted: mt5 skills regenerate && git add mt5_universal/skills/SKILL.md && git commit -m "Phase 6: regenerate SKILL.md final pass"
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
| Legacy not imported | `grep -rn "from .core.ehukai\|from .core.analyze\|from .core.tester" mt5_universal/ mt5/ mt5_mcp/` | empty |
| CLI installed | `mt5 --help` | shows ea / indicator / tester / skills groups |
| MCP installed | `mt5-mcp --help` (or stdio smoke) | runs without import errors |
| Phase tags present | `git tag --list 'phase-*-complete'` | 6 tags (phase-1 through phase-6) |
| Origin in sync | `git rev-list --count HEAD...origin/mt5-universal` | 0 |

When all 11 are green: the universal refactor is shipped on the `mt5-universal` branch, ready to merge to `master`.

## After merging — first user EA

The shortest path for an agent to use the new system end-to-end:

```bash
# 1. Scaffold
mt5 ea new my_first --template scalper

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


