//+------------------------------------------------------------------+
//| Advanced_OrderFlow_Proxy_Confluence.mq5                          |
//| Closed-bar order-flow proxy diagnostics for Advanced Wavelet.     |
//| Research prototype. Proxy only; not true footprint volume.        |
//+------------------------------------------------------------------+
#property strict
#property copyright "Research prototype"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 9
#property indicator_plots   9

#property indicator_label1  "OFProxyDelta"
#property indicator_type1   DRAW_NONE
#property indicator_label2  "OFProxyDivergence"
#property indicator_type2   DRAW_NONE
#property indicator_label3  "OFProxyAggression"
#property indicator_type3   DRAW_NONE
#property indicator_label4  "OFProxyStackedPressure"
#property indicator_type4   DRAW_NONE
#property indicator_label5  "OFProxyAbsorption"
#property indicator_type5   DRAW_NONE
#property indicator_label6  "OFProxyConfluenceScore"
#property indicator_type6   DRAW_NONE
#property indicator_label7  "OFProxyRawState"
#property indicator_type7   DRAW_NONE
#property indicator_label8  "OFProxyReasonCode"
#property indicator_type8   DRAW_NONE
#property indicator_label9  "OFProxyDataMode"
#property indicator_type9   DRAW_NONE

//--- Bar-only proxy inputs. Tick enrichment is deliberately not in v1.
input int      InpOFATRPeriod                 = 14;     // ATR period for normalization
input int      InpOFDeltaLookback             = 48;     // Tick-volume baseline lookback
input int      InpOFDivergenceLookback        = 24;     // Rolling divergence lookback
input int      InpOFStructureLookback         = 36;     // Support/resistance context lookback
input double   InpOFVolumeRatioCap            = 2.50;   // Volume ratio that maps to full pressure
input double   InpOFDivergenceMinDeltaGap     = 0.10;   // Minimum proxy delta gap for divergence
input double   InpOFAggressionMinDelta        = 0.20;   // Minimum delta proxy for aggression
input double   InpOFAggressionMinVolumeRatio  = 1.15;   // Minimum tick volume ratio for aggression
input int      InpOFStackedMinBars            = 3;      // Bars required for full stack score
input int      InpOFStackedWindowBars         = 5;      // Recent closed bars in stack scan
input double   InpOFAbsorptionMinEffort       = 0.65;   // Effort threshold for absorption proxy
input double   InpOFAbsorptionMaxProgressATR  = 0.25;   // Max body/ATR for poor progress
input double   InpOFAbsorptionMinWickRatio    = 0.35;   // Wick ratio threshold for rejection
input double   InpOFStructureDistanceATR      = 1.20;   // Structure proximity cap in ATR
input double   InpOFNeutralThreshold          = 0.10;   // Raw state neutral band
input double   InpOFMixedThreshold            = 0.15;   // Buy/sell score gap for mixed state

//--- Indicator buffers
double OFProxyDeltaBuffer[];
double OFProxyDivergenceBuffer[];
double OFProxyAggressionBuffer[];
double OFProxyStackedPressureBuffer[];
double OFProxyAbsorptionBuffer[];
double OFProxyConfluenceScoreBuffer[];
double OFProxyRawStateBuffer[];
double OFProxyReasonCodeBuffer[];
double OFProxyDataModeBuffer[];

//--- Reason-code bit mask
#define OF_DATA_AVAILABLE          1
#define OF_BAR_PROXY_MODE          2
#define OF_DELTA_BUY               16
#define OF_DELTA_SELL              32
#define OF_PRICE_DELTA_AGREE       64
#define OF_BULLISH_DIVERGENCE      128
#define OF_BEARISH_DIVERGENCE      256
#define OF_BUY_AGGRESSION          512
#define OF_SELL_AGGRESSION         1024
#define OF_BUY_STACK               2048
#define OF_SELL_STACK              4096
#define OF_SELLING_ABSORBED        8192
#define OF_BUYING_ABSORBED         16384
#define OF_STRUCTURE_PRESENT       32768

//+------------------------------------------------------------------+
//| Utility helpers                                                  |
//+------------------------------------------------------------------+
double ClampValue(const double value,const double low,const double high)
{
   if(value<low)  return low;
   if(value>high) return high;
   return value;
}

int SignValue(const double value,const double threshold)
{
   if(value>threshold)
      return 1;
   if(value<-threshold)
      return -1;
   return 0;
}

int MaxBarsNeeded()
{
   int need=MathMax(InpOFATRPeriod+2,InpOFDeltaLookback+2);
   need=MathMax(need,InpOFDivergenceLookback+2);
   need=MathMax(need,InpOFStructureLookback+2);
   need=MathMax(need,InpOFStackedWindowBars+2);
   return need+5;
}

void ClearBar(const int i)
{
   OFProxyDeltaBuffer[i]=0.0;
   OFProxyDivergenceBuffer[i]=0.0;
   OFProxyAggressionBuffer[i]=0.0;
   OFProxyStackedPressureBuffer[i]=0.0;
   OFProxyAbsorptionBuffer[i]=0.0;
   OFProxyConfluenceScoreBuffer[i]=0.0;
   OFProxyRawStateBuffer[i]=0.0;
   OFProxyReasonCodeBuffer[i]=0.0;
   OFProxyDataModeBuffer[i]=0.0;
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

double HighestBuffer(const double &buffer[],const int start,const int count,const int rates_total)
{
   double value=-DBL_MAX;
   for(int k=start;k<start+count && k<rates_total;k++)
      value=MathMax(value,buffer[k]);
   if(value==-DBL_MAX)
      return 0.0;
   return value;
}

double LowestBuffer(const double &buffer[],const int start,const int count,const int rates_total)
{
   double value=DBL_MAX;
   for(int k=start;k<start+count && k<rates_total;k++)
      value=MathMin(value,buffer[k]);
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

double NormalizeSignedScore(const double buy_score,const double sell_score)
{
   const double buy=ClampValue(buy_score,0.0,1.0);
   const double sell=ClampValue(sell_score,0.0,1.0);
   return ClampValue(buy-sell,-1.0,1.0);
}

//+------------------------------------------------------------------+
//| Initialization                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0,OFProxyDeltaBuffer,INDICATOR_DATA);
   SetIndexBuffer(1,OFProxyDivergenceBuffer,INDICATOR_DATA);
   SetIndexBuffer(2,OFProxyAggressionBuffer,INDICATOR_DATA);
   SetIndexBuffer(3,OFProxyStackedPressureBuffer,INDICATOR_DATA);
   SetIndexBuffer(4,OFProxyAbsorptionBuffer,INDICATOR_DATA);
   SetIndexBuffer(5,OFProxyConfluenceScoreBuffer,INDICATOR_DATA);
   SetIndexBuffer(6,OFProxyRawStateBuffer,INDICATOR_DATA);
   SetIndexBuffer(7,OFProxyReasonCodeBuffer,INDICATOR_DATA);
   SetIndexBuffer(8,OFProxyDataModeBuffer,INDICATOR_DATA);

   ArraySetAsSeries(OFProxyDeltaBuffer,true);
   ArraySetAsSeries(OFProxyDivergenceBuffer,true);
   ArraySetAsSeries(OFProxyAggressionBuffer,true);
   ArraySetAsSeries(OFProxyStackedPressureBuffer,true);
   ArraySetAsSeries(OFProxyAbsorptionBuffer,true);
   ArraySetAsSeries(OFProxyConfluenceScoreBuffer,true);
   ArraySetAsSeries(OFProxyRawStateBuffer,true);
   ArraySetAsSeries(OFProxyReasonCodeBuffer,true);
   ArraySetAsSeries(OFProxyDataModeBuffer,true);

   IndicatorSetInteger(INDICATOR_DIGITS,4);
   IndicatorSetString(INDICATOR_SHORTNAME,"Advanced OF Proxy Confluence");
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

   // Current forming bar is deliberately neutral to preserve closed-bar usage.
   ClearBar(0);

   const int atrPeriod=MathMax(InpOFATRPeriod,2);
   const int deltaLookback=MathMax(InpOFDeltaLookback,2);
   const int divLookback=MathMax(InpOFDivergenceLookback,3);
   const int structureLookback=MathMax(InpOFStructureLookback,3);
   const int stackedWindow=MathMax(InpOFStackedWindowBars,1);
   const int stackedMin=MathMax(InpOFStackedMinBars,1);
   const double volumeCap=MathMax(InpOFVolumeRatioCap,1.01);
   const double minDelta=ClampValue(InpOFAggressionMinDelta,0.01,0.95);
   const double minVolumeRatio=MathMax(InpOFAggressionMinVolumeRatio,1.0);
   const double structureDistanceATR=MathMax(InpOFStructureDistanceATR,0.05);

   for(int i=start;i>=1;i--)
   {
      ClearBar(i);
      if(i+needed+1>=rates_total)
         continue;

      const double atr=CalculateATR(high,low,close,i,atrPeriod,rates_total);
      if(atr<=_Point)
      {
         OFProxyRawStateBuffer[i]=-2.0;
         OFProxyDataModeBuffer[i]=-1.0;
         continue;
      }

      const double range=MathMax(high[i]-low[i],_Point);
      const double body=close[i]-open[i];
      const double absBody=MathAbs(body);
      const double upperWick=MathMax(high[i]-MathMax(open[i],close[i]),0.0);
      const double lowerWick=MathMax(MathMin(open[i],close[i])-low[i],0.0);
      const double closeLocation=ClampValue((close[i]-low[i])/range,0.0,1.0);
      const double closeLocationSigned=ClampValue((2.0*closeLocation)-1.0,-1.0,1.0);
      const double bodyEfficiency=ClampValue(body/range,-1.0,1.0);
      const double avgVolume=AverageTickVolume(tick_volume,i+1,deltaLookback,rates_total);
      const double volumeRatio=(avgVolume>0.0 ? (double)tick_volume[i]/avgVolume : 1.0);
      const double normalizedVolume=ClampValue(volumeRatio/volumeCap,0.0,1.0);
      const double volumeSurprise=ClampValue((volumeRatio-minVolumeRatio)/MathMax(volumeCap-minVolumeRatio,0.01),0.0,1.0);

      const double rawDelta=ClampValue((0.60*bodyEfficiency)+(0.40*closeLocationSigned),-1.0,1.0);
      const double ofDelta=ClampValue(rawDelta*normalizedVolume,-1.0,1.0);

      const double priorHigh=HighestHigh(high,i+1,divLookback,rates_total);
      const double priorLow=LowestLow(low,i+1,divLookback,rates_total);
      const double priorDeltaHigh=HighestBuffer(OFProxyDeltaBuffer,i+1,divLookback,rates_total);
      const double priorDeltaLow=LowestBuffer(OFProxyDeltaBuffer,i+1,divLookback,rates_total);
      const double minDeltaGap=MathMax(InpOFDivergenceMinDeltaGap,0.01);

      double divergence=0.0;
      if(priorHigh>0.0 && high[i]>priorHigh && ofDelta<priorDeltaHigh-minDeltaGap)
      {
         const double priceStrength=ClampValue((high[i]-priorHigh)/(atr*0.50),0.0,1.0);
         const double deltaStrength=ClampValue((priorDeltaHigh-ofDelta)/MathMax(1.0-minDeltaGap,0.01),0.0,1.0);
         divergence=-(0.50*priceStrength+0.50*deltaStrength);
      }
      else if(priorLow>0.0 && low[i]<priorLow && ofDelta>priorDeltaLow+minDeltaGap)
      {
         const double priceStrength=ClampValue((priorLow-low[i])/(atr*0.50),0.0,1.0);
         const double deltaStrength=ClampValue((ofDelta-priorDeltaLow)/MathMax(1.0-minDeltaGap,0.01),0.0,1.0);
         divergence=0.50*priceStrength+0.50*deltaStrength;
      }

      const double rangeATR=range/atr;
      double rangeQuality=ClampValue(rangeATR/0.90,0.0,1.0);
      if(rangeATR>2.80)
         rangeQuality*=ClampValue(1.0-((rangeATR-2.80)/2.80),0.20,1.0);

      const double buyDeltaStrength=ClampValue((ofDelta-minDelta)/(1.0-minDelta),0.0,1.0);
      const double sellDeltaStrength=ClampValue((-ofDelta-minDelta)/(1.0-minDelta),0.0,1.0);
      const double buyAggression=buyDeltaStrength*volumeSurprise*closeLocation*rangeQuality;
      const double sellAggression=sellDeltaStrength*volumeSurprise*(1.0-closeLocation)*rangeQuality;
      const double aggression=NormalizeSignedScore(buyAggression,sellAggression);

      const double support=LowestLow(low,i+1,structureLookback,rates_total);
      const double resistance=HighestHigh(high,i+1,structureLookback,rates_total);
      const double supportDistanceATR=(support>0.0 ? MathAbs(low[i]-support)/atr : 999.0);
      const double resistanceDistanceATR=(resistance>0.0 ? MathAbs(high[i]-resistance)/atr : 999.0);
      const double supportScore=ClampValue(1.0-(supportDistanceATR/structureDistanceATR),0.0,1.0);
      const double resistanceScore=ClampValue(1.0-(resistanceDistanceATR/structureDistanceATR),0.0,1.0);
      const bool structurePresent=(supportScore>0.0 || resistanceScore>0.0);

      int buyStackCount=0;
      int sellStackCount=0;
      double buyStackSum=0.0;
      double sellStackSum=0.0;
      for(int k=0;k<stackedWindow && i+k<rates_total;k++)
      {
         double value=(k==0 ? aggression : OFProxyAggressionBuffer[i+k]);
         if(value>=minDelta)
         {
            buyStackCount++;
            buyStackSum+=MathAbs(value);
         }
         if(value<=-minDelta)
         {
            sellStackCount++;
            sellStackSum+=MathAbs(value);
         }
      }
      const double buyStackAvg=(buyStackCount>0 ? buyStackSum/(double)buyStackCount : 0.0);
      const double sellStackAvg=(sellStackCount>0 ? sellStackSum/(double)sellStackCount : 0.0);
      const double buyStack=ClampValue((double)buyStackCount/(double)stackedMin,0.0,1.0)*buyStackAvg*supportScore;
      const double sellStack=ClampValue((double)sellStackCount/(double)stackedMin,0.0,1.0)*sellStackAvg*resistanceScore;
      const double stackedPressure=NormalizeSignedScore(buyStack,sellStack);

      const double effort=volumeSurprise*MathAbs(ofDelta);
      const double progressATR=absBody/atr;
      const double progressScore=ClampValue(1.0-(progressATR/MathMax(InpOFAbsorptionMaxProgressATR,0.01)),0.0,1.0);
      const double upperWickRatio=upperWick/range;
      const double lowerWickRatio=lowerWick/range;

      double buyAbsorbed=0.0;
      double sellAbsorbed=0.0;
      if(ofDelta>minDelta && effort>=InpOFAbsorptionMinEffort && progressScore>0.0 &&
         (upperWickRatio>=InpOFAbsorptionMinWickRatio || closeLocation<0.55))
      {
         const double wickScore=ClampValue(MathMax(upperWickRatio,1.0-closeLocation),0.0,1.0);
         buyAbsorbed=ClampValue(effort*progressScore*wickScore*resistanceScore,0.0,1.0);
      }
      if(ofDelta<-minDelta && effort>=InpOFAbsorptionMinEffort && progressScore>0.0 &&
         (lowerWickRatio>=InpOFAbsorptionMinWickRatio || closeLocation>0.45))
      {
         const double wickScore=ClampValue(MathMax(lowerWickRatio,closeLocation),0.0,1.0);
         sellAbsorbed=ClampValue(effort*progressScore*wickScore*supportScore,0.0,1.0);
      }
      const double absorption=NormalizeSignedScore(sellAbsorbed,buyAbsorbed);

      const double buyScore=ClampValue(MathMax(ofDelta,0.0)+MathMax(divergence,0.0)+
                                      MathMax(aggression,0.0)+MathMax(stackedPressure,0.0)+
                                      MathMax(absorption,0.0),0.0,5.0)/5.0;
      const double sellScore=ClampValue(MathMax(-ofDelta,0.0)+MathMax(-divergence,0.0)+
                                       MathMax(-aggression,0.0)+MathMax(-stackedPressure,0.0)+
                                       MathMax(-absorption,0.0),0.0,5.0)/5.0;
      const double confluence=NormalizeSignedScore(buyScore,sellScore);

      int rawState=0;
      const double neutralBand=MathMax(InpOFNeutralThreshold,0.0);
      if(buyScore>0.35 && sellScore>0.35 && MathAbs(buyScore-sellScore)<=MathMax(InpOFMixedThreshold,0.0))
         rawState=2;
      else if(confluence>neutralBand)
         rawState=1;
      else if(confluence<-neutralBand)
         rawState=-1;

      int reason=OF_DATA_AVAILABLE|OF_BAR_PROXY_MODE;
      if(ofDelta>minDelta)       reason|=OF_DELTA_BUY;
      if(ofDelta<-minDelta)      reason|=OF_DELTA_SELL;
      if(SignValue(body,0.0)==SignValue(ofDelta,minDelta)) reason|=OF_PRICE_DELTA_AGREE;
      if(divergence>0.0)         reason|=OF_BULLISH_DIVERGENCE;
      if(divergence<0.0)         reason|=OF_BEARISH_DIVERGENCE;
      if(aggression>0.0)         reason|=OF_BUY_AGGRESSION;
      if(aggression<0.0)         reason|=OF_SELL_AGGRESSION;
      if(stackedPressure>0.0)    reason|=OF_BUY_STACK;
      if(stackedPressure<0.0)    reason|=OF_SELL_STACK;
      if(absorption>0.0)         reason|=OF_SELLING_ABSORBED;
      if(absorption<0.0)         reason|=OF_BUYING_ABSORBED;
      if(structurePresent)       reason|=OF_STRUCTURE_PRESENT;

      OFProxyDeltaBuffer[i]=ofDelta;
      OFProxyDivergenceBuffer[i]=divergence;
      OFProxyAggressionBuffer[i]=aggression;
      OFProxyStackedPressureBuffer[i]=stackedPressure;
      OFProxyAbsorptionBuffer[i]=absorption;
      OFProxyConfluenceScoreBuffer[i]=confluence;
      OFProxyRawStateBuffer[i]=(double)rawState;
      OFProxyReasonCodeBuffer[i]=(double)reason;
      OFProxyDataModeBuffer[i]=1.0;
   }

   return rates_total;
}
//+------------------------------------------------------------------+
