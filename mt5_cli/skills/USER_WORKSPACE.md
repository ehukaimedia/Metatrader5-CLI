# User workspace conventions for `metatrader5-cli`

This file describes where the CLI looks for things on the USER's machine.
It ships with the tool so AI agents can introspect it.

## What lives in the user's workspace (CWD where `mt5` runs)

- `./ea/<name>.mq5` and `./ea/<name>.ex5` — user-authored Expert Advisors
- `./indicators/<name>.mq5` and `./indicators/<name>.ex5` — user-authored indicators
- `./presets/<name>.<symbol>.<tf>.set` — tester parameter presets (Phase 4)
- `./results/<run-id>/` — captured tester run artifacts (Phase 4)
- `./.metatrader5-cli.json` — optional per-project config override

## What lives in the user's data dir (XDG_DATA_HOME convention)

When no project-local `./ea` / `./indicators` exists, `mt5` falls back to
the user's data dir. EAs/indicators/presets/results are user-authored
DATA, so they belong under `XDG_DATA_HOME` (not `XDG_CONFIG_HOME`, which
is for settings). Phase 3 placeholder resolution order:

1. `$CWD/ea/` and `$CWD/indicators/` (first preference)
2. `~/.local/share/metatrader5-cli/{ea,indicators}/`

Phase 6 `paths.py` will widen this to the full
`MT5_EA_DIR` / `MT5_INDICATORS_DIR` env override + `$XDG_DATA_HOME` +
`%APPDATA%` / `~/Library/Application Support` chain.

The config FILE itself follows a separate resolution and is a flat JSON
file (XDG_CONFIG_HOME convention):
`MT5_CONFIG` env → `$XDG_CONFIG_HOME/metatrader5-cli.json` →
`%APPDATA%/metatrader5-cli.json` → `~/.config/metatrader5-cli.json`.

## What never lives in this repo

This repo is a tool. It contains no user EAs, no user indicators, no
`.set` presets, no backtest results, no strategy docs. The two
`mt5_cli/mql5/templates/*.mq5` files are minimal MQL5 skeletons (the
boilerplate that MT5 requires); they contain no strategy logic or
opinionated parameters.

## MetaEditor + terminal data dir resolution

- MetaEditor binary: `MT5_METAEDITOR_PATH` env →
  `C:\Program Files\MetaTrader 5\metaeditor64.exe` (and Program Files
  (x86) / AppData variants) → `shutil.which("metaeditor64")`.
- Terminal data dir (for `mt5 ea deploy` to write into
  `MQL5/Experts/`): `MT5_TERMINAL_DATA_DIR` env → newest hash dir under
  `%APPDATA%\MetaQuotes\Terminal\` that contains an `MQL5/` subdir.

Both resolution chains return a clear `*_NOT_FOUND` envelope when no
candidate is reachable, never a Python exception.
