//+------------------------------------------------------------------+
//| Advanced_Wavelet_Entry_ResearchEA.mq5                            |
//| Diagnostic/export EA with optional tiny-demo execution.           |
//| Research prototype. No profitability claims.                     |
//+------------------------------------------------------------------+
#property strict
#property copyright "Research prototype"
#property version   "1.00"
#property tester_indicator "Advanced_Wavelet_Entry_Signal.ex5"
#property tester_indicator "Advanced_OrderFlow_Proxy_Confluence.ex5"

#include <Trade\Trade.mqh>

CTrade trade;

//--- Operating mode and risk controls
input bool     InpAllowTrading                    = false;       // Default observe-only; must be true to trade
input bool     InpDemoAccountsOnly                = true;        // Refuse live/real trading when true
input double   InpLots                            = 0.01;        // Conservative demo research lot
input double   InpMaxSafetyLots                   = 0.01;        // Hard cap for research lot size
input long     InpMagicBase                       = 88001001;    // Base magic number
input bool     InpUseSymbolMagic                  = true;        // Add stable per-symbol hash to magic
input int      InpSlippagePoints                  = 20;          // Allowed deviation
input bool     InpPreferFOK                       = true;        // Prefer fill-or-kill if broker accepts it
input bool     InpOnePositionPerSymbol            = true;        // FIFO/netting-friendly symbol guard
input int      InpMaxTradesPerDay                 = 3;           // 0 disables daily trade count guard
input double   InpDailyLossLimitMoney             = 20.0;        // 0 disables daily realized-loss guard
input bool     InpDailyGuardsAccountWide          = false;       // Count all account deals, not just this symbol/magic
input int      InpEntryMaxSpreadPoints            = 30;          // Current spread filter; 0 disables
input double   InpSignalThreshold                 = 0.70;        // EA decision threshold
input bool     InpCloseOnOppositeSignal           = false;       // Close, do not reverse on same bar
input int      InpTimeExitBars                    = 24;          // Time exit in bars; 0 disables
input bool     InpUseATRStops                     = false;       // Optional ATR SL/TP
input double   InpATRStopLossMult                 = 1.50;        // ATR SL multiplier
input double   InpATRTakeProfitMult               = 2.00;        // ATR TP multiplier

//--- CSV diagnostics
input bool     InpExportSignalCSV                 = true;
input bool     InpExportTradeCSV                  = true;
input bool     InpAppendCSV                       = true;
input string   InpCSVFolder                       = "WaveletResearch";
input string   InpRunTag                          = "diag";
input string   InpSignalCSVFile                   = "";          // Blank = auto per symbol/timeframe/run tag
input string   InpTradeCSVFile                    = "";          // Blank = auto per symbol/timeframe/run tag
input bool     InpWriteForwardReturns             = true;        // Delayed, non-leaking forward labels
input bool     InpWriteIncompleteForwardRowsOnDeinit = true;     // Partial labels at test end
input int      InpForwardBars1                    = 3;
input int      InpForwardBars2                    = 6;
input int      InpForwardBars3                    = 12;
input int      InpForwardBars4                    = 24;
input int      InpForwardBars5                    = 48;

//--- Optional order-flow proxy diagnostics. Disabled by default; does not change trade decisions.
input bool     InpUseOrderFlowProxy               = false;
input string   InpOFIndicatorName                 = "Advanced_OrderFlow_Proxy_Confluence";
input bool     InpOFExportCSV                     = true;
input int      InpOFATRPeriod                     = 14;
input int      InpOFDeltaLookback                 = 48;
input int      InpOFDivergenceLookback            = 24;
input int      InpOFStructureLookback             = 36;
input double   InpOFVolumeRatioCap                = 2.50;
input double   InpOFDivergenceMinDeltaGap         = 0.10;
input double   InpOFAggressionMinDelta            = 0.20;
input double   InpOFAggressionMinVolumeRatio      = 1.15;
input int      InpOFStackedMinBars                = 3;
input int      InpOFStackedWindowBars             = 5;
input double   InpOFAbsorptionMinEffort           = 0.65;
input double   InpOFAbsorptionMaxProgressATR      = 0.25;
input double   InpOFAbsorptionMinWickRatio        = 0.35;
input double   InpOFStructureDistanceATR          = 1.20;
input double   InpOFNeutralThreshold              = 0.10;
input double   InpOFMixedThreshold                = 0.15;
input double   InpOFDecisionProceedEvidence       = 0.08;        // Diagnostic proceed evidence threshold
input double   InpOFDecisionMaxProceedConflict    = 0.15;        // Max conflict for diagnostic proceed
input double   InpOFDecisionStandDownConflict     = 0.25;        // Conflict threshold for diagnostic stand-down
input double   InpOFDecisionNoEvidenceThreshold   = 0.05;        // Below this, classify as no-evidence stand-down

//--- Indicator inputs forwarded to Advanced_Wavelet_Entry_Signal
input int      InpIndWaveletWindow                = 64;
input int      InpIndWaveletLevels                = 4;
input int      InpIndATRPeriod                    = 14;
input int      InpIndVolumeLookback               = 96;
input int      InpIndPivotLookback                = 36;
input int      InpIndStructureLookback            = 48;
input double   InpIndicatorMinSignalScore         = 0.50;        // Low discovery threshold; EA threshold filters trades
input double   InpIndMinWaveletEnergyScore        = 0.35;
input double   InpIndMaxNoiseRatio                = 0.62;
input double   InpIndMinVolumeAnomaly             = 1.10;
input double   InpIndVolumeAnomalyCap             = 2.50;
input double   InpIndMaxPivotDistanceATR          = 1.20;
input double   InpIndRangeATRTarget               = 0.90;
input double   InpIndMaxRangeATRForPenalty        = 2.80;
input double   InpIndMinDirectionMargin           = 0.03;
input int      InpIndMaxSpreadPoints              = 30;
input bool     InpIndUseSessionFilter             = false;
input int      InpIndSessionStartHour             = 6;
input int      InpIndSessionEndHour               = 20;
input bool     InpIndUseTrendBiasFilter           = false;
input bool     InpIndUseHardFilters               = true;
input bool     InpIndRequireVolumeAnomaly         = true;
input bool     InpIndRequireRejectionQuality      = false;
input double   InpIndMinRejectionQuality          = 0.25;
input bool     InpIndRequirePivotProximity        = false;
input double   InpIndMinPivotQuality              = 0.25;
input double   InpIndWeightWavelet                = 1.25;
input double   InpIndWeightNoise                  = 1.00;
input double   InpIndWeightVolume                 = 0.85;
input double   InpIndWeightRejection              = 1.00;
input double   InpIndWeightATRRange               = 0.75;
input double   InpIndWeightPivot                  = 0.90;
input double   InpIndWeightStructure              = 0.75;
input double   InpIndWeightSpread                 = 0.35;
input double   InpIndWeightSession                = 0.25;
input double   InpIndWeightTrendBias              = 0.50;
input double   InpIndArrowOffsetATR               = 0.10;

//--- Optimization scoring controls
input int      InpTesterMinTrades                 = 80;          // Penalize low trade counts
input double   InpTesterDDPenaltyPercent          = 10.0;        // DD percent scale for penalty

//--- Indicator buffer map
#define BUF_BUY_PRICE          0
#define BUF_SELL_PRICE         1
#define BUF_DIRECTION          2
#define BUF_SCORE              3
#define BUF_WAVELET            4
#define BUF_NOISE              5
#define BUF_VOLUME             6
#define BUF_PIVOT_CONTEXT      7
#define BUF_DEBUG              8
#define BUF_ATR                9
#define BUF_SPREAD             10
#define BUF_PIVOT_DISTANCE     11
#define BUF_STRUCTURE          12
#define BUF_RANGE_QUALITY      13
#define BUF_REJECTION_QUALITY  14
#define BUF_TREND_BIAS         15

//--- Order-flow proxy companion indicator buffer map
#define OF_BUF_DELTA            0
#define OF_BUF_DIVERGENCE       1
#define OF_BUF_AGGRESSION       2
#define OF_BUF_STACKED          3
#define OF_BUF_ABSORPTION       4
#define OF_BUF_CONFLUENCE       5
#define OF_BUF_RAW_STATE        6
#define OF_BUF_REASON           7
#define OF_BUF_DATA_MODE        8

struct SignalSnapshot
{
   datetime bar_time;
   int      direction;
   double   score;
   double   wavelet_energy;
   double   noise_ratio;
   double   volume_ratio;
   double   spread_points;
   double   atr;
   double   pivot_distance_atr;
   int      structure_class;
   int      debug_mask;
   double   close_price;
   double   signal_price;
   bool     of_available;
   double   of_delta;
   double   of_divergence;
   double   of_aggression;
   double   of_stacked_pressure;
   double   of_absorption;
   double   of_confluence_score;
   int      of_raw_state;
   int      of_decision_state;
   int      of_reason_code;
   int      of_data_mode;
   double   of_adjusted_score;
   double   of_alignment_score;
   double   of_evidence_score;
   double   of_conflict_score;
   int      of_profile_state;
   string   of_decision_class;
};

struct ActiveTradeState
{
   bool     valid;
   ulong    ticket;
   datetime signal_time;
   datetime open_time;
   int      direction;
   double   entry;
   double   score;
   string   reason_opened;
   double   spread_entry_points;
   double   mfe_points;
   double   mae_points;
   int      of_state_at_entry;
   double   of_score_at_entry;
   int      of_reason_at_entry;
};

int              g_indicator_handle=INVALID_HANDLE;
int              g_of_indicator_handle=INVALID_HANDLE;
ulong            g_magic=0;
bool             g_trade_enabled=false;
datetime         g_last_bar_time=0;
datetime         g_today_start=0;
int              g_trades_today=0;
int              g_signal_file=INVALID_HANDLE;
int              g_trade_file=INVALID_HANDLE;
string           g_signal_filename="";
string           g_trade_filename="";
SignalSnapshot   g_pending_signals[];
ActiveTradeState g_active;

void ResetActiveState()
{
   g_active.valid=false;
   g_active.ticket=0;
   g_active.signal_time=0;
   g_active.open_time=0;
   g_active.direction=0;
   g_active.entry=0.0;
   g_active.score=0.0;
   g_active.reason_opened="";
   g_active.spread_entry_points=0.0;
   g_active.mfe_points=0.0;
   g_active.mae_points=0.0;
   g_active.of_state_at_entry=0;
   g_active.of_score_at_entry=EMPTY_VALUE;
   g_active.of_reason_at_entry=0;
}

//+------------------------------------------------------------------+
//| String/format helpers                                            |
//+------------------------------------------------------------------+
string TimeString(const datetime value)
{
   if(value<=0)
      return "";
   return TimeToString(value,TIME_DATE|TIME_MINUTES);
}

string PeriodString()
{
   string s=EnumToString((ENUM_TIMEFRAMES)_Period);
   StringReplace(s,"PERIOD_","");
   return s;
}

string CleanFilePart(string s)
{
   StringReplace(s," ","_");
   StringReplace(s,":","-");
   StringReplace(s,"/","-");
   StringReplace(s,"\\","-");
   StringReplace(s,".","-");
   return s;
}

string DoubleField(const double value,const int digits)
{
   if(value==EMPTY_VALUE || value==DBL_MAX || value<-DBL_MAX/2.0)
      return "";
   return DoubleToString(value,digits);
}

string DirectionString(const int direction)
{
   if(direction>0)
      return "buy";
   if(direction<0)
      return "sell";
   return "none";
}

datetime DayStart(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t,dt);
   dt.hour=0;
   dt.min=0;
   dt.sec=0;
   return StructToTime(dt);
}

ulong SymbolHash(const string symbol)
{
   ulong hash=0;
   const int len=StringLen(symbol);
   for(int i=0;i<len;i++)
   {
      hash=(hash*131+(ushort)StringGetCharacter(symbol,i))%1000000;
   }
   return hash;
}

ulong ComputeMagic()
{
   long base_long=InpMagicBase;
   if(base_long<1)
      base_long=1;
   ulong base=(ulong)base_long;
   if(InpUseSymbolMagic)
      base+=SymbolHash(_Symbol);
   return base;
}

int MaxForwardBars()
{
   int maxv=MathMax(InpForwardBars1,InpForwardBars2);
   maxv=MathMax(maxv,InpForwardBars3);
   maxv=MathMax(maxv,InpForwardBars4);
   maxv=MathMax(maxv,InpForwardBars5);
   return MathMax(maxv,0);
}

bool UseOFProxyCSV()
{
   return (InpUseOrderFlowProxy && InpOFExportCSV);
}

void ClearOFProxyFields(SignalSnapshot &s)
{
   s.of_available=false;
   s.of_delta=EMPTY_VALUE;
   s.of_divergence=EMPTY_VALUE;
   s.of_aggression=EMPTY_VALUE;
   s.of_stacked_pressure=EMPTY_VALUE;
   s.of_absorption=EMPTY_VALUE;
   s.of_confluence_score=EMPTY_VALUE;
   s.of_raw_state=0;
   s.of_decision_state=0;
   s.of_reason_code=0;
   s.of_data_mode=0;
   s.of_adjusted_score=s.score;
   s.of_alignment_score=EMPTY_VALUE;
   s.of_evidence_score=EMPTY_VALUE;
   s.of_conflict_score=EMPTY_VALUE;
   s.of_profile_state=0;
   s.of_decision_class="neutral";
}

string OFDecisionClass(const int state,const int profile_state)
{
   if(profile_state==-3)
      return "proxy_not_ready";
   if(profile_state==-1)
      return "no_evidence";
   if(state==-2)
      return "stand_down";
   if(state==2)
      return "investigate";
   if(state>0)
      return "proceed_buy";
   if(state<0)
      return "proceed_sell";
   return "neutral";
}

void MarkOFProxyUnavailable(SignalSnapshot &s,const int data_mode,const string decision_class)
{
   ClearOFProxyFields(s);
   s.of_available=false;
   s.of_data_mode=data_mode;
   s.of_profile_state=-3;
   s.of_decision_class=decision_class;
}

//+------------------------------------------------------------------+
//| CSV handling                                                     |
//+------------------------------------------------------------------+
string DefaultCSVFileName(const string suffix)
{
   string tag=CleanFilePart(InpRunTag);
   if(tag=="")
      tag="run";
   string schema_suffix=suffix;
   if(UseOFProxyCSV())
      schema_suffix=suffix+"_ofproxy_v2";
   return InpCSVFolder+"\\"+_Symbol+"_"+PeriodString()+"_"+tag+"_"+schema_suffix+".csv";
}

void WriteSignalHeader(const int handle)
{
   if(UseOFProxyCSV())
   {
      FileWrite(handle,
                "schema_version",
                "symbol","timeframe","bar_time","direction","score","wavelet_energy","noise_ratio",
                "volume_ratio","spread_points","atr","pivot_distance_atr","structure_class",
                "debug_reason_code","close_price","signal_price",
                "of_proxy_data_mode","of_proxy_delta","of_proxy_divergence","of_proxy_aggression",
                "of_proxy_stacked_pressure","of_proxy_absorption","of_proxy_confluence_score",
                "of_proxy_raw_state","of_proxy_decision_state","of_proxy_reason_code","of_proxy_adjusted_score",
                "of_proxy_alignment_score","of_proxy_evidence_score","of_proxy_conflict_score","of_proxy_profile_state",
                "of_proxy_decision_class","of_proxy_signal_direction",
                "fwd_ret_"+IntegerToString(InpForwardBars1)+"_points",
                "fwd_ret_"+IntegerToString(InpForwardBars2)+"_points",
                "fwd_ret_"+IntegerToString(InpForwardBars3)+"_points",
                "fwd_ret_"+IntegerToString(InpForwardBars4)+"_points",
                "fwd_ret_"+IntegerToString(InpForwardBars5)+"_points",
                "export_time","maturity_status");
      return;
   }

   FileWrite(handle,
             "symbol","timeframe","bar_time","direction","score","wavelet_energy","noise_ratio",
             "volume_ratio","spread_points","atr","pivot_distance_atr","structure_class",
             "debug_reason_code","close_price","signal_price",
             "fwd_ret_"+IntegerToString(InpForwardBars1)+"_points",
             "fwd_ret_"+IntegerToString(InpForwardBars2)+"_points",
             "fwd_ret_"+IntegerToString(InpForwardBars3)+"_points",
             "fwd_ret_"+IntegerToString(InpForwardBars4)+"_points",
             "fwd_ret_"+IntegerToString(InpForwardBars5)+"_points",
             "export_time","maturity_status");
}

void WriteTradeHeader(const int handle)
{
   if(UseOFProxyCSV())
   {
      FileWrite(handle,
                "schema_version",
                "event_type","symbol","timeframe","signal_bar_time","open_time","close_time","direction",
                "entry","exit","score","reason_opened","reason_blocked","reason_closed","profit",
                "mfe_points","mae_points","spread_entry_points","ticket","magic",
                "of_proxy_state_at_entry","of_proxy_score_at_entry","of_proxy_reason_at_entry",
                "of_proxy_state_at_exit","of_proxy_score_at_exit","of_proxy_reason_at_exit");
      return;
   }

   FileWrite(handle,
             "event_type","symbol","timeframe","signal_bar_time","open_time","close_time","direction",
             "entry","exit","score","reason_opened","reason_blocked","reason_closed","profit",
             "mfe_points","mae_points","spread_entry_points","ticket","magic");
}

int OpenCSVFile(const string filename,const bool append,const bool is_signal)
{
   string folder="";
   const int slash=StringFind(filename,"\\");
   const int forward=StringFind(filename,"/");
   int last=-1;
   int pos=slash;
   while(pos>=0)
   {
      last=pos;
      pos=StringFind(filename,"\\",pos+1);
   }
   pos=forward;
   while(pos>=0)
   {
      if(pos>last)
         last=pos;
      pos=StringFind(filename,"/",pos+1);
   }
   if(last>0)
   {
      folder=StringSubstr(filename,0,last);
      ResetLastError();
      if(!FolderCreate(folder) && GetLastError()!=5019)
         PrintFormat("CSV folder create failed or already unavailable: %s, error=%d",folder,GetLastError());
   }

   bool existed=FileIsExist(filename);
   int flags=FILE_WRITE|FILE_CSV|FILE_SHARE_READ|FILE_SHARE_WRITE;
   if(append)
      flags|=FILE_READ;

   ResetLastError();
   int handle=FileOpen(filename,flags,',');
   if(handle==INVALID_HANDLE)
   {
      PrintFormat("CSV open failed: %s, error=%d",filename,GetLastError());
      return INVALID_HANDLE;
   }

   if(append)
      FileSeek(handle,0,SEEK_END);

   if(!existed || FileSize(handle)==0)
   {
      if(is_signal)
         WriteSignalHeader(handle);
      else
         WriteTradeHeader(handle);
      FileFlush(handle);
   }
   return handle;
}

void InitCSV()
{
   if(InpExportSignalCSV)
   {
      g_signal_filename=(InpSignalCSVFile=="" ? DefaultCSVFileName("signals") : InpSignalCSVFile);
      g_signal_file=OpenCSVFile(g_signal_filename,InpAppendCSV,true);
   }
   if(InpExportTradeCSV)
   {
      g_trade_filename=(InpTradeCSVFile=="" ? DefaultCSVFileName("trades") : InpTradeCSVFile);
      g_trade_file=OpenCSVFile(g_trade_filename,InpAppendCSV,false);
   }
}

void CloseCSV()
{
   if(g_signal_file!=INVALID_HANDLE)
   {
      FileFlush(g_signal_file);
      FileClose(g_signal_file);
      g_signal_file=INVALID_HANDLE;
   }
   if(g_trade_file!=INVALID_HANDLE)
   {
      FileFlush(g_trade_file);
      FileClose(g_trade_file);
      g_trade_file=INVALID_HANDLE;
   }
}

void WriteSignalRow(const SignalSnapshot &s,const double &returns_points[],const string maturity_status)
{
   if(!InpExportSignalCSV || g_signal_file==INVALID_HANDLE)
      return;

   if(UseOFProxyCSV())
   {
      FileWrite(g_signal_file,
                "ofproxy_v2",
                _Symbol,
                PeriodString(),
                TimeString(s.bar_time),
                DirectionString(s.direction),
                DoubleField(s.score,6),
                DoubleField(s.wavelet_energy,6),
                DoubleField(s.noise_ratio,6),
                DoubleField(s.volume_ratio,6),
                DoubleField(s.spread_points,1),
                DoubleField(s.atr,_Digits),
                DoubleField(s.pivot_distance_atr,6),
                IntegerToString(s.structure_class),
                IntegerToString(s.debug_mask),
                DoubleField(s.close_price,_Digits),
                DoubleField(s.signal_price,_Digits),
                IntegerToString(s.of_data_mode),
                (s.of_available ? DoubleField(s.of_delta,6) : ""),
                (s.of_available ? DoubleField(s.of_divergence,6) : ""),
                (s.of_available ? DoubleField(s.of_aggression,6) : ""),
                (s.of_available ? DoubleField(s.of_stacked_pressure,6) : ""),
                (s.of_available ? DoubleField(s.of_absorption,6) : ""),
                (s.of_available ? DoubleField(s.of_confluence_score,6) : ""),
                IntegerToString(s.of_raw_state),
                IntegerToString(s.of_decision_state),
                IntegerToString(s.of_reason_code),
                DoubleField(s.of_adjusted_score,6),
                (s.of_available ? DoubleField(s.of_alignment_score,6) : ""),
                (s.of_available ? DoubleField(s.of_evidence_score,6) : ""),
                (s.of_available ? DoubleField(s.of_conflict_score,6) : ""),
                IntegerToString(s.of_profile_state),
                s.of_decision_class,
                IntegerToString(s.direction),
                DoubleField(returns_points[0],2),
                DoubleField(returns_points[1],2),
                DoubleField(returns_points[2],2),
                DoubleField(returns_points[3],2),
                DoubleField(returns_points[4],2),
                TimeString(TimeCurrent()),
                maturity_status);
      FileFlush(g_signal_file);
      return;
   }

   FileWrite(g_signal_file,
             _Symbol,
             PeriodString(),
             TimeString(s.bar_time),
             DirectionString(s.direction),
             DoubleField(s.score,6),
             DoubleField(s.wavelet_energy,6),
             DoubleField(s.noise_ratio,6),
             DoubleField(s.volume_ratio,6),
             DoubleField(s.spread_points,1),
             DoubleField(s.atr,_Digits),
             DoubleField(s.pivot_distance_atr,6),
             IntegerToString(s.structure_class),
             IntegerToString(s.debug_mask),
             DoubleField(s.close_price,_Digits),
             DoubleField(s.signal_price,_Digits),
             DoubleField(returns_points[0],2),
             DoubleField(returns_points[1],2),
             DoubleField(returns_points[2],2),
             DoubleField(returns_points[3],2),
             DoubleField(returns_points[4],2),
             TimeString(TimeCurrent()),
             maturity_status);
   FileFlush(g_signal_file);
}

void WriteTradeRow(const string event_type,
                   const datetime signal_time,
                   const datetime open_time,
                   const datetime close_time,
                   const int direction,
                   const double entry,
                   const double exit_price,
                   const double score,
                   const string reason_opened,
                   const string reason_blocked,
                   const string reason_closed,
                   const double profit,
                   const double mfe_points,
                   const double mae_points,
                   const double spread_entry_points,
                   const ulong ticket,
                   const int of_state_at_entry=0,
                   const double of_score_at_entry=EMPTY_VALUE,
                   const int of_reason_at_entry=0,
                   const int of_state_at_exit=0,
                   const double of_score_at_exit=EMPTY_VALUE,
                   const int of_reason_at_exit=0)
{
   if(!InpExportTradeCSV || g_trade_file==INVALID_HANDLE)
      return;

   if(UseOFProxyCSV())
   {
      FileWrite(g_trade_file,
                "ofproxy_v2",
                event_type,
                _Symbol,
                PeriodString(),
                TimeString(signal_time),
                TimeString(open_time),
                TimeString(close_time),
                DirectionString(direction),
                DoubleField(entry,_Digits),
                DoubleField(exit_price,_Digits),
                DoubleField(score,6),
                reason_opened,
                reason_blocked,
                reason_closed,
                DoubleField(profit,2),
                DoubleField(mfe_points,2),
                DoubleField(mae_points,2),
                DoubleField(spread_entry_points,1),
                (ticket>0 ? IntegerToString((long)ticket) : ""),
                IntegerToString((long)g_magic),
                (of_state_at_entry!=0 ? IntegerToString(of_state_at_entry) : ""),
                DoubleField(of_score_at_entry,6),
                (of_reason_at_entry!=0 ? IntegerToString(of_reason_at_entry) : ""),
                (of_state_at_exit!=0 ? IntegerToString(of_state_at_exit) : ""),
                DoubleField(of_score_at_exit,6),
                (of_reason_at_exit!=0 ? IntegerToString(of_reason_at_exit) : ""));
      FileFlush(g_trade_file);
      return;
   }

   FileWrite(g_trade_file,
             event_type,
             _Symbol,
             PeriodString(),
             TimeString(signal_time),
             TimeString(open_time),
             TimeString(close_time),
             DirectionString(direction),
             DoubleField(entry,_Digits),
             DoubleField(exit_price,_Digits),
             DoubleField(score,6),
             reason_opened,
             reason_blocked,
             reason_closed,
             DoubleField(profit,2),
             DoubleField(mfe_points,2),
             DoubleField(mae_points,2),
             DoubleField(spread_entry_points,1),
             (ticket>0 ? IntegerToString((long)ticket) : ""),
             IntegerToString((long)g_magic));
   FileFlush(g_trade_file);
}

//+------------------------------------------------------------------+
//| Indicator access                                                 |
//+------------------------------------------------------------------+
bool CopyOne(const int buffer_index,const int shift,double &value)
{
   return CopyOneFromHandle(g_indicator_handle,buffer_index,shift,value);
}

bool CopyOneFromHandle(const int handle,const int buffer_index,const int shift,double &value)
{
   double tmp[1];
   ResetLastError();
   const int copied=CopyBuffer(handle,buffer_index,shift,1,tmp);
   if(copied!=1)
   {
      const int err=GetLastError();
      if(err!=0)
         PrintFormat("CopyBuffer failed buffer=%d shift=%d error=%d",buffer_index,shift,err);
      return false;
   }
   value=tmp[0];
   return true;
}

void DeriveOFProxyDecision(SignalSnapshot &s)
{
   s.of_adjusted_score=s.score;
   s.of_decision_state=0;
   s.of_profile_state=0;
   if(!s.of_available || s.direction==0)
      return;

   const double alignment=(double)s.direction*s.of_confluence_score;
   const double delta_alignment=(double)s.direction*s.of_delta*0.50;
   const double aggression_alignment=(double)s.direction*s.of_aggression;
   const double stacked_alignment=(double)s.direction*s.of_stacked_pressure;
   const double absorption_alignment=(double)s.direction*s.of_absorption;
   const double divergence_alignment=(double)s.direction*s.of_divergence;
   double evidence=MathMax(0.0,alignment);
   evidence=MathMax(evidence,delta_alignment);
   evidence=MathMax(evidence,aggression_alignment);
   evidence=MathMax(evidence,stacked_alignment);
   evidence=MathMax(evidence,absorption_alignment);
   evidence=MathMax(evidence,divergence_alignment);

   double conflict=MathMax(0.0,-alignment);
   conflict=MathMax(conflict,-delta_alignment);
   conflict=MathMax(conflict,-aggression_alignment);
   conflict=MathMax(conflict,-stacked_alignment);
   conflict=MathMax(conflict,-absorption_alignment);
   conflict=MathMax(conflict,-divergence_alignment);

   s.of_alignment_score=alignment;
   s.of_evidence_score=evidence;
   s.of_conflict_score=conflict;

   const double proceedEvidence=MathMax(InpOFDecisionProceedEvidence,0.0);
   const double maxProceedConflict=MathMax(InpOFDecisionMaxProceedConflict,0.0);
   const double standDownConflict=MathMax(InpOFDecisionStandDownConflict,0.0);
   const double noEvidence=MathMax(InpOFDecisionNoEvidenceThreshold,0.0);

   if(conflict>=standDownConflict || absorption_alignment<=-0.20)
   {
      s.of_decision_state=-2;
      s.of_profile_state=-2;
      s.of_decision_class=OFDecisionClass(s.of_decision_state,s.of_profile_state);
      return;
   }

   if(evidence<noEvidence && MathAbs(alignment)<noEvidence)
   {
      s.of_decision_state=-2;
      s.of_profile_state=-1;
      s.of_decision_class=OFDecisionClass(s.of_decision_state,s.of_profile_state);
      return;
   }

   if(evidence>=proceedEvidence && conflict<maxProceedConflict)
   {
      s.of_decision_state=s.direction;
      s.of_profile_state=1;
      s.of_decision_class=OFDecisionClass(s.of_decision_state,s.of_profile_state);
      return;
   }

   s.of_decision_state=2;
   s.of_profile_state=2;
   s.of_decision_class=OFDecisionClass(s.of_decision_state,s.of_profile_state);
}

void ReadOFProxyAtShift(const int shift,SignalSnapshot &s)
{
   ClearOFProxyFields(s);
   if(!InpUseOrderFlowProxy)
      return;
   if(g_of_indicator_handle==INVALID_HANDLE)
   {
      MarkOFProxyUnavailable(s,-2,"proxy_handle_invalid");
      return;
   }
   if(BarsCalculated(g_of_indicator_handle)<=0)
   {
      MarkOFProxyUnavailable(s,-1,"proxy_not_ready");
      return;
   }

   double value=0.0;
   bool ok=true;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_DELTA,shift,value) && ok);
   s.of_delta=value;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_DIVERGENCE,shift,value) && ok);
   s.of_divergence=value;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_AGGRESSION,shift,value) && ok);
   s.of_aggression=value;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_STACKED,shift,value) && ok);
   s.of_stacked_pressure=value;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_ABSORPTION,shift,value) && ok);
   s.of_absorption=value;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_CONFLUENCE,shift,value) && ok);
   s.of_confluence_score=value;
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_RAW_STATE,shift,value) && ok);
   s.of_raw_state=(int)MathRound(value);
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_REASON,shift,value) && ok);
   s.of_reason_code=(int)MathRound(value);
   ok=(CopyOneFromHandle(g_of_indicator_handle,OF_BUF_DATA_MODE,shift,value) && ok);
   s.of_data_mode=(int)MathRound(value);

   s.of_available=ok && s.of_data_mode>0;
   if(!s.of_available)
      MarkOFProxyUnavailable(s,(ok ? s.of_data_mode : -1),"proxy_not_ready");
   else
      DeriveOFProxyDecision(s);
}

bool ReadSignalAtShift(const int shift,SignalSnapshot &s)
{
   if(g_indicator_handle==INVALID_HANDLE || BarsCalculated(g_indicator_handle)<=0)
      return false;

   double direction_value=0.0;
   if(!CopyOne(BUF_DIRECTION,shift,direction_value))
      return false;

   const int direction=(int)MathRound(direction_value);
   if(direction==0)
      return false;
   if(direction!=1 && direction!=-1)
   {
      PrintFormat("Ignoring invalid SignalState value at shift=%d: %.6f",shift,direction_value);
      return false;
   }

   s.direction=direction;
   s.bar_time=iTime(_Symbol,_Period,shift);
   s.close_price=iClose(_Symbol,_Period,shift);

   double buy_price=EMPTY_VALUE;
   double sell_price=EMPTY_VALUE;
   CopyOne(BUF_BUY_PRICE,shift,buy_price);
   CopyOne(BUF_SELL_PRICE,shift,sell_price);
   s.signal_price=(direction>0 ? buy_price : sell_price);
   if(s.signal_price==EMPTY_VALUE || s.signal_price==DBL_MAX)
      s.signal_price=s.close_price;

   double value=0.0;
   if(CopyOne(BUF_SCORE,shift,value))             s.score=value; else s.score=0.0;
   if(CopyOne(BUF_WAVELET,shift,value))           s.wavelet_energy=value; else s.wavelet_energy=0.0;
   if(CopyOne(BUF_NOISE,shift,value))             s.noise_ratio=value; else s.noise_ratio=0.0;
   if(CopyOne(BUF_VOLUME,shift,value))            s.volume_ratio=value; else s.volume_ratio=0.0;
   if(CopyOne(BUF_SPREAD,shift,value))            s.spread_points=value; else s.spread_points=0.0;
   if(CopyOne(BUF_ATR,shift,value))               s.atr=value; else s.atr=0.0;
   if(CopyOne(BUF_PIVOT_DISTANCE,shift,value))    s.pivot_distance_atr=value; else s.pivot_distance_atr=0.0;
   if(CopyOne(BUF_STRUCTURE,shift,value))         s.structure_class=(int)MathRound(value); else s.structure_class=0;
   if(CopyOne(BUF_DEBUG,shift,value))             s.debug_mask=(int)MathRound(value); else s.debug_mask=0;

   ReadOFProxyAtShift(shift,s);
   return true;
}

void CurrentOFProxyExitFields(const int direction,int &state,double &score,int &reason)
{
   state=0;
   score=EMPTY_VALUE;
   reason=0;
   if(!InpUseOrderFlowProxy)
      return;

   SignalSnapshot s;
   s.direction=direction;
   s.score=0.0;
   ClearOFProxyFields(s);
   ReadOFProxyAtShift(1,s);
   if(!s.of_available)
      return;

   state=s.of_decision_state;
   score=s.of_confluence_score;
   reason=s.of_reason_code;
}

//+------------------------------------------------------------------+
//| Forward-return diagnostics                                       |
//+------------------------------------------------------------------+
void AddPendingSignal(const SignalSnapshot &s)
{
   const int n=ArraySize(g_pending_signals);
   ArrayResize(g_pending_signals,n+1);
   g_pending_signals[n]=s;
}

void RemovePendingSignal(const int index)
{
   const int n=ArraySize(g_pending_signals);
   if(index<0 || index>=n)
      return;
   for(int i=index;i<n-1;i++)
      g_pending_signals[i]=g_pending_signals[i+1];
   ArrayResize(g_pending_signals,n-1);
}

void ComputeForwardReturns(const SignalSnapshot &s,double &returns_points[],bool &complete)
{
   ArrayResize(returns_points,5);
   for(int i=0;i<5;i++)
      returns_points[i]=EMPTY_VALUE;

   int bars[5];
   bars[0]=InpForwardBars1;
   bars[1]=InpForwardBars2;
   bars[2]=InpForwardBars3;
   bars[3]=InpForwardBars4;
   bars[4]=InpForwardBars5;

   complete=true;
   const int signal_shift=iBarShift(_Symbol,_Period,s.bar_time,true);
   if(signal_shift<0)
   {
      complete=false;
      return;
   }

   for(int j=0;j<5;j++)
   {
      const int fwd=bars[j];
      if(fwd<=0)
      {
         returns_points[j]=0.0;
         continue;
      }
      if(signal_shift>=fwd+1)
      {
         const int target_shift=signal_shift-fwd;
         const double target_close=iClose(_Symbol,_Period,target_shift);
         if(target_close>0.0)
            returns_points[j]=((double)s.direction)*(target_close-s.close_price)/_Point;
         else
            complete=false;
      }
      else
         complete=false;
   }
}

void FlushPendingSignals(const bool only_matured)
{
   if(!InpExportSignalCSV || !InpWriteForwardReturns)
      return;

   const int max_fwd=MaxForwardBars();
   for(int i=ArraySize(g_pending_signals)-1;i>=0;i--)
   {
      const int signal_shift=iBarShift(_Symbol,_Period,g_pending_signals[i].bar_time,true);
      if(signal_shift<0)
         continue;

      const bool matured=(signal_shift>=max_fwd+1);
      if(!matured && only_matured)
         continue;
      if(!matured && !InpWriteIncompleteForwardRowsOnDeinit)
         continue;

      double returns_points[];
      bool complete=false;
      ComputeForwardReturns(g_pending_signals[i],returns_points,complete);
      WriteSignalRow(g_pending_signals[i],returns_points,(complete ? "matured" : "partial"));
      RemovePendingSignal(i);
   }
}

void ExportSignalNowOrPending(const SignalSnapshot &s)
{
   if(!InpExportSignalCSV)
      return;

   if(InpWriteForwardReturns)
      AddPendingSignal(s);
   else
   {
      double returns_points[];
      ArrayResize(returns_points,5);
      for(int i=0;i<5;i++)
         returns_points[i]=EMPTY_VALUE;
      WriteSignalRow(s,returns_points,"not_requested");
   }
}

//+------------------------------------------------------------------+
//| Position and account helpers                                     |
//+------------------------------------------------------------------+
bool FindOwnPosition(ulong &ticket,int &direction,double &entry,datetime &open_time,double &profit)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      const ulong pos_ticket=PositionGetTicket(i);
      if(pos_ticket==0)
         continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=g_magic)
         continue;

      const long type=PositionGetInteger(POSITION_TYPE);
      ticket=pos_ticket;
      direction=(type==POSITION_TYPE_BUY ? 1 : -1);
      entry=PositionGetDouble(POSITION_PRICE_OPEN);
      open_time=(datetime)PositionGetInteger(POSITION_TIME);
      profit=PositionGetDouble(POSITION_PROFIT);
      return true;
   }
   return false;
}

bool HasAnySymbolPosition()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      const ulong pos_ticket=PositionGetTicket(i);
      if(pos_ticket==0)
         continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol)
         return true;
   }
   return false;
}

int VolumeDigitsFromStep(const double step)
{
   if(step<=0.0)
      return 2;
   for(int digits=0;digits<=8;digits++)
   {
      const double scaled=step*MathPow(10.0,digits);
      if(MathAbs(scaled-MathRound(scaled))<0.0000001)
         return digits;
   }
   return 8;
}

bool ResolveVolumeForSymbol(const double lots,double &volume,string &reason_blocked)
{
   double minLot=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maxLot=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(minLot<=0.0) minLot=0.01;
   if(maxLot<=0.0) maxLot=100.0;
   if(step<=0.0)   step=0.01;

   const double safetyMax=MathMax(InpMaxSafetyLots,0.0);
   if(lots<minLot)
   {
      reason_blocked="configured_lots_below_symbol_min_"+DoubleToString(minLot,VolumeDigitsFromStep(step));
      volume=0.0;
      return false;
   }
   if(lots>maxLot)
   {
      reason_blocked="configured_lots_above_symbol_max_"+DoubleToString(maxLot,VolumeDigitsFromStep(step));
      volume=0.0;
      return false;
   }
   if(safetyMax>0.0 && lots>safetyMax)
   {
      reason_blocked="configured_lots_above_research_safety_cap_"+DoubleToString(safetyMax,VolumeDigitsFromStep(step));
      volume=0.0;
      return false;
   }

   volume=MathFloor(lots/step)*step;
   volume=MathFloor(volume/step)*step;
   volume=NormalizeDouble(volume,VolumeDigitsFromStep(step));
   if(volume<minLot)
   {
      reason_blocked="normalized_lots_below_symbol_min_"+DoubleToString(minLot,VolumeDigitsFromStep(step));
      volume=0.0;
      return false;
   }
   return true;
}

bool DealMatchesDailyGuardScope(const ulong deal)
{
   if(InpDailyGuardsAccountWide)
      return true;
   if(HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol)
      return false;
   if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=g_magic)
      return false;
   return true;
}

double RealizedPLToday()
{
   const datetime now=TimeCurrent();
   const datetime start=DayStart(now);
   double pl=0.0;
   if(!HistorySelect(start,now+60))
      return pl;

   const int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      const ulong deal=HistoryDealGetTicket(i);
      if(deal==0)
         continue;
      if(!DealMatchesDailyGuardScope(deal))
         continue;

      const long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_INOUT)
      {
         pl+=HistoryDealGetDouble(deal,DEAL_PROFIT);
         pl+=HistoryDealGetDouble(deal,DEAL_COMMISSION);
         pl+=HistoryDealGetDouble(deal,DEAL_SWAP);
      }
   }
   return pl;
}

int TradesOpenedTodayFromHistory()
{
   const datetime now=TimeCurrent();
   const datetime start=DayStart(now);
   int count=0;
   if(!HistorySelect(start,now+60))
      return count;

   const int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      const ulong deal=HistoryDealGetTicket(i);
      if(deal==0)
         continue;
      if(!DealMatchesDailyGuardScope(deal))
         continue;

      const long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
         count++;
   }
   return count;
}

void UpdateDailyState()
{
   const datetime now=TimeCurrent();
   const datetime start=DayStart(now);
   if(g_today_start==0 || start!=g_today_start)
   {
      g_today_start=start;
      g_trades_today=TradesOpenedTodayFromHistory();
   }
}

bool LastCloseDealFromHistory(const datetime from_time,datetime &close_time,double &exit_price,double &profit)
{
   close_time=0;
   exit_price=0.0;
   profit=0.0;

   datetime from=from_time-300;
   if(from<0)
      from=0;
   if(!HistorySelect(from,TimeCurrent()+300))
      return false;

   for(int i=HistoryDealsTotal()-1;i>=0;i--)
   {
      const ulong deal=HistoryDealGetTicket(i);
      if(deal==0)
         continue;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=g_magic)
         continue;

      const long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_INOUT)
      {
         close_time=(datetime)HistoryDealGetInteger(deal,DEAL_TIME);
         exit_price=HistoryDealGetDouble(deal,DEAL_PRICE);
         profit=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_SWAP);
         return true;
      }
   }
   return false;
}

void SyncActiveMetadataFromPosition()
{
   ulong ticket=0;
   int direction=0;
   double entry=0.0;
   datetime open_time=0;
   double profit=0.0;
   if(!FindOwnPosition(ticket,direction,entry,open_time,profit))
      return;

   if(!g_active.valid || g_active.ticket!=ticket)
   {
      g_active.valid=true;
      g_active.ticket=ticket;
      g_active.signal_time=0;
      g_active.open_time=open_time;
      g_active.direction=direction;
      g_active.entry=entry;
      g_active.score=0.0;
      g_active.reason_opened="restored_position";
      g_active.spread_entry_points=(double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
      g_active.mfe_points=0.0;
      g_active.mae_points=0.0;
   }
}

void UpdateOpenTradeExcursions()
{
   if(!g_active.valid || g_active.entry<=0.0)
      return;

   const double h=iHigh(_Symbol,_Period,1);
   const double l=iLow(_Symbol,_Period,1);
   if(h<=0.0 || l<=0.0)
      return;

   if(g_active.direction>0)
   {
      g_active.mfe_points=MathMax(g_active.mfe_points,(h-g_active.entry)/_Point);
      g_active.mae_points=MathMax(g_active.mae_points,(g_active.entry-l)/_Point);
   }
   else if(g_active.direction<0)
   {
      g_active.mfe_points=MathMax(g_active.mfe_points,(g_active.entry-l)/_Point);
      g_active.mae_points=MathMax(g_active.mae_points,(h-g_active.entry)/_Point);
   }
}

bool CloseOwnPosition(const string reason_closed)
{
   ulong ticket=0;
   int direction=0;
   double entry=0.0;
   datetime open_time=0;
   double open_profit=0.0;
   if(!FindOwnPosition(ticket,direction,entry,open_time,open_profit))
      return false;

   ActiveTradeState snapshot=g_active;
   if(!snapshot.valid)
   {
      snapshot.valid=true;
      snapshot.ticket=ticket;
      snapshot.signal_time=0;
      snapshot.open_time=open_time;
      snapshot.direction=direction;
      snapshot.entry=entry;
      snapshot.score=0.0;
      snapshot.reason_opened="restored_position";
      snapshot.spread_entry_points=(double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
      snapshot.mfe_points=0.0;
      snapshot.mae_points=0.0;
   }

   ResetLastError();
   const bool ok=trade.PositionClose(ticket,(ulong)InpSlippagePoints);
   if(!ok)
   {
      PrintFormat("PositionClose failed. retcode=%u %s error=%d",trade.ResultRetcode(),trade.ResultRetcodeDescription(),GetLastError());
      return false;
   }

   datetime close_time=TimeCurrent();
   double exit_price=(direction>0 ? SymbolInfoDouble(_Symbol,SYMBOL_BID) : SymbolInfoDouble(_Symbol,SYMBOL_ASK));
   double profit=open_profit;
   datetime hist_close=0;
   double hist_exit=0.0;
   double hist_profit=0.0;
   if(LastCloseDealFromHistory(open_time,hist_close,hist_exit,hist_profit))
   {
      close_time=hist_close;
      exit_price=hist_exit;
      profit=hist_profit;
   }

   int of_exit_state=0;
   double of_exit_score=EMPTY_VALUE;
   int of_exit_reason=0;
   CurrentOFProxyExitFields(snapshot.direction,of_exit_state,of_exit_score,of_exit_reason);

   WriteTradeRow("closed",snapshot.signal_time,snapshot.open_time,close_time,snapshot.direction,
                 snapshot.entry,exit_price,snapshot.score,snapshot.reason_opened,"",reason_closed,
                 profit,snapshot.mfe_points,snapshot.mae_points,snapshot.spread_entry_points,snapshot.ticket,
                 snapshot.of_state_at_entry,snapshot.of_score_at_entry,snapshot.of_reason_at_entry,
                 of_exit_state,of_exit_score,of_exit_reason);
   g_active.valid=false;
   return true;
}

void DetectExternalCloseIfNeeded()
{
   if(!g_active.valid)
      return;

   ulong ticket=0;
   int direction=0;
   double entry=0.0;
   datetime open_time=0;
   double open_profit=0.0;
   if(FindOwnPosition(ticket,direction,entry,open_time,open_profit))
      return;

   datetime close_time=TimeCurrent();
   double exit_price=(g_active.direction>0 ? SymbolInfoDouble(_Symbol,SYMBOL_BID) : SymbolInfoDouble(_Symbol,SYMBOL_ASK));
   double profit=0.0;
   datetime hist_close=0;
   double hist_exit=0.0;
   double hist_profit=0.0;
   if(LastCloseDealFromHistory(g_active.open_time,hist_close,hist_exit,hist_profit))
   {
      close_time=hist_close;
      exit_price=hist_exit;
      profit=hist_profit;
   }

   int of_exit_state=0;
   double of_exit_score=EMPTY_VALUE;
   int of_exit_reason=0;
   CurrentOFProxyExitFields(g_active.direction,of_exit_state,of_exit_score,of_exit_reason);

   WriteTradeRow("closed",g_active.signal_time,g_active.open_time,close_time,g_active.direction,
                 g_active.entry,exit_price,g_active.score,g_active.reason_opened,"","external_or_sl_tp",
                 profit,g_active.mfe_points,g_active.mae_points,g_active.spread_entry_points,g_active.ticket,
                 g_active.of_state_at_entry,g_active.of_score_at_entry,g_active.of_reason_at_entry,
                 of_exit_state,of_exit_score,of_exit_reason);
   g_active.valid=false;
}

void ManageOpenPosition()
{
   DetectExternalCloseIfNeeded();
   SyncActiveMetadataFromPosition();
   if(!g_active.valid)
      return;

   UpdateOpenTradeExcursions();
   if(InpTimeExitBars>0)
   {
      const int bars_open=iBarShift(_Symbol,_Period,g_active.open_time,false);
      if(bars_open>=InpTimeExitBars)
         CloseOwnPosition("time_exit_"+IntegerToString(InpTimeExitBars)+"_bars");
   }
}

//+------------------------------------------------------------------+
//| Execution decision                                               |
//+------------------------------------------------------------------+
bool TradingGuardAllows(string &reason_blocked)
{
   reason_blocked="";
   if(!g_trade_enabled || !InpAllowTrading)
   {
      reason_blocked="observe_only";
      return false;
   }

   if(InpDemoAccountsOnly && (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
   {
      reason_blocked="demo_accounts_only";
      return false;
   }

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      reason_blocked="terminal_trade_not_allowed";
      return false;
   }

   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      reason_blocked="ea_trade_not_allowed";
      return false;
   }

   if(InpEntryMaxSpreadPoints>0 && (int)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD)>InpEntryMaxSpreadPoints)
   {
      reason_blocked="entry_spread_filter";
      return false;
   }

   if(InpMaxTradesPerDay>0 && g_trades_today>=InpMaxTradesPerDay)
   {
      reason_blocked="daily_trade_count_guard";
      return false;
   }

   if(InpDailyLossLimitMoney>0.0 && RealizedPLToday()<=-MathAbs(InpDailyLossLimitMoney))
   {
      reason_blocked="daily_loss_guard";
      return false;
   }

   if(InpOnePositionPerSymbol && HasAnySymbolPosition())
   {
      reason_blocked="symbol_position_exists";
      return false;
   }

   ulong ticket=0;
   int direction=0;
   double entry=0.0;
   datetime open_time=0;
   double profit=0.0;
   if(FindOwnPosition(ticket,direction,entry,open_time,profit))
   {
      reason_blocked="own_position_exists";
      return false;
   }

   return true;
}

void BuildStops(const int direction,const double entry,const double atr,double &sl,double &tp)
{
   sl=0.0;
   tp=0.0;
   if(!InpUseATRStops || atr<=_Point)
      return;

   const double minStopDistance=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   double slDist=MathMax(MathAbs(InpATRStopLossMult)*atr,minStopDistance);
   double tpDist=MathMax(MathAbs(InpATRTakeProfitMult)*atr,minStopDistance);

   if(direction>0)
   {
      sl=NormalizeDouble(entry-slDist,_Digits);
      tp=NormalizeDouble(entry+tpDist,_Digits);
   }
   else
   {
      sl=NormalizeDouble(entry+slDist,_Digits);
      tp=NormalizeDouble(entry-tpDist,_Digits);
   }
}

bool TryOpenTrade(const SignalSnapshot &s,string &reason_opened,string &reason_blocked)
{
   reason_opened="";
   reason_blocked="";

   if(s.score<InpSignalThreshold)
   {
      reason_blocked="below_ea_threshold";
      return false;
   }

   if(!TradingGuardAllows(reason_blocked))
      return false;

   double volume=0.0;
   if(!ResolveVolumeForSymbol(InpLots,volume,reason_blocked) || volume<=0.0)
      return false;

   const double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   const double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   const double entry=(s.direction>0 ? ask : bid);
   if(entry<=0.0)
   {
      reason_blocked="invalid_market_price";
      return false;
   }

   double sl=0.0;
   double tp=0.0;
   BuildStops(s.direction,entry,s.atr,sl,tp);

   if(InpPreferFOK)
      trade.SetTypeFilling(ORDER_FILLING_FOK);
   else
      trade.SetTypeFillingBySymbol(_Symbol);

   const string comment="AWES_"+DirectionString(s.direction)+"_"+DoubleToString(s.score,2);
   ResetLastError();
   bool ok=false;
   if(s.direction>0)
      ok=trade.Buy(volume,_Symbol,0.0,sl,tp,comment);
   else
      ok=trade.Sell(volume,_Symbol,0.0,sl,tp,comment);

   // If a symbol rejects the preferred FOK filling, retry once with broker-reported filling mode.
   if(!ok && InpPreferFOK)
   {
      trade.SetTypeFillingBySymbol(_Symbol);
      ResetLastError();
      if(s.direction>0)
         ok=trade.Buy(volume,_Symbol,0.0,sl,tp,comment);
      else
         ok=trade.Sell(volume,_Symbol,0.0,sl,tp,comment);
   }

   if(!ok)
   {
      reason_blocked="trade_send_failed_"+IntegerToString((int)trade.ResultRetcode())+"_"+trade.ResultRetcodeDescription();
      PrintFormat("Trade send failed: %s",reason_blocked);
      return false;
   }

   reason_opened="opened_"+IntegerToString((int)trade.ResultRetcode())+"_"+trade.ResultRetcodeDescription();

   ulong ticket=0;
   int direction=0;
   double pos_entry=0.0;
   datetime open_time=TimeCurrent();
   double pos_profit=0.0;
   if(FindOwnPosition(ticket,direction,pos_entry,open_time,pos_profit))
   {
      g_active.valid=true;
      g_active.ticket=ticket;
      g_active.signal_time=s.bar_time;
      g_active.open_time=open_time;
      g_active.direction=s.direction;
      g_active.entry=pos_entry;
      g_active.score=s.score;
      g_active.reason_opened=reason_opened;
      g_active.spread_entry_points=(double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
      g_active.mfe_points=0.0;
      g_active.mae_points=0.0;
      g_active.of_state_at_entry=s.of_decision_state;
      g_active.of_score_at_entry=s.of_confluence_score;
      g_active.of_reason_at_entry=s.of_reason_code;
   }
   else
   {
      g_active.valid=true;
      g_active.ticket=trade.ResultOrder();
      g_active.signal_time=s.bar_time;
      g_active.open_time=TimeCurrent();
      g_active.direction=s.direction;
      g_active.entry=entry;
      g_active.score=s.score;
      g_active.reason_opened=reason_opened;
      g_active.spread_entry_points=(double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
      g_active.mfe_points=0.0;
      g_active.mae_points=0.0;
      g_active.of_state_at_entry=s.of_decision_state;
      g_active.of_score_at_entry=s.of_confluence_score;
      g_active.of_reason_at_entry=s.of_reason_code;
   }

   g_trades_today++;
   WriteTradeRow("opened",s.bar_time,g_active.open_time,0,s.direction,g_active.entry,EMPTY_VALUE,s.score,
                 reason_opened,"","",EMPTY_VALUE,0.0,0.0,g_active.spread_entry_points,g_active.ticket,
                 s.of_decision_state,s.of_confluence_score,s.of_reason_code);
   return true;
}

void ProcessSignal(const SignalSnapshot &s)
{
   ExportSignalNowOrPending(s);

   // A trade decision row is written even for observe-only and blocked research decisions.
   if(s.score<InpSignalThreshold)
   {
      WriteTradeRow("blocked",s.bar_time,0,0,s.direction,EMPTY_VALUE,EMPTY_VALUE,s.score,"","below_ea_threshold","",EMPTY_VALUE,EMPTY_VALUE,EMPTY_VALUE,s.spread_points,0,
                    s.of_decision_state,s.of_confluence_score,s.of_reason_code);
      return;
   }

   ulong ticket=0;
   int open_dir=0;
   double entry=0.0;
   datetime open_time=0;
   double profit=0.0;
   if(FindOwnPosition(ticket,open_dir,entry,open_time,profit))
   {
      if(InpCloseOnOppositeSignal && open_dir*s.direction<0)
      {
         CloseOwnPosition("opposite_signal");
         WriteTradeRow("blocked",s.bar_time,0,0,s.direction,EMPTY_VALUE,EMPTY_VALUE,s.score,"","opposite_closed_no_same_bar_reverse","",EMPTY_VALUE,EMPTY_VALUE,EMPTY_VALUE,s.spread_points,0,
                       s.of_decision_state,s.of_confluence_score,s.of_reason_code);
      }
      else
         WriteTradeRow("blocked",s.bar_time,open_time,0,s.direction,entry,EMPTY_VALUE,s.score,"","position_exists","",EMPTY_VALUE,EMPTY_VALUE,EMPTY_VALUE,s.spread_points,ticket,
                       s.of_decision_state,s.of_confluence_score,s.of_reason_code);
      return;
   }

   string reason_opened="";
   string reason_blocked="";
   if(!TryOpenTrade(s,reason_opened,reason_blocked))
   {
      WriteTradeRow("blocked",s.bar_time,0,0,s.direction,EMPTY_VALUE,EMPTY_VALUE,s.score,"",reason_blocked,"",EMPTY_VALUE,EMPTY_VALUE,EMPTY_VALUE,s.spread_points,0,
                    s.of_decision_state,s.of_confluence_score,s.of_reason_code);
   }
}

//+------------------------------------------------------------------+
//| Event handlers                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   ResetActiveState();
   g_magic=ComputeMagic();
   g_trade_enabled=InpAllowTrading;

   if(InpAllowTrading && InpDemoAccountsOnly && (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
   {
      Print("Trading disabled: InpDemoAccountsOnly=true and this account is not demo.");
      g_trade_enabled=false;
   }

   trade.SetExpertMagicNumber(g_magic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetAsyncMode(false);
   if(InpPreferFOK)
      trade.SetTypeFilling(ORDER_FILLING_FOK);
   else
      trade.SetTypeFillingBySymbol(_Symbol);

   ResetLastError();
   g_indicator_handle=iCustom(_Symbol,_Period,"Advanced_Wavelet_Entry_Signal",
                              InpIndWaveletWindow,
                              InpIndWaveletLevels,
                              InpIndATRPeriod,
                              InpIndVolumeLookback,
                              InpIndPivotLookback,
                              InpIndStructureLookback,
                              InpIndicatorMinSignalScore,
                              InpIndMinWaveletEnergyScore,
                              InpIndMaxNoiseRatio,
                              InpIndMinVolumeAnomaly,
                              InpIndVolumeAnomalyCap,
                              InpIndMaxPivotDistanceATR,
                              InpIndRangeATRTarget,
                              InpIndMaxRangeATRForPenalty,
                              InpIndMinDirectionMargin,
                              InpIndMaxSpreadPoints,
                              InpIndUseSessionFilter,
                              InpIndSessionStartHour,
                              InpIndSessionEndHour,
                              InpIndUseTrendBiasFilter,
                              InpIndUseHardFilters,
                              InpIndRequireVolumeAnomaly,
                              InpIndRequireRejectionQuality,
                              InpIndMinRejectionQuality,
                              InpIndRequirePivotProximity,
                              InpIndMinPivotQuality,
                              InpIndWeightWavelet,
                              InpIndWeightNoise,
                              InpIndWeightVolume,
                              InpIndWeightRejection,
                              InpIndWeightATRRange,
                              InpIndWeightPivot,
                              InpIndWeightStructure,
                              InpIndWeightSpread,
                              InpIndWeightSession,
                              InpIndWeightTrendBias,
                              InpIndArrowOffsetATR);

   if(g_indicator_handle==INVALID_HANDLE)
   {
      PrintFormat("iCustom failed for Advanced_Wavelet_Entry_Signal, error=%d",GetLastError());
      return INIT_FAILED;
   }

   if(InpUseOrderFlowProxy)
   {
      ResetLastError();
      g_of_indicator_handle=iCustom(_Symbol,_Period,InpOFIndicatorName,
                                    InpOFATRPeriod,
                                    InpOFDeltaLookback,
                                    InpOFDivergenceLookback,
                                    InpOFStructureLookback,
                                    InpOFVolumeRatioCap,
                                    InpOFDivergenceMinDeltaGap,
                                    InpOFAggressionMinDelta,
                                    InpOFAggressionMinVolumeRatio,
                                    InpOFStackedMinBars,
                                    InpOFStackedWindowBars,
                                    InpOFAbsorptionMinEffort,
                                    InpOFAbsorptionMaxProgressATR,
                                    InpOFAbsorptionMinWickRatio,
                                    InpOFStructureDistanceATR,
                                    InpOFNeutralThreshold,
                                    InpOFMixedThreshold);
      if(g_of_indicator_handle==INVALID_HANDLE)
      {
         PrintFormat("iCustom failed for required order-flow proxy indicator %s, error=%d",InpOFIndicatorName,GetLastError());
         IndicatorRelease(g_indicator_handle);
         g_indicator_handle=INVALID_HANDLE;
         return INIT_FAILED;
      }
   }

   InitCSV();
   g_today_start=DayStart(TimeCurrent());
   g_trades_today=TradesOpenedTodayFromHistory();
   g_last_bar_time=iTime(_Symbol,_Period,0);
   SyncActiveMetadataFromPosition();

   PrintFormat("Advanced Wavelet Research EA initialized: symbol=%s tf=%s magic=%s trading=%s signal_csv=%s trade_csv=%s",
               _Symbol,PeriodString(),IntegerToString((long)g_magic),(g_trade_enabled ? "true" : "false"),g_signal_filename,g_trade_filename);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   FlushPendingSignals(false);
   if(g_indicator_handle!=INVALID_HANDLE)
   {
      IndicatorRelease(g_indicator_handle);
      g_indicator_handle=INVALID_HANDLE;
   }
   if(g_of_indicator_handle!=INVALID_HANDLE)
   {
      IndicatorRelease(g_of_indicator_handle);
      g_of_indicator_handle=INVALID_HANDLE;
   }
   CloseCSV();
}

void OnTick()
{
   const datetime current_bar_time=iTime(_Symbol,_Period,0);
   if(current_bar_time<=0)
      return;

   if(g_last_bar_time==0)
   {
      g_last_bar_time=current_bar_time;
      return;
   }

   if(current_bar_time==g_last_bar_time)
      return;

   g_last_bar_time=current_bar_time;
   UpdateDailyState();
   FlushPendingSignals(true);
   ManageOpenPosition();

   SignalSnapshot s;
   if(ReadSignalAtShift(1,s))
      ProcessSignal(s);
}

// Custom optimization objective. It is intentionally conservative and penalizes low sample size and drawdown.
double OnTester()
{
   const double profit=TesterStatistics(STAT_PROFIT);
   const double trades=TesterStatistics(STAT_TRADES);
   const double expected=TesterStatistics(STAT_EXPECTED_PAYOFF);
   double pf=TesterStatistics(STAT_PROFIT_FACTOR);
   const double recovery=TesterStatistics(STAT_RECOVERY_FACTOR);
   const double dd_pct=TesterStatistics(STAT_EQUITY_DDREL_PERCENT);

   if(pf==DBL_MAX || pf>10.0)
      pf=10.0;

   const double minTrades=(double)MathMax(InpTesterMinTrades,1);
   double tradePenalty=1.0;
   if(trades<minTrades)
      tradePenalty=MathMax(0.05,(trades/minTrades)*(trades/minTrades));

   const double ddScale=MathMax(InpTesterDDPenaltyPercent,1.0);
   const double ddPenalty=1.0/(1.0+MathMax(dd_pct,0.0)/ddScale);
   const double profitComponent=(profit/100.0)/(1.0+MathAbs(profit/100.0));
   const double pfComponent=pf/10.0;
   const double expectedComponent=(expected/10.0)/(1.0+MathAbs(expected/10.0));
   const double recoveryComponent=(recovery/5.0)/(1.0+MathAbs(recovery/5.0));
   double score=(4.0*profitComponent*tradePenalty*ddPenalty)+(1.0*expectedComponent)+(1.5*recoveryComponent)+(2.0*pfComponent);

   if(trades<minTrades)
      score-=0.10*(minTrades-trades);
   if(profit<=0.0)
      score-=5.0;

   if(MQLInfoInteger(MQL_OPTIMIZATION))
   {
      double frame[7];
      frame[0]=profit;
      frame[1]=trades;
      frame[2]=expected;
      frame[3]=pf;
      frame[4]=recovery;
      frame[5]=dd_pct;
      frame[6]=score;
      FrameAdd("AWES",(long)g_magic,score,frame);
   }

   return score;
}
//+------------------------------------------------------------------+
