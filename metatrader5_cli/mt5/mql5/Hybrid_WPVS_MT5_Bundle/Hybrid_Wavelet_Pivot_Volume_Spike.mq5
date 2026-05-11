//+------------------------------------------------------------------+
//| Hybrid_Wavelet_Pivot_Volume_Spike.mq5                            |
//| Closed-bar hybrid volume spike pivot + lightweight regime filter  |
//| Non-trading indicator. Designed for diagnostic EA consumption.    |
//+------------------------------------------------------------------+
#property copyright "OpenAI / user-specified project"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 8
#property indicator_plots   8

//--- Plot 0: buy arrow
#property indicator_label1  "BuySignal"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_width1  2
//--- Plot 1: sell arrow
#property indicator_label2  "SellSignal"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrTomato
#property indicator_width2  2
//--- Hidden diagnostic plots/buffers
#property indicator_label3  "SignalState"
#property indicator_type3   DRAW_NONE
#property indicator_label4  "SignalScore"
#property indicator_type4   DRAW_NONE
#property indicator_label5  "VolumeRatio"
#property indicator_type5   DRAW_NONE
#property indicator_label6  "WaveletRegime"
#property indicator_type6   DRAW_NONE
#property indicator_label7  "StructureClass"
#property indicator_type7   DRAW_NONE
#property indicator_label8  "DebugReasonCode"
#property indicator_type8   DRAW_NONE

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
enum ENUM_WPVS_SIGNAL_BAR
  {
   WPVS_CURRENT_BAR_VISUAL_ONLY = 0,   // Current bar visual mode; can flicker/repaint
   WPVS_CLOSED_BAR_ONLY         = 1    // Closed-bar signals only
  };

input ENUM_WPVS_SIGNAL_BAR InpSignalBar            = WPVS_CLOSED_BAR_ONLY;
input int                  InpVolumeLookback       = 20;
input double               InpVolumeMultiplier     = 1.80;
input long                 InpMinBarVolume         = 50;
input int                  InpPivotLookback        = 8;
input int                  InpPivotTolerancePoints = 5;
input double               InpMinWickToRange       = 0.35;
input double               InpClosePosition        = 0.55;
input bool                 InpRequireCandleColor   = true;
input bool                 InpUseATRRangeFilter    = true;
input int                  InpATRPeriod            = 14;
input double               InpMinRangeATR          = 0.35;
input int                  InpWaveletWindow        = 48;
input int                  InpWaveletLevel         = 3;
input double               InpMinWaveletEnergy     = 0.10;
input double               InpMaxNoiseRatio        = 0.78;
input bool                 InpUseTrendBias         = false;
input int                  InpTrendLookback        = 32;
input int                  InpMaxSpreadPoints      = 0;
input bool                 InpUseSessionFilter     = false;
input int                  InpSessionStartHour     = 7;
input int                  InpSessionEndHour       = 18;
input int                  InpMaxBarsToProcess     = 500000;
input bool                 InpEnableAlerts         = false;

//--- Additional conservative controls
input double               InpMinSignalScore       = 0.55;
input bool                 InpEnableStructureClass = true;
input bool                 InpAllowBuyHL           = true;
input bool                 InpAllowBuyLL           = false;
input bool                 InpAllowSellHH          = true;
input bool                 InpAllowSellLH          = false;
input int                  InpStructureLookback    = 80;
input int                  InpArrowOffsetPoints    = 10;

//+------------------------------------------------------------------+
//| Indicator buffers                                                 |
//+------------------------------------------------------------------+
double BuySignalBuffer[];        // Buffer 0: plotted buy arrow price or EMPTY_VALUE
double SellSignalBuffer[];       // Buffer 1: plotted sell arrow price or EMPTY_VALUE
double SignalStateBuffer[];      // Buffer 2: +1 buy, -1 sell, 0 none
double SignalScoreBuffer[];      // Buffer 3: normalized 0.0..1.0 for accepted signals
double VolumeRatioBuffer[];      // Buffer 4: bar tick volume / prior lookback average
double WaveletRegimeBuffer[];    // Buffer 5: -1 bearish clean, 0 neutral/noisy, +1 bullish clean
double StructureClassBuffer[];   // Buffer 6: HH=0, HL=1, LH=2, LL=3, EMPTY_VALUE unknown
double DebugReasonBuffer[];      // Buffer 7: bitmask reason code for accepted signals

//--- Alert de-duplication
datetime g_last_alert_time = 0;

//--- Debug reason bits for Buffer 7
#define REASON_VOLUME_PASS       1
#define REASON_PIVOT_PASS        2
#define REASON_REJECTION_PASS    4
#define REASON_ATR_PASS          8
#define REASON_WAVELET_PASS      16
#define REASON_BUY               32
#define REASON_SELL              64
#define REASON_SESSION_PASS      128
#define REASON_SPREAD_PASS       256
#define REASON_TREND_PASS        512

//+------------------------------------------------------------------+
//| Utility functions                                                 |
//+------------------------------------------------------------------+
double ClampDouble(const double value,const double min_value,const double max_value)
  {
   if(value < min_value)
      return min_value;
   if(value > max_value)
      return max_value;
   return value;
  }

int MaxInt(const int a,const int b)
  {
   return (a > b ? a : b);
  }

int MinInt(const int a,const int b)
  {
   return (a < b ? a : b);
  }

int RequiredDepth()
  {
   int depth = 0;
   depth = MaxInt(depth, InpVolumeLookback + 1);
   depth = MaxInt(depth, InpPivotLookback + 1);
   depth = MaxInt(depth, InpATRPeriod + 2);
   depth = MaxInt(depth, InpWaveletWindow + 2);
   depth = MaxInt(depth, InpTrendLookback + 2);
   depth = MaxInt(depth, InpStructureLookback + InpPivotLookback + 2);
   return depth;
  }

void ClearBar(const int i)
  {
   BuySignalBuffer[i]      = EMPTY_VALUE;
   SellSignalBuffer[i]     = EMPTY_VALUE;
   SignalStateBuffer[i]    = 0.0;
   SignalScoreBuffer[i]    = 0.0;
   VolumeRatioBuffer[i]    = 0.0;
   WaveletRegimeBuffer[i]  = 0.0;
   StructureClassBuffer[i] = EMPTY_VALUE;
   DebugReasonBuffer[i]    = 0.0;
  }

void InitializeBuffers()
  {
   ArrayInitialize(BuySignalBuffer,      EMPTY_VALUE);
   ArrayInitialize(SellSignalBuffer,     EMPTY_VALUE);
   ArrayInitialize(SignalStateBuffer,    0.0);
   ArrayInitialize(SignalScoreBuffer,    0.0);
   ArrayInitialize(VolumeRatioBuffer,    0.0);
   ArrayInitialize(WaveletRegimeBuffer,  0.0);
   ArrayInitialize(StructureClassBuffer, EMPTY_VALUE);
   ArrayInitialize(DebugReasonBuffer,    0.0);
  }

bool HasEnoughData(const int i,const int rates_total)
  {
   return (i + RequiredDepth() < rates_total);
  }

bool PassSession(const datetime bar_time)
  {
   if(!InpUseSessionFilter)
      return true;

   MqlDateTime dt;
   TimeToStruct(bar_time, dt);

   int start_hour = (int)ClampDouble((double)InpSessionStartHour,0.0,23.0);
   int end_hour   = (int)ClampDouble((double)InpSessionEndHour,0.0,23.0);

   if(start_hour == end_hour)
      return true; // Treat equal start/end as all-day session.

   if(start_hour < end_hour)
      return (dt.hour >= start_hour && dt.hour < end_hour);

   // Cross-midnight session, for example 22 -> 6.
   return (dt.hour >= start_hour || dt.hour < end_hour);
  }

bool PassSpread(const int spread_points)
  {
   if(InpMaxSpreadPoints <= 0)
      return true;
   if(spread_points < 0)
      return false;
   return (spread_points <= InpMaxSpreadPoints);
  }

double AverageTickVolume(const int i,const int lookback,const long &tick_volume[],const int rates_total)
  {
   if(lookback <= 0 || i + lookback > rates_total)
      return 0.0;

   double sum = 0.0;
   int count = 0;
   for(int k = i; k < i + lookback && k < rates_total; k++)
     {
      sum += (double)tick_volume[k];
      count++;
     }

   if(count <= 0)
      return 0.0;
   return sum / (double)count;
  }

double TrueRangeAt(const int i,const double &high[],const double &low[],const double &close[],const int rates_total)
  {
   if(i + 1 >= rates_total)
      return 0.0;

   double range1 = high[i] - low[i];
   double range2 = MathAbs(high[i] - close[i + 1]);
   double range3 = MathAbs(low[i]  - close[i + 1]);
   return MathMax(range1, MathMax(range2, range3));
  }

double AverageTrueRangePastOnly(const int i,const int period,const double &high[],const double &low[],const double &close[],const int rates_total)
  {
   if(period <= 0 || i + period + 1 >= rates_total)
      return 0.0;

   double sum = 0.0;
   int count = 0;
   for(int k = i; k < i + period && k + 1 < rates_total; k++)
     {
      sum += TrueRangeAt(k, high, low, close, rates_total);
      count++;
     }

   if(count <= 0)
      return 0.0;
   return sum / (double)count;
  }

bool IsPastOnlyPivotLow(const int i,const double &low[],const int rates_total)
  {
   if(InpPivotLookback <= 0 || i + InpPivotLookback >= rates_total)
      return false;

   double tolerance = (double)InpPivotTolerancePoints * _Point;
   double candidate = low[i];

   for(int k = 1; k <= InpPivotLookback; k++)
     {
      if(low[i + k] < candidate - tolerance)
         return false;
     }
   return true;
  }

bool IsPastOnlyPivotHigh(const int i,const double &high[],const int rates_total)
  {
   if(InpPivotLookback <= 0 || i + InpPivotLookback >= rates_total)
      return false;

   double tolerance = (double)InpPivotTolerancePoints * _Point;
   double candidate = high[i];

   for(int k = 1; k <= InpPivotLookback; k++)
     {
      if(high[i + k] > candidate + tolerance)
         return false;
     }
   return true;
  }

double PivotExtremityScore(const bool is_buy,const int i,const double &high[],const double &low[],const int rates_total)
  {
   if(InpPivotLookback <= 0 || i + InpPivotLookback >= rates_total)
      return 0.0;

   double window_high = -1.0e100;
   double window_low  =  1.0e100;

   for(int k = 1; k <= InpPivotLookback; k++)
     {
      int idx = i + k;
      if(high[idx] > window_high)
         window_high = high[idx];
      if(low[idx] < window_low)
         window_low = low[idx];
     }

   double width = window_high - window_low;
   if(width <= _Point)
      return 0.5;

   if(is_buy)
      return ClampDouble((window_high - low[i]) / width, 0.0, 1.0);

   return ClampDouble((high[i] - window_low) / width, 0.0, 1.0);
  }

bool FindPreviousPastOnlyPivotLow(const int i,const double &low[],const int rates_total,double &previous_low)
  {
   previous_low = 0.0;
   if(!InpEnableStructureClass)
      return false;

   int max_shift = MinInt(rates_total - InpPivotLookback - 2, i + MathMax(InpStructureLookback, InpPivotLookback + 2));
   for(int j = i + 1; j <= max_shift; j++)
     {
      if(IsPastOnlyPivotLow(j, low, rates_total))
        {
         previous_low = low[j];
         return true;
        }
     }
   return false;
  }

bool FindPreviousPastOnlyPivotHigh(const int i,const double &high[],const int rates_total,double &previous_high)
  {
   previous_high = 0.0;
   if(!InpEnableStructureClass)
      return false;

   int max_shift = MinInt(rates_total - InpPivotLookback - 2, i + MathMax(InpStructureLookback, InpPivotLookback + 2));
   for(int j = i + 1; j <= max_shift; j++)
     {
      if(IsPastOnlyPivotHigh(j, high, rates_total))
        {
         previous_high = high[j];
         return true;
        }
     }
   return false;
  }

double StructureClassForSignal(const bool is_buy,const int i,const double &high[],const double &low[],const int rates_total)
  {
   if(!InpEnableStructureClass)
      return EMPTY_VALUE;

   double tolerance = (double)InpPivotTolerancePoints * _Point;

   if(is_buy)
     {
      double previous_low;
      if(!FindPreviousPastOnlyPivotLow(i, low, rates_total, previous_low))
         return EMPTY_VALUE;

      // HL = 1, LL = 3. Equal/retest lows are tagged by the side of the tolerance band.
      if(low[i] >= previous_low - tolerance)
         return 1.0; // HL
      return 3.0;    // LL
     }

   double previous_high;
   if(!FindPreviousPastOnlyPivotHigh(i, high, rates_total, previous_high))
      return EMPTY_VALUE;

   // HH = 0, LH = 2. Equal/retest highs are tagged as HH inside tolerance.
   if(high[i] >= previous_high - tolerance)
      return 0.0; // HH
   return 2.0;    // LH
  }

bool StructureClassAllowed(const bool is_buy,const double structure_class)
  {
   if(!InpEnableStructureClass)
      return true;

   if(structure_class == EMPTY_VALUE)
      return false;

   int cls = (int)MathRound(structure_class);
   if(is_buy)
     {
      if(cls == 1)
         return InpAllowBuyHL;
      if(cls == 3)
         return InpAllowBuyLL;
      return false;
     }

   if(cls == 0)
      return InpAllowSellHH;
   if(cls == 2)
      return InpAllowSellLH;
   return false;
  }

bool ComputeWaveletContext(const int i,
                           const int rates_total,
                           const double &open[],
                           const double &high[],
                           const double &low[],
                           const double &close[],
                           const double atr_value,
                           int &regime,
                           double &quality,
                           double &energy,
                           double &noise_ratio,
                           double &direction)
  {
   regime      = 0;
   quality     = 0.0;
   energy      = 0.0;
   noise_ratio = 1.0;
   direction   = 0.0;

   int window = MathMax(8, InpWaveletWindow);
   if(i + window + 1 >= rates_total)
      return false;

   double normalizer = MathMax(atr_value, _Point);

   // Directional impulse and path efficiency. All samples are bar i and older.
   double net_move = close[i] - close[i + window - 1];
   double path = 0.0;
   for(int k = i; k < i + window - 1; k++)
      path += MathAbs(close[k] - close[k + 1]);

   if(path <= _Point)
      path = _Point;

   double efficiency = ClampDouble(MathAbs(net_move) / path, 0.0, 1.0);
   noise_ratio = ClampDouble(1.0 - efficiency, 0.0, 1.0);
   direction = (net_move > 0.0 ? 1.0 : (net_move < 0.0 ? -1.0 : 0.0));

   // Lightweight Haar-style multiscale detail energy.
   int max_level = MathMax(1, MathMin(InpWaveletLevel, 5));
   double detail_energy = 0.0;
   int detail_count = 0;

   int block = 2;
   for(int level = 1; level <= max_level; level++)
     {
      if(block > window)
         break;

      int half = block / 2;
      for(int s = i; s + block - 1 < i + window; s += block)
        {
         double newer_avg = 0.0;
         double older_avg = 0.0;

         for(int j = 0; j < half; j++)
            newer_avg += close[s + j];
         for(int j = half; j < block; j++)
            older_avg += close[s + j];

         newer_avg /= (double)half;
         older_avg /= (double)half;

         double detail = newer_avg - older_avg;
         detail_energy += detail * detail;
         detail_count++;
        }

      block *= 2;
     }

   if(detail_count > 0)
      energy = MathSqrt(detail_energy / (double)detail_count) / normalizer;
   else
      energy = 0.0;

   // Compression/expansion context using range expansion in the newer quarter of the window.
   int slice = MathMax(4, window / 4);
   if(i + 2 * slice + 1 >= rates_total)
      slice = MathMax(2, (rates_total - i - 2) / 2);

   double recent_range = 0.0;
   double older_range  = 0.0;
   int range_count = 0;

   for(int j = 0; j < slice; j++)
     {
      recent_range += (high[i + j] - low[i + j]);
      older_range  += (high[i + slice + j] - low[i + slice + j]);
      range_count++;
     }

   double expansion_ratio = 1.0;
   if(range_count > 0)
     {
      recent_range /= (double)range_count;
      older_range  /= (double)range_count;
      expansion_ratio = recent_range / MathMax(older_range, _Point);
     }

   double energy_score    = ClampDouble(energy / MathMax(InpMinWaveletEnergy * 3.0, 0.0001), 0.0, 1.0);
   double expansion_score = ClampDouble((expansion_ratio - 0.70) / 1.30, 0.0, 1.0);
   double impulse_score   = ClampDouble(MathAbs(net_move) / MathMax(normalizer * MathSqrt((double)window), _Point), 0.0, 1.0);
   double clean_score     = ClampDouble(1.0 - noise_ratio, 0.0, 1.0);

   quality = ClampDouble(0.35 * clean_score +
                         0.30 * energy_score +
                         0.20 * expansion_score +
                         0.15 * impulse_score,
                         0.0, 1.0);

   bool clean_enough = (noise_ratio <= InpMaxNoiseRatio);
   bool energetic    = (energy >= InpMinWaveletEnergy);

   // Optional trend lookback refines sign only; it still uses bar i and older data.
   double trend_net = net_move;
   int trend_lookback = MathMax(2, InpTrendLookback);
   if(i + trend_lookback < rates_total)
      trend_net = close[i] - close[i + trend_lookback - 1];

   if(clean_enough && energetic)
     {
      if(trend_net > 0.0)
         regime = 1;
      else if(trend_net < 0.0)
         regime = -1;
      else
         regime = 0;
     }

   return true;
  }

double CombinedSignalScore(const double volume_ratio,
                           const double wick_ratio,
                           const double pivot_score,
                           const double range_atr_ratio,
                           const double wavelet_quality)
  {
   double volume_score = ClampDouble(volume_ratio / MathMax(InpVolumeMultiplier * 2.0, 0.0001), 0.0, 1.0);
   double wick_score   = ClampDouble(wick_ratio, 0.0, 1.0);
   double atr_score    = ClampDouble(range_atr_ratio / MathMax(InpMinRangeATR * 2.0, 0.0001), 0.0, 1.0);
   double pivot_quality= ClampDouble(pivot_score, 0.0, 1.0);
   double wave_score   = ClampDouble(wavelet_quality, 0.0, 1.0);

   return ClampDouble(0.25 * volume_score +
                      0.25 * wick_score +
                      0.15 * pivot_quality +
                      0.15 * atr_score +
                      0.20 * wave_score,
                      0.0, 1.0);
  }

void CalculateSignalForBar(const int i,
                           const int rates_total,
                           const datetime &time[],
                           const double &open[],
                           const double &high[],
                           const double &low[],
                           const double &close[],
                           const long &tick_volume[],
                           const int &spread[])
  {
   ClearBar(i);

   if(!HasEnoughData(i, rates_total))
      return;

   double bar_range = high[i] - low[i];
   if(bar_range <= _Point)
      return;

   bool session_pass = PassSession(time[i]);
   bool spread_pass  = PassSpread(spread[i]);
   if(!session_pass || !spread_pass)
      return;

   double avg_volume = AverageTickVolume(i + 1, InpVolumeLookback, tick_volume, rates_total);
   if(avg_volume <= 0.0)
      return;

   double volume_ratio = (double)tick_volume[i] / avg_volume;
   VolumeRatioBuffer[i] = volume_ratio;

   bool volume_pass = ((long)tick_volume[i] >= InpMinBarVolume && volume_ratio >= InpVolumeMultiplier);
   if(!volume_pass)
      return;

   double atr_value = AverageTrueRangePastOnly(i, InpATRPeriod, high, low, close, rates_total);
   if(atr_value <= _Point)
      atr_value = bar_range;

   double range_atr_ratio = bar_range / MathMax(atr_value, _Point);
   bool atr_pass = (!InpUseATRRangeFilter || range_atr_ratio >= InpMinRangeATR);
   if(!atr_pass)
      return;

   int wavelet_regime = 0;
   double wavelet_quality = 0.0;
   double wavelet_energy = 0.0;
   double noise_ratio = 1.0;
   double wavelet_direction = 0.0;

   if(!ComputeWaveletContext(i, rates_total, open, high, low, close, atr_value,
                             wavelet_regime, wavelet_quality, wavelet_energy, noise_ratio, wavelet_direction))
      return;

   WaveletRegimeBuffer[i] = (double)wavelet_regime;

   bool wavelet_pass = (wavelet_energy >= InpMinWaveletEnergy && noise_ratio <= InpMaxNoiseRatio);
   if(!wavelet_pass)
      return;

   double lower_wick = MathMin(open[i], close[i]) - low[i];
   double upper_wick = high[i] - MathMax(open[i], close[i]);
   double lower_wick_ratio = ClampDouble(lower_wick / bar_range, 0.0, 1.0);
   double upper_wick_ratio = ClampDouble(upper_wick / bar_range, 0.0, 1.0);
   double close_position_buy  = ClampDouble((close[i] - low[i]) / bar_range, 0.0, 1.0);
   double close_position_sell = ClampDouble((high[i] - close[i]) / bar_range, 0.0, 1.0);

   bool buy_pivot  = IsPastOnlyPivotLow(i, low, rates_total);
   bool sell_pivot = IsPastOnlyPivotHigh(i, high, rates_total);

   bool buy_rejection = (lower_wick_ratio >= InpMinWickToRange &&
                         close_position_buy >= InpClosePosition &&
                         (!InpRequireCandleColor || close[i] > open[i]));

   bool sell_rejection = (upper_wick_ratio >= InpMinWickToRange &&
                          close_position_sell >= InpClosePosition &&
                          (!InpRequireCandleColor || close[i] < open[i]));

   bool trend_buy_pass = (!InpUseTrendBias || wavelet_regime >= 0);
   bool trend_sell_pass = (!InpUseTrendBias || wavelet_regime <= 0);

   int common_reason = REASON_VOLUME_PASS | REASON_ATR_PASS | REASON_WAVELET_PASS;
   if(session_pass)
      common_reason |= REASON_SESSION_PASS;
   if(spread_pass)
      common_reason |= REASON_SPREAD_PASS;

   double buy_score = 0.0;
   double sell_score = 0.0;

   if(buy_pivot && buy_rejection && trend_buy_pass)
     {
      double pivot_score = PivotExtremityScore(true, i, high, low, rates_total);
      buy_score = CombinedSignalScore(volume_ratio, lower_wick_ratio, pivot_score, range_atr_ratio, wavelet_quality);

      if(buy_score >= InpMinSignalScore)
        {
         double structure_class = StructureClassForSignal(true, i, high, low, rates_total);
         if(!StructureClassAllowed(true, structure_class))
            return;

         BuySignalBuffer[i]      = low[i] - (double)InpArrowOffsetPoints * _Point;
         SignalStateBuffer[i]    = 1.0;
         SignalScoreBuffer[i]    = buy_score;
         StructureClassBuffer[i] = structure_class;
         DebugReasonBuffer[i]    = (double)(common_reason | REASON_PIVOT_PASS | REASON_REJECTION_PASS | REASON_TREND_PASS | REASON_BUY);
         return;
        }
     }

   if(sell_pivot && sell_rejection && trend_sell_pass)
     {
      double pivot_score = PivotExtremityScore(false, i, high, low, rates_total);
      sell_score = CombinedSignalScore(volume_ratio, upper_wick_ratio, pivot_score, range_atr_ratio, wavelet_quality);

      if(sell_score >= InpMinSignalScore)
        {
         double structure_class = StructureClassForSignal(false, i, high, low, rates_total);
         if(!StructureClassAllowed(false, structure_class))
            return;

         SellSignalBuffer[i]     = high[i] + (double)InpArrowOffsetPoints * _Point;
         SignalStateBuffer[i]    = -1.0;
         SignalScoreBuffer[i]    = sell_score;
         StructureClassBuffer[i] = structure_class;
         DebugReasonBuffer[i]    = (double)(common_reason | REASON_PIVOT_PASS | REASON_REJECTION_PASS | REASON_TREND_PASS | REASON_SELL);
         return;
        }
     }
  }

void MaybeAlert(const int shift,const datetime &time[])
  {
   if(!InpEnableAlerts)
      return;
   if(shift < 0)
      return;
   if(time[shift] == g_last_alert_time)
      return;

   double state = SignalStateBuffer[shift];
   if(state == 0.0)
      return;

   string direction = (state > 0.0 ? "BUY" : "SELL");
   string mode = (InpSignalBar == WPVS_CLOSED_BAR_ONLY ? "closed-bar" : "current-bar visual");
   Alert(StringFormat("Hybrid_WPVS %s %s %s score=%.3f volRatio=%.2f regime=%.0f",
                      _Symbol,
                      EnumToString((ENUM_TIMEFRAMES)_Period),
                      direction,
                      SignalScoreBuffer[shift],
                      VolumeRatioBuffer[shift],
                      WaveletRegimeBuffer[shift]));
   PrintFormat("Hybrid_WPVS alert [%s] %s %s at %s score=%.3f volRatio=%.2f regime=%.0f mode=%s",
               direction,
               _Symbol,
               EnumToString((ENUM_TIMEFRAMES)_Period),
               TimeToString(time[shift], TIME_DATE | TIME_SECONDS),
               SignalScoreBuffer[shift],
               VolumeRatioBuffer[shift],
               WaveletRegimeBuffer[shift],
               mode);

   g_last_alert_time = time[shift];
  }

//+------------------------------------------------------------------+
//| Custom indicator initialization                                  |
//+------------------------------------------------------------------+
int OnInit()
  {
   SetIndexBuffer(0, BuySignalBuffer,      INDICATOR_DATA);
   SetIndexBuffer(1, SellSignalBuffer,     INDICATOR_DATA);
   SetIndexBuffer(2, SignalStateBuffer,    INDICATOR_DATA);
   SetIndexBuffer(3, SignalScoreBuffer,    INDICATOR_DATA);
   SetIndexBuffer(4, VolumeRatioBuffer,    INDICATOR_DATA);
   SetIndexBuffer(5, WaveletRegimeBuffer,  INDICATOR_DATA);
   SetIndexBuffer(6, StructureClassBuffer, INDICATOR_DATA);
   SetIndexBuffer(7, DebugReasonBuffer,    INDICATOR_DATA);

   ArraySetAsSeries(BuySignalBuffer,      true);
   ArraySetAsSeries(SellSignalBuffer,     true);
   ArraySetAsSeries(SignalStateBuffer,    true);
   ArraySetAsSeries(SignalScoreBuffer,    true);
   ArraySetAsSeries(VolumeRatioBuffer,    true);
   ArraySetAsSeries(WaveletRegimeBuffer,  true);
   ArraySetAsSeries(StructureClassBuffer, true);
   ArraySetAsSeries(DebugReasonBuffer,    true);

   PlotIndexSetInteger(0, PLOT_ARROW, 233);
   PlotIndexSetInteger(1, PLOT_ARROW, 234);

   for(int p = 0; p < 8; p++)
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("Hybrid_WPVS(closed=%s, vol=%.2f, pivot=%d, wave=%d)",
                                   (InpSignalBar == WPVS_CLOSED_BAR_ONLY ? "true" : "false"),
                                   InpVolumeMultiplier,
                                   InpPivotLookback,
                                   InpWaveletWindow));

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Custom indicator iteration                                       |
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
   if(rates_total <= RequiredDepth() + 5)
      return 0;

   ArraySetAsSeries(time,        true);
   ArraySetAsSeries(open,        true);
   ArraySetAsSeries(high,        true);
   ArraySetAsSeries(low,         true);
   ArraySetAsSeries(close,       true);
   ArraySetAsSeries(tick_volume, true);
   ArraySetAsSeries(volume,      true);
   ArraySetAsSeries(spread,      true);

   int min_shift = (InpSignalBar == WPVS_CLOSED_BAR_ONLY ? 1 : 0);
   int oldest_valid_shift = rates_total - RequiredDepth() - 1;
   if(oldest_valid_shift < min_shift)
      return rates_total;

   // The current bar is non-tradeable by default and is kept empty in closed-bar mode.
   if(InpSignalBar == WPVS_CLOSED_BAR_ONLY)
      ClearBar(0);

   int bars_to_process = MathMax(10, InpMaxBarsToProcess);
   int start_shift;

   if(prev_calculated == 0)
     {
      InitializeBuffers();
      start_shift = MinInt(oldest_valid_shift, min_shift + bars_to_process - 1);
     }
   else
     {
      int newly_added = rates_total - prev_calculated;
      if(newly_added < 0)
         newly_added = 0;

      // Recalculate only the newest few bars. This is deterministic because only past bars are read.
      start_shift = MinInt(oldest_valid_shift, min_shift + newly_added + 3);
      start_shift = MinInt(start_shift, min_shift + bars_to_process - 1);
     }

   for(int i = start_shift; i >= min_shift; i--)
      CalculateSignalForBar(i, rates_total, time, open, high, low, close, tick_volume, spread);

   if(prev_calculated > 0)
      MaybeAlert(min_shift, time);

   return rates_total;
  }
//+------------------------------------------------------------------+
