# Codex Review Prompt — Phase 3a CLI + chart-control bundle

**Reviewer:** Spock (assignee). **Orchestrator:** Piccard.

Review the mt5-universal branch at HEAD `69cfc1a` against the baseline
of the last Codex pass (`9caf433`, post-fix P2 closure). This range
covers two commits:

- `00c22b7` Chart-control completion bundle (NOT previously reviewed)
- `69cfc1a` Phase 3a `mt5` CLI (1550-line addition)

Post-fix closure at `5ae1722` cleared the prior cycle; both commits
above are net-new and need first-pass external eyes.

## Required reading FIRST

1. `docs/code-reviews/codex-mt5-universal-post-fix-closure-review-2026-05-16.md`
   (the previous review; verify it stays closed)
2. `docs/specs/2026-05-15-mt5-universal-review-context.md` — locked
   decisions, in/out of bounds rules
3. `docs/specs/2026-05-15-mt5-universal-agent-native-design.md` —
   Phase 3 section. Phase 3a is shipped (CLI), Phase 3b (MQL5 plugin
   host) is TODO. The CLI acceptance criteria are inline.

## Commits in range (9caf433..69cfc1a)

### 00c22b7 — Chart-control completion bundle

- `attach_ea(expert_name)` — Insert > Experts > <name> menu poke
- `cycle_chart(direction)` — MDI tab navigation (wraps around)
- `close_chart(chart_id)` — WM_CLOSE on chart child + verify-gone
- `ensure_chart()` BEHAVIOR CHANGE: now calls `new_chart()` when no
  chart exists for the symbol (was: typed symbol into active chart,
  destroying it). Lazy import to avoid the chart.py <-> new_chart.py
  cycle.
- 24 new tests; 302 total passed at this commit.

### 69cfc1a — Phase 3a CLI

- `mt5/__init__.py`, `mt5/__main__.py`, `mt5/emit.py`, `mt5/cli.py`
  (~600 LOC of click wrapping)
- `setup.py`: console_scripts entry point `mt5 = mt5.cli:main`
- `tests/test_cli.py` (35 CliRunner smoke tests)
- spec section Phase 3 split into 3a (shipped) and 3b (TODO)
- 337 total passed
- Manually verified all 11 groups against live Trading.com demo
  (see commit message for end-to-end outputs)

## Verification priorities (highest first)

### 1. Triple-lock plumbing for EVERY mutating CLI command

Codex post-fix P1 (`62c7081`) extended `risk._live_gate_check` to
require `cfg` + enforce the triple lock for orders.cancel / modify /
cancel_all_pending. The CLI's responsibility is to thread BOTH `cfg`
AND `is_live_intent` into those calls.

For each of:

  - mt5 order market | limit | stop | dryrun
  - mt5 order cancel | cancel-all | modify
  - mt5 position close | close-all | move-sl | breakeven

Verify:

- Does the CLI command pass `cfg=ctx.obj["cfg"]` to the library?
  (Order commands MUST. positions.close*/move_sl/breakeven still use
  the single-flag gate per the prior-review out-of-scope decision —
  confirm none accidentally tried to pass `cfg`.)
- Does the CLI command pass `is_live_intent=is_live` where the value
  comes from a `--live` click flag?
- Is there ANY mutating SDK command that ships without `--live`?

### 2. Auto-connect coverage

`_autoconnect(cfg)` is called before every SDK-dependent command.
Chart and screenshot commands are pure Win32 / mss and skip it. config
and connect commands also skip. Verify:

- No command that actually uses the SDK skipped `_autoconnect`
  (would AttributeError on disconnected MT5)
- No pure-Win32 command needlessly called `_autoconnect` (would try to
  connect on hosts without MT5 installed)

### 3. Envelope contract

Per spec section 3, the CLI must:

- ALWAYS exit 0 (success status lives in envelope's `ok` field)
- Emit JSON envelope to stdout with `--json`, human-readable summary
  to stdout (ok) / stderr (fail) without `--json`

Did any command bypass `emit(envelope, ctx.obj["json"])`? Did any
command propagate a Python exception out of click instead of returning
a fail envelope? Particular concern: `_autoconnect` returns a fail
envelope on connection error — is that envelope actually `emit()`ed
by EVERY caller, or are some treating it as "skip the command
silently"?

### 4. `config show` mask_secrets behavior

Default is `--mask-secrets` (login + password redacted).
`--no-mask-secrets` disables both. Verify:

- With default, JSON envelope's `data.password` is `"***"` not the
  real value
- With default, `data.login` is `"***"` not the real account number
- With `--no-mask-secrets`, both real values appear (this is the
  ONLY way the real password should ever reach stdout)

### 5. Argument threading correctness

For a sampling of commands across groups, trace:

- Click option names → Python parameter names (any `--foo-bar` mismatches
  with `foo_bar` kwarg?)
- Required vs optional (any required library param accepting None
  silently?)
- Type coercion (`--volume` = float, `--ticket` = int, `--bars` = int)
- Default values match the library function defaults

Specific commands worth tracing end-to-end:

- `mt5 order limit ... --price P` — does price reach `orders.place_limit()`
  AND get passed to `check_order`'s `entry_price`?
- `mt5 history orders --from D --to D` — date parsing edge cases:
  ISO-8601 with timezone, YYYY-MM-DD, garbage, empty string
- `mt5 chart attach-ea NAME --no-confirm` — does `no-confirm` correctly
  invert to `auto_confirm=False`?
- `mt5 screenshot annotate IN OUT TEXT --xy 50,80` — xy parsing edge
  cases: `"50,80"`, `"50, 80"`, `"50"`, `"50,80,90"`, `"x,y"`

### 6. emit.py payload handling

The human formatter renders dict / list / scalar. What happens with:

- A list of dicts (history orders) — does the `---` separator appear
  correctly?
- Nested dicts (a value that is itself a dict)
- bytes payload (probably none in practice but check)
- datetime objects (the library returns ISO strings, but if any slip
  through?)
- None payload from `ok(None)` — the code prints `OK`, confirm

### 7. Setup.py entry point + the stale-binary story

The legacy `mt5.exe` at `~/AppData/Roaming/Python/Python313/Scripts/mt5`
pointed at the archived `metatrader5_cli.mt5.mt5_cli:main` and was
broken. `pip install -e .` should have REPLACED it with the new
`mt5.cli:main` wrapper. Verify:

- `which mt5` resolves to the new binary
- The setup.py `entry_points` dict is well-formed
- No console_scripts entry points were accidentally registered for
  `mt5-mcp` / other future commands

### 8. Test boundary correctness

`tests/test_cli.py` uses stubs at the `mt5.cli` module level. That
tests plumbing (arg parsing, envelope routing, --json/--live threading)
but NOT library behavior. Verify:

- Stubs are at the right level (`mt5.cli._orders_mod.cancel`, not
  `mt5_cli.orders.cancel` — the former is what the CLI actually calls
  because of the module-level imports)
- The cache-safe purge pattern handles `mt5.cli` + `mt5.emit`
- No test actually invokes the MT5 SDK (would slow CI massively)
- Tests cover the `--live` flag both directions per command

### 9. Chart-control bundle at 00c22b7 (first external review)

Same priorities as the previous chart-related reviews:

- Bridge isolation: `attach_ea.py` never imports MetaTrader5
- Menu walk: `find_leaf_command_id_recursive` used so EAs nested under
  Examples/Advisors are found
- `ensure_chart` upgrade: when `chart_id` is None AND no existing chart
  matches the symbol, calls `new_chart`. When `chart_id` IS supplied,
  skips the lookup and uses the named MDI child. Lazy import to avoid
  the cycle.
- `cycle_chart` wrap-around: from last index, "next" wraps to 0; from
  index 0, "prev" wraps to last. Edge case: `active_index` is None (no
  active chart detected) — falls back to index 0.
- `close_chart` verify-gone: posts WM_CLOSE, settles, re-enumerates,
  checks `chart_id not in after_hwnds`. Returns CHART_CLOSE_VERIFY_FAILED
  if still present (MT5 save-profile dialog).

## Standing constraints (do NOT propose patches that fight these)

1. Single-broker scope; no `BrokerProfile` ABC; no `generic_mt5`
2. Zero indicator math in the tool
3. Bridge singleton (only `mt5_cli/bridge/mt5_backend.py`)
4. Package is `mt5_cli/` + `mt5/` (the CLI wrapper); config at
   `~/.config/metatrader5-cli.json`; user data at
   `~/.local/share/metatrader5-cli/` (XDG_DATA_HOME)
5. No hardcoded user paths in `mt5_cli/`, `mt5/`, `mt5_mcp/`
6. Tool ships hands, not strategies
7. CLI exit code is ALWAYS 0; envelope's `ok` carries the status

## What feedback is NOT welcome

- Re-litigating any closed finding from prior reviews
- "Add a TUI / interactive prompt mode" (out of scope; FastMCP is Phase 5)
- "Add --version" (click can do it; not requested, not blocking)
- "Use rich for human output" (emit.py is deliberately plain print; adds a dep)
- "Phase 3b should be done first" (3a/3b split is intentional; user
  prioritized having a working CLI to verify)
- Style nits without a project convention behind them

## Validation to run

```
python -m pytest -q
# -> expect 337 passed

git diff --check 9caf433..HEAD
# -> expect exit 0

git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5
# -> expect only mt5_cli/bridge/mt5_backend.py

mt5 --help
# -> expect "Usage: mt5 [OPTIONS] COMMAND [ARGS]..." and 11 groups

mt5 --json config show
# -> expect ok envelope with filling=FOK, rollover_utc_hour=22,
#    password masked as "***", login masked as "***"

mt5 --json config retcode 10030
# -> expect ok envelope with help text containing "FOK"

mt5 --json status
# -> if MT5 is running: ok envelope with account fields
# -> if MT5 not running: fail envelope MT5_CONNECTION_ERROR
```

## Reporting format

Write to: `docs/code-reviews/codex-mt5-universal-cli-review-2026-05-16.md`

Modeled on prior reviews:

- Header: review target (branch + SHA `69cfc1a`), compared against
  (base SHA `9caf433`)
- Findings as P1 / P2 / P3 with exact `file:line` citations, observed
  behavior, why-it-matters tied to the chosen design
- Verified Closures section listing what stayed closed from prior reviews
- Validation section listing the exact commands you ran and outputs
- Open questions / assumptions section

If a regression in any previously-closed finding is found, flag it as
a fresh P1/P2 with new evidence — don't say "see prior review."

Don't propose patches inline.

When the review file is committed, reply on the bus with a one-line
summary (P-count) and the path. The orchestrator (Piccard) will
triage and create a follow-up implementation task for Kirk if needed.
