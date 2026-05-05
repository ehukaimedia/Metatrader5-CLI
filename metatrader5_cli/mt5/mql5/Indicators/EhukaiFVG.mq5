//+------------------------------------------------------------------+
//|                                                    EhukaiFVG.mq5 |
//|                                    Ehukai Trading - FVG Detector |
//|              v2.3 - TDA-ready zones and labels                    |
//+------------------------------------------------------------------+
#property copyright "Ehukai Trading"
#property version   "2.30"
#property indicator_chart_window
#property indicator_plots 0

//+------------------------------------------------------------------+
//| CLI / Visual TDA contract                                         |
//|                                                                  |
//| This indicator is intentionally vendored with metatrader5-cli.    |
//| Keep object prefix, label text, colors, and tooltips stable so    |
//| screenshot agents can pair visual overlays with CLI JSON context. |
//|                                                                  |
//| Stable object prefix: EFVG_                                       |
//| Stable label shape: BULL/BEAR FVG OPEN/PARTIAL/FILLED <pips>p    |
//| Stable colors: lime = bullish FVG, red = bearish FVG, gray=filled |
//| Stable geometry: rectangle bounds + upper/lower + dashed midpoint |
//| Structured pair: mt5 --json indicator fvg SYMBOL TF               |
//+------------------------------------------------------------------+

//--- Input parameters
input int      InpLookback       = 100;        // Lookback bars
input bool     InpShowBullish    = true;        // Show Bullish FVGs
input bool     InpShowBearish    = true;        // Show Bearish FVGs
input bool     InpShowFilled     = false;       // Show Filled FVGs
input bool     InpAlertOnEntry   = false;       // Alert when price enters FVG
input color    InpBullColor      = clrLime;     // Bullish border color
input color    InpBearColor      = clrRed;      // Bearish border color
input color    InpBullFill       = clrHoneydew; // Bullish fill color
input color    InpBearFill       = clrMistyRose; // Bearish fill color
input color    InpFilledColor    = clrDimGray;  // Filled FVG color
input int      InpMaxZones       = 4;           // Max active zones to display
input bool     InpFillRects      = false;       // Fill rectangles (off = cleaner TDA)
input int      InpBorderWidth    = 2;           // Border width
input double   InpMinGapPips     = 1.0;         // Minimum gap size (pips)
input bool     InpShrinkOnFill   = true;        // Shrink zones on partial fill
input bool     InpVolumeFilter   = false;       // Volume filter (require above-avg volume)
input double   InpVolumeMult     = 1.5;         // Volume multiplier threshold
input int      InpExtendBars     = 40;          // Extend active zones right by bars
input double   InpMaxDistancePips = 120.0;      // Max distance from price (0 disables)
input bool     InpShowMidline    = true;        // Show zone midpoint line
input bool     InpShowLabels     = true;        // Show TDA-readable labels
input int      InpLabelFontSize  = 8;           // Label font size
input double   InpMaxFillGapPips = 30.0;        // Only fill small zones for clean TDA

//--- Global variables
string         g_prefix = "EFVG_";
int            g_lastAlertBar = 0;
string         g_lastAlertZone = "";
bool           g_wasInZone = false;
double         g_point;
int            g_digits;

//+------------------------------------------------------------------+
//| FVG data structure                                                |
//+------------------------------------------------------------------+
struct FVGZone
  {
   datetime          time_start;    // Candle 3 time (where gap confirmed)
   datetime          time_end;      // End time for drawing
   datetime          time_filled;   // When zone was filled (0 if not)
   double            upper;         // Upper boundary
   double            lower;         // Lower boundary
   double            orig_upper;    // Original upper (before shrink)
   double            orig_lower;    // Original lower (before shrink)
   double            gap_pips;      // Original gap size in pips
   bool              is_bullish;
   bool              is_filled;
   bool              is_partial;    // Partially filled
   int               bar_index;     // Bar index of candle 3
   string            name;
  };

FVGZone g_zones[];
int     g_zone_count = 0;

//+------------------------------------------------------------------+
//| Custom indicator initialization                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_point = _Point;
   g_digits = _Digits;
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Custom indicator deinitialization                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, g_prefix);
   ArrayFree(g_zones);
   g_zone_count = 0;
  }

//+------------------------------------------------------------------+
//| Check if a candle has above-average volume                       |
//+------------------------------------------------------------------+
bool HasHighVolume(int bar, int period = 20)
  {
   if(!InpVolumeFilter)
      return true;

   long vol[];
   if(CopyTickVolume(_Symbol, PERIOD_CURRENT, bar, period, vol) < period)
      return true;

   double avg = 0;
   for(int i = 1; i < period; i++)
      avg += (double)vol[i];
   avg /= (period - 1);

   return ((double)vol[0] > avg * InpVolumeMult);
  }

//+------------------------------------------------------------------+
//| Convert pips to price for current symbol                         |
//+------------------------------------------------------------------+
double PipsToPrice(double pips)
  {
   if(g_digits == 3 || g_digits == 5)
      return pips * g_point * 10;
   else
      return pips * g_point;
   }

//+------------------------------------------------------------------+
//| Current timeframe label                                           |
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
//| Zone status label                                                 |
//+------------------------------------------------------------------+
string ZoneStatus(const FVGZone &zone)
  {
   if(zone.is_filled)
      return "FILLED";
   if(zone.is_partial)
      return "PARTIAL";
   return "OPEN";
  }

//+------------------------------------------------------------------+
//| Distance from current price to zone in pips                       |
//+------------------------------------------------------------------+
double ZoneDistancePips(const FVGZone &zone, const double current_price)
  {
   double distance = 0.0;
   if(current_price > zone.upper)
      distance = current_price - zone.upper;
   else if(current_price < zone.lower)
      distance = zone.lower - current_price;
   return distance / PipsToPrice(1.0);
  }

//+------------------------------------------------------------------+
//| Shared object defaults for clean screenshots                      |
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
//| Detect and process all FVGs                                      |
//+------------------------------------------------------------------+
void DetectFVGs(const double &high[], const double &low[],
                const double &open[], const double &close[],
                const datetime &time[], int rates_total)
  {
   // Clear everything
   ObjectsDeleteAll(0, g_prefix);
   ArrayResize(g_zones, 0);
   g_zone_count = 0;

   int lookback = MathMin(InpLookback, rates_total - 3);
   int start = rates_total - lookback;
   double min_gap = PipsToPrice(InpMinGapPips);

   // Temporary array for all detected zones (before filtering)
   FVGZone temp_zones[];
   int temp_count = 0;

   for(int i = start; i < rates_total - 2; i++)
     {
      int c1 = i;
      int c2 = i + 1;
      int c3 = i + 2;

      // Bullish FVG: gap between candle 1 HIGH and candle 3 LOW
      if(InpShowBullish && low[c3] > high[c1])
        {
         double gap_size = low[c3] - high[c1];
         if(gap_size >= min_gap && HasHighVolume(c2))
           {
            FVGZone zone;
            zone.time_start = time[c3]; // Start from candle 3, not candle 1
            zone.orig_upper = low[c3];
             zone.orig_lower = high[c1];
             zone.upper = zone.orig_upper;
             zone.lower = zone.orig_lower;
             zone.gap_pips = gap_size / PipsToPrice(1.0);
             zone.is_bullish = true;
            zone.is_filled = false;
            zone.is_partial = false;
            zone.time_filled = 0;
            zone.bar_index = c3;

            // Check fill status and shrink
             ProcessFillStatus(zone, high, low, time, c3, rates_total);

            temp_count++;
            ArrayResize(temp_zones, temp_count);
            temp_zones[temp_count - 1] = zone;
           }
        }

      // Bearish FVG: gap between candle 1 LOW and candle 3 HIGH
      if(InpShowBearish && high[c3] < low[c1])
        {
         double gap_size = low[c1] - high[c3];
         if(gap_size >= min_gap && HasHighVolume(c2))
           {
            FVGZone zone;
            zone.time_start = time[c3];
            zone.orig_upper = low[c1];
             zone.orig_lower = high[c3];
             zone.upper = zone.orig_upper;
             zone.lower = zone.orig_lower;
             zone.gap_pips = gap_size / PipsToPrice(1.0);
             zone.is_bullish = false;
            zone.is_filled = false;
            zone.is_partial = false;
            zone.time_filled = 0;
            zone.bar_index = c3;

             ProcessFillStatus(zone, high, low, time, c3, rates_total);

            temp_count++;
            ArrayResize(temp_zones, temp_count);
            temp_zones[temp_count - 1] = zone;
           }
        }
     }

   // Filter: only keep unfilled (and optionally filled) zones
   // Keep only the most recent N unfilled zones
   int unfilled_count = 0;
   double current_price = close[rates_total - 1];

   // Count unfilled from newest to oldest
   for(int i = temp_count - 1; i >= 0; i--)
     {
      if(temp_zones[i].is_filled && !InpShowFilled)
         continue;

      if(InpMaxDistancePips > 0 && ZoneDistancePips(temp_zones[i], current_price) > InpMaxDistancePips)
         continue;

      if(!temp_zones[i].is_filled)
         unfilled_count++;

      int max_zones = MathMax(1, MathMin(InpMaxZones, 4));

      // Skip if we've hit max zones. Cap at four even when an older
      // attached chart/template still has the previous noisy setting.
      if(unfilled_count > max_zones && !temp_zones[i].is_filled)
         continue;

      g_zone_count++;
      ArrayResize(g_zones, g_zone_count);
      temp_zones[i].name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_" +
                           (temp_zones[i].is_bullish ? "B_" : "S_") +
                           IntegerToString(temp_zones[i].bar_index);
      g_zones[g_zone_count - 1] = temp_zones[i];
     }

   datetime chart_end = time[rates_total - 1] + InpExtendBars * PeriodSeconds();
   datetime label_time = time[rates_total - 1] + MathMax(2, MathMin(8, InpExtendBars / 6)) * PeriodSeconds();

   // Draw all visible zones
   for(int i = 0; i < g_zone_count; i++)
      DrawFVGZone(g_zones[i], chart_end, label_time);

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Process fill status — check if zone was filled or partially filled|
//+------------------------------------------------------------------+
void ProcessFillStatus(FVGZone &zone,
                       const double &high[], const double &low[],
                       const datetime &time[],
                       int start_bar, int rates_total)
  {
   double deepest_penetration = 0;

   for(int j = start_bar + 1; j < rates_total; j++)
     {
      if(zone.is_bullish)
        {
         // Bullish FVG: filled when price drops below zone lower
          if(low[j] <= zone.orig_lower)
            {
             zone.is_filled = true;
             zone.time_filled = time[j];
             return;
            }
          // Partial fill: price entered zone from above
          if(low[j] < zone.orig_upper && low[j] > zone.orig_lower)
            {
             zone.is_partial = true;
             if(InpShrinkOnFill)
               {
                double pen = zone.orig_upper - low[j];
               if(pen > deepest_penetration)
                 {
                   deepest_penetration = pen;
                   zone.upper = low[j]; // Shrink upper boundary down
                  }
               }
            }
        }
      else
        {
         // Bearish FVG: filled when price rises above zone upper
          if(high[j] >= zone.orig_upper)
            {
             zone.is_filled = true;
             zone.time_filled = time[j];
             return;
            }
          // Partial fill: price entered zone from below
          if(high[j] > zone.orig_lower && high[j] < zone.orig_upper)
            {
             zone.is_partial = true;
             if(InpShrinkOnFill)
               {
                double pen = high[j] - zone.orig_lower;
               if(pen > deepest_penetration)
                 {
                   deepest_penetration = pen;
                   zone.lower = high[j]; // Shrink lower boundary up
                  }
               }
            }
        }
     }

   // If shrunk to nothing, mark as filled
   double remaining = zone.upper - zone.lower;
   if(remaining < PipsToPrice(0.1))
      zone.is_filled = true;
  }

//+------------------------------------------------------------------+
//| Draw FVG zone for screenshot-based TDA                           |
//+------------------------------------------------------------------+
void DrawFVGZone(const FVGZone &zone, const datetime chart_end, const datetime label_time)
  {
   // End time: use candle time, not wall-clock time, so screenshots are stable
   // across closed markets, weekends, and fast repeated TDA captures.
   datetime end_time;
   if(zone.is_filled && zone.time_filled > 0)
      end_time = zone.time_filled;
   else if(zone.is_filled)
      end_time = zone.time_start + MathMax(3, InpExtendBars / 2) * PeriodSeconds();
   else
      end_time = chart_end;

   // Border color (directional) and fill color (subtle)
   color border_color;
   color fill_color;
   if(zone.is_filled)
     {
      border_color = InpFilledColor;
      fill_color = InpFilledColor;
     }
   else if(zone.is_bullish)
     {
      border_color = InpBullColor;
      fill_color = InpBullFill;
     }
   else
     {
      border_color = InpBearColor;
      fill_color = InpBearFill;
     }

   string status = ZoneStatus(zone);
   string side = zone.is_bullish ? "BULL" : "BEAR";
   double midprice = (zone.upper + zone.lower) / 2.0;
   string tooltip = StringFormat("%s %s FVG %s: %.5f-%.5f, %.1fp",
                                 side, TimeframeLabel(), status,
                                 zone.lower, zone.upper, zone.gap_pips);

   bool fill_rect = InpFillRects && (InpMaxFillGapPips <= 0 || zone.gap_pips <= InpMaxFillGapPips);

   // Main rectangle: only small local gaps may fill; large HTF zones remain
   // outlines so candles stay readable in screenshot TDA.
   string rect_name = zone.name + "_r";
   if(ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0,
                   zone.time_start, zone.upper,
                   end_time, zone.lower))
     {
      ObjectSetInteger(0, rect_name, OBJPROP_COLOR, fill_rect ? fill_color : border_color);
      ObjectSetInteger(0, rect_name, OBJPROP_FILL, fill_rect);
      ObjectSetInteger(0, rect_name, OBJPROP_WIDTH, InpBorderWidth);
      ObjectSetInteger(0, rect_name, OBJPROP_STYLE, zone.is_filled ? STYLE_DOT : STYLE_SOLID);
      ObjectSetString(0, rect_name, OBJPROP_TOOLTIP, tooltip);
      SetObjectDefaults(rect_name, true);
     }

   // Upper boundary line.
   string upper_name = zone.name + "_u";
   if(ObjectCreate(0, upper_name, OBJ_TREND, 0,
                   zone.time_start, zone.upper, end_time, zone.upper))
     {
      ObjectSetInteger(0, upper_name, OBJPROP_COLOR, border_color);
      ObjectSetInteger(0, upper_name, OBJPROP_STYLE, zone.is_filled ? STYLE_DOT : STYLE_SOLID);
      ObjectSetInteger(0, upper_name, OBJPROP_WIDTH, InpBorderWidth);
      ObjectSetInteger(0, upper_name, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, upper_name, OBJPROP_TOOLTIP, tooltip);
      SetObjectDefaults(upper_name, false);
     }

   // Lower boundary line.
   string lower_name = zone.name + "_l";
   if(ObjectCreate(0, lower_name, OBJ_TREND, 0,
                   zone.time_start, zone.lower, end_time, zone.lower))
     {
      ObjectSetInteger(0, lower_name, OBJPROP_COLOR, border_color);
      ObjectSetInteger(0, lower_name, OBJPROP_STYLE, zone.is_filled ? STYLE_DOT : STYLE_SOLID);
      ObjectSetInteger(0, lower_name, OBJPROP_WIDTH, InpBorderWidth);
      ObjectSetInteger(0, lower_name, OBJPROP_RAY_RIGHT, false);
      ObjectSetString(0, lower_name, OBJPROP_TOOLTIP, tooltip);
      SetObjectDefaults(lower_name, false);
     }

   if(InpShowMidline)
     {
      string mid_name = zone.name + "_m";
      if(ObjectCreate(0, mid_name, OBJ_TREND, 0,
                      zone.time_start, midprice, end_time, midprice))
        {
         ObjectSetInteger(0, mid_name, OBJPROP_COLOR, border_color);
         ObjectSetInteger(0, mid_name, OBJPROP_STYLE, STYLE_DASH);
         ObjectSetInteger(0, mid_name, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, mid_name, OBJPROP_RAY_RIGHT, false);
         ObjectSetString(0, mid_name, OBJPROP_TOOLTIP, tooltip);
         SetObjectDefaults(mid_name, false);
        }
     }

   if(InpShowLabels)
     {
      string label_name = zone.name + "_t";
      if(ObjectCreate(0, label_name, OBJ_TEXT, 0, label_time, midprice))
        {
         ObjectSetString(0, label_name, OBJPROP_TEXT,
                         StringFormat("%s FVG %s %.1fp", side, status, zone.gap_pips));
         ObjectSetInteger(0, label_name, OBJPROP_COLOR, border_color);
         ObjectSetInteger(0, label_name, OBJPROP_FONTSIZE, InpLabelFontSize);
         ObjectSetString(0, label_name, OBJPROP_FONT, "Arial Bold");
         ObjectSetString(0, label_name, OBJPROP_TOOLTIP, tooltip);
         SetObjectDefaults(label_name, false);
        }
     }
  }

//+------------------------------------------------------------------+
//| Check if current price is inside any active FVG                  |
//+------------------------------------------------------------------+
void CheckAlerts(double bid)
  {
   if(!InpAlertOnEntry)
      return;

   // Find if price is currently inside any active zone
   string current_zone = "";
   string zone_type = "";
   double zone_lower = 0, zone_upper = 0;

   for(int i = 0; i < g_zone_count; i++)
     {
      if(g_zones[i].is_filled)
         continue;

      if(bid >= g_zones[i].lower && bid <= g_zones[i].upper)
        {
         current_zone = g_zones[i].name;
         zone_type = g_zones[i].is_bullish ? "Bullish" : "Bearish";
         zone_lower = g_zones[i].lower;
         zone_upper = g_zones[i].upper;
         break;
        }
     }

   // Only alert on ENTRY — when transitioning from outside to inside a zone
   // or when entering a DIFFERENT zone
   if(current_zone != "" && (!g_wasInZone || current_zone != g_lastAlertZone))
     {
      string msg = StringFormat("%s: Price in %s FVG (%.3f-%.3f)",
                                _Symbol, zone_type, zone_lower, zone_upper);
      Alert(msg);
      g_lastAlertZone = current_zone;
     }

   g_wasInZone = (current_zone != "");
  }

//+------------------------------------------------------------------+
//| Custom indicator iteration function                              |
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
   if(rates_total < 3)
      return(0);

   if(prev_calculated == 0 || rates_total != prev_calculated)
     {
      DetectFVGs(high, low, open, close, time, rates_total);
     }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   CheckAlerts(bid);

   return(rates_total);
  }
//+------------------------------------------------------------------+
