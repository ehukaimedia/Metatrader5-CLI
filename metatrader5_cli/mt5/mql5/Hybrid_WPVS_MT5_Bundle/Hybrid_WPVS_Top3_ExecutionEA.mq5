//+------------------------------------------------------------------+
//| Hybrid_WPVS_Top3_ExecutionEA.mq5                                 |
//| Closed-bar execution harness for top-3 Hybrid WPVS candidates.    |
//+------------------------------------------------------------------+
#property copyright "OpenAI / user-specified project"
#property version   "1.00"
#property tester_indicator "Hybrid_Wavelet_Pivot_Volume_Spike.ex5"

#include <Trade/Trade.mqh>

//+------------------------------------------------------------------+
//| Indicator input enum mirror                                       |
//+------------------------------------------------------------------+
enum ENUM_WPVS_SIGNAL_BAR
  {
   WPVS_CURRENT_BAR_VISUAL_ONLY = 0,
   WPVS_CLOSED_BAR_ONLY         = 1
  };

//+------------------------------------------------------------------+
//| Execution inputs                                                  |
//+------------------------------------------------------------------+
input string               InpAllowedSymbols        = "GBPUSD,AUDUSD,USDJPY";
input long                 InpMagicNumber           = 26051080;
input double               InpFixedLots             = 0.01;
input int                  InpExitAfterBars         = 24;
input bool                 InpCloseOnOppositeSignal = false;
input int                  InpMaxSpreadPointsTrade  = 0;
input int                  InpDeviationPoints       = 20;
input bool                 InpUseAtrStop            = true;
input double               InpStopAtrMultiple       = 2.50;
input bool                 InpUseAtrTakeProfit      = false;
input double               InpTakeProfitAtrMultiple = 3.00;

//+------------------------------------------------------------------+
//| Mirrored indicator inputs                                         |
//+------------------------------------------------------------------+
input string               InpIndicatorName         = "Hybrid_Wavelet_Pivot_Volume_Spike";
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
input double               InpMinSignalScore        = 0.80;
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
CTrade   g_trade;
int      g_indicator_handle = INVALID_HANDLE;
int      g_atr_handle       = INVALID_HANDLE;
datetime g_last_bar_time    = 0;

//+------------------------------------------------------------------+
//| Helpers                                                           |
//+------------------------------------------------------------------+
string TrimString(string value)
  {
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
  }

bool IsAllowedSymbol()
  {
   string items[];
   int count = StringSplit(InpAllowedSymbols, ',', items);
   for(int i = 0; i < count; i++)
     {
      string item = TrimString(items[i]);
      if(item == _Symbol)
         return true;
     }
   return false;
  }

int CurrentSpreadPoints()
  {
   long spread = 0;
   if(!SymbolInfoInteger(_Symbol, SYMBOL_SPREAD, spread))
      return 0;
   return (int)spread;
  }

bool SpreadAllowsTrade()
  {
   if(InpMaxSpreadPointsTrade <= 0)
      return true;
   return CurrentSpreadPoints() <= InpMaxSpreadPointsTrade;
  }

double NormalizeLots(const double lots)
  {
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(step <= 0.0)
      step = 0.01;

   double normalized = MathFloor(lots / step) * step;
   normalized = MathMax(min_lot, MathMin(max_lot, normalized));
   return NormalizeDouble(normalized, 2);
  }

bool CopyOneBufferValue(const int buffer_index,const int shift,double &value)
  {
   double data[];
   ArraySetAsSeries(data, true);

   ResetLastError();
   int copied = CopyBuffer(g_indicator_handle, buffer_index, shift, 1, data);
   if(copied != 1)
     {
      PrintFormat("CopyBuffer index=%d shift=%d failed. copied=%d error=%d",
                  buffer_index,
                  shift,
                  copied,
                  GetLastError());
      return false;
     }

   value = data[0];
   return true;
  }

bool CopyAtrValue(const int shift,double &atr)
  {
   atr = 0.0;
   if(g_atr_handle == INVALID_HANDLE)
      return false;

   double data[];
   ArraySetAsSeries(data, true);

   ResetLastError();
   int copied = CopyBuffer(g_atr_handle, 0, shift, 1, data);
   if(copied != 1)
     {
      PrintFormat("CopyBuffer ATR shift=%d failed. copied=%d error=%d",
                  shift,
                  copied,
                  GetLastError());
      return false;
     }

   atr = data[0];
   return atr > 0.0;
  }

bool SelectOwnPosition()
  {
   if(!PositionSelect(_Symbol))
      return false;

   long magic = (long)PositionGetInteger(POSITION_MAGIC);
   return magic == InpMagicNumber;
  }

int OwnPositionType()
  {
   if(!SelectOwnPosition())
      return -1;
   return (int)PositionGetInteger(POSITION_TYPE);
  }

int PositionAgeBars()
  {
   if(!SelectOwnPosition())
      return -1;

   datetime entry_time = (datetime)PositionGetInteger(POSITION_TIME);
   int shift = iBarShift(_Symbol, _Period, entry_time, false);
   if(shift < 0)
      return -1;

   return shift;
  }

bool CloseOwnPosition(const string reason)
  {
   if(!SelectOwnPosition())
      return true;

   ResetLastError();
   if(g_trade.PositionClose(_Symbol))
     {
      PrintFormat("Closed %s position on %s. reason=%s",
                  _Symbol,
                  EnumToString((ENUM_TIMEFRAMES)_Period),
                  reason);
      return true;
     }

   PrintFormat("PositionClose failed. retcode=%d error=%d reason=%s",
               g_trade.ResultRetcode(),
               GetLastError(),
               reason);
   return false;
  }

void BuildStops(const int direction,double &sl,double &tp)
  {
   sl = 0.0;
   tp = 0.0;

   double atr = 0.0;
   if(!CopyAtrValue(1, atr))
      return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double entry = (direction > 0 ? ask : bid);
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freeze_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double min_distance = (MathMax(stops_level, freeze_level) + 2) * _Point;

   if(InpUseAtrStop && InpStopAtrMultiple > 0.0)
     {
      if(direction > 0)
         sl = MathMin(entry - (atr * InpStopAtrMultiple), bid - min_distance);
      else
         sl = MathMax(entry + (atr * InpStopAtrMultiple), ask + min_distance);
      sl = NormalizeDouble(sl, _Digits);
     }

   if(InpUseAtrTakeProfit && InpTakeProfitAtrMultiple > 0.0)
     {
      if(direction > 0)
         tp = MathMax(entry + (atr * InpTakeProfitAtrMultiple), ask + min_distance);
      else
         tp = MathMin(entry - (atr * InpTakeProfitAtrMultiple), bid - min_distance);
      tp = NormalizeDouble(tp, _Digits);
     }
  }

bool OpenSignalPosition(const int direction,const double score)
  {
   if(direction == 0)
      return false;

   if(!SpreadAllowsTrade())
     {
      PrintFormat("Signal skipped: spread=%d max=%d",
                  CurrentSpreadPoints(),
                  InpMaxSpreadPointsTrade);
      return false;
     }

   double lots = NormalizeLots(InpFixedLots);
   double sl = 0.0;
   double tp = 0.0;
   BuildStops(direction, sl, tp);

   ResetLastError();
   bool ok = false;
   if(direction > 0)
      ok = g_trade.Buy(lots, _Symbol, 0.0, sl, tp, "WPVS top3 buy");
   else
      ok = g_trade.Sell(lots, _Symbol, 0.0, sl, tp, "WPVS top3 sell");

   if(ok)
     {
      PrintFormat("Opened %s lots=%.2f score=%.4f sl=%s tp=%s",
                  (direction > 0 ? "BUY" : "SELL"),
                  lots,
                  score,
                  (sl > 0.0 ? DoubleToString(sl, _Digits) : "none"),
                  (tp > 0.0 ? DoubleToString(tp, _Digits) : "none"));
      return true;
     }

   PrintFormat("Order send failed direction=%d lots=%.2f score=%.4f retcode=%d error=%d",
               direction,
               lots,
               score,
               g_trade.ResultRetcode(),
               GetLastError());
   return false;
  }

void ManageOpenPosition(const int signal_direction)
  {
   int age = PositionAgeBars();
   if(age >= InpExitAfterBars && InpExitAfterBars > 0)
     {
      CloseOwnPosition("time_exit_" + IntegerToString(InpExitAfterBars));
      return;
     }

   if(!InpCloseOnOppositeSignal || signal_direction == 0)
      return;

   int pos_type = OwnPositionType();
   if(pos_type == POSITION_TYPE_BUY && signal_direction < 0)
      CloseOwnPosition("opposite_sell_signal");
   else if(pos_type == POSITION_TYPE_SELL && signal_direction > 0)
      CloseOwnPosition("opposite_buy_signal");
  }

void ProcessClosedBar()
  {
   double state = 0.0;
   double score = 0.0;

   if(!CopyOneBufferValue(2, 1, state))
      return;
   if(!CopyOneBufferValue(3, 1, score))
      return;

   int signal_direction = 0;
   if(state > 0.0)
      signal_direction = 1;
   else if(state < 0.0)
      signal_direction = -1;

   ManageOpenPosition(signal_direction);
   if(SelectOwnPosition())
      return;

   if(signal_direction == 0)
      return;

   OpenSignalPosition(signal_direction, score);
  }

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(!IsAllowedSymbol())
     {
      PrintFormat("Hybrid_WPVS_Top3_ExecutionEA disabled on %s. Allowed symbols: %s",
                  _Symbol,
                  InpAllowedSymbols);
      return INIT_PARAMETERS_INCORRECT;
     }

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
      PrintFormat("iATR failed. ATR stops will be disabled. error=%d", GetLastError());

   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);

   g_last_bar_time = iTime(_Symbol, _Period, 0);
   PrintFormat("Hybrid_WPVS_Top3_ExecutionEA initialized on %s %s",
               _Symbol,
               EnumToString((ENUM_TIMEFRAMES)_Period));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_indicator_handle != INVALID_HANDLE)
      IndicatorRelease(g_indicator_handle);
   if(g_atr_handle != INVALID_HANDLE)
      IndicatorRelease(g_atr_handle);
  }

//+------------------------------------------------------------------+
//| Expert tick                                                       |
//+------------------------------------------------------------------+
void OnTick()
  {
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == 0)
      return;

   if(current_bar_time == g_last_bar_time)
      return;

   g_last_bar_time = current_bar_time;
   ProcessClosedBar();
  }
//+------------------------------------------------------------------+
