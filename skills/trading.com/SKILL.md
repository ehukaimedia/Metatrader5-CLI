---
name: metatrader-5-trading.com
description: Specifics for the Trading.com US MT5 environment, including regulatory constraints and execution details.
---

# Trading.com MT5 Skill

## Job Description
Trading.com US is a CFTC/NFA regulated broker. This imposes specific constraints on the MetaTrader 5 environment that the agent MUST respect to avoid order rejection or account flags.

## Rules
### Critical Constraints (US Regulation)
-   **No Hedging:** You cannot hold simultaneous Long and Short positions on the same symbol. The system must use a **Netting** logic.
-   **FIFO (First In, First Out):** If multiple positions exist for the same symbol, you must close the oldest one first.
-   **Leverage:** Capped at 1:50 for major currencies (2% margin).

### Risk Management
-   **Leverage Amplification:** Agents must NEVER exceed effective 1:50 leverage sizing.
-   **Margin:** Margin Call at 50% level. Stop Out at 20%.

## Workflow
### Execution Specifics
-   **Account Type:** Spread-based (Zero Commission). Ensure `spread` is factored into the "Edge" calculation.
-   **Execution Mode:** Market Execution. Use `deviation` parameter (e.g., 5-10 points) to handle slippage.
-   **Rollover (Swaps):** Short holds are paid; Long holds bleed (-7.2 points vs +3.8 points for EURUSD).

### Configuration Recommendations
```python
# Trading.com Specifics
LEVERAGE = 50
HEDGING_ENABLED = False
FIFO_ENFORCED = True
COMMISSION_SCHEME = "SPREAD_ONLY"
```

## Common Errors
-   `Retcode 10030 (Unsupported filling)`: Default to `ORDER_FILLING_FOK` (Fill or Kill).
-   `Retcode 10027 (Auto-trading disabled)`: Ensure "Algo Trading" is enabled in the MT5 Terminal toolbar.
