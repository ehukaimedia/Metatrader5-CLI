# MT5 Universal — Agent-Native CLI Refactor (design)

| | |
|---|---|
| Date | 2026-05-15 |
| Branch | `mt5-universal` |
| Status | Active design; Phase 1 archived, Phase 2 builds fresh from archived patterns |
| Companion | [docs/playgrounds/mt5-universal-refactor-playground.html](../playgrounds/mt5-universal-refactor-playground.html) |
| **Reviewers — read first** | [2026-05-15-mt5-universal-review-context.md](2026-05-15-mt5-universal-review-context.md) (locked decisions, scope rules, what feedback is in/out of bounds) |
| Supersedes (when shipped) | [archive/legacy-docs/specs/mt5-cli-spec.md](../../archive/legacy-docs/specs/mt5-cli-spec.md) (the v0.5 spec is now archived as historical reference for the legacy core) |

## 1. Problem

The archived `metatrader5_cli/mt5/` was a 9.9k-LOC, 21-module CLI with the right *bones* — bridge / risk gate / dual JSON+human output — but the **domain semantics were baked into the agnostic layer**:

- `core/ehukai.py` (944 LOC), `core/analyze.py` (1,098 LOC: `sniper_poc`, `topdown`, `place_ready_limit`), `core/tda_manifest.py`, `core/mfe.py` are Ehukai/TDA-specific.
- `core/tester.py` (526 LOC) hardcodes `EhukaiTDAEA` and `AdaptiveTrailEA` — no path for a third EA without source edits.
- `mt5_cli.py` is a 1,869-LOC monolith wiring all the above.
- The bundled MQL5 ships specific assets: `Experts/AdaptiveTrailEA.mq5`, `Experts/EhukaiTDAEA.mq5`, `Hybrid_WPVS_MT5_Bundle/`, an untracked `Advanced_Wavelet_Entry_System/`, and the `WF_FractalPredictor` zip.
- An agent that wants to "use MT5" inherits all of this.

We want **an agnostic, agent-native CLI**: agents (and operators) can author their own MQL5 strategies/indicators, drive MT5's Strategy Tester from the CLI, get JSON results, and do all of it without inheriting a particular trading thesis.

## 2. Goals

1. Strip Ehukai / TDA / wavelet / Hybrid-WPVS semantics out of `core/`. Domain code lives in user plugins, not in the agnostic library.
2. Make MT5's native Strategy Tester (EA + indicator) **fully driveable from the CLI** with structured JSON results.
3. Expose the library as **both an MCP server and a CLI** so MCP-aware agents (Claude Code, Cursor, Claude Desktop) get typed tools while shell-based workflows keep working.
4. Treat **Trading.com as the only currently supported broker**. Its quirks (FOK filling, no hedging, 22:00 UTC rollover, retcode help) live in `mt5_cli/config/trading_com.py` and merge into the standard config loader. Multi-broker support is a later addition; when a second broker is added, refactor to a `BrokerProfile` ABC at that time — do NOT pre-build the abstraction.
5. **Portable**: no hardcoded user paths. Clone anywhere; `pip install -e .` works.

## 3. Non-goals

- Replacing MT5 itself or building a Python-side backtester. The Strategy Tester is the canonical engine.
- Transpiling Python to MQL5 or wrapping MQL5 in a Python DSL. Authors write MQL5 directly.
- Live multi-broker abstraction at the protocol level. Other brokers also go through MT5; broker-specific quirks (filling mode, hedging, retcodes, rollover) currently live in `mt5_cli/config/trading_com.py`. When a second broker is added, factor the shared interface out at that time — do not pre-build the abstraction now.
- Rewriting any in-flight Ehukai / Wavelet / Hybrid-WPVS strategy. Those archive as-is and can be re-introduced as user-dir plugins later.
- **Shipping any custom EA, indicator, strategy doc, backtest result, or workspace dir.** `metatrader5-cli` is a pip-installable tool that gives AI agents (and humans) hands to MT5. Users install via pip and operate `mt5` (CLI) or `mt5-mcp` (MCP server) **from their own external workspace** — they don't clone this repo or edit its code. The `ea/`, `indicators/`, `presets/`, `results/` discovery dirs live in the user's CWD or `~/.local/share/metatrader5-cli/` (XDG_DATA_HOME; `%APPDATA%/metatrader5-cli/` on Windows), **never in this repo**.

## 4. Locked decisions (from brainstorm)

| # | Decision | Rationale |
|---|---|---|
| 1 | "Agnostic" means **all four**: strategy-, indicator-, backtest-, broker-agnostic. Trading.com remains the canonical default profile. | Preserves working today while removing assumptions. |
| 2 | **MQL5 is the canonical author format** for strategies and indicators. Python is the harness only (CLI + MCP + MQL5 scaffolding/compile/deploy + tester drive + results parsing). | MT5 Strategy Tester only runs MQL5; matches what the test environment actually executes. |
| 3 | **MT5 Strategy Tester is THE backtest engine.** Both EA single/optimize/genetic/forward/scanner/stress and Indicator visual tests are CLI-driven. Drop the Python event-driven backtester. | Realistic ticks, broker-side fills, no parallel engine to maintain. |
| 4 | **Hard fork** the existing core. Move legacy to `archive/`. Build the new core from scratch under `mt5_cli/`. | The user explicitly chose this over coexistence; cleanest result. |
| 5 | **Library-first architecture.** Submodule-per-concern Python library. CLI and MCP are thin wrappers over the same library. | Each module has one job; FastMCP tools map 1:1; testable in isolation. |
| 6 | **MCP + CLI dual surface** from one library. Same core powers both. | MCP-aware agents get schemas; shell agents/scripts keep working. |
| 7 | **Portability rails** baked in from day 1. No hardcoded user paths anywhere in `mt5_cli/`, `mt5/`, or `mt5_mcp/`. CI greps source for forbidden path roots. | The user explicitly added this constraint. |

## 5. Design conventions

The library follows 8 conventions that keep agents productive and the codebase honest:

1. **Single bridge module rule** → `mt5_cli/bridge/mt5_backend.py` is the **only** module that imports `MetaTrader5`. AST-enforced via `tests/test_bridge_singleton.py`.
2. **Dual `--json` + human output** for every CLI command. The JSON shape is the canonical envelope (`{"ok": bool, "data": {...}, "error": {...}}`).
3. **`skills/SKILL.md` with YAML frontmatter** (`name`, `description`), command-group tables, examples, and an "For AI Agents" usage protocol. Migrated from the archived 11k-char manifest in `archive/legacy-mt5/skills/SKILL.md` rather than rewritten.
4. **`skill_generator.py`** introspects the Click command tree and regenerates only the command-group tables in `SKILL.md` so they don't drift from the code. The curated workflow narrative stays hand-edited.
5. **`ReplSkin` banner prints SKILL.md path** so an agent can `Read` the skill file directly from the startup banner — no guessing the absolute path.
6. **Templates / scaffolding** for MQL5 sources (`mt5 ea new <name>`, `mt5 indicator new <name>`) — minimal skeletons only, no strategy connotations.
7. **MCP server publication** — `mt5-mcp` entry point exposes the library via FastMCP so agents get typed tools, not just a CLI.
8. **`MT5_HARNESS.md` SOP** — a 7-phase methodology document so future contributors and agents have a written extension SOP for adding commands, EAs, or test surfaces.

## 6. Architecture

### 6.1 Repo layout (target)

```
Metatrader5-CLI/
├── archive/
│   ├── legacy-mt5/               # retired metatrader5_cli/mt5 package, kept as cherry-pick reference
│   ├── legacy-docs/              # retired strategy docs/playgrounds/handoffs/specs
│   └── legacy-mql5/              # Advanced_Wavelet_Entry_System and standalone MQL5 history
├── mt5_cli/                # NEW: agnostic library (pip-installable)
│   ├── bridge/
│   │   └── mt5_backend.py        # the ONE module that imports MetaTrader5
│   ├── config/
│   │   ├── config.py             # 4-layer resolver (DEFAULTS → file → env → CLI overrides)
│   │   └── trading_com.py        # Trading.com-only: FOK, no hedge, 22:00 UTC rollover, retcode_help
│   ├── market/                   # info, tick, depth, sessions, search
│   ├── rates/                    # OHLCV fetch, timeframe enum, pandas DataFrame
│   ├── orders/                   # market/limit/stop, dryrun, modify, cancel
│   ├── positions/                # list, close, modify, breakeven
│   ├── account/                  # info, balance, exposure, daily P&L
│   ├── history/                  # deals, by-strategy, equity curve
│   ├── risk/                     # gate every order passes — preserved from current core/risk.py
│   ├── mql5/                     # MQL5 source management
│   │   ├── compiler.py           # metaeditor64.exe wrapper (.mq5 → .ex5)
│   │   ├── deployer.py           # copy to terminal Experts/Indicators folders
│   │   ├── discovery.py          # discover user EAs/indicators
│   │   └── templates/            # scaffolding templates
│   ├── tester/                   # Strategy Tester driver
│   │   ├── ea.py                 # single / optimize / genetic / forward / scanner / stress
│   │   ├── indicator.py          # visual indicator test
│   │   ├── ini_builder.py        # generate tester .ini + .set files
│   │   ├── launcher.py           # fresh terminal64.exe /config batch mode
│   │   ├── results.py            # parse HTML + journal CSV + opt XML → JSON
│   │   └── cache.py              # results/<run-id>/ snapshots
│   ├── config/
│   │   ├── __init__.py           # 4-layer resolution (DEFAULTS → file → env → CLI)
│   │   └── paths.py              # XDG_CONFIG_HOME / APPDATA / HOME resolution
│   ├── reports/                  # JSON envelopes, backtest reports
│   └── skills/
│       └── SKILL.md              # migrated from archive/legacy-mt5/skills/SKILL.md
├── mt5/                          # CLI package — `pip install -e .` installs `mt5` script
│   └── cli.py                    # thin click wrappers calling mt5_cli.*
├── mt5_mcp/                      # MCP server — installs `mt5-mcp` script
│   └── server.py                 # FastMCP tools mapping 1:1 to mt5_cli functions
├── docs/
│   ├── specs/                    # this file lives here
│   ├── playgrounds/              # the refactor playground lives here
│   └── ...
├── MT5_HARNESS.md                # 7-phase methodology SOP for adding new commands
├── setup.py                      # declares both `mt5` and `mt5-mcp` console scripts
└── pytest.ini
```

User-side `ea/`, `indicators/`, `presets/`, and `results/` directories are deliberately **not** part of this repo. The tool discovers them from the user's current working directory or platform data/config directories.

### 6.2 MQL5 inventory (corrected per [code review 2026-05-15](../code-reviews/codex-mt5-universal-playground-review-2026-05-15.md) finding 2)

What lived at `metatrader5_cli/mt5/mql5/` before the wholesale archive move, now preserved under `archive/legacy-mt5/mql5/` unless otherwise noted:

| Path | Tracked? | Contents |
|---|---|---|
| `Experts/AdaptiveTrailEA.mq5` | ✅ | Trail EA (BE + Chandelier reference) |
| `Experts/EhukaiTDAEA.mq5` | ✅ | TDA sniper EA |
| `Hybrid_WPVS_MT5_Bundle/` | ✅ | Hybrid WPVS Diagnostic + Top3 Execution EAs + .set presets + README |
| `Hybrid_WPVS_MT5_Bundle.zip` | ❌ ignored by `.gitignore: *.zip` | Snapshot zip on disk; not tracked |
| `Advanced_Wavelet_Entry_System/` | ❌ untracked | In-flight wavelet research (commit before archive) |
| `Advanced_Wavelet_Entry_System.zip` | ❌ ignored by `.gitignore: *.zip` | Snapshot zip on disk; not tracked |
| `Indicators/` | ✅ | Custom MT5 indicators |
| `WF_FractalPredictor_MQ5_v1_10.zip` | ❌ ignored by `.gitignore: *.zip` | Snapshot zip on disk; not tracked |

**Phase 1 result:** the separately developed `Advanced_Wavelet_Entry_System/` source tree is preserved under `archive/legacy-mql5/Advanced_Wavelet_Entry_System/`. Ignored `.zip` snapshots remain non-source artifacts and are not part of the live universal tool.

### 6.3 Module boundary rules

- `mt5_cli/bridge/mt5_backend.py` is the **only** module that imports `MetaTrader5`. CI test enforces this.
- `mt5_cli/risk/` is called from `orders/` for **every** order call. CLI, MCP, plugin code, direct library import — all paths flow through it. Non-negotiable; preserved from the archived [mt5-cli-spec.md](../../archive/legacy-docs/specs/mt5-cli-spec.md) §1.
- Plugins (user EAs/indicators) never import from `mt5/` (CLI) or `mt5_mcp/`. Read-only relationship.
- `ea/` and `indicators/` user dirs are searched in this order: current working directory → `~/.local/share/metatrader5-cli/{ea,indicators}/` (XDG_DATA_HOME convention; `%APPDATA%/metatrader5-cli/` on Windows) → installed entry points. First-match wins.

## 7. Strategy Tester contract (Phase 4)

Maps 1:1 to MT5's Strategy Tester Settings panel knobs:

```bash
mt5 tester ea single \
  --expert my_strategy \
  --symbol AUDUSD --tf M5 \
  --from 2021-05-09 --to 2026-05-09 \
  --modelling real-ticks  | ohlc-1m | every-tick \
  --delays zero | random-min | random-medium | random-strong | NN-ms \
  --deposit 10000 --currency USD --leverage 1:50 \
  --visual                                  # opens visual mode in MT5
  --json
```

Other forms:

| Command | Purpose |
|---|---|
| `mt5 tester ea optimize --mode complete | genetic | math --param "..." --forward 2024-09-07` | Parameter sweep with optional forward window |
| `mt5 tester ea scanner --symbols AUDUSD,EURUSD,GBPUSD,USDJPY` | Market Scanner mode |
| `mt5 tester ea stress --delays 50ms` | Stress & Delays mode |
| `mt5 tester indicator visual --indicator my_signal --symbol AUDUSD --tf M5 --from … --to … --modelling ohlc-1m` | Indicator visual test (matches the right-pane "Indicator visual test:" rows in the tester history) |
| `mt5 tester list` | Recent runs from `results/` |
| `mt5 tester show <run-id>` | Compact summary |
| `mt5 --json tester show <run-id>` | Full structured envelope |

**Result envelope shape** (returned by `tester.results.parse()`):

```json
{
  "ok": true,
  "data": {
    "run_id": "2026-05-15T14-22-05_my_strategy_AUDUSD_M5",
    "expert": "my_strategy",
    "symbol": "AUDUSD",
    "timeframe": "M5",
    "from": "2021-05-09",
    "to": "2026-05-09",
    "modelling": "real-ticks",
    "deposit": 10000,
    "currency": "USD",
    "leverage": "1:50",
    "stats": {
      "total_trades": 412,
      "win_rate": 0.58,
      "profit_factor": 1.42,
      "max_drawdown_pct": 12.3,
      "sharpe": 0.91,
      "expectancy": 4.2
    },
    "deals": [ {"time": "...", "symbol": "...", "type": "buy", "volume": 0.10, "price": 0.6543, "profit": 12.34}, ... ],
    "equity_curve": [ {"time": "...", "balance": 10000, "equity": 10012}, ... ],
    "journal_events": [ {"time": "...", "level": "info", "msg": "..."}, ... ]
  }
}
```

No agent ever scrapes the HTML report or parses `Tester.log` itself — `tester.results` does it once and serves JSON.

## 8. Phase plan

Each phase gets its own commit (or PR-equivalent), green tests, and a HEAD tag.

### Phase 0 — Baseline (✅ done as of `f481fc0`)
- Branch `mt5-universal` off master. `pytest.ini` cleaned (was referencing the moved `adaptive-forex-mt5/tests`). 240 passed, 1 skipped.
- This spec + the playground are the planning artifacts that ship before Phase 1.

### Phase 1 — Archive legacy (✅ done by wholesale user move)
- The entire `metatrader5_cli/mt5/` tree was relocated to `archive/legacy-mt5/` as reference material.
- Strategy-flavored docs/playgrounds/handoffs/specs moved to `archive/legacy-docs/`.
- The standalone `Advanced_Wavelet_Entry_System/` tree moved under `archive/legacy-mql5/`; the old in-package MQL5 assets remain preserved under `archive/legacy-mt5/mql5/`.
- The live `metatrader5_cli/` package is gone. No compatibility shim or `mt5-legacy` entry point exists.
- **Acceptance:** current suite is green via the transitional placeholder (`1 passed`), `archive/` is git-tracked, and no live module imports `MetaTrader5` because the new bridge has not landed yet.

### Phase 2 — `mt5_cli/` skeleton
- Create the submodule tree from §6.1.
- Recreate the surviving primitives fresh under `mt5_cli/`, cherry-picking patterns from `archive/legacy-mt5/core/` and `archive/legacy-mt5/utils/mt5_backend.py` without importing or moving the archived package back into the live tree.
- Submodules built: `bridge/` (single MetaTrader5 importer), `market/`, `rates/`, `account/`, `history/`, `risk/`, `orders/`, `positions/`, `reports/`, `config/`, `chart/` (pure Win32 + `chart/indicators_attach.py` bridge-mediated), `screenshot/`.
- **Single-broker scope:** Trading.com only. `mt5_cli/config/trading_com.py` ships `TRADING_COM_DEFAULTS` (FOK filling, no hedging, 22:00 UTC rollover) merged into `config.DEFAULTS`, plus `retcode_help()` for actionable MT5 retcode explanations. NO `BrokerProfile` ABC, NO `generic_mt5.py` — multi-broker is a later addition.
- CI guard: `tests/test_bridge_singleton.py` (AST-based) fails the suite if any module besides `mt5_cli/bridge/mt5_backend.py` imports MetaTrader5.
- **Acceptance (Phase 2 complete at tag `phase-2-complete`):**
  - `from mt5_cli import market, rates, orders, positions, account, history, risk` — no ImportError
  - `from mt5_cli.chart import switch_tf, symbol, ensure_chart, find_window, current_title, attach, attach_ea, new_chart, close_chart, cycle_chart` — no ImportError. The five GUI menu-poke / MDI primitives (`attach`, `attach_ea`, `new_chart`, `close_chart`, `cycle_chart`) share the helpers in `mt5_cli/chart/_menu.py` (see Task 2.8 for `attach`, Task 2.13 for `new_chart`, Task 2.14 for `attach_ea` + `cycle_chart` + `close_chart` + the `ensure_chart` upgrade).
  - `from mt5_cli.screenshot import take, dom, annotate` — no ImportError
  - `MT5_CONFIG=/nonexistent.json python -c "from mt5_cli.config import load, retcode_help; cfg = load(); print(cfg['filling'], cfg.get('rollover_utc_hour'))"` prints `FOK 22`
  - `python -m pytest -q` returns 214 passed (or higher as Phase 3+ grows the suite)
  - `git grep -n "import MetaTrader5\|from MetaTrader5" -- mt5_cli` returns only `mt5_cli/bridge/mt5_backend.py:10`

### Phase 3 — `mt5` CLI + MQL5 plugin host

Phase 3 ships in two sub-phases:

**3a (SHIPPED, tag `phase-3a-complete` at `854f9dd`): `mt5` CLI around the Phase 2 library.**
- `mt5/` package shipped (`cli.py`, `emit.py`, `__init__.py`, `__main__.py`).
- `mt5 = mt5.cli:main` console_script registered in `setup.py`.
- 11 command groups exposing the full Phase 2 library:
  `connect`, `status`, `account`, `market`, `rates`, `order`, `position`,
  `history`, `chart`, `screenshot`, `config`. Global `--json` flag for
  agent-parseable output; per-command `--live` flag on mutating order /
  position commands (one third of the live triple lock).
- `EnvelopeGroup` wraps every Click `UsageError` into an
  `MT5_INVALID_PARAMS` envelope (post-Codex P1 #2 fix at `804ec03`), so
  invalid args produce structured failure on stdout with exit 0 — never
  the default Click usage-text-to-stderr-with-exit-2 path.
- Three Codex review cycles ran on this phase (`384bd17` → `8fc6227` →
  `854f9dd`); all 11 findings closed across two Kirk fix commits
  (`804ec03`, `3269f7b`, `6515738`).
- **Acceptance (3a) — verified at `854f9dd`:**
  - `pytest -q` → **367 passed**
  - `mt5 --help` → all 11 groups listed
  - `mt5 --json config show` → resolved DEFAULTS with `filling=FOK`,
    `rollover_utc_hour=22`, login/password masked by default
  - `mt5 --json status` → live account envelope (`trade_allowed=True`)
  - `mt5 --json order poll-fill <ticket> --timeout 0.5` → `ok=true`
    envelope, exit 0 (P1 #1 regression-watch)
  - `mt5 --json order market <sym> junk ...` → `MT5_INVALID_PARAMS`
    envelope, exit 0 (P1 #2 regression-watch)
  - `mt5 --json history orders --from garbage` →
    `MT5_INVALID_PARAMS` envelope, exit 0, NO MT5 connection
    attempted (P2 #7 regression-watch)
  - `mt5 --json chart close <stale-hwnd>` → `CHART_ID_NOT_FOUND`
    envelope, exit 0, zero Win32 messages posted (post-Codex
    attach_ea-pattern regression-watch at `6515738`)
  - Full 24-row live smoke matrix passed against Trading.com demo
    (`mt5 chart find-window` / `chart list` / `chart cycle` /
    `market info / tick / search` / `rates fetch` / `order dryrun`
    / `history stats` / `screenshot take`). 3 live charts enumerated,
    real OHLCV bars, 186 KB PNG captured.
  - Bridge singleton holds: `git grep "import MetaTrader5" -- mt5_cli mt5`
    returns only `mt5_cli/bridge/mt5_backend.py:10`.

**3b (TODO): MQL5 plugin host.**
- Add `mt5_cli/mql5/{compiler,deployer,discovery,templates}.py`.
- Document the user workspace convention. `mt5 ea new` / `mt5 indicator
  new` create `./ea` or `./indicators` in the user's current working
  directory when invoked; this repo does not ship those directories.
- Wire `mt5 ea new <name>`, `mt5 ea compile <name>`, `mt5 ea deploy
  <name>`, and the indicator equivalents.
- **Acceptance (3b):** from a user workspace, `mt5 ea new demo && mt5
  ea compile demo && mt5 ea deploy demo` produces `./ea/demo.ex5` and a
  copy in the terminal's `Experts/` folder. (Only the minimal MQL5
  skeleton ships; strategy-flavored variants like scalper/swing are
  deliberately NOT shipped per locked decision #10 — hands, not
  strategies.)

### Phase 4 — Strategy Tester driver
- **Implementation status:** reviewed GO on branch `mt5-universal` at
  `aaf08dc` after Spock re-review. The shipped code includes
  `mt5_cli/tester/{ea,indicator,ini_builder,launcher,results,cache}.py`,
  CLI wiring for `mt5 tester ea/indicator/list/show`, HTML report + journal
  CSV + optimization XML parsing, emitted `equity_curve`, safe malformed
  journal handling, direct-library invalid-modelling envelopes, and optimize
  `.set` / `--param` support.
- **Live close-out status:** not yet tagged `phase-4-complete`. Trading.com
  DEMO is a live broker execution environment and must be handled with live
  operational caution. Screenshot-backed diagnosis on 2026-05-17 HST showed
  MT5 does not apply a Strategy Tester `[Tester]` block to an already-running
  `terminal64.exe`; the UI remained on the prior indicator configuration.
  The CLI now treats Strategy Tester batch mode as a fresh-terminal `/config`
  startup contract and returns `TERMINAL_ALREADY_RUNNING` instead of a
  misleading `TESTER_REPORT_MISSING` envelope when MT5 is open. Full EA smoke
  still requires an operator-approved close/relaunch proof. Live
  trade-placement smoke is also gated by broker market hours; the latest
  attempted AUDUSD market order returned MT5 retcode `10018` (`Market closed`)
  after `order dryrun` passed.
- **Acceptance before tag:** `mt5 tester ea single --expert demo --symbol
  AUDUSD --tf M5 --from 2024-01-01 --to 2024-06-30 --modelling ohlc-1m
  --json` returns a populated envelope; `mt5 tester indicator visual` produces
  a captured run; live-style order smoke is run only with tiny volume and
  explicit operator intent, with open position/pending order cleanup verified.

### Phase 5 — Agent surface
- Migrate `archive/legacy-mt5/skills/SKILL.md` → `mt5_cli/skills/SKILL.md`. Add YAML frontmatter (`name`, `description`).
- Add `mt5_mcp/server.py` with FastMCP. One MCP tool per top-level CLI command group.
- Recreate the archived ReplSkin pattern in the new CLI so the banner prints the SKILL.md absolute path.
- Add `skill_generator.py` that introspects the Click tree and regenerates only the *Command Groups* section of SKILL.md (the curated workflow narrative stays hand-edited).
- **Acceptance:** `mt5-mcp` runs as a stdio MCP server; `claude mcp add mt5 mt5-mcp` makes the tools visible to Claude Code; banner shows SKILL.md path.

### Phase 6 — Portability + tests + harness doc
- `mt5_cli/config/paths.py` resolves `MT5_CONFIG`, `MT5_EA_DIR`, `MT5_INDICATORS_DIR`, `MT5_PRESETS_DIR`, `MT5_RESULTS_DIR`, `MT5_CACHE_DIR`, `MT5_LOG_DIR` against XDG / APPDATA / HOME.
- `tests/test_no_hardcoded_paths.py` greps `mt5_cli/`, `mt5/`, `mt5_mcp/` for `C:\Users\`, `/home/`, `/Users/`, hardcoded drive letters. Fails on any hit.
- Full pytest pyramid: unit (mocked bridge) + tester smoke (gated on `MT5_DEMO_INTEGRATION=1`).
- Write `MT5_HARNESS.md` documenting the 7-phase methodology for adding new commands or new EAs.
- **Acceptance:** suite runs on a fresh clone with no path edits; CI guard is green; `MT5_HARNESS.md` exists and links from README.

## 9. Risk-gate non-negotiables (preserved)

From the archived [mt5-cli-spec.md](../../archive/legacy-docs/specs/mt5-cli-spec.md) §1 — these survive the refactor unchanged:

1. `mt5_cli/risk/` runs for **every** order call. Library callers cannot bypass it.
2. `--strategy-id TEXT` on all order commands. Auto-derives magic via `sha256(id)[:8] % 80000 + 100000` → range `[100000, 180000)`.
3. Same JSON envelope (`{"ok": true/false, "data"/{...}, "error": {...}}`) returned by CLI `--json` and direct Python import.
4. Live trading requires all three gates: `cfg["live"]: true` + `MT5_LIVE=1` env + `--live` CLI flag.

## 10. Portability rules

No code in `mt5_cli/`, `mt5/`, or `mt5_mcp/` may contain absolute user paths, hardcoded MT5 install paths, hardcoded monitor indices, or machine-specific usernames/logins/account numbers. All paths route through `mt5_cli.config.paths`. CI test (`tests/test_no_hardcoded_paths.py`) greps the source tree and fails on any hit.

Library code runs on Linux/macOS for development, testing, and *backtest mode* against cached data. Live mode short-circuits with a clear "MT5 terminal not available on this OS" if not on Windows.

## 11. Resolved Phase 1 questions

These questions were open before Phase 1 and are now resolved by the wholesale archive move:

1. `archive/` is git-tracked.
2. Strategy-flavored docs/playgrounds/handoffs/specs are under `archive/legacy-docs/`.
3. `Advanced_Wavelet_Entry_System/` is preserved under `archive/legacy-mql5/`.
4. `archive/wf-fractal-cleanup-20260510-195855/` remains as historical cleanup material.

## 12. References

- [docs/playgrounds/mt5-universal-refactor-playground.html](../playgrounds/mt5-universal-refactor-playground.html) — interactive 7-phase walkthrough, click-to-comment, generates a markdown brief for review
- [docs/code-reviews/codex-mt5-universal-playground-review-2026-05-15.md](../code-reviews/codex-mt5-universal-playground-review-2026-05-15.md) — review that prompted this spec (P1)
- [archive/legacy-docs/specs/mt5-cli-spec.md](../../archive/legacy-docs/specs/mt5-cli-spec.md) — historical CLI spec (v0.5) for the archived legacy core
- [archive/legacy-mt5/skills/SKILL.md](../../archive/legacy-mt5/skills/SKILL.md) — existing 11k-char SKILL.md being migrated in Phase 5
- MT5 Strategy Tester docs (in MetaTrader5 terminal Help)
