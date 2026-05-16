//+------------------------------------------------------------------+
//|                                      EhukaiVolumeProfilePOC.mq5   |
//|                     Ehukai Trading - Volume Profile POC           |
//|                     v1.00 - TDA-ready POC / VAH / VAL map         |
//+------------------------------------------------------------------+
#property copyright "Ehukai Trading"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

//+------------------------------------------------------------------+
//| CLI / Visual TDA contract                                         |
//|                                                                  |
//| Stable object prefix: EVP_                                        |
//| Stable labels: VP POC <price> | VA <val>-<vah>                    |
//| Stable geometry: right-side histogram + POC + VAH/VAL lines       |
//| Structured pair: mt5 --json ehukai volume-profile SYMBOL TF       |
//+------------------------------------------------------------------+

input int     InpLookbackBars      = 120;          // Closed bars in fixed profile
input int     InpRows              = 40;           // Price rows
input double  InpValueAreaPercent  = 70.0;         // Value area %
input int     InpHistogramWidthBars = 5;           // Max histogram width in bars
input int     InpRightOffsetBars   = 14;           // Right-side offset in bars
input bool    InpShowHistogram     = true;         // Show volume histogram
input bool    InpShowValueArea     = true;         // Show VAH/VAL
input bool    InpShowProfileRange  = false;        // Show profile high/low
input bool    InpShowLabels        = true;         // Show short labels
input color   InpHistogramColor    = clrLightSteelBlue;// Histogram color
input color   InpValueAreaColor    = clrCornflowerBlue; // Value area histogram color
input color   InpPocColor          = clrMagenta;   // POC line color
input color   InpValueLineColor    = clrDeepSkyBlue;// VAH/VAL color
input color   InpRangeColor        = clrSilver;    // Profile high/low color
input int     InpLineWidth         = 2;            // POC line width
input int     InpLabelFontSize     = 8;            // Label font size

string g_prefix = "EVP_";
double g_point;
int    g_digits;
datetime g_last_profile_bar_time = 0;

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
//| Timeframe helpers                                                 |
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

void SetObjectDefaults(const string name, const bool back)
  {
   ObjectSetInteger(0, name, OBJPROP_BACK, back);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_ZORDER, 0);
  }

int ClampIndex(const int value, const int upper)
  {
   return MathMax(0, MathMin(upper, value));
  }

//+------------------------------------------------------------------+
//| Value area expansion from POC                                     |
//+------------------------------------------------------------------+
void ComputeValueArea(const double &totals[], const int row_count, const int poc_index,
                      const double value_area_percent, int &va_low, int &va_high,
                      double &va_volume)
  {
   double total = 0.0;
   for(int i = 0; i < row_count; i++)
      total += totals[i];

   double target = total * MathMax(1.0, MathMin(100.0, value_area_percent)) / 100.0;
   va_low = poc_index;
   va_high = poc_index;
   va_volume = totals[poc_index];

   while(va_volume < target && (va_low > 0 || va_high < row_count - 1))
     {
      double above = (va_high < row_count - 1 ? totals[va_high + 1] : -1.0);
      double below = (va_low > 0 ? totals[va_low - 1] : -1.0);
      if(above >= below)
        {
         va_high++;
         va_volume += MathMax(0.0, above);
        }
      else
        {
         va_low--;
         va_volume += MathMax(0.0, below);
        }
     }
  }

//+------------------------------------------------------------------+
//| Draw helpers                                                      |
//+------------------------------------------------------------------+
void DrawLevel(const string suffix, const datetime left_time, const datetime right_time,
               const double price, const color line_color, const int style,
               const int width, const string text)
  {
   string line_name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_" + suffix;
   if(ObjectCreate(0, line_name, OBJ_TREND, 0, left_time, price, right_time, price))
     {
      ObjectSetInteger(0, line_name, OBJPROP_COLOR, line_color);
      ObjectSetInteger(0, line_name, OBJPROP_STYLE, style);
      ObjectSetInteger(0, line_name, OBJPROP_WIDTH, width);
      ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, line_name, OBJPROP_TOOLTIP, text);
      SetObjectDefaults(line_name, false);
     }

   if(InpShowLabels)
     {
      string label_name = line_name + "_label";
      string short_text = "VP " + suffix;
      if(ObjectCreate(0, label_name, OBJ_TEXT, 0, left_time, price))
        {
         ObjectSetString(0, label_name, OBJPROP_TEXT, short_text);
         ObjectSetInteger(0, label_name, OBJPROP_COLOR, line_color);
         ObjectSetInteger(0, label_name, OBJPROP_FONTSIZE, InpLabelFontSize);
         ObjectSetString(0, label_name, OBJPROP_FONT, "Arial Bold");
         ObjectSetString(0, label_name, OBJPROP_TOOLTIP, text);
         SetObjectDefaults(label_name, false);
        }
     }
  }

void DrawHistogramRow(const int index, const datetime left_time, const datetime right_time,
                      const double upper, const double lower, const color fill_color,
                      const double volume)
  {
   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_ROW_" + IntegerToString(index);
   if(ObjectCreate(0, name, OBJ_RECTANGLE, 0, left_time, upper, right_time, lower))
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, fill_color);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_FILL, true);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, fill_color);
      ObjectSetString(0, name, OBJPROP_TOOLTIP,
                      StringFormat("VP row %.5f-%.5f volume %.0f", lower, upper, volume));
      SetObjectDefaults(name, true);
     }
  }

//+------------------------------------------------------------------+
//| Main calculation                                                  |
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

   int row_count = MathMax(8, InpRows);
   int end_index = rates_total - 2; // closed-bar profile for stable TDA reads
   if(end_index < 10)
      return rates_total;
   if(prev_calculated > 0 && g_last_profile_bar_time == time[end_index])
      return rates_total;
   g_last_profile_bar_time = time[end_index];

   int lookback = MathMin(MathMax(10, InpLookbackBars), end_index + 1);
   int start_index = end_index - lookback + 1;

   double profile_high = high[start_index];
   double profile_low = low[start_index];
   for(int i = start_index; i <= end_index; i++)
     {
      profile_high = MathMax(profile_high, high[i]);
      profile_low = MathMin(profile_low, low[i]);
     }
   if(profile_high <= profile_low)
      return rates_total;

   double row_height = (profile_high - profile_low) / (double)row_count;
   double totals[];
   double ups[];
   double downs[];
   ArrayResize(totals, row_count);
   ArrayResize(ups, row_count);
   ArrayResize(downs, row_count);
   ArrayInitialize(totals, 0.0);
   ArrayInitialize(ups, 0.0);
   ArrayInitialize(downs, 0.0);

   for(int i = start_index; i <= end_index; i++)
     {
      double bar_volume = (double)tick_volume[i];
      if(bar_volume <= 0.0)
         continue;
      int first = ClampIndex((int)MathFloor((low[i] - profile_low) / row_height), row_count - 1);
      int last = ClampIndex((int)MathFloor((high[i] - profile_low) / row_height), row_count - 1);
      if(last < first)
        {
         int tmp = first;
         first = last;
         last = tmp;
        }
      int touched = MathMax(1, last - first + 1);
      double share = bar_volume / (double)touched;
      for(int row = first; row <= last; row++)
        {
         totals[row] += share;
         if(close[i] >= open[i])
            ups[row] += share;
         else
            downs[row] += share;
        }
     }

   double max_volume = 0.0;
   double total_volume = 0.0;
   int poc_index = 0;
   for(int row = 0; row < row_count; row++)
     {
      total_volume += totals[row];
      if(totals[row] > max_volume)
        {
         max_volume = totals[row];
         poc_index = row;
        }
     }
   if(total_volume <= 0.0 || max_volume <= 0.0)
      return rates_total;

   int va_low_idx = poc_index;
   int va_high_idx = poc_index;
   double va_volume = 0.0;
   ComputeValueArea(totals, row_count, poc_index, InpValueAreaPercent, va_low_idx, va_high_idx, va_volume);

   double poc = profile_low + ((double)poc_index + 0.5) * row_height;
   double val = profile_low + (double)va_low_idx * row_height;
   double vah = profile_low + ((double)va_high_idx + 1.0) * row_height;
   string tf = TimeframeLabel();
   string summary = StringFormat("VP POC %.5f | VA %.5f-%.5f", poc, val, vah);

   int seconds = PeriodSeconds(_Period);
   if(seconds <= 0)
      seconds = 60;
   datetime hist_left = time[end_index] + (datetime)(seconds * MathMax(1, InpRightOffsetBars));
   datetime max_right = hist_left + (datetime)(seconds * MathMax(1, InpHistogramWidthBars));
   datetime level_left = time[start_index];

   if(InpShowHistogram)
     {
      for(int row = 0; row < row_count; row++)
        {
         double width_ratio = totals[row] / max_volume;
         int width_seconds = (int)MathMax(1.0, MathRound((double)(seconds * MathMax(1, InpHistogramWidthBars)) * width_ratio));
         datetime row_right = hist_left + (datetime)width_seconds;
         double lower = profile_low + (double)row * row_height;
         double upper = lower + row_height;
         color row_color = (row >= va_low_idx && row <= va_high_idx) ? InpValueAreaColor : InpHistogramColor;
         DrawHistogramRow(row, hist_left, row_right, upper, lower, row_color, totals[row]);
        }
     }

   DrawLevel("POC", level_left, max_right, poc, InpPocColor, STYLE_SOLID, InpLineWidth,
             StringFormat("%s %s POC %.5f", tf, _Symbol, poc));

   if(InpShowValueArea)
     {
      DrawLevel("VAH", level_left, max_right, vah, InpValueLineColor, STYLE_DASH, 1,
                StringFormat("%s %s VAH %.5f", tf, _Symbol, vah));
      DrawLevel("VAL", level_left, max_right, val, InpValueLineColor, STYLE_DASH, 1,
                StringFormat("%s %s VAL %.5f", tf, _Symbol, val));
     }

   if(InpShowProfileRange)
     {
      DrawLevel("HIGH", level_left, max_right, profile_high, InpRangeColor, STYLE_DOT, 1,
                StringFormat("%s %s Profile High %.5f", tf, _Symbol, profile_high));
      DrawLevel("LOW", level_left, max_right, profile_low, InpRangeColor, STYLE_DOT, 1,
                StringFormat("%s %s Profile Low %.5f", tf, _Symbol, profile_low));
     }

   if(false && InpShowLabels)
     {
      string name = g_prefix + _Symbol + "_" + tf + "_SUMMARY";
      if(ObjectCreate(0, name, OBJ_TEXT, 0, max_right, poc))
        {
         ObjectSetString(0, name, OBJPROP_TEXT, summary);
         ObjectSetInteger(0, name, OBJPROP_COLOR, InpPocColor);
         ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
         ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
         ObjectSetString(0, name, OBJPROP_TOOLTIP,
                         StringFormat("%s total tick volume %.0f value area %.1f%%", summary, total_volume, InpValueAreaPercent));
         SetObjectDefaults(name, false);
        }
     }

   return rates_total;
  }
