//+------------------------------------------------------------------+
//|                                             EhukaiTDAOverlay.mq5  |
//|                  Ehukai Trading - Unified TDA Visual Overlay      |
//|                  v1.00 - Clean screenshot presentation layer      |
//+------------------------------------------------------------------+
#property copyright "Ehukai Trading"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

//+------------------------------------------------------------------+
//| CLI / Visual TDA contract                                         |
//|                                                                  |
//| This is the preferred chart overlay for visual TDA screenshots.   |
//| It composes structure, FVG, and liquidity concepts with low-noise  |
//| defaults while the CLI keeps exact structured logic separate.      |
//|                                                                  |
//| Primitive/debug overlays: EhukaiFVG, EhukaiMarketStructure,        |
//| EhukaiLiquiditySwings. Apply this overlay by itself for agents.    |
//|                                                                  |
//| Stable object prefix: ETDA_                                       |
//| Stable panel: TDA <TF>: <BIAS> | H <kind> <price> | L ...         |
//| Stable FVG labels: BULL/BEAR FVG OPEN/PARTIAL <pips>p             |
//| Stable liquidity labels: BSL/SSL LIQ OPEN/SWEPT C<count> V<vol>   |
//| Structured pair: mt5 --json ehukai structure/fvg/liquidity        |
//+------------------------------------------------------------------+

enum ENUM_TDA_MODE
  {
   TDA_AGENT_SCREENSHOT = 0, // Agent Screenshot
   TDA_MANUAL_ANALYSIS  = 1  // Manual Analysis
  };

input ENUM_TDA_MODE InpMode               = TDA_AGENT_SCREENSHOT; // Visual mode
input int           InpLookbackBars       = 300;                  // Lookback bars
input int           InpExtendBars         = 48;                   // Extend active objects
input bool          InpShowStructure      = true;                 // Show structure
input bool          InpShowFVG            = true;                 // Show nearest FVGs
input bool          InpShowLiquidity      = true;                 // Show liquidity pools
input int           InpPivotBars          = 4;                    // Structure pivot bars
input int           InpMaxSwingLabels     = 6;                    // Max swing labels
input int           InpMaxFVGZones        = 3;                    // Max FVG zones
input double        InpMinFVGGapPips      = 1.0;                  // Min FVG size
input double        InpMaxFVGDistancePips = 160.0;                // Max FVG distance
input int           InpLiquidityLookback  = 14;                   // Liquidity pivot lookback
input int           InpMaxLiquidityPools  = 4;                    // Max liquidity pools
input bool          InpShowSweptLiquidity = true;                 // Include swept pools
input bool          InpFillSmallZones     = false;                // Fill small zones
input double        InpMaxFillPips        = 25.0;                 // Max filled-zone size
input int           InpLabelFontSize      = 8;                    // Label size
input double        InpLabelOffsetPips    = 3.0;                  // Label offset
input color         InpBullColor          = clrLimeGreen;         // Bullish color
input color         InpBearColor          = clrTomato;            // Bearish color
input color         InpNeutralColor       = clrSilver;            // Neutral color
input color         InpLevelColor         = clrDodgerBlue;        // Structure level color
input color         InpLiquidityBuyColor  = clrTomato;            // Buy-side liquidity
input color         InpLiquiditySellColor = clrTeal;              // Sell-side liquidity

string g_prefix = "ETDA_";
double g_point;
int    g_digits;

struct SwingPoint
  {
   datetime time;
   double   price;
   bool     is_high;
   int      index;
   string   kind;
  };

struct FVGZone
  {
   datetime time_start;
   datetime time_filled;
   double   upper;
   double   lower;
   double   orig_upper;
   double   orig_lower;
   double   gap_pips;
   bool     is_bullish;
   bool     is_filled;
   bool     is_partial;
   int      index;
  };

//+------------------------------------------------------------------+
//| Initialization / cleanup                                          |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_point = _Point;
   g_digits = _Digits;
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, g_prefix);
  }

//+------------------------------------------------------------------+
//| Shared helpers                                                     |
//+------------------------------------------------------------------+
double PipsToPrice(const double pips)
  {
   if(g_digits == 3 || g_digits == 5)
      return pips * g_point * 10.0;
   return pips * g_point;
  }

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

int EffectivePivotBars()
  {
   int pivot = MathMax(1, InpPivotBars);
   if(_Period == PERIOD_M1 || _Period == PERIOD_M5)
      return MathMin(pivot, 2);
   if(_Period == PERIOD_M15 || _Period == PERIOD_M30)
      return MathMin(pivot, 3);
   return pivot;
  }

int ModeMaxFVG()
  {
   int cap = (InpMode == TDA_AGENT_SCREENSHOT ? 3 : 5);
   return MathMax(1, MathMin(InpMaxFVGZones, cap));
  }

int ModeMaxLiquidity()
  {
   int cap = (InpMode == TDA_AGENT_SCREENSHOT ? 4 : 8);
   return MathMax(1, MathMin(InpMaxLiquidityPools, cap));
  }

void SetObjectDefaults(const string name, const bool back, const int zorder)
  {
   ObjectSetInteger(0, name, OBJPROP_BACK, back);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_ZORDER, zorder);
  }

datetime FutureTime(const datetime &time[], const int rates_total)
  {
   int seconds = PeriodSeconds(_Period);
   if(seconds <= 0)
      seconds = 60;
   return time[rates_total - 1] + (datetime)(seconds * InpExtendBars);
  }

//+------------------------------------------------------------------+
//| Structure detection                                                |
//+------------------------------------------------------------------+
void AddSwing(SwingPoint &swings[], int &count, const datetime t,
              const double price, const bool is_high, const int index)
  {
   count++;
   ArrayResize(swings, count);
   swings[count - 1].time = t;
   swings[count - 1].price = price;
   swings[count - 1].is_high = is_high;
   swings[count - 1].index = index;
   swings[count - 1].kind = "";
  }

void DetectSwings(const double &high[], const double &low[],
                  const datetime &time[], const int rates_total,
                  SwingPoint &swings[], int &swing_count)
  {
   ArrayResize(swings, 0);
   swing_count = 0;
   int pivot = EffectivePivotBars();
   int lookback = MathMin(InpLookbackBars, rates_total - (pivot * 2) - 1);
   int start = MathMax(pivot, rates_total - lookback);
   int stop = rates_total - pivot;

   for(int i = start; i < stop; i++)
     {
      bool is_high = true;
      bool is_low = true;
      for(int j = i - pivot; j <= i + pivot; j++)
        {
         if(j == i)
            continue;
         if(high[i] <= high[j])
            is_high = false;
         if(low[i] >= low[j])
            is_low = false;
         if(!is_high && !is_low)
            break;
        }
      if(is_high)
         AddSwing(swings, swing_count, time[i], high[i], true, i);
      if(is_low)
         AddSwing(swings, swing_count, time[i], low[i], false, i);
     }
  }

void ClassifySwings(SwingPoint &swings[], const int swing_count)
  {
   double last_high = 0.0;
   double last_low = 0.0;
   bool have_high = false;
   bool have_low = false;
   for(int i = 0; i < swing_count; i++)
     {
      if(swings[i].is_high)
        {
         swings[i].kind = have_high ? (swings[i].price > last_high ? "HH" : "LH") : "SH";
         last_high = swings[i].price;
         have_high = true;
        }
      else
        {
         swings[i].kind = have_low ? (swings[i].price > last_low ? "HL" : "LL") : "SL";
         last_low = swings[i].price;
         have_low = true;
        }
     }
  }

bool LatestSwing(const SwingPoint &swings[], const int swing_count,
                 const bool want_high, SwingPoint &out_swing)
  {
   for(int i = swing_count - 1; i >= 0; i--)
     {
      if(swings[i].is_high == want_high)
        {
         out_swing = swings[i];
         return true;
        }
     }
   return false;
  }

string StructureBias(const SwingPoint &last_high, const bool have_high,
                     const SwingPoint &last_low, const bool have_low,
                     const double last_close)
  {
   if(have_high && last_close > last_high.price)
      return "BULLISH BOS";
   if(have_low && last_close < last_low.price)
      return "BEARISH BOS";
   if(have_high && have_low && last_high.kind == "HH" && last_low.kind == "HL")
      return "BULLISH HH/HL";
   if(have_high && have_low && last_high.kind == "LH" && last_low.kind == "LL")
      return "BEARISH LH/LL";
   return "NEUTRAL / RANGE";
  }

color StructureColor(const string kind)
  {
   if(kind == "HH" || kind == "HL")
      return InpBullColor;
   if(kind == "LH" || kind == "LL")
      return InpBearColor;
   return InpNeutralColor;
  }

void DrawSwing(const SwingPoint &swing, const int ordinal)
  {
   color c = StructureColor(swing.kind);
   double y = swing.is_high ? swing.price + PipsToPrice(InpLabelOffsetPips)
                            : swing.price - PipsToPrice(InpLabelOffsetPips);
   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_SW_" + IntegerToString(ordinal);

   string marker = base + "_mk";
   if(ObjectCreate(0, marker, OBJ_ARROW, 0, swing.time, swing.price))
     {
      ObjectSetInteger(0, marker, OBJPROP_COLOR, c);
      ObjectSetInteger(0, marker, OBJPROP_ARROWCODE, swing.is_high ? 234 : 233);
      ObjectSetInteger(0, marker, OBJPROP_WIDTH, 1);
      SetObjectDefaults(marker, false, 4);
     }

   string label = base + "_tx";
   if(ObjectCreate(0, label, OBJ_TEXT, 0, swing.time, y))
     {
      ObjectSetString(0, label, OBJPROP_TEXT, swing.kind);
      ObjectSetInteger(0, label, OBJPROP_COLOR, c);
      ObjectSetInteger(0, label, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, label, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(label, false, 5);
     }
  }

void DrawStructureLevel(const SwingPoint &swing, const datetime chart_end,
                        const string suffix, const color c)
  {
   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_" + suffix;
   if(ObjectCreate(0, name, OBJ_TREND, 0, swing.time, swing.price, chart_end, swing.price))
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, name, OBJPROP_TOOLTIP,
                      StringFormat("%s %s %.5f", TimeframeLabel(), suffix, swing.price));
      SetObjectDefaults(name, false, 2);
     }
  }

void DrawBiasPanel(const string bias, const SwingPoint &last_high, const bool have_high,
                   const SwingPoint &last_low, const bool have_low)
  {
   color c = InpNeutralColor;
   if(StringFind(bias, "BULLISH") >= 0)
      c = InpBullColor;
   if(StringFind(bias, "BEARISH") >= 0)
      c = InpBearColor;

   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_PANEL";
   if(ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
     {
      string hi = have_high ? StringFormat("H %s %.3f", last_high.kind, last_high.price) : "H n/a";
      string lo = have_low ? StringFormat("L %s %.3f", last_low.kind, last_low.price) : "L n/a";
      ObjectSetString(0, name, OBJPROP_TEXT,
                      StringFormat("TDA %s: %s | %s | %s", TimeframeLabel(), bias, hi, lo));
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 28);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false, 6);
     }
  }

void RenderStructure(const double &high[], const double &low[],
                     const datetime &time[], const double &close[],
                     const int rates_total)
  {
   if(!InpShowStructure)
      return;

   SwingPoint swings[];
   int swing_count = 0;
   DetectSwings(high, low, time, rates_total, swings, swing_count);
   ClassifySwings(swings, swing_count);

   SwingPoint last_high;
   SwingPoint last_low;
   bool have_high = LatestSwing(swings, swing_count, true, last_high);
   bool have_low = LatestSwing(swings, swing_count, false, last_low);
   string bias = StructureBias(last_high, have_high, last_low, have_low, close[rates_total - 1]);

   int max_labels = MathMax(1, InpMaxSwingLabels);
   if(InpMode == TDA_AGENT_SCREENSHOT)
      max_labels = MathMin(max_labels, 6);
   int shown = 0;
   for(int i = swing_count - 1; i >= 0 && shown < max_labels; i--)
     {
      DrawSwing(swings[i], shown);
      shown++;
     }

   datetime chart_end = FutureTime(time, rates_total);
   if(have_high)
      DrawStructureLevel(last_high, chart_end, "RESISTANCE", InpLevelColor);
   if(have_low)
      DrawStructureLevel(last_low, chart_end, "SUPPORT", InpLevelColor);
   DrawBiasPanel(bias, last_high, have_high, last_low, have_low);
  }

//+------------------------------------------------------------------+
//| FVG detection and rendering                                       |
//+------------------------------------------------------------------+
void ProcessFVGFill(FVGZone &zone, const double &high[], const double &low[],
                    const datetime &time[], const int start_bar, const int rates_total)
  {
   double deepest = 0.0;
   for(int j = start_bar + 1; j < rates_total; j++)
     {
      if(zone.is_bullish)
        {
         if(low[j] <= zone.orig_lower)
           {
            zone.is_filled = true;
            zone.time_filled = time[j];
            return;
           }
         if(low[j] < zone.orig_upper && low[j] > zone.orig_lower)
           {
            zone.is_partial = true;
            double pen = zone.orig_upper - low[j];
            if(pen > deepest)
              {
               deepest = pen;
               zone.upper = low[j];
              }
           }
        }
      else
        {
         if(high[j] >= zone.orig_upper)
           {
            zone.is_filled = true;
            zone.time_filled = time[j];
            return;
           }
         if(high[j] > zone.orig_lower && high[j] < zone.orig_upper)
           {
            zone.is_partial = true;
            double pen = high[j] - zone.orig_lower;
            if(pen > deepest)
              {
               deepest = pen;
               zone.lower = high[j];
              }
           }
        }
     }

   if((zone.upper - zone.lower) < PipsToPrice(0.1))
      zone.is_filled = true;
  }

double FVGDistancePips(const FVGZone &zone, const double current_price)
  {
   double d = 0.0;
   if(current_price > zone.upper)
      d = current_price - zone.upper;
   else if(current_price < zone.lower)
      d = zone.lower - current_price;
   return d / PipsToPrice(1.0);
  }

void AddFVG(FVGZone &zones[], int &count, const FVGZone &zone)
  {
   count++;
   ArrayResize(zones, count);
   zones[count - 1] = zone;
  }

void DrawFVG(const FVGZone &zone, const int ordinal,
             const datetime chart_end, const datetime label_time)
  {
   color c = zone.is_bullish ? InpBullColor : InpBearColor;
   string side = zone.is_bullish ? "BULL" : "BEAR";
   string status = zone.is_partial ? "PARTIAL" : "OPEN";
   string label_text = StringFormat("%s FVG %s %.1fp", side, status, zone.gap_pips);
   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_FVG_" + IntegerToString(ordinal);
   bool fill_rect = InpFillSmallZones && (InpMaxFillPips <= 0 || zone.gap_pips <= InpMaxFillPips);

   string rect = base + "_r";
   if(ObjectCreate(0, rect, OBJ_RECTANGLE, 0, zone.time_start, zone.upper, chart_end, zone.lower))
     {
      ObjectSetInteger(0, rect, OBJPROP_COLOR, c);
      ObjectSetInteger(0, rect, OBJPROP_FILL, fill_rect);
      ObjectSetInteger(0, rect, OBJPROP_WIDTH, 2);
      ObjectSetString(0, rect, OBJPROP_TOOLTIP,
                      StringFormat("%s %.5f-%.5f", label_text, zone.lower, zone.upper));
      SetObjectDefaults(rect, true, 0);
     }

   double mid = (zone.upper + zone.lower) / 2.0;
   string midline = base + "_m";
   if(ObjectCreate(0, midline, OBJ_TREND, 0, zone.time_start, mid, chart_end, mid))
     {
      ObjectSetInteger(0, midline, OBJPROP_COLOR, c);
      ObjectSetInteger(0, midline, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, midline, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, midline, OBJPROP_RAY_RIGHT, false);
      SetObjectDefaults(midline, false, 1);
     }

   string label = base + "_label";
   if(ObjectCreate(0, label, OBJ_TEXT, 0, label_time, mid))
     {
      ObjectSetString(0, label, OBJPROP_TEXT, label_text);
      ObjectSetInteger(0, label, OBJPROP_COLOR, c);
      ObjectSetInteger(0, label, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, label, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(label, false, 5);
     }
  }

void RenderFVGs(const double &open[], const double &high[], const double &low[],
                const double &close[], const datetime &time[], const int rates_total)
  {
   if(!InpShowFVG)
      return;

   int lookback = MathMin(InpLookbackBars, rates_total - 3);
   int start = MathMax(0, rates_total - lookback);
   double min_gap = PipsToPrice(InpMinFVGGapPips);
   double current_price = close[rates_total - 1];
   FVGZone zones[];
   int count = 0;

   for(int i = start; i < rates_total - 2; i++)
     {
      int c1 = i;
      int c3 = i + 2;
      FVGZone z;
      bool found = false;
      if(low[c3] > high[c1] && (low[c3] - high[c1]) >= min_gap)
        {
         z.time_start = time[c3];
         z.orig_upper = low[c3];
         z.orig_lower = high[c1];
         z.upper = z.orig_upper;
         z.lower = z.orig_lower;
         z.gap_pips = (z.orig_upper - z.orig_lower) / PipsToPrice(1.0);
         z.is_bullish = true;
         found = true;
        }
      else if(high[c3] < low[c1] && (low[c1] - high[c3]) >= min_gap)
        {
         z.time_start = time[c3];
         z.orig_upper = low[c1];
         z.orig_lower = high[c3];
         z.upper = z.orig_upper;
         z.lower = z.orig_lower;
         z.gap_pips = (z.orig_upper - z.orig_lower) / PipsToPrice(1.0);
         z.is_bullish = false;
         found = true;
        }

      if(found)
        {
         z.is_filled = false;
         z.is_partial = false;
         z.time_filled = 0;
         z.index = c3;
         ProcessFVGFill(z, high, low, time, c3, rates_total);
         if(z.is_filled)
            continue;
         if(InpMaxFVGDistancePips > 0 && FVGDistancePips(z, current_price) > InpMaxFVGDistancePips)
            continue;
         AddFVG(zones, count, z);
        }
     }

   datetime chart_end = FutureTime(time, rates_total);
   datetime label_time = time[rates_total - 1] + (datetime)(MathMax(2, InpExtendBars / 6) * PeriodSeconds(_Period));
   int shown = 0;
   for(int i = count - 1; i >= 0 && shown < ModeMaxFVG(); i--)
     {
      DrawFVG(zones[i], shown, chart_end, label_time);
      shown++;
     }
  }

//+------------------------------------------------------------------+
//| Liquidity detection and rendering                                 |
//+------------------------------------------------------------------+
bool PivotHighAt(const int index, const int length, const double &high[])
  {
   for(int j = index - length; j <= index + length; j++)
      if(j != index && high[index] <= high[j])
         return false;
   return true;
  }

bool PivotLowAt(const int index, const int length, const double &low[])
  {
   for(int j = index - length; j <= index + length; j++)
      if(j != index && low[index] >= low[j])
         return false;
   return true;
  }

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

bool FindSweep(const bool buy_side, const int start_index, const double top,
               const double bottom, const double &close[], const datetime &time[],
               const int rates_total, datetime &swept_time)
  {
   swept_time = 0;
   for(int j = start_index + 1; j < rates_total; j++)
     {
      if(buy_side && close[j] > top)
        {
         swept_time = time[j];
         return true;
        }
      if(!buy_side && close[j] < bottom)
        {
         swept_time = time[j];
         return true;
        }
     }
   return false;
  }

void DrawLiquidity(const int ordinal, const bool buy_side, const datetime pivot_time,
                   const datetime right_time, const double top, const double bottom,
                   const double level, const bool swept, const int count, const double volume)
  {
   string side = buy_side ? "BSL" : "SSL";
   string status = swept ? "SWEPT" : "OPEN";
   string text = StringFormat("%s LIQ %s C%d V%.0f", side, status, count, volume);
   color c = buy_side ? InpLiquidityBuyColor : InpLiquiditySellColor;
   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_LIQ_" + IntegerToString(ordinal);

   if(!swept)
     {
      string zone = base + "_zone";
      if(ObjectCreate(0, zone, OBJ_RECTANGLE, 0, pivot_time, top, right_time, bottom))
        {
         ObjectSetInteger(0, zone, OBJPROP_COLOR, c);
         ObjectSetInteger(0, zone, OBJPROP_FILL, false);
         ObjectSetInteger(0, zone, OBJPROP_WIDTH, 1);
         ObjectSetString(0, zone, OBJPROP_TOOLTIP, text);
         SetObjectDefaults(zone, true, 0);
        }
     }

   string line = base + "_line";
   if(ObjectCreate(0, line, OBJ_TREND, 0, pivot_time, level, right_time, level))
     {
      ObjectSetInteger(0, line, OBJPROP_COLOR, c);
      ObjectSetInteger(0, line, OBJPROP_STYLE, swept ? STYLE_DASH : STYLE_SOLID);
      ObjectSetInteger(0, line, OBJPROP_WIDTH, swept ? 1 : 2);
      ObjectSetInteger(0, line, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, line, OBJPROP_TOOLTIP, StringFormat("%s %.5f", text, level));
      SetObjectDefaults(line, false, 3);
     }

   string label = base + "_label";
   double y = buy_side ? level + PipsToPrice(InpLabelOffsetPips)
                       : level - PipsToPrice(InpLabelOffsetPips);
   if(ObjectCreate(0, label, OBJ_TEXT, 0, pivot_time, y))
     {
      ObjectSetString(0, label, OBJPROP_TEXT, text);
      ObjectSetInteger(0, label, OBJPROP_COLOR, c);
      ObjectSetInteger(0, label, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, label, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(label, false, 5);
     }
  }

void RenderLiquidity(const double &open[], const double &high[], const double &low[],
                     const double &close[], const datetime &time[], const long &tick_volume[],
                     const int rates_total)
  {
   if(!InpShowLiquidity)
      return;

   int length = MathMax(1, InpLiquidityLookback);
   if(rates_total < length * 2 + 3)
      return;
   int lookback = MathMin(InpLookbackBars, rates_total - (length * 2) - 1);
   int start = MathMax(length, rates_total - lookback);
   int stop = rates_total - length;
   datetime future_time = FutureTime(time, rates_total);
   int drawn = 0;

   for(int i = stop - 1; i >= start && drawn < ModeMaxLiquidity(); i--)
     {
      if(PivotHighAt(i, length, high))
        {
         double top = high[i];
         double bottom = MathMax(open[i], close[i]);
         int count = 0;
         double vol = 0.0;
         PoolStats(i, top, bottom, high, low, tick_volume, rates_total, count, vol);
         datetime swept_time = 0;
         bool swept = FindSweep(true, i, top, bottom, close, time, rates_total, swept_time);
         if(count > 0 && (!swept || InpShowSweptLiquidity))
           {
            DrawLiquidity(drawn, true, time[i], swept ? swept_time : future_time,
                          top, bottom, top, swept, count, vol);
            drawn++;
           }
        }
      if(drawn >= ModeMaxLiquidity())
         break;
      if(PivotLowAt(i, length, low))
        {
         double bottom = low[i];
         double top = MathMin(open[i], close[i]);
         int count = 0;
         double vol = 0.0;
         PoolStats(i, top, bottom, high, low, tick_volume, rates_total, count, vol);
         datetime swept_time = 0;
         bool swept = FindSweep(false, i, top, bottom, close, time, rates_total, swept_time);
         if(count > 0 && (!swept || InpShowSweptLiquidity))
           {
            DrawLiquidity(drawn, false, time[i], swept ? swept_time : future_time,
                          top, bottom, bottom, swept, count, vol);
            drawn++;
           }
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
   if(rates_total < 20)
      return rates_total;

   RenderFVGs(open, high, low, close, time, rates_total);
   RenderLiquidity(open, high, low, close, time, tick_volume, rates_total);
   RenderStructure(high, low, time, close, rates_total);
   ChartRedraw(0);
   return rates_total;
  }
