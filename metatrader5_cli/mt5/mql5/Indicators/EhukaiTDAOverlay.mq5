//+------------------------------------------------------------------+
//|                                             EhukaiTDAOverlay.mq5  |
//|                  Ehukai Trading - Unified TDA Visual Overlay      |
//|                  v1.24 - Live setup-contract guide                |
//+------------------------------------------------------------------+
#property copyright "Ehukai Trading"
#property version   "1.24"
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
   TDA_MANUAL_ANALYSIS  = 1, // Manual Analysis
   TDA_SNIPER           = 2  // Sniper
  };

input ENUM_TDA_MODE InpMode               = TDA_SNIPER;           // Visual mode
input int           InpLookbackBars       = 300;                  // Lookback bars
input int           InpExtendBars         = 24;                   // Extend active objects
input bool          InpCleanAgentScreenshot = false;              // Agent mode: clean chart
input bool          InpCleanLegacyEhukaiObjects = true;           // Agent mode: clear old Ehukai objects
input bool          InpShowStructure      = true;                 // Show structure
input bool          InpShowEliteStructure = true;                 // Show elite structure state
input bool          InpShowEliteEvents    = false;                // Show elite event history
input bool          InpShowEliteLevels    = false;                // Draw strong/weak internal rails
input bool          InpShowBreakMap       = true;                 // Show recent BOS/CHOCH rails
input bool          InpShowBreakTextLabels = false;               // Label BOS/CHOCH rails
input bool          InpShowLatestBreakLabel = true;               // Label latest BOS/CHOCH
input bool          InpShowTradeGuide     = true;                 // Show manual trade guide
input bool          InpShowTopDownPanel   = true;                 // Show W/D/H4/current bias
input bool          InpShowStatusHeaders  = false;                // Show top-right status headers
input bool          InpShowFVG            = true;                 // Show active FVGs
input bool          InpShowHistoricalFVG  = true;                 // Keep active historical FVGs
input bool          InpShowFVGTextLabels  = false;                // Label FVG zones
input bool          InpShowLiquidity      = false;                // Draw liquidity pools
input bool          InpUseLiquidityContext = true;                // Use liquidity in setup context
input bool          InpShowSweepMarkers   = true;                 // Show subtle sweep markers
input int           InpPivotBars          = 8;                    // Structure pivot bars
input int           InpInternalPivotBars  = 3;                    // Internal pivot bars
input int           InpFractalPivotBars   = 1;                    // Fractal CHOCH pivot bars
input int           InpMaxSwingLabels     = 6;                    // Max swing labels
input int           InpMaxEliteEvents     = 4;                    // Max elite event labels
input int           InpMaxBreakEvents     = 1;                    // Max BOS/CHOCH rails
input int           InpMaxFVGZones        = 12;                   // Max active FVG zones
input bool          InpUseAdaptiveFVGMinGap = true;               // Adapt FVG min size by timeframe
input double        InpMinFVGGapPips      = 1.0;                  // Min FVG size
input double        InpEntryFVGMinGapPips = 0.2;                  // M1/M5 min FVG size
input double        InpSetupFVGMinGapPips = 0.5;                  // M15/M30 min FVG size
input double        InpMaxFVGSizePips     = 80.0;                 // Max FVG size in screenshot mode
input double        InpMaxFVGDistancePips = 160.0;                // Max FVG distance
input int           InpLiquidityLookback  = 14;                   // Liquidity pivot lookback
input int           InpFastLiquidityLookback = 5;                 // M1/M5 liquidity lookback
input int           InpMaxLiquidityPools  = 4;                    // Max liquidity pools
input bool          InpShowSweptLiquidity = true;                 // Include swept pools
input double        InpMaxLiquidityDistancePips = 120.0;          // Max liquidity distance
input double        InpBehindZoneTolerancePips = 15.0;            // Trap liquidity tolerance
input int           InpMaxSweepMarkerAgeBars = 40;                // Max sweep marker age
input bool          InpFillSmallZones     = false;                // Fill small zones
input double        InpMaxFillPips        = 25.0;                 // Max filled-zone size
input bool          InpShowSniperState    = true;                 // Show sniper state
input bool          InpShowOnlyActionableZones = true;            // Sniper: only actionable zones
input int           InpMinTDAScore        = 70;                   // Minimum actionable score
input double        InpGuideEntryProximityPips = 6.0;             // Guide: entry-zone proximity
input bool          InpUseClosedBarSignals = true;                // Confirm signals on closed bar
input double        InpBreakBufferPips    = 0.2;                  // BOS close buffer
input bool          InpAlertOnWatch       = false;                // Alert on watch state
input bool          InpAlertOnArmed       = false;                // Alert on armed state
input bool          InpAlertOnTrigger     = true;                 // Alert on trigger state
input int           InpLabelFontSize      = 8;                    // Label size
input double        InpLabelOffsetPips    = 3.0;                  // Label offset
input color         InpBullColor          = C'134,239,172';       // Bullish color
input color         InpBearColor          = C'248,113,113';       // Bearish color
input color         InpNeutralColor       = clrSilver;            // Neutral color
input color         InpLevelColor         = clrDodgerBlue;        // Structure level color
input color         InpEQColor            = C'100,116,139';       // Elite range EQ color
input color         InpStrongColor        = C'245,158,11';        // Strong internal color
input color         InpWeakColor          = C'148,163,184';       // Weak internal color
input color         InpFailureColor       = clrOrange;            // Strong failure color
input color         InpStateTextColor     = clrBlack;             // Elite state text color
input color         InpGuideBgColor       = C'15,23,42';          // Guide panel background
input color         InpGuideTextColor     = clrWhite;             // Guide panel text
input color         InpLiquidityBuyColor  = clrDeepPink;          // Buy-side liquidity
input color         InpLiquiditySellColor = clrTeal;              // Sell-side liquidity

string g_prefix = "ETDA_";
double g_point;
int    g_digits;
string g_last_alert_key = "";
datetime g_last_alert_bar_time = 0;

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

struct LiquidityCandidate
  {
   bool     valid;
   bool     buy_side;
   datetime pivot_time;
   datetime right_time;
   double   top;
   double   bottom;
   double   level;
   bool     swept;
   int      count;
   double   volume;
   double   distance_pips;
  };

struct SetupContext
  {
   string bias;
   int    bias_dir;
   bool   bull_bos;
   bool   bear_bos;
   bool   bull_choch;
   bool   bear_choch;
   bool   bull_poi_near;
   bool   bear_poi_near;
   bool   bull_poi_touched;
   bool   bear_poi_touched;
   bool   buy_liquidity_swept;
   bool   sell_liquidity_swept;
   bool   buy_opposing_liquidity_front;
   bool   sell_opposing_liquidity_front;
   bool   buy_liquidity_behind_zone;
   bool   sell_liquidity_behind_zone;
   bool   buy_poi_trap_risk;
   bool   sell_poi_trap_risk;
   double nearest_bull_poi_pips;
   double nearest_bear_poi_pips;
   double bull_poi_upper;
   double bull_poi_lower;
   double bear_poi_upper;
   double bear_poi_lower;
   double support_level;
   double resistance_level;
   string state;
   string direction;
   string reason;
   int    score;
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

string TimeframeShortLabel(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      default:         return EnumToString(tf);
     }
  }

int EffectivePivotBars()
  {
   return MathMax(1, InpPivotBars);
  }

int EffectiveLiquidityLookback()
  {
   int length = MathMax(1, InpLiquidityLookback);
   if(_Period == PERIOD_M1 || _Period == PERIOD_M5)
      return MathMin(length, MathMax(1, InpFastLiquidityLookback));
   return length;
  }

double EffectiveFVGMinGapPips()
  {
   double base = MathMax(0.0, InpMinFVGGapPips);
   if(!InpUseAdaptiveFVGMinGap)
      return base;
   if(_Period == PERIOD_M1 || _Period == PERIOD_M5)
      return MathMin(base, MathMax(0.0, InpEntryFVGMinGapPips));
   if(_Period == PERIOD_M15 || _Period == PERIOD_M30)
      return MathMin(base, MathMax(0.0, InpSetupFVGMinGapPips));
   return base;
  }

int ModeMaxFVG()
  {
   if(InpMode == TDA_SNIPER && InpShowOnlyActionableZones)
      return 2;
   int cap = (InpMode == TDA_AGENT_SCREENSHOT ? 2 : 14);
   return MathMax(1, MathMin(InpMaxFVGZones, cap));
  }

int ModeMaxLiquidity()
  {
   if(InpMode == TDA_SNIPER && InpShowOnlyActionableZones)
      return 2;
   int cap = (InpMode == TDA_AGENT_SCREENSHOT ? 4 : 8);
   return MathMax(1, MathMin(InpMaxLiquidityPools, cap));
  }

bool IsSniperMode()
  {
   return InpMode == TDA_SNIPER;
  }

bool CleanAgentScreenshotMode()
  {
   return InpMode == TDA_AGENT_SCREENSHOT && InpCleanAgentScreenshot;
  }

bool DrawLiquidityVisuals()
  {
   return InpShowLiquidity && !CleanAgentScreenshotMode();
  }

void CleanupVisualObjects()
  {
   ObjectsDeleteAll(0, g_prefix);
   if(CleanAgentScreenshotMode() && InpCleanLegacyEhukaiObjects)
     {
      ObjectsDeleteAll(0, "EMS_");
      ObjectsDeleteAll(0, "EFVG_");
      ObjectsDeleteAll(0, "ELS_");
     }
  }

void InitSetupContext(SetupContext &ctx)
  {
   ctx.bias = "NEUTRAL / RANGE";
   ctx.bias_dir = 0;
   ctx.bull_bos = false;
   ctx.bear_bos = false;
   ctx.bull_choch = false;
   ctx.bear_choch = false;
   ctx.bull_poi_near = false;
   ctx.bear_poi_near = false;
   ctx.bull_poi_touched = false;
   ctx.bear_poi_touched = false;
   ctx.buy_liquidity_swept = false;
   ctx.sell_liquidity_swept = false;
   ctx.buy_opposing_liquidity_front = false;
   ctx.sell_opposing_liquidity_front = false;
   ctx.buy_liquidity_behind_zone = false;
   ctx.sell_liquidity_behind_zone = false;
   ctx.buy_poi_trap_risk = false;
   ctx.sell_poi_trap_risk = false;
   ctx.nearest_bull_poi_pips = DBL_MAX;
   ctx.nearest_bear_poi_pips = DBL_MAX;
   ctx.bull_poi_upper = 0.0;
   ctx.bull_poi_lower = 0.0;
   ctx.bear_poi_upper = 0.0;
   ctx.bear_poi_lower = 0.0;
   ctx.support_level = 0.0;
   ctx.resistance_level = 0.0;
   ctx.state = "NO_TRADE";
   ctx.direction = "-";
   ctx.reason = "No actionable alignment";
   ctx.score = 0;
  }

bool PriceInZone(const double price, const double top, const double bottom)
  {
   return price <= top && price >= bottom;
  }

void TrackFVGContext(SetupContext &ctx, const FVGZone &zone, const double current_price)
  {
   double distance = FVGDistancePips(zone, current_price);
   bool touched = PriceInZone(current_price, zone.upper, zone.lower);

   if(zone.is_bullish)
     {
      if(distance < ctx.nearest_bull_poi_pips)
        {
         ctx.nearest_bull_poi_pips = distance;
         ctx.bull_poi_upper = zone.upper;
         ctx.bull_poi_lower = zone.lower;
        }
      ctx.bull_poi_near = true;
      if(touched)
         ctx.bull_poi_touched = true;
     }
   else
     {
      if(distance < ctx.nearest_bear_poi_pips)
        {
         ctx.nearest_bear_poi_pips = distance;
         ctx.bear_poi_upper = zone.upper;
         ctx.bear_poi_lower = zone.lower;
        }
      ctx.bear_poi_near = true;
      if(touched)
         ctx.bear_poi_touched = true;
     }
  }

void TrackLiquidityContext(SetupContext &ctx, const bool buy_side, const bool swept,
                           const double level, const double current_price)
  {
   double behind_tolerance = PipsToPrice(InpBehindZoneTolerancePips);

   if(buy_side)
     {
      if(swept)
         ctx.buy_liquidity_swept = true;
      if(ctx.bear_poi_upper > 0.0 && ctx.bear_poi_lower > 0.0)
        {
         if(level >= current_price && level <= ctx.bear_poi_upper)
            ctx.sell_opposing_liquidity_front = true;
         if(level >= ctx.bear_poi_upper && level <= ctx.bear_poi_upper + behind_tolerance)
            ctx.sell_liquidity_behind_zone = true;
        }
     }
   else
     {
      if(swept)
         ctx.sell_liquidity_swept = true;
      if(ctx.bull_poi_upper > 0.0 && ctx.bull_poi_lower > 0.0)
        {
         if(level >= ctx.bull_poi_lower && level <= current_price)
            ctx.buy_opposing_liquidity_front = true;
         if(level <= ctx.bull_poi_lower && level >= ctx.bull_poi_lower - behind_tolerance)
            ctx.buy_liquidity_behind_zone = true;
        }
     }
  }

void InitLiquidityCandidate(LiquidityCandidate &candidate)
  {
   candidate.valid = false;
   candidate.buy_side = false;
   candidate.pivot_time = 0;
   candidate.right_time = 0;
   candidate.top = 0.0;
   candidate.bottom = 0.0;
   candidate.level = 0.0;
   candidate.swept = false;
   candidate.count = 0;
   candidate.volume = 0.0;
   candidate.distance_pips = DBL_MAX;
  }

void SetLiquidityCandidate(LiquidityCandidate &candidate, const bool buy_side,
                           const datetime pivot_time, const datetime right_time,
                           const double top, const double bottom, const double level,
                           const bool swept, const int count, const double volume,
                           const double distance_pips)
  {
   candidate.valid = true;
   candidate.buy_side = buy_side;
   candidate.pivot_time = pivot_time;
   candidate.right_time = right_time;
   candidate.top = top;
   candidate.bottom = bottom;
   candidate.level = level;
   candidate.swept = swept;
   candidate.count = count;
   candidate.volume = volume;
   candidate.distance_pips = distance_pips;
  }

void SetObjectDefaults(const string name, const bool back, const int zorder)
  {
   ObjectSetInteger(0, name, OBJPROP_BACK, back);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_ZORDER, zorder);
  }

void DrawPanelBackground(const string name, const ENUM_BASE_CORNER corner,
                         const int x, const int y, const int width, const int height,
                         const color bg, const color border, const int zorder)
  {
   if(ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0))
     {
      ObjectSetInteger(0, name, OBJPROP_CORNER, corner);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, name, OBJPROP_XSIZE, width);
      ObjectSetInteger(0, name, OBJPROP_YSIZE, height);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg);
      ObjectSetInteger(0, name, OBJPROP_COLOR, border);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      SetObjectDefaults(name, false, zorder);
     }
  }

void DrawPanelLine(const string name, const ENUM_BASE_CORNER corner,
                   const ENUM_ANCHOR_POINT anchor, const int x, const int y,
                   const string text, const color c, const bool bold,
                   const int zorder)
  {
   if(ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, text);
      ObjectSetInteger(0, name, OBJPROP_CORNER, corner);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, bold ? "Arial Bold" : "Arial");
      SetObjectDefaults(name, false, zorder);
     }
  }

datetime FutureTime(const datetime &time[], const int rates_total)
  {
   int seconds = PeriodSeconds(_Period);
   if(seconds <= 0)
      seconds = 60;
   return time[rates_total - 1] + (datetime)(seconds * InpExtendBars);
  }

int SignalBarIndex(const int rates_total)
  {
   if(rates_total < 2)
      return 0;
   return InpUseClosedBarSignals ? rates_total - 2 : rates_total - 1;
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

void AddPivot(PivotPoint &pivots[], int &count, const datetime t,
              const double price, const bool is_high, const int index)
  {
   count++;
   ArrayResize(pivots, count);
   pivots[count - 1].time = t;
   pivots[count - 1].price = price;
   pivots[count - 1].is_high = is_high;
   pivots[count - 1].index = index;
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

void DetectPivots(const double &high[], const double &low[],
                  const datetime &time[], const int rates_total,
                  const int pivot, PivotPoint &pivots[], int &pivot_count)
  {
   ArrayResize(pivots, 0);
   pivot_count = 0;

   int effective_pivot = MathMax(1, pivot);
   int lookback = MathMin(InpLookbackBars, rates_total - (effective_pivot * 2) - 1);
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

int PivotForTF(const ENUM_TIMEFRAMES tf)
  {
   return MathMax(1, InpPivotBars);
  }

color BiasColor(const string bias)
  {
   if(StringFind(bias, "Bull") >= 0 || StringFind(bias, "BULL") >= 0)
      return InpBullColor;
   if(StringFind(bias, "Bear") >= 0 || StringFind(bias, "BEAR") >= 0)
      return InpBearColor;
   return InpNeutralColor;
  }

string ComputeTFStructureRead(const ENUM_TIMEFRAMES tf)
  {
   MqlRates rates[];
   int copied = CopyRates(_Symbol, tf, 0, 240, rates);
   if(copied < 30)
      return "No data";

   ArraySetAsSeries(rates, false);
   int pivot = PivotForTF(tf);
   int signal = copied - 2;
   if(signal <= pivot * 2)
      return "No data";

   double last_high = 0.0;
   double prev_high = 0.0;
   double last_low = 0.0;
   double prev_low = 0.0;
   bool have_high = false;
   bool have_low = false;

   for(int i = pivot; i <= signal - pivot; i++)
     {
      bool is_high = true;
      bool is_low = true;
      for(int j = i - pivot; j <= i + pivot; j++)
        {
         if(j == i)
            continue;
         if(rates[j].high >= rates[i].high)
            is_high = false;
         if(rates[j].low <= rates[i].low)
            is_low = false;
        }
      if(is_high)
        {
         prev_high = last_high;
         last_high = rates[i].high;
         have_high = true;
        }
      if(is_low)
        {
         prev_low = last_low;
         last_low = rates[i].low;
         have_low = true;
        }
     }

   if(!have_high || !have_low || prev_high == 0.0 || prev_low == 0.0)
      return "Neutral build";

   double close_price = rates[signal].close;
   double buffer = PipsToPrice(InpBreakBufferPips);
   bool hh = last_high > prev_high;
   bool hl = last_low > prev_low;
   bool lh = last_high < prev_high;
   bool ll = last_low < prev_low;

   if(close_price > last_high + buffer)
      return (lh && ll) ? "Bull CHOCH" : "Bull BOS";
   if(close_price < last_low - buffer)
      return (hh && hl) ? "Bear CHOCH" : "Bear BOS";
   if(hh && hl)
      return "Bull HH/HL";
   if(lh && ll)
      return "Bear LH/LL";
   return "Neutral range";
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
   if(!InpShowStatusHeaders)
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
                      StringFormat("TDA v1.24 %s: %s | %s | %s", TimeframeLabel(), bias, hi, lo));
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

void DrawTopDownPanel()
  {
   if(!InpShowTopDownPanel)
      return;

   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_TOPDOWN";
   int x = 14;
   int y = 94;
   DrawPanelBackground(base + "_BG", CORNER_LEFT_UPPER, x, y, 205, 112,
                       InpGuideBgColor, C'55,65,81', 8);
   DrawPanelLine(base + "_T", CORNER_LEFT_UPPER, ANCHOR_LEFT_UPPER, x + 10, y + 8,
                 "TDA v1.24 TOP-DOWN", InpGuideTextColor, true, 9);

   ENUM_TIMEFRAMES frames[5] = {PERIOD_D1, PERIOD_H4, PERIOD_M15, PERIOD_M5, PERIOD_M1};
   for(int i = 0; i < 5; i++)
     {
      string read = ComputeTFStructureRead(frames[i]);
      string line = TimeframeShortLabel(frames[i]) + "  " + read;
      DrawPanelLine(base + "_R" + IntegerToString(i), CORNER_LEFT_UPPER, ANCHOR_LEFT_UPPER,
                    x + 10, y + 27 + i * 16, line, BiasColor(read), false, 9);
     }
  }

string EliteBiasText(const int dir)
  {
   if(dir > 0)
      return "Bullish";
   if(dir < 0)
      return "Bearish";
   return "Neutral";
  }

string EliteInternalText(const int dir, const bool seeded)
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

string EliteZoneText(const double price, const EliteState &state)
  {
   if(!state.has_range)
      return "No Range";
   double eq = (MathMax(state.dealing_high, state.dealing_low) + MathMin(state.dealing_high, state.dealing_low)) / 2.0;
   if(price > eq)
      return "Premium";
   if(price < eq)
      return "Discount";
   return "EQ";
  }

bool EliteInsideRange(const double price, const int pivot_index, const EliteState &state)
  {
   if(!state.has_range)
      return false;
   double top = MathMax(state.dealing_high, state.dealing_low);
   double bot = MathMin(state.dealing_high, state.dealing_low);
   return price < top && price > bot && pivot_index > state.last_swing_break_index;
  }

void AddEliteEvent(StructureEvent &events[], int &event_count,
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

void DrawEliteLine(const string name, const datetime t1, const double price,
                   const datetime t2, const color c,
                   const ENUM_LINE_STYLE style, const int width)
  {
   if(ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price))
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_STYLE, style);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
      SetObjectDefaults(name, false, 3);
     }
  }

void DrawEliteText(const string name, const datetime t, const double price,
                  const string text, const color c, const bool above)
  {
   double y = above ? price + PipsToPrice(InpLabelOffsetPips) : price - PipsToPrice(InpLabelOffsetPips);
   if(ObjectCreate(0, name, OBJ_TEXT, 0, t, y))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, text);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false, 6);
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
   DrawEliteLine(base + "_LN", start_time, price, chart_end, c, style, width);
   DrawEliteText(base + "_TX", chart_end, price, text, c, true);
  }

string CompactBreakText(const StructureEvent &event)
  {
   string arrow = event.bullish ? " ^" : " v";
   if(event.text == "BOS")
      return "BOS" + arrow;
   if(event.text == "CHOCH")
      return "CHOCH" + arrow;
   if(event.text == "iBOS")
      return "iBOS" + arrow;
   return event.text;
  }

int NextNearestUndrawnFVG(const FVGZone &zones[], const int count,
                          const bool &drawn[], const double current_price)
  {
   int best = -1;
   double best_distance = DBL_MAX;
   for(int i = 0; i < count; i++)
     {
      if(drawn[i])
         continue;
      double distance = FVGDistancePips(zones[i], current_price);
      if(distance < best_distance)
        {
         best_distance = distance;
         best = i;
        }
     }
   return best;
  }

void DrawEliteStatePanel(const EliteState &state, const double last_close)
  {
   if(!InpShowStatusHeaders)
      return;

   int display_dir = state.internal_dir != 0 ? state.internal_dir : (state.has_range ? state.swing_dir : 0);
   bool display_seeded = state.internal_seeded || (state.internal_dir == 0 && display_dir != 0 && state.has_range);
   string event_text = state.last_event == "" ? EliteBiasText(state.swing_dir) : state.last_event;
   string signal_text = state.early_signal == "" ? "Waiting for fCHOCH / iBOS" : state.early_signal;
   string text = StringFormat("TDA v1.24 | %s | Swing %s\nInternal %s | %s\n%s",
                              TimeframeLabel(), event_text,
                              EliteInternalText(display_dir, display_seeded),
                              EliteZoneText(last_close, state), signal_text);
   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_ELITE_STATE";
   if(ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, text);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 66);
      ObjectSetInteger(0, name, OBJPROP_COLOR, InpStateTextColor);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false, 8);
     }
  }

void DrawEliteOverlays(const EliteState &state, const StructureEvent &events[],
                       const int event_count, const datetime chart_end,
                       const datetime last_time, const double last_close)
  {
   if(!InpShowEliteStructure)
      return;

   if(InpShowEliteEvents)
     {
      int max_events = MathMax(1, InpMaxEliteEvents);
      int start_event = MathMax(0, event_count - max_events);
      for(int i = start_event; i < event_count; i++)
        {
         bool is_failure = StringFind(events[i].text, "Fail") >= 0;
         color c = is_failure ? InpFailureColor : (events[i].bullish ? InpBullColor : InpBearColor);
         string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_ELITE_EV_" + IntegerToString(i);
         if(!is_failure)
            DrawEliteLine(base + "_LN", events[i].start_time, events[i].price, events[i].end_time, c, STYLE_DASH, 1);
         DrawEliteText(base + "_TX", events[i].end_time, events[i].price, events[i].text, c, events[i].label_above);
        }
     }

   bool show_elite_levels = InpShowEliteLevels && !CleanAgentScreenshotMode();
   if(show_elite_levels && state.has_range)
     {
      double eq = (MathMax(state.dealing_high, state.dealing_low) + MathMin(state.dealing_high, state.dealing_low)) / 2.0;
      DrawEliteLine(g_prefix + _Symbol + "_" + TimeframeLabel() + "_ELITE_EQ",
                    last_time, eq, chart_end, InpEQColor, STYLE_DOT, 1);
     }

   if(show_elite_levels && state.internal_dir > 0)
     {
      DrawEliteLevel("ELITE_STRONG_IL", last_time, state.strong_low, chart_end,
                     "Strong iL", InpStrongColor, STYLE_SOLID, 2);
      DrawEliteLevel("ELITE_WEAK_IH", last_time, state.weak_high, chart_end,
                     "Weak iH", InpWeakColor, STYLE_DASH, 1);
     }
   else if(show_elite_levels && state.internal_dir < 0)
     {
      DrawEliteLevel("ELITE_STRONG_IH", last_time, state.strong_high, chart_end,
                     "Strong iH", InpStrongColor, STYLE_SOLID, 2);
      DrawEliteLevel("ELITE_WEAK_IL", last_time, state.weak_low, chart_end,
                     "Weak iL", InpWeakColor, STYLE_DASH, 1);
     }

   DrawEliteStatePanel(state, last_close);
  }

void DrawBreakMap(const StructureEvent &events[], const int event_count)
  {
   if(!InpShowBreakMap || event_count <= 0)
      return;

   int max_events = MathMax(1, InpMaxBreakEvents);
   if(CleanAgentScreenshotMode())
      max_events = MathMin(max_events, 4);

   int shown = 0;
   for(int i = event_count - 1; i >= 0 && shown < max_events; i--)
     {
      bool is_bos = events[i].text == "BOS";
      bool is_choch = events[i].text == "CHOCH";
      bool is_ibos = events[i].text == "iBOS";
      if(!is_bos && !is_choch && !is_ibos)
         continue;

      color c = events[i].bullish ? InpBullColor : InpBearColor;
      ENUM_LINE_STYLE style = is_ibos ? STYLE_DOT : STYLE_SOLID;
      int width = is_ibos ? 1 : 2;
      string side = events[i].bullish ? "Bull " : "Bear ";
      string text = side + events[i].text;
      string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_BREAK_" + IntegerToString(shown);

      DrawEliteLine(base + "_LN", events[i].start_time, events[i].price, events[i].end_time, c, style, width);
      if(InpShowBreakTextLabels || (InpShowLatestBreakLabel && shown == 0))
         DrawEliteText(base + "_TX", events[i].end_time, events[i].price,
                       InpShowBreakTextLabels ? text : CompactBreakText(events[i]),
                       c, events[i].label_above);
      shown++;
     }
  }

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
   int start = MathMax(0, rates_total - InpLookbackBars);
   int signal_end = SignalBarIndex(rates_total);

   for(int i = start; i <= signal_end; i++)
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

      bool raw_bull_break = high_armed && have_swing_high && close[i] > last_swing_high + PipsToPrice(InpBreakBufferPips);
      bool raw_bear_break = low_armed && have_swing_low && close[i] < last_swing_low - PipsToPrice(InpBreakBufferPips);
      bool bull_break = raw_bull_break && !raw_bear_break;
      bool bear_break = raw_bear_break && !raw_bull_break;

      if(bull_break)
        {
         string event_text = state.swing_dir < 0 ? "CHOCH" : "BOS";
         AddEliteEvent(events, event_count, last_swing_high_time, time[i], last_swing_high, event_text, true, true);
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
         state.weak_high_time = state.dealing_high_time;
         state.weak_low = 0.0;
         state.weak_low_time = 0;
         fractal_high_armed = false;
         fractal_low_armed = false;
         fractal_dir = 0;
         state.early_signal = "";
        }

      if(bear_break)
        {
         string event_text = state.swing_dir > 0 ? "CHOCH" : "BOS";
         AddEliteEvent(events, event_count, last_swing_low_time, time[i], last_swing_low, event_text, false, false);
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
         internal_high_armed = false;
         internal_low_armed = false;
         state.internal_dir = -1;
         state.internal_seeded = true;
         state.last_ibos_dir = 0;
         state.strong_high = high[i];
         state.strong_high_time = time[i];
         state.strong_low = 0.0;
         state.strong_low_time = 0;
         state.weak_high = 0.0;
         state.weak_high_time = 0;
         state.weak_low = state.dealing_low;
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
         if(EliteInsideRange(pivot.price, pivot.index, state))
           {
            if(pivot.is_high)
              {
               last_internal_high = pivot.price;
               last_internal_high_time = pivot.time;
               internal_high_armed = true;
              }
            else
              {
               last_internal_low = pivot.price;
               last_internal_low_time = pivot.time;
               internal_low_armed = true;
              }
           }
         internal_ptr++;
        }

      while(fractal_ptr < fractal_count && fractal_pivots[fractal_ptr].index + fractal_pivot <= i)
        {
         PivotPoint pivot = fractal_pivots[fractal_ptr];
         if(EliteInsideRange(pivot.price, pivot.index, state))
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
      bool seeded_bull_ibos = !bull_ibos && state.internal_seeded && state.internal_dir > 0 && state.weak_high > 0.0 && close[i] > state.weak_high && i > state.last_swing_break_index;
      bool seeded_bear_ibos = !bear_ibos && state.internal_seeded && state.internal_dir < 0 && state.weak_low > 0.0 && close[i] < state.weak_low && i > state.last_swing_break_index;

      if(bull_ibos)
        {
         AddEliteEvent(events, event_count, last_internal_high_time, time[i], last_internal_high, "iBOS", true, true);
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
         AddEliteEvent(events, event_count, state.weak_high_time, time[i], state.weak_high, "iBOS", true, true);
         state.internal_seeded = false;
         state.last_ibos_dir = 1;
         state.weak_high = range_top;
         state.weak_high_time = state.dealing_high_time;
        }
      if(bear_ibos)
        {
         AddEliteEvent(events, event_count, last_internal_low_time, time[i], last_internal_low, "iBOS", false, false);
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
         AddEliteEvent(events, event_count, state.weak_low_time, time[i], state.weak_low, "iBOS", false, false);
         state.internal_seeded = false;
         state.last_ibos_dir = -1;
         state.weak_low = range_bot;
         state.weak_low_time = state.dealing_low_time;
        }

      bool failed_bull_internal = state.internal_dir > 0 && state.strong_low > 0.0 && close[i] < state.strong_low;
      bool failed_bear_internal = state.internal_dir < 0 && state.strong_high > 0.0 && close[i] > state.strong_high;
      if(failed_bull_internal)
        {
         AddEliteEvent(events, event_count, time[i], time[i], state.strong_low, "Strong iL Fail", false, false);
         state.internal_dir = -1;
         state.internal_seeded = false;
         state.last_ibos_dir = -1;
         state.strong_low = 0.0;
         state.strong_low_time = 0;
         state.early_signal = "Bull strong iL failed";
        }
      if(failed_bear_internal)
        {
         AddEliteEvent(events, event_count, time[i], time[i], state.strong_high, "Strong iH Fail", true, true);
         state.internal_dir = 1;
         state.internal_seeded = false;
         state.last_ibos_dir = 1;
         state.strong_high = 0.0;
         state.strong_high_time = 0;
         state.early_signal = "Bear strong iH failed";
        }
     }
  }

void RenderStructure(const double &high[], const double &low[],
                     const datetime &time[], const double &close[],
                     const int rates_total, SetupContext &ctx)
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
   int signal_index = SignalBarIndex(rates_total);
   string bias = StructureBias(last_high, have_high, last_low, have_low, close[signal_index]);
   ctx.bias = bias;
   ctx.bias_dir = StringFind(bias, "BULLISH") >= 0 ? 1 : StringFind(bias, "BEARISH") >= 0 ? -1 : 0;
   ctx.bull_bos = StringFind(bias, "BULLISH BOS") >= 0;
   ctx.bear_bos = StringFind(bias, "BEARISH BOS") >= 0;
   ctx.bull_choch = StringFind(bias, "BULLISH CHOCH") >= 0;
   ctx.bear_choch = StringFind(bias, "BEARISH CHOCH") >= 0;

   int max_labels = MathMax(1, InpMaxSwingLabels);
   if(CleanAgentScreenshotMode())
      max_labels = MathMin(max_labels, 3);
   else if(InpMode == TDA_AGENT_SCREENSHOT)
      max_labels = MathMin(max_labels, 6);
   if(IsSniperMode())
      max_labels = MathMin(max_labels, 4);
   int shown = 0;
   for(int i = swing_count - 1; i >= 0 && shown < max_labels; i--)
     {
      DrawSwing(swings[i], shown);
      shown++;
     }

   datetime chart_end = FutureTime(time, rates_total);
   if(have_high)
     {
      ctx.resistance_level = last_high.price;
      DrawStructureLevel(last_high, chart_end, "RESISTANCE", InpLevelColor);
     }
   if(have_low)
     {
      ctx.support_level = last_low.price;
      DrawStructureLevel(last_low, chart_end, "SUPPORT", InpLevelColor);
     }
   DrawBiasPanel(bias, last_high, have_high, last_low, have_low);
   DrawTopDownPanel();

   EliteState elite_state;
   StructureEvent elite_events[];
   int elite_event_count = 0;
   CalculateEliteState(swings, swing_count, high, low, time, close, rates_total,
                       elite_state, elite_events, elite_event_count);
   DrawBreakMap(elite_events, elite_event_count);
   DrawEliteOverlays(elite_state, elite_events, elite_event_count, chart_end, time[signal_index], close[signal_index]);
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

bool FVGDisplayAllowed(const FVGZone &zone, const double current_price)
  {
   if(InpMaxFVGSizePips > 0 && zone.gap_pips > InpMaxFVGSizePips)
      return false;
   if(InpMaxFVGDistancePips > 0 && FVGDistancePips(zone, current_price) > InpMaxFVGDistancePips)
      return false;
   return true;
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
      ObjectSetInteger(0, rect, OBJPROP_WIDTH, zone.is_partial ? 1 : 2);
      ObjectSetString(0, rect, OBJPROP_TOOLTIP,
                      StringFormat("%s %.5f-%.5f", label_text, zone.lower, zone.upper));
      SetObjectDefaults(rect, true, 0);
     }

   double mid = (zone.upper + zone.lower) / 2.0;
   string midline = base + "_m";
   if(ObjectCreate(0, midline, OBJ_TREND, 0, zone.time_start, mid, chart_end, mid))
     {
      ObjectSetInteger(0, midline, OBJPROP_COLOR, c);
      ObjectSetInteger(0, midline, OBJPROP_STYLE, zone.is_partial ? STYLE_DOT : STYLE_DASH);
      ObjectSetInteger(0, midline, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, midline, OBJPROP_RAY_RIGHT, false);
      SetObjectDefaults(midline, false, 1);
     }

   if(InpShowFVGTextLabels)
     {
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
  }

void RenderFVGs(const double &open[], const double &high[], const double &low[],
                const double &close[], const datetime &time[], const int rates_total,
                SetupContext &ctx)
  {
   if(!InpShowFVG)
      return;

   int lookback = MathMin(InpLookbackBars, rates_total - 3);
   int start = MathMax(0, rates_total - lookback);
   double min_gap = PipsToPrice(EffectiveFVGMinGapPips());
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
         if(!FVGDisplayAllowed(z, current_price))
            continue;
         AddFVG(zones, count, z);
        }
     }

   datetime chart_end = FutureTime(time, rates_total);
   datetime label_time = time[rates_total - 1] + (datetime)(MathMax(2, InpExtendBars / 6) * PeriodSeconds(_Period));

   for(int i = 0; i < count; i++)
      TrackFVGContext(ctx, zones[i], current_price);

   if(IsSniperMode() && InpShowOnlyActionableZones)
     {
      int best_bull = -1;
      int best_bear = -1;
      double best_bull_distance = DBL_MAX;
      double best_bear_distance = DBL_MAX;

      for(int i = 0; i < count; i++)
        {
         double distance = FVGDistancePips(zones[i], current_price);
         if(zones[i].is_bullish && distance < best_bull_distance)
           {
            best_bull_distance = distance;
            best_bull = i;
           }
         if(!zones[i].is_bullish && distance < best_bear_distance)
           {
            best_bear_distance = distance;
            best_bear = i;
           }
        }

      bool show_bull = ctx.bias_dir >= 0;
      bool show_bear = ctx.bias_dir <= 0;
      int shown_sniper = 0;
      if(show_bull && best_bull >= 0)
        {
         DrawFVG(zones[best_bull], shown_sniper, chart_end, label_time);
         shown_sniper++;
        }
      if(show_bear && best_bear >= 0)
         DrawFVG(zones[best_bear], shown_sniper, chart_end, label_time);
      return;
     }

   int shown = 0;
   int max_fvg = ModeMaxFVG();
   if(InpShowHistoricalFVG)
     {
      bool drawn[];
      ArrayResize(drawn, count);
      ArrayInitialize(drawn, false);
      while(shown < max_fvg)
        {
         int idx = NextNearestUndrawnFVG(zones, count, drawn, current_price);
         if(idx < 0)
            break;
         drawn[idx] = true;
         DrawFVG(zones[idx], shown, chart_end, label_time);
         shown++;
        }
      return;
     }

   for(int i = count - 1; i >= 0 && shown < max_fvg; i--)
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
               const double bottom, const double &high[], const double &low[],
               const double &close[], const datetime &time[],
               const int last_index, datetime &swept_time)
  {
   swept_time = 0;
   for(int j = start_index + 1; j <= last_index; j++)
     {
      if(buy_side && high[j] > top && close[j] <= top)
        {
         swept_time = time[j];
         return true;
        }
      if(!buy_side && low[j] < bottom && close[j] >= bottom)
        {
         swept_time = time[j];
         return true;
        }
     }
   return false;
  }

double LiquidityDistancePips(const double top, const double bottom, const double current_price)
  {
   double d = 0.0;
   if(current_price > top)
      d = current_price - top;
   else if(current_price < bottom)
      d = bottom - current_price;
   return d / PipsToPrice(1.0);
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
   if(ObjectCreate(0, label, OBJ_TEXT, 0, right_time, y))
     {
      ObjectSetString(0, label, OBJPROP_TEXT, text);
      ObjectSetInteger(0, label, OBJPROP_COLOR, c);
      ObjectSetInteger(0, label, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, label, OBJPROP_FONT, "Arial Bold");
     SetObjectDefaults(label, false, 5);
     }
  }

void DrawSweepMarker(const int ordinal, const bool buy_side, const datetime swept_time,
                     const double level)
  {
   if(!InpShowSweepMarkers || swept_time <= 0)
      return;

   string side = buy_side ? "BSL sweep" : "SSL sweep";
   color c = C'245,158,11';
   double y = buy_side ? level + PipsToPrice(InpLabelOffsetPips)
                       : level - PipsToPrice(InpLabelOffsetPips);
   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_SWEEP_" + IntegerToString(ordinal);
   if(ObjectCreate(0, name, OBJ_TEXT, 0, swept_time, y))
     {
      ObjectSetString(0, name, OBJPROP_TEXT, side);
      ObjectSetInteger(0, name, OBJPROP_COLOR, c);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, MathMax(7, InpLabelFontSize - 1));
      ObjectSetString(0, name, OBJPROP_FONT, "Arial");
      ObjectSetString(0, name, OBJPROP_TOOLTIP, side + " - liquidity taken and reclaimed");
      SetObjectDefaults(name, false, 6);
     }
  }

bool RecentSweepMarker(const datetime swept_time, const datetime &time[], const int rates_total)
  {
   if(swept_time <= 0)
      return false;
   int age = MathMax(1, InpMaxSweepMarkerAgeBars);
   int start = MathMax(0, rates_total - age);
   return swept_time >= time[start];
  }

void RenderLiquidity(const double &open[], const double &high[], const double &low[],
                     const double &close[], const datetime &time[], const long &tick_volume[],
                     const int rates_total, SetupContext &ctx)
  {
   bool draw_liquidity = DrawLiquidityVisuals();
   if(!draw_liquidity && !InpUseLiquidityContext)
      return;

   int length = MathMax(1, InpLiquidityLookback);
   if(rates_total < length * 2 + 3)
      return;
   int lookback = MathMin(InpLookbackBars, rates_total - (length * 2) - 1);
   int start = MathMax(length, rates_total - lookback);
   int stop = rates_total - length;
   datetime future_time = FutureTime(time, rates_total);
   int signal_index = SignalBarIndex(rates_total);
   double current_price = close[signal_index];
   int drawn = 0;
   int sweep_markers = 0;
   LiquidityCandidate best_buy;
   LiquidityCandidate best_sell;
   InitLiquidityCandidate(best_buy);
   InitLiquidityCandidate(best_sell);

   for(int i = stop - 1; i >= start; i--)
     {
      if(PivotHighAt(i, length, high))
        {
         double top = high[i];
         double bottom = MathMax(open[i], close[i]);
         int count = 0;
         double vol = 0.0;
         PoolStats(i, top, bottom, high, low, tick_volume, rates_total, count, vol);
         datetime swept_time = 0;
         bool swept = FindSweep(true, i, top, bottom, high, low, close, time, signal_index, swept_time);
         double distance = LiquidityDistancePips(top, bottom, current_price);
          if(InpUseLiquidityContext)
             TrackLiquidityContext(ctx, true, swept, top, current_price);
          if(!draw_liquidity && swept && count > 0 && sweep_markers < 2
             && RecentSweepMarker(swept_time, time, rates_total)
             && (InpMaxLiquidityDistancePips <= 0 || distance <= InpMaxLiquidityDistancePips))
            {
             DrawSweepMarker(sweep_markers, true, swept_time, top);
             sweep_markers++;
            }
          if(count > 0 && (!swept || InpShowSweptLiquidity)
             && (InpMaxLiquidityDistancePips <= 0 || distance <= InpMaxLiquidityDistancePips))
            {
             if(IsSniperMode() && InpShowOnlyActionableZones)
               {
                if(distance < best_buy.distance_pips)
                   SetLiquidityCandidate(best_buy, true, time[i], swept ? swept_time : future_time,
                                         top, bottom, top, swept, count, vol, distance);
               }
             else if(draw_liquidity)
               {
                DrawLiquidity(drawn, true, time[i], swept ? swept_time : future_time,
                              top, bottom, top, swept, count, vol);
                drawn++;
               }
            }
        }
      if(draw_liquidity && !IsSniperMode() && drawn >= ModeMaxLiquidity())
         break;
      if(PivotLowAt(i, length, low))
        {
         double bottom = low[i];
         double top = MathMin(open[i], close[i]);
         int count = 0;
         double vol = 0.0;
         PoolStats(i, top, bottom, high, low, tick_volume, rates_total, count, vol);
         datetime swept_time = 0;
         bool swept = FindSweep(false, i, top, bottom, high, low, close, time, signal_index, swept_time);
         double distance = LiquidityDistancePips(top, bottom, current_price);
          if(InpUseLiquidityContext)
             TrackLiquidityContext(ctx, false, swept, bottom, current_price);
          if(!draw_liquidity && swept && count > 0 && sweep_markers < 2
             && RecentSweepMarker(swept_time, time, rates_total)
             && (InpMaxLiquidityDistancePips <= 0 || distance <= InpMaxLiquidityDistancePips))
            {
             DrawSweepMarker(sweep_markers, false, swept_time, bottom);
             sweep_markers++;
            }
          if(count > 0 && (!swept || InpShowSweptLiquidity)
             && (InpMaxLiquidityDistancePips <= 0 || distance <= InpMaxLiquidityDistancePips))
            {
            if(IsSniperMode() && InpShowOnlyActionableZones)
              {
               if(distance < best_sell.distance_pips)
                  SetLiquidityCandidate(best_sell, false, time[i], swept ? swept_time : future_time,
                                        top, bottom, bottom, swept, count, vol, distance);
              }
             else if(draw_liquidity)
               {
                DrawLiquidity(drawn, false, time[i], swept ? swept_time : future_time,
                              top, bottom, bottom, swept, count, vol);
                drawn++;
               }
            }
         }
      if(draw_liquidity && !IsSniperMode() && drawn >= ModeMaxLiquidity())
         break;
     }

   if(draw_liquidity && IsSniperMode() && InpShowOnlyActionableZones)
     {
      bool draw_buy_side = ctx.bias_dir <= 0;
      bool draw_sell_side = ctx.bias_dir >= 0;
      if(draw_buy_side && best_buy.valid)
        {
         DrawLiquidity(drawn, best_buy.buy_side, best_buy.pivot_time, best_buy.right_time,
                       best_buy.top, best_buy.bottom, best_buy.level, best_buy.swept,
                       best_buy.count, best_buy.volume);
         drawn++;
        }
      if(draw_sell_side && best_sell.valid)
         DrawLiquidity(drawn, best_sell.buy_side, best_sell.pivot_time, best_sell.right_time,
                       best_sell.top, best_sell.bottom, best_sell.level, best_sell.swept,
                       best_sell.count, best_sell.volume);
     }
  }

//+------------------------------------------------------------------+
//| Sniper state and alerts                                           |
//+------------------------------------------------------------------+
int ClampScore(const int score)
  {
   return MathMax(0, MathMin(100, score));
  }

void EvaluateSetupState(SetupContext &ctx)
  {
   int buy_score = 0;
   int sell_score = 0;

   if(ctx.bias_dir > 0)
      buy_score += 25;
   else if(ctx.bias_dir == 0)
      buy_score += 8;

   if(ctx.bias_dir < 0)
      sell_score += 25;
   else if(ctx.bias_dir == 0)
      sell_score += 8;

   if(ctx.bull_poi_near)
      buy_score += 20;
   if(ctx.bear_poi_near)
      sell_score += 20;

   if(ctx.bull_poi_touched)
      buy_score += 10;
   if(ctx.bear_poi_touched)
      sell_score += 10;

   if(ctx.sell_liquidity_swept)
      buy_score += 20;
   if(ctx.buy_liquidity_swept)
      sell_score += 20;

   if(ctx.buy_opposing_liquidity_front)
      buy_score += 10;
   if(ctx.sell_opposing_liquidity_front)
      sell_score += 10;

   if(ctx.bull_bos || ctx.bull_choch)
      buy_score += 20;
   if(ctx.bear_bos || ctx.bear_choch)
      sell_score += 20;

   if(ctx.nearest_bull_poi_pips != DBL_MAX && ctx.nearest_bull_poi_pips <= 20.0)
      buy_score += 5;
   if(ctx.nearest_bear_poi_pips != DBL_MAX && ctx.nearest_bear_poi_pips <= 20.0)
      sell_score += 5;

   buy_score = ClampScore(buy_score);
   sell_score = ClampScore(sell_score);

   bool buy_has_poi = ctx.bull_poi_near;
   bool sell_has_poi = ctx.bear_poi_near;
   ctx.buy_poi_trap_risk = ctx.buy_liquidity_behind_zone && !ctx.buy_opposing_liquidity_front;
   ctx.sell_poi_trap_risk = ctx.sell_liquidity_behind_zone && !ctx.sell_opposing_liquidity_front;
   if(ctx.buy_poi_trap_risk)
      buy_score = MathMax(0, buy_score - 25);
   if(ctx.sell_poi_trap_risk)
      sell_score = MathMax(0, sell_score - 25);

   bool buy_armed = ctx.bull_poi_touched || ctx.sell_liquidity_swept;
   bool sell_armed = ctx.bear_poi_touched || ctx.buy_liquidity_swept;
   bool buy_trigger = buy_armed && (ctx.bull_bos || ctx.bull_choch);
   bool sell_trigger = sell_armed && (ctx.bear_bos || ctx.bear_choch);

   if(buy_score >= sell_score)
     {
      ctx.score = buy_score;
      ctx.direction = "BUY";
      if(ctx.buy_poi_trap_risk)
        {
         ctx.state = "NO_TRADE";
         ctx.direction = "-";
         ctx.reason = "Bull POI trap risk: SSL behind zone";
        }
      else if(buy_trigger && buy_score >= InpMinTDAScore)
        {
         ctx.state = "READY_BUY";
         ctx.reason = ctx.bull_choch ? "Bullish close-confirmed CHOCH after POI/sweep"
                                     : "Bullish close-confirmed BOS after POI/sweep";
        }
      else if(buy_armed && buy_score >= InpMinTDAScore)
        {
         ctx.state = "WATCH_BUY";
         ctx.reason = "Bullish POI/sell-side sweep active";
        }
      else if(buy_has_poi && buy_score >= 50)
        {
         ctx.state = "WATCH_BUY";
         ctx.reason = "Bullish POI nearby";
        }
      else
        {
         ctx.state = "NO_TRADE";
         ctx.direction = "-";
         ctx.reason = "Buy score below threshold";
        }
     }
   else
     {
      ctx.score = sell_score;
      ctx.direction = "SELL";
      if(ctx.sell_poi_trap_risk)
        {
         ctx.state = "NO_TRADE";
         ctx.direction = "-";
         ctx.reason = "Bear POI trap risk: BSL behind zone";
        }
      else if(sell_trigger && sell_score >= InpMinTDAScore)
        {
         ctx.state = "READY_SELL";
         ctx.reason = ctx.bear_choch ? "Bearish close-confirmed CHOCH after POI/sweep"
                                     : "Bearish close-confirmed BOS after POI/sweep";
        }
      else if(sell_armed && sell_score >= InpMinTDAScore)
        {
         ctx.state = "WATCH_SELL";
         ctx.reason = "Bearish POI/buy-side sweep active";
        }
      else if(sell_has_poi && sell_score >= 50)
        {
         ctx.state = "WATCH_SELL";
         ctx.reason = "Bearish POI nearby";
        }
      else
        {
         ctx.state = "NO_TRADE";
         ctx.direction = "-";
         ctx.reason = "Sell score below threshold";
        }
     }
  }

color StateColor(const SetupContext &ctx)
  {
   if(StringFind(ctx.state, "BUY") >= 0)
      return InpBullColor;
   if(StringFind(ctx.state, "SELL") >= 0)
      return InpBearColor;
   return InpNeutralColor;
  }

color GuideActionColor(const string action)
  {
   if(StringFind(action, "NO TRADE") >= 0)
      return InpNeutralColor;
   if(StringFind(action, "WAIT") >= 0)
      return InpStrongColor;
   if(StringFind(action, "READY") >= 0)
      return InpGuideTextColor;
   if(StringFind(action, "BUY") >= 0)
      return InpBullColor;
   if(StringFind(action, "SELL") >= 0)
      return InpBearColor;
   return InpGuideTextColor;
  }

string GuidePOIText(const bool bullish, const SetupContext &ctx)
  {
   double upper = bullish ? ctx.bull_poi_upper : ctx.bear_poi_upper;
   double lower = bullish ? ctx.bull_poi_lower : ctx.bear_poi_lower;
   double dist = bullish ? ctx.nearest_bull_poi_pips : ctx.nearest_bear_poi_pips;

   if(upper <= 0.0 || lower <= 0.0 || dist == DBL_MAX)
      return bullish ? "Bull FVG: none nearby" : "Bear FVG: none nearby";

   return StringFormat("%s FVG %.3f-%.3f (%.1fp)",
                       bullish ? "Bull" : "Bear", lower, upper, dist);
  }

string GuideInvalidationText(const bool bullish, const SetupContext &ctx)
  {
   if(bullish && ctx.support_level > 0.0)
      return StringFormat("Invalid below HL %.3f", ctx.support_level);
   if(!bullish && ctx.resistance_level > 0.0)
      return StringFormat("Invalid above LH %.3f", ctx.resistance_level);
   return "Invalidation: wait for clear swing";
  }

void DrawTradeGuide(const SetupContext &ctx, const double current_price)
  {
   if(!InpShowTradeGuide)
      return;

   string action = "NO TRADE - WAIT FOR STRUCTURE";
   string step1 = "Need BOS/CHOCH plus usable FVG";
   string step2 = "Do not force a trade from the middle";
   string step3 = ctx.reason;

   if(ctx.bias_dir > 0)
     {
      bool has_poi = ctx.bull_poi_upper > 0.0 && ctx.bull_poi_lower > 0.0;
      bool poi_below_support = has_poi && ctx.support_level > 0.0 && ctx.bull_poi_upper < ctx.support_level;
      if(ctx.state == "READY_BUY")
         action = "READY BUY - DRY-RUN ONLY";
      else if(ctx.buy_poi_trap_risk)
         action = "NO TRADE - BULL POI TRAP";
      else if(ctx.bull_poi_touched)
         action = "WATCH BUY - IN BULL FVG";
      else if(has_poi && ctx.nearest_bull_poi_pips <= InpGuideEntryProximityPips)
         action = "WATCH BUY - FVG CLOSE";
      else if(poi_below_support)
         action = "WAIT - BULLISH, FVG BELOW HL";
      else if(has_poi)
         action = "WAIT PULLBACK - DO NOT CHASE";
      else
         action = "WAIT - BULLISH, NO BULL FVG";

      if(ctx.buy_poi_trap_risk)
         step1 = "Liquidity: SSL behind POI, wait";
      else if(ctx.buy_opposing_liquidity_front)
         step1 = "Liquidity: SSL in front/cleared";
      else
         step1 = ctx.sell_liquidity_swept ? "Sweep: SSL taken" : "Liquidity: no front clue";
      step2 = GuidePOIText(true, ctx);
      step3 = GuideInvalidationText(true, ctx);
     }
   else if(ctx.bias_dir < 0)
     {
      bool has_poi = ctx.bear_poi_upper > 0.0 && ctx.bear_poi_lower > 0.0;
      bool poi_above_resistance = has_poi && ctx.resistance_level > 0.0 && ctx.bear_poi_lower > ctx.resistance_level;
      if(ctx.state == "READY_SELL")
         action = "READY SELL - DRY-RUN ONLY";
      else if(ctx.sell_poi_trap_risk)
         action = "NO TRADE - BEAR POI TRAP";
      else if(ctx.bear_poi_touched)
         action = "WATCH SELL - IN BEAR FVG";
      else if(has_poi && ctx.nearest_bear_poi_pips <= InpGuideEntryProximityPips)
         action = "WATCH SELL - FVG CLOSE";
      else if(poi_above_resistance)
         action = "WAIT - BEARISH, FVG ABOVE LH";
      else if(has_poi)
         action = "WAIT PULLBACK - DO NOT CHASE";
      else
         action = "WAIT - BEARISH, NO BEAR FVG";

      if(ctx.sell_poi_trap_risk)
         step1 = "Liquidity: BSL behind POI, wait";
      else if(ctx.sell_opposing_liquidity_front)
         step1 = "Liquidity: BSL in front/cleared";
      else
         step1 = ctx.buy_liquidity_swept ? "Sweep: BSL taken" : "Liquidity: no front clue";
      step2 = GuidePOIText(false, ctx);
      step3 = GuideInvalidationText(false, ctx);
     }

   if(ctx.state != "NO_TRADE")
      step1 = StringFormat("%s | Score %d | %s", ctx.state, ctx.score, step1);

   string base = g_prefix + _Symbol + "_" + TimeframeLabel() + "_TRADE_GUIDE";
   int x = 14;
   int y = InpShowTopDownPanel ? 214 : 94;
   DrawPanelBackground(base + "_BG", CORNER_LEFT_UPPER, x, y, 310, 88,
                       InpGuideBgColor, C'55,65,81', 8);
   DrawPanelLine(base + "_L0", CORNER_LEFT_UPPER, ANCHOR_LEFT_UPPER, x + 10, y + 8,
                 "GUIDE: " + action, GuideActionColor(action), true, 9);
   DrawPanelLine(base + "_L1", CORNER_LEFT_UPPER, ANCHOR_LEFT_UPPER, x + 10, y + 27,
                 step1, InpGuideTextColor, false, 9);
   DrawPanelLine(base + "_L2", CORNER_LEFT_UPPER, ANCHOR_LEFT_UPPER, x + 10, y + 45,
                 step2, InpGuideTextColor, false, 9);
   DrawPanelLine(base + "_L3", CORNER_LEFT_UPPER, ANCHOR_LEFT_UPPER, x + 10, y + 63,
                 step3, InpGuideTextColor, false, 9);
  }

void DrawSniperState(const SetupContext &ctx)
  {
   if(!InpShowSniperState || !IsSniperMode())
      return;

   string name = g_prefix + _Symbol + "_" + TimeframeLabel() + "_SNIPER_STATE";
   if(ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
     {
      ObjectSetString(0, name, OBJPROP_TEXT,
                      StringFormat("SNIPER %s | %s | %d | %s",
                                   TimeframeLabel(), ctx.state, ctx.score, ctx.reason));
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, InpShowEliteStructure ? 112 : 48);
      ObjectSetInteger(0, name, OBJPROP_COLOR, StateColor(ctx));
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      SetObjectDefaults(name, false, 7);
     }
  }

void MaybeAlertSniperState(const SetupContext &ctx, const datetime signal_time)
  {
   if(!IsSniperMode() || ctx.state == "NO_TRADE")
      return;

   bool enabled = false;
   if(StringFind(ctx.state, "WATCH") >= 0)
      enabled = InpAlertOnWatch;
   else if(StringFind(ctx.state, "READY") >= 0)
      enabled = InpAlertOnTrigger;

   if(!enabled)
      return;

   string key = _Symbol + "|" + TimeframeLabel() + "|" + ctx.state;
   if(key == g_last_alert_key && signal_time == g_last_alert_bar_time)
      return;

   g_last_alert_key = key;
   g_last_alert_bar_time = signal_time;
   Alert(StringFormat("Ehukai TDA %s %s %s score %d: %s",
                      _Symbol, TimeframeLabel(), ctx.state, ctx.score, ctx.reason));
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
   CleanupVisualObjects();
   if(rates_total < 20)
      return rates_total;

   SetupContext ctx;
   InitSetupContext(ctx);

   RenderStructure(high, low, time, close, rates_total, ctx);
   RenderFVGs(open, high, low, close, time, rates_total, ctx);
   RenderLiquidity(open, high, low, close, time, tick_volume, rates_total, ctx);
   EvaluateSetupState(ctx);
   DrawTradeGuide(ctx, close[SignalBarIndex(rates_total)]);
   DrawSniperState(ctx);
   MaybeAlertSniperState(ctx, time[SignalBarIndex(rates_total)]);

   ChartRedraw(0);
   return rates_total;
  }
