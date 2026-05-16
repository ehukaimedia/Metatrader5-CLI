# MT5 Universal Plan Audit - 2026-05-15

Branch: `mt5-universal`
Reviewed HEAD: `ca5eebc`
Scope: `docs/superpowers/plans/2026-05-15-mt5-universal-agent-native.md`

## Findings

1. P1 - Task 2.5 tells implementers to commit a known-red test state.

   The plan adds `test_get_profile_returns_trading_com_by_default` and `test_profile_retcode_help_returns_string` in `docs/superpowers/plans/2026-05-15-mt5-universal-agent-native.md:763` and `:775`, both of which require the `trading_com` profile to exist and be registered. The same task then says those imports should be commented out, the `trading_com` test will fail, and still proceeds to commit at `:837` and `:841`. That conflicts with the reviewer-context rule that implementation commits should pass acceptance criteria and not break previously-passing tests, and it gives worker agents permission to land a red intermediate commit. Fix by either moving the `trading_com` expectations into Task 2.6, or by implementing/registering the concrete `trading_com` profile before the Task 2.5 commit.

2. P2 - The plan is in the wrong documentation directory.

   The committed plan lives at `docs/superpowers/plans/2026-05-15-mt5-universal-agent-native.md:1`. The repo instructions require plans under `docs/plans/`, and the reviewer context also names `docs/plans/` as the plan location in `docs/specs/2026-05-15-mt5-universal-review-context.md:100`. This means downstream agents following the repo architecture contract may miss the implementation plan or create a duplicate canonical plan elsewhere. Move the file to `docs/plans/2026-05-15-mt5-universal-agent-native.md` and update relative links if needed.

3. P3 - The new plan fails the branch whitespace gate.

   `git diff --check master...HEAD` reports `docs/superpowers/plans/2026-05-15-mt5-universal-agent-native.md:5173: new blank line at EOF.` The plan's own final acceptance table requires `git diff --check master...HEAD` to pass, so the branch currently violates the validation rule it asks implementers to use. Trim the trailing blank line so the file ends with exactly one newline.

## Open Questions

- Was `docs/superpowers/plans/` chosen intentionally by the writing-plans skill? If yes, the repo-level AGENTS documentation and reviewer context need to be updated together. As written, `docs/plans/` is the canonical location.

## Validation

- `git fetch origin --prune` -> branch synced with `origin/mt5-universal` at `ca5eebc`.
- `python -m pytest -q` -> `240 passed, 1 skipped`.
- `git diff --check master...HEAD` -> failed on the plan's trailing blank line.
- Placeholder scan found no actionable `TODO`, `TBD`, `FIXME`, `XXX`, `CHANGEME`, or `REPLACE_ME` markers; `PLACEHOLDER` only appears in intentional template-token instructions.
- Targeted drift search found no stale `MT5_STRATEGIES_DIR`, `mt5 mql5 compile`, or `mt5 mql5 deploy` usage in the plan.

## Summary

The plan is detailed and mostly aligned with the locked refactor design, but it is not ready as the canonical implementation plan until the location, whitespace gate, and Task 2.5 red-commit sequence are fixed.
