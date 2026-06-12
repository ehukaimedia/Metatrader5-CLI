# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `mt5 tester ea stress` now runs a real execution-delay ladder using MT5's
  native `ExecutionMode` setting (ideal, fixed millisecond delays, and random),
  caches each rung under its own `results/<run-id>/`, and returns a `stress.v1`
  envelope with a deterministic robustness score (`robust` / `degraded` /
  `fragile` / `ungraded`) — the worst-case profit retention versus the ideal
  baseline. New `--delays` flag accepts comma-separated millisecond integers
  and/or `random`.
- `build_ea_ini(execution_mode=...)` and `tester.ea.single(delay_ms=...)` thread
  the order-execution delay through the INI layer; new `mt5_cli.tester.stress`
  module owns delay parsing, ladder normalization, and scoring.
- `mt5 chart zoom in|out|set` controls MT5 chart zoom through Win32 keyboard
  input so agents can tune chart density before `mt5 screenshot take`.
- Proposed the alert-seeded trading decision architecture, including permission
  modes for notification-only, ask-before-trade, and dry-run flows.

### Changed

- **Breaking:** `mt5 tester ea stress` replaces the `--delays-ms` flag (and the
  `tester.ea.stress(delays_ms=...)` library argument) with `--delays` /
  `delays=[...]`. The old flag recorded a `stress_delay_ms` field on an
  otherwise ideal-execution run without ever applying the delay; it is removed
  rather than aliased so the envelope no longer claims stress it did not run.
- Added `mt5 alert watch` for bounded MT5 alert wake envelopes, policy matching,
  dedupe state, JSONL audit records, and dry-run decisions. The first slice reads
  alert definitions as a watch-list only; it does not detect fired alerts, create
  alerts, wake external agent runtimes, queue mobile notifications, or send live
  orders.

## [0.4.0]

Initial public release.

A Python library (`import mt5_cli`) and command-line interface (the `mt5` console
command, ~63 commands across 15 groups) for controlling a running MetaTrader 5
terminal from scripts and agents. This is a tooling project: it ships no trading
strategies, indicators, or signals.

Every CLI command accepts `--json` (in any position), prints a JSON envelope on
stdout, and always exits 0 — callers parse the envelope's `ok` boolean rather than
the process exit code. Real-account mutations are guarded by a triple-lock and are
enforced in the library layer, so a direct Python call cannot bypass them.

### Added

- Terminal connection and status: connect to and report the state of a running
  MetaTrader 5 terminal.
- Read commands for account, market, rates, and trade history.
- Order workflow: place, modify, cancel, and dry-run orders, with real-account
  execution protected by a triple-lock — `cfg["live"]=true`, the `MT5_LIVE=1`
  environment variable, and the `--live` flag must all be present, or the call
  returns `RISK_LIVE_GATE_BLOCKED`. Demo and contest accounts bypass the gate by
  design. These gates are enforced in the library layer (orders, positions, risk).
- Position management: close positions, move stop-loss, and set break-even.
- Chart control and screenshots (`mt5 screenshot take`).
- MQL5 tooling: scaffold, compile, and deploy Expert Advisors and indicators.
- A driver for MetaTrader 5's native Strategy Tester.
- `mt5 describe --json`: a machine-readable catalog of every command and the full
  error-code taxonomy.
- `mt5 --version`: prints the version.
- Position-independent `--json` flag, accepted anywhere on the command line.
- An optional MCP server (`mt5-mcp`, installed via the `[mcp]` extra) exposing 13
  typed read and dry-run tools. It exposes no live-money mutation over MCP, by
  design.
