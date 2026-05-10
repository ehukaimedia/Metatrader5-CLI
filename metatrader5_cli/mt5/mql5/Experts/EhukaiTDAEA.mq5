//+------------------------------------------------------------------+
//|                                             EhukaiTDAEA.mq5       |
//|                  Ehukai / Photon SMC Strategy Tester EA          |
//|                  v0.1 - deterministic backtest harness           |
//+------------------------------------------------------------------+
#property strict
#property copyright "Ehukai Trading"
#property version   "1.000"
#property description "Backtest-first Ehukai / Photon SMC EA: TDA setup planner, risk sizing, and adaptive management"

#include <Trade/Trade.mqh>

enum ENUM_EHUKAI_STATUS
  {
   EHUKAI_NO_TRADE = 0,
   EHUKAI_WATCH    = 1,
   EHUKAI_READY    = 2
  };

enum ENUM_ENTRY_MODE
  {
   ENTRY_LIMIT_FVG_MID = 0,
   ENTRY_MARKET_SMOKE  = 1
  };

input group "Strategy Scope"
input string          InpStrategyIdPrefix       = "ehukai-poc";       // Must match CLI prefix
input long            InpMagicOverride          = 0;                  // 0 = known ehukai-poc pair mapping
input ENUM_ENTRY_MODE InpEntryMode              = ENTRY_LIMIT_FVG_MID;
input bool            InpOneActiveTrade         = true;
input bool            InpAllowRolloverWindow    = false;              // FX 21:00-22:59 UTC guard

input group "TDA Timeframes"
input ENUM_TIMEFRAMES InpPermissionTF1          = PERIOD_D1;
input ENUM_TIMEFRAMES InpPermissionTF2          = PERIOD_H4;
input ENUM_TIMEFRAMES InpSetupTF                = PERIOD_M15;
input ENUM_TIMEFRAMES InpEntryTF1               = PERIOD_M5;
input ENUM_TIMEFRAMES InpEntryTF2               = PERIOD_M1;

input group "Setup Filters"
input int             InpLookbackBars           = 300;
input int             InpSwingPivotBars         = 8;
input int             InpInternalPivotBars      = 3;
input int             InpLiquidityPivotBars     = 14;
input int             InpFastLiquidityPivotBars = 5;
input int             InpMaxFvgAgeBars          = 40;
input double          InpMaxEntryDistancePips   = 15.0;
input bool            InpIncludePartialFVG      = false;
input int             InpMaxSweepAgeBars        = 12;
input double          InpBehindZoneTolerancePips = 15.0;
input int             InpMinTDAScore            = 70;
input bool            InpRequireEntryStructure  = true;
input int             InpMaxSpreadPoints        = 30;
input bool            InpSkipFriday             = false;              // Broker-server Friday entry filter
input int             InpMaxInitialRiskPips     = 50;                 // 0 = disabled; caps entry-to-SL distance in pips

input group "Risk"
input double          InpRiskPercent            = 0.25;
input double          InpFixedLots              = 0.0;                // >0 overrides risk percent
input int             InpMinStopPoints          = 80;
input int             InpMinStopPointsJPY       = 150;
input int             InpMinStopPointsMajor     = 80;
input double          InpSLATRFloorMultiplier   = 1.5;
input double          InpSLAnchorBufferATR      = 0.3;
input double          InpSpreadAdjustedATRThreshold = 1.0;
input double          InpDeeperPoolXATR         = 1.0;
input double          InpStopBufferPips         = 1.0;
input double          InpMinRR                  = 1.5;
input double          InpDefaultRR              = 3.0;
input int             InpEntryBufferPoints      = 5;
input bool            InpUseNewsWindowGuard     = false;
input int             InpNewsGuardMinutesBefore = 15;
input int             InpNewsGuardMinutesAfter  = 30;

input group "Volume Profile"
input bool            InpUseVolumeProfile       = true;
input bool            InpHardGatePOCBlock       = false;
input int             InpVolumeProfileBars      = 120;
input int             InpVolumeProfileRows      = 40;
input double          InpVolumeProfileValueAreaPct = 70.0;
input int             InpVolumeProfileScoreWeight = 8;
input double          InpPocBlockDistancePips   = 8.0;

input group "Trade Management"
input bool            InpUseBreakeven           = true;
input double          InpBETriggerR             = 0.80;
input int             InpBEBufferPoints         = 5;
input int             InpChandelierATRPeriod    = 22;
input double          InpChandelierATRMultiplier = 3.0;
input int             InpChandelierLookback     = 22;
input ENUM_TIMEFRAMES InpChandelierTF           = PERIOD_M5;
input int             InpMinSLImprovementPoints = 5;

input group "Journaling"
input bool            InpJournalEnabled         = true;
input string          InpJournalFolder          = "EhukaiTDAEA";
input bool            InpJournalResetOnInit     = false;
input bool            InpJournalNoTrade         = false;
input bool            InpVerbose                = true;

struct StructureRead
  {
   int      direction;       // 1 bull, -1 bear, 0 neutral
   string   stage;
   string   event_type;
   int      event_dir;
   double   last_high;
   double   last_low;
   double   prior_high;
   double   prior_low;
   datetime signal_time;
   bool     ok;
  };

struct FVGChoice
  {
   bool             ok;
   ENUM_TIMEFRAMES  timeframe;
   bool             bullish;
   bool             partial;
   int              age_bars;
   double           upper;
   double           lower;
   double           mid;
   double           distance_pips;
   string           reason;
  };

struct LiquidityRead
  {
   bool   sweep;
   bool   front;
   bool   behind;
   bool   trap;
   bool   deeper_pool_too_close;
   double swept_level;
   double deeper_pool_level;
   int    swept_pivot_age_bars;
   int    swept_event_age_bars;
   datetime sweep_event_time;
   string reason;
  };

struct VPRead
  {
   bool   ok;
   double poc;
   double vah;
   double val;
   double distance_pips;
   int    buy_score;
   int    sell_score;
   bool   buy_block;
   bool   sell_block;
   string context;
   string read;
  };

struct SetupRead
  {
   ENUM_EHUKAI_STATUS status;
   int      direction;
   int      score;
   string   failure;
   string   gates;
   FVGChoice poi;
   LiquidityRead liquidity;
   VPRead   vp;
   double   entry;
   double   sl;
   double   tp;
   double   rr;
   double   risk;
   double   lots;
   double   htf_momentum_d1;
   int      time_since_sweep_pivot_bars;
   int      time_since_sweep_event_bars;
   double   room_to_swing_high_pips;
   double   spread_to_atr_ratio;
   int      m5_m1_event_lag_bars;
  };

CTrade   g_trade;
long     g_magic = 0;
datetime g_last_entry_bar_time = 0;
double   g_last_initial_risk = 0.0;
ulong    g_last_position_id = 0;
double   g_last_htf_momentum_d1 = 0.0;
int      g_last_time_since_sweep_pivot_bars = -1;
int      g_last_time_since_sweep_event_bars = -1;
double   g_last_room_to_swing_high_pips = -1.0;
double   g_last_spread_to_atr_ratio = 0.0;
int      g_last_m5_m1_event_lag_bars = -1;
ulong    g_journaled_deals[];

//+------------------------------------------------------------------+
//| Lifecycle                                                        |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_magic = ResolveMagic(_Symbol);
   g_trade.SetExpertMagicNumber(g_magic);

   if(InpJournalEnabled)
      InitJournals();

   if(InpVerbose)
      PrintFormat("EhukaiTDAEA loaded: symbol=%s magic=%I64d strategy_id=%s-%s",
                  _Symbol, g_magic, InpStrategyIdPrefix, _Symbol);

   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   ManageOpenPosition();

   datetime bar_time = iTime(_Symbol, InpEntryTF1, 1);
   if(bar_time <= 0 || bar_time == g_last_entry_bar_time)
      return;
   g_last_entry_bar_time = bar_time;

   SetupRead setup;
   EvaluateSetup(setup);
   if(InpJournalEnabled && (setup.status != EHUKAI_NO_TRADE || InpJournalNoTrade))
      JournalSetup(setup);

   if(setup.status == EHUKAI_READY)
      PlaceSetup(setup);
  }

double OnTester()
  {
   double profit = TesterStatistics(STAT_PROFIT);
   double drawdown = TesterStatistics(STAT_EQUITY_DD);
   double trades = TesterStatistics(STAT_TRADES);
   if(drawdown <= 0.0)
      return(profit);
   return((profit / drawdown) * MathMax(1.0, trades));
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(!InpJournalEnabled || trans.type != TRADE_TRANSACTION_DEAL_ADD || trans.deal == 0)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;

   const string symbol = HistoryDealGetString(trans.deal, DEAL_SYMBOL);
   const long magic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   if(symbol != _Symbol || magic != g_magic)
      return;

   const ENUM_DEAL_ENTRY entry_type = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(!RememberJournaledDeal(trans.deal))
      return;

   if(entry_type == DEAL_ENTRY_IN)
      JournalEntryDeal(trans.deal);
   else if(entry_type == DEAL_ENTRY_OUT || entry_type == DEAL_ENTRY_INOUT)
      JournalExitDeal(trans.deal);
  }

//+------------------------------------------------------------------+
//| Setup evaluation                                                  |
//+------------------------------------------------------------------+
void EvaluateSetup(SetupRead &setup)
  {
   ResetSetup(setup);

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
     {
      setup.failure = "no tick";
      setup.gates = "tick=fail";
      return;
     }

   const double point = SymbolPoint();
   const double pip = PipSize();
   const int spread_points = point > 0.0 ? (int)MathRound((tick.ask - tick.bid) / point) : (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);

   StructureRead d1;
   StructureRead h4;
   StructureRead m15;
   StructureRead m5;
   StructureRead m1;
   ReadStructure(InpPermissionTF1, InpLookbackBars, InpSwingPivotBars, d1);
   ReadStructure(InpPermissionTF2, InpLookbackBars, InpSwingPivotBars, h4);
   ReadStructure(InpSetupTF, InpLookbackBars, InpSwingPivotBars, m15);
   ReadStructure(InpEntryTF1, InpLookbackBars, InpInternalPivotBars, m5);
   ReadStructure(InpEntryTF2, InpLookbackBars, InpInternalPivotBars, m1);

   const int direction = ResolveDirection(d1, h4, m15);
   setup.direction = direction;

   const bool spread_ok = spread_points <= InpMaxSpreadPoints;
   const bool rollover_ok = InpAllowRolloverWindow || !IsFxRolloverWindow();
   const bool news_ok = NewsWindowOk();
   const bool friday_ok = !InpSkipFriday || !IsFridayUTC();
   const bool structure_ok = direction != 0 && d1.ok && h4.ok && m15.ok;

   FVGChoice fvg;
   FindBestFVG(direction, tick.bid, tick.ask, fvg);
   setup.poi = fvg;

   LiquidityRead liq;
   ReadLiquidity(direction, fvg, tick.bid, tick.ask, liq);
   setup.liquidity = liq;

   VPRead vp;
   ReadVolumeProfile(vp);
   setup.vp = vp;
   const double atr_m5 = ATRPrice(InpEntryTF1, 14);
   setup.htf_momentum_d1 = D1MomentumRatio();
   setup.time_since_sweep_pivot_bars = liq.swept_pivot_age_bars;
   setup.time_since_sweep_event_bars = liq.swept_event_age_bars;
   setup.spread_to_atr_ratio = atr_m5 > 0.0 ? (tick.ask - tick.bid) / atr_m5 : 0.0;
   setup.m5_m1_event_lag_bars = EventLagBarsM1(direction, m5, m1, liq.sweep_event_time);

   const bool entry_confirmed = EntryConfirmed(direction, m5, m1);
   const bool quote_side_ok = fvg.ok && (
      (direction > 0 && fvg.mid <= tick.bid - InpEntryBufferPoints * point) ||
      (direction < 0 && fvg.mid >= tick.ask + InpEntryBufferPoints * point)
   );
   const bool sweep_ok = liq.sweep;
   const bool deeper_pool_ok = !liq.deeper_pool_too_close;
   const bool vp_ok = !InpUseVolumeProfile || !InpHardGatePOCBlock ||
      (direction > 0 ? !vp.buy_block : direction < 0 ? !vp.sell_block : false);
   const bool active_ok = !InpOneActiveTrade || !HasActiveStrategy();

   int score = 0;
   if(direction > 0 && (d1.direction >= 0 || h4.direction >= 0))
      score += 25;
   if(direction < 0 && (d1.direction <= 0 || h4.direction <= 0))
      score += 25;
   if(fvg.ok)
      score += 20;
   if(fvg.ok && PriceInZone(direction > 0 ? tick.bid : tick.ask, fvg.upper, fvg.lower))
      score += 10;
   if(liq.sweep)
      score += 20;
   if(liq.front)
      score += 10;
   if(entry_confirmed)
      score += 20;
   if(vp.ok)
      score += direction > 0 ? vp.buy_score : direction < 0 ? vp.sell_score : 0;
   if(liq.trap)
      score -= 25;
   setup.score = ClampInt(score, 0, 100);

   bool risk_ok = false;
   if(fvg.ok)
      risk_ok = BuildRiskPlan(direction, fvg, tick, setup);
   setup.room_to_swing_high_pips = RoomToSwingExtremePips(direction, setup.entry);

   const bool score_ok = setup.score >= InpMinTDAScore;
   const bool entry_ok = !InpRequireEntryStructure || entry_confirmed;
   const bool blockers =
      !spread_ok || !rollover_ok || !news_ok || !friday_ok || !structure_ok || !fvg.ok || !quote_side_ok ||
      !sweep_ok || !deeper_pool_ok || liq.trap || !vp_ok || !risk_ok || !score_ok || !entry_ok || !active_ok;

   setup.gates = StringFormat(
      "spread=%s(%d/%d);rollover=%s;news=%s;friday=%s;risk_pips=%.1f/%d;structure=%s;fvg=%s;quote_side=%s;liq_sweep=%s;deeper_pool=%s;liq_trap=%s;vp=%s;entry=%s;risk=%s;score=%d/%d;active=%s",
      BoolText(spread_ok), spread_points, InpMaxSpreadPoints,
      BoolText(rollover_ok), BoolText(news_ok), BoolText(friday_ok),
      pip > 0.0 ? setup.risk / pip : 0.0, InpMaxInitialRiskPips,
      BoolText(structure_ok), BoolText(fvg.ok),
      BoolText(quote_side_ok), BoolText(sweep_ok), BoolText(deeper_pool_ok), BoolText(!liq.trap),
      BoolText(vp_ok), BoolText(entry_ok), BoolText(risk_ok),
      setup.score, InpMinTDAScore, BoolText(active_ok)
   );

   if(!blockers)
     {
      setup.status = EHUKAI_READY;
      setup.failure = "";
     }
   else if(friday_ok && structure_ok && fvg.ok && sweep_ok && deeper_pool_ok && !liq.trap && vp_ok && risk_ok && active_ok)
     {
      setup.status = EHUKAI_WATCH;
      setup.failure = FirstFailure(spread_ok, rollover_ok, friday_ok, quote_side_ok, score_ok, entry_ok);
     }
   else
     {
      setup.status = EHUKAI_NO_TRADE;
      setup.failure = FirstFailure(spread_ok, rollover_ok, news_ok, friday_ok, structure_ok, fvg.ok, quote_side_ok,
                                   sweep_ok, deeper_pool_ok, !liq.trap, vp_ok, risk_ok,
                                   score_ok, entry_ok, active_ok);
     }
  }

void ResetSetup(SetupRead &setup)
  {
   setup.status = EHUKAI_NO_TRADE;
   setup.direction = 0;
   setup.score = 0;
   setup.failure = "not evaluated";
   setup.gates = "";
   setup.entry = 0.0;
   setup.sl = 0.0;
   setup.tp = 0.0;
   setup.rr = 0.0;
   setup.risk = 0.0;
   setup.lots = 0.0;
   setup.htf_momentum_d1 = 0.0;
   setup.time_since_sweep_pivot_bars = -1;
   setup.time_since_sweep_event_bars = -1;
   setup.room_to_swing_high_pips = -1.0;
   setup.spread_to_atr_ratio = 0.0;
   setup.m5_m1_event_lag_bars = -1;

   setup.poi.ok = false;
   setup.poi.reason = "none";
   setup.liquidity.sweep = false;
   setup.liquidity.front = false;
   setup.liquidity.behind = false;
   setup.liquidity.trap = false;
   setup.liquidity.deeper_pool_too_close = false;
   setup.liquidity.swept_level = 0.0;
   setup.liquidity.deeper_pool_level = 0.0;
   setup.liquidity.swept_pivot_age_bars = -1;
   setup.liquidity.swept_event_age_bars = -1;
   setup.liquidity.sweep_event_time = 0;
   setup.liquidity.reason = "none";
   setup.vp.ok = false;
   setup.vp.read = "VP: off";
  }

int ResolveDirection(const StructureRead &d1, const StructureRead &h4, const StructureRead &m15)
  {
   if(!d1.ok || !h4.ok || !m15.ok)
      return 0;
   if(d1.direction == 0 || h4.direction == 0 || m15.direction == 0)
      return 0;
   if(d1.direction != m15.direction || h4.direction != m15.direction)
      return 0;
   return m15.direction;
  }

bool EntryConfirmed(const int direction, const StructureRead &m5, const StructureRead &m1)
  {
   if(direction == 0)
      return false;
   if((m5.event_type == "BOS" || m5.event_type == "CHOCH" || m5.event_type == "iBOS") && m5.event_dir == direction)
      return true;
   if((m1.event_type == "BOS" || m1.event_type == "CHOCH" || m1.event_type == "iBOS") && m1.event_dir == direction)
      return true;
   return false;
  }

//+------------------------------------------------------------------+
//| Structure                                                         |
//+------------------------------------------------------------------+
void ReadStructure(const ENUM_TIMEFRAMES tf, const int bars, const int pivot, StructureRead &read)
  {
   read.ok = false;
   read.direction = 0;
   read.stage = "range";
   read.event_type = "";
   read.event_dir = 0;
   read.last_high = 0.0;
   read.last_low = 0.0;
   read.prior_high = 0.0;
   read.prior_low = 0.0;
   read.signal_time = 0;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int copied = CopyRates(_Symbol, tf, 0, MathMax(bars, pivot * 4 + 20), rates);
   if(copied < pivot * 2 + 10)
      return;

   const int signal = 1;
   read.signal_time = rates[signal].time;
   const double signal_close = rates[signal].close;
   const double buffer = PipsToPrice(0.2);
   int highs_found = 0;
   int lows_found = 0;

   for(int i = signal + pivot; i < copied - pivot && (highs_found < 2 || lows_found < 2); i++)
     {
      if(highs_found < 2 && PivotHighAt(rates, copied, i, pivot))
        {
         if(highs_found == 0)
            read.last_high = rates[i].high;
         else
            read.prior_high = rates[i].high;
         highs_found++;
        }
      if(lows_found < 2 && PivotLowAt(rates, copied, i, pivot))
        {
         if(lows_found == 0)
            read.last_low = rates[i].low;
         else
            read.prior_low = rates[i].low;
         lows_found++;
        }
     }

   if(read.last_high <= 0.0 || read.last_low <= 0.0)
      return;

   const bool prior_bullish = read.prior_high > 0.0 && read.prior_low > 0.0 &&
                              read.last_high > read.prior_high && read.last_low > read.prior_low;
   const bool prior_bearish = read.prior_high > 0.0 && read.prior_low > 0.0 &&
                              read.last_high < read.prior_high && read.last_low < read.prior_low;

   if(signal_close > read.last_high + buffer)
     {
      read.direction = 1;
      read.event_dir = 1;
      read.event_type = prior_bearish ? "CHOCH" : "BOS";
      read.stage = read.event_type;
     }
   else if(signal_close < read.last_low - buffer)
     {
      read.direction = -1;
      read.event_dir = -1;
      read.event_type = prior_bullish ? "CHOCH" : "BOS";
      read.stage = read.event_type;
     }
   else if(prior_bullish)
     {
      read.direction = 1;
      read.stage = "HH_HL";
     }
   else if(prior_bearish)
     {
      read.direction = -1;
      read.stage = "LH_LL";
     }
   else
     {
      read.direction = 0;
      read.stage = "range";
     }

   read.ok = true;
  }

bool PivotHighAt(const MqlRates &rates[], const int count, const int index, const int pivot)
  {
   if(index - pivot < 0 || index + pivot >= count)
      return false;
   const double value = rates[index].high;
   for(int k = 1; k <= pivot; k++)
     {
      if(value <= rates[index - k].high || value <= rates[index + k].high)
         return false;
     }
   return true;
  }

bool PivotLowAt(const MqlRates &rates[], const int count, const int index, const int pivot)
  {
   if(index - pivot < 0 || index + pivot >= count)
      return false;
   const double value = rates[index].low;
   for(int k = 1; k <= pivot; k++)
     {
      if(value >= rates[index - k].low || value >= rates[index + k].low)
         return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| FVG / POI                                                         |
//+------------------------------------------------------------------+
void FindBestFVG(const int direction, const double bid, const double ask, FVGChoice &best)
  {
   best.ok = false;
   best.reason = "no aligned FVG";
   if(direction == 0)
      return;

   FVGChoice c1;
   FVGChoice c2;
   FVGChoice c3;
   FindFVGOnTF(InpEntryTF2, direction, bid, ask, c1);
   FindFVGOnTF(InpEntryTF1, direction, bid, ask, c2);
   FindFVGOnTF(InpSetupTF, direction, bid, ask, c3);

   FVGChoice choices[3];
   choices[0] = c1;
   choices[1] = c2;
   choices[2] = c3;
   for(int i = 0; i < 3; i++)
     {
      if(!choices[i].ok)
         continue;
      if(!best.ok || choices[i].distance_pips < best.distance_pips)
         best = choices[i];
     }
  }

void FindFVGOnTF(const ENUM_TIMEFRAMES tf, const int direction, const double bid,
                 const double ask, FVGChoice &choice)
  {
   choice.ok = false;
   choice.timeframe = tf;
   choice.reason = "no FVG";

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int copied = CopyRates(_Symbol, tf, 0, MathMax(80, InpMaxFvgAgeBars + 10), rates);
   if(copied < 10)
      return;

   const double pip = PipSize();
   const double quote = direction > 0 ? ask : bid;
   for(int i = 1; i < copied - 2; i++)
     {
      bool bullish = rates[i].low > rates[i + 2].high;
      bool bearish = rates[i].high < rates[i + 2].low;
      if(direction > 0 && !bullish)
         continue;
      if(direction < 0 && !bearish)
         continue;

      double upper = bullish ? rates[i].low : rates[i + 2].low;
      double lower = bullish ? rates[i + 2].high : rates[i].high;
      if(upper <= lower)
         continue;

      bool filled = false;
      bool partial = false;
      for(int j = i - 1; j >= 1; j--)
        {
         if(bullish)
           {
            if(rates[j].low <= lower)
               filled = true;
            if(rates[j].low < upper)
               partial = true;
           }
         else
           {
            if(rates[j].high >= upper)
               filled = true;
            if(rates[j].high > lower)
               partial = true;
           }
         if(filled)
            break;
        }
      if(filled || (partial && !InpIncludePartialFVG))
         continue;

      const double mid = (upper + lower) / 2.0;
      if(direction > 0 && mid >= bid)
         continue;
      if(direction < 0 && mid <= ask)
         continue;

      const double dist = pip > 0.0 ? MathAbs(quote - mid) / pip : 0.0;
      if(dist > InpMaxEntryDistancePips)
         continue;

      choice.ok = true;
      choice.timeframe = tf;
      choice.bullish = bullish;
      choice.partial = partial;
      choice.age_bars = i;
      choice.upper = upper;
      choice.lower = lower;
      choice.mid = mid;
      choice.distance_pips = dist;
      choice.reason = partial ? "partial aligned FVG" : "fresh aligned FVG";
      return;
     }
  }

//+------------------------------------------------------------------+
//| Liquidity                                                         |
//+------------------------------------------------------------------+
void ReadLiquidity(const int direction, const FVGChoice &fvg, const double bid,
                   const double ask, LiquidityRead &read)
  {
   read.sweep = false;
   read.front = false;
   read.behind = false;
   read.trap = false;
   read.deeper_pool_too_close = false;
   read.swept_level = 0.0;
   read.deeper_pool_level = 0.0;
   read.swept_pivot_age_bars = -1;
   read.swept_event_age_bars = -1;
   read.sweep_event_time = 0;
   read.reason = "liquidity neutral";
   if(direction == 0 || !fvg.ok)
      return;

   LiquidityScanTF(InpEntryTF2, direction, fvg, bid, ask, read);
   LiquidityScanTF(InpEntryTF1, direction, fvg, bid, ask, read);
   LiquidityScanTF(InpSetupTF, direction, fvg, bid, ask, read);

   read.trap = read.behind && !read.front && !read.sweep;
   if(read.deeper_pool_too_close)
      read.reason = direction > 0 ? "deeper unswept SSL too close below entry" : "deeper unswept BSL too close above entry";
   else if(read.trap)
      read.reason = direction > 0 ? "SSL behind bullish POI without front liquidity" : "BSL behind bearish POI without front liquidity";
   else if(read.sweep && read.front)
      read.reason = "recent sweep plus opposing liquidity in front";
   else if(read.sweep)
      read.reason = "recent opposing liquidity sweep";
   else if(read.front)
      read.reason = "opposing liquidity in front";
  }

void LiquidityScanTF(const ENUM_TIMEFRAMES tf, const int direction, const FVGChoice &fvg,
                     const double bid, const double ask, LiquidityRead &read)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int pivot = (tf == PERIOD_M1 || tf == PERIOD_M5) ? InpFastLiquidityPivotBars : InpLiquidityPivotBars;
   const int copied = CopyRates(_Symbol, tf, 0, MathMax(InpLookbackBars, pivot * 4 + 40), rates);
   if(copied < pivot * 2 + 10)
      return;

   const double tol = PipsToPrice(InpBehindZoneTolerancePips);
   const double quote = direction > 0 ? bid : ask;
   const double atr = ATRPrice(InpEntryTF1, 14);
   const double deeper_distance = atr > 0.0 ? atr * MathMax(0.0, InpDeeperPoolXATR) : 0.0;
   const double entry_ref = fvg.mid;
   for(int i = pivot + 2; i < copied - pivot; i++)
     {
      if(direction > 0 && PivotLowAt(rates, copied, i, pivot))
        {
         const double level = rates[i].low;
         const double top = MathMin(rates[i].open, rates[i].close);
         const double mid = (top + level) / 2.0;
         int sweep_age = 999999;
         bool swept = PoolSwept(false, rates, i, level, mid, sweep_age);
         if(swept && sweep_age <= InpMaxSweepAgeBars)
           {
            read.sweep = true;
            if(read.swept_level <= 0.0 || level < read.swept_level)
              {
               read.swept_level = level;
               read.swept_pivot_age_bars = i;
               read.swept_event_age_bars = sweep_age;
               read.sweep_event_time = SweepEventTime(rates, copied, i, sweep_age);
              }
           }
         if(!swept && deeper_distance > 0.0 && level < entry_ref && (entry_ref - level) <= deeper_distance)
           {
            read.deeper_pool_too_close = true;
            read.deeper_pool_level = level;
           }
         if(level >= fvg.lower && level <= quote)
            read.front = true;
         if(level <= fvg.lower && level >= fvg.lower - tol)
            read.behind = true;
        }
      if(direction < 0 && PivotHighAt(rates, copied, i, pivot))
        {
         const double level = rates[i].high;
         const double bottom = MathMax(rates[i].open, rates[i].close);
         const double mid = (bottom + level) / 2.0;
         int sweep_age = 999999;
         bool swept = PoolSwept(true, rates, i, level, mid, sweep_age);
         if(swept && sweep_age <= InpMaxSweepAgeBars)
           {
            read.sweep = true;
            if(read.swept_level <= 0.0 || level > read.swept_level)
              {
               read.swept_level = level;
               read.swept_pivot_age_bars = i;
               read.swept_event_age_bars = sweep_age;
               read.sweep_event_time = SweepEventTime(rates, copied, i, sweep_age);
              }
           }
         if(!swept && deeper_distance > 0.0 && level > entry_ref && (level - entry_ref) <= deeper_distance)
           {
            read.deeper_pool_too_close = true;
            read.deeper_pool_level = level;
           }
         if(level <= fvg.upper && level >= quote)
            read.front = true;
         if(level >= fvg.upper && level <= fvg.upper + tol)
            read.behind = true;
        }
     }
  }

bool PoolSwept(const bool buy_side, const MqlRates &rates[], const int pivot_index,
               const double level, const double mid, int &age_bars)
  {
   for(int j = pivot_index - 1; j >= 1; j--)
     {
      if(buy_side)
        {
         if(rates[j].high > level && rates[j].close < mid)
           {
            age_bars = j - 1;
            return true;
           }
         if(rates[j].close > level)
            return false;
        }
      else
        {
         if(rates[j].low < level && rates[j].close > mid)
           {
            age_bars = j - 1;
            return true;
           }
         if(rates[j].close < level)
            return false;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Volume Profile                                                    |
//+------------------------------------------------------------------+
void ReadVolumeProfile(VPRead &vp)
  {
   vp.ok = false;
   vp.poc = 0.0;
   vp.vah = 0.0;
   vp.val = 0.0;
   vp.distance_pips = 0.0;
   vp.buy_score = 0;
   vp.sell_score = 0;
   vp.buy_block = false;
   vp.sell_block = false;
   vp.context = "disabled";
   vp.read = "VP: off";
   if(!InpUseVolumeProfile)
      return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int rows = MathMax(8, InpVolumeProfileRows);
   const int copied = CopyRates(_Symbol, InpSetupTF, 0, MathMax(20, InpVolumeProfileBars + 2), rates);
   if(copied < 20)
      return;

   double high = rates[1].high;
   double low = rates[1].low;
   for(int i = 1; i < copied; i++)
     {
      high = MathMax(high, rates[i].high);
      low = MathMin(low, rates[i].low);
     }
   if(high <= low)
      return;

   double totals[];
   ArrayResize(totals, rows);
   ArrayInitialize(totals, 0.0);
   const double step = (high - low) / rows;
   for(int i = 1; i < copied; i++)
     {
      const double volume = (double)rates[i].tick_volume;
      if(volume <= 0.0)
         continue;
      int first = ClampInt((int)((rates[i].low - low) / step), 0, rows - 1);
      int last = ClampInt((int)((rates[i].high - low) / step), 0, rows - 1);
      if(last < first)
        {
         int tmp = first;
         first = last;
         last = tmp;
        }
      const int touched = MathMax(1, last - first + 1);
      const double share = volume / touched;
      for(int row = first; row <= last; row++)
         totals[row] += share;
     }

   int poc_index = 0;
   double max_volume = totals[0];
   double total = 0.0;
   for(int row = 0; row < rows; row++)
     {
      total += totals[row];
      if(totals[row] > max_volume)
        {
         max_volume = totals[row];
         poc_index = row;
        }
     }
   if(total <= 0.0)
      return;

   int va_low = poc_index;
   int va_high = poc_index;
   double covered = totals[poc_index];
   const double target = total * MathMax(1.0, MathMin(100.0, InpVolumeProfileValueAreaPct)) / 100.0;
   while(covered < target && (va_low > 0 || va_high < rows - 1))
     {
      const double below = va_low > 0 ? totals[va_low - 1] : -1.0;
      const double above = va_high < rows - 1 ? totals[va_high + 1] : -1.0;
      if(above >= below && va_high < rows - 1)
        {
         va_high++;
         covered += totals[va_high];
        }
      else if(va_low > 0)
        {
         va_low--;
         covered += totals[va_low];
        }
      else
         break;
     }

   const double current = rates[1].close;
   vp.poc = low + (poc_index + 0.5) * step;
   vp.val = low + va_low * step;
   vp.vah = low + (va_high + 1) * step;
   vp.distance_pips = PipSize() > 0.0 ? MathAbs(current - vp.poc) / PipSize() : 0.0;
   if(current > vp.vah)
      vp.context = "above_value";
   else if(current < vp.val)
      vp.context = "below_value";
   else
      vp.context = "inside_value";

   const int weight = MathMax(0, InpVolumeProfileScoreWeight);
   if(current > vp.poc)
     {
      vp.buy_score = vp.context == "inside_value" ? weight / 2 : weight;
      vp.sell_score = vp.distance_pips <= InpPocBlockDistancePips ? -weight : -(weight / 2);
      vp.sell_block = vp.distance_pips <= InpPocBlockDistancePips;
      vp.read = vp.context == "inside_value" ? "VP: inside value" : "VP: above POC";
     }
   else if(current < vp.poc)
     {
      vp.sell_score = vp.context == "inside_value" ? weight / 2 : weight;
      vp.buy_score = vp.distance_pips <= InpPocBlockDistancePips ? -weight : -(weight / 2);
      vp.buy_block = vp.distance_pips <= InpPocBlockDistancePips;
      vp.read = vp.context == "inside_value" ? "VP: inside value" : "VP: below POC";
     }
   else
      vp.read = "VP: at POC";

   vp.ok = true;
  }

//+------------------------------------------------------------------+
//| Risk and order placement                                          |
//+------------------------------------------------------------------+
bool BuildRiskPlan(const int direction, const FVGChoice &fvg, const MqlTick &tick, SetupRead &setup)
  {
   const double point = SymbolPoint();
   if(point <= 0.0)
      return false;
   if(!setup.liquidity.sweep || setup.liquidity.swept_level <= 0.0)
      return false;

   setup.entry = InpEntryMode == ENTRY_MARKET_SMOKE
                 ? (direction > 0 ? tick.ask : tick.bid)
                 : fvg.mid;

   const double atr = ATRPrice(InpEntryTF1, 14);
   if(atr <= 0.0)
      return false;

   const int pair_min_points = EffectiveMinStopPoints();
   const double pair_floor = pair_min_points * point;
   const double anchor_buffer = MathMax(atr * MathMax(0.0, InpSLAnchorBufferATR), pair_floor);
   const double spread_price = MathMax(0.0, tick.ask - tick.bid);
   if(direction > 0)
     {
      setup.sl = setup.liquidity.swept_level - anchor_buffer;
      const double atr_floor_sl = setup.entry - atr * MathMax(0.0, InpSLATRFloorMultiplier);
      const double pair_floor_sl = setup.entry - pair_floor;
      setup.sl = MathMin(setup.sl, atr_floor_sl);
      setup.sl = MathMin(setup.sl, pair_floor_sl);
      setup.tp = setup.entry + MathAbs(setup.entry - setup.sl) * MathMax(InpDefaultRR, InpMinRR);
     }
   else
     {
      setup.sl = setup.liquidity.swept_level + anchor_buffer;
      const double atr_floor_sl = setup.entry + atr * MathMax(0.0, InpSLATRFloorMultiplier);
      const double pair_floor_sl = setup.entry + pair_floor;
      setup.sl = MathMax(setup.sl, atr_floor_sl);
      setup.sl = MathMax(setup.sl, pair_floor_sl);
      setup.tp = setup.entry - MathAbs(setup.entry - setup.sl) * MathMax(InpDefaultRR, InpMinRR);
     }

   setup.entry = NormalizeDouble(setup.entry, _Digits);
   setup.sl = NormalizeDouble(setup.sl, _Digits);
   setup.tp = NormalizeDouble(setup.tp, _Digits);
   setup.risk = MathAbs(setup.entry - setup.sl);
   const double reward = MathAbs(setup.tp - setup.entry);
   setup.rr = setup.risk > 0.0 ? reward / setup.risk : 0.0;
   setup.lots = ResolveLots(setup.entry, setup.sl);

   const double stop_points = setup.risk / point;
   const double spread_adjusted_atr = (setup.risk - spread_price) / atr;
   const double pip = PipSize();
   if(InpMaxInitialRiskPips > 0 && pip > 0.0 && setup.risk / pip > InpMaxInitialRiskPips)
      return false;
   return setup.risk > 0.0 &&
          setup.rr >= InpMinRR &&
          stop_points >= pair_min_points &&
          setup.risk >= atr * MathMax(0.0, InpSLATRFloorMultiplier) &&
          spread_adjusted_atr >= MathMax(0.0, InpSpreadAdjustedATRThreshold) &&
          setup.lots > 0.0;
  }

double ResolveLots(const double entry, const double sl)
  {
   const double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   const double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   const double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(InpFixedLots > 0.0)
      return NormalizeVolume(InpFixedLots, min_lot, max_lot, step);

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(equity <= 0.0 || tick_value <= 0.0 || tick_size <= 0.0)
      return 0.0;

   const double risk_money = equity * MathMax(0.0, InpRiskPercent) / 100.0;
   const double ticks = MathAbs(entry - sl) / tick_size;
   if(ticks <= 0.0)
      return 0.0;

   double lots = risk_money / (ticks * tick_value);
   return NormalizeVolume(lots, min_lot, max_lot, step);
  }

int EffectiveMinStopPoints()
  {
   if(StringFind(_Symbol, "JPY") >= 0)
      return MathMax(InpMinStopPoints, InpMinStopPointsJPY);
   return MathMax(InpMinStopPoints, InpMinStopPointsMajor);
  }

double ATRPrice(const ENUM_TIMEFRAMES tf, const int period)
  {
   const int handle = iATR(_Symbol, tf, MathMax(1, period));
   if(handle == INVALID_HANDLE)
      return 0.0;

   double atr[];
   ArraySetAsSeries(atr, true);
   const int copied = CopyBuffer(handle, 0, 1, 1, atr);
   IndicatorRelease(handle);
   if(copied <= 0)
      return 0.0;
   return atr[0];
  }

double NormalizeVolume(const double lots, const double min_lot, const double max_lot, const double step)
  {
   if(lots <= 0.0 || step <= 0.0)
      return 0.0;
   double normalized = MathFloor(lots / step) * step;
   normalized = MathMax(min_lot, MathMin(max_lot, normalized));
   return NormalizeDouble(normalized, 2);
  }

void PlaceSetup(const SetupRead &setup)
  {
   if(HasActiveStrategy())
      return;

   g_last_initial_risk = setup.risk;
   g_last_htf_momentum_d1 = setup.htf_momentum_d1;
   g_last_time_since_sweep_pivot_bars = setup.time_since_sweep_pivot_bars;
   g_last_time_since_sweep_event_bars = setup.time_since_sweep_event_bars;
   g_last_room_to_swing_high_pips = setup.room_to_swing_high_pips;
   g_last_spread_to_atr_ratio = setup.spread_to_atr_ratio;
   g_last_m5_m1_event_lag_bars = setup.m5_m1_event_lag_bars;
   const string comment = StringSubstr(InpStrategyIdPrefix + "-" + _Symbol, 0, 31);
   bool ok = false;
   if(InpEntryMode == ENTRY_MARKET_SMOKE)
     {
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
      ok = setup.direction > 0
           ? g_trade.Buy(setup.lots, _Symbol, 0.0, setup.sl, setup.tp, comment)
           : g_trade.Sell(setup.lots, _Symbol, 0.0, setup.sl, setup.tp, comment);
     }
   else
     {
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
      ok = setup.direction > 0
           ? g_trade.BuyLimit(setup.lots, setup.entry, _Symbol, setup.sl, setup.tp, ORDER_TIME_GTC, 0, comment)
           : g_trade.SellLimit(setup.lots, setup.entry, _Symbol, setup.sl, setup.tp, ORDER_TIME_GTC, 0, comment);
     }

   if(!ok && InpJournalEnabled)
      JournalFailure("order_send", setup, IntegerToString((int)g_trade.ResultRetcode()) + ":" + g_trade.ResultRetcodeDescription());
  }

bool HasActiveStrategy()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionSelectByTicket(ticket))
        {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == g_magic)
            return true;
        }
     }

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = OrderGetTicket(i);
      if(ticket > 0 && OrderSelect(ticket))
        {
         if(OrderGetString(ORDER_SYMBOL) == _Symbol && OrderGetInteger(ORDER_MAGIC) == g_magic)
            return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Trade management                                                  |
//+------------------------------------------------------------------+
void ManageOpenPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != g_magic)
         continue;

      const ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      const double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      const double current_sl = PositionGetDouble(POSITION_SL);
      const double current_tp = PositionGetDouble(POSITION_TP);
      const double point = SymbolPoint();
      if(point <= 0.0)
         continue;

      double risk = MathAbs(entry - current_sl);
      if(g_last_initial_risk > 0.0)
         risk = g_last_initial_risk;
      if(risk <= 0.0)
         continue;

      const double exit_price = CurrentExitPrice(type);
      const double profit_distance = type == POSITION_TYPE_BUY ? exit_price - entry : entry - exit_price;
      double proposed_sl = current_sl;

      if(InpUseBreakeven && profit_distance >= risk * InpBETriggerR)
        {
         const double be = type == POSITION_TYPE_BUY
                           ? entry + InpBEBufferPoints * point
                           : entry - InpBEBufferPoints * point;
         proposed_sl = ImproveSL(type, proposed_sl, be);
        }

      double chandelier = 0.0;
      if(ComputeChandelier(type, chandelier))
         proposed_sl = ImproveSL(type, proposed_sl, chandelier);

      proposed_sl = EnforceStopsLevel(type, NormalizeDouble(proposed_sl, _Digits));
      if(ShouldModifySL(type, current_sl, proposed_sl))
         g_trade.PositionModify(ticket, proposed_sl, current_tp);
     }
  }

bool ComputeChandelier(const ENUM_POSITION_TYPE type, double &sl)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int lookback = MathMax(1, InpChandelierLookback);
   const int copied = CopyRates(_Symbol, InpChandelierTF, 0, lookback, rates);
   if(copied < lookback)
      return false;

   double extreme = type == POSITION_TYPE_BUY ? rates[0].high : rates[0].low;
   for(int i = 1; i < copied; i++)
     {
      if(type == POSITION_TYPE_BUY)
         extreme = MathMax(extreme, rates[i].high);
      else
         extreme = MathMin(extreme, rates[i].low);
     }

   const int handle = iATR(_Symbol, InpChandelierTF, MathMax(1, InpChandelierATRPeriod));
   if(handle == INVALID_HANDLE)
      return false;

   double atr[];
   ArraySetAsSeries(atr, true);
   const int got = CopyBuffer(handle, 0, 0, 1, atr);
   IndicatorRelease(handle);
   if(got <= 0 || atr[0] <= 0.0)
      return false;

   sl = type == POSITION_TYPE_BUY
        ? extreme - InpChandelierATRMultiplier * atr[0]
        : extreme + InpChandelierATRMultiplier * atr[0];
   return sl > 0.0;
  }

double ImproveSL(const ENUM_POSITION_TYPE type, const double current, const double candidate)
  {
   if(candidate <= 0.0)
      return current;
   if(current <= 0.0)
      return candidate;
   return type == POSITION_TYPE_BUY ? MathMax(current, candidate) : MathMin(current, candidate);
  }

bool ShouldModifySL(const ENUM_POSITION_TYPE type, const double current_sl, const double proposed_sl)
  {
   if(proposed_sl <= 0.0)
      return false;
   const double min_improvement = InpMinSLImprovementPoints * SymbolPoint();
   if(current_sl <= 0.0)
      return true;
   const double improvement = type == POSITION_TYPE_BUY ? proposed_sl - current_sl : current_sl - proposed_sl;
   return improvement >= min_improvement;
  }

double EnforceStopsLevel(const ENUM_POSITION_TYPE type, const double proposed_sl)
  {
   const double point = SymbolPoint();
   long stops = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(stops <= 0)
      stops = 5;
   const double distance = (stops + 1) * point;
   const double price = CurrentExitPrice(type);
   if(type == POSITION_TYPE_BUY)
      return MathMin(proposed_sl, price - distance);
   return MathMax(proposed_sl, price + distance);
  }

double CurrentExitPrice(const ENUM_POSITION_TYPE type)
  {
   MqlTick tick;
   if(SymbolInfoTick(_Symbol, tick))
      return type == POSITION_TYPE_BUY ? tick.bid : tick.ask;
   return SymbolInfoDouble(_Symbol, type == POSITION_TYPE_BUY ? SYMBOL_BID : SYMBOL_ASK);
  }

//+------------------------------------------------------------------+
//| Journaling                                                        |
//+------------------------------------------------------------------+
void InitJournals()
  {
   ArrayResize(g_journaled_deals, 0);
   FolderCreate(InpJournalFolder);
   InitJournalFile("setups", "time,symbol,tf,status,direction,score,gates,poi_tf,poi_lower,poi_upper,entry,sl,tp,rr,liquidity,vp,failure");
   InitJournalFile("entries", "time,symbol,deal,position,magic,direction,lots,price,sl,tp,initial_risk,commission,swap,profit,htf_momentum_d1,time_since_sweep_pivot_bars,time_since_sweep_event_bars,room_to_swing_high_pips,spread_to_atr_ratio,m5_m1_event_lag_bars");
   InitJournalFile("exits", "time,symbol,deal,position,magic,direction,lots,price,realized_r,commission,swap,profit,reason,htf_momentum_d1,time_since_sweep_pivot_bars,time_since_sweep_event_bars,room_to_swing_high_pips,spread_to_atr_ratio,m5_m1_event_lag_bars");
   InitJournalFile("failures", "time,symbol,stage,status,direction,score,entry,sl,tp,rr,reason,detail");
  }

void InitJournalFile(const string kind, const string header)
  {
   const string path = JournalPath(kind);
   if(InpJournalResetOnInit)
     {
      const int reset_handle = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
      if(reset_handle != INVALID_HANDLE)
        {
         FileWriteString(reset_handle, header + "\r\n");
         FileClose(reset_handle);
        }
      return;
     }

   const int handle = FileOpen(path, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(handle == INVALID_HANDLE)
      return;
   if(FileSize(handle) == 0)
     {
      FileWriteString(handle, header + "\r\n");
     }
   else
     {
      FileSeek(handle, 0, SEEK_SET);
      const string current_header = FileReadString(handle);
      if(current_header != header)
        {
         FileClose(handle);
         const int rewrite_handle = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
         if(rewrite_handle != INVALID_HANDLE)
           {
            FileWriteString(rewrite_handle, header + "\r\n");
            FileClose(rewrite_handle);
           }
         return;
        }
     }
   FileClose(handle);
  }

bool RememberJournaledDeal(const ulong deal)
  {
   const int count = ArraySize(g_journaled_deals);
   for(int i = 0; i < count; i++)
     {
      if(g_journaled_deals[i] == deal)
         return false;
     }
   ArrayResize(g_journaled_deals, count + 1);
   g_journaled_deals[count] = deal;
   return true;
  }

void JournalSetup(const SetupRead &setup)
  {
   string row = StringFormat("%s,%s,%s,%s,%s,%d,%s,%s,%.5f,%.5f,%.5f,%.5f,%.5f,%.2f,%s,%s,%s",
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      _Symbol,
      TimeframeText(InpEntryTF1),
      StatusText(setup.status),
      DirectionText(setup.direction),
      setup.score,
      Csv(setup.gates),
      TimeframeText(setup.poi.timeframe),
      setup.poi.lower,
      setup.poi.upper,
      setup.entry,
      setup.sl,
      setup.tp,
      setup.rr,
      Csv(setup.liquidity.reason),
      Csv(setup.vp.read),
      Csv(setup.failure)
   );
   AppendJournal("setups", row);
  }

void JournalEntryDeal(const ulong deal)
  {
   const long deal_type = HistoryDealGetInteger(deal, DEAL_TYPE);
   const string direction = deal_type == DEAL_TYPE_BUY ? "BUY" : "SELL";
   const ulong position_id = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
   g_last_position_id = position_id;
   string row = StringFormat("%s,%s,%I64u,%I64u,%I64d,%s,%.2f,%.5f,%.5f,%.5f,%.5f,%.2f,%.2f,%.2f,%.4f,%d,%d,%.1f,%.4f,%d",
      TimeToString((datetime)HistoryDealGetInteger(deal, DEAL_TIME), TIME_DATE | TIME_SECONDS),
      _Symbol,
      deal,
      position_id,
      g_magic,
      direction,
      HistoryDealGetDouble(deal, DEAL_VOLUME),
      HistoryDealGetDouble(deal, DEAL_PRICE),
      PositionSelect(_Symbol) ? PositionGetDouble(POSITION_SL) : 0.0,
      PositionSelect(_Symbol) ? PositionGetDouble(POSITION_TP) : 0.0,
      g_last_initial_risk,
      HistoryDealGetDouble(deal, DEAL_COMMISSION),
      HistoryDealGetDouble(deal, DEAL_SWAP),
      HistoryDealGetDouble(deal, DEAL_PROFIT),
      g_last_htf_momentum_d1,
      g_last_time_since_sweep_pivot_bars,
      g_last_time_since_sweep_event_bars,
      g_last_room_to_swing_high_pips,
      g_last_spread_to_atr_ratio,
      g_last_m5_m1_event_lag_bars
   );
   AppendJournal("entries", row);
  }

void JournalExitDeal(const ulong deal)
  {
   const long deal_type = HistoryDealGetInteger(deal, DEAL_TYPE);
   const string direction = deal_type == DEAL_TYPE_BUY ? "BUY" : "SELL";
   const double profit = HistoryDealGetDouble(deal, DEAL_PROFIT) +
                         HistoryDealGetDouble(deal, DEAL_COMMISSION) +
                         HistoryDealGetDouble(deal, DEAL_SWAP);
   const double volume = HistoryDealGetDouble(deal, DEAL_VOLUME);
   double realized_r = 0.0;
   if(g_last_initial_risk > 0.0 && volume > 0.0)
     {
      const double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      const double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      const double money_r = tick_size > 0.0 ? (g_last_initial_risk / tick_size) * tick_value * volume : 0.0;
      if(money_r > 0.0)
         realized_r = profit / money_r;
     }
   string row = StringFormat("%s,%s,%I64u,%I64u,%I64d,%s,%.2f,%.5f,%.2f,%.2f,%.2f,%.2f,%s,%.4f,%d,%d,%.1f,%.4f,%d",
      TimeToString((datetime)HistoryDealGetInteger(deal, DEAL_TIME), TIME_DATE | TIME_SECONDS),
      _Symbol,
      deal,
      (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID),
      g_magic,
      direction,
      volume,
      HistoryDealGetDouble(deal, DEAL_PRICE),
      realized_r,
      HistoryDealGetDouble(deal, DEAL_COMMISSION),
      HistoryDealGetDouble(deal, DEAL_SWAP),
      HistoryDealGetDouble(deal, DEAL_PROFIT),
      Csv(HistoryDealGetString(deal, DEAL_COMMENT)),
      g_last_htf_momentum_d1,
      g_last_time_since_sweep_pivot_bars,
      g_last_time_since_sweep_event_bars,
      g_last_room_to_swing_high_pips,
      g_last_spread_to_atr_ratio,
      g_last_m5_m1_event_lag_bars
   );
   AppendJournal("exits", row);
  }

void JournalFailure(const string stage, const SetupRead &setup, const string detail)
  {
   string row = StringFormat("%s,%s,%s,%s,%s,%d,%.5f,%.5f,%.5f,%.2f,%s,%s",
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      _Symbol,
      stage,
      StatusText(setup.status),
      DirectionText(setup.direction),
      setup.score,
      setup.entry,
      setup.sl,
      setup.tp,
      setup.rr,
      Csv(setup.failure),
      Csv(detail)
   );
   AppendJournal("failures", row);
  }

void AppendJournal(const string kind, const string row)
  {
   const int handle = FileOpen(JournalPath(kind), FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(handle == INVALID_HANDLE)
      return;
   FileSeek(handle, 0, SEEK_END);
   FileWriteString(handle, row + "\r\n");
   FileClose(handle);
  }

string JournalPath(const string kind)
  {
   return InpJournalFolder + "\\" + "EhukaiTDAEA_" + _Symbol + "_" + kind + ".csv";
  }

string Csv(string value)
  {
   StringReplace(value, "\"", "'");
   StringReplace(value, "\r", " ");
   StringReplace(value, "\n", " ");
   return "\"" + value + "\"";
  }

//+------------------------------------------------------------------+
//| Utility                                                           |
//+------------------------------------------------------------------+
long ResolveMagic(const string symbol)
  {
   if(InpMagicOverride > 0)
      return InpMagicOverride;
   const string s = symbol;
   if(s == "USDJPY") return 176879;
   if(s == "EURUSD") return 172432;
   if(s == "GBPUSD") return 140360;
   if(s == "AUDUSD") return 128648;
   if(s == "USDCAD") return 128461;
   if(s == "NZDUSD") return 146145;
   if(s == "USDCHF") return 171860;
   if(s == "EURJPY") return 159469;
   if(s == "GBPJPY") return 174473;
   if(s == "AUDJPY") return 137163;
   if(s == "EURGBP") return 143861;
   return 179999;
  }

bool IsFxRolloverWindow()
  {
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   return dt.hour == 21 || dt.hour == 22;
  }

bool IsFridayUTC()
  {
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   return dt.day_of_week == 5;
  }

bool NewsWindowOk()
  {
   // Structural placeholder: when enabled before a calendar source is wired,
   // fail closed instead of pretending news risk was checked.
   if(!InpUseNewsWindowGuard)
      return true;
   return false;
  }

double SymbolPoint()
  {
   double point = 0.0;
   if(SymbolInfoDouble(_Symbol, SYMBOL_POINT, point))
      return point;
   return _Point;
  }

double PipSize()
  {
   const double point = SymbolPoint();
   const int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return (digits == 3 || digits == 5) ? point * 10.0 : point;
  }

double PipsToPrice(const double pips)
  {
   return pips * PipSize();
  }

double D1MomentumRatio(const int bars = 10)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int copied = CopyRates(_Symbol, PERIOD_D1, 1, bars, rates);
   if(copied < bars)
      return 0.0;

   const double net = rates[0].close - rates[copied - 1].close;
   double range_sum = 0.0;
   for(int i = 0; i < copied; i++)
      range_sum += MathAbs(rates[i].high - rates[i].low);
   return range_sum > 0.0 ? net / range_sum : 0.0;
  }

double RoomToSwingExtremePips(const int direction, const double entry_price)
  {
   if(direction == 0 || entry_price <= 0.0)
      return 0.0;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   const int copied = CopyRates(_Symbol, PERIOD_M15, 0, InpLookbackBars, rates);
   const int pivot = InpSwingPivotBars;
   if(copied < pivot * 4)
      return 0.0;

   double nearest = 0.0;
   for(int i = pivot; i < copied - pivot; i++)
     {
      if(direction > 0 && PivotHighAt(rates, copied, i, pivot))
        {
         const double level = rates[i].high;
         if(level > entry_price && (nearest == 0.0 || level < nearest))
            nearest = level;
        }
      else if(direction < 0 && PivotLowAt(rates, copied, i, pivot))
        {
         const double level = rates[i].low;
         if(level < entry_price && (nearest == 0.0 || level > nearest))
            nearest = level;
        }
     }
   return nearest == 0.0 || PipSize() <= 0.0 ? 0.0 : MathAbs(nearest - entry_price) / PipSize();
  }

datetime SweepEventTime(const MqlRates &rates[], const int count, const int pivot_index, const int age_bars)
  {
   const int index = pivot_index - 1 - age_bars;
   if(index >= 0 && index < count)
      return rates[index].time;
   return 0;
  }

datetime EntryConfirmTime(const int direction, const StructureRead &m5, const StructureRead &m1)
  {
   if(direction == 0)
      return 0;
   if(m1.event_dir == direction && (m1.event_type == "BOS" || m1.event_type == "CHOCH" || m1.event_type == "iBOS"))
      return m1.signal_time;
   if(m5.event_dir == direction && (m5.event_type == "BOS" || m5.event_type == "CHOCH" || m5.event_type == "iBOS"))
      return m5.signal_time;
   return 0;
  }

int EventLagBarsM1(const int direction, const StructureRead &m5, const StructureRead &m1, const datetime sweep_event_time)
  {
   const datetime confirm_time = EntryConfirmTime(direction, m5, m1);
   if(confirm_time <= 0 || sweep_event_time <= 0)
      return -1;
   return (int)((confirm_time - sweep_event_time) / 60);
  }

bool PriceInZone(const double price, const double upper, const double lower)
  {
   return price <= upper && price >= lower;
  }

int ClampInt(const int value, const int lower, const int upper)
  {
   return MathMax(lower, MathMin(upper, value));
  }

string BoolText(const bool value)
  {
   return value ? "pass" : "fail";
  }

string DirectionText(const int direction)
  {
   if(direction > 0)
      return "BUY";
   if(direction < 0)
      return "SELL";
   return "-";
  }

string StatusText(const ENUM_EHUKAI_STATUS status)
  {
   if(status == EHUKAI_READY)
      return "READY";
   if(status == EHUKAI_WATCH)
      return "WATCH";
   return "NO_TRADE";
  }

string TimeframeText(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      default:         return EnumToString(tf);
     }
  }

string FirstFailure(const bool spread_ok, const bool rollover_ok, const bool friday_ok,
                    const bool quote_ok, const bool score_ok, const bool entry_ok)
  {
   if(!spread_ok) return "spread";
   if(!rollover_ok) return "rollover";
   if(!friday_ok) return "friday";
   if(!quote_ok) return "quote_side_or_structure";
   if(!score_ok) return "score";
   if(!entry_ok) return "entry";
   return "watch";
  }

string FirstFailure(const bool spread_ok, const bool rollover_ok, const bool news_ok, const bool friday_ok,
                    const bool structure_ok, const bool fvg_ok, const bool quote_ok,
                    const bool sweep_ok, const bool deeper_pool_ok, const bool liq_ok,
                    const bool vp_ok, const bool risk_ok, const bool score_ok,
                    const bool entry_ok, const bool active_ok)
  {
   if(!spread_ok) return "spread";
   if(!rollover_ok) return "rollover";
   if(!news_ok) return "news_guard";
   if(!friday_ok) return "friday";
   if(!structure_ok) return "structure";
   if(!fvg_ok) return "fvg";
   if(!quote_ok) return "quote_side";
   if(!sweep_ok) return "liquidity_sweep";
   if(!deeper_pool_ok) return "deeper_pool";
   if(!liq_ok) return "liquidity_trap";
   if(!vp_ok) return "vp_poc_block";
   if(!risk_ok) return "risk";
   if(!score_ok) return "score";
   if(!entry_ok) return "entry_structure";
   if(!active_ok) return "active_strategy";
   return "unknown";
  }
