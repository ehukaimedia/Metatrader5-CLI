# MT5 CLI — Testing Guide

---

## Unit tests (no MT5 terminal required)

All unit tests live in `test_core.py` and mock the `MetaTrader5` package via
`unittest.mock`.  They run in under two seconds with no external dependencies.

```bash
# Run the full suite
python -m pytest metatrader5_cli/mt5/tests/test_core.py -v

# Run a specific class
python -m pytest metatrader5_cli/mt5/tests/test_core.py::TestOrder -v

# Stop on first failure
python -m pytest metatrader5_cli/mt5/tests/test_core.py -x
```

---

## Integration tests (live MT5 terminal on a demo account required)

Integration tests live in `test_e2e.py` and are skipped by default.  They
require a running MetaTrader 5 terminal connected to a **demo account**.

### Enable

```bash
export MT5_DEMO_INTEGRATION=1        # Linux / macOS / WSL
$env:MT5_DEMO_INTEGRATION = "1"      # PowerShell (Windows)

python -m pytest metatrader5_cli/mt5/tests/test_e2e.py -v
```

### What they cover

- Connect to the terminal and read account info
- Fetch OHLCV rates and compute an EMA indicator
- Place a 0.01-lot demo market order
- Poll until fill is confirmed
- Close the position
- Assert that history reflects the round-trip (deal appears in `history deals`)

### pytest marks

All integration tests carry `@pytest.mark.integration`.  To run only unit
tests (skipping integration even if the env var is set):

```bash
python -m pytest -m "not integration" metatrader5_cli/mt5/tests/
```

---

## The "no live-money tests" rule

**Integration tests must never run against a real (live) account.**

`test_e2e.py` enforces this with a module-level assertion:

```python
assert account.info()["data"]["trade_mode"] != "real"
```

If the terminal is connected to a live account the entire module is skipped
with an informative message.  Do not remove or weaken this guard.

---

## CI integration

Add this to your CI pipeline to run only unit tests (safe, no MT5 needed):

```yaml
- run: python -m pytest metatrader5_cli/mt5/tests/test_core.py -v
```

To enable integration tests in a CI environment that has MT5 running:

```yaml
env:
  MT5_DEMO_INTEGRATION: "1"
- run: python -m pytest metatrader5_cli/mt5/tests/ -v
```
