# Codex1 Pre-Push Sweep - cea4e6b - 2026-05-08

Audit target: `cea4e6b` (`Gitignore build artifacts and audit-only research material`), 71 commits ahead of `origin/master`.

Scope requested by Claude1: machine-specific paths, secrets/keys/tokens, build/tmp residue, main README link, `.gitignore` safety, and full pytest.

## Findings

### P1 - Tracked docs still contain local machine paths

Files:

- `docs/code-reviews/codex-adaptive-forex-mt5-7405ca1-audit-2026-05-08.md:5`
- `docs/code-reviews/codex-adaptive-forex-mt5-f583d88-audit-2026-05-08.md:12`
- `docs/superpowers/plans/2026-05-08-trade-manager-and-llm-review.md:2804`

The pre-push path scan still finds local Windows-user paths, the local MetaQuotes terminal id, and the local workspace path in tracked files. Because the operator explicitly asked for `Metatrader5-CLI` / `adaptive-forex-mt5` portability across other machines, these should not be pushed as concrete local paths. (Real values redacted in this audit doc post-fix.)

Suggested change: replace these with portable placeholders, for example:

- `%APPDATA%\MetaQuotes\Terminal\<TERMINAL_ID>\MQL5\Experts\AdaptiveTrailEA.set`
- `cd <workspace>\Metatrader5-CLI\adaptive-forex-mt5`

Confidence: High.

### P1 - Operator MT5 login appears in tracked public docs and fixtures

Files:

- `README.md:91`
- `metatrader5_cli/mt5/tests/test_core.py:44`
- `metatrader5_cli/mt5/tests/test_core.py:50`
- `metatrader5_cli/mt5/tests/test_core.py:1127` and related fake MT5 title fixtures

A real-looking MT5 account login appears in the main README example and test fixtures. It is not an API key/password, but it looks like the operator's actual MT5 account login and should not be pushed as a real account identifier if the goal is portable/public-safe source. (Real value redacted in this audit doc post-fix.)

Suggested change: use a clearly fake placeholder in docs (`12345678` or `<YOUR_MT5_LOGIN>`) and update tests to a non-real fixture value.

Confidence: High.

## Non-Findings

- Secret scan found no concrete API keys, bearer tokens, ntfy topics, or passwords. Hits were placeholder examples (`"password": "secret"`, `ANTHROPIC_API_KEY` env-var name, token-count variables).
- No tracked build/runtime residue found. The only tracked match from the residue pattern was the legitimate source file `metatrader5_cli/mt5/core/screenshot.py`; `.ex5`, `.log`, screenshot bundles, and video transcript artifacts are ignored.
- `.gitignore` behavior looks safe for the new patterns: it ignores compiled MQL5 binaries, compile logs, audit screenshot bundles, and video transcript media while leaving source/docs like `adaptive-forex-mt5/config.example.json` and `adaptive-forex-mt5/docs/playgrounds/architecture.html` trackable.
- Main README's `adaptive-forex-mt5/` link and architecture playground link read correctly.
- Full suite passed: `358 passed, 1 skipped`.

## Verdict

NO-GO for push until the local paths and real-looking account id are scrubbed from tracked files. Everything else in the requested pre-push sweep is green.

