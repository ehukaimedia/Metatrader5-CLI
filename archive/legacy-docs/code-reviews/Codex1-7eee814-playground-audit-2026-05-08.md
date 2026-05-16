# Codex1 Playground Audit - 7eee814 - 2026-05-08

Audit target: `adaptive-forex-mt5/docs/playgrounds/architecture.html` at `7eee814` (`Playground: fix code-reviewer findings (edges + phase membership + README)`).

Scope: architecture accuracy against `adaptive-forex-mt5/`, phase membership/presets, self-containment, and comment-to-prompt XSS safety. Findings below are limited to high-confidence issues.

## Findings

### P2 - Phase presets hide runtime nodes/edges that belong to those phases

File: `adaptive-forex-mt5/docs/playgrounds/architecture.html:318`

`Phase 1 (foundation)` and `Phase 3 (adoption)` omit layer/connection types that are part of those phases:

- Phase 1 excludes `skill`, so the `ehukaiconnect -> ClaudeReviewer` dispatcher-wake edge at line 269 disappears even though Phase 1 includes the single-reviewer pipeline and the reviewer node itself is tagged `p1`.
- Phase presets exclude `ui`, so `dashboard.py` disappears from Phase 1/2/3 views even though it is a long-running runtime process and Phase 3 specifically surfaces adopted/autopilot tags through the dashboard.

This makes phase-focused views look partially disconnected or incomplete while the full view is accurate.

Suggested change:

- Add `skill` to the Phase 1 preset connection list.
- Include `ui` in all phase presets, or create a clearly named "runtime core only" preset if hiding the dashboard is intentional.

Confidence: High.

### P2 - Trade-manager journal data flow is underrepresented

File: `adaptive-forex-mt5/docs/playgrounds/architecture.html:285`

The trade-manager section shows `trade_manager.py -> state_db.py`, `bootstrap -> journal.py` for placement matching, and `manage -> mt5`, but it omits the journal writes that are central to Phase 1 and Phase 3 evidence collection:

- `trade_manager.py` logs unmanaged POC positions through `journal.log_unmanaged_poc_position()` when bootstrap fails (`adaptive-forex-mt5/trade_manager.py:186`).
- `attempt_modify()` records confirmed/slipped management decisions through `journal.log_manage_action()` and `journal.log_manage_skip()` (`adaptive-forex-mt5/trade_manager.py:354`, `adaptive-forex-mt5/trade_manager.py:379`).
- Adoption synthesis writes `placement`/`adoption` records via `journal.append()` (`adaptive-forex-mt5/trade_manager.py:532`, `adaptive-forex-mt5/trade_manager.py:553`).

Because the playground has a "Data flow only" preset, missing these edges can mislead reviewers into thinking trade management state lives only in SQLite, while the immutable JSONL is also part of the management/adoption evidence stream.

Suggested change:

- Add `manage -> journal` labeled `manage_action / manage_skip`.
- Add `trade-mgr -> journal` or `adopt -> journal` labeled `adoption / synthesized placement`.
- Clarify `bootstrap -> journal` as `read placement match / unmanaged warning` if that single edge is intended to cover both read and write paths.

Confidence: High.

## Non-Findings

- Self-containment looks good: the playground is a single HTML file with inline CSS/JS and no external script/link/fetch imports found.
- XSS posture looks good for the comment flow: user-entered comments are stored in memory and rendered with `textContent` into the comment list and prompt, not inserted as HTML.
- The patched edge directions for `trade_manager -> adopt` and removal of the fabricated `journal -> state_db` edge match the current code.

