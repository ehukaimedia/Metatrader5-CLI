//+------------------------------------------------------------------+
//| Hybrid_WPVS_DiagnosticEA.mq5                                     |
//| Non-trading CSV diagnostic exporter for Hybrid_WPVS indicator.    |
//+------------------------------------------------------------------+
#property copyright "OpenAI / user-specified project"
#property version   "1.00"
#property tester_indicator "Hybrid_Wavelet_Pivot_Volume_Spike.ex5"

//+------------------------------------------------------------------+
//| Indicator input enum mirror                                       |
//+------------------------------------------------------------------+
enum ENUM_WPVS_SIGNAL_BAR
  {
   WPVS_CURRENT_BAR_VISUAL_ONLY = 0,
   WPVS_CLOSED_BAR_ONLY         = 1
  };

//+------------------------------------------------------------------+
//| Diagnostic EA inputs                                              |
//+------------------------------------------------------------------+
input string               InpIndicatorName         = "Hybrid_Wavelet_Pivot_Volume_Spike";
input bool                 InpUseCommonFiles        = true;
input string               InpCsvFileName           = "Hybrid_WPVS_Diagnostic.csv";
input bool                 InpAutoTagCsvBySymbol    = true;
input int                  InpBarsToScan            = 500000;
input bool                 InpExportOnInit          = false;
input bool                 InpExportOnEveryNewBar   = false;
input bool                 InpExportOnDeinit        = true;
input bool                 InpIncludeUnmaturedRows  = false;
input bool                 InpRestrictToObservedBars = true;
input int                  InpHorizon1              = 3;
input int                  InpHorizon2              = 6;
input int                  InpHorizon3              = 12;
input int                  InpHorizon4              = 24;
input int                  InpHorizon5              = 48;

//+------------------------------------------------------------------+
//| Mirrored indicator inputs                                         |
//+------------------------------------------------------------------+
input ENUM_WPVS_SIGNAL_BAR InpSignalBar             = WPVS_CLOSED_BAR_ONLY;
input int                  InpVolumeLookback        = 20;
input double               InpVolumeMultiplier      = 1.80;
input long                 InpMinBarVolume          = 50;
input int                  InpPivotLookback         = 8;
input int                  InpPivotTolerancePoints  = 5;
input double               InpMinWickToRange        = 0.35;
input double               InpClosePosition         = 0.55;
input bool                 InpRequireCandleColor    = true;
input bool                 InpUseATRRangeFilter     = true;
input int                  InpATRPeriod             = 14;
input double               InpMinRangeATR           = 0.35;
input int                  InpWaveletWindow         = 48;
input int                  InpWaveletLevel          = 3;
input double               InpMinWaveletEnergy      = 0.10;
input double               InpMaxNoiseRatio         = 0.78;
input bool                 InpUseTrendBias          = false;
input int                  InpTrendLookback         = 32;
input int                  InpMaxSpreadPoints       = 0;
input bool                 InpUseSessionFilter      = false;
input int                  InpSessionStartHour      = 7;
input int                  InpSessionEndHour        = 18;
input int                  InpMaxBarsToProcess      = 500000;
input bool                 InpEnableAlerts          = false;
input double               InpMinSignalScore        = 0.55;
input bool                 InpEnableStructureClass  = true;
input bool                 InpAllowBuyHL            = true;
input bool                 InpAllowBuyLL            = false;
input bool                 InpAllowSellHH           = true;
input bool                 InpAllowSellLH           = false;
input int                  InpStructureLookback     = 80;
input int                  InpArrowOffsetPoints     = 10;

//+------------------------------------------------------------------+
//| Globals                                                           |
//+------------------------------------------------------------------+
int      g_indicator_handle = INVALID_HANDLE;
int      g_atr_handle       = INVALID_HANDLE;
datetime g_last_bar_time    = 0;
datetime g_first_seen_time   = 0;
datetime g_last_seen_time    = 0;

//+------------------------------------------------------------------+
//| Helpers                                                           |
//+------------------------------------------------------------------+
int MaxInt(const int a,const int b)
  {
   return (a > b ? a : b);
  }

int MinInt(const int a,const int b)
  {
   return (a < b ? a : b);
  }

string DirectionText(const double state)
  {
   if(state > 0.0)
      return "BUY";
   if(state < 0.0)
      return "SELL";
   return "NONE";
  }

string StructureText(const double structure_value)
  {
   if(structure_value == EMPTY_VALUE)
      return "";

   int v = (int)MathRound(structure_value);
   if(v == 0)
      return "HH";
   if(v == 1)
      return "HL";
   if(v == 2)
      return "LH";
   if(v == 3)
      return "LL";
   return "";
  }

string SafeFileName()
  {
   string file_name = InpCsvFileName;
   if(StringLen(file_name) <= 0)
      file_name = "Hybrid_WPVS_Diagnostic.csv";

   if(!InpAutoTagCsvBySymbol)
      return file_name;

   string tag = "_" + _Symbol + "_" + EnumToString((ENUM_TIMEFRAMES)_Period);
   int dot = StringFind(file_name, ".csv");
   if(dot < 0)
      dot = StringFind(file_name, ".CSV");

   if(dot >= 0)
      return StringSubstr(file_name, 0, dot) + tag + StringSubstr(file_name, dot);

   return file_name + tag + ".csv";
  }

int MaxHorizon()
  {
   int h = 0;
   h = MaxInt(h, InpHorizon1);
   h = MaxInt(h, InpHorizon2);
   h = MaxInt(h, InpHorizon3);
   h = MaxInt(h, InpHorizon4);
   h = MaxInt(h, InpHorizon5);
   return h;
  }

void TrackObservedBar(const datetime bar_time)
  {
   if(bar_time == 0)
      return;

   if(g_first_seen_time == 0 || bar_time < g_first_seen_time)
      g_first_seen_time = bar_time;

   if(g_last_seen_time == 0 || bar_time > g_last_seen_time)
      g_last_seen_time = bar_time;
  }

bool InObservedExportWindow(const datetime bar_time)
  {
   if(!InpRestrictToObservedBars)
      return true;

   if(g_first_seen_time == 0 || g_last_seen_time == 0)
      return true;

   return (bar_time >= g_first_seen_time && bar_time <= g_last_seen_time);
  }

string ReturnPointsString(const int signal_shift,
                          const int horizon,
                          const int direction,
                          const MqlRates &rates[])
  {
   if(horizon <= 0)
      return "";

   int future_shift = signal_shift - horizon;
   if(future_shift < 1)
      return ""; // Keep forward return based on closed bars only.

   double raw_points = (rates[future_shift].close - rates[signal_shift].close) / _Point;
   double signed_points = raw_points * (double)direction;
   return DoubleToString(signed_points, 1);
  }

string ReturnRawPointsString(const int signal_shift,
                             const int horizon,
                             const MqlRates &rates[])
  {
   if(horizon <= 0)
      return "";

   int future_shift = signal_shift - horizon;
   if(future_shift < 1)
      return "";

   double raw_points = (rates[future_shift].close - rates[signal_shift].close) / _Point;
   return DoubleToString(raw_points, 1);
  }

bool CopyIndicatorBuffers(const int bars,
                          double &buy_signal[],
                          double &sell_signal[],
                          double &signal_state[],
                          double &signal_score[],
                          double &volume_ratio[],
                          double &wavelet_regime[],
                          double &structure_class[],
                          double &debug_reason[])
  {
   ArraySetAsSeries(buy_signal,      true);
   ArraySetAsSeries(sell_signal,     true);
   ArraySetAsSeries(signal_state,    true);
   ArraySetAsSeries(signal_score,    true);
   ArraySetAsSeries(volume_ratio,    true);
   ArraySetAsSeries(wavelet_regime,  true);
   ArraySetAsSeries(structure_class, true);
   ArraySetAsSeries(debug_reason,    true);

   ResetLastError();
   if(CopyBuffer(g_indicator_handle, 0, 0, bars, buy_signal) <= 0)
     {
      PrintFormat("CopyBuffer BuySignal failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 1, 0, bars, sell_signal) <= 0)
     {
      PrintFormat("CopyBuffer SellSignal failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 2, 0, bars, signal_state) <= 0)
     {
      PrintFormat("CopyBuffer SignalState failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 3, 0, bars, signal_score) <= 0)
     {
      PrintFormat("CopyBuffer SignalScore failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 4, 0, bars, volume_ratio) <= 0)
     {
      PrintFormat("CopyBuffer VolumeRatio failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 5, 0, bars, wavelet_regime) <= 0)
     {
      PrintFormat("CopyBuffer WaveletRegime failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 6, 0, bars, structure_class) <= 0)
     {
      PrintFormat("CopyBuffer StructureClass failed. error=%d", GetLastError());
      return false;
     }
   if(CopyBuffer(g_indicator_handle, 7, 0, bars, debug_reason) <= 0)
     {
      PrintFormat("CopyBuffer DebugReasonCode failed. error=%d", GetLastError());
      return false;
     }

   return true;
  }

bool CopyAtrBuffer(const int bars,double &atr_buffer[])
  {
   ArraySetAsSeries(atr_buffer, true);
   if(g_atr_handle == INVALID_HANDLE)
      return false;

   ResetLastError();
   int copied = CopyBuffer(g_atr_handle, 0, 0, bars, atr_buffer);
   if(copied <= 0)
     {
      PrintFormat("CopyBuffer ATR failed. error=%d", GetLastError());
      return false;
     }
   return true;
  }

void WriteCsvHeader(const int file_handle)
  {
   FileWrite(file_handle,
             "symbol",
             "timeframe",
             "bar_time",
             "direction",
             "signal_state",
             "score",
             "volume_ratio",
             "wavelet_regime",
             "structure_class",
             "debug_reason_code",
             "spread_points",
             "atr",
             "close_price",
             "buy_signal_price",
             "sell_signal_price",
             "ret_signed_points_h" + IntegerToString(InpHorizon1),
             "ret_raw_points_h"    + IntegerToString(InpHorizon1),
             "ret_signed_points_h" + IntegerToString(InpHorizon2),
             "ret_raw_points_h"    + IntegerToString(InpHorizon2),
             "ret_signed_points_h" + IntegerToString(InpHorizon3),
             "ret_raw_points_h"    + IntegerToString(InpHorizon3),
             "ret_signed_points_h" + IntegerToString(InpHorizon4),
             "ret_raw_points_h"    + IntegerToString(InpHorizon4),
             "ret_signed_points_h" + IntegerToString(InpHorizon5),
             "ret_raw_points_h"    + IntegerToString(InpHorizon5));
  }

bool ExportDiagnostics(const string reason)
  {
   if(g_indicator_handle == INVALID_HANDLE)
     {
      Print("Diagnostic export skipped: indicator handle is invalid.");
      return false;
     }

   int terminal_bars = Bars(_Symbol, _Period);
   int bars = MinInt(MathMax(100, InpBarsToScan), terminal_bars);
   if(bars <= MaxHorizon() + 5)
     {
      PrintFormat("Diagnostic export skipped: not enough bars. bars=%d maxHorizon=%d", bars, MaxHorizon());
      return false;
     }

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   ResetLastError();
   int copied_rates = CopyRates(_Symbol, _Period, 0, bars, rates);
   if(copied_rates <= MaxHorizon() + 5)
     {
      PrintFormat("CopyRates failed or insufficient. copied=%d error=%d", copied_rates, GetLastError());
      return false;
     }
   bars = copied_rates;

   double buy_signal[];
   double sell_signal[];
   double signal_state[];
   double signal_score[];
   double volume_ratio[];
   double wavelet_regime[];
   double structure_class[];
   double debug_reason[];
   double atr_buffer[];

   if(!CopyIndicatorBuffers(bars,
                            buy_signal,
                            sell_signal,
                            signal_state,
                            signal_score,
                            volume_ratio,
                            wavelet_regime,
                            structure_class,
                            debug_reason))
      return false;

   bool atr_ok = CopyAtrBuffer(bars, atr_buffer);

   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;

   string file_name = SafeFileName();
   ushort comma_character = StringGetCharacter(",", 0);
   ResetLastError();
   int file_handle = FileOpen(file_name, flags, (short)comma_character);
   if(file_handle == INVALID_HANDLE)
     {
      PrintFormat("FileOpen failed for %s. error=%d", file_name, GetLastError());
      return false;
     }

   WriteCsvHeader(file_handle);

   int rows = 0;
   int max_horizon = MaxHorizon();

   // Oldest to newest, closed bars only. Shift 0 is never exported as a signal row.
   for(int i = bars - 1; i >= 1; i--)
     {
      double state = signal_state[i];
      if(MathAbs(state) < 0.5)
         continue;

      if(!InObservedExportWindow(rates[i].time))
         continue;

      if(!InpIncludeUnmaturedRows && i - max_horizon < 1)
         continue;

      int direction = (state > 0.0 ? 1 : -1);
      string r1_signed = ReturnPointsString(i, InpHorizon1, direction, rates);
      string r1_raw    = ReturnRawPointsString(i, InpHorizon1, rates);
      string r2_signed = ReturnPointsString(i, InpHorizon2, direction, rates);
      string r2_raw    = ReturnRawPointsString(i, InpHorizon2, rates);
      string r3_signed = ReturnPointsString(i, InpHorizon3, direction, rates);
      string r3_raw    = ReturnRawPointsString(i, InpHorizon3, rates);
      string r4_signed = ReturnPointsString(i, InpHorizon4, direction, rates);
      string r4_raw    = ReturnRawPointsString(i, InpHorizon4, rates);
      string r5_signed = ReturnPointsString(i, InpHorizon5, direction, rates);
      string r5_raw    = ReturnRawPointsString(i, InpHorizon5, rates);

      double atr_value = (atr_ok ? atr_buffer[i] : 0.0);
      string buy_price = (buy_signal[i] == EMPTY_VALUE ? "" : DoubleToString(buy_signal[i], _Digits));
      string sell_price = (sell_signal[i] == EMPTY_VALUE ? "" : DoubleToString(sell_signal[i], _Digits));

      FileWrite(file_handle,
                _Symbol,
                EnumToString((ENUM_TIMEFRAMES)_Period),
                TimeToString(rates[i].time, TIME_DATE | TIME_SECONDS),
                DirectionText(state),
                DoubleToString(state, 0),
                DoubleToString(signal_score[i], 6),
                DoubleToString(volume_ratio[i], 6),
                DoubleToString(wavelet_regime[i], 0),
                StructureText(structure_class[i]),
                DoubleToString(debug_reason[i], 0),
                IntegerToString((int)rates[i].spread),
                DoubleToString(atr_value, _Digits),
                DoubleToString(rates[i].close, _Digits),
                buy_price,
                sell_price,
                r1_signed,
                r1_raw,
                r2_signed,
                r2_raw,
                r3_signed,
                r3_raw,
                r4_signed,
                r4_raw,
                r5_signed,
                r5_raw);
      rows++;
     }

   FileFlush(file_handle);
   FileClose(file_handle);

   PrintFormat("Hybrid_WPVS diagnostic export complete: %s rows=%d reason=%s common=%s",
               file_name,
               rows,
               reason,
               (InpUseCommonFiles ? "true" : "false"));
   return true;
  }

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   ResetLastError();
   g_indicator_handle = iCustom(_Symbol,
                                _Period,
                                InpIndicatorName,
                                InpSignalBar,
                                InpVolumeLookback,
                                InpVolumeMultiplier,
                                InpMinBarVolume,
                                InpPivotLookback,
                                InpPivotTolerancePoints,
                                InpMinWickToRange,
                                InpClosePosition,
                                InpRequireCandleColor,
                                InpUseATRRangeFilter,
                                InpATRPeriod,
                                InpMinRangeATR,
                                InpWaveletWindow,
                                InpWaveletLevel,
                                InpMinWaveletEnergy,
                                InpMaxNoiseRatio,
                                InpUseTrendBias,
                                InpTrendLookback,
                                InpMaxSpreadPoints,
                                InpUseSessionFilter,
                                InpSessionStartHour,
                                InpSessionEndHour,
                                InpMaxBarsToProcess,
                                InpEnableAlerts,
                                InpMinSignalScore,
                                InpEnableStructureClass,
                                InpAllowBuyHL,
                                InpAllowBuyLL,
                                InpAllowSellHH,
                                InpAllowSellLH,
                                InpStructureLookback,
                                InpArrowOffsetPoints);

   if(g_indicator_handle == INVALID_HANDLE)
     {
      PrintFormat("iCustom failed for %s. error=%d", InpIndicatorName, GetLastError());
      return INIT_FAILED;
     }

   ResetLastError();
   g_atr_handle = iATR(_Symbol, _Period, InpATRPeriod);
   if(g_atr_handle == INVALID_HANDLE)
      PrintFormat("iATR failed. ATR column will be zero. error=%d", GetLastError());

   g_last_bar_time = iTime(_Symbol, _Period, 0);
   TrackObservedBar(g_last_bar_time);

   if(InpExportOnInit)
      ExportDiagnostics("init");

   Print("Hybrid_WPVS_DiagnosticEA initialized. This EA does not place trades.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(InpExportOnDeinit)
      ExportDiagnostics("deinit_" + IntegerToString(reason));

   if(g_indicator_handle != INVALID_HANDLE)
     {
      IndicatorRelease(g_indicator_handle);
      g_indicator_handle = INVALID_HANDLE;
     }

   if(g_atr_handle != INVALID_HANDLE)
     {
      IndicatorRelease(g_atr_handle);
      g_atr_handle = INVALID_HANDLE;
     }
  }

//+------------------------------------------------------------------+
//| Expert tick                                                       |
//+------------------------------------------------------------------+
void OnTick()
  {
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == 0)
      return;

   TrackObservedBar(current_bar_time);

   if(current_bar_time != g_last_bar_time)
     {
      g_last_bar_time = current_bar_time;
      TrackObservedBar(current_bar_time);
      if(InpExportOnEveryNewBar)
         ExportDiagnostics("new_bar");
     }
  }
//+------------------------------------------------------------------+
