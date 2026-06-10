# Tester Stress & Delays Plan

Status: Implemented (PR #7)
Date: 2026-06-10
Spec: [Tester Stress & Delays Spec](../specs/tester-stress-delays.md)
Playground: [Tester Stress & Delays](../playgrounds/specs/tester-stress-delays.html)

## Scope

Implement the spec's five parts: a validated `ExecutionMode` key in the INI
builder, a pure `mt5_cli/tester/stress.py` module (ladder + scoring), a
`delay_ms` passthrough on `ea.single()`, a delay-ladder `ea.stress()` that
returns `stress.v1`, and the `--delays` CLI flag. TDD throughout — each phase
starts with the failing tests listed in the spec's Acceptance Tests section.

## Phases

Each phase is independently committable and leaves the suite green.

### Phase 1 — INI layer

- Tests first (`tests/test_ini_builder.py` or the existing INI test module):
  acceptance tests 1–3 (default `ExecutionMode=0`, exact emission for `-1`
  and `250`, `ValueError` for `-2` and `600001`).
- Implement `execution_mode: int = 0` on `build_ea_ini()` in
  `mt5_cli/tester/ini_builder.py`, validated, always emitted.
- Do not touch `build_indicator_ini()`.

### Phase 2 — Pure stress module

- Tests first (`tests/test_tester_stress.py`, new): acceptance tests 4–8
  (token parsing, normalization, worst-case scoring, clamping, rounding,
  ungraded cases, `incomplete`).
- Implement `mt5_cli/tester/stress.py`: `parse_delays(str) -> list[int]`,
  `normalize_ladder(list[int]) -> list[int]`, and
  `score(baseline_stats, scenario_rows) -> dict` per the spec's scoring
  contract. Stdlib-only, no filesystem, no launcher imports.

### Phase 3 — Orchestration

- Tests first (`tests/test_tester_ea.py`): acceptance tests 9–13 with a
  monkeypatched `single`/launcher, following the existing patterns in that
  file. Delete `test_stress_adds_delay_metadata` (lines 332–348) in the same
  commit that changes the behavior it locks in.
- Implement `delay_ms: int = 0` on `ea.single()` (threaded to
  `build_ea_ini(execution_mode=...)`, recorded in run metadata) and rewrite
  `ea.stress()` to the ladder contract: serial scenario runs, collision-safe
  per-rung run ids (`stress-{token}-{expert}` prefix, spec Architecture
  part 4), `STRESS_BASELINE_FAILED` short-circuit with the failed baseline
  envelope under `error.data.baseline`, per-scenario envelopes, robustness
  block, `schema: "stress.v1"`.

### Phase 4 — CLI and error registry

- Tests first (`tests/test_cli.py`): acceptance tests 14–15.
- Replace `--delays-ms` with `--delays` on `mt5/cli.py` (`tester ea stress`,
  lines 1455–1465); add `--modelling` and `--timeout` options mirroring the
  library signature.
- Register `INVALID_DELAYS` and `STRESS_BASELINE_FAILED` in
  `mt5_cli/errors.py`.

### Phase 5 — Docs

- README: document the real `stress` contract wherever tester commands are
  described. Note: `OPEN_SOURCE_PLAN.md:129` already tracks adding
  scanner/stress to the README command table — close that gap here rather
  than describing the old stub.
- `AGENTS.md`: add the `stress.v1` envelope and the verdict bands so agents
  gate on `robustness.verdict` instead of parsing stats.
- `CHANGELOG.md` Unreleased: `Added` (delay ladder + robustness score) and
  `Changed` (breaking: `--delays-ms`/`delays_ms` removed and why).
- Flip this plan and the spec to `Status: Implemented (merged ..., PR #N)`;
  refresh the playground if the shipped contract diverged from it.

## Unsupported Boundaries

- `optimize()` keeps default execution; stressed-optimization ranking is a
  future slice.
- No spread/slippage/requote modeling; MT5's native delay emulation only.
- No multi-symbol stress; no indicator-test changes; no new MCP surface.

## Verification Gate

Run before merge:

```bash
ruff check .
pytest -m "not integration"
mypy mt5_cli mt5 mt5_mcp
git diff --check
```

Live integration (manual, optional): with a closed terminal and a compiled
demo EA, run a two-rung ladder (`--delays 0,500`) and confirm the run dirs'
`tester.ini` files differ only in `ExecutionMode` and the stressed run's
journal shows delayed executions.
