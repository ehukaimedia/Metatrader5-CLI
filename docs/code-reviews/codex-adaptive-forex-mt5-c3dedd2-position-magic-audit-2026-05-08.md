# Codex Review: c3dedd2 Position Magic Fix

Review target: `c3dedd2` on `master`

## Findings

No blocking findings.

The production bug is correctly diagnosed and the fix is the right layer:

- `adaptive-forex-mt5/agent.py::active_strategies()` already depended on `list_positions(cfg)` returning `magic`.
- Pending orders had `magic`; open positions did not.
- Once a limit filled into an open position, the agent could no longer identify it as its own `(symbol, magic)` and could place another same-strategy pending order.
- `metatrader5_cli/mt5/core/position.py::_pos_to_dict()` now includes both `magic` and `comment`, so `position list` and `position show` expose the same identity fields that the agent needs.

## Residual Risk / Carry-Forward

- The global active cap still counts every integer-magic position/order returned by the terminal, not only configured POC magics. This was already noted in the `ff73a59` audit and is not made worse by this fix.
- There is no new unit test asserting `position.list()` includes `magic` and `comment`. Existing non-live tests still pass, and the live smoke reportedly verified the broker output, but a mock-level regression test would be a good next hardening patch.

## Verification

- `python -m py_compile metatrader5_cli\mt5\core\position.py adaptive-forex-mt5\agent.py` passed.
- `python -m pytest metatrader5_cli\mt5\tests\test_core.py metatrader5_cli\mt5\tests\test_decoupling.py` passed: `217 passed`.
- I did not query or modify live orders/positions during this review.

## Verdict

`c3dedd2` closes the live duplicate-placement hole. With the orphan pending order already cancelled and the agent restarted, the per-pair active-strategy guard should now recognize the open USDJPY agent position by magic and refuse additional USDJPY placements until it resolves. Green for continued supervised demo monitoring.
