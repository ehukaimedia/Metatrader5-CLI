//+------------------------------------------------------------------+
//|                                         EhukaiMarketStructure.mq5 |
//|                         Ehukai Trading - Visual Market Structure  |
//|                         v1.12 - elite-v1 8/3/1 structure          |
//+------------------------------------------------------------------+
#property copyright "Ehukai Trading"
#property version   "1.12"
#property indicator_chart_window
#property indicator_plots 0

//+------------------------------------------------------------------+
//| CLI / Visual TDA contract                                         |
//|                                                                  |
//| This indicator is intentionally vendored with metatrader5-cli.    |
//| Keep object prefix, label text, colors, and tooltips stable so    |
//| screenshot agents can pair visual overlays with CLI JSON context. |
//|                                                                  |
//| Stable object prefix: EMS_                                        |
//| Stable swing labels: SH/SL/HH/HL/LH/LL                            |
//| Stable panel shape: MS <TF>: <BIAS> | H <kind> <price> | L ...    |
//| Stable BOS label: BULLISH BOS / BEARISH BOS                       |
//| Stable level suffixes: SUPPORT / RESISTANCE                       |
//| Structured pair: mt5 --json analyze structure/topdown             |
//+------------------------------------------------------------------+

input int      InpLookback          = 300;          // Lookback bars
input int      InpPivotBars         = 8;            // Bars left/right for swing pivot
input int      InpInternalPivotBars = 3;            // Internal pivot bars
input int      InpFractalPivotBars  = 1;            // Fractal CHOCH pivot bars
input int      InpMaxSwings         = 10;           // Max swing labels to show
input int      InpExtendBars        = 60;           // Extend structure levels right by bars
input double   InpBreakBufferPips   = 0.2;          // BOS/CHOCH close buffer
input bool     InpShowSwingLabels   = true;         // Show HH/HL/LH/LL labels
input bool     InpShowMarkers       = true;         // Show swing markers
input bool     InpShowLevels        = true;         // Show latest swing high/low levels
input bool     InpShowInternal      = true;         // Show elite internal structure
input bool     InpShowStatePanel    = true;         // Show elite state panel
input bool     InpShowRangeEQ       = true;         // Show active range equilibrium
input bool     InpShowStrongWeak    = true;         // Show strong/weak internal levels
input bool     InpShowFailureMarks  = true;         // Show strong internal failures
input bool     InpShowBiasPanel     = true;         // Show structure bias panel
input bool     InpShowBreakLabels   = true;         // Show BOS labels on current break
input color    InpBullColor         = clrLimeGreen; // Bullish structure color
input color    InpBearColor         = clrTomato;    // Bearish structure color
input color    InpNeutralColor      = clrSilver;    // Neutral/mixed structure color
input color    InpLevelColor        = clrDodgerBlue;// Structure level color
input color    InpEQColor           = C'100,116,139'; // Range EQ color
input color    InpStrongColor       = clrGold;      // Strong internal color
input color    InpWeakColor         = C'148,163,184'; // Weak internal color
input color    InpFailureColor      = clrOrange;    // Strong failure color
input color    InpStateTextColor    = clrWhite;     // Elite state text color
input int      InpLineWidth         = 2;            // Level line width
input int      InpLabelFontSize     = 9;            // Swing label font size
input double   InpLabelOffsetPips   = 4.0;          // Label offset in pips

string g_prefix = "EMS_";
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

struct PivotPoint
  {
   datetime time;
   double   price;
   bool     is_high;
   int      index;
  };

struct StructureEvent
  {
   datetime start_time;
   datetime end_time;
   double   price;
   string   text;
   bool     bullish;
   bool     label_above;
  };

struct EliteState
  {
   int      swing_dir;
   int      internal_dir;
   int      last_ibos_dir;
   int      last_swing_break_index;
   bool     internal_seeded;
   bool     has_range;
   string   last_event;
   string   early_signal;
   double   dealing_high;
   double   dealing_low;
   datetime dealing_high_time;
   datetime dealing_low_time;
   datetime dealing_start_time;
   double   strong_high;
   double   strong_low;
   double   weak_high;
   double   weak_low;
   datetime strong_high_time;
   datetime strong_low_time;
   datetime weak_high_time;
   datetime weak_low_time;
  };

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
//| Adaptive pivot for sniper frames                                  |
//+------------------------------------------------------------------+
int EffectivePivotBars()
  {
   int pivot = MathMax(1, InpPivotBars);
   if(_Period == PERIOD_M1 || _Period == PERIOD_M5)
      return MathMin(pivot, 2);
   if(_Period == PERIOD_M15 || _Period == PERIOD_M30)
      return MathMin(pivot, 3);
   return pivot;
  }

//+------------------------------------------------------------------+
//| Add a swing point                                                  |
//+------------------------------------------------------------------+
void AddSwing(SwingPoint &swings[], int &count, const datetime time_value,
              const double price, const bool is_high, const int index)
  {
   count++;
   ArrayResize(swings, count);
   swings[count - 1].time = time_value;
   swings[count - 1].price = price;
   swings[count - 1].is_high = is_high;
   swings[count - 1].index = index;
   swings[count - 1].kind = "";
  }

//+------------------------------------------------------------------+
//| Add a generic pivot point                                         |
//+------------------------------------------------------------------+
void AddPivot(PivotPoint &pivots[], int &count, const datetime time_value,
              const double price, const bool is_high, const int index)
  {
   count++;
   ArrayResize(pivots, count);
   pivots[count - 1].time = time_value;
   pivots[count - 1].price = price;
   pivots[count - 1].is_high = is_high;
   pivots[count - 1].index = index;
  }

//+------------------------------------------------------------------+
//| Detect pivot swings                                                |
//+------------------------------------------------------------------+
void DetectSwings(const double &high[], const double &low[],
                  const datetime &time[], const int rates_total,
                  SwingPoint &swings[], int &swing_count)
  {
   ArrayResize(swings, 0);
   swing_count = 0;

   int pivot = EffectivePivotBars();
   int lookback = MathMin(InpLookback, rates_total - (pivot * 2) - 1);
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

//+------------------------------------------------------------------+
//| Detect generic pivots for internal/fractal structure              |
//+------------------------------------------------------------------+
void DetectPivots(const double &high[], const double &low[],
                  const datetime &time[], const int rates_total,
                  const int pivot, PivotPoint &pivots[], int &pivot_count)
  {
   ArrayResize(pivots, 0);
   pivot_count = 0;

   int effective_pivot = MathMax(1, pivot);
   int lookback = MathMin(InpLookback, rates_total - (effective_pivot * 2) - 1);
   int start = MathMax(effective_pivot, rates_total - lookback);
   int stop = rates_total - effective_pivot;

   for(int i = start; i < stop; i++)
     {
      bool is_high = true;
      bool is_low = true;

      for(int j = i - effective_pivot; j <= i + effective_pivot; j++)
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
         AddPivot(pivots, pivot_count, time[i], high[i], true, i);
      if(is_low)
         AddPivot(pivots, pivot_count, time[i], low[i], false, i);
     }
  }

//+------------------------------------------------------------------+
//| Classify swings as HH/LH and HL/LL                                |
//+------------------------------------------------------------------+
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
         if(!have_high)
            swings[i].kind = "SH";
         else
            swings[i].kind = (swings[i].price > last_high ? "HH" : "LH");
         last_high = swings[i].price;
         have_high = true;
        }
      else
        {
         if(!have_low)
            swings[i].kind = "SL";
         else
            swings[i].kind = (swings[i].price > last_low ? "HL" : "LL");
         last_low = swings[i].price;
         have_low = true;
        }
     }
  }

//+------------------------------------------------------------------+
//| Find latest swing by side                                          |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| Bias from latest high/low classifications                          |
//+------------------------------------------------------------------+
string StructureBias(const SwingPoint &last_high, const bool have_high,
                     const SwingPoint &last_low, const bool have_low,
                     const double signal_close)
  {
   double buffer = PipsToPrice(InpBreakBufferPips);
   if(have_high && signal_close > last_high.price + buffer)
     {
      bool prior_bearish = have_low && last_high.kind == "LH" && last_low.kind == "LL";
      return prior_bearish ? "BULLISH CHOCH" : "BULLISH BOS";
     }
   if(have_low && signal_close < last_low.price - buffer)
     {
      bool prior_bullish = have_high && last_high.kind == "HH" && last_low.kind == "HL";
      return prior_bullish ? "BEARISH CHOCH" : "BEARISH BOS";
     }
   if(have_high && have_low && last_high.kind == "HH" && last_low.kind == "HL")
      return "BULLISH HH/HL";
   if(have_high && have_low && last_high.kind == "LH" && last_low.kind == "LL")
      return "BEARISH LH/LL";
   return "NEUTRAL / RANGE";
  }

//+------------------------------------------------------------------+
//| Color for structure kind                                           |
//+------------------------------------------------------------------+
color StructureColor(const string kind)
  {
   if(kind == "HH" || kind == "HL")
      return InpBullColor;
   if(kind == "LH" || kind == "LL")
      return InpBearColor;
   return InpNeutralColor;
  }

//+------------------------------------------------------------------+
//| Draw swing label and marker                                        |
//+------------------------------------------------------------------+
void DrawSwing(const SwingPoint &swing, const int ordinal)
  {
   color c = StructureColor(swing.kind);
   double offset = PipsToPrice(InpLabelOffsetPips);
   double label_price = swing.is_high ? swing.price + offset : swing.price - offset;
   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_SW_" + IntegerToString(ordinal);

   if(InpShowMarkers)
     {
      string marker_name = base + "_mk";
      if(ObjectCreate(0, marker_name, OBJ_ARROW, 0, swing.time, swing.price))
        {
         ObjectSetInteger(0, marker_name, OBJPROP_COLOR, c);
         ObjectSetInteger(0, marker_name, OBJPROP_ARROWCODE, swing.is_high ? 234 : 233);
         ObjectSetInteger(0, marker_name, OBJPROP_WIDTH, 1);
         SetObjectDefaults(marker_name, false);
        }
     }

   if(InpShowSwingLabels)
     {
      string text_name = base + "_tx";
      if(ObjectCreate(0, text_name, OBJ_TEXT, 0, swing.time, label_price))
        {
         ObjectSetString(0, text_name, OBJPROP_TEXT, swing.kind);
         ObjectSetInteger(0, text_name, OBJPROP_COLOR, c);
         ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, InpLabelFontSize);
         ObjectSetString(0, text_name, OBJPROP_FONT, "Arial Bold");
         SetObjectDefaults(text_name, false);
        }
     }
  }

//+------------------------------------------------------------------+
//| Draw latest support/resistance structure levels                    |
//+------------------------------------------------------------------+
void DrawLevel(const SwingPoint &swing, const datetime chart_end,
               const string suffix, const color c)
  {
   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_" + suffix;
   if(ObjectCreate(0, name, OBJ_TREND, 0, swing.time, swing.price, chart_end, swing.price))
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, InpLineWidth);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, name, OBJPROP_TOOLTIP,
                      StringFormat("%s %s %.5f", TimeframeLabel(), suffix, swing.price));
      SetObjectDefaults(name, false);
     }
  }

//+------------------------------------------------------------------+
//| Draw current bias panel                                            |
//+------------------------------------------------------------------+
void DrawBiasPanel(const string bias, const SwingPoint &last_high, const bool have_high,
                   const SwingPoint &last_low, const bool have_low)
  {
   if(!InpShowBiasPanel)
      return;

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
                      StringFormat("MS %s: %s | %s | %s", TimeframeLabel(), bias, hi, lo));
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 28);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false);
     }
  }

//+------------------------------------------------------------------+
//| Draw BOS label near latest candle                                  |
//+------------------------------------------------------------------+
void DrawBreakLabel(const string bias, const datetime last_time, const double last_close)
  {
   if(!InpShowBreakLabels)
      return;
   if(StringFind(bias, "BOS") < 0)
      return;

   color c = (StringFind(bias, "BULLISH") >= 0 ? InpBullColor : InpBearColor);
   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_BOS";
   if(ObjectCreate(0, name, OBJ_TEXT, 0, last_time, last_close))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, bias);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize + 1);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
     SetObjectDefaults(name, false);
     }
  }

//+------------------------------------------------------------------+
//| Elite structure helpers                                           |
//+------------------------------------------------------------------+
string BiasText(const int dir)
  {
   if(dir > 0)
      return "Bullish";
   if(dir < 0)
      return "Bearish";
   return "Neutral";
  }

string InternalStateText(const int dir, const bool seeded)
  {
   if(seeded && dir > 0)
      return "Bull Seeded";
   if(seeded && dir < 0)
      return "Bear Seeded";
   if(dir > 0)
      return "Bullish iBOS";
   if(dir < 0)
      return "Bearish iBOS";
   return "Unconfirmed";
  }

string ZoneText(const double price, const EliteState &state)
  {
   if(!state.has_range)
      return "No Range";
   double top = MathMax(state.dealing_high, state.dealing_low);
   double bot = MathMin(state.dealing_high, state.dealing_low);
   double eq = (top + bot) / 2.0;
   if(price > eq)
      return "Premium";
   if(price < eq)
      return "Discount";
   return "EQ";
  }

bool InsideActiveRange(const double price, const int pivot_index, const EliteState &state)
  {
   if(!state.has_range)
      return false;
   double top = MathMax(state.dealing_high, state.dealing_low);
   double bot = MathMin(state.dealing_high, state.dealing_low);
   return price < top && price > bot && pivot_index > state.last_swing_break_index;
  }

void AddStructureEvent(StructureEvent &events[], int &event_count,
                       const datetime start_time, const datetime end_time,
                       const double price, const string text,
                       const bool bullish, const bool label_above)
  {
   event_count++;
   ArrayResize(events, event_count);
   events[event_count - 1].start_time = start_time;
   events[event_count - 1].end_time = end_time;
   events[event_count - 1].price = price;
   events[event_count - 1].text = text;
   events[event_count - 1].bullish = bullish;
   events[event_count - 1].label_above = label_above;
  }

void DrawTrendLine(const string name, const datetime t1, const double p1,
                   const datetime t2, const double p2, const color c,
                   const ENUM_LINE_STYLE style, const int width)
  {
   if(ObjectCreate(0, name, OBJ_TREND, 0, t1, p1, t2, p2))
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_STYLE, style);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
      SetObjectDefaults(name, false);
     }
  }

void DrawTextAtPrice(const string name, const datetime t, const double price,
                     const string text, const color c, const bool above)
  {
   double offset = PipsToPrice(InpLabelOffsetPips);
   double label_price = above ? price + offset : price - offset;
   if(ObjectCreate(0, name, OBJ_TEXT, 0, t, label_price))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, text);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false);
     }
  }

void DrawStatePanel(const EliteState &state, const double last_close)
  {
   if(!InpShowStatePanel)
      return;

   int display_dir = state.internal_dir != 0 ? state.internal_dir : (state.has_range ? state.swing_dir : 0);
   bool display_seeded = state.internal_seeded || (state.internal_dir == 0 && display_dir != 0 && state.has_range);
   string event_text = (state.last_event == "" ? BiasText(state.swing_dir) : state.last_event);
   string signal_text = (state.early_signal == "" ? "Waiting for fCHOCH / iBOS" : state.early_signal);
   string text = StringFormat("EMS v1.12 | %s | Swing %s\nInternal %s | %s\n%s",
                              TimeframeLabel(), event_text,
                              InternalStateText(display_dir, display_seeded),
                              ZoneText(last_close, state), signal_text);

   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_ELITE_STATE";
   if(ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, text);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 54);
      ObjectSetInteger(0, name, OBJPROP_COLOR, InpStateTextColor);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false);
     }
  }

void DrawEliteLevel(const string suffix, const datetime start_time,
                    const double price, const datetime chart_end,
                    const string text, const color c,
                    const ENUM_LINE_STYLE style, const int width)
  {
   if(start_time <= 0 || price == 0.0)
      return;

   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_" + suffix;
   DrawTrendLine(base + "_LN", start_time, price, chart_end, price, c, style, width);
   DrawTextAtPrice(base + "_TX", chart_end, price, text, c, true);
  }

void DrawEliteOverlays(const EliteState &state, const StructureEvent &events[],
                       const int event_count, const datetime chart_end,
                       const double last_close)
  {
   if(!InpShowInternal)
      return;

   for(int i = 0; i < event_count; i++)
     {
      bool is_failure = StringFind(events[i].text, "Fail") >= 0;
      color c = is_failure ? InpFailureColor : (events[i].bullish ? InpBullColor : InpBearColor);
      string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_EV_" + IntegerToString(i);
      if(!is_failure)
         DrawTrendLine(base + "_LN", events[i].start_time, events[i].price,
                       events[i].end_time, events[i].price, c, STYLE_DASH, 1);
      DrawTextAtPrice(base + "_TX", events[i].end_time, events[i].price,
                      events[i].text, c, events[i].label_above);
     }

   if(InpShowRangeEQ && state.has_range)
     {
      double eq = (MathMax(state.dealing_high, state.dealing_low) + MathMin(state.dealing_high, state.dealing_low)) / 2.0;
      DrawTrendLine(g_prefix + _Symbol + "_" + TimeframeLabel() + "_RANGE_EQ",
                    state.dealing_start_time, eq, chart_end, eq, InpEQColor, STYLE_DOT, 1);
     }

   if(InpShowStrongWeak)
     {
      if(state.internal_dir > 0)
        {
         DrawEliteLevel("STRONG_IL", state.strong_low_time, state.strong_low, chart_end,
                        "Strong iL", InpStrongColor, STYLE_SOLID, 2);
         DrawEliteLevel("WEAK_IH", state.weak_high_time, state.weak_high, chart_end,
                        "Weak iH", InpWeakColor, STYLE_DASH, 1);
        }
      else if(state.internal_dir < 0)
        {
         DrawEliteLevel("STRONG_IH", state.strong_high_time, state.strong_high, chart_end,
                        "Strong iH", InpStrongColor, STYLE_SOLID, 2);
         DrawEliteLevel("WEAK_IL", state.weak_low_time, state.weak_low, chart_end,
                        "Weak iL", InpWeakColor, STYLE_DASH, 1);
        }
     }

   DrawStatePanel(state, last_close);
  }

//+------------------------------------------------------------------+
//| Calculate elite market-structure state                            |
//+------------------------------------------------------------------+
void CalculateEliteState(const SwingPoint &swings[], const int swing_count,
                         const double &high[], const double &low[],
                         const datetime &time[], const double &close[],
                         const int rates_total, EliteState &state,
                         StructureEvent &events[], int &event_count)
  {
   state.swing_dir = 0;
   state.internal_dir = 0;
   state.last_ibos_dir = 0;
   state.last_swing_break_index = -1;
   state.internal_seeded = false;
   state.has_range = false;
   state.last_event = "";
   state.early_signal = "";
   state.dealing_high = 0.0;
   state.dealing_low = 0.0;
   state.dealing_high_time = 0;
   state.dealing_low_time = 0;
   state.dealing_start_time = 0;
   state.strong_high = 0.0;
   state.strong_low = 0.0;
   state.weak_high = 0.0;
   state.weak_low = 0.0;
   state.strong_high_time = 0;
   state.strong_low_time = 0;
   state.weak_high_time = 0;
   state.weak_low_time = 0;

   ArrayResize(events, 0);
   event_count = 0;

   PivotPoint internal_pivots[];
   PivotPoint fractal_pivots[];
   int internal_count = 0;
   int fractal_count = 0;
   int swing_pivot = EffectivePivotBars();
   int internal_pivot = MathMax(1, InpInternalPivotBars);
   int fractal_pivot = MathMax(1, InpFractalPivotBars);
   DetectPivots(high, low, time, rates_total, internal_pivot, internal_pivots, internal_count);
   DetectPivots(high, low, time, rates_total, fractal_pivot, fractal_pivots, fractal_count);

   double last_swing_high = 0.0;
   double last_swing_low = 0.0;
   datetime last_swing_high_time = 0;
   datetime last_swing_low_time = 0;
   int last_swing_high_index = -1;
   int last_swing_low_index = -1;
   bool have_swing_high = false;
   bool have_swing_low = false;
   bool high_armed = false;
   bool low_armed = false;

   double last_internal_high = 0.0;
   double last_internal_low = 0.0;
   datetime last_internal_high_time = 0;
   datetime last_internal_low_time = 0;
   int last_internal_high_index = -1;
   int last_internal_low_index = -1;
   bool internal_high_armed = false;
   bool internal_low_armed = false;

   double last_fractal_high = 0.0;
   double last_fractal_low = 0.0;
   bool fractal_high_armed = false;
   bool fractal_low_armed = false;
   int fractal_dir = 0;

   int swing_ptr = 0;
   int internal_ptr = 0;
   int fractal_ptr = 0;
   int start = MathMax(0, rates_total - InpLookback);

   for(int i = start; i < rates_total; i++)
     {
      while(swing_ptr < swing_count && swings[swing_ptr].index + swing_pivot <= i)
        {
         if(swings[swing_ptr].is_high)
           {
            last_swing_high = swings[swing_ptr].price;
            last_swing_high_time = swings[swing_ptr].time;
            last_swing_high_index = swings[swing_ptr].index;
            have_swing_high = true;
            high_armed = true;
           }
         else
           {
            last_swing_low = swings[swing_ptr].price;
            last_swing_low_time = swings[swing_ptr].time;
            last_swing_low_index = swings[swing_ptr].index;
            have_swing_low = true;
            low_armed = true;
           }
         swing_ptr++;
        }

      bool raw_bull_break = high_armed && have_swing_high && close[i] > last_swing_high;
      bool raw_bear_break = low_armed && have_swing_low && close[i] < last_swing_low;
      bool bull_break = raw_bull_break && !raw_bear_break;
      bool bear_break = raw_bear_break && !raw_bull_break;

      if(bull_break)
        {
         string event_text = state.swing_dir < 0 ? "CHOCH" : "BOS";
         AddStructureEvent(events, event_count, last_swing_high_time, time[i],
                           last_swing_high, event_text, true, true);
         state.swing_dir = 1;
         state.last_event = "Bull " + event_text;
         state.last_swing_break_index = i;
         high_armed = false;

         if(have_swing_high && have_swing_low)
           {
            state.has_range = true;
            state.dealing_high = last_swing_high;
            state.dealing_high_time = last_swing_high_time;
            state.dealing_low = last_swing_low;
            state.dealing_low_time = last_swing_low_time;
            state.dealing_start_time = last_swing_high_index < last_swing_low_index ? last_swing_high_time : last_swing_low_time;
           }

         last_internal_high = 0.0;
         last_internal_low = low[i];
         last_internal_high_time = 0;
         last_internal_low_time = time[i];
         last_internal_high_index = -1;
         last_internal_low_index = i;
         internal_high_armed = false;
         internal_low_armed = false;
         state.internal_dir = 1;
         state.internal_seeded = true;
         state.last_ibos_dir = 0;
         state.strong_high = 0.0;
         state.strong_low = low[i];
         state.strong_high_time = 0;
         state.strong_low_time = time[i];
         state.weak_high = state.dealing_high;
         state.weak_low = 0.0;
         state.weak_high_time = state.dealing_high_time;
         state.weak_low_time = 0;
         fractal_high_armed = false;
         fractal_low_armed = false;
         fractal_dir = 0;
         state.early_signal = "";
        }

      if(bear_break)
        {
         string event_text = state.swing_dir > 0 ? "CHOCH" : "BOS";
         AddStructureEvent(events, event_count, last_swing_low_time, time[i],
                           last_swing_low, event_text, false, false);
         state.swing_dir = -1;
         state.last_event = "Bear " + event_text;
         state.last_swing_break_index = i;
         low_armed = false;

         if(have_swing_high && have_swing_low)
           {
            state.has_range = true;
            state.dealing_high = last_swing_high;
            state.dealing_high_time = last_swing_high_time;
            state.dealing_low = last_swing_low;
            state.dealing_low_time = last_swing_low_time;
            state.dealing_start_time = last_swing_high_index < last_swing_low_index ? last_swing_high_time : last_swing_low_time;
           }

         last_internal_high = high[i];
         last_internal_low = 0.0;
         last_internal_high_time = time[i];
         last_internal_low_time = 0;
         last_internal_high_index = i;
         last_internal_low_index = -1;
         internal_high_armed = false;
         internal_low_armed = false;
         state.internal_dir = -1;
         state.internal_seeded = true;
         state.last_ibos_dir = 0;
         state.strong_high = high[i];
         state.strong_low = 0.0;
         state.strong_high_time = time[i];
         state.strong_low_time = 0;
         state.weak_high = 0.0;
         state.weak_low = state.dealing_low;
         state.weak_high_time = 0;
         state.weak_low_time = state.dealing_low_time;
         fractal_high_armed = false;
         fractal_low_armed = false;
         fractal_dir = 0;
         state.early_signal = "";
        }

      if(!bull_break && !bear_break && state.has_range)
        {
         if(state.swing_dir > 0 && high[i] > state.dealing_high)
           {
            state.dealing_high = high[i];
            state.dealing_high_time = time[i];
           }
         if(state.swing_dir < 0 && low[i] < state.dealing_low)
           {
            state.dealing_low = low[i];
            state.dealing_low_time = time[i];
           }
        }

      while(internal_ptr < internal_count && internal_pivots[internal_ptr].index + internal_pivot <= i)
        {
         PivotPoint pivot = internal_pivots[internal_ptr];
         if(InsideActiveRange(pivot.price, pivot.index, state))
           {
            if(pivot.is_high)
              {
               last_internal_high = pivot.price;
               last_internal_high_time = pivot.time;
               last_internal_high_index = pivot.index;
               internal_high_armed = true;
              }
            else
              {
               last_internal_low = pivot.price;
               last_internal_low_time = pivot.time;
               last_internal_low_index = pivot.index;
               internal_low_armed = true;
              }
           }
         internal_ptr++;
        }

      while(fractal_ptr < fractal_count && fractal_pivots[fractal_ptr].index + fractal_pivot <= i)
        {
         PivotPoint pivot = fractal_pivots[fractal_ptr];
         if(InsideActiveRange(pivot.price, pivot.index, state))
           {
            if(pivot.is_high)
              {
               last_fractal_high = pivot.price;
               fractal_high_armed = true;
              }
            else
              {
               last_fractal_low = pivot.price;
               fractal_low_armed = true;
              }
           }
         fractal_ptr++;
        }

      double range_top = state.has_range ? MathMax(state.dealing_high, state.dealing_low) : 0.0;
      double range_bot = state.has_range ? MathMin(state.dealing_high, state.dealing_low) : 0.0;

      bool bull_fractal_break = state.has_range && fractal_high_armed && last_fractal_high > 0.0 && close[i] > last_fractal_high && close[i] < range_top;
      bool bear_fractal_break = state.has_range && fractal_low_armed && last_fractal_low > 0.0 && close[i] < last_fractal_low && close[i] > range_bot;
      if(bull_fractal_break)
        {
         if(fractal_dir <= 0)
            state.early_signal = state.internal_dir < 0 ? "Bull fCHOCH: internal pullback may start" : "Bull fCHOCH: internal pullback may end";
         fractal_dir = 1;
         fractal_high_armed = false;
        }
      if(bear_fractal_break)
        {
         if(fractal_dir >= 0)
            state.early_signal = state.internal_dir > 0 ? "Bear fCHOCH: internal pullback may start" : "Bear fCHOCH: internal pullback may end";
         fractal_dir = -1;
         fractal_low_armed = false;
        }

      bool bull_ibos = state.has_range && internal_high_armed && last_internal_high > 0.0 && close[i] > last_internal_high && close[i] < range_top;
      bool bear_ibos = state.has_range && internal_low_armed && last_internal_low > 0.0 && close[i] < last_internal_low && close[i] > range_bot;
      bool seeded_bull_ibos = !bull_ibos && state.internal_seeded && state.internal_dir > 0 && state.has_range &&
                              state.weak_high > 0.0 && close[i] > state.weak_high && i > state.last_swing_break_index;
      bool seeded_bear_ibos = !bear_ibos && state.internal_seeded && state.internal_dir < 0 && state.has_range &&
                              state.weak_low > 0.0 && close[i] < state.weak_low && i > state.last_swing_break_index;

      if(bull_ibos)
        {
         AddStructureEvent(events, event_count, last_internal_high_time, time[i],
                           last_internal_high, "iBOS", true, true);
         state.internal_dir = 1;
         state.internal_seeded = false;
         state.last_ibos_dir = 1;
         state.strong_low = last_internal_low;
         state.strong_low_time = last_internal_low_time;
         state.weak_high = range_top;
         state.weak_high_time = state.dealing_high_time;
         internal_high_armed = false;
        }

      if(seeded_bull_ibos)
        {
         AddStructureEvent(events, event_count, state.weak_high_time, time[i],
                           state.weak_high, "iBOS", true, true);
         state.internal_seeded = false;
         state.last_ibos_dir = 1;
         state.weak_high = range_top;
         state.weak_high_time = state.dealing_high_time;
        }

      if(bear_ibos)
        {
         AddStructureEvent(events, event_count, last_internal_low_time, time[i],
                           last_internal_low, "iBOS", false, false);
         state.internal_dir = -1;
         state.internal_seeded = false;
         state.last_ibos_dir = -1;
         state.strong_high = last_internal_high;
         state.strong_high_time = last_internal_high_time;
         state.weak_low = range_bot;
         state.weak_low_time = state.dealing_low_time;
         internal_low_armed = false;
        }

      if(seeded_bear_ibos)
        {
         AddStructureEvent(events, event_count, state.weak_low_time, time[i],
                           state.weak_low, "iBOS", false, false);
         state.internal_seeded = false;
         state.last_ibos_dir = -1;
         state.weak_low = range_bot;
         state.weak_low_time = state.dealing_low_time;
        }

      bool failed_bull_internal = state.internal_dir > 0 && state.strong_low > 0.0 && close[i] < state.strong_low;
      bool failed_bear_internal = state.internal_dir < 0 && state.strong_high > 0.0 && close[i] > state.strong_high;

      if(failed_bull_internal)
        {
         if(InpShowFailureMarks)
            AddStructureEvent(events, event_count, time[i], time[i], state.strong_low,
                              "Strong iL Fail", false, false);
         state.internal_dir = -1;
         state.internal_seeded = false;
         state.last_ibos_dir = -1;
         state.strong_low = 0.0;
         state.strong_low_time = 0;
         state.early_signal = "Bull strong iL failed";
        }

      if(failed_bear_internal)
        {
         if(InpShowFailureMarks)
            AddStructureEvent(events, event_count, time[i], time[i], state.strong_high,
                              "Strong iH Fail", true, true);
         state.internal_dir = 1;
         state.internal_seeded = false;
         state.last_ibos_dir = 1;
         state.strong_high = 0.0;
         state.strong_high_time = 0;
         state.early_signal = "Bear strong iH failed";
        }
     }
  }

//+------------------------------------------------------------------+
//| Main rendering                                                     |
//+------------------------------------------------------------------+
void RenderStructure(const double &high[], const double &low[],
                     const datetime &time[], const double &close[],
                     const int rates_total)
  {
   ObjectsDeleteAll(0, g_prefix);

   SwingPoint swings[];
   int swing_count = 0;
   DetectSwings(high, low, time, rates_total, swings, swing_count);
   ClassifySwings(swings, swing_count);

   SwingPoint last_high;
   SwingPoint last_low;
   bool have_high = LatestSwing(swings, swing_count, true, last_high);
   bool have_low = LatestSwing(swings, swing_count, false, last_low);
   int signal_index = MathMax(0, rates_total - 2);
   string bias = StructureBias(last_high, have_high, last_low, have_low, close[signal_index]);

   int shown = 0;
   for(int i = swing_count - 1; i >= 0 && shown < InpMaxSwings; i--)
     {
      DrawSwing(swings[i], shown);
      shown++;
     }

   datetime chart_end = time[rates_total - 1] + InpExtendBars * PeriodSeconds();
   EliteState elite_state;
   StructureEvent elite_events[];
   int elite_event_count = 0;
   CalculateEliteState(swings, swing_count, high, low, time, close, rates_total,
                       elite_state, elite_events, elite_event_count);

   if(InpShowLevels)
     {
      if(have_high)
         DrawLevel(last_high, chart_end, "RESISTANCE", InpBearColor);
      if(have_low)
         DrawLevel(last_low, chart_end, "SUPPORT", InpBullColor);
     }

   DrawBiasPanel(bias, last_high, have_high, last_low, have_low);
   DrawBreakLabel(bias, time[signal_index], close[signal_index]);
   DrawEliteOverlays(elite_state, elite_events, elite_event_count, chart_end, close[rates_total - 1]);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Custom indicator calculation                                      |
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
   int pivot = EffectivePivotBars();
   if(rates_total < (pivot * 2 + 5))
      return(0);

   RenderStructure(high, low, time, close, rates_total);

   return(rates_total);
  }
//+------------------------------------------------------------------+
