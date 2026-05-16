//+------------------------------------------------------------------+
//| Hybrid_WPVS_Top3_ExecutionEA.mq5                                 |
//| Closed-bar execution harness for top-3 Hybrid WPVS candidates.    |
//+------------------------------------------------------------------+
#property copyright "OpenAI / user-specified project"
#property version   "1.10"
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
input string               InpTradeSymbols          = "GBPUSD,AUDUSD,USDJPY";
input long                 InpMagicNumber           = 26051080;
input bool                 InpUseAutoSymbolMagic    = true;
input bool                 InpAllowTrading          = false;
input bool                 InpAllowPositionManagement = false;
input bool                 InpDemoAccountsOnly      = true;
input double               InpTradeMinSignalScore   = 0.80;
input double               InpFixedLots             = 0.01;
input int                  InpExitAfterBars         = 24;
input bool                 InpCloseOnOppositeSignal = false;
input int                  InpMaxSpreadPointsTrade  = 30;
input int                  InpMaxTradesPerDay       = 3;
input double               InpMaxDailyLossMoney     = 25.00;
input int                  InpDeviationPoints       = 10;
input bool                 InpForceFokFilling       = true;
input bool                 InpUseAtrStop            = true;
input double               InpStopAtrMultiple       = 2.50;
input bool                 InpUseAtrTakeProfit      = false;
input double               InpTakeProfitAtrMultiple = 3.00;
input bool                 InpLogSignals            = true;
input bool                 InpUseCommonFiles        = true;
input string               InpSignalLogFileName     = "Hybrid_WPVS_LIVE_SIGNAL_LOG.csv";

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
datetime g_day_start_time   = 0;
double   g_day_start_equity = 0.0;
long     g_effective_magic  = 0;

//+------------------------------------------------------------------+
//| Helpers                                                           |
//+------------------------------------------------------------------+
string TrimString(string value)
  {
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
  }

bool SymbolInList(const string csv_list,const string symbol)
  {
   string items[];
   int count = StringSplit(csv_list, ',', items);
   for(int i = 0; i < count; i++)
     {
      string item = TrimString(items[i]);
      if(item == symbol)
         return true;
     }
   return false;
  }

bool IsAllowedSymbol()
  {
   return SymbolInList(InpAllowedSymbols, _Symbol);
  }

bool IsTradeSymbol()
  {
   return SymbolInList(InpTradeSymbols, _Symbol);
  }

long SymbolMagicOffset()
  {
   uint hash = 0;
   int length = StringLen(_Symbol);
   for(int i = 0; i < length; i++)
      hash = (hash * 131) + (uint)StringGetCharacter(_Symbol, i);

   return (long)(hash % 100000);
  }

datetime StartOfDay(const datetime value)
  {
   MqlDateTime parts;
   TimeToStruct(value, parts);
   parts.hour = 0;
   parts.min = 0;
   parts.sec = 0;
   return StructToTime(parts);
  }

void RefreshDailyWindow()
  {
   datetime now = TimeCurrent();
   datetime day_start = StartOfDay(now);
   if(g_day_start_time == day_start)
      return;

   g_day_start_time = day_start;
   g_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   PrintFormat("Daily guard reset on %s. start_equity=%.2f",
               TimeToString(g_day_start_time, TIME_DATE),
               g_day_start_equity);
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

string DirectionText(const int direction)
  {
   if(direction > 0)
      return "BUY";
   if(direction < 0)
      return "SELL";
   return "NONE";
  }

bool IsTester()
  {
   return (bool)MQLInfoInteger(MQL_TESTER);
  }

string AccountTradeModeText()
  {
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode == ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO";
   if(mode == ACCOUNT_TRADE_MODE_REAL)
      return "REAL";
   if(mode == ACCOUNT_TRADE_MODE_CONTEST)
      return "CONTEST";
   return "UNKNOWN";
  }

string StructureClassText(const double value)
  {
   if(value == EMPTY_VALUE)
      return "";

   int structure = (int)MathRound(value);
   if(structure == 0)
      return "HH";
   if(structure == 1)
      return "HL";
   if(structure == 2)
      return "LH";
   if(structure == 3)
      return "LL";
   return IntegerToString(structure);
  }

string NumericText(const double value,const int digits)
  {
   if(value == EMPTY_VALUE)
      return "";
   return DoubleToString(value, digits);
  }

int OwnOpenPositionCount()
  {
   int count = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != g_effective_magic)
         continue;
      count++;
     }
   return count;
  }

int TodaysEntryCount()
  {
   RefreshDailyWindow();
   if(!HistorySelect(g_day_start_time, TimeCurrent()))
      return 0;

   int count = 0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != g_effective_magic)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      count++;
     }
   return count;
  }

bool TradeGateAllows(const int direction,const double score,string &block_reason)
  {
   block_reason = "allowed";
   RefreshDailyWindow();

   if(direction == 0)
     {
      block_reason = "no_signal";
      return false;
     }
   if(score < InpTradeMinSignalScore)
     {
      block_reason = "shadow_score";
      return false;
     }
   if(!IsTradeSymbol())
     {
      block_reason = "research_symbol";
      return false;
     }
   if(!InpAllowTrading)
     {
      block_reason = "allow_trading_false";
      return false;
     }
   if(InpDemoAccountsOnly && !IsTester() && AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
     {
      block_reason = "not_demo_account";
      return false;
     }
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0 || AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) == 0)
     {
      block_reason = "terminal_or_account_trade_disabled";
      return false;
     }
   if(!SpreadAllowsTrade())
     {
      block_reason = "spread_too_high";
      return false;
     }
   if(InpMaxTradesPerDay > 0 && TodaysEntryCount() >= InpMaxTradesPerDay)
     {
      block_reason = "max_trades_per_day";
      return false;
     }
   if(InpMaxDailyLossMoney > 0.0 && g_day_start_equity > 0.0)
     {
      double equity_loss = g_day_start_equity - AccountInfoDouble(ACCOUNT_EQUITY);
      if(equity_loss >= InpMaxDailyLossMoney)
        {
         block_reason = "daily_loss_cutoff";
         return false;
        }
     }
   if(OwnOpenPositionCount() > 0)
     {
      block_reason = "own_position_exists";
      return false;
     }

   return true;
  }

void LogSignalEvent(const int direction,
                    const double score,
                    const double volume_ratio,
                    const double wavelet_regime,
                    const double structure_class,
                    const double debug_reason,
                    const bool trade_allowed,
                    const string block_reason,
                    const ulong ticket)
  {
   if(!InpLogSignals)
      return;

   int flags = FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;

   ResetLastError();
   int handle = FileOpen(InpSignalLogFileName, flags, ',');
   if(handle == INVALID_HANDLE)
     {
      PrintFormat("Signal log open failed: %s error=%d", InpSignalLogFileName, GetLastError());
      return;
     }

   bool write_header = (FileSize(handle) == 0);
   FileSeek(handle, 0, SEEK_END);
   if(write_header)
     {
      FileWrite(handle,
                "server_time",
                "signal_bar_time",
                "account_login",
                "account_mode",
                "symbol",
                "timeframe",
                "magic",
                "direction",
                "score",
                "trade_min_score",
                "spread_points",
                "volume_ratio",
                "wavelet_regime",
                "structure_class",
                "debug_reason",
                "trade_allowed",
                "block_reason",
                "ticket");
     }

   datetime signal_time = iTime(_Symbol, _Period, 1);
   FileWrite(handle,
             TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
             TimeToString(signal_time, TIME_DATE | TIME_SECONDS),
             (long)AccountInfoInteger(ACCOUNT_LOGIN),
             AccountTradeModeText(),
             _Symbol,
             EnumToString((ENUM_TIMEFRAMES)_Period),
             g_effective_magic,
             DirectionText(direction),
             DoubleToString(score, 4),
             DoubleToString(InpTradeMinSignalScore, 4),
             CurrentSpreadPoints(),
             NumericText(volume_ratio, 4),
             NumericText(wavelet_regime, 0),
             StructureClassText(structure_class),
             NumericText(debug_reason, 0),
             (trade_allowed ? "true" : "false"),
             block_reason,
             (long)ticket);

   FileClose(handle);
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

double OptionalBufferValue(const int buffer_index,const int shift)
  {
   double value = EMPTY_VALUE;
   if(!CopyOneBufferValue(buffer_index, shift, value))
      return EMPTY_VALUE;
   return value;
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
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != g_effective_magic)
         continue;
      return true;
     }
   return false;
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

bool OpenSignalPosition(const int direction,const double score,ulong &ticket)
  {
   ticket = 0;
   if(direction == 0)
      return false;

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
      ticket = g_trade.ResultDeal();
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
   if(!InpAllowPositionManagement)
      return;

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
   if(signal_direction == 0)
      return;

   double volume_ratio = OptionalBufferValue(4, 1);
   double wavelet_regime = OptionalBufferValue(5, 1);
   double structure_class = OptionalBufferValue(6, 1);
   double debug_reason = OptionalBufferValue(7, 1);

   string block_reason = "";
   bool gate_allowed = TradeGateAllows(signal_direction, score, block_reason);
   bool trade_executed = false;
   ulong ticket = 0;
   if(gate_allowed)
      trade_executed = OpenSignalPosition(signal_direction, score, ticket);
   if(trade_executed)
      block_reason = "executed";
   else if(gate_allowed)
      block_reason = "order_send_failed";
   else if(block_reason == "")
      block_reason = "order_send_failed";

   LogSignalEvent(signal_direction,
                  score,
                  volume_ratio,
                  wavelet_regime,
                  structure_class,
                  debug_reason,
                  trade_executed,
                  block_reason,
                  ticket);
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

   g_effective_magic = InpMagicNumber;
   if(InpUseAutoSymbolMagic)
      g_effective_magic += SymbolMagicOffset();

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

   g_trade.SetExpertMagicNumber(g_effective_magic);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   if(InpForceFokFilling)
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else
      g_trade.SetTypeFillingBySymbol(_Symbol);

   RefreshDailyWindow();
   g_last_bar_time = iTime(_Symbol, _Period, 0);
   PrintFormat("Hybrid_WPVS_Top3_ExecutionEA initialized on %s %s magic=%d allow_trading=%s trade_symbols=%s account_mode=%s",
               _Symbol,
               EnumToString((ENUM_TIMEFRAMES)_Period),
               g_effective_magic,
               (InpAllowTrading ? "true" : "false"),
               InpTradeSymbols,
               AccountTradeModeText());
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
