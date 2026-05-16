//+------------------------------------------------------------------+
//|                                         EhukaiLiquiditySwings.mq5 |
//|                     Ehukai Trading - Liquidity Swing Pools        |
//|                     v1.10 - TDA-ready liquidity map               |
//+------------------------------------------------------------------+
#property copyright "Ehukai Trading"
#property version   "1.10"
#property indicator_chart_window
#property indicator_plots 0

//+------------------------------------------------------------------+
//| CLI / Visual TDA contract                                         |
//|                                                                  |
//| This indicator is intentionally vendored with metatrader5-cli.    |
//| Keep object prefix, label text, colors, and tooltips stable so    |
//| screenshot agents can pair visual overlays with CLI JSON context. |
//|                                                                  |
//| Stable object prefix: ELS_                                        |
//| Stable labels: BSL/SSL LIQ OPEN/SWEPT C<count> V<volume>          |
//| Stable colors: red = buy-side liquidity, teal = sell-side         |
//| Stable geometry: zone rectangle + level line + count/volume label |
//| Structured pair: mt5 --json ehukai liquidity SYMBOL TF            |
//+------------------------------------------------------------------+

enum ENUM_LS_AREA
  {
   LS_WICK_EXTREMITY = 0, // Wick Extremity
   LS_FULL_RANGE     = 1  // Full Range
  };

enum ENUM_LS_FILTER
  {
   LS_FILTER_COUNT  = 0, // Count
   LS_FILTER_VOLUME = 1  // Volume
  };

input int            InpLookbackBars   = 300;               // Lookback bars
input int            InpPivotLookback  = 14;                // Pivot lookback
input ENUM_LS_AREA   InpSwingArea      = LS_WICK_EXTREMITY; // Swing area
input bool           InpUseAtrZones    = true;              // Use ATR-width pool zones
input int            InpAtrPeriod      = 14;                // ATR period for pool zones
input double         InpPoolHalfAtr    = 0.40;              // Pool half-width as ATR
input double         InpMinPenAtr      = 0.00;              // Min penetration as ATR
input ENUM_LS_FILTER InpFilterBy       = LS_FILTER_COUNT;   // Filter areas by
input double         InpFilterValue    = 0.0;               // Filter threshold
input bool           InpShowBuySide    = true;              // Show swing-high liquidity
input bool           InpShowSellSide   = true;              // Show swing-low liquidity
input int            InpMaxPools       = 10;                // Max pools to display
input int            InpExtendBars     = 40;                // Extend open pools right by bars
input color          InpBuySideColor   = clrTomato;         // Buy-side level color
input color          InpSellSideColor  = clrTeal;           // Sell-side level color
input color          InpBuySideFill    = clrMistyRose;      // Buy-side zone fill
input color          InpSellSideFill   = clrHoneydew;       // Sell-side zone fill
input bool           InpFillZones      = false;             // Fill rectangles
input int            InpLineWidth      = 2;                 // Level line width
input bool           InpShowLabels     = true;              // Show TDA labels
input int            InpLabelFontSize  = 8;                 // Label font size
input double         InpLabelOffsetPips = 3.0;              // Label offset in pips

string g_prefix = "ELS_";
double g_point;
int    g_digits;

//+------------------------------------------------------------------+
//| Initialization                                                    |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_point = _Point;
   g_digits = _Digits;
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Cleanup                                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, g_prefix);
  }

//+------------------------------------------------------------------+
//| Pip conversion                                                     |
//+------------------------------------------------------------------+
double PipsToPrice(const double pips)
  {
   if(g_digits == 3 || g_digits == 5)
      return pips * g_point * 10.0;
   return pips * g_point;
  }

//+------------------------------------------------------------------+
//| Current timeframe label                                            |
//+------------------------------------------------------------------+
string TimeframeLabel()
  {
   switch(_Period)
     {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      case PERIOD_MN1: return "MN1";
      default:         return EnumToString(_Period);
     }
  }

//+------------------------------------------------------------------+
//| Shared object defaults                                             |
//+------------------------------------------------------------------+
void SetObjectDefaults(const string name, const bool back)
  {
   ObjectSetInteger(0, name, OBJPROP_BACK, back);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_ZORDER, 0);
  }

//+------------------------------------------------------------------+
//| Pivot checks                                                       |
//+------------------------------------------------------------------+
bool IsPivotHigh(const int index, const int length, const double &high[])
  {
   for(int j = index - length; j <= index + length; j++)
     {
      if(j == index)
         continue;
      if(high[index] <= high[j])
         return false;
     }
   return true;
  }

bool IsPivotLow(const int index, const int length, const double &low[])
  {
   for(int j = index - length; j <= index + length; j++)
     {
      if(j == index)
         continue;
      if(low[index] >= low[j])
         return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| ATR helpers                                                       |
//+------------------------------------------------------------------+
double TrueRangeAt(const int index, const double &high[], const double &low[],
                   const double &close[])
  {
   if(index <= 0)
      return high[index] - low[index];
   return MathMax(high[index] - low[index],
                  MathMax(MathAbs(high[index] - close[index - 1]),
                          MathAbs(low[index] - close[index - 1])));
  }

double AtrAt(const int index, const double &high[], const double &low[],
             const double &close[])
  {
   int period = MathMax(1, InpAtrPeriod);
   int start = MathMax(0, index - period + 1);
   double total = 0.0;
   int count = 0;
   for(int j = start; j <= index; j++)
     {
      total += TrueRangeAt(j, high, low, close);
      count++;
     }
   return count > 0 ? total / (double)count : 0.0;
  }

void PoolZoneFromLevel(const int index, const double level,
                       const double &high[], const double &low[], const double &close[],
                       double &top, double &bottom)
  {
   double half = MathMax(AtrAt(index, high, low, close) * MathMax(0.0, InpPoolHalfAtr),
                         g_point * 5.0);
   top = level + half;
   bottom = level - half;
  }

//+------------------------------------------------------------------+
//| Count later interactions with a pool                               |
//+------------------------------------------------------------------+
void PoolStats(const int start_index, const double top, const double bottom,
               const double &high[], const double &low[], const long &tick_volume[],
               const int rates_total, int &count, double &volume)
  {
   count = 0;
   volume = 0.0;
   for(int j = start_index + 1; j < rates_total; j++)
     {
      if(low[j] < top && high[j] > bottom)
        {
         count++;
         volume += (double)tick_volume[j];
        }
     }
  }

//+------------------------------------------------------------------+
//| Sweep status                                                       |
//+------------------------------------------------------------------+
int FindSweep(const bool buy_side, const int start_index, const double top,
              const double bottom, const double min_penetration,
              const double &high[], const double &low[], const double &close[],
              const datetime &time[], const int rates_total, datetime &swept_time)
  {
   swept_time = 0;
   double mid = (top + bottom) / 2.0;
   for(int j = start_index + 1; j < rates_total; j++)
     {
      if(buy_side)
        {
         if(high[j] > top + min_penetration && close[j] < mid)
           {
            swept_time = time[j];
            return 1;
           }
         if(close[j] > top)
           {
            swept_time = time[j];
            return 2;
           }
        }
      else
        {
         if(low[j] < bottom - min_penetration && close[j] > mid)
           {
            swept_time = time[j];
            return 1;
           }
         if(close[j] < bottom)
           {
            swept_time = time[j];
            return 2;
           }
        }
     }
   return 0;
  }

//+------------------------------------------------------------------+
//| Filter pass                                                        |
//+------------------------------------------------------------------+
bool PassesFilter(const int count, const double volume)
  {
   double target = (InpFilterBy == LS_FILTER_COUNT ? (double)count : volume);
   return target > InpFilterValue;
  }

//+------------------------------------------------------------------+
//| Draw a liquidity pool                                              |
//+------------------------------------------------------------------+
void DrawPool(const int ordinal, const bool buy_side, const datetime pivot_time,
              const datetime right_time, const double top, const double bottom,
              const double level, const bool swept, const int count, const double volume)
  {
   string tf = TimeframeLabel();
   string side = buy_side ? "BSL" : "SSL";
   string status = swept ? "SWEPT" : "OPEN";
   color level_color = buy_side ? InpBuySideColor : InpSellSideColor;
   color fill_color = buy_side ? InpBuySideFill : InpSellSideFill;
   string base = g_prefix + _Symbol + "_" + tf + "_" + side + "_" + IntegerToString(ordinal);
   string label = StringFormat("%s LIQ %s C%d V%.0f", side, status, count, volume);

   string zone_name = base + "_zone";
   if(ObjectCreate(0, zone_name, OBJ_RECTANGLE, 0, pivot_time, top, right_time, bottom))
     {
      ObjectSetInteger(0, zone_name, OBJPROP_COLOR, level_color);
      ObjectSetInteger(0, zone_name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, zone_name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, zone_name, OBJPROP_FILL, InpFillZones);
      ObjectSetInteger(0, zone_name, OBJPROP_BGCOLOR, fill_color);
      ObjectSetString(0, zone_name, OBJPROP_TOOLTIP,
                      StringFormat("%s %s %.5f-%.5f count=%d volume=%.0f",
                                   tf, label, bottom, top, count, volume));
      SetObjectDefaults(zone_name, true);
     }

   string line_name = base + "_level";
   if(ObjectCreate(0, line_name, OBJ_TREND, 0, pivot_time, level, right_time, level))
     {
      ObjectSetInteger(0, line_name, OBJPROP_COLOR, level_color);
      ObjectSetInteger(0, line_name, OBJPROP_STYLE, swept ? STYLE_DASH : STYLE_SOLID);
      ObjectSetInteger(0, line_name, OBJPROP_WIDTH, InpLineWidth);
      ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, line_name, OBJPROP_TOOLTIP,
                      StringFormat("%s %.5f", label, level));
      SetObjectDefaults(line_name, false);
     }

   if(InpShowLabels)
     {
      double y = buy_side ? level + PipsToPrice(InpLabelOffsetPips)
                          : level - PipsToPrice(InpLabelOffsetPips);
      string text_name = base + "_label";
      if(ObjectCreate(0, text_name, OBJ_TEXT, 0, pivot_time, y))
        {
         ObjectSetString(0, text_name, OBJPROP_TEXT, label);
         ObjectSetInteger(0, text_name, OBJPROP_COLOR, level_color);
         ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, InpLabelFontSize);
         ObjectSetString(0, text_name, OBJPROP_FONT, "Arial Bold");
         SetObjectDefaults(text_name, false);
        }
     }
  }

//+------------------------------------------------------------------+
//| Main calculation                                                   |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   ObjectsDeleteAll(0, g_prefix);

   int length = MathMax(1, InpPivotLookback);
   if(rates_total < (length * 2 + 3))
      return rates_total;

   int lookback = MathMin(InpLookbackBars, rates_total - (length * 2) - 1);
   int start = MathMax(length, rates_total - lookback);
   int stop = rates_total - length;
   int drawn = 0;
   int max_pools = MathMax(1, InpMaxPools);
   int seconds = PeriodSeconds(_Period);
   if(seconds <= 0)
      seconds = 60;
   datetime future_time = time[rates_total - 1] + (datetime)(seconds * InpExtendBars);

   for(int i = stop - 1; i >= start && drawn < max_pools; i--)
     {
      if(InpShowBuySide && IsPivotHigh(i, length, high))
        {
         double level = high[i];
         double top = high[i];
         double bottom = low[i];
         if(InpSwingArea == LS_WICK_EXTREMITY && InpUseAtrZones)
            PoolZoneFromLevel(i, level, high, low, close, top, bottom);
         else if(InpSwingArea == LS_WICK_EXTREMITY)
            bottom = MathMax(open[i], close[i]);
         int count = 0;
         double vol = 0.0;
         PoolStats(i, top, bottom, high, low, tick_volume, rates_total, count, vol);
         if(PassesFilter(count, vol))
           {
            datetime swept_time = 0;
            double min_pen = AtrAt(i, high, low, close) * MathMax(0.0, InpMinPenAtr);
            int status = FindSweep(true, i, top, bottom, min_pen, high, low, close, time, rates_total, swept_time);
            if(status != 2)
              {
               bool swept = (status == 1);
               DrawPool(drawn, true, time[i], swept ? swept_time : future_time,
                        top, bottom, level, swept, count, vol);
               drawn++;
              }
           }
        }

      if(drawn >= max_pools)
         break;

      if(InpShowSellSide && IsPivotLow(i, length, low))
        {
         double level = low[i];
         double top = high[i];
         double bottom = low[i];
         if(InpSwingArea == LS_WICK_EXTREMITY && InpUseAtrZones)
            PoolZoneFromLevel(i, level, high, low, close, top, bottom);
         else if(InpSwingArea == LS_WICK_EXTREMITY)
            top = MathMin(open[i], close[i]);
         int count = 0;
         double vol = 0.0;
         PoolStats(i, top, bottom, high, low, tick_volume, rates_total, count, vol);
         if(PassesFilter(count, vol))
           {
            datetime swept_time = 0;
            double min_pen = AtrAt(i, high, low, close) * MathMax(0.0, InpMinPenAtr);
            int status = FindSweep(false, i, top, bottom, min_pen, high, low, close, time, rates_total, swept_time);
            if(status != 2)
              {
               bool swept = (status == 1);
               DrawPool(drawn, false, time[i], swept ? swept_time : future_time,
                        top, bottom, level, swept, count, vol);
               drawn++;
              }
           }
        }
     }

   return rates_total;
  }
