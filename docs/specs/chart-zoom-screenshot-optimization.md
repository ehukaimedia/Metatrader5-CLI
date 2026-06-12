# Chart Zoom Screenshot Optimization Spec

Status: Implemented
Date: 2026-06-12
Owner: metatrader5-cli maintainers
Related playground: [Chart Zoom Screenshot Optimization](../playgrounds/specs/chart-zoom-screenshot-optimization.html)
Related plan: [Chart Zoom Screenshot Optimization Plan](../plans/chart-zoom-screenshot-optimization-plan.md)

## Purpose

Agents need to tune chart density before taking MT5 screenshots. The screenshot
module currently captures the visible terminal pixels with `mss`; it does not
drive MT5's built-in "Save As Picture" dialog. The right slice is a chart zoom
primitive that changes the on-screen chart scale before `mt5 screenshot take`
captures it.

The command must remain honest about what it can verify. The Win32 path can send
zoom keystrokes to a target chart and report the target/action, but it does not
read MT5's `CHART_SCALE` value back through the Python SDK.

## Source Anchors

- CLI layering rule: `CONTRIBUTING.md:50-57` says `mt5/` is parsing/routing
  only and business logic belongs in `mt5_cli/`.
- Existing chart command surface: `mt5/cli.py:989-1140` exposes `chart` as the
  Win32 GUI-control group.
- Existing chart library surface: `mt5_cli/chart/chart.py:619-633` has the
  keyboard helpers, and `mt5_cli/chart/chart.py:639-783` resolves the zoom
  target chart, sends a UI action, and returns an envelope.
- Existing chart export surface: `mt5_cli/chart/__init__.py:24-29` lists the
  agent-facing chart primitives that must stay current.
- Existing screenshot implementation: `mt5_cli/screenshot/screenshot.py:132-205`
  captures a window or monitor with `mss`; it does not use MT5's "Save As
  Picture" dialog.

## Goals

- Add `mt5 chart zoom in --steps N` and `mt5 chart zoom out --steps N`.
- Add `mt5 chart zoom set LEVEL` for deterministic screenshot preparation by
  sending enough zoom-out keystrokes to reach the bottom of MT5's six-step scale
  and then zooming in `LEVEL` times.
- Support `--chart-id` and `--substring` like the other chart controls.
- Keep the screenshot module unchanged: callers compose `chart zoom ...` then
  `screenshot take`.
- Return structured envelopes and register any new error code.

## Non-Goals

- No automated use of MT5's "Save As Picture" dialog in this slice.
- No chart-only file export; `screenshot take` remains a pixel capture of the
  matched window or monitor.
- No claim that the final MT5 zoom level was read back or verified.
- No MCP surface change.

## Architecture

1. `mt5_cli/chart/chart.py` owns zoom behavior. It locates the MT5 window,
   resolves the active or requested MDI child chart, activates it, and sends
   `VK_ADD` for zoom-in or `VK_SUBTRACT` for zoom-out.
2. `zoom(direction, steps, ...)` validates `direction in {"in", "out"}` and a
   bounded positive step count, then emits one keypress per step.
3. `set_zoom(level, ...)` validates `level in 0..5`, sends six zoom-out steps to
   floor the MT5 chart scale, then sends `level` zoom-in steps. The envelope
   reports `requested_level`, `reset_steps`, and `verified: false`.
4. `mt5/cli.py` exposes a nested `chart zoom` group with `in`, `out`, and `set`
   commands. It only parses options and emits the library envelope.
5. `mt5_cli/errors.py` registers `CHART_INVALID_ZOOM` for bad direction, step,
   or level values.

## Command Contract

```bash
mt5 --json chart zoom in --steps 2
mt5 --json chart zoom out --steps 1 --chart-id 2500
mt5 --json chart zoom set 3 --substring MT5
mt5 --json screenshot take --window MT5
```

Successful relative zoom:

```json
{
  "ok": true,
  "data": {
    "direction": "in",
    "steps": 2,
    "hwnd": 2500,
    "parent_hwnd": 1000,
    "title": "[EURUSD,M15]",
    "method": "keyboard",
    "verified": false
  }
}
```

Successful deterministic request:

```json
{
  "ok": true,
  "data": {
    "requested_level": 3,
    "reset_direction": "out",
    "reset_steps": 6,
    "in_steps": 3,
    "method": "keyboard-reset-then-in",
    "verified": false
  }
}
```

## Error Codes

- `CHART_INVALID_ZOOM` - direction must be `in` or `out`, steps must be a
  positive bounded integer, and set levels must be `0..5`.
- Existing chart errors remain unchanged: `CHART_WINDOW_NOT_FOUND`,
  `CHART_ID_NOT_FOUND`, and `CHART_NO_CHARTS_OPEN`.

## Acceptance Tests

1. `zoom("sideways")` returns `CHART_INVALID_ZOOM`.
2. `zoom("in", steps=0)` and an excessive step count return
   `CHART_INVALID_ZOOM`.
3. `zoom("in")` returns `CHART_WINDOW_NOT_FOUND` when no MT5 window matches.
4. `zoom("in", steps=2)` activates the target chart and posts two `VK_ADD`
   keypresses to that chart hwnd.
5. `zoom("out", steps=1, chart_id=...)` targets the requested chart id.
6. `set_zoom(3)` posts six `VK_SUBTRACT` keypresses followed by three `VK_ADD`
   keypresses and reports `requested_level: 3`, `verified: false`.
7. `set_zoom(-1)` and `set_zoom(6)` return `CHART_INVALID_ZOOM`.
8. CLI commands thread `--steps`, `--chart-id`, and `--substring` to the chart
   library.
9. The error registry remains exact (`tests/test_errors.py`).

## Verification

Before merge: `pytest tests/test_chart.py tests/test_cli.py tests/test_errors.py`
and `ruff check .`.

Manual terminal check (optional, requires MT5): run `mt5 --json chart zoom set 3`
then `mt5 --json screenshot take`, and confirm the chart density changes before
the capture.
