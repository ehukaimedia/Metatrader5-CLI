//+------------------------------------------------------------------+
//| {{name}}.mq5 - minimal EA skeleton (author your strategy here)   |
//+------------------------------------------------------------------+
#property strict
#property version "0.1"

input long MagicNumber = 88888;

int OnInit()                    { return INIT_SUCCEEDED; }
void OnDeinit(const int reason) { /* cleanup if needed */ }
void OnTick()                   { /* author entry / management / exit here */ }
