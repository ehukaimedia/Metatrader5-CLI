//+------------------------------------------------------------------+
//| {{name}}.mq5 - minimal indicator skeleton (author your math here) |
//+------------------------------------------------------------------+
#property strict
#property version "0.1.0"
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_label1  "{{name}}"

double Buf[];

int OnInit()
{
    SetIndexBuffer(0, Buf, INDICATOR_DATA);
    return INIT_SUCCEEDED;
}

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
    /* author your calculation into Buf[i] here */
    return rates_total;
}
