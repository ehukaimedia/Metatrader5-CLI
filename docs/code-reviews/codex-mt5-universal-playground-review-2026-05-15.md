# Codex Review: mt5-universal playground consolidation

Review target: `mt5-universal` at `2082285` (`Add MT5 universal refactor playground`)

Compared against: `master` at `4d26992`

## Findings

1. P1 - The universal refactor contract exists only inside the playground HTML.

   `docs/playgrounds/mt5-universal-refactor-playground.html:552`, `:573`, and `:580` define the future `mt5_universal/` package, MCP server, generated skill surface, portability rails, CI path guard, and harness document. The branch does not add a matching spec under `docs/specs/` or a plan under `docs/plans/`; `git ls-files docs/specs docs/plans | rg "universal|refactor|mt5-universal|mt5_universal|harness|mcp|plugin"` returns no tracked spec/plan artifact for this refactor. Given this repo's mandatory spec-driven architecture rules, the HTML becomes the only source of truth for a large refactor, which is fragile for future agents and easy to drift from.

2. P2 - The current-state MQL5 inventory points agents at the wrong archive scope.

   `docs/playgrounds/mt5-universal-refactor-playground.html:239` and `:538` say `mql5/Experts/*.mq5` includes `Advanced_Wavelet_Entry` and `Hybrid_WPVS`, and `:545` tells the refactor to move `mql5/Experts/*` for all four systems. In the tracked branch, `metatrader5_cli/mt5/mql5/Experts/` contains only `AdaptiveTrailEA.mq5` and `EhukaiTDAEA.mq5`; `Hybrid_WPVS` lives under `metatrader5_cli/mt5/mql5/Hybrid_WPVS_MT5_Bundle/`, and `Advanced_Wavelet_Entry_System/` is currently untracked. An agent following the playground literally could archive only `Experts/*` and leave major MQL5 assets behind while thinking the archive step is complete.

3. P2 - Copy Prompt has no denied-permission or missing-clipboard fallback.

   `docs/playgrounds/mt5-universal-refactor-playground.html:907-912` assumes `navigator.clipboard.writeText()` exists and succeeds. It worked in the Codex Playwright browser, but an independent local/headless check reproduced `Write permission denied`, and a DOM harness with no `navigator.clipboard` throws before showing any feedback. Copy is a core playground requirement, so this should catch failures and provide visible fallback feedback, such as selecting the prompt text.

4. P3 - Phase 5 treats the existing MT5 skill manifest as absent.

   `docs/playgrounds/mt5-universal-refactor-playground.html:540` says there is no `SKILL.md` manifest today, while HEAD already tracks `metatrader5_cli/mt5/skills/SKILL.md`. Phase 5 at `:573` should say the refactor migrates or regenerates that existing agent safety/usage contract into the new `mt5_universal` surface rather than creating one from nothing.

5. P3 - Narrow viewports collapse the playground's usable work area.

   The page uses `body{overflow:hidden}`, a fixed `310px` sidebar, and a horizontal flex workspace. An independent Playwright check at `390x844` measured the main/prompt area at roughly `80px` wide with the legend overflowing the viewport. Desktop rendering is fine, but side-by-side or mobile review windows make the canvas and prompt hard to use. A responsive breakpoint that stacks or collapses the sidebar would keep the playground usable.

## Open Questions / Assumptions

- I treated untracked Advanced Wavelet docs/MQL5 files in the working tree as outside the reviewed branch. If those are intended to be part of the refactor baseline, they need to be committed or the playground should avoid depending on them.
- The `pytest.ini` change still looks correct: `adaptive-forex-mt5/tests` is not tracked or present on this branch, so the branch now discovers only the existing MT5 CLI tests.
- I did not run live MT5 or Strategy Tester smoke tests. This branch is documentation/playground plus pytest discovery cleanup.

## Validation

- `python -m pytest -q` -> `240 passed, 1 skipped`
- `python -m pytest --collect-only -q` -> `240 tests collected`
- `git diff --check master...HEAD` -> passed
- Playwright `file://` smoke of `docs/playgrounds/mt5-universal-refactor-playground.html` -> no console errors; all seven phase buttons rendered non-empty node/edge sets; modal comment save updated the prompt; desktop screenshot looked usable.
- Static security scan found no `innerHTML`, `insertAdjacentHTML`, `document.write`, or `eval`; comment and prompt rendering use `textContent` / explicit DOM nodes.

