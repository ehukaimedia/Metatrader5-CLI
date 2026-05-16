# MDI Tile-Preserving Chart Activation Plan

## Goal

Fix chart activation so `mt5 chart symbol`, `chart ensure`, and `screenshot tda` can focus an existing MT5 MDI child chart without collapsing a tiled/cascaded chart layout into a single maximized chart.

## Plan

1. Split MDI child activation from non-MDI/top-level fallback activation in `core/chart.py`.
2. Use `WM_MDIACTIVATE` on the terminal `MDIClient` whenever an MDI client is present.
3. Keep `ShowWindow`, `BringWindowToTop`, and foreground fallback behavior only for non-MDI paths.
4. Add a mocked Win32 regression test proving MDI activation avoids child `ShowWindow` / `BringWindowToTop` calls.
5. Update the spec and architecture playground to document layout-preserving activation.

## Verification

- Run `python -m pytest -q`.
