//+------------------------------------------------------------------+
//|                              XAUUSD_1M_Strategy_v6_Optimized.mq5 |
//|                                                                  |
//|              XAUUSD 1-Minute Trading Strategy - Version 6        |
//|              Optimized with K=6, D=6, RSI=28, Stoch=28          |
//+------------------------------------------------------------------+
#property copyright "Optimized Strategy v6"
#property link      ""
#property version   "6.12"
#property strict
#property description "Stochastic RSI + EMA Crossover + Choppiness Filter"
#property description "K Decision Making: Primary signal generator"
#property description "v6.10: 2-bar EMA cross detection + cross memory + reverse-after-stop"
#property description "v6.12: Stoch RSI permission exact (Long K>=75 stay >50 off <50 | Short K<=25 stay <50 off >50)"
#property description "v6.11: auto-detect order filling mode (fixes [Unsupported filling mode] on brokers without FOK)"

//--- Capital & Risk Management
input group "Capital & Risk Management"
input double InitialCapital = 1000.0;      // Initial Capital ($)
input double FixedStopLoss = 50.0;         // Fixed Stop Loss per trade ($)
input double LotSize = 0.10;               // Lot Size
input int MagicNumber = 123456;            // Magic Number

//--- EMA Settings
input group "EMA Trend Settings"
input int FastEMA = 20;                    // Fast EMA Period
input int SlowEMA = 50;                    // Slow EMA Period

//--- Stochastic RSI Settings (Version 6 Optimized)
input group "Stochastic RSI Settings (v6 Optimized)"
input int RSILength = 28;                  // RSI Length
input int StochLength = 28;                // Stochastic Length  
input int KSmooth = 6;                     // K Smooth Period (Primary Decision)
input int DSmooth = 6;                     // D Smooth Period
input double UpperBand = 75.0;             // Upper Band - Long Permission (≥75)
input double LowerBand = 25.0;             // Lower Band - Short Permission (≤25)
input double MiddleBand = 50.0;            // Middle Band - Permission Reset
input double Tolerance = 1.0;              // (Unused since v6.12 - permission uses exact 75/50/25)

//--- Choppiness Index Settings (Version 6 Optimized)
input group "Choppiness Index Settings (v6)"
input int ChopLength = 14;                 // Choppiness Index Length
input double ChopMaxEntry = 55.0;          // Maximum CHOP for Entry (at or below = trending)

//--- Trading Permissions
input group "Trading Permissions"
input bool AllowLong = true;               // Allow Long Positions
input bool AllowShort = true;              // Allow Short Positions
input bool AllowFlip = true;               // Allow Same-Bar Flip Trade (Exit + Enter Opposite)
input bool UseStrictKDecision = true;      // Use Strict K-Value Decision Making
input bool AllowLookaheadEntry = true;     // (Unused since v6.12 - permission stays active while K>50 / K<50)

//--- Exit Strategy
input group "Exit Strategy"
input bool ExitOnOppositeEMA = true;       // Exit on Opposite EMA Cross
input bool UseTrailingStop = true;         // Use Progressive Profit-Based Trailing Stop
input double TrailingStopDistance = 30.0;  // Trailing Stop Distance (points) - DEPRECATED

//--- Cross Detection & Re-entry (v6.10 fix)
input group "Cross Detection & Re-entry (v6.10)"
input bool UseCrossMemory = true;          // Remember an EMA cross for a few bars (late K/CHOP pass can still enter)
input int CrossMemoryBars = 3;             // Bars a cross stays valid for entry (0 = same bar only)
input bool AllowReverseAfterStop = true;   // After a trailing/SL exit, allow entry in the OPPOSITE direction if EMA already agrees
input int ReverseAfterStopBars = 5;        // Bars after the stop-out during which the reverse entry is allowed

//--- Session Filter (Optional)
input group "Session Filter (Optional)"
input bool UseSessionFilter = false;       // Enable Session Filter
input int SessionStartHour = 0;            // Session Start Hour (0-23)
input int SessionEndHour = 23;             // Session End Hour (0-23)

//--- Global Variables
double fastEMABuffer[], slowEMABuffer[];
double rsiBuffer[];
double stochKBuffer[], stochDBuffer[];
double chopBuffer[];
bool longPermission = false;
bool shortPermission = false;
int longPermissionBar = -999;   // Track which bar granted long permission
int shortPermissionBar = -999;  // Track which bar granted short permission
int barsTotal = 0;
datetime lastBarTime = 0;

//--- Progressive Trailing Stop Variables
double positionEntryPrice = 0;
double currentTrailingSL = 0;
double highestProfit = 0;  // Track highest profit reached
bool trailingStopActive = false;

//--- Cross memory / stop-out tracking (v6.10)
int barCounter = 0;                // Counts processed bars
int bullCrossAge = -1;             // Bars since bullish cross (-1 = none, 9999 = already used)
int bearCrossAge = -1;             // Bars since bearish cross (-1 = none, 9999 = already used)
bool bullCrossSignal = false;      // Bullish cross seen on this bar (used by exit logic)
bool bearCrossSignal = false;      // Bearish cross seen on this bar (used by exit logic)
int trackedPosType = -1;           // Position type the EA believes is open (-1 = none)
int stopExitType = -1;             // Type of position closed by broker SL/trailing (-1 = none)
int stopExitBar = -9999;           // barCounter value when that stop-out was noticed

//--- Indicator Handles
int handleFastEMA, handleSlowEMA;
int handleRSI;

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- Initialize indicator handles
   handleFastEMA = iMA(_Symbol, PERIOD_M1, FastEMA, 0, MODE_EMA, PRICE_CLOSE);
   handleSlowEMA = iMA(_Symbol, PERIOD_M1, SlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   handleRSI = iRSI(_Symbol, PERIOD_M1, RSILength, PRICE_CLOSE);
   
   if(handleFastEMA == INVALID_HANDLE || handleSlowEMA == INVALID_HANDLE || handleRSI == INVALID_HANDLE)
   {
      Print("❌ Error creating indicator handles");
      return(INIT_FAILED);
   }
   
   //--- Set arrays as series
   ArraySetAsSeries(fastEMABuffer, true);
   ArraySetAsSeries(slowEMABuffer, true);
   ArraySetAsSeries(rsiBuffer, true);
   ArraySetAsSeries(stochKBuffer, true);
   ArraySetAsSeries(stochDBuffer, true);
   ArraySetAsSeries(chopBuffer, true);
   
   barsTotal = iBars(_Symbol, PERIOD_M1);
   lastBarTime = iTime(_Symbol, PERIOD_M1, 0);
   
   //--- If the EA is (re)loaded while a position is open, keep managing it
   trackedPosType = GetCurrentPosition();
   if(trackedPosType != -1)
   {
      positionEntryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      currentTrailingSL = PositionGetDouble(POSITION_SL);
      trailingStopActive = true;
      Print("Existing position found on load - trailing stop management resumed");
   }
   
   //--- Print initialization info
   Print("═══════════════════════════════════════════════════════");
   Print("✓ XAUUSD 1M Strategy v6 - Progressive Trailing Stop");
   Print("═══════════════════════════════════════════════════════");
   Print("💰 Initial Capital: $", InitialCapital);
   Print("🛑 Initial Stop Loss: -$", FixedStopLoss, " (Maximum Loss)");
   Print("📈 Progressive Trailing Stop Logic:");
   Print("   └─ Profit $50  → SL moves to $0 (breakeven)");
   Print("   └─ Profit $100 → SL moves to +$30");
   Print("   └─ Profit $150 → SL moves to +$60");
   Print("   └─ Every +$50 profit → +$30 SL increase");
   Print("   └─ SL ONLY moves upward (LONG) or downward price (SHORT)");
   Print("📊 Lot Size: ", LotSize);
   Print("───────────────────────────────────────────────────────");
   Print("📈 EMA: ", FastEMA, "/", SlowEMA);
   Print("📊 Stoch RSI: RSI=", RSILength, ", Stoch=", StochLength);
   Print("🎯 K/D Smoothing: ", KSmooth, "/", DSmooth, " (K = Primary Decision)");
   Print("📏 Permission Bands: Upper=", UpperBand, " (≥75 = Long), Lower=", LowerBand, " (≤25 = Short), Middle=", MiddleBand);
   Print("📏 Entry Tolerance: ±", Tolerance);
   Print("🔍 Lookahead Entry: ", (AllowLookaheadEntry ? "Enabled (1-2 bars)" : "Disabled"));
   Print("Cross memory: ", (UseCrossMemory ? "ON" : "OFF"), " | window=", CrossMemoryBars, " bars | Reverse-after-stop: ", (AllowReverseAfterStop ? "ON" : "OFF"), " (", ReverseAfterStopBars, " bars)");
   Print("Order filling mode: ", EnumToString(GetFillingMode()), " | symbol filling flags=", SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE), " | symbol=", _Symbol);
   Print("🌊 Choppiness: Length=", ChopLength, ", Max=", ChopMaxEntry);
   Print("───────────────────────────────────────────────────────");
   Print("✅ Strategy initialized successfully");
   Print("═══════════════════════════════════════════════════════");
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   //--- Release indicator handles
   if(handleFastEMA != INVALID_HANDLE) IndicatorRelease(handleFastEMA);
   if(handleSlowEMA != INVALID_HANDLE) IndicatorRelease(handleSlowEMA);
   if(handleRSI != INVALID_HANDLE) IndicatorRelease(handleRSI);
   
   Print("Strategy deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   //--- CRITICAL: Monitor every tick for trailing stop updates
   //--- Check for new bar for entry/exit signals
   datetime currentBarTime = iTime(_Symbol, PERIOD_M1, 0);
   
   static bool firstRun = true;
   bool isNewBar = (currentBarTime != lastBarTime);
   
   //--- Update trailing stop every tick (for progressive profit-based SL)
   int posType = GetCurrentPosition();
   if(posType != -1 && UseTrailingStop)
   {
      UpdateProgressiveTrailingStop(posType);
   }
   
   // Entry/exit signals only checked on new bar
   if(!isNewBar && !firstRun) return;
   
   if(isNewBar)
   {
      lastBarTime = currentBarTime;
      Print("══════════════════════════════════════════════════════");
      Print("🕐 NEW BAR | Time: ", TimeToString(currentBarTime, TIME_DATE|TIME_MINUTES));
      Print("══════════════════════════════════════════════════════");
   }
   firstRun = false;
   
   //--- Session filter
   if(UseSessionFilter && !IsInTradingSession())
   {
      return;
   }
   
   //--- Update indicators
   if(!UpdateIndicators()) return;
   
   //--- Update permission flags based on K value
   UpdateKBasedPermissions();
   
   //--- v6.10: cross memory and stop-out detection (once per bar)
   barCounter++;
   UpdateCrossMemory();
   DetectBrokerSideExit();
   
   //--- Check current position (re-check after potential trailing stop update)
   posType = GetCurrentPosition();
   
   //--- Track if we closed a position this bar (for flip trade logic)
   bool positionClosedThisBar = false;
   int closedPositionType = -1;
   
   //--- Manage existing position
   if(posType != -1)
   {
      //--- Log current position status
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(PositionSelectByTicket(ticket))
         {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
               PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
               double currentSL = PositionGetDouble(POSITION_SL);
               double currentProfit = PositionGetDouble(POSITION_PROFIT);
               double currentPrice = (posType == POSITION_TYPE_BUY) ? 
                                    SymbolInfoDouble(_Symbol, SYMBOL_BID) : 
                                    SymbolInfoDouble(_Symbol, SYMBOL_ASK);
               
               Print("📊 POSITION STATUS:");
               Print("   Type: ", (posType == POSITION_TYPE_BUY ? "LONG" : "SHORT"));
               Print("   Entry: ", NormalizeDouble(positionEntryPrice, _Digits));
               Print("   Current: ", NormalizeDouble(currentPrice, _Digits));
               Print("   P/L: $", NormalizeDouble(currentProfit, 2));
               Print("   Current SL: ", NormalizeDouble(currentSL, _Digits));
               Print("   Trailing Active: ", (trailingStopActive ? "YES" : "NO"));
               
               // WARNING: If SL was somehow removed
               if(currentSL <= 0)
               {
                  Print("⚠️ WARNING: Stop Loss missing from position #", ticket, "!");
               }
            }
         }
      }
      
      //--- Check for EMA exit signal
      if(CheckExitSignal(posType))
      {
         closedPositionType = posType;
         ClosePosition("EMA Cross Exit");
         trackedPosType = -1; // closed by the EA itself, not a stop-out
         positionClosedThisBar = true;
         
         // Reset trailing stop variables
         ResetTrailingStopVariables();
         
         // Wait a moment for position to close
         Sleep(100);
         
         // Verify position is actually closed
         posType = GetCurrentPosition();
         
         Print("📊 Position closed via EMA signal | Type: ", (closedPositionType == POSITION_TYPE_BUY ? "LONG" : "SHORT"),
               " | Flip allowed: ", (AllowFlip ? "Yes" : "No"));
      }
   }
   
   //--- Check for entry signals (if no position OR flip trade allowed)
   posType = GetCurrentPosition(); // Re-check position status
   
   if(posType == -1)
   {
      //--- Check for flip trade opportunity
      if(positionClosedThisBar && AllowFlip)
      {
         Print("🔄 FLIP TRADE CHECK | Just closed ", (closedPositionType == POSITION_TYPE_BUY ? "LONG" : "SHORT"), 
               " | Checking opposite direction...");
         
         // If we just closed a LONG, check for SHORT entry
         if(closedPositionType == POSITION_TYPE_BUY)
         {
            if(CheckShortEntry() && AllowShort)
            {
               Print("🔄 FLIP TRADE DETECTED | LONG → SHORT");
               OpenPosition(ORDER_TYPE_SELL);
               return;
            }
         }
         // If we just closed a SHORT, check for LONG entry
         else if(closedPositionType == POSITION_TYPE_SELL)
         {
            if(CheckLongEntry() && AllowLong)
            {
               Print("🔄 FLIP TRADE DETECTED | SHORT → LONG");
               OpenPosition(ORDER_TYPE_BUY);
               return;
            }
         }
         
         Print("🔄 No flip trade signal | Conditions not met for opposite direction");
      }
      
      //--- Normal entry logic (if not a flip trade scenario)
      if(!positionClosedThisBar)
      {
         //--- v6.10: reverse trade after the previous position was closed by SL / trailing stop
         if(stopExitType != -1)
         {
            if(!AllowReverseAfterStop || (barCounter - stopExitBar) > ReverseAfterStopBars)
            {
               stopExitType = -1; // window over
            }
            else if(stopExitType == POSITION_TYPE_SELL && AllowLong && CheckLongEntry(true))
            {
               Print("REVERSE AFTER STOP | SHORT stopped out -> LONG (EMA already bullish)");
               OpenPosition(ORDER_TYPE_BUY);
               return;
            }
            else if(stopExitType == POSITION_TYPE_BUY && AllowShort && CheckShortEntry(true))
            {
               Print("REVERSE AFTER STOP | LONG stopped out -> SHORT (EMA already bearish)");
               OpenPosition(ORDER_TYPE_SELL);
               return;
            }
         }
         
         if(CheckLongEntry() && AllowLong)
         {
            OpenPosition(ORDER_TYPE_BUY);
         }
         else if(CheckShortEntry() && AllowShort)
         {
            OpenPosition(ORDER_TYPE_SELL);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Update all indicator buffers                                       |
//+------------------------------------------------------------------+
bool UpdateIndicators()
{
   //--- Copy EMA values (need 3 bars for crossover detection)
   if(CopyBuffer(handleFastEMA, 0, 0, 3, fastEMABuffer) <= 0)
   {
      Print("Error copying Fast EMA buffer");
      return false;
   }
   
   if(CopyBuffer(handleSlowEMA, 0, 0, 3, slowEMABuffer) <= 0)
   {
      Print("Error copying Slow EMA buffer");
      return false;
   }
   
   //--- Copy RSI values (need more bars for Stochastic calculation)
   int rsiBufferSize = StochLength + KSmooth + DSmooth + 10;
   if(CopyBuffer(handleRSI, 0, 0, rsiBufferSize, rsiBuffer) <= 0)
   {
      Print("Error copying RSI buffer");
      return false;
   }
   
   //--- Calculate Stochastic RSI with K=6, D=6
   CalculateStochasticRSI();
   
   //--- Calculate Choppiness Index with Length=14
   CalculateChoppinessIndex();
   
   return true;
}

//+------------------------------------------------------------------+
//| Calculate Stochastic RSI (K=6, D=6 optimized for decision making) |
//+------------------------------------------------------------------+
void CalculateStochasticRSI()
{
   ArrayResize(stochKBuffer, 10);
   ArrayResize(stochDBuffer, 10);
   
   //--- Calculate %K (Stochastic on RSI)
   static double rawStochValues[];
   static double kValues[];
   static double dValues[];
   
   ArrayResize(rawStochValues, StochLength + 10);
   ArrayResize(kValues, KSmooth + 10);
   ArrayResize(dValues, DSmooth + 10);
   
   //--- Calculate raw stochastic value
   double rsiHigh = rsiBuffer[0];
   double rsiLow = rsiBuffer[0];
   
   for(int i = 0; i < StochLength && i < ArraySize(rsiBuffer); i++)
   {
      if(rsiBuffer[i] > rsiHigh) rsiHigh = rsiBuffer[i];
      if(rsiBuffer[i] < rsiLow) rsiLow = rsiBuffer[i];
   }
   
   double rawStoch = 0;
   if(rsiHigh - rsiLow > 0.001) // Avoid division by zero
      rawStoch = 100.0 * (rsiBuffer[0] - rsiLow) / (rsiHigh - rsiLow);
   else
      rawStoch = 50.0;
   
   //--- Shift arrays and add new value
   ArrayCopy(rawStochValues, rawStochValues, 1, 0, ArraySize(rawStochValues) - 1);
   rawStochValues[0] = rawStoch;
   
   //--- Calculate K (SMA of raw stochastic with period=6)
   double kSum = 0;
   for(int i = 0; i < KSmooth; i++)
      kSum += rawStochValues[i];
   
   double kValue = kSum / KSmooth;
   
   ArrayCopy(kValues, kValues, 1, 0, ArraySize(kValues) - 1);
   kValues[0] = kValue;
   
   stochKBuffer[0] = kValue;
   
   //--- Calculate D (SMA of K with period=6)
   double dSum = 0;
   for(int i = 0; i < DSmooth; i++)
      dSum += kValues[i];
   
   double dValue = dSum / DSmooth;
   
   ArrayCopy(dValues, dValues, 1, 0, ArraySize(dValues) - 1);
   dValues[0] = dValue;
   
   stochDBuffer[0] = dValue;
   
   //--- Store historical values
   for(int i = 1; i < MathMin(10, ArraySize(stochKBuffer)); i++)
   {
      stochKBuffer[i] = kValues[i];
      stochDBuffer[i] = dValues[i];
   }
}

//+------------------------------------------------------------------+
//| Calculate Choppiness Index (Length=14, Threshold=55)              |
//+------------------------------------------------------------------+
void CalculateChoppinessIndex()
{
   ArrayResize(chopBuffer, 3);
   
   double highestHigh = 0;
   double lowestLow = DBL_MAX;
   double sumTrueRange = 0;
   
   for(int i = 0; i < ChopLength; i++)
   {
      double high = iHigh(_Symbol, PERIOD_M1, i);
      double low = iLow(_Symbol, PERIOD_M1, i);
      double prevClose = (i + 1 < iBars(_Symbol, PERIOD_M1)) ? iClose(_Symbol, PERIOD_M1, i + 1) : low;
      
      if(high > highestHigh) highestHigh = high;
      if(low < lowestLow) lowestLow = low;
      
      // True Range calculation
      double tr = MathMax(high - low, MathMax(MathAbs(high - prevClose), MathAbs(low - prevClose)));
      sumTrueRange += tr;
   }
   
   double range = highestHigh - lowestLow;
   
   if(range > 0.0001 && sumTrueRange > 0.0001)
      chopBuffer[0] = 100.0 * MathLog10(sumTrueRange / range) / MathLog10(ChopLength);
   else
      chopBuffer[0] = 50.0; // Neutral value
}

//+------------------------------------------------------------------+
//| Update Stoch RSI entry permissions (evaluated once per bar)        |
//| LONG : K >= 75 -> ON | stays ON while K > 50 | K < 50 -> OFF       |
//| SHORT: K <= 25 -> ON | stays ON while K < 50 | K > 50 -> OFF       |
//| Permission only gates NEW entries. It is NEVER used as an exit.    |
//+------------------------------------------------------------------+
void UpdateKBasedPermissions()
{
   double stochK = stochKBuffer[0];
   
   if(UseStrictKDecision)
   {
      //--- LONG PERMISSION
      bool longJustActivated = false;
      if(stochK >= UpperBand && !longPermission)
      {
         longPermission = true;
         longPermissionBar = 0;
         longJustActivated = true;
         Print("✅ LONG PERMISSION ACTIVATED | K=", NormalizeDouble(stochK, 2), " reached/crossed ", UpperBand);
      }
      
      if(longPermission && stochK < MiddleBand)
      {
         longPermission = false;
         longPermissionBar = -999;
         Print("❌ LONG PERMISSION DEACTIVATED | K=", NormalizeDouble(stochK, 2), " dropped below ", MiddleBand);
      }
      else if(longPermission && !longJustActivated)
      {
         longPermissionBar++; // bars since permission was granted (log only)
      }
      
      //--- SHORT PERMISSION
      bool shortJustActivated = false;
      if(stochK <= LowerBand && !shortPermission)
      {
         shortPermission = true;
         shortPermissionBar = 0;
         shortJustActivated = true;
         Print("✅ SHORT PERMISSION ACTIVATED | K=", NormalizeDouble(stochK, 2), " reached/crossed ", LowerBand);
      }
      
      if(shortPermission && stochK > MiddleBand)
      {
         shortPermission = false;
         shortPermissionBar = -999;
         Print("❌ SHORT PERMISSION DEACTIVATED | K=", NormalizeDouble(stochK, 2), " rose above ", MiddleBand);
      }
      else if(shortPermission && !shortJustActivated)
      {
         shortPermissionBar++; // bars since permission was granted (log only)
      }
   }
   else
   {
      //--- Relaxed permission logic (always on)
      longPermission = true;
      shortPermission = true;
   }
}

//+------------------------------------------------------------------+
//| v6.11: Pick an order filling mode the symbol supports              |
//| Brokers differ: some allow FOK, some only IOC, some only Return.   |
//| A hard-coded FOK gives "Unsupported filling mode" on those.        |
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING GetFillingMode()
{
   long flags = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   
   if((flags & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   if((flags & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   
   return ORDER_FILLING_RETURN;
}

//+------------------------------------------------------------------+
//| v6.10: Update EMA cross memory                                     |
//| A cross counts if it happened between bar[1]->[0], OR between      |
//| bar[2]->[1] while Fast is still on the new side. The second case   |
//| catches a cross that happened on the previous bar (or where the    |
//| EMAs were equal to the cent) - a one-bar test misses it forever.   |
//+------------------------------------------------------------------+
void UpdateCrossMemory()
{
   double f0 = fastEMABuffer[0], f1 = fastEMABuffer[1], f2 = fastEMABuffer[2];
   double s0 = slowEMABuffer[0], s1 = slowEMABuffer[1], s2 = slowEMABuffer[2];
   
   //--- Forget a cross once the EMAs are no longer on that side
   if(f0 <= s0) bullCrossAge = -1;
   if(f0 >= s0) bearCrossAge = -1;
   
   //--- Age remembered crosses (9999 = already used, stays used until the side flips)
   if(bullCrossAge >= 0 && bullCrossAge < 9999) bullCrossAge++;
   if(bearCrossAge >= 0 && bearCrossAge < 9999) bearCrossAge++;
   
   bool bullNow  = (f1 <= s1 && f0 > s0);
   bool bullLate = (f2 <= s2 && f1 > s1 && f0 > s0);
   bool bearNow  = (f1 >= s1 && f0 < s0);
   bool bearLate = (f2 >= s2 && f1 < s1 && f0 < s0);
   
   bullCrossSignal = (bullNow || bullLate);
   bearCrossSignal = (bearNow || bearLate);
   
   if(bullCrossSignal && bullCrossAge < 0)
   {
      bullCrossAge = 0;
      Print("BULLISH EMA CROSS registered (", (bullNow ? "this bar" : "previous bar"), ") | Fast=",
            NormalizeDouble(f0, _Digits), " Slow=", NormalizeDouble(s0, _Digits));
   }
   if(bearCrossSignal && bearCrossAge < 0)
   {
      bearCrossAge = 0;
      Print("BEARISH EMA CROSS registered (", (bearNow ? "this bar" : "previous bar"), ") | Fast=",
            NormalizeDouble(f0, _Digits), " Slow=", NormalizeDouble(s0, _Digits));
   }
}

//+------------------------------------------------------------------+
//| v6.10: Is there a remembered bullish / bearish cross we may use?   |
//+------------------------------------------------------------------+
bool BullCrossValid()
{
   int maxAge = UseCrossMemory ? MathMax(CrossMemoryBars, 0) : 0;
   return (bullCrossAge >= 0 && bullCrossAge <= maxAge && fastEMABuffer[0] > slowEMABuffer[0]);
}

bool BearCrossValid()
{
   int maxAge = UseCrossMemory ? MathMax(CrossMemoryBars, 0) : 0;
   return (bearCrossAge >= 0 && bearCrossAge <= maxAge && fastEMABuffer[0] < slowEMABuffer[0]);
}

//+------------------------------------------------------------------+
//| v6.10: Notice when the broker closed our position (SL / trailing)  |
//| The EA only closes positions through ClosePosition(), which resets |
//| trackedPosType. If a position we tracked is gone, the server hit   |
//| its stop - remember direction so a reverse trade can be considered.|
//+------------------------------------------------------------------+
void DetectBrokerSideExit()
{
   int nowPos = GetCurrentPosition();
   
   if(trackedPosType != -1 && nowPos == -1)
   {
      stopExitType = trackedPosType;
      stopExitBar = barCounter;
      trackedPosType = -1;
      ResetTrailingStopVariables();
      Print("STOP-OUT DETECTED | ", (stopExitType == POSITION_TYPE_BUY ? "LONG" : "SHORT"),
            " closed by SL/trailing stop | reverse window: ", ReverseAfterStopBars, " bars");
   }
   else if(nowPos != -1)
   {
      trackedPosType = nowPos;
   }
}

//+------------------------------------------------------------------+
//| Check for long entry signal (EMA cross + K permission + CHOP)     |
//| v6.12: K permission = longPermission flag only (75 / 50 rule)      |
//+------------------------------------------------------------------+
bool CheckLongEntry(bool stateMode = false)
{
   Print("═══════════════════════════════════════════════════════");
   Print("🔍 LONG ENTRY ANALYSIS - CHECKING ALL CONDITIONS");
   Print("═══════════════════════════════════════════════════════");
   
   //--- EMA Crossover: Fast EMA crosses above Slow EMA
   bool emaBullishCross = stateMode ? (fastEMABuffer[0] > slowEMABuffer[0]) : BullCrossValid();
   
   Print("� CONDITION 1: EMA CROSSOVER (Fast crosses ABOVE Slow)");
   Print("   Previous Bar [1]: Fast=", NormalizeDouble(fastEMABuffer[1], _Digits), 
         " vs Slow=", NormalizeDouble(slowEMABuffer[1], _Digits),
         " | Fast ", (fastEMABuffer[1] <= slowEMABuffer[1] ? "≤" : ">"), " Slow");
   Print("   Current Bar  [0]: Fast=", NormalizeDouble(fastEMABuffer[0], _Digits), 
         " vs Slow=", NormalizeDouble(slowEMABuffer[0], _Digits),
         " | Fast ", (fastEMABuffer[0] > slowEMABuffer[0] ? ">" : "≤"), " Slow");
   Print("   ➜ EMA Bullish Cross: ", (emaBullishCross ? "✅ YES - Cross Detected!" : "❌ NO - No Cross"));
   Print("   Cross memory: age=", bullCrossAge, " bar(s), valid if 0..", (UseCrossMemory ? CrossMemoryBars : 0), " | mode: ", (stateMode ? "STATE (reverse-after-stop)" : "CROSS"));
   
   if(!emaBullishCross)
   {
      Print("═══════════════════════════════════════════════════════");
      Print("❌ LONG ENTRY REJECTED: EMA Cross NOT detected");
      Print("═══════════════════════════════════════════════════════");
      return false;
   }
   
   //--- K-based permission check (primary decision)
   double stochK = stochKBuffer[0];
   double stochD = stochDBuffer[0];
   double rsi = rsiBuffer[0];
   
   Print("───────────────────────────────────────────────────────");
   Print("📊 CONDITION 2: STOCHASTIC RSI PERMISSION (K Value)");
   Print("   RSI Value: ", NormalizeDouble(rsi, 2));
   Print("   Stochastic K: ", NormalizeDouble(stochK, 2));
   Print("   Stochastic D: ", NormalizeDouble(stochD, 2));
   Print("   Upper Band (Long Permission): ", UpperBand);
   Print("   Middle Band (Cutoff): ", MiddleBand);
   Print("   Lower Band (Short Permission): ", LowerBand);
   
   //--- Stoch RSI permission gate (state kept by UpdateKBasedPermissions)
   //--- Long allowed only after K reached >= 75 and while K has stayed > 50
   Print("   Rule: Long permission ON at K >= ", UpperBand, " | stays ON while K > ", MiddleBand, " | OFF when K < ", MiddleBand);
   
   bool kInLongZone = longPermission;
   
   Print("   • Long Permission: ", (longPermission ? "ACTIVE ✅" : "NOT ACTIVE ❌"), " [K=", NormalizeDouble(stochK, 2), "]");
   Print("   ➜ K Permission Status: ", (kInLongZone ? "✅ GRANTED" : "❌ DENIED"));
   
   if(!kInLongZone)
   {
      Print("═══════════════════════════════════════════════════════");
      Print("❌ LONG ENTRY REJECTED: Long permission NOT active");
      if(stochK < MiddleBand)
         Print("   Reason: K=", NormalizeDouble(stochK, 2), " below middle band ", MiddleBand);
      else
         Print("   Reason: K=", NormalizeDouble(stochK, 2), " has not reached ", UpperBand, " (or permission was reset)");
      Print("═══════════════════════════════════════════════════════");
      return false;
   }
   
   //--- Choppiness filter (CHOP must be <= ChopMaxEntry = 55, trending market)
   double chopValue = chopBuffer[0];
   bool chopOK = (chopValue <= ChopMaxEntry);
   
   Print("───────────────────────────────────────────────────────");
   Print("🌊 CONDITION 3: CHOPPINESS INDEX FILTER (Trending Market)");
   Print("   Choppiness Value: ", NormalizeDouble(chopValue, 2));
   Print("   Maximum for Entry: ", ChopMaxEntry);
   Print("   Market State: ", (chopValue <= ChopMaxEntry ? "TRENDING ✅" : "CHOPPY ❌"));
   Print("   ➜ Choppiness Filter: ", (chopOK ? "✅ PASSED (Market is Trending)" : "❌ FAILED (Market is Choppy)"));
   
   if(!chopOK)
   {
      Print("═══════════════════════════════════════════════════════");
      Print("❌ LONG ENTRY REJECTED: Market is CHOPPY");
      Print("   CHOP=", NormalizeDouble(chopValue, 2), " exceeds max ", ChopMaxEntry);
      Print("═══════════════════════════════════════════════════════");
      return false;
   }
   
   //--- All conditions met
   Print("═══════════════════════════════════════════════════════");
   Print("✅✅✅ ALL CONDITIONS SATISFIED - LONG ENTRY APPROVED ✅✅✅");
   Print("═══════════════════════════════════════════════════════");
   Print("� ENTRY SUMMARY:");
   Print("   1. EMA Cross: ✅ Fast (", NormalizeDouble(fastEMABuffer[0], _Digits), 
         ") crossed above Slow (", NormalizeDouble(slowEMABuffer[0], _Digits), ")");
   Print("   2. K Permission: ✅ K=", NormalizeDouble(stochK, 2), " | D=", NormalizeDouble(stochD, 2), 
         " | RSI=", NormalizeDouble(rsi, 2));
   Print("   3. Choppiness: ✅ CHOP=", NormalizeDouble(chopValue, 2), " (Trending market)");
   Print("   Long Permission: ", (longPermission ? "ACTIVE" : "Just Granted"));
   Print("═══════════════════════════════════════════════════════");
   
   return true;
}

//+------------------------------------------------------------------+
//| Check for short entry signal (EMA cross + K permission + CHOP)    |
//| v6.12: K permission = shortPermission flag only (25 / 50 rule)     |
//+------------------------------------------------------------------+
bool CheckShortEntry(bool stateMode = false)
{
   Print("═══════════════════════════════════════════════════════");
   Print("🔍 SHORT ENTRY ANALYSIS - CHECKING ALL CONDITIONS");
   Print("═══════════════════════════════════════════════════════");
   
   //--- EMA Crossover: Fast EMA crosses below Slow EMA
   bool emaBearishCross = stateMode ? (fastEMABuffer[0] < slowEMABuffer[0]) : BearCrossValid();
   
   Print("� CONDITION 1: EMA CROSSOVER (Fast crosses BELOW Slow)");
   Print("   Previous Bar [1]: Fast=", NormalizeDouble(fastEMABuffer[1], _Digits), 
         " vs Slow=", NormalizeDouble(slowEMABuffer[1], _Digits),
         " | Fast ", (fastEMABuffer[1] >= slowEMABuffer[1] ? "≥" : "<"), " Slow");
   Print("   Current Bar  [0]: Fast=", NormalizeDouble(fastEMABuffer[0], _Digits), 
         " vs Slow=", NormalizeDouble(slowEMABuffer[0], _Digits),
         " | Fast ", (fastEMABuffer[0] < slowEMABuffer[0] ? "<" : "≥"), " Slow");
   Print("   ➜ EMA Bearish Cross: ", (emaBearishCross ? "✅ YES - Cross Detected!" : "❌ NO - No Cross"));
   Print("   Cross memory: age=", bearCrossAge, " bar(s), valid if 0..", (UseCrossMemory ? CrossMemoryBars : 0), " | mode: ", (stateMode ? "STATE (reverse-after-stop)" : "CROSS"));
   
   if(!emaBearishCross)
   {
      Print("═══════════════════════════════════════════════════════");
      Print("❌ SHORT ENTRY REJECTED: EMA Cross NOT detected");
      Print("═══════════════════════════════════════════════════════");
      return false;
   }
   
   //--- K-based permission check (primary decision)
   double stochK = stochKBuffer[0];
   double stochD = stochDBuffer[0];
   double rsi = rsiBuffer[0];
   
   Print("───────────────────────────────────────────────────────");
   Print("📊 CONDITION 2: STOCHASTIC RSI PERMISSION (K Value)");
   Print("   RSI Value: ", NormalizeDouble(rsi, 2));
   Print("   Stochastic K: ", NormalizeDouble(stochK, 2));
   Print("   Stochastic D: ", NormalizeDouble(stochD, 2));
   Print("   Upper Band (Long Permission): ", UpperBand);
   Print("   Middle Band (Cutoff): ", MiddleBand);
   Print("   Lower Band (Short Permission): ", LowerBand);
   
   //--- Stoch RSI permission gate (state kept by UpdateKBasedPermissions)
   //--- Short allowed only after K reached <= 25 and while K has stayed < 50
   Print("   Rule: Short permission ON at K <= ", LowerBand, " | stays ON while K < ", MiddleBand, " | OFF when K > ", MiddleBand);
   
   bool kInShortZone = shortPermission;
   
   Print("   • Short Permission: ", (shortPermission ? "ACTIVE ✅" : "NOT ACTIVE ❌"), " [K=", NormalizeDouble(stochK, 2), "]");
   Print("   ➜ K Permission Status: ", (kInShortZone ? "✅ GRANTED" : "❌ DENIED"));
   
   if(!kInShortZone)
   {
      Print("═══════════════════════════════════════════════════════");
      Print("❌ SHORT ENTRY REJECTED: Short permission NOT active");
      if(stochK > MiddleBand)
         Print("   Reason: K=", NormalizeDouble(stochK, 2), " above middle band ", MiddleBand);
      else
         Print("   Reason: K=", NormalizeDouble(stochK, 2), " has not reached ", LowerBand, " (or permission was reset)");
      Print("═══════════════════════════════════════════════════════");
      return false;
   }
   
   //--- Choppiness filter (CHOP must be <= ChopMaxEntry = 55, trending market)
   double chopValue = chopBuffer[0];
   bool chopOK = (chopValue <= ChopMaxEntry);
   
   Print("───────────────────────────────────────────────────────");
   Print("🌊 CONDITION 3: CHOPPINESS INDEX FILTER (Trending Market)");
   Print("   Choppiness Value: ", NormalizeDouble(chopValue, 2));
   Print("   Maximum for Entry: ", ChopMaxEntry);
   Print("   Market State: ", (chopValue <= ChopMaxEntry ? "TRENDING ✅" : "CHOPPY ❌"));
   Print("   ➜ Choppiness Filter: ", (chopOK ? "✅ PASSED (Market is Trending)" : "❌ FAILED (Market is Choppy)"));
   
   if(!chopOK)
   {
      Print("═══════════════════════════════════════════════════════");
      Print("❌ SHORT ENTRY REJECTED: Market is CHOPPY");
      Print("   CHOP=", NormalizeDouble(chopValue, 2), " exceeds max ", ChopMaxEntry);
      Print("═══════════════════════════════════════════════════════");
      return false;
   }
   
   //--- All conditions met
   Print("═══════════════════════════════════════════════════════");
   Print("✅✅✅ ALL CONDITIONS SATISFIED - SHORT ENTRY APPROVED ✅✅✅");
   Print("═══════════════════════════════════════════════════════");
   Print("� ENTRY SUMMARY:");
   Print("   1. EMA Cross: ✅ Fast (", NormalizeDouble(fastEMABuffer[0], _Digits), 
         ") crossed below Slow (", NormalizeDouble(slowEMABuffer[0], _Digits), ")");
   Print("   2. K Permission: ✅ K=", NormalizeDouble(stochK, 2), " | D=", NormalizeDouble(stochD, 2), 
         " | RSI=", NormalizeDouble(rsi, 2));
   Print("   3. Choppiness: ✅ CHOP=", NormalizeDouble(chopValue, 2), " (Trending market)");
   Print("   Short Permission: ", (shortPermission ? "ACTIVE" : "Just Granted"));
   Print("═══════════════════════════════════════════════════════");
   
   return true;
}

//+------------------------------------------------------------------+
//| Check for exit signal (opposite EMA cross)                        |
//+------------------------------------------------------------------+
bool CheckExitSignal(int posType)
{
   if(!ExitOnOppositeEMA) return false;
   
   Print("═══════════════════════════════════════════════════════");
   Print("� EXIT SIGNAL ANALYSIS - EMA CROSS CHECK");
   Print("═══════════════════════════════════════════════════════");
   Print("📊 Current Position: ", (posType == POSITION_TYPE_BUY ? "LONG" : "SHORT"));
   
   // Get current position details for comprehensive logging
   double currentProfit = 0;
   double currentSL = 0;
   double entryPrice = 0;
   double currentPrice = 0;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            currentProfit = PositionGetDouble(POSITION_PROFIT);
            currentSL = PositionGetDouble(POSITION_SL);
            entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            currentPrice = (posType == POSITION_TYPE_BUY) ? 
                          SymbolInfoDouble(_Symbol, SYMBOL_BID) : 
                          SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            break;
         }
      }
   }
   
   Print("📈 Position Status:");
   Print("   Entry Price: ", NormalizeDouble(entryPrice, _Digits));
   Print("   Current Price: ", NormalizeDouble(currentPrice, _Digits));
   Print("   Current P/L: $", NormalizeDouble(currentProfit, 2));
   Print("   Current SL: ", NormalizeDouble(currentSL, _Digits));
   Print("   Highest Profit: $", NormalizeDouble(highestProfit, 2));
   
   Print("───────────────────────────────────────────────────────");
   Print("📉 EMA Crossover Analysis:");
   Print("   Previous Bar [1]: Fast=", NormalizeDouble(fastEMABuffer[1], _Digits), 
         " vs Slow=", NormalizeDouble(slowEMABuffer[1], _Digits));
   Print("   Current Bar  [0]: Fast=", NormalizeDouble(fastEMABuffer[0], _Digits), 
         " vs Slow=", NormalizeDouble(slowEMABuffer[0], _Digits));
   
   //--- Long position: exit on bearish EMA cross
   if(posType == POSITION_TYPE_BUY)
   {
      bool bearishCross = bearCrossSignal; // v6.10: 2-bar cross detection
      
      Print("   Looking for: BEARISH Cross (Fast crosses BELOW Slow)");
      Print("   Previous: Fast ", (fastEMABuffer[1] >= slowEMABuffer[1] ? "≥" : "<"), " Slow");
      Print("   Current: Fast ", (fastEMABuffer[0] < slowEMABuffer[0] ? "<" : "≥"), " Slow");
      Print("   ➜ Bearish Cross Detected: ", (bearishCross ? "✅ YES" : "❌ NO"));
      
      if(bearishCross)
      {
         Print("═══════════════════════════════════════════════════════");
         Print("🚨 EXIT SIGNAL CONFIRMED - EMA BEARISH CROSS");
         Print("═══════════════════════════════════════════════════════");
         Print("📋 EXIT REASON: Fast EMA crossed below Slow EMA");
         Print("   Entry: ", NormalizeDouble(entryPrice, _Digits));
         Print("   Exit: ", NormalizeDouble(currentPrice, _Digits));
         Print("   P/L: $", NormalizeDouble(currentProfit, 2));
         Print("═══════════════════════════════════════════════════════");
      }
      else
      {
         Print("═══════════════════════════════════════════════════════");
         Print("✋ NO EXIT - EMA Cross not detected, position remains open");
         Print("═══════════════════════════════════════════════════════");
      }
      
      return bearishCross;
   }
   
   //--- Short position: exit on bullish EMA cross
   if(posType == POSITION_TYPE_SELL)
   {
      bool bullishCross = bullCrossSignal; // v6.10: 2-bar cross detection
      
      Print("   Looking for: BULLISH Cross (Fast crosses ABOVE Slow)");
      Print("   Previous: Fast ", (fastEMABuffer[1] <= slowEMABuffer[1] ? "≤" : ">"), " Slow");
      Print("   Current: Fast ", (fastEMABuffer[0] > slowEMABuffer[0] ? ">" : "≤"), " Slow");
      Print("   ➜ Bullish Cross Detected: ", (bullishCross ? "✅ YES" : "❌ NO"));
      
      if(bullishCross)
      {
         Print("═══════════════════════════════════════════════════════");
         Print("🚨 EXIT SIGNAL CONFIRMED - EMA BULLISH CROSS");
         Print("═══════════════════════════════════════════════════════");
         Print("📋 EXIT REASON: Fast EMA crossed above Slow EMA");
         Print("   Entry: ", NormalizeDouble(entryPrice, _Digits));
         Print("   Exit: ", NormalizeDouble(currentPrice, _Digits));
         Print("   P/L: $", NormalizeDouble(currentProfit, 2));
         Print("═══════════════════════════════════════════════════════");
      }
      else
      {
         Print("═══════════════════════════════════════════════════════");
         Print("✋ NO EXIT - EMA Cross not detected, position remains open");
         Print("═══════════════════════════════════════════════════════");
      }
      
      return bullishCross;
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| Get current position type                                          |
//+------------------------------------------------------------------+
int GetCurrentPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            return (int)PositionGetInteger(POSITION_TYPE);
         }
      }
   }
   return -1;
}

//+------------------------------------------------------------------+
//| Open a position with fixed $50 stop loss                          |
//+------------------------------------------------------------------+
void OpenPosition(ENUM_ORDER_TYPE orderType)
{
   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);
   
   double price = (orderType == ORDER_TYPE_BUY) ? 
                  SymbolInfoDouble(_Symbol, SYMBOL_ASK) : 
                  SymbolInfoDouble(_Symbol, SYMBOL_BID);
   
   //--- SIMPLIFIED: Calculate stop loss to lose exactly $50
   //--- For XAUUSD: 1 lot = $100 per $1 move
   //--- Example: 0.10 lots = $10 per $1 move
   //--- To lose $50 with 0.10 lots, need $5 price move (50 / 10 = 5)
   
   double dollarValuePerLot = 100.0; // Standard for XAUUSD (1 lot = $100 per $1)
   double dollarValueForPosition = dollarValuePerLot * LotSize; // e.g., 0.10 * 100 = $10 per $1
   
   // How many dollars of price movement to lose $FixedStopLoss?
   double priceDistanceNeeded = FixedStopLoss / dollarValueForPosition; // e.g., 50 / 10 = 5.0
   
   double sl = 0;
   if(priceDistanceNeeded > 0)
   {
      if(orderType == ORDER_TYPE_BUY)
         sl = NormalizeDouble(price - priceDistanceNeeded, _Digits);
      else
         sl = NormalizeDouble(price + priceDistanceNeeded, _Digits);
      
      Print("💡 SIMPLIFIED SL Calculation:");
      Print("   Lot Size: ", LotSize);
      Print("   $ per $1 move: $", NormalizeDouble(dollarValueForPosition, 2));
      Print("   Target Loss: $", FixedStopLoss);
      Print("   Price Distance: $", NormalizeDouble(priceDistanceNeeded, 2));
      Print("   Entry: ", NormalizeDouble(price, _Digits));
      Print("   Stop Loss: ", NormalizeDouble(sl, _Digits));
      
      // Verify with broker minimum
      double minStopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
      double actualDistance = MathAbs(price - sl);
      
      if(minStopLevel > 0 && actualDistance < minStopLevel)
      {
         Print("⚠️ WARNING: Broker requires minimum ", NormalizeDouble(minStopLevel, _Digits), 
               " distance, but calculated ", NormalizeDouble(actualDistance, _Digits));
         Print("⚠️ Adjusting to broker minimum (loss may exceed $", FixedStopLoss, ")");
         
         if(orderType == ORDER_TYPE_BUY)
            sl = NormalizeDouble(price - minStopLevel, _Digits);
         else
            sl = NormalizeDouble(price + minStopLevel, _Digits);
      }
   }
   else
   {
      Print("❌ ERROR: Cannot calculate SL. Lot size may be 0 or invalid.");
   }
   
   //--- Prepare request
   request.action = TRADE_ACTION_DEAL;
   request.symbol = _Symbol;
   request.volume = LotSize;
   request.type = orderType;
   request.price = price;
   request.sl = sl;  // CRITICAL: This SL is set on BROKER SERVER - triggers automatically
   request.tp = 0; // No take profit, exit on signal
   request.deviation = 10;
   request.magic = MagicNumber;
   request.comment = "v6 K-Decision";
   request.type_filling = GetFillingMode(); // v6.11: use a filling mode the broker/symbol actually supports
   
   //--- CRITICAL VALIDATION: Verify SL is actually set before sending
   if(sl <= 0 || MathAbs(price - sl) < 0.01)
   {
      Print("❌ CRITICAL ERROR: Stop Loss not calculated properly!");
      Print("   Price: ", NormalizeDouble(price, _Digits));
      Print("   SL: ", NormalizeDouble(sl, _Digits));
      Print("   Distance: ", NormalizeDouble(MathAbs(price - sl), 2));
      Print("   ABORTING TRADE - Fix SL calculation first!");
      return; // DON'T open position without valid SL
   }
   
   Print("🔍 Final Order Details:");
   Print("   Type: ", (orderType == ORDER_TYPE_BUY ? "BUY" : "SELL"));
   Print("   Price: ", NormalizeDouble(price, _Digits));
   Print("   Volume: ", LotSize);
   Print("   Stop Loss: ", NormalizeDouble(sl, _Digits));
   Print("   Expected Loss if SL hit: $", FixedStopLoss);
   
   //--- Send order
   if(OrderSend(request, result))
   {
      if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
      {
         // Verify the position was opened and SL is set
         Sleep(200); // Wait for position to register on server
         
         bool foundPosition = false;
         for(int i = PositionsTotal() - 1; i >= 0; i--)
         {
            ulong ticket = PositionGetTicket(i);
            if(PositionSelectByTicket(ticket))
            {
               if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
                  PositionGetInteger(POSITION_MAGIC) == MagicNumber)
               {
                  foundPosition = true;
                  double actualSL = PositionGetDouble(POSITION_SL);
                  double actualPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                  double actualVolume = PositionGetDouble(POSITION_VOLUME);
                  
                  // Initialize trailing stop variables
                  positionEntryPrice = actualPrice;
                  currentTrailingSL = actualSL;
                  highestProfit = 0;
                  trailingStopActive = true;
                  
                  // v6.10: track position, clear stop-out window, mark the cross as used
                  trackedPosType = (orderType == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
                  stopExitType = -1;
                  if(orderType == ORDER_TYPE_BUY) bullCrossAge = 9999; else bearCrossAge = 9999;
               
                  Print("═══════════════════════════════════════════════");
                  Print("✅ POSITION OPENED SUCCESSFULLY");
                  Print("═══════════════════════════════════════════════");
                  Print("📊 Type: ", (orderType == ORDER_TYPE_BUY ? "BUY" : "SELL"));
                  Print("💰 Entry Price: ", NormalizeDouble(actualPrice, _Digits));
                  Print("🛑 Initial Stop Loss: ", NormalizeDouble(actualSL, _Digits), " (Maximum -$", FixedStopLoss, ")");
                  Print("📏 SL Distance: $", NormalizeDouble(MathAbs(actualPrice - actualSL), 2));
                  Print("📦 Volume: ", actualVolume, " lots");
                  Print("🎫 Ticket: ", ticket);
                  Print("📈 Progressive Trailing: ACTIVE");
                  Print("───────────────────────────────────────────────");
                  
                  // CRITICAL VERIFICATION: Check if SL was actually set on broker
                  if(actualSL <= 0.0001)
                  {
                     Print("❌❌❌ CRITICAL ERROR ❌❌❌");
                     Print("❌ STOP LOSS WAS NOT SET ON BROKER SERVER!");
                     Print("❌ Position is UNPROTECTED!");
                     Print("❌ Manual intervention required - set SL manually!");
                     Print("❌ Or close position immediately!");
                     Print("═══════════════════════════════════════════════");
                  }
                  else
                  {
                     // Calculate expected loss
                     double expectedLoss = MathAbs(actualPrice - actualSL) * actualVolume * 100.0;
                     Print("✅ Stop Loss CONFIRMED active on broker server");
                     Print("✅ Expected loss if SL hit: $", NormalizeDouble(expectedLoss, 2));
                     Print("✅ Target loss: $", FixedStopLoss);
                     
                     if(MathAbs(expectedLoss - FixedStopLoss) > FixedStopLoss * 0.15)
                     {
                        Print("⚠️ WARNING: Calculated loss ($", NormalizeDouble(expectedLoss, 2), 
                              ") differs from target ($", FixedStopLoss, ") by >15%");
                     }
                     Print("═══════════════════════════════════════════════");
                  }
                  break;
               }
            }
         }
         
         if(!foundPosition)
         {
            Print("⚠️ WARNING: Position opened but could not verify in terminal");
         }
      }
      else
      {
         Print("❌ ORDER WARNING: Return code ", result.retcode, " - ", result.comment);
      }
   }
   else
   {
      Print("❌ ERROR OPENING POSITION: ", GetLastError(), " - ", result.comment);
      
      // Try to diagnose the problem
      Print("🔍 Diagnosis:");
      Print("   Requested Price: ", NormalizeDouble(price, _Digits));
      Print("   Requested SL: ", NormalizeDouble(sl, _Digits));
      Print("   SL Distance: $", NormalizeDouble(MathAbs(price - sl), 2));
      Print("   Volume: ", LotSize);
      
      // Check if it's a broker restriction
      double minStop = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
      if(minStop > 0)
      {
         Print("   Broker Min Stop: $", NormalizeDouble(minStop, 2));
         if(MathAbs(price - sl) < minStop)
         {
            Print("   ❌ SL too close! Increase FixedStopLoss parameter");
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Close current position with detailed exit analysis                |
//+------------------------------------------------------------------+
void ClosePosition(string reason)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            // Get position details before closing
            double profit = PositionGetDouble(POSITION_PROFIT);
            double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            double posVolume = PositionGetDouble(POSITION_VOLUME);
            double currentSL = PositionGetDouble(POSITION_SL);
            datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
            datetime currentTime = TimeCurrent();
            int tradeDurationSeconds = (int)(currentTime - openTime);
            int tradeDurationMinutes = tradeDurationSeconds / 60;
            
            // Get current indicator values at exit
            double exitStochK = stochKBuffer[0];
            double exitStochD = stochDBuffer[0];
            double exitRSI = rsiBuffer[0];
            double exitCHOP = chopBuffer[0];
            double exitFastEMA = fastEMABuffer[0];
            double exitSlowEMA = slowEMABuffer[0];
            
            MqlTradeRequest request;
            MqlTradeResult result;
            ZeroMemory(request);
            ZeroMemory(result);
            
            request.action = TRADE_ACTION_DEAL;
            request.position = ticket;
            request.symbol = _Symbol;
            request.volume = posVolume;
            request.type = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            request.price = (request.type == ORDER_TYPE_SELL) ? 
                           SymbolInfoDouble(_Symbol, SYMBOL_BID) : 
                           SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            request.deviation = 10;
            request.magic = MagicNumber;
            request.comment = reason;
            request.type_filling = GetFillingMode(); // v6.11
            
            if(OrderSend(request, result))
            {
               double closePrice = request.price;
               double priceMove = closePrice - openPrice;
               double priceMoveAbs = MathAbs(priceMove);
               
               Print("═══════════════════════════════════════════════════════");
               Print("🚪 POSITION CLOSED - DETAILED EXIT REPORT");
               Print("═══════════════════════════════════════════════════════");
               Print("� EXIT INFORMATION:");
               Print("   Ticket #: ", ticket);
               Print("   Position Type: ", (posType == POSITION_TYPE_BUY ? "LONG" : "SHORT"));
               Print("   Exit Reason: ", reason);
               Print("───────────────────────────────────────────────────────");
               Print("💰 PRICE & PROFIT DETAILS:");
               Print("   Entry Price: ", NormalizeDouble(openPrice, _Digits));
               Print("   Exit Price: ", NormalizeDouble(closePrice, _Digits));
               Print("   Price Movement: ", (priceMove > 0 ? "+" : ""), NormalizeDouble(priceMove, _Digits), 
                     " ($", NormalizeDouble(priceMoveAbs, 2), ")");
               Print("   Final P/L: ", (profit >= 0 ? "+" : ""), "$", NormalizeDouble(profit, 2));
               Print("   Highest Profit Reached: $", NormalizeDouble(highestProfit, 2));
               if(highestProfit > profit + 10)
               {
                  Print("   ⚠️ Gave back: $", NormalizeDouble(highestProfit - profit, 2), 
                        " from highest profit");
               }
               Print("───────────────────────────────────────────────────────");
               Print("⏱️ TIMING INFORMATION:");
               Print("   Entry Time: ", TimeToString(openTime, TIME_DATE|TIME_MINUTES|TIME_SECONDS));
               Print("   Exit Time: ", TimeToString(currentTime, TIME_DATE|TIME_MINUTES|TIME_SECONDS));
               Print("   Trade Duration: ", tradeDurationMinutes, " minutes (", tradeDurationSeconds, " seconds)");
               Print("───────────────────────────────────────────────────────");
               Print("📊 STOP LOSS INFORMATION:");
               Print("   Initial SL Target: -$", FixedStopLoss);
               Print("   Final SL Price: ", NormalizeDouble(currentSL, _Digits));
               Print("   SL Distance from Entry: $", NormalizeDouble(MathAbs(openPrice - currentSL), 2));
               if(profit > 0 && currentSL != 0)
               {
                  double slProfitLevel = (currentSL - openPrice) * posVolume * 100.0;
                  if(posType == POSITION_TYPE_SELL)
                     slProfitLevel = (openPrice - currentSL) * posVolume * 100.0;
                  Print("   SL Profit Level: $", NormalizeDouble(slProfitLevel, 2));
               }
               Print("   Trailing Stop Status: ", (trailingStopActive ? "WAS ACTIVE" : "NOT ACTIVE"));
               Print("───────────────────────────────────────────────────────");
               Print("📈 EXIT INDICATORS STATE:");
               Print("   Fast EMA: ", NormalizeDouble(exitFastEMA, _Digits));
               Print("   Slow EMA: ", NormalizeDouble(exitSlowEMA, _Digits));
               Print("   EMA Status: Fast ", (exitFastEMA > exitSlowEMA ? "ABOVE ▲" : "BELOW ▼"), " Slow");
               Print("   Stochastic K: ", NormalizeDouble(exitStochK, 2));
               Print("   Stochastic D: ", NormalizeDouble(exitStochD, 2));
               Print("   RSI: ", NormalizeDouble(exitRSI, 2));
               Print("   Choppiness: ", NormalizeDouble(exitCHOP, 2), 
                     (exitCHOP <= ChopMaxEntry ? " (Trending)" : " (Choppy)"));
               Print("───────────────────────────────────────────────────────");
               Print("✅ EXIT COMPLETED SUCCESSFULLY");
               
               // Determine exit method for final summary
               string exitMethod = "UNKNOWN";
               if(StringFind(reason, "EMA Cross") >= 0)
                  exitMethod = "EMA CROSSOVER SIGNAL";
               else if(StringFind(reason, "Trailing") >= 0 || StringFind(reason, "SL") >= 0)
                  exitMethod = "TRAILING STOP LOSS HIT";
               else if(StringFind(reason, "Manual") >= 0)
                  exitMethod = "MANUAL EXIT";
               
               Print("📌 EXIT METHOD: ", exitMethod);
               Print("═══════════════════════════════════════════════════════");
                     
               // WARNING: If loss exceeds fixed SL amount
               if(profit < 0 && MathAbs(profit) > FixedStopLoss * 1.1)
               {
                  Print("⚠️⚠️⚠️ WARNING: STOP LOSS ISSUE ⚠️⚠️⚠️");
                  Print("   Actual loss: $", NormalizeDouble(MathAbs(profit), 2));
                  Print("   Target loss: $", FixedStopLoss);
                  Print("   Exceeded by: ", NormalizeDouble((MathAbs(profit) - FixedStopLoss) / FixedStopLoss * 100, 1), "%");
                  Print("   Possible slippage or SL execution delay");
                  Print("═══════════════════════════════════════════════════════");
               }
            }
            else
            {
               Print("═══════════════════════════════════════════════════════");
               Print("❌ ERROR CLOSING POSITION");
               Print("═══════════════════════════════════════════════════════");
               Print("   Error Code: ", GetLastError());
               Print("   Error Message: ", result.comment);
               Print("   Ticket: ", ticket);
               Print("═══════════════════════════════════════════════════════");
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Update Progressive Profit-Based Trailing Stop                     |
//| Formula:                                                            |
//| - Profit $50  → SL = $0 (breakeven)                               |
//| - Profit $100 → SL = +$30                                         |
//| - Every +$50 profit → +$30 SL increase                            |
//| - SL can ONLY move in favorable direction (never backward)        |
//+------------------------------------------------------------------+
void UpdateProgressiveTrailingStop(int posType)
{
   if(!trailingStopActive) return;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            double currentProfit = PositionGetDouble(POSITION_PROFIT);
            double currentSL = PositionGetDouble(POSITION_SL);
            double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            double currentPrice = (posType == POSITION_TYPE_BUY) ? 
                                 SymbolInfoDouble(_Symbol, SYMBOL_BID) : 
                                 SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double volume = PositionGetDouble(POSITION_VOLUME);
            
            // Track highest profit
            if(currentProfit > highestProfit)
            {
               highestProfit = currentProfit;
            }
            
            //--- Calculate target SL profit based on current profit
            double targetSLProfit = -FixedStopLoss; // Initial: -$50
            
            if(currentProfit >= 50.0)
            {
               // Profit reached $50 → SL = $0
               targetSLProfit = 0.0;
               
               if(currentProfit >= 100.0)
               {
                  // Every $50 beyond $50 adds $30 to SL profit
                  // Profit $100 → SL +$30, $150 → SL +$60, $200 → SL +$90, etc.
                  double profitAbove50 = currentProfit - 50.0;
                  int profitSteps = (int)(profitAbove50 / 50.0);
                  targetSLProfit = profitSteps * 30.0;
               }
            }
            
            //--- Convert target SL profit to SL price
            // For LONG: SL price = Entry + (targetSLProfit / (volume * $100))
            // For SHORT: SL price = Entry - (targetSLProfit / (volume * $100))
            double dollarValuePerLot = 100.0; // XAUUSD standard
            double dollarValueForPosition = dollarValuePerLot * volume;
            
            double newSL = 0;
            if(posType == POSITION_TYPE_BUY)
            {
               // LONG: SL moves upward in price
               newSL = openPrice + (targetSLProfit / dollarValueForPosition);
               newSL = NormalizeDouble(newSL, _Digits);
               
               // Only update if new SL is higher than current (never move backward)
               if(newSL > currentSL)
               {
                  Print("═══════════════════════════════════════════════════════");
                  Print("📈 TRAILING STOP UPDATE - LONG POSITION");
                  Print("═══════════════════════════════════════════════════════");
                  Print("💰 Profit Information:");
                  Print("   Current Profit: $", NormalizeDouble(currentProfit, 2));
                  Print("   Highest Profit: $", NormalizeDouble(highestProfit, 2));
                  Print("   Entry Price: ", NormalizeDouble(openPrice, _Digits));
                  Print("   Current Price: ", NormalizeDouble(currentPrice, _Digits));
                  Print("───────────────────────────────────────────────────────");
                  Print("🎯 Trailing Stop Logic:");
                  Print("   Target SL Profit: $", NormalizeDouble(targetSLProfit, 2));
                  
                  // Show which profit level triggered this update
                  if(targetSLProfit == 0)
                     Print("   Trigger Level: $50 profit → Breakeven ($0)");
                  else if(targetSLProfit == 30)
                     Print("   Trigger Level: $100 profit → SL +$30");
                  else if(targetSLProfit == 60)
                     Print("   Trigger Level: $150 profit → SL +$60");
                  else if(targetSLProfit == 90)
                     Print("   Trigger Level: $200 profit → SL +$90");
                  else if(targetSLProfit >= 120)
                     Print("   Trigger Level: $", NormalizeDouble(50 + ((targetSLProfit / 30) * 50), 0), 
                           " profit → SL +$", NormalizeDouble(targetSLProfit, 2));
                  
                  Print("───────────────────────────────────────────────────────");
                  Print("🛑 Stop Loss Adjustment:");
                  Print("   Old SL: ", NormalizeDouble(currentSL, _Digits));
                  Print("   New SL: ", NormalizeDouble(newSL, _Digits));
                  Print("   SL Price Move: +$", NormalizeDouble(newSL - currentSL, 2));
                  Print("   SL Protection: Locks in $", NormalizeDouble(targetSLProfit, 2), " profit");
                  Print("═══════════════════════════════════════════════════════");
                  
                  ModifyPosition(ticket, newSL, 0);
                  currentTrailingSL = newSL;
               }
            }
            else if(posType == POSITION_TYPE_SELL)
            {
               // SHORT: SL moves downward in price
               newSL = openPrice - (targetSLProfit / dollarValueForPosition);
               newSL = NormalizeDouble(newSL, _Digits);
               
               // Only update if new SL is lower than current (never move backward)
               if(newSL < currentSL || currentSL == 0)
               {
                  Print("═══════════════════════════════════════════════════════");
                  Print("📉 TRAILING STOP UPDATE - SHORT POSITION");
                  Print("═══════════════════════════════════════════════════════");
                  Print("💰 Profit Information:");
                  Print("   Current Profit: $", NormalizeDouble(currentProfit, 2));
                  Print("   Highest Profit: $", NormalizeDouble(highestProfit, 2));
                  Print("   Entry Price: ", NormalizeDouble(openPrice, _Digits));
                  Print("   Current Price: ", NormalizeDouble(currentPrice, _Digits));
                  Print("───────────────────────────────────────────────────────");
                  Print("🎯 Trailing Stop Logic:");
                  Print("   Target SL Profit: $", NormalizeDouble(targetSLProfit, 2));
                  
                  // Show which profit level triggered this update
                  if(targetSLProfit == 0)
                     Print("   Trigger Level: $50 profit → Breakeven ($0)");
                  else if(targetSLProfit == 30)
                     Print("   Trigger Level: $100 profit → SL +$30");
                  else if(targetSLProfit == 60)
                     Print("   Trigger Level: $150 profit → SL +$60");
                  else if(targetSLProfit == 90)
                     Print("   Trigger Level: $200 profit → SL +$90");
                  else if(targetSLProfit >= 120)
                     Print("   Trigger Level: $", NormalizeDouble(50 + ((targetSLProfit / 30) * 50), 0), 
                           " profit → SL +$", NormalizeDouble(targetSLProfit, 2));
                  
                  Print("───────────────────────────────────────────────────────");
                  Print("🛑 Stop Loss Adjustment:");
                  Print("   Old SL: ", NormalizeDouble(currentSL, _Digits));
                  Print("   New SL: ", NormalizeDouble(newSL, _Digits));
                  Print("   SL Price Move: -$", NormalizeDouble(MathAbs(newSL - currentSL), 2));
                  Print("   SL Protection: Locks in $", NormalizeDouble(targetSLProfit, 2), " profit");
                  Print("═══════════════════════════════════════════════════════");
                  
                  ModifyPosition(ticket, newSL, 0);
                  currentTrailingSL = newSL;
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Reset trailing stop variables                                      |
//+------------------------------------------------------------------+
void ResetTrailingStopVariables()
{
   positionEntryPrice = 0;
   currentTrailingSL = 0;
   highestProfit = 0;
   trailingStopActive = false;
   
   Print("🔄 Trailing stop variables reset");
}

//+------------------------------------------------------------------+
//| Modify position SL/TP                                              |
//+------------------------------------------------------------------+
void ModifyPosition(ulong ticket, double sl, double tp)
{
   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);
   
   request.action = TRADE_ACTION_SLTP;
   request.position = ticket;
   request.symbol = _Symbol;
   request.sl = sl;
   request.tp = tp;
   
   if(OrderSend(request, result))
   {
      if(result.retcode == TRADE_RETCODE_DONE)
      {
         Print("✅ Stop Loss modified successfully to ", NormalizeDouble(sl, _Digits));
      }
      else
      {
         Print("⚠️ Modify warning: ", result.retcode, " - ", result.comment);
      }
   }
   else
   {
      Print("❌ Error modifying position: ", GetLastError(), " - ", result.comment);
   }
}

//+------------------------------------------------------------------+
//| Check if current time is within trading session                   |
//+------------------------------------------------------------------+
bool IsInTradingSession()
{
   MqlDateTime currentTime;
   TimeToStruct(TimeCurrent(), currentTime);
   
   int currentHour = currentTime.hour;
   
   if(SessionStartHour <= SessionEndHour)
   {
      return (currentHour >= SessionStartHour && currentHour < SessionEndHour);
   }
   else
   {
      // Handle overnight sessions (e.g., 22:00 to 06:00)
      return (currentHour >= SessionStartHour || currentHour < SessionEndHour);
   }
}
//+------------------------------------------------------------------+
