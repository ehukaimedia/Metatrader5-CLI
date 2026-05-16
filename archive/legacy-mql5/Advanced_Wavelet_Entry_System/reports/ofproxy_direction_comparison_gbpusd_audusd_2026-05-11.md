# OFProxy Direction Comparison

Generated: 2026-05-11 14:01:44
Score threshold: `0.80`

This report analyzes `*_signals_ofproxy_v2.csv` diagnostics only. It is not a profitability claim and it does not use trade execution results.

## Files

- `AUDUSD`: `C:\Users\arsen\AppData\Roaming\MetaQuotes\Tester\D0E8209F77C8CF37AD8BF550E51FF075\Agent-127.0.0.1-3000\MQL5\Files\WaveletResearch\AUDUSD_M5_AUDUSD_M5_HC80_OFProxy_Diagnostic_signals_ofproxy_v2.csv`
- `GBPUSD`: `C:\Users\arsen\AppData\Roaming\MetaQuotes\Tester\D0E8209F77C8CF37AD8BF550E51FF075\Agent-127.0.0.1-3000\MQL5\Files\WaveletResearch\GBPUSD_M5_GBPUSD_M5_HC80_OFProxy_Diagnostic_signals_ofproxy_v2.csv`

## AUDUSD

- Total signal rows: `8609`
- High-confidence rows: `174`
- Data modes: `{'1': 8609}`
- HC decision classes: `{'proceed_buy': 79, 'no_evidence': 18, 'proceed_sell': 60, 'stand_down': 9, 'investigate': 8}`

| Bucket | N | Avg 12 | Med 12 | Win 12 | Avg 24 | Med 24 | Win 24 | Avg 48 | Med 48 | Win 48 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_hc | 174 | 4.46 | -14.00 | 45.4% | -5.94 | -15.50 | 43.1% | 6.09 | -19.00 | 45.4% |
| all_buy | 98 | -3.81 | -23.50 | 39.8% | -11.00 | -22.00 | 38.8% | -0.97 | -34.00 | 40.8% |
| all_sell | 76 | 15.12 | 13.00 | 52.6% | 0.58 | -5.50 | 48.7% | 15.18 | 7.50 | 51.3% |
| proceed_all | 139 | 6.24 | -5.00 | 46.8% | 1.94 | -9.00 | 46.0% | 14.79 | -3.00 | 48.9% |
| proceed_buy | 79 | -7.92 | -22.00 | 39.2% | -11.16 | -30.00 | 38.0% | -3.58 | -34.00 | 43.0% |
| proceed_sell | 60 | 24.90 | 25.00 | 56.7% | 19.18 | 17.50 | 56.7% | 38.98 | 19.50 | 56.7% |
| non_proceed | 35 | -2.63 | -31.00 | 40.0% | -37.23 | -41.00 | 31.4% | -28.49 | -41.00 | 31.4% |
| investigate | 8 | 0.38 | -47.00 | 37.5% | -6.12 | -34.00 | 25.0% | 75.62 | -26.50 | 37.5% |
| no_evidence | 18 | -15.00 | -24.00 | 38.9% | -68.28 | -40.50 | 27.8% | -99.94 | -66.00 | 22.2% |
| stand_down | 9 | 19.44 | -18.00 | 44.4% | -2.78 | -79.00 | 44.4% | 21.89 | -6.00 | 44.4% |

**AUDUSD Year Split, 24-Bar Forward Return**

| Class | Year | N | Avg 24 | Median 24 |
|---|---:|---:|---:|---:|
| investigate | 2022 | 2 | -90.50 | -90.50 |
| investigate | 2024 | 3 | 49.67 | -19.00 |
| investigate | 2025 | 3 | -5.67 | -19.00 |
| no_evidence | 2021 | 2 | -79.50 | -79.50 |
| no_evidence | 2022 | 2 | -14.00 | -14.00 |
| no_evidence | 2023 | 5 | -61.60 | -15.00 |
| no_evidence | 2024 | 4 | -60.25 | -65.50 |
| no_evidence | 2025 | 3 | 17.67 | 31.00 |
| no_evidence | 2026 | 2 | -273.00 | -273.00 |
| proceed_buy | 2021 | 11 | -64.09 | -31.00 |
| proceed_buy | 2022 | 13 | 66.46 | -9.00 |
| proceed_buy | 2023 | 16 | -26.44 | 14.50 |
| proceed_buy | 2024 | 18 | 24.22 | 24.00 |
| proceed_buy | 2025 | 17 | -50.00 | -65.00 |
| proceed_buy | 2026 | 4 | -51.00 | -51.00 |
| proceed_sell | 2021 | 11 | 53.82 | 81.00 |
| proceed_sell | 2022 | 10 | 61.20 | 49.00 |
| proceed_sell | 2023 | 6 | 71.33 | 100.00 |
| proceed_sell | 2024 | 15 | -21.93 | -33.00 |
| proceed_sell | 2025 | 14 | 0.57 | -12.50 |
| proceed_sell | 2026 | 4 | -40.00 | -10.00 |
| stand_down | 2021 | 2 | -33.50 | -33.50 |
| stand_down | 2023 | 2 | 16.50 | 16.50 |
| stand_down | 2024 | 4 | 43.75 | 56.50 |
| stand_down | 2026 | 1 | -166.00 | -166.00 |

## GBPUSD

- Total signal rows: `8450`
- High-confidence rows: `158`
- Data modes: `{'1': 8450}`
- HC decision classes: `{'proceed_buy': 58, 'proceed_sell': 57, 'no_evidence': 15, 'investigate': 19, 'stand_down': 9}`

| Bucket | N | Avg 12 | Med 12 | Win 12 | Avg 24 | Med 24 | Win 24 | Avg 48 | Med 48 | Win 48 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_hc | 158 | -10.10 | 2.00 | 51.9% | -15.56 | -17.00 | 48.1% | -7.20 | -14.00 | 48.7% |
| all_buy | 78 | -18.46 | 2.00 | 52.6% | -45.22 | -36.50 | 39.7% | -39.17 | -42.50 | 42.3% |
| all_sell | 80 | -1.95 | 4.00 | 51.2% | 13.35 | 25.50 | 56.2% | 23.98 | 21.00 | 55.0% |
| proceed_all | 115 | -12.60 | 2.00 | 50.4% | -17.25 | -25.00 | 47.0% | -3.63 | -0.00 | 49.6% |
| proceed_buy | 58 | -31.59 | -9.00 | 48.3% | -56.69 | -41.50 | 36.2% | -47.24 | -49.00 | 43.1% |
| proceed_sell | 57 | 6.72 | 5.00 | 52.6% | 22.88 | 32.00 | 57.9% | 40.74 | 44.00 | 56.1% |
| non_proceed | 43 | -3.42 | 2.00 | 55.8% | -11.05 | 6.00 | 51.2% | -16.72 | -29.00 | 46.5% |
| investigate | 19 | -38.84 | 19.00 | 57.9% | -37.84 | -20.00 | 47.4% | 30.05 | 8.00 | 57.9% |
| no_evidence | 15 | 8.60 | -18.00 | 46.7% | 23.73 | 6.00 | 53.3% | -28.33 | -67.00 | 33.3% |
| stand_down | 9 | 51.33 | 38.00 | 66.7% | -12.44 | 17.00 | 55.6% | -96.11 | -31.00 | 44.4% |

**GBPUSD Year Split, 24-Bar Forward Return**

| Class | Year | N | Avg 24 | Median 24 |
|---|---:|---:|---:|---:|
| investigate | 2021 | 4 | -66.75 | -53.00 |
| investigate | 2022 | 2 | -138.50 | -138.50 |
| investigate | 2023 | 1 | 60.00 | 60.00 |
| investigate | 2024 | 2 | -66.50 | -66.50 |
| investigate | 2025 | 9 | -22.56 | 10.00 |
| investigate | 2026 | 1 | 101.00 | 101.00 |
| no_evidence | 2021 | 3 | -40.67 | -107.00 |
| no_evidence | 2022 | 2 | 165.00 | 165.00 |
| no_evidence | 2023 | 2 | -146.50 | -146.50 |
| no_evidence | 2024 | 4 | 145.75 | 114.00 |
| no_evidence | 2025 | 4 | -35.50 | -21.00 |
| proceed_buy | 2021 | 8 | -103.62 | -35.50 |
| proceed_buy | 2022 | 5 | -92.20 | -75.00 |
| proceed_buy | 2023 | 15 | -72.13 | -78.00 |
| proceed_buy | 2024 | 12 | -51.42 | -27.50 |
| proceed_buy | 2025 | 14 | 4.64 | 79.00 |
| proceed_buy | 2026 | 4 | -91.00 | -61.00 |
| proceed_sell | 2021 | 7 | 58.71 | 51.00 |
| proceed_sell | 2022 | 5 | -209.80 | -85.00 |
| proceed_sell | 2023 | 8 | 66.38 | 98.50 |
| proceed_sell | 2024 | 20 | 34.45 | 22.50 |
| proceed_sell | 2025 | 13 | 63.77 | 49.00 |
| proceed_sell | 2026 | 4 | -26.75 | -5.00 |
| stand_down | 2021 | 2 | -53.50 | -53.50 |
| stand_down | 2022 | 1 | 133.00 | 133.00 |
| stand_down | 2023 | 2 | -180.50 | -180.50 |
| stand_down | 2024 | 1 | -15.00 | -15.00 |
| stand_down | 2025 | 2 | 48.00 | 48.00 |
| stand_down | 2026 | 1 | 142.00 | 142.00 |

## Direction-Aware Lift

Lift is `proceed_direction avg 24` minus `all same-direction avg 24`. Positive lift means the proxy classification improved that direction versus taking every high-confidence signal in the same direction.

| Symbol/Direction | Lift 24 |
|---|---:|
| AUDUSD buy lift | -0.16 |
| AUDUSD sell lift | 18.60 |
| GBPUSD buy lift | -11.47 |
| GBPUSD sell lift | 9.53 |

## Interpretation Guardrails

- Treat buckets with fewer than 30 signals as weak evidence.
- Prefer median and year consistency over average alone.
- Do not promote a filter to execution until it survives symbol and year splits.
- Current OFProxy outputs are spot-FX order-flow proxies, not true footprint delta.
