# Codex Re-Review: mt5-universal reviewer context and spec

Review target: `mt5-universal` at `4d49da37e836b06dfa9c09c07325becf53d781b3`

Compared against: `master` at `4d26992f21e9e9d132567dc8f81ea1e4a1fe7f96`

## Findings

1. P2 - The MQL5 zip inventory still marks ignored zip artifacts as tracked.

   `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:132` marks `Hybrid_WPVS_MT5_Bundle.zip` as tracked, and `:136` marks `WF_FractalPredictor_MQ5_v1_10.zip` as tracked. In this checkout, `git ls-files metatrader5_cli/mt5/mql5 | rg "\.zip$"` returns no tracked MQL5 zips, while `.gitignore:17` ignores `*.zip` and `git check-ignore -v` confirms the MQL5 zip snapshots are ignored. Phase 1 can still omit snapshot artifacts while the spec tells implementation agents those files are already captured.

2. P2 - The hard-fork rule and the Phase 1 legacy entry-point option conflict.

   `docs/specs/2026-05-15-mt5-universal-review-context.md:20` locks the hard fork as "No coexistence layer, no compat shims." But `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:221` allows quarantining the old CLI behind a deprecation entry point named `mt5-legacy` until Phase 5. Reviewers and implementation agents need one rule here: either `mt5-legacy` is an explicitly allowed temporary migration harness, or the Phase 1 option should be removed.

3. P2 - Phase 3 command names drift between spec and playground.

   The spec acceptance path uses `mt5 ea compile` and `mt5 ea deploy` at `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:234-235`. The playground examples use `mt5 mql5 compile ea` and `mt5 mql5 deploy ea` at `docs/playgrounds/mt5-universal-refactor-playground.html:319-320`, `:566`, and `:568`. Agents using the copied playground prompt could implement the wrong CLI surface.

4. P2 - EA plugin directory naming is not single-sourced.

   The target layout and Phase 3 use `ea/` at `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:110` and `:233`, but the module boundary rule switches to `strategies/` at `:145`, and Phase 6 names `MT5_STRATEGIES_DIR` at `:251`. That leaves the repo-root discovery directory and environment variable ambiguous for EAs.

5. P3 - Narrow viewport layout is improved but still clipped.

   `docs/playgrounds/mt5-universal-refactor-playground.html:16-20` adds a responsive breakpoint, but `#legend{display:flex}` is declared later at `:62`, overriding the intended `#legend{display:none}` rule. In a `390x844` Playwright smoke, the main area no longer collapsed to 80px, but the canvas was about 172px tall, the absolute phase banner was about 197px tall, and the legend still displayed. The preview is still cramped and partially clipped on narrow screens.

6. P3 - SVG comment nodes are mouse-only.

   Nodes are rendered as SVG `<g data-id>` elements at `docs/playgrounds/mt5-universal-refactor-playground.html:674`, and only a click handler is attached at `:704`. They have no `tabindex`, role, accessible name, or Enter/Space keyboard handler. Since the reviewer context explicitly invites accessibility feedback, the playground should let keyboard users open the comment modal too.

7. P3 - The repository-level whitespace validation currently fails.

   `docs/specs/2026-05-15-mt5-universal-review-context.md:90` says `git diff --check master...HEAD` should pass, but it currently reports `docs/code-reviews/codex-mt5-universal-playground-review-2026-05-15.md:42: new blank line at EOF`. This is small, but it contradicts the branch's own green contract.

## Prior Findings Status

- Fixed: the refactor is no longer only in the playground. The branch now tracks the spec, reviewer context, playground, and prior review.
- Fixed: the playground now points reviewers at the context doc, and the spec points reviewers there too.
- Fixed: MQL5 inventory now distinguishes `Experts/`, `Hybrid_WPVS_MT5_Bundle/`, and untracked `Advanced_Wavelet_Entry_System/`; only the zip tracked/ignored status remains inaccurate.
- Fixed: Phase 5 now says the existing `metatrader5_cli/mt5/skills/SKILL.md` is migrated, not absent.
- Fixed: `Copy Prompt` has a visible fallback when clipboard access is missing or denied.

## Validation

- `python -m pytest -q` -> `240 passed, 1 skipped`
- `python -m pytest --collect-only -q` -> `240 tests collected`
- `git diff --check master...HEAD` -> failed on `docs/code-reviews/codex-mt5-universal-playground-review-2026-05-15.md:42: new blank line at EOF`
- Playwright `file://` smoke -> no console errors; all seven phases rendered non-empty node/edge sets; context link resolved; missing/denied clipboard paths selected the prompt and showed fallback feedback.
- Narrow viewport Playwright smoke at `390x844` -> layout stacks, but banner/legend still crowd the canvas.

