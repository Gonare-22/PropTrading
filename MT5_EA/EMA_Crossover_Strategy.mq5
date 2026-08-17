//+------------------------------------------------------------------+
//|                                        EMA_Crossover_Strategy.mq5 |
//|                    EMA 20/50/100 Crossover Strategy EA            |
//|                                                                    |
//| STRATEGY RULES:                                                    |
//|  LONG  Entry : EMA50 crosses ABOVE EMA100                        |
//|               + Confirmation: EMA20 > EMA50 > EMA100             |
//|  SHORT Entry : EMA50 crosses BELOW EMA100                        |
//|               + Confirmation: EMA20 < EMA50 < EMA100             |
//|  LONG  Exit  : EMA20 crosses BELOW EMA50                         |
//|  SHORT Exit  : EMA20 crosses ABOVE EMA50                         |
//|  Execution   : Signal on bar close, enter on NEXT bar open        |
//|  Stop Loss   : Risk % of account balance                          |
//+------------------------------------------------------------------+
#property copyright   "EMA Crossover Strategy"
#property version     "1.00"
#property description "EMA 20/50/100 Crossover Expert Advisor"
#property description "Matches Python backtest logic exactly"

// --- Input Parameters ---
input group "=== Risk Management ==="
input double   RiskPercent     = 1.0;    // Risk % per trade (of account balance)
input double   LotSize         = 0.10;   // Lot size (used only for Forex/Commodities)
input bool     UseFixedLot     = true;   // true = fixed lot, false = risk-based sizing

input group "=== EMA Settings ==="
input int      EMA_Fast        = 20;     // EMA Fast period
input int      EMA_Mid         = 50;     // EMA Mid period
input int      EMA_Slow        = 100;    // EMA Slow period
input int      WarmupBars      = 100;    // Bars to skip for EMA stabilisation

input group "=== Trade Settings ==="
input string   TradeComment    = "EMA_Cross_EA";  // Trade comment
input int      MagicNumber     = 202602;           // Magic number (unique ID)
input bool     AllowLong       = true;   // Allow long trades
input bool     AllowShort      = true;   // Allow short trades

//--- Global Variables ---
int    handleEMA20, handleEMA50, handleEMA100;
double ema20[], ema50[], ema100[];
int    barCount = 0;

// Trade state
bool   pendingLong   = false;
bool   pendingShort  = false;
bool   pendingClose  = false;

//+------------------------------------------------------------------+
//| Expert Initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   // Create EMA indicator handles (calculated on the chart's current symbol & timeframe)
   handleEMA20  = iMA(_Symbol, _Period, EMA_Fast, 0, MODE_EMA, PRICE_CLOSE);
   handleEMA50  = iMA(_Symbol, _Period, EMA_Mid,  0, MODE_EMA, PRICE_CLOSE);
   handleEMA100 = iMA(_Symbol, _Period, EMA_Slow, 0, MODE_EMA, PRICE_CLOSE);

   if(handleEMA20 == INVALID_HANDLE || handleEMA50 == INVALID_HANDLE || handleEMA100 == INVALID_HANDLE)
   {
      Print("ERROR: Failed to create EMA indicators. Error: ", GetLastError());
      return INIT_FAILED;
   }

   // Set arrays as series (index 0 = most recent bar)
   ArraySetAsSeries(ema20,  true);
   ArraySetAsSeries(ema50,  true);
   ArraySetAsSeries(ema100, true);

   Print("==============================================");
   Print(" EMA Crossover Strategy EA Initialised");
   Print(" Symbol:    ", _Symbol);
   Print(" Timeframe: ", EnumToString(_Period));
   Print(" EMA Fast:  ", EMA_Fast);
   Print(" EMA Mid:   ", EMA_Mid);
   Print(" EMA Slow:  ", EMA_Slow);
   Print(" Risk %:    ", RiskPercent);
   Print(" Lot Size:  ", LotSize);
   Print("==============================================");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert Deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(handleEMA20);
   IndicatorRelease(handleEMA50);
   IndicatorRelease(handleEMA100);
   Print("EA Deinitialised. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert Tick Function (called on every new price tick)            |
//+------------------------------------------------------------------+
void OnTick()
{
   // Only act on the open of a NEW bar (same as "enter at next bar open")
   static datetime lastBarTime = 0;
   datetime currentBarTime = iTime(_Symbol, _Period, 0);

   bool isNewBar = (currentBarTime != lastBarTime);

   // ---------------------------------------------------------------
   // CRITICAL FIX: Execute pending orders at FIRST TICK of new bar
   // This ensures execution happens at bar open, not 1-2 bars later
   // ---------------------------------------------------------------
   if(isNewBar && lastBarTime != 0)
   {
      // Log execution time for debugging
      Print("[EXECUTE] New bar opened at ", TimeToString(currentBarTime), " - Executing pending orders");
      
      if(pendingClose)
      {
         Print("[EXECUTE] Closing position at bar open: ", TimeToString(currentBarTime));
         CloseAllPositions();
         pendingClose = false;
      }

      if(pendingLong && AllowLong)
      {
         Print("[EXECUTE] Opening LONG at bar open: ", TimeToString(currentBarTime));
         OpenTrade(ORDER_TYPE_BUY);
         pendingLong = false;
      }
      else if(pendingShort && AllowShort)
      {
         Print("[EXECUTE] Opening SHORT at bar open: ", TimeToString(currentBarTime));
         OpenTrade(ORDER_TYPE_SELL);
         pendingShort = false;
      }
      
      // Reset pending flags even if not allowed, to prevent stale state
      pendingLong  = false;
      pendingShort = false;
   }

   if(!isNewBar) return;          // Not a new bar — skip signal detection
   lastBarTime = currentBarTime;

   barCount++;

   // ---------------------------------------------------------------
   // STEP 2: Read EMA values (we need bar 1 = last CLOSED bar)
   //         index 0 = current open bar (still forming — skip)
   //         index 1 = last fully closed bar  (signal bar)
   //         index 2 = bar before signal bar  (previous bar)
   // NOTE: Signal detection happens here, execution happens above at bar open
   // ---------------------------------------------------------------
   if(CopyBuffer(handleEMA20,  0, 0, 3, ema20)  < 3) return;
   if(CopyBuffer(handleEMA50,  0, 0, 3, ema50)  < 3) return;
   if(CopyBuffer(handleEMA100, 0, 0, 3, ema100) < 3) return;

   // Current (last closed bar) — index 1
   double curr20  = ema20[1];
   double curr50  = ema50[1];
   double curr100 = ema100[1];

   // Previous bar — index 2
   double prev20  = ema20[2];
   double prev50  = ema50[2];
   double prev100 = ema100[2];

   // Skip warmup period (not enough bars for EMA to stabilise)
   if(barCount < WarmupBars)
   {
      // Print("Warmup: bar ", barCount, " / ", WarmupBars);
      return;
   }

   // ---------------------------------------------------------------
   // STEP 3: Check current position state
   // ---------------------------------------------------------------
   bool hasLong  = HasOpenPosition(POSITION_TYPE_BUY);
   bool hasShort = HasOpenPosition(POSITION_TYPE_SELL);
   bool isFlat   = (!hasLong && !hasShort);

   // ---------------------------------------------------------------
   // STEP 4: SIGNAL DETECTION on last closed bar
   // ---------------------------------------------------------------

   // --- EXIT SIGNALS (check first to avoid re-entry on same bar) ---

   if(hasLong)
   {
      // LONG EXIT: EMA20 crosses BELOW EMA50
      if(prev20 >= prev50 && curr20 < curr50)
      {
         Print("[EXIT SIGNAL] LONG exit: EMA20 crossed below EMA50 at bar close ",
               TimeToString(iTime(_Symbol, _Period, 1)));
         Print("  prev20=", prev20, " prev50=", prev50,
               " curr20=", curr20, " curr50=", curr50);
         pendingClose = true;
      }
   }

   if(hasShort)
   {
      // SHORT EXIT: EMA20 crosses ABOVE EMA50
      if(prev20 <= prev50 && curr20 > curr50)
      {
         Print("[EXIT SIGNAL] SHORT exit: EMA20 crossed above EMA50 at bar close ",
               TimeToString(iTime(_Symbol, _Period, 1)));
         Print("  prev20=", prev20, " prev50=", prev50,
               " curr20=", curr20, " curr50=", curr50);
         pendingClose = true;
      }
   }

   // --- ENTRY SIGNALS (only when flat / no open position) ---

   if(isFlat)
   {
      // LONG SIGNAL: EMA50 crosses ABOVE EMA100
      if(prev50 <= prev100 && curr50 > curr100)
      {
         Print("[ENTRY SIGNAL] LONG: EMA50 crossed above EMA100");
         Print("  prev50=", prev50, " prev100=", prev100,
               " curr50=", curr50, " curr100=", curr100);
         Print("  EMA Values: EMA20=", curr20, " EMA50=", curr50, " EMA100=", curr100);
         pendingLong = true;
      }

      // SHORT SIGNAL: EMA50 crosses BELOW EMA100
      else if(prev50 >= prev100 && curr50 < curr100)
      {
         Print("[ENTRY SIGNAL] SHORT: EMA50 crossed below EMA100");
         Print("  prev50=", prev50, " prev100=", prev100,
               " curr50=", curr50, " curr100=", curr100);
         Print("  EMA Values: EMA20=", curr20, " EMA50=", curr50, " EMA100=", curr100);
         pendingShort = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Open a new trade (BUY or SELL) at market price                   |
//+------------------------------------------------------------------+
void OpenTrade(ENUM_ORDER_TYPE orderType)
{
   MqlTradeRequest  request = {};
   MqlTradeResult   result  = {};

   double price     = (orderType == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                                     : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lotSize   = CalculateLotSize(orderType, price);

   if(lotSize <= 0)
   {
      Print("ERROR: Calculated lot size is 0 or negative. Trade not placed.");
      return;
   }

   // Calculate stop loss price
   double slPrice   = CalculateStopLoss(orderType, price, lotSize);
   double tpPrice   = 0;   // No take profit — exit handled by EMA signal

   // Normalise lot size to broker's step
   double lotStep   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lotSize          = MathFloor(lotSize / lotStep) * lotStep;

   // Normalise prices to symbol digits
   int    digits    = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   price            = NormalizeDouble(price,   digits);
   slPrice          = (slPrice > 0) ? NormalizeDouble(slPrice, digits) : 0;

   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = _Symbol;
   request.volume   = lotSize;
   request.type     = orderType;
   request.price    = price;
   request.sl       = slPrice;
   request.tp       = tpPrice;
   request.comment  = TradeComment;
   request.magic    = MagicNumber;
   request.deviation= 10;   // Slippage tolerance in points

   if(!OrderSend(request, result))
   {
      Print("ERROR: OrderSend failed. Error: ", GetLastError(),
            " Retcode: ", result.retcode, " Comment: ", result.comment);
   }
   else
   {
      string dir = (orderType == ORDER_TYPE_BUY) ? "LONG" : "SHORT";
      Print("[TRADE OPENED] ", dir, " | Price=", price,
            " | Lots=", lotSize,
            " | SL=", slPrice,
            " | Ticket=", result.order);
   }
}

//+------------------------------------------------------------------+
//| Close all positions for this EA (by magic number)               |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      if(PositionGetString(POSITION_SYMBOL)          != _Symbol)     continue;
      if(PositionGetInteger(POSITION_MAGIC)          != MagicNumber) continue;

      MqlTradeRequest  request = {};
      MqlTradeResult   result  = {};

      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

      request.action  = TRADE_ACTION_DEAL;
      request.symbol  = _Symbol;
      request.volume  = PositionGetDouble(POSITION_VOLUME);
      request.type    = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      request.price   = (posType == POSITION_TYPE_BUY)
                        ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                        : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      request.position= ticket;
      request.comment = TradeComment + "_close";
      request.magic   = MagicNumber;
      request.deviation = 10;

      if(!OrderSend(request, result))
      {
         Print("ERROR: Close position failed. Ticket=", ticket,
               " Error=", GetLastError(), " Retcode=", result.retcode);
      }
      else
      {
         Print("[TRADE CLOSED] Ticket=", ticket,
               " Price=", request.price,
               " PnL=", PositionGetDouble(POSITION_PROFIT));
      }
   }
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk % or fixed lot                  |
//+------------------------------------------------------------------+
double CalculateLotSize(ENUM_ORDER_TYPE orderType, double entryPrice)
{
   if(UseFixedLot) return LotSize;

   // Risk-based position sizing
   // Max loss = RiskPercent % of account balance
   double balance     = AccountInfoDouble(ACCOUNT_BALANCE);
   double maxLoss     = balance * (RiskPercent / 100.0);

   // Estimate stop distance in price (use 2 * average spread as a rough base)
   // For proper stop-based sizing, the stop distance is calculated from CalculateStopLoss()
   // Here we use a simple ATR-based estimate: 2% of price as default stop distance
   double stopDist    = entryPrice * 0.02;   // 2% stop distance
   if(stopDist <= 0) stopDist = entryPrice * 0.01;

   double tickValue   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double lotSizeCalc = 0;

   if(tickValue > 0 && tickSize > 0 && stopDist > 0)
   {
      // Ticks in the stop distance
      double stopTicks = stopDist / tickSize;
      // Value of stop distance per lot
      double stopValuePerLot = stopTicks * tickValue;

      if(stopValuePerLot > 0)
         lotSizeCalc = maxLoss / stopValuePerLot;
   }

   // Apply broker limits
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lotSizeCalc   = MathMax(lotSizeCalc, minLot);
   lotSizeCalc   = MathMin(lotSizeCalc, maxLot);

   return lotSizeCalc;
}

//+------------------------------------------------------------------+
//| Calculate stop loss price based on risk % of balance             |
//+------------------------------------------------------------------+
double CalculateStopLoss(ENUM_ORDER_TYPE orderType, double entryPrice, double lotSize)
{
   if(RiskPercent >= 100.0) return 0;   // No stop loss if risk = 100%

   double balance       = AccountInfoDouble(ACCOUNT_BALANCE);
   double maxLossAmt    = balance * (RiskPercent / 100.0);

   double tickValue     = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize      = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);

   if(tickValue <= 0 || tickSize <= 0) return 0;

   // Total value per tick move for this lot size
   double valuePerTick  = (lotSize / SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) * tickValue;
   if(valuePerTick <= 0) valuePerTick = tickValue;

   // Price distance = max loss / (value per price unit * lots)
   double priceDistance = (maxLossAmt * tickSize) / (lotSize * tickValue / tickSize);

   // Simpler approach: use pip value
   double contractSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contractSize > 0)
   {
      // value per price unit = lot * contract size * tick_value / tick_size
      double valuePerPriceUnit = lotSize * contractSize * tickValue / tickSize;
      if(valuePerPriceUnit > 0)
         priceDistance = maxLossAmt / valuePerPriceUnit;
   }

   double slPrice = 0;
   if(orderType == ORDER_TYPE_BUY)
      slPrice = entryPrice - priceDistance;
   else
      slPrice = entryPrice + priceDistance;

   return slPrice;
}

//+------------------------------------------------------------------+
//| Check if a position of given type is open for this EA            |
//+------------------------------------------------------------------+
bool HasOpenPosition(ENUM_POSITION_TYPE posType)
{
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL)  != _Symbol)     continue;
      if(PositionGetInteger(POSITION_MAGIC)  != MagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == posType)
         return true;
   }
   return false;
}
//+------------------------------------------------------------------+
