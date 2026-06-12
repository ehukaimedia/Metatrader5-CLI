# Chart Zoom Screenshot Optimization Plan

Status: Implemented
Date: 2026-06-12
Spec: [Chart Zoom Screenshot Optimization Spec](../specs/chart-zoom-screenshot-optimization.md)
Playground: [Chart Zoom Screenshot Optimization](../playgrounds/specs/chart-zoom-screenshot-optimization.html)

## Scope

Add chart zoom as a composable MT5 UI-control primitive. The CLI prepares the
visible chart; the existing screenshot command captures the pixels afterwards.
MT5's Save As Picture dialog is documented as out of scope for this slice.

## Phases

### Phase 1 - Contract tests

- Add chart-unit tests for invalid zoom values, window-not-found behavior, key
  posting, requested chart id routing, and deterministic set-level key sequence.
- Add CLI plumbing tests for `chart zoom in`, `chart zoom out`, and
  `chart zoom set`.

### Phase 2 - Library

- Implement `zoom()` and `set_zoom()` in `mt5_cli/chart/chart.py`.
- Reuse the existing chart-window and child-chart resolution helpers.
- Send `VK_ADD` / `VK_SUBTRACT` keyboard messages to the target MDI child chart.
- Register `CHART_INVALID_ZOOM` in `mt5_cli/errors.py`.

### Phase 3 - CLI and exports

- Export the new functions from `mt5_cli/chart/__init__.py`.
- Add `mt5 chart zoom in|out|set` commands under the existing chart group.
- Keep `mt5/cli.py` thin: parse arguments, call library, emit the envelope.

### Phase 4 - Docs and cleanup

- Update README examples and command table.
- Update AGENTS.md with the screenshot-prep workflow.
- Update CHANGELOG Unreleased.
- Remove or correct stale wording discovered while touching the chart docs.

## Verification Gate

```bash
pytest tests/test_chart.py tests/test_cli.py tests/test_errors.py
ruff check .
```

Optional live check:

```bash
mt5 --json chart zoom set 3
mt5 --json screenshot take --window MT5
```
