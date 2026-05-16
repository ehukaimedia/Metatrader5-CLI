# CSV Schema

## Signal CSV

Rows are written after forward horizons have closed, unless incomplete rows are flushed at EA deinitialization.

| Column | Description |
|---|---|
| `symbol` | MT5 symbol |
| `timeframe` | Timeframe, for example `M5` |
| `bar_time` | Closed signal bar time |
| `direction` | `buy` or `sell` |
| `score` | Normalized score, 0.0 to 1.0 |
| `wavelet_energy` | Normalized wavelet energy score |
| `noise_ratio` | High-frequency energy / total energy |
| `volume_ratio` | Tick volume anomaly ratio |
| `spread_points` | Spread points from indicator context |
| `atr` | ATR value used for normalization |
| `pivot_distance_atr` | Distance to prior support/resistance in ATR units |
| `structure_class` | +2, +1, 0, -1, -2 |
| `debug_reason_code` | Indicator bitmask |
| `close_price` | Signal bar close |
| `signal_price` | Arrow price |
| `fwd_ret_<InpForwardBars1>_points` | Directional close-to-close return after the first configured horizon, default 3 bars |
| `fwd_ret_<InpForwardBars2>_points` | Directional close-to-close return after the second configured horizon, default 6 bars |
| `fwd_ret_<InpForwardBars3>_points` | Directional close-to-close return after the third configured horizon, default 12 bars |
| `fwd_ret_<InpForwardBars4>_points` | Directional close-to-close return after the fourth configured horizon, default 24 bars |
| `fwd_ret_<InpForwardBars5>_points` | Directional close-to-close return after the fifth configured horizon, default 48 bars |
| `export_time` | Time row was written |
| `maturity_status` | `matured`, `partial`, or `not_requested` |

## Signal CSV With Order-Flow Proxy Enabled

When `InpUseOrderFlowProxy=true` and `InpOFExportCSV=true`, default filenames use an `ofproxy_v2` suffix so old append-mode CSV headers are not mixed with the new schema.

Additional columns:

| Column | Description |
|---|---|
| `schema_version` | `ofproxy_v2` |
| `of_proxy_data_mode` | `1` for bar proxy, `-1` proxy not ready/unavailable in the EA CSV; enabled proxy handle failures fail initialization |
| `of_proxy_delta` | Signed bar pressure proxy |
| `of_proxy_divergence` | Rolling price-vs-proxy divergence |
| `of_proxy_aggression` | Candle-level aggression proxy |
| `of_proxy_stacked_pressure` | Consecutive same-side pressure proxy |
| `of_proxy_absorption` | High-effort, poor-progress proxy near structure |
| `of_proxy_confluence_score` | Signed proxy bias, `[-1,+1]` |
| `of_proxy_raw_state` | Companion indicator raw state |
| `of_proxy_decision_state` | EA-derived state relative to the base wavelet signal |
| `of_proxy_reason_code` | Companion indicator reason-code bitmask |
| `of_proxy_adjusted_score` | Reserved diagnostic field; equals base score in CSV-only v2 |
| `of_proxy_alignment_score` | Signed confluence score in the wavelet signal direction |
| `of_proxy_evidence_score` | Best aligned proxy evidence component in the wavelet direction |
| `of_proxy_conflict_score` | Strongest opposing proxy component against the wavelet direction |
| `of_proxy_profile_state` | `1` proceed evidence, `2` mixed/investigate, `-1` no evidence, `-2` conflict, `-3` proxy not ready |
| `of_proxy_decision_class` | Stable text enum: `proceed_buy`, `proceed_sell`, `investigate`, `stand_down`, `no_evidence`, `proxy_not_ready`, `neutral` |
| `of_proxy_signal_direction` | Numeric wavelet direction, separated from the decision class |

## Trade CSV

The trade CSV is event-based. It writes `blocked`, `opened`, and `closed` rows rather than editing previous rows.

| Column | Description |
|---|---|
| `event_type` | `blocked`, `opened`, or `closed` |
| `symbol` | MT5 symbol |
| `timeframe` | Timeframe |
| `signal_bar_time` | Signal bar that caused the decision |
| `open_time` | Position open time, if applicable |
| `close_time` | Position close time, if applicable |
| `direction` | `buy`, `sell`, or `none` |
| `entry` | Entry price |
| `exit` | Exit price |
| `score` | Signal score |
| `reason_opened` | Broker/result text for opened rows |
| `reason_blocked` | Blocking reason for blocked rows |
| `reason_closed` | Time exit, opposite signal, SL/TP/external, etc. |
| `profit` | Closed trade profit including commission/swap when history is available |
| `mfe_points` | Max favorable excursion in points based on closed bars |
| `mae_points` | Max adverse excursion in points based on closed bars |
| `spread_entry_points` | Spread points at decision/open context |
| `ticket` | Position/order ticket where available |
| `magic` | EA magic number |

When order-flow proxy CSV is enabled, trade CSV filenames also use an `ofproxy_v2` suffix and include proxy state-at-entry/exit columns. Signal CSV remains the authoritative source for proxy bucket analysis.
