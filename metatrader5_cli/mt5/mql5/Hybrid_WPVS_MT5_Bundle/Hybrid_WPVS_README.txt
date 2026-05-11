Hybrid_WPVS MT5 Bundle
======================

Files
-----
1. Hybrid_Wavelet_Pivot_Volume_Spike.mq5
   - Install to: MQL5\Indicators\
   - Non-trading indicator.
   - Closed-bar mode is default.

2. Hybrid_WPVS_DiagnosticEA.mq5
   - Install to: MQL5\Experts\
   - Non-trading diagnostic CSV exporter.
   - Reads the indicator with iCustom and CopyBuffer.
   - Exports to Terminal\Common\Files by default when FILE_COMMON is enabled.

3. Hybrid_WPVS_M5_Forex_Default.set
   - First-test indicator preset.

4. Hybrid_WPVS_DiagnosticEA_M5_Default.set
   - First-test diagnostic EA preset.

5. Hybrid_WPVS_Top3_ExecutionEA.mq5
   - Minimal trading EA for proof-of-concept validation only.
   - Reads the indicator with iCustom and CopyBuffer.
   - Uses closed-bar signals and conservative fixed-lot test defaults.

6. Hybrid_WPVS_Top3_*_NoATRStop.set
   - Current pair-specific research presets for GBPUSD, AUDUSD, and USDJPY.
   - These are not live-profit claims. They are candidate validation settings for the next real-tick and forward-test pass.

7. Hybrid_WPVS_Top3_LiveDemo_ObserveOnly_M5.set
   - First live-demo attachment preset for GBPUSD, AUDUSD, and USDJPY M5 charts.
   - Does not trade. Logs closed-bar candidate signals to Terminal\Common\Files\Hybrid_WPVS_LIVE_SIGNAL_LOG.csv.
   - Uses lower indicator threshold 0.60 so daily signal cadence can be studied.

8. Hybrid_WPVS_Top3_*_LiveDemo_TinyTrade.set
   - Pair-specific tiny-trade presets for Trading.com demo only.
   - Keep 0.01 lots, one symbol per chart, spread gate, max trades/day, daily loss cutoff, FOK filling, and pair-specific exit bars.

Compile order
-------------
1. Compile Hybrid_Wavelet_Pivot_Volume_Spike.mq5 first in MetaEditor.
2. Compile Hybrid_WPVS_DiagnosticEA.mq5 second.
3. Compile Hybrid_WPVS_Top3_ExecutionEA.mq5 third if you want to run trading backtests.
4. Restart MT5 Navigator or right-click Refresh if files do not appear.

Buffer map
----------
0 BuySignal price, EMPTY_VALUE when none
1 SellSignal price, EMPTY_VALUE when none
2 SignalState: +1 buy, -1 sell, 0 none
3 SignalScore: 0.0 to 1.0
4 VolumeRatio
5 WaveletRegime: -1 bearish usable, 0 neutral/noisy, +1 bullish usable
6 StructureClass: HH=0, HL=1, LH=2, LL=3, EMPTY_VALUE unknown
7 DebugReasonCode bitmask

DebugReasonCode bits
--------------------
1 volume pass
2 pivot pass
4 rejection pass
8 ATR/range pass
16 wavelet pass
32 buy signal
64 sell signal
128 session pass
256 spread pass
512 trend-bias pass

Non-repaint notes
-----------------
Default signal mode uses shift 1 only. Current-bar visual mode exists but is disabled by default.
Pivot checks compare the candidate only to older bars. ATR, volume, wavelet context, and structure context use bar i and older data only.
The diagnostic EA uses forward returns only as labels in exported CSV and does not trade.

Current research snapshot
-------------------------
Date captured: 2026-05-10
Tester period: 2021.05.09 through 2026.05.09
Timeframe: M5
Modeling used for first sweep: 1 minute OHLC
Lot size: 0.01 fixed

Top-three candidates from the first execution sweep:
- GBPUSD with Hybrid_WPVS_Top3_GBPUSD_M5_TimeExit48_NoATRStop.set
  - Exit after 48 bars, ATR stop disabled
  - Observed first-sweep net: +28.44 on 10000 deposit
- AUDUSD with Hybrid_WPVS_Top3_AUDUSD_M5_TimeExit24_NoATRStop.set
  - Exit after 24 bars, ATR stop disabled
  - Observed first-sweep net: +31.75 on 10000 deposit
- USDJPY with Hybrid_WPVS_Top3_USDJPY_M5_TimeExit24_NoATRStop.set
  - Exit after 24 bars, ATR stop disabled
  - Observed first-sweep net: +22.34 on 10000 deposit

Next validation step
--------------------
Run the same three pair-specific presets with Every tick based on real ticks.
After that, run Forward = 1/3 for the same period and reject any preset that collapses out of sample.
Do not treat these files as live trading presets until real-tick and forward validation are complete.

Live-demo operating model
-------------------------
Use one EA codebase on one M5 chart per symbol. The custom indicator must be installed and compiled, but it does not need to be manually attached to each chart because the EA loads it with iCustom.

Recommended first three charts:
- GBPUSD,M5 with Hybrid_WPVS_Top3_LiveDemo_ObserveOnly_M5.set
- AUDUSD,M5 with Hybrid_WPVS_Top3_LiveDemo_ObserveOnly_M5.set
- USDJPY,M5 with Hybrid_WPVS_Top3_LiveDemo_ObserveOnly_M5.set

After observe-only logging is confirmed, use the matching tiny-trade preset on each chart:
- GBPUSD,M5 with Hybrid_WPVS_Top3_GBPUSD_M5_LiveDemo_TinyTrade.set
- AUDUSD,M5 with Hybrid_WPVS_Top3_AUDUSD_M5_LiveDemo_TinyTrade.set
- USDJPY,M5 with Hybrid_WPVS_Top3_USDJPY_M5_LiveDemo_TinyTrade.set

Trading.com notes:
- No hedging assumption: the EA uses one position per symbol/effective magic.
- FIFO risk is minimized by allowing one own position per symbol/effective magic.
- Live presets force FOK filling and use 10 points deviation.
- InpDemoAccountsOnly should stay true for this proof-of-concept.
