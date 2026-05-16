# MT5 Universal — Agent-Native CLI Refactor (design)

| | |
|---|---|
| Date | 2026-05-15 |
| Branch | `mt5-universal` |
| Status | Draft (brainstorm done, ready for review → plan) |
| Companion | [docs/playgrounds/mt5-universal-refactor-playground.html](../playgrounds/mt5-universal-refactor-playground.html) |
| **Reviewers — read first** | [2026-05-15-mt5-universal-review-context.md](2026-05-15-mt5-universal-review-context.md) (locked decisions, scope rules, what feedback is in/out of bounds) |
| Supersedes (when shipped) | [docs/specs/mt5-cli-spec.md](mt5-cli-spec.md) (the v0.5 spec keeps as historical reference for the legacy core) |

## 1. Problem

Today's `metatrader5_cli/mt5/` is a 9.9k-LOC, 21-module CLI with the right *bones* — bridge / risk gate / dual JSON+human output — but the **domain semantics are baked into the agnostic layer**:

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
4. Treat **Trading.com as the canonical default broker profile**, not as a hardcoded assumption — generalize to other MT5 brokers via a small `BrokerProfile` abstraction.
5. **Portable**: no hardcoded user paths. Clone anywhere; `pip install -e .` works.

## 3. Non-goals

- Replacing MT5 itself or building a Python-side backtester. The Strategy Tester is the canonical engine.
- Transpiling Python to MQL5 or wrapping MQL5 in a Python DSL. Authors write MQL5 directly.
- Live multi-broker abstraction at the protocol level. Other brokers go through MT5 too; the broker layer just captures broker-quirk differences (filling mode, hedging, retcodes, rollover).
- Rewriting any in-flight Ehukai / Wavelet / Hybrid-WPVS strategy. Those archive as-is and can be re-introduced as user-dir plugins later.

## 4. Locked decisions (from brainstorm)

| # | Decision | Rationale |
|---|---|---|
| 1 | "Agnostic" means **all four**: strategy-, indicator-, backtest-, broker-agnostic. Trading.com remains the canonical default profile. | Preserves working today while removing assumptions. |
| 2 | **MQL5 is the canonical author format** for strategies and indicators. Python is the harness only (CLI + MCP + MQL5 scaffolding/compile/deploy + tester drive + results parsing). | MT5 Strategy Tester only runs MQL5; matches what the test environment actually executes. |
| 3 | **MT5 Strategy Tester is THE backtest engine.** Both EA single/optimize/genetic/forward/scanner/stress and Indicator visual tests are CLI-driven. Drop the Python event-driven backtester. | Realistic ticks, broker-side fills, no parallel engine to maintain. |
| 4 | **Hard fork** the existing core. Move legacy to `archive/`. Build the new core from scratch under `mt5_universal/`. | The user explicitly chose this over coexistence; cleanest result. |
| 5 | **Library-first architecture.** Submodule-per-concern Python library. CLI and MCP are thin wrappers over the same library. | Each module has one job; FastMCP tools map 1:1; testable in isolation. |
| 6 | **MCP + CLI dual surface** from one library. Same core powers both. | MCP-aware agents get schemas; shell agents/scripts keep working. |
| 7 | **Portability rails** baked in from day 1. No hardcoded user paths anywhere in `mt5_universal/`, `mt5/`, or `mt5_mcp/`. CI greps source for forbidden path roots. | The user explicitly added this constraint. |

## 5. Cherry-picked patterns from CLI-Anything

[CLI-Anything](https://github.com/HKUDS/CLI-Anything) ships a `cli-anything-plugin/HARNESS.md` SOP + a registry of agent-native CLIs. We adopt 8 patterns:

1. **Single `utils/<app>_backend.py` rule** → reinforced as `mt5_universal/bridge/mt5_backend.py` being the **only** module that imports `MetaTrader5`.
2. **Dual `--json` + human output** → already present, kept as the contract for every command.
3. **`skills/SKILL.md` template** with YAML frontmatter (`name`, `description`), command-group tables, examples, **"For AI Agents" usage protocol** → applied to the existing `metatrader5_cli/mt5/skills/SKILL.md` (currently 11k chars, hand-maintained, no frontmatter) by *migrating* it.
4. **`skill_generator.py`** → introspects the Click command tree and regenerates the command-group tables in `SKILL.md` so they don't drift from the code. The curated workflow narrative stays hand-edited.
5. **`ReplSkin` banner that prints SKILL.md path** → the existing `utils/repl_skin.py` is upgraded so REPL startup shows the absolute path, letting an agent read the skill file via `Read` without guessing.
6. **Templates / scaffolding** → `mt5 ea new <name> --template scalper` and `mt5 indicator new <name> --template oscillator` scaffold MQL5 source from packaged templates, mirroring CLI-Anything's `templates/` pattern.
7. **MCP backend pattern, *inverted*** → CLI-Anything's `guides/mcp-backend.md` shows how to *consume* an MCP backend; we *publish* `mt5_universal` as an MCP server (`mt5-mcp` entry point, FastMCP).
8. **HARNESS.md SOP + per-plugin TEST.md** → adopted as `MT5_HARNESS.md` (7-phase methodology) so future contributors and agents have a written extension SOP.

## 6. Architecture

### 6.1 Repo layout (target)

```
Metatrader5-CLI/
├── archive/
│   ├── legacy-core/              # everything moved out of metatrader5_cli/mt5/core/ in Phase 1
│   └── legacy-mql5/              # full MQL5 tree archived (see §6.2 inventory)
├── mt5_universal/                # NEW: agnostic library (pip-installable)
│   ├── bridge/
│   │   └── mt5_backend.py        # the ONE module that imports MetaTrader5
│   ├── broker/
│   │   ├── base.py               # BrokerProfile ABC
│   │   ├── trading_com.py        # canonical default — FOK, no hedge, 22:00 UTC rollover
│   │   └── generic_mt5.py        # permissive default for other brokers
│   ├── market/                   # info, tick, depth, sessions, search
│   ├── rates/                    # OHLCV fetch, timeframe enum, pandas DataFrame
│   ├── indicators/               # python quicklook ONLY (ema/atr/rsi/sma/bbands/fvg/swing_pivots)
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
│   │   ├── launcher.py           # terminal64.exe /config + portable mode
│   │   ├── results.py            # parse HTML + journal CSV + opt XML → JSON
│   │   └── cache.py              # results/<run-id>/ snapshots
│   ├── config/
│   │   ├── __init__.py           # 4-layer resolution (DEFAULTS → file → env → CLI)
│   │   └── paths.py              # XDG_CONFIG_HOME / APPDATA / HOME resolution
│   ├── reports/                  # JSON envelopes, backtest reports
│   └── skills/
│       └── SKILL.md              # migrated from metatrader5_cli/mt5/skills/SKILL.md
├── mt5/                          # CLI package — `pip install -e .` installs `mt5` script
│   └── cli.py                    # thin click wrappers calling mt5_universal.*
├── mt5_mcp/                      # MCP server — installs `mt5-mcp` script
│   └── server.py                 # FastMCP tools mapping 1:1 to mt5_universal functions
├── ea/                           # user MQL5 EAs (auto-discovered) — .gitkeep + examples/
├── indicators/                   # user MQL5 indicators (auto-discovered) — .gitkeep + examples/
├── presets/                      # tester .set files per strategy — .gitkeep
├── results/                      # tester report snapshots (gitignored)
├── docs/
│   ├── specs/                    # this file lives here
│   ├── playgrounds/              # the refactor playground lives here
│   └── ...
├── MT5_HARNESS.md                # 7-phase methodology SOP for adding new commands
├── setup.py                      # declares both `mt5` and `mt5-mcp` console scripts
└── pytest.ini
```

### 6.2 MQL5 inventory (corrected per [code review 2026-05-15](../code-reviews/codex-mt5-universal-playground-review-2026-05-15.md) finding 2)

What actually lives at `metatrader5_cli/mt5/mql5/` today, all bound for `archive/legacy-mql5/` in Phase 1:

| Path | Tracked? | Contents |
|---|---|---|
| `Experts/AdaptiveTrailEA.mq5` | ✅ | Trail EA (BE + Chandelier reference) |
| `Experts/EhukaiTDAEA.mq5` | ✅ | TDA sniper EA |
| `Hybrid_WPVS_MT5_Bundle/` | ✅ | Hybrid WPVS Diagnostic + Top3 Execution EAs + .set presets + README |
| `Hybrid_WPVS_MT5_Bundle.zip` | ✅ | Snapshot zip of the bundle |
| `Advanced_Wavelet_Entry_System/` | ❌ untracked | In-flight wavelet research (commit before archive) |
| `Advanced_Wavelet_Entry_System.zip` | ❌ untracked | Snapshot zip |
| `Indicators/` | ✅ | Custom MT5 indicators |
| `WF_FractalPredictor_MQ5_v1_10.zip` | ✅ | Fractal predictor zip |

**Critical Phase 1 prerequisite:** the untracked Advanced Wavelet files must be committed *before* the archive move so the move is captured in git history.

### 6.3 Module boundary rules

- `mt5_universal/bridge/mt5_backend.py` is the **only** module that imports `MetaTrader5`. CI test enforces this.
- `mt5_universal/risk/` is called from `orders/` for **every** order call. CLI, MCP, plugin code, direct library import — all paths flow through it. Non-negotiable; preserved from [mt5-cli-spec.md](mt5-cli-spec.md) §1.
- Plugins (user EAs/indicators) never import from `mt5/` (CLI) or `mt5_mcp/`. Read-only relationship.
- `strategies/` and `indicators/` user dirs are searched in this order: repo root → `~/.config/mt5-universal/{ea,indicators}/` → installed entry points. First-match wins.

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
| `mt5 tester results <run-id> --json` | Full structured envelope |

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

### Phase 1 — Archive legacy
- Commit untracked `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System*` first so its history is captured.
- Remove `archive/` from `.gitignore` (currently excluded — would silently swallow the moved files).
- `git mv` Ehukai/TDA-flavored core modules → `archive/legacy-core/`.
- `git mv` the full `metatrader5_cli/mt5/mql5/` tree → `archive/legacy-mql5/`.
- Strip the corresponding imports from `mt5_cli.py` (or quarantine the whole CLI behind a deprecation entry-point named `mt5-legacy` until Phase 5 takes over).
- **Acceptance:** unit tests still green for the surviving modules; archived modules are reachable in git history but not imported.

### Phase 2 — `mt5_universal/` skeleton
- Create the submodule tree from §6.1.
- Move (don't rewrite) the surviving primitives: `bridge`, `market`, `rates`, `account`, `history`, `orders`, `positions`, `risk` from `metatrader5_cli/mt5/core/` into their new homes.
- Add `broker/base.py` ABC. Extract Trading.com quirks (FOK, no-hedge, 22:00 UTC rollover, retcode map) from current code into `broker/trading_com.py`. Add a permissive `broker/generic_mt5.py`.
- Add `indicators/` (python quicklook only — `ema`, `atr`, `rsi`, `sma`, `bbands`, `fvg`, `swing_pivots`).
- **Acceptance:** unit tests pass against the new module paths; `from mt5_universal import market, rates, orders, risk` works.

### Phase 3 — MQL5 plugin host
- Add `mt5_universal/mql5/{compiler,deployer,discovery,templates}.py`.
- Create `ea/` and `indicators/` user dirs at repo root with `.gitkeep` + `examples/`.
- Wire `mt5 ea new <name>`, `mt5 ea compile <name>`, `mt5 ea deploy <name>`, and the indicator equivalents.
- **Acceptance:** `mt5 ea new demo --template scalper && mt5 ea compile demo && mt5 ea deploy demo` produces an `ea/demo.ex5` and a copy in the terminal's `Experts/` folder.

### Phase 4 — Strategy Tester driver
- Add `mt5_universal/tester/{ea,indicator,ini_builder,launcher,results,cache}.py`.
- Wire CLI commands per §7.
- Implement results parser for HTML report + journal CSV + optimization XML.
- **Acceptance:** `mt5 tester ea single --expert demo --symbol AUDUSD --tf M5 --from 2024-01-01 --to 2024-06-30 --modelling ohlc-1m --json` returns a populated envelope; `mt5 tester indicator visual` produces a captured run.

### Phase 5 — Agent surface
- Migrate `metatrader5_cli/mt5/skills/SKILL.md` → `mt5_universal/skills/SKILL.md`. Add YAML frontmatter (`name`, `description`).
- Add `mt5_mcp/server.py` with FastMCP. One MCP tool per top-level CLI command group.
- Upgrade `utils/repl_skin.py` to print the SKILL.md absolute path on banner.
- Add `skill_generator.py` that introspects the Click tree and regenerates only the *Command Groups* section of SKILL.md (the curated workflow narrative stays hand-edited).
- **Acceptance:** `mt5-mcp` runs as a stdio MCP server; `claude mcp add mt5 mt5-mcp` makes the tools visible to Claude Code; banner shows SKILL.md path.

### Phase 6 — Portability + tests + harness doc
- `mt5_universal/config/paths.py` resolves `MT5_CONFIG`, `MT5_STRATEGIES_DIR`, `MT5_INDICATORS_DIR`, `MT5_CACHE_DIR`, `MT5_LOG_DIR` against XDG / APPDATA / HOME.
- `tests/test_no_hardcoded_paths.py` greps `mt5_universal/`, `mt5/`, `mt5_mcp/` for `C:\Users\`, `/home/`, `/Users/`, hardcoded drive letters. Fails on any hit.
- Full pytest pyramid: unit (mocked bridge) + tester smoke (gated on `MT5_DEMO_INTEGRATION=1`).
- Write `MT5_HARNESS.md` documenting the 7-phase methodology for adding new commands or new EAs.
- **Acceptance:** suite runs on a fresh clone with no path edits; CI guard is green; `MT5_HARNESS.md` exists and links from README.

## 9. Risk-gate non-negotiables (preserved)

From [mt5-cli-spec.md](mt5-cli-spec.md) §1 — these survive the refactor unchanged:

1. `mt5_universal/risk/` runs for **every** order call. Library callers cannot bypass it.
2. `--strategy-id TEXT` on all order commands. Auto-derives magic via `sha256(id)[:8] % 80000 + 100000` → range `[100000, 180000)`.
3. Same JSON envelope (`{"ok": true/false, "data"/{...}, "error": {...}}`) returned by CLI `--json` and direct Python import.
4. Live trading requires all three gates: `cfg["live"]: true` + `MT5_LIVE=1` env + `--live` CLI flag.

## 10. Portability rules

No code in `mt5_universal/`, `mt5/`, or `mt5_mcp/` may contain absolute user paths, hardcoded MT5 install paths, hardcoded monitor indices, or machine-specific usernames/logins/account numbers. All paths route through `mt5_universal.config.paths`. CI test (`tests/test_no_hardcoded_paths.py`) greps the source tree and fails on any hit.

Library code runs on Linux/macOS for development, testing, and *backtest mode* against cached data. Live mode short-circuits with a clear "MT5 terminal not available on this OS" if not on Windows.

## 11. Open questions / decisions pending

These are deliberately not locked yet; they're surfaced for review before Phase 1:

1. `archive/` in `.gitignore` — recommend removing so archived code is tracked in git history. Phase 1 prerequisite.
2. Untracked Advanced Wavelet docs (12 files at `docs/specs/`, `docs/plans/`, `docs/playgrounds/`, `docs/code-reviews/`) — commit as historical record, archive alongside the code, or discard?
3. Untracked `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/` — must be committed before the Phase 1 archive move to capture the history.
4. `archive/wf-fractal-cleanup-20260510-195855/` — local cleanup snapshot, keep or delete?

## 12. References

- [docs/playgrounds/mt5-universal-refactor-playground.html](../playgrounds/mt5-universal-refactor-playground.html) — interactive 7-phase walkthrough, click-to-comment, generates a markdown brief for review
- [docs/code-reviews/codex-mt5-universal-playground-review-2026-05-15.md](../code-reviews/codex-mt5-universal-playground-review-2026-05-15.md) — review that prompted this spec (P1)
- [docs/specs/mt5-cli-spec.md](mt5-cli-spec.md) — current canonical CLI spec (v0.5), historical reference for the legacy core layer being archived
- [metatrader5_cli/mt5/skills/SKILL.md](../../metatrader5_cli/mt5/skills/SKILL.md) — existing 11k-char SKILL.md being migrated in Phase 5
- [CLI-Anything](https://github.com/HKUDS/CLI-Anything) — `cli-anything-plugin/HARNESS.md` SOP, `templates/SKILL.md.template`, `cli-hub-meta-skill/SKILL.md`, `guides/mcp-backend.md`
- MT5 Strategy Tester docs (in MetaTrader5 terminal Help)
