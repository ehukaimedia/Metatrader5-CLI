//+------------------------------------------------------------------+
//|                                         EhukaiMarketStructure.mq5 |
//|                         Ehukai Trading - Visual Market Structure  |
//|                         v1.10 - TDA screenshot structure overlay  |
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
//| Stable object prefix: EMS_                                        |
//| Stable swing labels: SH/SL/HH/HL/LH/LL                            |
//| Stable panel shape: MS <TF>: <BIAS> | H <kind> <price> | L ...    |
//| Stable BOS label: BULLISH BOS / BEARISH BOS                       |
//| Stable level suffixes: SUPPORT / RESISTANCE                       |
//| Structured pair: mt5 --json analyze structure/topdown             |
//+------------------------------------------------------------------+

input int      InpLookback          = 300;          // Lookback bars
input int      InpPivotBars         = 4;            // Bars left/right for swing pivot
input int      InpMaxSwings         = 10;           // Max swing labels to show
input int      InpExtendBars        = 60;           // Extend structure levels right by bars
input bool     InpShowSwingLabels   = true;         // Show HH/HL/LH/LL labels
input bool     InpShowMarkers       = true;         // Show swing markers
input bool     InpShowLevels        = true;         // Show latest swing high/low levels
input bool     InpShowBiasPanel     = true;         // Show structure bias panel
input bool     InpShowBreakLabels   = true;         // Show BOS labels on current break
input color    InpBullColor         = clrLimeGreen; // Bullish structure color
input color    InpBearColor         = clrTomato;    // Bearish structure color
input color    InpNeutralColor      = clrSilver;    // Neutral/mixed structure color
input color    InpLevelColor        = clrDodgerBlue;// Structure level color
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
   string bias = StructureBias(last_high, have_high, last_low, have_low, close[rates_total - 1]);

   int shown = 0;
   for(int i = swing_count - 1; i >= 0 && shown < InpMaxSwings; i--)
     {
      DrawSwing(swings[i], shown);
      shown++;
     }

   datetime chart_end = time[rates_total - 1] + InpExtendBars * PeriodSeconds();
   if(InpShowLevels)
     {
      if(have_high)
         DrawLevel(last_high, chart_end, "RESISTANCE", InpBearColor);
      if(have_low)
         DrawLevel(last_low, chart_end, "SUPPORT", InpBullColor);
     }

   DrawBiasPanel(bias, last_high, have_high, last_low, have_low);
   DrawBreakLabel(bias, time[rates_total - 1], close[rates_total - 1]);
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
