# Quant Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented — PR #10 (under review). Built in 5 codex-gated checkpoints; full suite green. **Task 0 is CLOSED**: dog-fooding a live optimization confirmed MT5 emits a **SpreadsheetML** report (not the `<pass>`-children shape assumed below), so `parse_optimization_xml` + `tests/fixtures/sample_optimization.xml` were rewritten to match it and validated live (0 → 20 passes). The detailed Task-0 / passes steps below **predate the dogfood and are superseded** by the spec and the shipped code — keep the spec as the source of truth.

**Goal:** Ship `mt5 quant` — a campaign that drives the native MT5 Strategy Tester across a symbol × timeframe matrix with explicit two-pass IS/OOS validation, configurable selection gates, ranked survivors, a `quant.v1` envelope, a dependency-free HTML report, and a static agent playbook.

**Architecture:** A new pure-stdlib package `mt5_cli/quant/` (matrix, passes, selection, report, store, campaign) composes the existing `mt5_cli.tester.ea` primitives; `mt5/cli.py` adds a thin `quant` group plus `tester ea stress --set-file`. Per cell, serially: optimize IS `[from, split−1d]` → pick winner by in-sample PF (among passes clearing an in-sample trade floor `--min-is-trades`, default `--min-trades`) → `single` OOS `[split, to]` → `single` FULL `[from, to]`. Like the tester package, `quant` never imports MetaTrader5.

> **Post-merge refinement (selection):** `pick_winner` gained an in-sample trade floor (`--min-is-trades`, default `--min-trades`) so a sparse, overfit pass can't be crowned over a denser, more robust one; since FULL ⊇ IS, the default also implies the FULL `MIN_TRADES` gate. See the spec's *Selection & ranking contract* — the source of truth.

**Tech Stack:** Python 3.10+, click, stdlib only (`xml.etree`, `datetime`, `html.parser`); pytest; the existing `mt5_cli.tester` and `mt5_cli.reports` modules.

**Spec:** [docs/specs/quant-workflow.md](../specs/quant-workflow.md) · **Playground:** [docs/playgrounds/specs/quant-workflow.html](../playgrounds/specs/quant-workflow.html)

**Conventions:** No AI commit trailers (repo policy). Run `ruff check .`, `pytest -m "not integration"`, `mypy mt5_cli mt5 mt5_mcp`, `git diff --check` before any merge. Commit after every green step.

---

## Data shapes (stable across tasks)

```python
# matrix.py
Cell = tuple[str, str]                     # (symbol, timeframe)

# passes.py — one per optimization pass
Pass = dict  # {"params": dict[str, str], "is": ISMetrics}
ISMetrics = dict  # {"profit_factor": float|None, "trades": int|None, "sharpe": float|None, "net_profit": float|None}

# selection.py — one assembled cell after the two-pass runs
CellResult = dict  # {
#   "symbol": str, "timeframe": str, "side": str|None, "validated": bool,
#   "set_file": str, "run_id": str,
#   "is":   {"profit_factor","trades","sharpe","net_profit"},
#   "oos":  {"profit_factor","trades","sharpe","net_profit","max_drawdown_pct","win_rate"},
#   "full": {"profit_factor","trades","sharpe","net_profit","max_drawdown_pct","win_rate"},
# }
Reject = dict  # {"symbol","timeframe","reason": "NO_WINNER"|"MIN_TRADES"|"CELL_FAILED", ...}
```

The envelope is `quant.v1` exactly as in the spec's *Envelope* section.

---

## File Structure

- Create `mt5_cli/quant/__init__.py` — exports `campaign`, `list_campaigns`, `get_campaign`.
- Create `mt5_cli/quant/matrix.py` — pure: cell expansion, split→date, param parsing.
- Create `mt5_cli/quant/passes.py` — pure: read IS optimization passes (params + IS metrics).
- Create `mt5_cli/quant/selection.py` — pure: `pick_winner`, `gate_and_rank`.
- Create `mt5_cli/quant/report.py` — pure: dependency-free HTML + inline-SVG equity.
- Create `mt5_cli/quant/store.py` — campaign id + `manifest.json` + list/get.
- Create `mt5_cli/quant/campaign.py` — orchestration: per-cell two-pass → `quant.v1`.
- Create `mt5_cli/skills/QUANT_WORKFLOW.md` — agent playbook (ships in Task 10).
- Modify `mt5_cli/errors.py` — register 4 root error codes.
- Modify `mt5_cli/tester/ea.py` — thread `set_file` into `stress()`.
- Modify `mt5/cli.py` — `quant` group (`run`/`list`/`show`) + `tester ea stress --set-file`.
- Create `tests/fixtures/quant/optimization_is.xml` — real captured MT5 optimization report.
- Create `tests/test_quant_matrix.py`, `test_quant_passes.py`, `test_quant_selection.py`, `test_quant_report.py`, `test_quant_store.py`, `test_quant_campaign.py`, `test_quant_cli.py`, `test_quant_playbook.py`.
- Modify `mt5_cli/tester/tests/...` (or repo test home) — stress `--set-file` coverage.
- Modify `README.md`, `AGENTS.md`, `CHANGELOG.md`, and the `describe` catalog source.

---

## Task 0: Discharge the optimization-XML assumption (milestone 1)

> **SUPERSEDED — do not follow the steps below.** Dog-fooding closed this gate:
> real MT5 emits a **SpreadsheetML** report (not the `<pass>`-children shape these
> steps assume), parsed by `results.parse_optimization_xml`; the real fixture is
> `tests/fixtures/sample_optimization.xml`. The spec and shipped code are
> authoritative; this section is kept only as a historical record.

The whole feature rests on the optimization report exposing each pass's **input
parameter columns** and **in-sample profit factor**. Prove it against a real MT5
artifact before building on it. (Spec: *Implementation risks #1*.)

**Files:**
- Create: `tests/fixtures/quant/optimization_is.xml` (captured, committed)
- Create: `tests/fixtures/quant/README.md` (how it was captured)

- [ ] **Step 1: Capture a real optimization report (operator, manual)**

On a Windows box with MT5 + a compiled demo EA exposing ≥2 `input`s, run a small genetic optimization and copy the produced `optimization.xml` to the fixture path:

```bash
mt5 --json tester ea optimize --expert demo --symbol EURUSD --tf H1 \
  --from 2023-01-01 --to 2023-06-30 --mode genetic \
  --param FastPeriod=9,5,1,21 --param SlowPeriod=21,10,5,60
# copy results/<run-id>/optimization.xml -> tests/fixtures/quant/optimization_is.xml
```

- [ ] **Step 2: Inspect the columns and record the decision**

Open the fixture and confirm, per `<pass>`: (a) the input parameters appear as named child elements (e.g. `FastPeriod`, `SlowPeriod`), and (b) an in-sample profit-factor column exists (MT5 commonly labels it `Profit Factor`). Write findings into `tests/fixtures/quant/README.md`, including the exact column tag names.

- [ ] **Step 3: Branch the contract on what the fixture shows**

  - **If params + Profit Factor are present** → proceed with Tasks 3–4 as written; record the exact tag-name map.
  - **If in-sample PF is absent** → the gate/winner needs it: add a 4th launch per cell (an explicit IS `single` on `[from, split−1d]`) in Task 7, and `passes.read` reads only parameters; selection then reads IS PF from that IS `single`'s parsed stats. Note this in `README.md` and adjust Task 3/7 accordingly.

- [ ] **Step 4: Commit the fixture + decision**

```bash
git add tests/fixtures/quant/optimization_is.xml tests/fixtures/quant/README.md
git commit -m "test: capture real MT5 optimization.xml fixture for quant winner selection"
```

---

## Task 1: Register root error codes

**Files:**
- Modify: `mt5_cli/errors.py`
- Test: `tests/test_quant_errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quant_errors.py
from mt5_cli import errors

def test_quant_error_codes_registered():
    for code in ("EMPTY_MATRIX", "INVALID_SPLIT", "INVALID_PARAM", "INVALID_RANK_BY"):
        assert code in errors.REGISTRY
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `pytest tests/test_quant_errors.py -v` — Expected: FAIL (codes missing). If the registry symbol differs, mirror the existing `INVALID_DELAYS` registration in `mt5_cli/errors.py` and assert against the same structure.

- [ ] **Step 3: Register the codes**

Add to `mt5_cli/errors.py`, following the existing entry style:

```python
"EMPTY_MATRIX": "A quant campaign needs at least one symbol and one timeframe.",
"INVALID_SPLIT": "--split must be a 0<f<1 fraction or a YYYY-MM-DD date.",
"INVALID_PARAM": "--param must be NAME=value or NAME=value,start,step,stop.",
"INVALID_RANK_BY": "--rank-by must be one of full_net, oos_sharpe, oos_pf.",
```

- [ ] **Step 4: Run it, expect PASS** — `pytest tests/test_quant_errors.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(quant): register root error codes"`

---

## Task 2: `matrix.py` — cells, split→date, params

**Files:**
- Create: `mt5_cli/quant/__init__.py` (empty for now), `mt5_cli/quant/matrix.py`
- Test: `tests/test_quant_matrix.py`

- [ ] **Step 1: Write failing tests** (spec acceptance 1–4)

```python
# tests/test_quant_matrix.py
import pytest
from mt5_cli.quant import matrix

def test_expand_orders_and_dedupes():
    assert matrix.expand(["EURUSD", "XAUUSD"], ["H1", "H2"]) == [
        ("EURUSD", "H1"), ("EURUSD", "H2"), ("XAUUSD", "H1"), ("XAUUSD", "H2"),
    ]
    assert matrix.expand(["EURUSD", "EURUSD"], ["H1", "H1"]) == [("EURUSD", "H1")]

def test_expand_empty_raises():
    with pytest.raises(ValueError):
        matrix.expand([], ["H1"])
    with pytest.raises(ValueError):
        matrix.expand(["EURUSD"], [])

def test_resolve_split_fraction_floor():
    # 1095-day span, floor(0.70*1095)=766 -> 2024-02-06 (first OOS day)
    assert matrix.resolve_split("2022-01-01", "2024-12-31", "0.70") == "2024-02-06"

def test_resolve_split_explicit_date_passthrough():
    assert matrix.resolve_split("2022-01-01", "2024-12-31", "2024-06-01") == "2024-06-01"

def test_resolve_split_invalid():
    for bad in ("1.5", "0", "abc", ""):
        with pytest.raises(ValueError):
            matrix.resolve_split("2022-01-01", "2024-12-31", bad)

def test_is_end_is_day_before_split():
    assert matrix.is_end("2024-02-06") == "2024-02-05"

def test_parse_params_ok_and_bad():
    assert matrix.parse_params(["Risk=1.0,0.5,0.5,3.0"]) == ["Risk=1.0,0.5,0.5,3.0"]
    with pytest.raises(ValueError):
        matrix.parse_params(["Risk="])
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_matrix.py -v` (module missing)

- [ ] **Step 3: Implement `matrix.py`**

```python
"""Pure matrix expansion, split-date resolution, and param validation.

Stdlib-only; no MetaTrader5, no filesystem. Mirrors the tester package's
bridge-isolation rule.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from mt5_cli.tester import ini_builder


def expand(symbols: list[str], timeframes: list[str]) -> list[tuple[str, str]]:
    syms = list(dict.fromkeys(s.strip() for s in symbols if s.strip()))
    tfs = list(dict.fromkeys(t.strip() for t in timeframes if t.strip()))
    if not syms or not tfs:
        raise ValueError("A quant campaign needs at least one symbol and one timeframe.")
    return [(s, t) for s in syms for t in tfs]


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def resolve_split(from_date: str, to_date: str, split: str) -> str:
    """Return the first out-of-sample day (YYYY-MM-DD).

    A 0<f<1 fraction resolves to from + floor(f*(to-from)) days; an explicit
    YYYY-MM-DD strictly inside (from, to) is used as-is.
    """
    start, end = _parse_date(from_date), _parse_date(to_date)
    if end <= start:
        raise ValueError("--from must precede --to.")
    try:
        frac = float(split)
        is_fraction = "-" not in split
    except ValueError:
        is_fraction = False
    if is_fraction:
        if not (0.0 < frac < 1.0):
            raise ValueError("--split fraction must be 0<f<1.")
        offset = math.floor(frac * (end - start).days)
        boundary = start + timedelta(days=offset)
    else:
        try:
            boundary = _parse_date(split)
        except ValueError as exc:
            raise ValueError("--split must be a 0<f<1 fraction or a YYYY-MM-DD date.") from exc
    if not (start < boundary <= end):
        raise ValueError("--split must fall strictly after --from and on/before --to.")
    return boundary.isoformat()


def is_end(split: str) -> str:
    """Last in-sample day = the day before the (first-OOS) split day."""
    return (_parse_date(split) - timedelta(days=1)).isoformat()


def parse_params(specs: list[str]) -> list[str]:
    """Validate each NAME=value[,start,step,stop] spec via the .set grammar."""
    ini_builder.render_set(list(specs))  # raises ValueError on a bad spec
    return list(specs)
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_quant_matrix.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(quant): matrix expansion, split-date, param parsing"`

---

## Task 3: `passes.py` — read IS optimization passes

**Files:**
- Create: `mt5_cli/quant/passes.py`
- Test: `tests/test_quant_passes.py` (uses the Task 0 fixture)

> Use the exact column tag names recorded in `tests/fixtures/quant/README.md`. The map below is the expected default; adjust the right-hand keys to the fixture if MT5 labels differ.

- [ ] **Step 1: Write the failing test against the real fixture**

```python
# tests/test_quant_passes.py
from pathlib import Path
from mt5_cli.quant import passes

FIX = Path("tests/fixtures/quant/optimization_is.xml")

def test_read_yields_params_and_is_pf():
    rows = passes.read(FIX, param_names=["FastPeriod", "SlowPeriod"])
    assert rows, "fixture should contain at least one pass"
    first = rows[0]
    assert set(first["params"]) == {"FastPeriod", "SlowPeriod"}
    assert isinstance(first["is"]["profit_factor"], float)
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_passes.py -v`

- [ ] **Step 3: Implement `passes.py`**

```python
"""Read a native in-sample optimization report into per-pass records.

Wraps results.parse_optimization_xml (which yields each <pass>'s child tags as a
flat dict) and projects the columns this feature needs: the EA input parameters
(by name) and in-sample metrics. Stdlib-only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mt5_cli.tester import results

# MT5 optimization column tag -> our IS metric key. Confirm against the fixture.
_IS_COLUMNS = {
    "Profit Factor": "profit_factor",
    "Trades": "trades",
    "Sharpe Ratio": "sharpe",
    "Result": "net_profit",
}


def read(path: Path | str, *, param_names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in results.parse_optimization_xml(path):
        params = {name: raw[name] for name in param_names if name in raw}
        is_metrics = {
            our: raw.get(col) for col, our in _IS_COLUMNS.items()
        }
        # normalize to our key set even when a column is absent
        is_block = {
            "profit_factor": _as_float(is_metrics.get("profit_factor")),
            "trades": _as_int(is_metrics.get("trades")),
            "sharpe": _as_float(is_metrics.get("sharpe")),
            "net_profit": _as_float(is_metrics.get("net_profit")),
        }
        rows.append({"params": {k: str(v) for k, v in params.items()}, "is": is_block})
    return rows


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_quant_passes.py -v` (adjust `_IS_COLUMNS`/`param_names` to the fixture if needed, then re-run)
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(quant): read IS optimization passes (params + IS metrics)"`

---

## Task 4: `selection.py` — pick winner + gate/rank

**Files:**
- Create: `mt5_cli/quant/selection.py`
- Test: `tests/test_quant_selection.py`

- [ ] **Step 1: Write failing tests** (spec acceptance 6, 7, 11)

```python
# tests/test_quant_selection.py
from mt5_cli.quant import selection

def _pass(pf, fast):  # minimal IS pass
    return {"params": {"FastPeriod": str(fast)}, "is": {"profit_factor": pf, "trades": 400,
            "sharpe": 1.0, "net_profit": 100.0}}

def test_pick_winner_by_is_pf_above_gate():
    passes = [_pass(1.2, 9), _pass(1.9, 12), _pass(0.8, 5)]
    w = selection.pick_winner(passes, min_pf=1.0)
    assert w["params"]["FastPeriod"] == "12"   # best IS PF among gate-clearers

def test_pick_winner_none_when_no_pass_clears():
    assert selection.pick_winner([_pass(0.8, 5)], min_pf=1.0) is None

def test_gate_and_rank_full_net_default_and_caveat():
    cells = [
        {"symbol": "GOLD", "timeframe": "H1", "full": {"trades": 800, "net_profit": 55000.0},
         "oos": {"profit_factor": 2.0, "sharpe": 1.8}},
        {"symbol": "EURUSD", "timeframe": "H1", "full": {"trades": 900, "net_profit": 13000.0},
         "oos": {"profit_factor": 1.5, "sharpe": 1.0}},
    ]
    out = selection.gate_and_rank(cells, min_trades=300, oos_min_pf=1.0,
                                  rank_by="full_net", per_asset=2)
    assert [c["symbol"] for c in out["ranked"]] == ["GOLD", "EURUSD"]
    assert out["rank_caveat"] is None
    out2 = selection.gate_and_rank(cells, min_trades=300, oos_min_pf=1.0,
                                   rank_by="oos_sharpe", per_asset=2)
    assert out2["rank_caveat"] is not None

def test_gate_min_trades_rejects():
    cells = [{"symbol": "X", "timeframe": "H1", "full": {"trades": 100, "net_profit": 1.0},
              "oos": {"profit_factor": 1.2}}]
    out = selection.gate_and_rank(cells, min_trades=300, oos_min_pf=1.0,
                                  rank_by="full_net", per_asset=2)
    assert out["ranked"] == []
    assert out["rejected"][0]["reason"] == "MIN_TRADES"

def test_validated_flag_does_not_gate_ranking():
    cells = [{"symbol": "X", "timeframe": "H1", "full": {"trades": 400, "net_profit": 5.0},
              "oos": {"profit_factor": 0.9}}]
    out = selection.gate_and_rank(cells, min_trades=300, oos_min_pf=1.0,
                                  rank_by="full_net", per_asset=2)
    assert out["ranked"][0]["validated"] is False  # still ranked
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_selection.py -v`

- [ ] **Step 3: Implement `selection.py`**

```python
"""Pure winner selection and cross-cell ranking. The tester/stress.py analog."""
from __future__ import annotations

from typing import Any

_RANK_KEYS = {
    "full_net": lambda c: c["full"].get("net_profit"),
    "oos_sharpe": lambda c: c.get("oos", {}).get("sharpe"),
    "oos_pf": lambda c: c.get("oos", {}).get("profit_factor"),
}
_OOS_KEYS = {"oos_sharpe", "oos_pf"}


def pick_winner(passes: list[dict[str, Any]], *, min_pf: float) -> dict[str, Any] | None:
    """Best in-sample pass clearing min_pf, by in-sample profit factor. None -> NO_WINNER."""
    qualified = [p for p in passes if (p["is"].get("profit_factor") or 0.0) >= min_pf]
    if not qualified:
        return None
    return max(qualified, key=lambda p: p["is"]["profit_factor"])


def gate_and_rank(cells: list[dict[str, Any]], *, min_trades: int, oos_min_pf: float,
                  rank_by: str, per_asset: int) -> dict[str, Any]:
    if rank_by not in _RANK_KEYS:
        raise ValueError("--rank-by must be one of full_net, oos_sharpe, oos_pf.")

    survivors: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for c in cells:
        if (c["full"].get("trades") or 0) < min_trades:
            rejected.append({"symbol": c["symbol"], "timeframe": c["timeframe"],
                             "reason": "MIN_TRADES", "full": {"trades": c["full"].get("trades")}})
            continue
        c["validated"] = (c.get("oos", {}).get("profit_factor") or 0.0) >= oos_min_pf
        survivors.append(c)

    key = _RANK_KEYS[rank_by]
    survivors.sort(key=lambda c: (key(c) is not None, key(c)), reverse=True)

    ranked: list[dict[str, Any]] = []
    per: dict[str, int] = {}
    for c in survivors:
        n = per.get(c["symbol"], 0) + 1
        per[c["symbol"]] = n
        if n <= per_asset:
            c["rank"] = len(ranked) + 1
            ranked.append(c)

    return {
        "ranked": ranked,
        "rejected": rejected,
        "rank_caveat": ("oos_metric_can_reflect_asset_drift" if rank_by in _OOS_KEYS else None),
    }
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_quant_selection.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(quant): winner selection + gate/rank"`

---

## Task 5: `store.py` — campaign id + manifest

**Files:**
- Create: `mt5_cli/quant/store.py`
- Test: `tests/test_quant_store.py`

- [ ] **Step 1: Write failing tests** (spec acceptance 11, 15)

```python
# tests/test_quant_store.py
from mt5_cli.quant import store

def test_campaign_id_shape():
    cid = store.make_campaign_id("alpha", at="2026-06-16T19-40-00")
    assert cid == "2026-06-16T19-40-00_quant_alpha"

def test_manifest_roundtrip(tmp_path):
    cid = "2026-06-16T19-40-00_quant_alpha"
    data = {"schema": "quant.v1", "campaign_id": cid, "ranked": [], "rejected": []}
    store.write_manifest(cid, data, root=tmp_path)
    assert store.get_campaign(cid, root=tmp_path)["data"]["schema"] == "quant.v1"
    assert [c["campaign_id"] for c in store.list_campaigns(root=tmp_path)] == [cid]
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_store.py -v`

- [ ] **Step 3: Implement `store.py`**

```python
"""Campaign id + manifest.json persistence under <root>/<campaign-id>/.

Reuses the tester cache conventions (sortable UTC ids, lazy dir creation).
Time is injected so the module stays deterministic and testable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def make_campaign_id(label: str, *, at: str | None = None) -> str:
    stamp = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_quant_{label}"


def _dir(cid: str, root: Path | str) -> Path:
    p = Path(root) / cid
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_manifest(cid: str, data: dict[str, Any], *, root: Path | str = "results") -> Path:
    path = _dir(cid, root) / "manifest.json"
    path.write_text(json.dumps({"campaign_id": cid, "data": data}, indent=2), encoding="utf-8")
    return path


def get_campaign(cid: str, *, root: Path | str = "results") -> dict[str, Any] | None:
    path = Path(root) / cid / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_campaigns(*, root: Path | str = "results") -> list[dict[str, Any]]:
    rp = Path(root)
    if not rp.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted((d for d in rp.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True):
        man = d / "manifest.json"
        if man.exists():
            out.append({"campaign_id": d.name, "path": str(d)})
    return out
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_quant_store.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(quant): campaign id + manifest store"`

---

## Task 6: `report.py` — dependency-free HTML + inline SVG

**Files:**
- Create: `mt5_cli/quant/report.py`
- Test: `tests/test_quant_report.py`

- [ ] **Step 1: Write failing tests** (spec acceptance 13)

```python
# tests/test_quant_report.py
import re
from mt5_cli.quant import report

DATA = {
    "campaign_id": "cid", "from": "2022-01-01", "to": "2024-12-31", "split": "2024-02-06",
    "ranked": [{"rank": 1, "symbol": "XAUUSD", "timeframe": "H1", "validated": True,
                "run_id": "r1", "full": {"trades": 804, "net_profit": 55198.59, "profit_factor": 2.02},
                "is": {"profit_factor": 2.10}, "oos": {"profit_factor": 2.02, "sharpe": 1.79},
                "equity_curve": [{"balance": 10000}, {"balance": 10200}, {"balance": 10500}]}],
    "rejected": [{"symbol": "UKOIL", "timeframe": "H1", "reason": "MIN_TRADES"}],
}

def test_render_is_self_contained_with_svg_and_links():
    html = report.render(DATA)
    assert "<svg" in html and "<polyline" in html
    assert "results/r1/report.html" in html               # link to child run
    assert not re.search(r'(src|href)="https?://', html)  # no external assets
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_report.py -v`

- [ ] **Step 3: Implement `report.py`** (pure-Python templating; SVG polyline from balances)

```python
"""Render the consolidated campaign report as one self-contained HTML file.

No matplotlib / pandas: the equity curve is an inline-SVG <polyline> generated
from the parsed balance series. Links out to each child run's native report.
"""
from __future__ import annotations

from html import escape
from typing import Any


def _svg(curve: list[dict[str, Any]], width: int = 480, height: int = 120) -> str:
    pts = [p.get("balance") for p in curve if p.get("balance") is not None]
    if len(pts) < 2:
        return '<svg viewBox="0 0 480 120"></svg>'
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    step = width / (len(pts) - 1)
    coords = " ".join(
        f"{i * step:.1f},{height - (v - lo) / span * height:.1f}" for i, v in enumerate(pts)
    )
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">'
            f'<polyline fill="none" stroke="#0f766e" stroke-width="2" points="{coords}"/></svg>')


def _row(c: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{c.get('rank','')}</td><td>{escape(c['symbol'])}</td><td>{escape(c['timeframe'])}</td>"
        f"<td>{'yes' if c.get('validated') else 'no'}</td>"
        f"<td>{c['full'].get('trades','')}</td><td>{c['full'].get('net_profit','')}</td>"
        f"<td>{c.get('oos',{}).get('sharpe','')}</td>"
        f"<td><a href=\"results/{escape(str(c.get('run_id','')))}/report.html\">report</a></td>"
        "</tr>"
    )


def render(data: dict[str, Any]) -> str:
    ranked = "".join(_row(c) for c in data.get("ranked", []))
    cards = "".join(
        f"<section><h3>{escape(c['symbol'])} {escape(c['timeframe'])} — rank {c.get('rank','')}</h3>"
        f"{_svg(c.get('equity_curve', []))}</section>"
        for c in data.get("ranked", [])
    )
    rejected = "".join(
        f"<li>{escape(r['symbol'])} {escape(r['timeframe'])} — {escape(r['reason'])}</li>"
        for r in data.get("rejected", [])
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Quant campaign {escape(data.get('campaign_id',''))}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:6px 10px}}</style></head><body>
<h1>Quant campaign — {escape(data.get('from',''))} → {escape(data.get('to',''))} (split {escape(data.get('split',''))})</h1>
<table><tr><th>#</th><th>Asset</th><th>TF</th><th>validated</th><th>FULL trades</th>
<th>FULL net</th><th>OOS Sharpe</th><th>run</th></tr>{ranked}</table>
{cards}
<h2>Rejected</h2><ul>{rejected}</ul>
<p><small>Single broker / single asset is not validated edge — confirm broker clock, spread/slippage, and cost sensitivity.</small></p>
</body></html>"""
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_quant_report.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(quant): dependency-free HTML report with inline-SVG equity"`

---

## Task 7: `campaign.py` — two-pass orchestration

**Files:**
- Create: `mt5_cli/quant/campaign.py`, finalize `mt5_cli/quant/__init__.py`
- Test: `tests/test_quant_campaign.py` (fake launcher — no terminal)

- [ ] **Step 1: Write failing tests** (spec acceptance 8, 9, 10, 12, 14)

```python
# tests/test_quant_campaign.py
from mt5_cli.quant import campaign

def test_three_launches_per_cell(monkeypatch, tmp_path):
    calls = []
    def fake_optimize(**kw):
        calls.append(("optimize", kw["from_date"], kw["to_date"]))
        return {"ok": True, "data": {"optimization": [
            {"FastPeriod": "9", "Profit Factor": "1.8", "Trades": "400",
             "Sharpe Ratio": "1.2", "Result": "500"}],
            "run_dir": str(tmp_path / "opt")}}
    def fake_single(**kw):
        calls.append(("single", kw["from_date"], kw["to_date"]))
        return {"ok": True, "data": {"run_id": "r", "run_dir": str(tmp_path / "s"),
                "stats": {"total_trades": 400, "net_profit": 1000.0, "profit_factor": 1.7,
                          "sharpe": 1.1, "max_drawdown_pct": 5.0, "win_rate": 0.5},
                "equity_curve": [{"balance": 10000}, {"balance": 11000}]}}
    monkeypatch.setattr(campaign.ea, "optimize", fake_optimize)
    monkeypatch.setattr(campaign.ea, "single", fake_single)
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], results_root=tmp_path,
                       param_names=["FastPeriod"])
    assert env["data"]["schema"] == "quant.v1"
    kinds = [c[0] for c in calls]
    assert kinds == ["optimize", "single", "single"]                 # 3 launches
    assert calls[0][2] == "2024-02-05"                               # optimize to = split-1
    assert calls[1][1] == "2024-02-06"                               # OOS single from = split

def test_empty_matrix_zero_launches(tmp_path):
    env = campaign.run(expert="demo", symbols=[], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=[], results_root=tmp_path)
    assert env["ok"] is False and env["error"]["code"] == "EMPTY_MATRIX"

def test_dry_run_launches_nothing(monkeypatch, tmp_path):
    def boom(**kw):
        raise AssertionError("no launch in dry-run")
    monkeypatch.setattr(campaign.ea, "optimize", boom)
    monkeypatch.setattr(campaign.ea, "single", boom)
    env = campaign.run(expert="demo", symbols=["EURUSD", "XAUUSD"], timeframes=["H1", "H2"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=[], results_root=tmp_path, dry_run=True)
    assert env["data"]["cells"] == 4 and env["data"]["planned_launches"] == 12
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_campaign.py -v`

- [ ] **Step 3: Implement `campaign.py`**

```python
"""Quant campaign orchestration: per-cell two-pass -> quant.v1.

Composes the filesystem-only tester primitives. MUST NOT import MetaTrader5.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mt5_cli.reports import fail, ok
from mt5_cli.tester import cache, ea, ini_builder
from mt5_cli.tester import results as _results

from . import matrix, passes, report, selection, store


def run(*, expert: str, symbols: list[str], timeframes: list[str], from_date: str,
        to_date: str, split: str, params: list[str] | None = None, mode: str = "genetic",
        min_trades: int = 300, min_pf: float = 1.0, oos_min_pf: float = 1.0,
        rank_by: str = "full_net", per_asset: int = 2, modelling: str = "ohlc-1m",
        param_names: list[str] | None = None, results_root: Path | str = "results",
        dry_run: bool = False, html: bool = True, timeout: int = 1800,
        label: str | None = None) -> dict[str, Any]:
    try:
        cells = matrix.expand(symbols, timeframes)
        split_day = matrix.resolve_split(from_date, to_date, split)
        is_end = matrix.is_end(split_day)
        param_list = matrix.parse_params(params or [])
    except ValueError as exc:
        code = ("EMPTY_MATRIX" if "needs at least one" in str(exc)
                else "INVALID_SPLIT" if "split" in str(exc).lower()
                else "INVALID_PARAM")
        return fail(code, str(exc))
    if rank_by not in ("full_net", "oos_sharpe", "oos_pf"):
        return fail("INVALID_RANK_BY", "--rank-by must be one of full_net, oos_sharpe, oos_pf.")

    if dry_run:
        return ok({"schema": "quant.v1", "dry_run": True,
                   "matrix": {"symbols": list(dict.fromkeys(symbols)),
                              "timeframes": list(dict.fromkeys(timeframes))},
                   "cells": len(cells), "planned_launches": len(cells) * 3, "split": split_day})

    pnames = param_names or _param_names(param_list)
    assembled: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    child_ids: list[str] = []

    for symbol, tf in cells:
        cell = _run_cell(expert=expert, symbol=symbol, tf=tf, from_date=from_date,
                         to_date=to_date, split_day=split_day, is_end=is_end,
                         params=param_list, pnames=pnames, mode=mode, min_pf=min_pf,
                         modelling=modelling, results_root=results_root, timeout=timeout)
        if cell.get("reason"):
            rejected.append(cell)
        else:
            assembled.append(cell)
            child_ids.append(cell["run_id"])

    graded = selection.gate_and_rank(assembled, min_trades=min_trades, oos_min_pf=oos_min_pf,
                                     rank_by=rank_by, per_asset=per_asset)
    rejected.extend(graded["rejected"])
    if not graded["ranked"] and not rejected:
        return fail("NO_RESULTS", "No cell produced a ranked or rejected record.")

    cid = store.make_campaign_id(label or expert)
    data = {"schema": "quant.v1", "campaign_id": cid, "expert": expert,
            "matrix": {"symbols": [s for s, _ in cells][: len(set(s for s, _ in cells))],
                       "timeframes": sorted({t for _, t in cells})},
            "from": from_date, "to": to_date, "split": split_day,
            "selection": {"min_trades": min_trades, "min_pf": min_pf, "oos_min_pf": oos_min_pf,
                          "rank_by": rank_by, "per_asset": per_asset},
            "rank_caveat": graded["rank_caveat"], "ranked": graded["ranked"],
            "rejected": rejected, "child_run_ids": child_ids}
    store.write_manifest(cid, data, root=results_root)
    if html:
        (store._dir(cid, results_root) / "report.html").write_text(report.render(data), encoding="utf-8")
        data["artifacts"] = {"report_html": f"results/{cid}/report.html",
                             "manifest": f"results/{cid}/manifest.json"}
    return ok(data)


def _run_cell(*, expert, symbol, tf, from_date, to_date, split_day, is_end, params, pnames,
              mode, min_pf, modelling, results_root, timeout) -> dict[str, Any]:
    base = {"symbol": symbol, "timeframe": tf}
    opt = ea.optimize(expert=expert, symbol=symbol, timeframe=tf, from_date=from_date,
                      to_date=is_end, mode=mode, params=params, modelling=modelling,
                      results_root=results_root, timeout=timeout)
    if not opt["ok"]:
        return {**base, "reason": "CELL_FAILED", "envelope": opt}
    winner = selection.pick_winner(passes.read_rows(opt["data"]["optimization"], param_names=pnames),
                                   min_pf=min_pf)
    if winner is None:
        return {**base, "reason": "NO_WINNER"}

    set_path = Path(opt["data"]["run_dir"]) / f"{expert}.{symbol}.{tf}.set"
    ini_builder.write_set(set_path, [f"{k}={v}" for k, v in winner["params"].items()])

    oos = ea.single(expert=expert, symbol=symbol, timeframe=tf, from_date=split_day,
                    to_date=to_date, set_file=set_path, results_root=results_root, timeout=timeout)
    full = ea.single(expert=expert, symbol=symbol, timeframe=tf, from_date=from_date,
                     to_date=to_date, set_file=set_path, results_root=results_root, timeout=timeout)
    for env in (oos, full):
        if not env["ok"]:
            return {**base, "reason": "CELL_FAILED", "envelope": env}

    return {**base, "side": None, "set_file": str(set_path), "run_id": full["data"]["run_id"],
            "is": winner["is"], "oos": _metrics(oos), "full": _metrics(full),
            "equity_curve": full["data"].get("equity_curve", [])}


def _metrics(env: dict[str, Any]) -> dict[str, Any]:
    s = env["data"].get("stats", {})
    return {"trades": s.get("total_trades"), "net_profit": s.get("net_profit"),
            "profit_factor": s.get("profit_factor"), "sharpe": s.get("sharpe"),
            "max_drawdown_pct": s.get("max_drawdown_pct"), "win_rate": s.get("win_rate")}


def _param_names(param_list: list[str]) -> list[str]:
    return [spec.split("=", 1)[0].strip() for spec in param_list if "=" in spec]
```

Add a `passes.read_rows(parsed: list[dict], *, param_names)` helper to `passes.py` that does the same projection as `read` but over an already-parsed list (so the campaign reuses the parser output from `optimize`'s envelope without re-reading the file). Update Task 3 imports accordingly:

```python
def read_rows(parsed: list[dict[str, Any]], *, param_names: list[str]) -> list[dict[str, Any]]:
    rows = []
    for raw in parsed:
        rows.append({"params": {n: str(raw[n]) for n in param_names if n in raw},
                     "is": {"profit_factor": _as_float(raw.get("Profit Factor")),
                            "trades": _as_int(raw.get("Trades")),
                            "sharpe": _as_float(raw.get("Sharpe Ratio")),
                            "net_profit": _as_float(raw.get("Result"))}})
    return rows

def read(path, *, param_names):
    return read_rows(results.parse_optimization_xml(path), param_names=param_names)
```

Register `NO_RESULTS` in `mt5_cli/errors.py` (Task 1) alongside the others.

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_quant_campaign.py -v`
- [ ] **Step 5: Add the import-boundary test** (spec acceptance 14)

```python
# tests/test_quant_campaign.py (append)
import ast, pathlib
def test_quant_never_imports_metatrader5():
    for p in pathlib.Path("mt5_cli/quant").glob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])] + [getattr(node, "module", "") or ""]
                assert not any("MetaTrader5" in n for n in names), p
```

- [ ] **Step 6: Run + Commit** — `pytest tests/test_quant_campaign.py -v` then `git add -A && git commit -m "feat(quant): two-pass campaign orchestration + quant.v1"`

---

## Task 8: `tester ea stress --set-file`

**Files:**
- Modify: `mt5_cli/tester/ea.py` (`stress` signature + the `single()` call)
- Modify: `mt5/cli.py` (`tester_ea_stress` adds `--set-file`)
- Test: `tests/test_tester_stress_setfile.py`

- [ ] **Step 1: Write failing test** (spec acceptance 15)

```python
# tests/test_tester_stress_setfile.py
from pathlib import Path
from mt5_cli.tester import ea

def test_stress_threads_set_file(monkeypatch, tmp_path):
    seen = []
    def fake_single(**kw):
        seen.append(kw.get("set_file"))
        return {"ok": True, "data": {"run_id": "r", "stats": {"net_profit": 100.0}}}
    monkeypatch.setattr(ea, "single", fake_single)
    setf = tmp_path / "w.set"; setf.write_text("Risk=1.0\n", encoding="utf-8")
    ea.stress(expert="demo", symbol="EURUSD", timeframe="H1", from_date="2024-01-01",
              to_date="2024-06-30", delays=[0, 100], set_file=setf, results_root=tmp_path)
    assert all(s == setf for s in seen)
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_tester_stress_setfile.py -v`

- [ ] **Step 3: Thread `set_file`** — in `mt5_cli/tester/ea.py`, add `set_file: Path | str | None = None` to `stress(...)` and pass `set_file=set_file` into each `single(...)` call inside it.

- [ ] **Step 4: Add the CLI flag** — in `mt5/cli.py` `tester_ea_stress`, add `@click.option("--set-file", default=None, type=click.Path(dir_okay=False))` and pass it through to `_tester_ea.stress(...)`.

- [ ] **Step 5: Run + Commit** — `pytest tests/test_tester_stress_setfile.py -v` then `git add -A && git commit -m "feat(tester): stress --set-file to stress a winning parameter set"`

---

## Task 9: CLI `quant` group (run/list/show)

**Files:**
- Modify: `mt5/cli.py` (new `quant` group), `mt5_cli/quant/__init__.py` (export `list_campaigns`/`get_campaign`)
- Test: `tests/test_quant_cli.py`

- [ ] **Step 1: Write failing tests** (spec acceptance 16) using click's `CliRunner` against `mt5.cli:main`, monkeypatching `campaign.run` to return a canned `quant.v1` so no terminal launches. Assert `quant run --dry-run` emits `ok:true` + `schema:"quant.v1"`, and `quant list` reads back a written campaign.

```python
# tests/test_quant_cli.py
from click.testing import CliRunner
from mt5.cli import main

def test_quant_run_dry_run_emits_envelope(monkeypatch):
    r = CliRunner().invoke(main, ["--json", "quant", "run", "--expert", "demo",
        "--symbols", "EURUSD", "--tf", "H1", "--from", "2022-01-01", "--to", "2024-12-31",
        "--split", "0.70", "--dry-run"])
    assert r.exit_code == 0 and '"schema": "quant.v1"' in r.output
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_quant_cli.py -v`

- [ ] **Step 3: Implement the group** — add to `mt5/cli.py`, mirroring the `tester` group: a `quant` group with `run` (all spec flags; `--symbols`/`--tf` comma-split; repeatable `--param`), `list`, and `show <campaign-id>`, each calling the library and `emit(...)`. Reuse the global `--json` hoist.

- [ ] **Step 4: Run + Commit** — `pytest tests/test_quant_cli.py -v` then `git add -A && git commit -m "feat(quant): mt5 quant run/list/show CLI group"`

---

## Task 10: Agent playbook + anti-drift guard

**Files:**
- Create: `mt5_cli/skills/QUANT_WORKFLOW.md` (verbatim from the spec's *Quant agent playbook* section)
- Test: `tests/test_quant_playbook.py`

- [ ] **Step 1: Write the playbook** — copy the spec's playbook draft verbatim into `mt5_cli/skills/QUANT_WORKFLOW.md`.

- [ ] **Step 2: Write the anti-drift guard test** (spec acceptance 17, 18)

```python
# tests/test_quant_playbook.py
import json, re, subprocess, sys
from pathlib import Path

DOC = Path("mt5_cli/skills/QUANT_WORKFLOW.md")

def test_playbook_ships_as_package_data():
    assert DOC.exists()

def test_playbook_commands_and_options_resolve_in_describe():
    catalog = json.loads(subprocess.run([sys.executable, "-m", "mt5", "--json", "describe"],
                         capture_output=True, text=True).stdout)["data"]
    cmds = {c["command"]: set(c.get("options", [])) for c in catalog["commands"]}
    text = DOC.read_text(encoding="utf-8")
    for m in re.findall(r"`mt5 ([^`]+)`", text):
        toks = [t for t in m.split() if not t.startswith("<") and t != "..."]
        opts = [t for t in toks if t.startswith("--") and t != "--json"]
        path = " ".join(t for t in toks if not t.startswith("--"))
        path = re.sub(r"\s+--json", "", path).strip()
        assert path in cmds, f"unknown command path: {path!r}"
        for o in opts:
            assert o in cmds[path], f"{path!r} has no option {o!r}"
```

- [ ] **Step 3: Run, expect FAIL then PASS** — implement any `describe`-catalog option exposure needed so the guard passes (the catalog already walks the Click tree; ensure options are included). Run: `pytest tests/test_quant_playbook.py -v`.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(quant): ship QUANT_WORKFLOW.md agent playbook + anti-drift guard"`

---

## Task 11: Docs, describe catalog, packaging, status flip

**Files:**
- Modify: `README.md` (a `## Quant Workflow` section), `AGENTS.md` (the `quant.v1` schema + `quant`/`stress --set-file` rows + new error codes), `CHANGELOG.md`, `pyproject.toml` (confirm `mt5_cli.skills` package-data already ships `*.md` — it does), the `describe` catalog (auto if it walks the tree; verify `quant` appears).
- Modify: `docs/specs/quant-workflow.md` + `docs/plans/quant-workflow-plan.md` headers → `Status: Implemented (PR #NN)`.

- [ ] **Step 1** Add the README Quant section and AGENTS rows (mirror the tester/stress entries).
- [ ] **Step 2** Verify `mt5 --json describe` lists `quant run/list/show` and the new error codes; add a snapshot test if the repo has one for `describe`.
- [ ] **Step 3** CHANGELOG `Added`: `mt5 quant` campaign + `tester ea stress --set-file`.
- [ ] **Step 4** Flip spec + plan `Status` to Implemented; commit.
- [ ] **Step 5: Full gate** — `ruff check . && pytest -m "not integration" && mypy mt5_cli mt5 mt5_mcp && git diff --check`
- [ ] **Step 6: Commit** — `git add -A && git commit -m "docs(quant): README/AGENTS/CHANGELOG + flip spec/plan status"`

---

## Self-review notes

- **Spec coverage:** Tasks map to spec acceptance tests 1–18 — matrix (T2 ↔ 1-4), passes (T3 ↔ 5), selection (T4 ↔ 6,7,11), store (T5 ↔ 11,15-as-manifest), report (T6 ↔ 13), campaign incl. import boundary (T7 ↔ 8,9,10,12,14), stress set-file (T8 ↔ 15→19), CLI (T9 ↔ 16→20), playbook+guard (T10 ↔ 17,18→21,22), docs (T11). The deferred hybrid is intentionally absent.
- **Fixture gate:** Task 0 discharges the one live risk before any code depends on it, with the explicit IS-`single` fallback documented if in-sample PF is absent.
- **Charter:** `quant` imports no MetaTrader5 (T7 import-boundary test); report is pure-Python + inline SVG (no matplotlib/pandas); the EA stays the only alpha.
- **`NO_RESULTS`** is used by `campaign.run` for the degenerate "no cell yielded any record" case — register it in Task 1 (added to the four spec codes).
