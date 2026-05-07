//+------------------------------------------------------------------+
//|                                             AdaptiveTrailEA.mq5   |
//|                                      Copyright 2026, Ehukai       |
//|                                      https://github.com/ehukai    |
//|                                      Version 1.0                  |
//| Broker- and instrument-agnostic post-fill trade manager: BE move  |
//| + Chandelier trail, magic-scoped                                  |
//+------------------------------------------------------------------+
// USAGE
// 1. Compile in MetaEditor (0 errors / 0 warnings expected)
// 2. Attach to ANY chart with Algo Trading enabled. The EA will manage
//    every open position whose magic matches MagicNumbers, regardless of
//    which symbol's chart it is attached to. One instance per terminal
//    is sufficient.
// 3. Per-instrument tuning is done via MT5 .set preset files saved
//    alongside this EA. Suggested defaults:
//      EURUSD: BE_Trigger_Points=80, Chandelier_ATR_Multiplier=3.0,  Max_Spread_Points=20
//      USDJPY: BE_Trigger_Points=80, Chandelier_ATR_Multiplier=2.5,  Max_Spread_Points=15
//      XAUUSD: BE_Trigger_Points=300, Chandelier_ATR_Multiplier=3.5, Max_Spread_Points=80
//      NAS100: BE_Trigger_Points=200, Chandelier_ATR_Multiplier=3.0, Max_Spread_Points=200
// 4. Verify by opening a small demo position with one of MagicNumbers
//    and watching the Experts tab.
// 5. Verify magic isolation: open a separate position with a DIFFERENT
//    magic and confirm the EA never touches it.
// 6. Optional runner mode: set Allow_TP_Removal=true to remove an existing
//    TP after BE is armed when price comes within TP_Removal_Distance_Points
//    of TP. MT5 cannot run past a broker-side TP unless it is removed first.
// 7. Manual magic 0 is ignored by default. To manage manual trades, explicitly
//    enable Allow_Manual_Magic_0 and list exact symbols in Manual_Magic_0_Symbols.

#property strict
#property copyright "Copyright 2026, Ehukai"
#property link      "https://github.com/ehukai"
#property version   "1.0"
#property description "Broker- and instrument-agnostic post-fill trade manager: BE move + Chandelier trail, magic-scoped"

input group "Magic Scope"
input string                  MagicNumbers                 = "113054";          // Comma-separated magics this EA manages
input bool                    Allow_Manual_Magic_0         = false;             // Opt-in manual-trade management by symbol whitelist
input string                  Manual_Magic_0_Symbols       = "";                // Comma-separated symbols allowed for magic 0

input group "Breakeven"
input int                     BE_Trigger_Points            = 80;                // Profit in points that triggers the BE move
input int                     BE_Buffer_Points             = 5;                 // Points beyond entry where SL parks at BE

input group "Chandelier"
input int                     Chandelier_ATR_Period        = 22;                // ATR period
input double                  Chandelier_ATR_Multiplier    = 3.0;               // ATR multiplier
input int                     Chandelier_Extreme_Lookback  = 22;                // Bars scanned for highest high / lowest low
input ENUM_TIMEFRAMES         Chandelier_Timeframe         = PERIOD_M5;         // Chandelier timeframe

input group "Broker Safety"
input int                     Min_SL_Improvement_Points    = 5;                 // Minimum tightening before sending OrderSend
input int                     Max_Spread_Points            = 100;               // Set to 0 to disable spread check
input ENUM_ORDER_TYPE_FILLING Filling_Type                 = ORDER_FILLING_FOK; // Used in MqlTradeRequest.type_filling

input group "Take Profit Runner"
input bool                    Allow_TP_Removal             = false;             // Remove TP near target after BE is armed
input int                     TP_Removal_Distance_Points   = 10;                // Remove TP when current price is within this many points
input bool                    TP_Removal_Require_BE        = true;              // Only remove TP after BE/chandelier stage

input group "Logging"
input bool                    Verbose                      = true;              // Log decisions to Experts tab

enum TRAIL_STAGE
  {
   STAGE_PRE_BE      = 0,
   STAGE_BE_MOVE     = 1,
   STAGE_CHANDELIER  = 2,
   STAGE_TP_REMOVE   = 3
  };

struct TicketState
  {
   ulong ticket;
   int   stage;
  };

struct RetcodeLog
  {
   ulong ticket;
   int   stage;
   uint  retcode;
  };

struct FillingWarning
  {
   string symbol;
   bool   logged;
  };

long           g_magic_numbers[];
string         g_manual_magic0_symbols[];
TicketState    g_states[];
RetcodeLog     g_retcode_logs[];
FillingWarning g_filling_warnings[];

//+------------------------------------------------------------------+
//| Initialization / cleanup                                          |
//+------------------------------------------------------------------+
int OnInit()
  {
   ParseMagics(MagicNumbers);
   ParseManualMagic0Symbols(Manual_Magic_0_Symbols);

   if(Verbose)
      PrintFormat("EA loaded, managing magics: %s%s",
                  ManagedMagicsLabel(),
                  ManualMagic0Label());

   const string chart_symbol = _Symbol;
   const long filling_mask = SymbolInfoInteger(chart_symbol, SYMBOL_FILLING_MODE);
   if(!IsFillingAllowed(filling_mask, Filling_Type))
      PrintFormat("Filling mode warning: requested %s not in %s filling mask (%d)",
                  FillingTypeLabel(Filling_Type), chart_symbol, filling_mask);

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
  }

void OnTick()
  {
   for(int i = PositionsTotal() - 1; i >= 0; --i)
     {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      const string symbol = PositionGetString(POSITION_SYMBOL);
      const long magic = PositionGetInteger(POSITION_MAGIC);
      if(!IsManagedMagic(magic, symbol))
         continue;

      const long spread_points = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
      if(Max_Spread_Points > 0 && spread_points > Max_Spread_Points)
        {
         if(Verbose)
            PrintFormat("[#%I64u %s] Skip: spread %d pt > %d pt threshold",
                        ticket, symbol, spread_points, Max_Spread_Points);
         continue;
        }

      WarnFillingOnce(ticket, symbol);

      ENUM_POSITION_TYPE position_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if(position_type != POSITION_TYPE_BUY && position_type != POSITION_TYPE_SELL)
         continue;

      const double point = SymbolPoint(symbol);
      if(point <= 0.0)
         continue;

      const double entry_price = PositionGetDouble(POSITION_PRICE_OPEN);
      const double current_sl = PositionGetDouble(POSITION_SL);
      const double current_tp = PositionGetDouble(POSITION_TP);
      double managed_tp = current_tp;
      const int digits = SymbolDigits(symbol);
      int state_index = EnsureTicketState(ticket, position_type, entry_price, current_sl, point);
      int stage = g_states[state_index].stage;

      const double profit_points = PositionProfitInPoints(symbol, position_type, entry_price);
      if(stage == STAGE_PRE_BE)
        {
         if(profit_points < (double)BE_Trigger_Points)
            continue;

         const double raw_be_sl = BreakevenSL(position_type, entry_price, point);
         double proposed_sl = EnforceStopsLevel(symbol, position_type, raw_be_sl);
         proposed_sl = NormalizeDouble(proposed_sl, digits);

         if(TryUpdateSL(ticket, symbol, position_type, current_sl, current_tp, proposed_sl, STAGE_BE_MOVE))
           {
            g_states[state_index].stage = STAGE_CHANDELIER;
            if(Verbose)
               PrintFormat("[#%I64u %s] BE armed, SL -> %s (entry %s %s %d pts)",
                           ticket,
                           symbol,
                           PriceLabel(symbol, proposed_sl),
                           PriceLabel(symbol, entry_price),
                           (position_type == POSITION_TYPE_BUY ? "+" : "-"),
                           BE_Buffer_Points);
           }
         continue;
        }

      if(ShouldRemoveTP(symbol, position_type, stage, managed_tp))
        {
         if(TryRemoveTP(ticket, symbol, current_sl, managed_tp, STAGE_TP_REMOVE))
           {
            managed_tp = 0.0;
            if(Verbose)
               PrintFormat("[#%I64u %s] TP removed to let winner run (old TP %s, price %s)",
                           ticket,
                           symbol,
                           PriceLabel(symbol, current_tp),
                           PriceLabel(symbol, CurrentExitPrice(symbol, position_type)));
           }
        }

      double chandelier_sl = 0.0;
      double extreme = 0.0;
      double atr = 0.0;
      if(!ComputeChandelier(symbol, position_type, chandelier_sl, extreme, atr))
         continue;

      const double be_sl = BreakevenSL(position_type, entry_price, point);
      double effective_sl = current_sl;
      if(position_type == POSITION_TYPE_BUY)
        {
         effective_sl = MathMax(effective_sl, be_sl);
         effective_sl = MathMax(effective_sl, chandelier_sl);
        }
      else
        {
         if(effective_sl <= 0.0)
            effective_sl = be_sl;
         else
            effective_sl = MathMin(effective_sl, be_sl);
         effective_sl = MathMin(effective_sl, chandelier_sl);
        }

      double proposed_sl = EnforceStopsLevel(symbol, position_type, effective_sl);
      proposed_sl = NormalizeDouble(proposed_sl, digits);

      if(TryUpdateSL(ticket, symbol, position_type, current_sl, managed_tp, proposed_sl, STAGE_CHANDELIER))
        {
         if(Verbose)
           {
            if(position_type == POSITION_TYPE_BUY)
               PrintFormat("[#%I64u %s] Chandelier tightened SL: %s -> %s (HH %s - %.1fxATR %s on %s)",
                           ticket,
                           symbol,
                           PriceLabel(symbol, current_sl),
                           PriceLabel(symbol, proposed_sl),
                           PriceLabel(symbol, extreme),
                           Chandelier_ATR_Multiplier,
                           DoubleToString(atr, digits),
                           TimeframeLabel(Chandelier_Timeframe));
            else
               PrintFormat("[#%I64u %s] Chandelier tightened SL: %s -> %s (LL %s + %.1fxATR %s on %s)",
                           ticket,
                           symbol,
                           PriceLabel(symbol, current_sl),
                           PriceLabel(symbol, proposed_sl),
                           PriceLabel(symbol, extreme),
                           Chandelier_ATR_Multiplier,
                           DoubleToString(atr, digits),
                           TimeframeLabel(Chandelier_Timeframe));
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Required helpers                                                  |
//+------------------------------------------------------------------+
void ParseMagics(const string csv)
  {
   ArrayResize(g_magic_numbers, 0);

   string parts[];
   const int count = StringSplit(csv, ',', parts);
   for(int i = 0; i < count; ++i)
     {
      string token = parts[i];
      StringTrimLeft(token);
      StringTrimRight(token);
      if(StringLen(token) == 0)
         continue;
      if(!IsIntegerToken(token))
        {
         if(Verbose)
            PrintFormat("Skipping invalid magic token: %s", token);
         continue;
        }

      const long magic = (long)StringToInteger(token);
      if(magic == 0)
        {
         if(Verbose)
            Print("Skipping magic 0 so manual trades remain unmanaged");
         continue;
        }

      const int size = ArraySize(g_magic_numbers);
      ArrayResize(g_magic_numbers, size + 1);
      g_magic_numbers[size] = magic;
     }
  }

bool IsManagedMagic(const long magic)
  {
   return(IsManagedMagic(magic, ""));
  }

bool IsManagedMagic(const long magic, const string symbol)
  {
   if(magic == 0)
      return(IsManagedManualMagic0Symbol(symbol));

   for(int i = 0; i < ArraySize(g_magic_numbers); ++i)
     {
      if(g_magic_numbers[i] == magic)
         return(true);
     }
   return(false);
  }

void ParseManualMagic0Symbols(const string csv)
  {
   ArrayResize(g_manual_magic0_symbols, 0);

   string parts[];
   const int count = StringSplit(csv, ',', parts);
   for(int i = 0; i < count; ++i)
     {
      string token = parts[i];
      StringTrimLeft(token);
      StringTrimRight(token);
      if(StringLen(token) == 0)
         continue;

      const int size = ArraySize(g_manual_magic0_symbols);
      ArrayResize(g_manual_magic0_symbols, size + 1);
      g_manual_magic0_symbols[size] = token;
     }
  }

bool IsManagedManualMagic0Symbol(const string symbol)
  {
   if(!Allow_Manual_Magic_0 || StringLen(symbol) == 0)
      return(false);

   for(int i = 0; i < ArraySize(g_manual_magic0_symbols); ++i)
     {
      if(g_manual_magic0_symbols[i] == symbol)
         return(true);
     }

   return(false);
  }

bool IsIntegerToken(const string token)
  {
   const int length = StringLen(token);
   if(length <= 0)
      return(false);

   int start = 0;
   const ushort first = StringGetCharacter(token, 0);
   if(first == '+' || first == '-')
      start = 1;

   if(start >= length)
      return(false);

   for(int i = start; i < length; ++i)
     {
      const ushort ch = StringGetCharacter(token, i);
      if(ch < '0' || ch > '9')
         return(false);
     }

   return(true);
  }

double PositionProfitInPoints(const string symbol,
                              const ENUM_POSITION_TYPE position_type,
                              const double entry_price)
  {
   const double point = SymbolPoint(symbol);
   if(point <= 0.0)
      return(0.0);

   const double current_price = CurrentExitPrice(symbol, position_type);
   if(current_price <= 0.0)
      return(0.0);

   if(position_type == POSITION_TYPE_BUY)
      return((current_price - entry_price) / point);

   return((entry_price - current_price) / point);
  }

bool ComputeChandelier(const string symbol,
                       const ENUM_POSITION_TYPE position_type,
                       double &chandelier_sl,
                       double &extreme,
                       double &atr)
  {
   const int lookback = MathMax(1, Chandelier_Extreme_Lookback);
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int copied = CopyRates(symbol, Chandelier_Timeframe, 0, lookback, rates);
   if(copied < lookback)
      return(false);

   if(position_type == POSITION_TYPE_BUY)
     {
      extreme = rates[0].high;
      for(int i = 1; i < copied; ++i)
         extreme = MathMax(extreme, rates[i].high);
     }
   else
     {
      extreme = rates[0].low;
      for(int i = 1; i < copied; ++i)
         extreme = MathMin(extreme, rates[i].low);
     }

   const int atr_period = MathMax(1, Chandelier_ATR_Period);
   const int atr_handle = iATR(symbol, Chandelier_Timeframe, atr_period);
   if(atr_handle == INVALID_HANDLE)
      return(false);

   double atr_buffer[];
   ArraySetAsSeries(atr_buffer, true);
   const int atr_copied = CopyBuffer(atr_handle, 0, 0, 1, atr_buffer);
   IndicatorRelease(atr_handle);

   if(atr_copied <= 0 || atr_buffer[0] <= 0.0)
      return(false);

   atr = atr_buffer[0];
   if(position_type == POSITION_TYPE_BUY)
      chandelier_sl = extreme - (Chandelier_ATR_Multiplier * atr);
   else
      chandelier_sl = extreme + (Chandelier_ATR_Multiplier * atr);

   return(chandelier_sl > 0.0);
  }

bool TryUpdateSL(const ulong ticket,
                 const string symbol,
                 const ENUM_POSITION_TYPE position_type,
                 const double current_sl,
                 const double current_tp,
                 const double proposed_sl,
                 const int stage)
  {
   const double point = SymbolPoint(symbol);
   if(point <= 0.0 || proposed_sl <= 0.0)
      return(false);

   const double min_improvement = MathMax(0, Min_SL_Improvement_Points) * point;
   if(current_sl > 0.0)
     {
      const double improvement = (position_type == POSITION_TYPE_BUY)
                                 ? proposed_sl - current_sl
                                 : current_sl - proposed_sl;
      if(improvement < min_improvement)
         return(false);
     }

   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);

   request.action = TRADE_ACTION_SLTP;
   request.position = ticket;
   request.symbol = symbol;
   request.sl = proposed_sl;
   request.tp = current_tp;
   request.type_filling = Filling_Type;

   ResetLastError();
   if(!OrderSend(request, result))
     {
      if(Verbose)
         PrintFormat("[#%I64u %s] SL update failed before broker retcode: %d",
                     ticket, symbol, GetLastError());
      return(false);
     }

   if(result.retcode == TRADE_RETCODE_DONE)
      return(true);

   if(result.retcode == TRADE_RETCODE_INVALID_STOPS ||
      result.retcode == TRADE_RETCODE_NO_CHANGES)
     {
      if(Verbose && ShouldLogRetcode(ticket, stage, result.retcode))
         PrintFormat("[#%I64u %s] SL update skipped: %s (%s)",
                     ticket, symbol, TradeRetcodeLabel(result.retcode), result.comment);
      return(false);
     }

   if(Verbose)
      PrintFormat("[#%I64u %s] SL update rejected: retcode %u (%s)",
                  ticket, symbol, result.retcode, result.comment);

   return(false);
  }

bool TryRemoveTP(const ulong ticket,
                 const string symbol,
                 const double current_sl,
                 const double current_tp,
                 const int stage)
  {
   if(current_tp <= 0.0)
      return(false);

   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);

   request.action = TRADE_ACTION_SLTP;
   request.position = ticket;
   request.symbol = symbol;
   request.sl = current_sl;
   request.tp = 0.0;
   request.type_filling = Filling_Type;

   ResetLastError();
   if(!OrderSend(request, result))
     {
      if(Verbose)
         PrintFormat("[#%I64u %s] TP removal failed before broker retcode: %d",
                     ticket, symbol, GetLastError());
      return(false);
     }

   if(result.retcode == TRADE_RETCODE_DONE)
      return(true);

   if(result.retcode == TRADE_RETCODE_INVALID_STOPS ||
      result.retcode == TRADE_RETCODE_NO_CHANGES)
     {
      if(Verbose && ShouldLogRetcode(ticket, stage, result.retcode))
         PrintFormat("[#%I64u %s] TP removal skipped: %s (%s)",
                     ticket, symbol, TradeRetcodeLabel(result.retcode), result.comment);
      return(false);
     }

   if(Verbose)
      PrintFormat("[#%I64u %s] TP removal rejected: retcode %u (%s)",
                  ticket, symbol, result.retcode, result.comment);

   return(false);
  }

double EnforceStopsLevel(const string symbol,
                         const ENUM_POSITION_TYPE position_type,
                         const double proposed_sl)
  {
   double adjusted_sl = proposed_sl;
   const double point = SymbolPoint(symbol);
   if(point <= 0.0 || adjusted_sl <= 0.0)
      return(adjusted_sl);

   long stops_level = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(stops_level <= 0)
      stops_level = 5;

   const double floor_distance = ((double)stops_level + 1.0) * point;
   const double current_price = CurrentExitPrice(symbol, position_type);
   if(current_price <= 0.0)
      return(adjusted_sl);

   if(position_type == POSITION_TYPE_BUY)
     {
      const double max_sl = current_price - floor_distance;
      if(adjusted_sl > max_sl)
         adjusted_sl = max_sl;
     }
   else
     {
      const double min_sl = current_price + floor_distance;
      if(adjusted_sl < min_sl)
         adjusted_sl = min_sl;
     }

   return(NormalizeDouble(adjusted_sl, SymbolDigits(symbol)));
  }

//+------------------------------------------------------------------+
//| Local helpers                                                     |
//+------------------------------------------------------------------+
int EnsureTicketState(const ulong ticket,
                      const ENUM_POSITION_TYPE position_type,
                      const double entry_price,
                      const double current_sl,
                      const double point)
  {
   for(int i = 0; i < ArraySize(g_states); ++i)
     {
      if(g_states[i].ticket == ticket)
         return(i);
     }

   const int size = ArraySize(g_states);
   ArrayResize(g_states, size + 1);
   g_states[size].ticket = ticket;

   // Reload assumption: if an existing SL is already at or beyond entry +/- BE buffer,
   // this EA treats the position as post-BE and resumes Chandelier trailing only.
   const double be_sl = BreakevenSL(position_type, entry_price, point);
   if(current_sl > 0.0 &&
      ((position_type == POSITION_TYPE_BUY && current_sl >= be_sl - (0.1 * point)) ||
       (position_type == POSITION_TYPE_SELL && current_sl <= be_sl + (0.1 * point))))
      g_states[size].stage = STAGE_CHANDELIER;
   else
      g_states[size].stage = STAGE_PRE_BE;

   return(size);
  }

double BreakevenSL(const ENUM_POSITION_TYPE position_type,
                   const double entry_price,
                   const double point)
  {
   if(position_type == POSITION_TYPE_BUY)
      return(entry_price + ((double)BE_Buffer_Points * point));

   return(entry_price - ((double)BE_Buffer_Points * point));
  }

bool ShouldRemoveTP(const string symbol,
                    const ENUM_POSITION_TYPE position_type,
                    const int stage,
                    const double current_tp)
  {
   if(!Allow_TP_Removal || current_tp <= 0.0)
      return(false);

   if(TP_Removal_Require_BE && stage != STAGE_CHANDELIER)
      return(false);

   const double point = SymbolPoint(symbol);
   if(point <= 0.0)
      return(false);

   const double current_price = CurrentExitPrice(symbol, position_type);
   if(current_price <= 0.0)
      return(false);

   const double distance_points = (position_type == POSITION_TYPE_BUY)
                                  ? (current_tp - current_price) / point
                                  : (current_price - current_tp) / point;

   return(distance_points <= (double)MathMax(0, TP_Removal_Distance_Points));
  }

double CurrentExitPrice(const string symbol, const ENUM_POSITION_TYPE position_type)
  {
   MqlTick tick;
   if(SymbolInfoTick(symbol, tick))
     {
      if(position_type == POSITION_TYPE_BUY && tick.bid > 0.0)
         return(tick.bid);
      if(position_type == POSITION_TYPE_SELL && tick.ask > 0.0)
         return(tick.ask);
     }

   const ENUM_SYMBOL_INFO_DOUBLE price_field =
      (position_type == POSITION_TYPE_BUY ? SYMBOL_BID : SYMBOL_ASK);
   return(SymbolInfoDouble(symbol, price_field));
  }

double SymbolPoint(const string symbol)
  {
   double point = 0.0;
   if(SymbolInfoDouble(symbol, SYMBOL_POINT, point))
      return(point);
   return(0.0);
  }

int SymbolDigits(const string symbol)
  {
   return((int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
  }

string PriceLabel(const string symbol, const double price)
  {
   if(price <= 0.0)
      return("none");
   return(DoubleToString(price, SymbolDigits(symbol)));
  }

string ManagedMagicsLabel()
  {
   string label = "";
   for(int i = 0; i < ArraySize(g_magic_numbers); ++i)
     {
      if(i > 0)
         label += ", ";
      label += IntegerToString(g_magic_numbers[i]);
     }
   if(StringLen(label) == 0)
      label = "(none)";
   return(label);
  }

string ManualMagic0Label()
  {
   if(!Allow_Manual_Magic_0 || ArraySize(g_manual_magic0_symbols) <= 0)
      return("");

   string label = "; manual magic 0 symbols: ";
   for(int i = 0; i < ArraySize(g_manual_magic0_symbols); ++i)
     {
      if(i > 0)
         label += ", ";
      label += g_manual_magic0_symbols[i];
     }
   return(label);
  }

bool IsFillingAllowed(const long filling_mask, const ENUM_ORDER_TYPE_FILLING filling_type)
  {
   if(filling_type == ORDER_FILLING_FOK)
      return((filling_mask & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK);
   if(filling_type == ORDER_FILLING_IOC)
      return((filling_mask & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC);
   if(filling_type == ORDER_FILLING_BOC)
      return((filling_mask & SYMBOL_FILLING_BOC) == SYMBOL_FILLING_BOC);

   return(true);
  }

void WarnFillingOnce(const ulong ticket, const string symbol)
  {
   const long filling_mask = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if(IsFillingAllowed(filling_mask, Filling_Type))
      return;

   for(int i = 0; i < ArraySize(g_filling_warnings); ++i)
     {
      if(g_filling_warnings[i].symbol == symbol)
         return;
     }

   const int size = ArraySize(g_filling_warnings);
   ArrayResize(g_filling_warnings, size + 1);
   g_filling_warnings[size].symbol = symbol;
   g_filling_warnings[size].logged = true;

   if(Verbose)
      PrintFormat("[#%I64u %s] Filling mode warning: requested %s not in symbol's filling mask",
                  ticket, symbol, FillingTypeLabel(Filling_Type));
  }

bool ShouldLogRetcode(const ulong ticket, const int stage, const uint retcode)
  {
   for(int i = 0; i < ArraySize(g_retcode_logs); ++i)
     {
      if(g_retcode_logs[i].ticket == ticket &&
         g_retcode_logs[i].stage == stage &&
         g_retcode_logs[i].retcode == retcode)
         return(false);
     }

   const int size = ArraySize(g_retcode_logs);
   ArrayResize(g_retcode_logs, size + 1);
   g_retcode_logs[size].ticket = ticket;
   g_retcode_logs[size].stage = stage;
   g_retcode_logs[size].retcode = retcode;
   return(true);
  }

string FillingTypeLabel(const ENUM_ORDER_TYPE_FILLING filling_type)
  {
   if(filling_type == ORDER_FILLING_FOK)
      return("FOK");
   if(filling_type == ORDER_FILLING_IOC)
      return("IOC");
   if(filling_type == ORDER_FILLING_RETURN)
      return("RETURN");
   if(filling_type == ORDER_FILLING_BOC)
      return("BOC");
   return(EnumToString(filling_type));
  }

string TradeRetcodeLabel(const uint retcode)
  {
   if(retcode == TRADE_RETCODE_INVALID_STOPS)
      return("INVALID_STOPS");
   if(retcode == TRADE_RETCODE_NO_CHANGES)
      return("NO_CHANGES");
   return(IntegerToString((int)retcode));
  }

string TimeframeLabel(const ENUM_TIMEFRAMES timeframe)
  {
   switch(timeframe)
     {
      case PERIOD_M1:  return("M1");
      case PERIOD_M2:  return("M2");
      case PERIOD_M3:  return("M3");
      case PERIOD_M4:  return("M4");
      case PERIOD_M5:  return("M5");
      case PERIOD_M6:  return("M6");
      case PERIOD_M10: return("M10");
      case PERIOD_M12: return("M12");
      case PERIOD_M15: return("M15");
      case PERIOD_M20: return("M20");
      case PERIOD_M30: return("M30");
      case PERIOD_H1:  return("H1");
      case PERIOD_H2:  return("H2");
      case PERIOD_H3:  return("H3");
      case PERIOD_H4:  return("H4");
      case PERIOD_H6:  return("H6");
      case PERIOD_H8:  return("H8");
      case PERIOD_H12: return("H12");
      case PERIOD_D1:  return("D1");
      case PERIOD_W1:  return("W1");
      case PERIOD_MN1: return("MN1");
      default:         return(EnumToString(timeframe));
     }
  }
