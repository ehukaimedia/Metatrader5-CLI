# Reviewer Context — MT5 Universal Agent-Native Refactor

**Read this before reviewing any branch / commit / artifact related to the `mt5-universal` refactor.** It scopes what feedback is in-bounds and what is out-of-bounds, so reviews stay focused on the chosen outcome instead of re-opening settled decisions.

This file is a sibling to:
- [2026-05-15-mt5-universal-agent-native-design.md](2026-05-15-mt5-universal-agent-native-design.md) — the spec
- [../playgrounds/mt5-universal-refactor-playground.html](../playgrounds/mt5-universal-refactor-playground.html) — the visual companion
- (forthcoming) the implementation plan

## 1. What we are doing — in one paragraph

Hard-fork the existing `metatrader5_cli/mt5/core/` (which is tangled with Ehukai/TDA/wavelet/Hybrid-WPVS semantics) into an agnostic Python library at `mt5_universal/`. Author MQL5 EAs and indicators in user-dir plugins. Drive MT5's native Strategy Tester from the CLI for backtests. Publish the library as both a `mt5` CLI and a `mt5-mcp` MCP server so AI agents have hands. Trading.com stays as the canonical broker profile but is no longer hardcoded. No code in the new tree contains hardcoded user paths.

## 2. Locked decisions — do not re-litigate

These were settled during brainstorming (see spec §4). A reviewer flagging them as "you should consider X instead" is rejecting the user's explicit choice.

| # | Decision | What "out of bounds" looks like |
|---|---|---|
| 1 | **Hard fork** legacy → `archive/`. No coexistence layer, no compat shims. | "Have you considered keeping a parallel namespace?" — No. |
| 2 | **MQL5 is the canonical author format** for strategies and indicators. | "Why not Python strategies?" — Because MT5 Strategy Tester only runs MQL5. Closed. |
| 3 | **MT5 Strategy Tester is THE backtest engine.** | "You should add a Python event-driven backtester for parity / faster iteration." — No. We deliberately dropped that idea after seeing the user's screenshots of the actual tester. |
| 4 | **Library-first architecture** with submodule-per-concern. CLI and MCP are thin wrappers. | "Why not centralize in an Engine god-object?" — Considered (option B in brainstorm), rejected. |
| 5 | **MCP + CLI dual surface** from one library. | "Drop the CLI, MCP-only" or "Drop MCP, CLI-only" — both rejected. The user uses both. |
| 6 | **Trading.com is the default `BrokerProfile`,** not removed and not hardcoded. | "Strip Trading.com defaults" — No. It's the user's actual broker and the MT5-native default. |
| 7 | **Portability rails are mandatory** — no hardcoded user paths in `mt5_universal/`, `mt5/`, `mt5_mcp/`. CI-enforced. | "This is overkill for a single-user repo" — No. Explicit user constraint. |
| 8 | **Existing `metatrader5_cli/mt5/skills/SKILL.md` is migrated, not replaced.** | "Phase 5 should rebuild SKILL.md from a CLI-Anything template" — No. The 11k-char manifest stays as the workflow narrative; only the command-group tables are auto-regenerated. |

## 3. What feedback IS welcome

Aim your review here. These are the kinds of issues that reviews should surface:

- **Factual inaccuracies** — wrong file paths, wrong LOC counts, wrong MQL5 inventory, claims about modules that don't match what's in git. (Codex 2026-05-15 P2 was a great example.)
- **Drift between artifacts** — playground says X, spec says Y, code does Z.
- **Security concerns** — XSS in the playground (we already use textContent and avoid innerHTML), credential leaks, hardcoded secrets, command injection.
- **Portability violations** — anything matching `C:\\Users\\`, `/home/`, `/Users/`, hardcoded drive letters in `mt5_universal/`, `mt5/`, `mt5_mcp/`.
- **Risk-gate bypass paths** — any code path where an order can be placed without `mt5_universal/risk/` being called. This is non-negotiable.
- **Bridge violations** — any module besides `mt5_universal/bridge/mt5_backend.py` importing `MetaTrader5`.
- **Test coverage gaps for changed code** — when a phase commit touches a module, point out untested branches in the changed code.
- **Edge cases in tester result parsing** — Strategy Tester HTML / journal CSV / optimization XML have many edge cases; reviewers catching unhandled ones is gold.
- **Missing portability fallbacks** — clipboard, MetaEditor.exe path resolution, registry lookups.
- **Per-phase acceptance-criteria gaps** — does the work actually meet the phase's acceptance criteria from spec §8?
- **Broken links / references** in any committed artifact.
- **Accessibility** — keyboard nav, color contrast, screen-reader basics for the playground.

## 4. What feedback is NOT welcome

Skip these — they waste review time and risk pulling the design off-course:

- **Re-litigating §2.** If your suggestion is one of those rows, it's already been considered and rejected.
- **"Have you considered X?"** when X is one of the rejected alternatives.
- **Generic best-practice nudges** that fight the chosen design (e.g., "use plugins instead of MQL5", "add a Python backtester", "abstract MT5 behind a protocol class").
- **Scope creep** — "you should also add live alerting / web dashboard / news filter" — out of scope; those live in the now-separate `adaptive-forex-mt5` repo.
- **Style nits** that don't have a written project convention behind them.
- **Demands for symmetry** — e.g., "indicator visual test should support optimization too" — MT5's tester doesn't, so neither do we.
- **Comparing to non-MT5 platforms** — "MetaTrader 4 does it differently" / "TradingView API does it differently" — we're MT5-only by design.

## 5. Cherry-pick relationship to CLI-Anything

We deliberately copied 8 patterns from [CLI-Anything](https://github.com/HKUDS/CLI-Anything), listed in spec §5 with attribution. **Reviewer notes:**

- **Don't flag patterns that match CLI-Anything as "derivative."** That's the point — it's a documented cherry-pick.
- **Don't demand we adopt MORE of CLI-Anything than the 8 listed patterns.** They have ~50 patterns; we picked the 8 that fit. "Why not also use CLI-Hub auto-publish?" — because we're not publishing to PyPI.
- **DO flag deviations from a pattern we said we adopted.** E.g., if the SKILL.md template lacks the "For AI Agents" section after we said we'd include it, that's a real deviation.
- **CLI-Anything's `mcp-backend.md` guide is INVERTED** in our adoption — they consume MCP backends, we publish the library AS an MCP server. Don't flag this as misuse.

## 6. Relationship to the existing canonical spec

[mt5-cli-spec.md](mt5-cli-spec.md) is the v0.5 spec for the *current* core. **Reviewer notes:**

- The new spec **does not invalidate** mt5-cli-spec.md while the legacy core is still imported (Phase 0). Both are live during the transition.
- After Phase 1 (archive), mt5-cli-spec.md becomes historical reference for the archived code.
- The risk-gate non-negotiables in mt5-cli-spec.md §1 are **preserved verbatim** in the new spec §9 — these survive the refactor unchanged.

## 7. Phase scope — review phase-by-phase

Spec §8 lays out 7 phases (0 through 6). Each phase has acceptance criteria. **Reviewer notes:**

- **Don't expect Phase 5 deliverables in a Phase 1 commit.** If you're reviewing a Phase 1 commit, evaluate it against Phase 1's acceptance criteria, not against the final state.
- **Phase 0 is already done** as of `f481fc0` (green baseline + branch). Don't re-flag it.
- **The spec + playground are deliverables that ship before Phase 1.** They're planning artifacts, not code. Review them for clarity / accuracy / drift, not for "missing implementation."
- A commit that says "Phase 3" should pass Phase 3 acceptance, not Phase 4's.

## 8. What "green" means

| Command | Expected result |
|---|---|
| `python -m pytest -q` (from repo root) | `240 passed, 1 skipped` (the skip is `test_e2e.py`, gated on `MT5_DEMO_INTEGRATION=1` — intentional) |
| `python -m pytest --collect-only -q` | `240 tests collected` |
| `git diff --check master...HEAD` | passes (no whitespace errors) |

Anything else green is a bonus. A reviewer reporting the suite as "broken" because the skipped test didn't run is wrong — the skip is the spec.

## 9. Deliverable types and what to look for

| Artifact | What good looks like |
|---|---|
| **Spec** (this dir) | Internally consistent. Locked decisions match brainstorm. MQL5 inventory distinguishes tracked git contents from explicitly named ignored/untracked disk artifacts. Phase acceptance criteria are testable. |
| **Playground HTML** (`docs/playgrounds/`) | Self-contained single file. No external deps. Safe DOM (textContent / explicit nodes; no innerHTML on dynamic content). All phases render. Click-to-comment works. Copy Prompt has a fallback. Responsive at narrow viewport. |
| **Plan** (forthcoming, `docs/plans/`) | Per-phase tasks, dependency order, test-first per phase, single-commit-per-task. |
| **Implementation commits** | Match the phase they claim to implement. Pass the phase's acceptance criteria. Don't break previously-passing tests. Don't introduce hardcoded user paths. |
| **Code reviews** (`docs/code-reviews/`) | P1/P2/P3 priority labels. Validation section showing what was actually run. Open-questions section flagging assumptions. |

## 10. Open questions the reviewer is welcome to weigh in on

These are deliberately not locked — review feedback IS welcome here:

1. Whether to remove `archive/` from `.gitignore` (recommended) or rename the archive target.
2. What to do with the 12 untracked Advanced Wavelet docs (commit, archive, or discard).
3. Whether to commit `Advanced_Wavelet_Entry_System/` as-is before the Phase 1 archive move (recommended), or discard.
4. Whether `archive/wf-fractal-cleanup-20260510-195855/` should stay or be removed.

## 11. How to write a review for this work

Modeled on the [Codex 2026-05-15 review](../code-reviews/codex-mt5-universal-playground-review-2026-05-15.md) which was useful:

- Title: `<reviewer>-<topic>-<YYYY-MM-DD>.md` in `docs/code-reviews/`.
- Header: review target (branch + SHA), compared against (base SHA).
- **Findings**, each with **P1/P2/P3** label, exact file:line citation, observed behavior, and *why it matters for the chosen design* (not just "this is unusual").
- **Open questions / assumptions** — call out anything you treated as outside the review.
- **Validation** — list the commands you ran and their outputs.
- Don't propose patches inline — propose them in a follow-up if requested.

---

**Bottom line:** the playground and spec encode the *chosen* outcome after a multi-question brainstorm. Reviews should help us land *that* outcome accurately and safely — not pull us toward a different one.
