# Quant test fixtures

## `optimization_synthetic.xml` — synthetic, NOT a real capture

Hand-authored to unit-test the parser/projection/selection **logic** in
`mt5_cli/quant/passes.py` and `selection.py`. Its tags mirror the repo's canonical
`tests/fixtures/sample_optimization.xml` — `Profit`, `ProfitFactor`, `Trades`, and
the input params — plus a `Sharpe` column to exercise the one provisional constant
(`_SHARPE`; the canonical fixture has no Sharpe). Same `<pass>`-with-child-tags
shape that `results.parse_optimization_xml` reads. `passes.read` is also tested
directly against `sample_optimization.xml` (see `tests/test_quant_passes.py`).

## The open gate (plan Task 0)

This synthetic fixture proves the **logic**, not the **real-world shape**. Before
the feature is trusted end-to-end, capture a real artifact:

```
mt5 ea new demo            # add >=2 inputs, e.g. FastPeriod, SlowPeriod
mt5 --json ea compile demo
mt5 --json tester ea optimize --expert demo --symbol EURUSD --tf H1 \
  --from 2023-01-01 --to 2023-06-30 --mode genetic \
  --param FastPeriod=9,5,1,21 --param SlowPeriod=21,10,5,60
# copy results/<run-id>/optimization.xml -> tests/fixtures/quant/optimization_is.xml
```

Then confirm each pass exposes the EA input-parameter columns **and** an
in-sample profit-factor column. If the real tag names differ from the four
constants in `passes.py`, update those constants and add a test that reads the
real `optimization_is.xml`. If in-sample PF is absent from the report, switch the
campaign to the explicit IS-`single()` fallback (plan Task 0, Step 3).
