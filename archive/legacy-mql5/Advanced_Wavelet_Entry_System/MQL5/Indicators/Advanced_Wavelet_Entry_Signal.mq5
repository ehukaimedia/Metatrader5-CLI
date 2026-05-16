//+------------------------------------------------------------------+
//| Advanced_Wavelet_Entry_Signal.mq5                                |
//| Closed-bar, non-repainting wavelet-confluence entry indicator.    |
//| Research prototype. No profitability claims.                     |
//+------------------------------------------------------------------+
#property strict
#property copyright "Research prototype"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 16
#property indicator_plots   16

#property indicator_label1  "BuySignalPrice"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_style1  STYLE_SOLID
#property indicator_width1  1

#property indicator_label2  "SellSignalPrice"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrTomato
#property indicator_style2  STYLE_SOLID
#property indicator_width2  1

#property indicator_label3  "DirectionState"
#property indicator_type3   DRAW_NONE
#property indicator_label4  "SignalScore"
#property indicator_type4   DRAW_NONE
#property indicator_label5  "WaveletEnergyScore"
#property indicator_type5   DRAW_NONE
#property indicator_label6  "NoiseRatio"
#property indicator_type6   DRAW_NONE
#property indicator_label7  "VolumeAnomalyRatio"
#property indicator_type7   DRAW_NONE
#property indicator_label8  "PivotStructureContext"
#property indicator_type8   DRAW_NONE
#property indicator_label9  "DebugReasonMask"
#property indicator_type9   DRAW_NONE
#property indicator_label10 "ATR"
#property indicator_type10  DRAW_NONE
#property indicator_label11 "SpreadPoints"
#property indicator_type11  DRAW_NONE
#property indicator_label12 "PivotDistanceATR"
#property indicator_type12  DRAW_NONE
#property indicator_label13 "StructureClass"
#property indicator_type13  DRAW_NONE
#property indicator_label14 "ATRRangeQuality"
#property indicator_type14  DRAW_NONE
#property indicator_label15 "RejectionQuality"
#property indicator_type15  DRAW_NONE
#property indicator_label16 "TrendBiasClass"
#property indicator_type16  DRAW_NONE

//--- Core signal inputs
input int      InpWaveletWindow              = 64;     // Wavelet/energy window, bars
input int      InpWaveletLevels              = 4;      // Haar-like wavelet levels
input int      InpATRPeriod                  = 14;     // ATR period
input int      InpVolumeLookback             = 96;     // Tick volume baseline lookback
input int      InpPivotLookback              = 36;     // Prior support/resistance lookback
input int      InpStructureLookback          = 48;     // Prior structure lookback
input double   InpMinSignalScore             = 0.70;   // Minimum score to expose a state signal
input double   InpMinWaveletEnergyScore      = 0.35;   // Minimum normalized wavelet score
input double   InpMaxNoiseRatio              = 0.62;   // Maximum high-frequency/total energy ratio
input double   InpMinVolumeAnomaly           = 1.10;   // Minimum tick volume anomaly ratio
input double   InpVolumeAnomalyCap           = 2.50;   // Volume ratio that maps to full score
input double   InpMaxPivotDistanceATR        = 1.20;   // Pivot distance cap in ATR units
input double   InpRangeATRTarget             = 0.90;   // Candle range/ATR target for full quality
input double   InpMaxRangeATRForPenalty      = 2.80;   // Very large candles are penalized above this
input double   InpMinDirectionMargin         = 0.03;   // Minimum buy/sell score separation
input int      InpMaxSpreadPoints            = 30;     // 0 disables spread filter
input bool     InpUseSessionFilter           = false;  // Restrict to session hours
input int      InpSessionStartHour           = 6;      // Broker/server hour inclusive
input int      InpSessionEndHour             = 20;     // Broker/server hour exclusive
input bool     InpUseTrendBiasFilter         = false;  // Require direction to align with structure class
input bool     InpUseHardFilters             = true;   // Enforce score/noise/spread/etc. gates
input bool     InpRequireVolumeAnomaly       = true;   // Require volume ratio gate
input bool     InpRequireRejectionQuality    = false;  // Require rejection candle gate
input double   InpMinRejectionQuality        = 0.25;   // Rejection quality gate
input bool     InpRequirePivotProximity      = false;  // Require proximity to prior support/resistance
input double   InpMinPivotQuality            = 0.25;   // Pivot quality gate

//--- Scoring weights
input double   InpWeightWavelet              = 1.25;
input double   InpWeightNoise                = 1.00;
input double   InpWeightVolume               = 0.85;
input double   InpWeightRejection            = 1.00;
input double   InpWeightATRRange             = 0.75;
input double   InpWeightPivot                = 0.90;
input double   InpWeightStructure            = 0.75;
input double   InpWeightSpread               = 0.35;
input double   InpWeightSession              = 0.25;
input double   InpWeightTrendBias            = 0.50;
input double   InpArrowOffsetATR             = 0.10;   // Visual arrow offset in ATR units

//--- Indicator buffers
// 0..8 satisfy the requested public buffer map; 9..15 add CSV diagnostics.
double BuySignalBuffer[];
double SellSignalBuffer[];
double DirectionStateBuffer[];
double SignalScoreBuffer[];
double WaveletEnergyBuffer[];
double NoiseRatioBuffer[];
double VolumeAnomalyBuffer[];
double PivotStructureBuffer[];
double DebugReasonBuffer[];
double ATRBuffer[];
double SpreadPointsBuffer[];
double PivotDistanceATRBuffer[];
double StructureClassBuffer[];
double ATRRangeQualityBuffer[];
double RejectionQualityBuffer[];
double TrendBiasClassBuffer[];

//--- Debug reason-code bit mask
#define DBG_SCORE_PASS        1
#define DBG_WAVELET_PASS      2
#define DBG_NOISE_PASS        4
#define DBG_VOLUME_PASS       8
#define DBG_REJECTION_PASS    16
#define DBG_RANGE_PASS        32
#define DBG_PIVOT_PASS        64
#define DBG_STRUCTURE_ALIGN   128
#define DBG_SPREAD_PASS       256
#define DBG_SESSION_PASS      512
#define DBG_TREND_PASS        1024
#define DBG_BUY_CONTEXT       2048
#define DBG_SELL_CONTEXT      4096
#define DBG_DIRECTION_MARGIN  8192
#define DBG_SIGNAL_EXPOSED    16384
#define DBG_BLOCKED           32768

//+------------------------------------------------------------------+
//| Utility helpers                                                  |
//+------------------------------------------------------------------+
double ClampValue(const double value,const double low,const double high)
{
   if(value<low)  return low;
   if(value>high) return high;
   return value;
}

int Pow2Int(const int level)
{
   int result=1;
   for(int i=0;i<level;i++)
      result*=2;
   return result;
}

int MaxBarsNeeded()
{
   int maxScale=Pow2Int((int)ClampValue((double)InpWaveletLevels,1.0,8.0));
   int need=MathMax(InpWaveletWindow,maxScale);
   need=MathMax(need,InpATRPeriod+2);
   need=MathMax(need,InpVolumeLookback+2);
   need=MathMax(need,InpPivotLookback+2);
   need=MathMax(need,InpStructureLookback+2);
   return need+5;
}

void ClearBar(const int i)
{
   BuySignalBuffer[i]=EMPTY_VALUE;
   SellSignalBuffer[i]=EMPTY_VALUE;
   DirectionStateBuffer[i]=0.0;
   SignalScoreBuffer[i]=0.0;
   WaveletEnergyBuffer[i]=0.0;
   NoiseRatioBuffer[i]=0.0;
   VolumeAnomalyBuffer[i]=0.0;
   PivotStructureBuffer[i]=0.0;
   DebugReasonBuffer[i]=0.0;
   ATRBuffer[i]=0.0;
   SpreadPointsBuffer[i]=0.0;
   PivotDistanceATRBuffer[i]=0.0;
   StructureClassBuffer[i]=0.0;
   ATRRangeQualityBuffer[i]=0.0;
   RejectionQualityBuffer[i]=0.0;
   TrendBiasClassBuffer[i]=0.0;
}

double AverageClose(const double &close[],const int start,const int count,const int rates_total)
{
   if(count<=0 || start<0 || start+count>=rates_total+1)
      return 0.0;

   double sum=0.0;
   int used=0;
   for(int k=start;k<start+count && k<rates_total;k++)
   {
      sum+=close[k];
      used++;
   }
   if(used<=0)
      return 0.0;
   return sum/(double)used;
}

double AverageTickVolume(const long &tick_volume[],const int start,const int count,const int rates_total)
{
   if(count<=0 || start<0)
      return 0.0;

   double sum=0.0;
   int used=0;
   for(int k=start;k<start+count && k<rates_total;k++)
   {
      sum+=(double)tick_volume[k];
      used++;
   }
   if(used<=0)
      return 0.0;
   return sum/(double)used;
}

double HighestHigh(const double &high[],const int start,const int count,const int rates_total)
{
   double value=-DBL_MAX;
   for(int k=start;k<start+count && k<rates_total;k++)
      value=MathMax(value,high[k]);
   if(value==-DBL_MAX)
      return 0.0;
   return value;
}

double LowestLow(const double &low[],const int start,const int count,const int rates_total)
{
   double value=DBL_MAX;
   for(int k=start;k<start+count && k<rates_total;k++)
      value=MathMin(value,low[k]);
   if(value==DBL_MAX)
      return 0.0;
   return value;
}

double CalculateATR(const double &high[],const double &low[],const double &close[],const int shift,const int period,const int rates_total)
{
   if(period<=0 || shift+period+1>=rates_total)
      return 0.0;

   double sum=0.0;
   int used=0;
   for(int k=shift;k<shift+period && k+1<rates_total;k++)
   {
      const double tr1=high[k]-low[k];
      const double tr2=MathAbs(high[k]-close[k+1]);
      const double tr3=MathAbs(low[k]-close[k+1]);
      sum+=MathMax(tr1,MathMax(tr2,tr3));
      used++;
   }
   if(used<=0)
      return 0.0;
   return sum/(double)used;
}

bool SessionPasses(const datetime bar_time)
{
   if(!InpUseSessionFilter)
      return true;

   int startHour=(int)ClampValue((double)InpSessionStartHour,0.0,23.0);
   int endHour=(int)ClampValue((double)InpSessionEndHour,0.0,23.0);
   if(startHour==endHour)
      return true;

   MqlDateTime dt;
   TimeToStruct(bar_time,dt);
   if(startHour<endHour)
      return (dt.hour>=startHour && dt.hour<endHour);

   return (dt.hour>=startHour || dt.hour<endHour);
}

int StructureClass(const double &high[],const double &low[],const double &close[],const int shift,const int lookback,const int rates_total)
{
   int lb=MathMax(lookback,8);
   int half=MathMax(lb/2,4);
   if(shift+lb+2>=rates_total)
      return 0;

   const double recentHigh=HighestHigh(high,shift+1,half,rates_total);
   const double recentLow =LowestLow(low,shift+1,half,rates_total);
   const double olderHigh =HighestHigh(high,shift+1+half,half,rates_total);
   const double olderLow  =LowestLow(low,shift+1+half,half,rates_total);

   if(recentHigh<=0.0 || olderHigh<=0.0 || recentLow<=0.0 || olderLow<=0.0)
      return 0;

   if(recentHigh>olderHigh && recentLow>olderLow)
      return 2;       // HH/HL trend context
   if(recentHigh<olderHigh && recentLow<olderLow)
      return -2;      // LH/LL trend context
   if(close[shift]>recentHigh)
      return 1;       // upside breakout of prior recent structure
   if(close[shift]<recentLow)
      return -1;      // downside breakout of prior recent structure
   return 0;
}

double StructureScoreForDirection(const int direction,const int structure_class)
{
   if(structure_class==0)
      return 0.55;
   if(direction*structure_class>0)
      return 1.0;
   return 0.25;
}

double TrendScoreForDirection(const int direction,const int structure_class)
{
   if(structure_class==0)
      return 0.50;
   if(direction*structure_class>0)
      return 1.0;
   return 0.0;
}

bool TrendBiasPasses(const int direction,const int structure_class)
{
   if(!InpUseTrendBiasFilter)
      return true;
   return (direction*structure_class>0);
}

double WeightedScore(const double wavelet_score,
                     const double noise_score,
                     const double volume_score,
                     const double rejection_score,
                     const double range_score,
                     const double pivot_score,
                     const double structure_score,
                     const double spread_score,
                     const double session_score,
                     const double trend_score)
{
   double sum=0.0;
   double weights=0.0;

   sum+=InpWeightWavelet*ClampValue(wavelet_score,0.0,1.0);       weights+=InpWeightWavelet;
   sum+=InpWeightNoise*ClampValue(noise_score,0.0,1.0);           weights+=InpWeightNoise;
   sum+=InpWeightVolume*ClampValue(volume_score,0.0,1.0);         weights+=InpWeightVolume;
   sum+=InpWeightRejection*ClampValue(rejection_score,0.0,1.0);   weights+=InpWeightRejection;
   sum+=InpWeightATRRange*ClampValue(range_score,0.0,1.0);        weights+=InpWeightATRRange;
   sum+=InpWeightPivot*ClampValue(pivot_score,0.0,1.0);           weights+=InpWeightPivot;
   sum+=InpWeightStructure*ClampValue(structure_score,0.0,1.0);   weights+=InpWeightStructure;
   sum+=InpWeightSpread*ClampValue(spread_score,0.0,1.0);         weights+=InpWeightSpread;
   sum+=InpWeightSession*ClampValue(session_score,0.0,1.0);       weights+=InpWeightSession;
   sum+=InpWeightTrendBias*ClampValue(trend_score,0.0,1.0);       weights+=InpWeightTrendBias;

   if(weights<=0.0)
      return 0.0;
   return ClampValue(sum/weights,0.0,1.0);
}

double CalculateWaveletEnergyScore(const double &close[],
                                   const int shift,
                                   const int rates_total,
                                   const double atr,
                                   double &raw_energy,
                                   double &noise_ratio,
                                   double &signed_wavelet)
{
   raw_energy=0.0;
   noise_ratio=1.0;
   signed_wavelet=0.0;

   if(atr<=_Point || shift+InpWaveletWindow+2>=rates_total)
      return 0.0;

   const int maxLevel=(int)ClampValue((double)InpWaveletLevels,1.0,8.0);
   double totalEnergy=0.0;
   double highFreqEnergy=0.0;
   double signedSum=0.0;
   int usedLevels=0;

   for(int level=1;level<=maxLevel;level++)
   {
      int scale=Pow2Int(level);
      if(scale>InpWaveletWindow)
         break;
      if(scale<2)
         continue;
      if(shift+scale+1>=rates_total)
         break;

      const int half=scale/2;
      const double avgNew=AverageClose(close,shift,half,rates_total);
      const double avgOld=AverageClose(close,shift+half,half,rates_total);
      const double detail=(avgNew-avgOld)/atr;
      const double energy=MathAbs(detail)/MathSqrt((double)level);

      totalEnergy+=energy;
      if(level<=2)
         highFreqEnergy+=energy;
      signedSum+=detail/(double)level;
      usedLevels++;
   }

   if(usedLevels<=0)
      return 0.0;

   // A small realized-return contribution helps identify expansion without using future bars.
   double realizedReturnEnergy=0.0;
   int retUsed=0;
   for(int k=shift;k<shift+InpWaveletWindow && k+1<rates_total;k++)
   {
      realizedReturnEnergy+=MathAbs(close[k]-close[k+1])/atr;
      retUsed++;
   }
   if(retUsed>0)
      realizedReturnEnergy/=(double)retUsed;

   raw_energy=(totalEnergy/(double)usedLevels)+(0.30*realizedReturnEnergy);
   if(totalEnergy>0.0)
      noise_ratio=ClampValue(highFreqEnergy/totalEnergy,0.0,1.0);
   signed_wavelet=signedSum/(double)usedLevels;

   const double minEnergy=MathMax(InpMinWaveletEnergyScore,0.0001);
   return ClampValue(raw_energy/minEnergy,0.0,1.0);
}

//+------------------------------------------------------------------+
//| Initialization                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0,BuySignalBuffer,INDICATOR_DATA);
   SetIndexBuffer(1,SellSignalBuffer,INDICATOR_DATA);
   SetIndexBuffer(2,DirectionStateBuffer,INDICATOR_DATA);
   SetIndexBuffer(3,SignalScoreBuffer,INDICATOR_DATA);
   SetIndexBuffer(4,WaveletEnergyBuffer,INDICATOR_DATA);
   SetIndexBuffer(5,NoiseRatioBuffer,INDICATOR_DATA);
   SetIndexBuffer(6,VolumeAnomalyBuffer,INDICATOR_DATA);
   SetIndexBuffer(7,PivotStructureBuffer,INDICATOR_DATA);
   SetIndexBuffer(8,DebugReasonBuffer,INDICATOR_DATA);
   SetIndexBuffer(9,ATRBuffer,INDICATOR_DATA);
   SetIndexBuffer(10,SpreadPointsBuffer,INDICATOR_DATA);
   SetIndexBuffer(11,PivotDistanceATRBuffer,INDICATOR_DATA);
   SetIndexBuffer(12,StructureClassBuffer,INDICATOR_DATA);
   SetIndexBuffer(13,ATRRangeQualityBuffer,INDICATOR_DATA);
   SetIndexBuffer(14,RejectionQualityBuffer,INDICATOR_DATA);
   SetIndexBuffer(15,TrendBiasClassBuffer,INDICATOR_DATA);

   ArraySetAsSeries(BuySignalBuffer,true);
   ArraySetAsSeries(SellSignalBuffer,true);
   ArraySetAsSeries(DirectionStateBuffer,true);
   ArraySetAsSeries(SignalScoreBuffer,true);
   ArraySetAsSeries(WaveletEnergyBuffer,true);
   ArraySetAsSeries(NoiseRatioBuffer,true);
   ArraySetAsSeries(VolumeAnomalyBuffer,true);
   ArraySetAsSeries(PivotStructureBuffer,true);
   ArraySetAsSeries(DebugReasonBuffer,true);
   ArraySetAsSeries(ATRBuffer,true);
   ArraySetAsSeries(SpreadPointsBuffer,true);
   ArraySetAsSeries(PivotDistanceATRBuffer,true);
   ArraySetAsSeries(StructureClassBuffer,true);
   ArraySetAsSeries(ATRRangeQualityBuffer,true);
   ArraySetAsSeries(RejectionQualityBuffer,true);
   ArraySetAsSeries(TrendBiasClassBuffer,true);

   PlotIndexSetInteger(0,PLOT_ARROW,233);
   PlotIndexSetInteger(1,PLOT_ARROW,234);
   PlotIndexSetDouble(0,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   PlotIndexSetDouble(1,PLOT_EMPTY_VALUE,EMPTY_VALUE);

   IndicatorSetInteger(INDICATOR_DIGITS,_Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,"Advanced Wavelet Entry Signal");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Main calculation                                                 |
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
   ArraySetAsSeries(time,true);
   ArraySetAsSeries(open,true);
   ArraySetAsSeries(high,true);
   ArraySetAsSeries(low,true);
   ArraySetAsSeries(close,true);
   ArraySetAsSeries(tick_volume,true);
   ArraySetAsSeries(volume,true);
   ArraySetAsSeries(spread,true);

   const int needed=MaxBarsNeeded();
   if(rates_total<=needed+5)
      return 0;

   if(prev_calculated==0)
   {
      for(int j=0;j<rates_total;j++)
         ClearBar(j);
   }

   int start=0;
   if(prev_calculated==0)
      start=rates_total-needed-2;
   else
      start=rates_total-prev_calculated+3;

   start=MathMin(start,rates_total-needed-2);
   if(start<1)
      start=1;

   // Current forming bar is deliberately blank to enforce closed-bar-only usage.
   ClearBar(0);

   for(int i=start;i>=1;i--)
   {
      ClearBar(i);
      if(i+needed+1>=rates_total)
         continue;

      const double atr=CalculateATR(high,low,close,i,MathMax(InpATRPeriod,2),rates_total);
      if(atr<=_Point)
         continue;

      int spreadPoints=spread[i];
      if(spreadPoints<0)
         spreadPoints=0;
      const bool spreadKnown=(spreadPoints>0);
      const bool spreadPass=(InpMaxSpreadPoints<=0 || !spreadKnown || spreadPoints<=InpMaxSpreadPoints);
      const bool sessionPass=SessionPasses(time[i]);

      double rawEnergy=0.0;
      double noiseRatio=1.0;
      double signedWavelet=0.0;
      const double waveletEnergyScore=CalculateWaveletEnergyScore(close,i,rates_total,atr,rawEnergy,noiseRatio,signedWavelet);
      const double noiseScore=(InpMaxNoiseRatio>0.0 ? ClampValue((InpMaxNoiseRatio-noiseRatio)/InpMaxNoiseRatio,0.0,1.0) : 0.0);

      const double avgVol=AverageTickVolume(tick_volume,i+1,MathMax(InpVolumeLookback,2),rates_total);
      const double volRatio=(avgVol>0.0 ? ((double)tick_volume[i]/avgVol) : 1.0);
      const double volCap=MathMax(InpVolumeAnomalyCap,1.01);
      const double volumeScore=ClampValue((volRatio-1.0)/(volCap-1.0),0.0,1.0);

      const double range=MathMax(high[i]-low[i],_Point);
      const double body=MathAbs(close[i]-open[i]);
      const double lowerWick=MathMax(MathMin(open[i],close[i])-low[i],0.0);
      const double upperWick=MathMax(high[i]-MathMax(open[i],close[i]),0.0);
      const double closePosition=ClampValue((close[i]-low[i])/range,0.0,1.0);
      const double rejectionBuy=ClampValue(0.55*(lowerWick/range)+0.45*closePosition,0.0,1.0);
      const double rejectionSell=ClampValue(0.55*(upperWick/range)+0.45*(1.0-closePosition),0.0,1.0);

      const double rangeATR=range/atr;
      double rangeQuality=ClampValue(rangeATR/MathMax(InpRangeATRTarget,0.05),0.0,1.0);
      if(rangeATR>InpMaxRangeATRForPenalty && InpMaxRangeATRForPenalty>0.0)
      {
         const double penalty=ClampValue(1.0-((rangeATR-InpMaxRangeATRForPenalty)/InpMaxRangeATRForPenalty),0.20,1.0);
         rangeQuality*=penalty;
      }

      const double support=LowestLow(low,i+1,MathMax(InpPivotLookback,2),rates_total);
      const double resistance=HighestHigh(high,i+1,MathMax(InpPivotLookback,2),rates_total);
      const double pivotDistBuyATR=(support>0.0 ? MathAbs(low[i]-support)/atr : 999.0);
      const double pivotDistSellATR=(resistance>0.0 ? MathAbs(high[i]-resistance)/atr : 999.0);
      const double maxPivotDist=MathMax(InpMaxPivotDistanceATR,0.05);
      const double pivotScoreBuy=ClampValue(1.0-(pivotDistBuyATR/maxPivotDist),0.0,1.0);
      const double pivotScoreSell=ClampValue(1.0-(pivotDistSellATR/maxPivotDist),0.0,1.0);

      const int structureClass=StructureClass(high,low,close,i,MathMax(InpStructureLookback,8),rates_total);
      const double structureBuy=StructureScoreForDirection(1,structureClass);
      const double structureSell=StructureScoreForDirection(-1,structureClass);
      const double trendBuy=TrendScoreForDirection(1,structureClass);
      const double trendSell=TrendScoreForDirection(-1,structureClass);

      const double impulseBuy=ClampValue((close[i]-open[i])/(atr*0.50),0.0,1.0);
      const double impulseSell=ClampValue((open[i]-close[i])/(atr*0.50),0.0,1.0);
      const double directionalWaveletBuy=waveletEnergyScore*(signedWavelet>=0.0 ? 1.0 : 0.25);
      const double directionalWaveletSell=waveletEnergyScore*(signedWavelet<=0.0 ? 1.0 : 0.25);
      const double directionalRejectionBuy=ClampValue(MathMax(rejectionBuy,0.55*impulseBuy),0.0,1.0);
      const double directionalRejectionSell=ClampValue(MathMax(rejectionSell,0.55*impulseSell),0.0,1.0);
      const double spreadScore=(spreadPass ? 1.0 : 0.0);
      const double sessionScore=(sessionPass ? 1.0 : 0.0);

      const double scoreBuy=WeightedScore(directionalWaveletBuy,noiseScore,volumeScore,directionalRejectionBuy,
                                          rangeQuality,pivotScoreBuy,structureBuy,spreadScore,sessionScore,trendBuy);
      const double scoreSell=WeightedScore(directionalWaveletSell,noiseScore,volumeScore,directionalRejectionSell,
                                           rangeQuality,pivotScoreSell,structureSell,spreadScore,sessionScore,trendSell);

      int direction=(scoreBuy>=scoreSell ? 1 : -1);
      double signalScore=(direction>0 ? scoreBuy : scoreSell);
      const double directionMargin=MathAbs(scoreBuy-scoreSell);
      const double chosenPivotScore=(direction>0 ? pivotScoreBuy : pivotScoreSell);
      const double chosenPivotDistanceATR=(direction>0 ? pivotDistBuyATR : pivotDistSellATR);
      const double chosenRejection=(direction>0 ? directionalRejectionBuy : directionalRejectionSell);
      const double chosenTrendScore=(direction>0 ? trendBuy : trendSell);
      const bool trendPass=TrendBiasPasses(direction,structureClass);

      int debug=0;
      if(signalScore>=InpMinSignalScore)                     debug|=DBG_SCORE_PASS;
      if(waveletEnergyScore>=InpMinWaveletEnergyScore)       debug|=DBG_WAVELET_PASS;
      if(noiseRatio<=InpMaxNoiseRatio)                       debug|=DBG_NOISE_PASS;
      if(volRatio>=InpMinVolumeAnomaly)                      debug|=DBG_VOLUME_PASS;
      if(chosenRejection>=InpMinRejectionQuality)            debug|=DBG_REJECTION_PASS;
      if(rangeQuality>=0.50)                                 debug|=DBG_RANGE_PASS;
      if(chosenPivotScore>=InpMinPivotQuality)               debug|=DBG_PIVOT_PASS;
      if(direction*structureClass>0)                         debug|=DBG_STRUCTURE_ALIGN;
      if(spreadPass)                                         debug|=DBG_SPREAD_PASS;
      if(sessionPass)                                        debug|=DBG_SESSION_PASS;
      if(chosenTrendScore>0.0 || !InpUseTrendBiasFilter)      debug|=DBG_TREND_PASS;
      if(direction>0)                                        debug|=DBG_BUY_CONTEXT; else debug|=DBG_SELL_CONTEXT;
      if(directionMargin>=InpMinDirectionMargin)             debug|=DBG_DIRECTION_MARGIN;

      bool hardPass=true;
      if(signalScore<InpMinSignalScore)                      hardPass=false;
      if(waveletEnergyScore<InpMinWaveletEnergyScore)        hardPass=false;
      if(noiseRatio>InpMaxNoiseRatio)                        hardPass=false;
      if(InpRequireVolumeAnomaly && volRatio<InpMinVolumeAnomaly) hardPass=false;
      if(InpRequireRejectionQuality && chosenRejection<InpMinRejectionQuality) hardPass=false;
      if(InpRequirePivotProximity && chosenPivotScore<InpMinPivotQuality) hardPass=false;
      if(directionMargin<InpMinDirectionMargin)              hardPass=false;
      if(!spreadPass || !sessionPass || !trendPass)           hardPass=false;

      if(!InpUseHardFilters)
         hardPass=(signalScore>=InpMinSignalScore && spreadPass && sessionPass && directionMargin>=InpMinDirectionMargin);

      if(hardPass)
         debug|=DBG_SIGNAL_EXPOSED;
      else
         debug|=DBG_BLOCKED;

      DirectionStateBuffer[i]=(hardPass ? (double)direction : 0.0);
      SignalScoreBuffer[i]=signalScore;
      WaveletEnergyBuffer[i]=waveletEnergyScore;
      NoiseRatioBuffer[i]=noiseRatio;
      VolumeAnomalyBuffer[i]=volRatio;
      PivotStructureBuffer[i]=(double)direction*chosenPivotScore;
      DebugReasonBuffer[i]=(double)debug;
      ATRBuffer[i]=atr;
      SpreadPointsBuffer[i]=(double)spreadPoints;
      PivotDistanceATRBuffer[i]=chosenPivotDistanceATR;
      StructureClassBuffer[i]=(double)structureClass;
      ATRRangeQualityBuffer[i]=rangeQuality;
      RejectionQualityBuffer[i]=chosenRejection;
      TrendBiasClassBuffer[i]=(double)(structureClass>0 ? 1 : (structureClass<0 ? -1 : 0));

      if(hardPass)
      {
         const double offset=atr*MathMax(InpArrowOffsetATR,0.0);
         if(direction>0)
            BuySignalBuffer[i]=low[i]-offset;
         else
            SellSignalBuffer[i]=high[i]+offset;
      }
   }

   return rates_total;
}
//+------------------------------------------------------------------+
