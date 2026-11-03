//+------------------------------------------------------------------+
//|                    XAUUSD_10S_Strategy_v6_14_StrictCross_sl50.mq5 |
//|                                                                  |
//|   XAUUSD 10-second strategy                                      |
//|   Stoch RSI (RSI 28, Stoch 28, K 6, D 6) + EMA 20/50 cross       |
//|   Stop loss -$50 | Exit on opposite EMA cross only               |
//+------------------------------------------------------------------+
#property copyright "Optimized Strategy v6"
#property link      ""
#property version   "7.00"
#property description "10-second bars are built inside the EA from ticks (MT5 has no native 10s chart)"
#property description "Entry: fresh EMA 20/50 cross + Stoch RSI K permission (75 / 50 / 25 rule)"
#property description "Stop loss: fixed -$50 | Exit: opposite EMA cross (exit + opposite entry in the same instant)"
#property description "No trailing stop, no Choppiness filter"

//--- Capital & Risk Management
input group "Capital & Risk Management"
input double InitialCapital = 1000.0;      // Initial Capital ($)
input double FixedStopLoss = 50.0;         // Stop Loss per trade ($) - fixed, no trailing
input double LotSize = 0.10;               // Lot Size
input int MagicNumber = 123456;            // Magic Number

//--- Timeframe
input group "Timeframe (built from ticks)"
input int BarSeconds = 10;                 // Bar length in seconds (10 = 10-second chart)
input int WarmupMinutes = 120;             // Minutes of tick history used to pre-fill bars at start

//--- EMA Settings
input group "EMA Trend Settings"
input int FastEMA = 20;                    // Fast EMA Period
input int SlowEMA = 50;                    // Slow EMA Period

//--- Stochastic RSI Settings
input group "Stochastic RSI Settings"
input int RSILength = 28;                  // RSI Length
input int StochLength = 28;                // Stochastic Length
input int KSmooth = 6;                     // K Smooth Period
input int DSmooth = 6;                     // D Smooth Period
input double UpperBand = 75.0;             // Upper Band - Long Permission (K >= 75)
input double LowerBand = 25.0;             // Lower Band - Short Permission (K <= 25)
input double MiddleBand = 50.0;            // Middle Band - Permission Reset

//--- Trading Permissions
input group "Trading Permissions"
input bool AllowLong = true;               // Allow Long Positions
input bool AllowShort = true;              // Allow Short Positions
input bool AllowFlip = true;               // Exit + enter opposite trade in the same instant
input bool UseStrictKDecision = true;      // Use Strict K-Value Decision Making

//--- Session Filter (Optional)
input group "Session Filter (Optional)"
input bool UseSessionFilter = false;       // Enable Session Filter
input int SessionStartHour = 0;            // Session Start Hour (0-23)
input int SessionEndHour = 23;             // Session End Hour (0-23)

//--- Logging
input group "Logging"
input bool VerboseLog = false;             // Print one status line for every 10s bar

//--- Constants
#define MAX_BARS 600      // completed bars kept in memory
#define MIN_BARS 300      // bars needed before trading (indicator warm-up)

//--- 10-second bar storage (completed bars, oldest first)
double closes[];
int    barCount = 0;
datetime curBarTime = 0;  // start time of the bar that is forming now
double curClose = 0;      // last price of the forming bar

//--- Indicator values (index 0 = last completed bar, 1 = the one before, ...)
double fastE[4], slowE[4];
double kNow = 0, dNow = 0, rsiNow = 0;

//--- Cross flags (evaluated once per new bar)
bool bullCrossNow = false;   // fast crossed above slow between bar[1] -> bar[0]
bool bearCrossNow = false;   // fast crossed below slow between bar[1] -> bar[0]
bool bullCrossAny = false;   // bullish cross on bar[1]->[0] or one bar earlier (exit logic)
bool bearCrossAny = false;   // bearish cross on bar[1]->[0] or one bar earlier (exit logic)

//--- Stoch RSI permissions
bool longPermission = false;
bool shortPermission = false;

bool warmupLogged = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   if(BarSeconds < 1 || FastEMA < 1 || SlowEMA < 1 || RSILength < 2 || StochLength < 2 || KSmooth < 1 || DSmooth < 1)
   {
      Print("ERROR: invalid input parameters");
      return(INIT_PARAMETERS_INCORRECT);
   }
   
   ArrayResize(closes, MAX_BARS);
   barCount = 0;
   curBarTime = 0;
   curClose = 0;
   longPermission = false;
   shortPermission = false;
   warmupLogged = false;
   
   //--- Pre-fill bars from tick history so the EA can trade quickly
   WarmupFromHistory();
   
   Print("=======================================================");
   Print("XAUUSD ", BarSeconds, "-second Strategy (v7.00)");
   Print("=======================================================");
   Print("Stop Loss: -$", FixedStopLoss, " fixed (no trailing stop)");
   Print("Exit: opposite EMA ", FastEMA, "/", SlowEMA, " cross only | Flip: ", (AllowFlip ? "ON" : "OFF"));
   Print("EMA: ", FastEMA, "/", SlowEMA);
   Print("Stoch RSI: RSI=", RSILength, ", Stoch=", StochLength, ", K=", KSmooth, ", D=", DSmooth);
   Print("Permission bands: Long K>=", UpperBand, " | Short K<=", LowerBand, " | Reset at ", MiddleBand);
   Print("Lot Size: ", LotSize, " | Order filling mode: ", EnumToString(GetFillingMode()));
   Print("Bars ready: ", barCount, " / ", MIN_BARS, " needed");
   Print("=======================================================");
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("Strategy deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return;
   if(tick.bid <= 0) return;
   
   //--- Build 10-second bars from ticks; act only when a new bar starts
   if(!BuildBarFromTick(tick.bid, tick.time)) return;
   
   OnNewBar();
}

//+------------------------------------------------------------------+
//| Feed one price into the bar builder                                |
//| Returns true when a NEW bar has just started (previous one closed) |
//+------------------------------------------------------------------+
bool BuildBarFromTick(double price, datetime tickTime)
{
   long t = (long)tickTime;
   datetime barStart = (datetime)((t / BarSeconds) * BarSeconds);
   
   if(curBarTime == 0)
   {
      curBarTime = barStart;
      curClose = price;
      return false;
   }
   
   if(barStart == curBarTime)
   {
      curClose = price;
      return false;
   }
   
   if(barStart < curBarTime) return false; // out-of-order tick, ignore
   
   //--- New bar: the forming bar is now complete
   PushClose(curClose);
   curBarTime = barStart;
   curClose = price;
   return true;
}

//+------------------------------------------------------------------+
//| Store a completed bar close                                        |
//+------------------------------------------------------------------+
void PushClose(double c)
{
   if(barCount < MAX_BARS)
   {
      closes[barCount] = c;
      barCount++;
   }
   else
   {
      for(int i = 1; i < MAX_BARS; i++)
         closes[i - 1] = closes[i];
      closes[MAX_BARS - 1] = c;
   }
}

//+------------------------------------------------------------------+
//| Pre-fill bars from historical ticks                                |
//+------------------------------------------------------------------+
void WarmupFromHistory()
{
   if(WarmupMinutes <= 0) return;
   
   long toMsc = (long)TimeCurrent() * 1000;
   long fromMsc = toMsc - (long)WarmupMinutes * 60 * 1000;
   
   MqlTick ticks[];
   int got = CopyTicksRange(_Symbol, ticks, COPY_TICKS_INFO, (ulong)fromMsc, (ulong)toMsc);
   
   if(got <= 0)
   {
      Print("Warm-up: no tick history available (", got, "). Bars will build live; trading starts after ", MIN_BARS, " bars (",
            (MIN_BARS * BarSeconds) / 60, " min).");
      return;
   }
   
   for(int i = 0; i < got; i++)
   {
      double p = ticks[i].bid;
      if(p <= 0) continue;
      BuildBarFromTick(p, (datetime)(ticks[i].time_msc / 1000));
   }
   
   Print("Warm-up: ", got, " ticks -> ", barCount, " completed ", BarSeconds, "s bars");
}

//+------------------------------------------------------------------+
//| Everything that happens once per new 10-second bar                 |
//+------------------------------------------------------------------+
void OnNewBar()
{
   if(barCount < MIN_BARS)
   {
      if(barCount % 20 == 0)
         Print("Warming up: ", barCount, " / ", MIN_BARS, " bars");
      return;
   }
   
   if(!warmupLogged)
   {
      warmupLogged = true;
      Print("Warm-up complete: ", barCount, " bars - trading enabled");
   }
   
   //--- Session filter
   if(UseSessionFilter && !IsInTradingSession()) return;
   
   //--- Indicators + permissions + cross flags (all on completed bars)
   if(!CalculateIndicators()) return;
   UpdateKBasedPermissions();
   UpdateCrossFlags();
   
   if(VerboseLog)
   {
      Print("BAR ", TimeToString(curBarTime, TIME_DATE|TIME_SECONDS), " | Fast=", NormalizeDouble(fastE[0], _Digits),
            " Slow=", NormalizeDouble(slowE[0], _Digits), " | K=", NormalizeDouble(kNow, 2), " D=", NormalizeDouble(dNow, 2),
            " | LongPerm=", longPermission, " ShortPerm=", shortPermission);
   }
   
   int posType = GetCurrentPosition();
   bool closedNow = false;
   int closedType = -1;
   
   //--- Exit on opposite EMA cross
   if(posType != -1 && CheckExitSignal(posType))
   {
      if(ClosePosition("EMA Cross Exit"))
      {
         closedNow = true;
         closedType = posType;
         posType = -1;
      }
   }
   
   if(posType != -1) return; // still in a trade
   
   //--- Same-instant flip: exit and enter the opposite side on this bar
   if(closedNow)
   {
      if(!AllowFlip) return;
      
      if(closedType == POSITION_TYPE_BUY)
      {
         if(AllowShort && CheckShortEntry())
            OpenPosition(ORDER_TYPE_SELL);
      }
      else
      {
         if(AllowLong && CheckLongEntry())
            OpenPosition(ORDER_TYPE_BUY);
      }
      return;
   }
   
   //--- Normal entry
   if(AllowLong && CheckLongEntry())
      OpenPosition(ORDER_TYPE_BUY);
   else if(AllowShort && CheckShortEntry())
      OpenPosition(ORDER_TYPE_SELL);
}

//+------------------------------------------------------------------+
//| Calculate EMA 20/50 and Stoch RSI from the stored bar closes       |
//+------------------------------------------------------------------+
bool CalculateIndicators()
{
   int n = barCount;
   if(n < MIN_BARS) return false;
   
   double fe[], se[], rsi[], raw[], kk[], dd[];
   ArrayResize(fe, n);
   ArrayResize(se, n);
   ArrayResize(rsi, n);
   ArrayResize(raw, n);
   ArrayResize(kk, n);
   ArrayResize(dd, n);
   ArrayInitialize(rsi, 50.0);
   ArrayInitialize(raw, 50.0);
   ArrayInitialize(kk, 50.0);
   ArrayInitialize(dd, 50.0);
   
   //--- EMAs
   double af = 2.0 / (FastEMA + 1.0);
   double asl = 2.0 / (SlowEMA + 1.0);
   fe[0] = closes[0];
   se[0] = closes[0];
   for(int i = 1; i < n; i++)
   {
      fe[i] = closes[i] * af + fe[i - 1] * (1.0 - af);
      se[i] = closes[i] * asl + se[i - 1] * (1.0 - asl);
   }
   
   //--- RSI (Wilder smoothing)
   double avgG = 0, avgL = 0;
   for(int i = 1; i <= RSILength; i++)
   {
      double ch = closes[i] - closes[i - 1];
      if(ch > 0) avgG += ch; else avgL -= ch;
   }
   avgG /= RSILength;
   avgL /= RSILength;
   rsi[RSILength] = CalcRSIValue(avgG, avgL);
   
   for(int i = RSILength + 1; i < n; i++)
   {
      double ch = closes[i] - closes[i - 1];
      double g = (ch > 0) ? ch : 0.0;
      double l = (ch < 0) ? -ch : 0.0;
      avgG = (avgG * (RSILength - 1) + g) / RSILength;
      avgL = (avgL * (RSILength - 1) + l) / RSILength;
      rsi[i] = CalcRSIValue(avgG, avgL);
   }
   
   //--- Raw Stochastic of RSI
   int firstRaw = RSILength + StochLength - 1;
   for(int i = firstRaw; i < n; i++)
   {
      double hi = rsi[i], lo = rsi[i];
      for(int j = i - StochLength + 1; j <= i; j++)
      {
         if(rsi[j] > hi) hi = rsi[j];
         if(rsi[j] < lo) lo = rsi[j];
      }
      if(hi - lo > 0.001)
         raw[i] = 100.0 * (rsi[i] - lo) / (hi - lo);
      else
         raw[i] = 50.0;
   }
   
   //--- K = SMA(raw, KSmooth)
   int firstK = firstRaw + KSmooth - 1;
   for(int i = firstK; i < n; i++)
   {
      double sum = 0;
      for(int j = i - KSmooth + 1; j <= i; j++) sum += raw[j];
      kk[i] = sum / KSmooth;
   }
   
   //--- D = SMA(K, DSmooth)
   int firstD = firstK + DSmooth - 1;
   for(int i = firstD; i < n; i++)
   {
      double sum = 0;
      for(int j = i - DSmooth + 1; j <= i; j++) sum += kk[j];
      dd[i] = sum / DSmooth;
   }
   
   //--- Export latest values
   for(int j = 0; j < 4; j++)
   {
      fastE[j] = fe[n - 1 - j];
      slowE[j] = se[n - 1 - j];
   }
   rsiNow = rsi[n - 1];
   kNow = kk[n - 1];
   dNow = dd[n - 1];
   
   return true;
}

double CalcRSIValue(double avgGain, double avgLoss)
{
   if(avgGain + avgLoss <= 0.0) return 50.0;
   if(avgLoss <= 0.0) return 100.0;
   return 100.0 - 100.0 / (1.0 + avgGain / avgLoss);
}

//+------------------------------------------------------------------+
//| EMA cross detection on completed 10s bars                          |
//+------------------------------------------------------------------+
void UpdateCrossFlags()
{
   bullCrossNow = (fastE[1] <= slowE[1] && fastE[0] > slowE[0]);
   bearCrossNow = (fastE[1] >= slowE[1] && fastE[0] < slowE[0]);
   
   // Cross one bar earlier while fast is still on the new side (used by exit only)
   bool bullLate = (fastE[2] <= slowE[2] && fastE[1] > slowE[1] && fastE[0] > slowE[0]);
   bool bearLate = (fastE[2] >= slowE[2] && fastE[1] < slowE[1] && fastE[0] < slowE[0]);
   
   bullCrossAny = (bullCrossNow || bullLate);
   bearCrossAny = (bearCrossNow || bearLate);
}

//+------------------------------------------------------------------+
//| Update Stoch RSI entry permissions (once per bar)                  |
//| LONG : K >= 75 -> ON | stays ON while K > 50 | K < 50 -> OFF       |
//| SHORT: K <= 25 -> ON | stays ON while K < 50 | K > 50 -> OFF       |
//+------------------------------------------------------------------+
void UpdateKBasedPermissions()
{
   if(!UseStrictKDecision)
   {
      longPermission = true;
      shortPermission = true;
      return;
   }
   
   //--- LONG PERMISSION
   if(kNow >= UpperBand && !longPermission)
   {
      longPermission = true;
      Print("LONG PERMISSION ON | K=", NormalizeDouble(kNow, 2), " reached ", UpperBand);
   }
   if(longPermission && kNow < MiddleBand)
   {
      longPermission = false;
      Print("LONG PERMISSION OFF | K=", NormalizeDouble(kNow, 2), " dropped below ", MiddleBand);
   }
   
   //--- SHORT PERMISSION
   if(kNow <= LowerBand && !shortPermission)
   {
      shortPermission = true;
      Print("SHORT PERMISSION ON | K=", NormalizeDouble(kNow, 2), " reached ", LowerBand);
   }
   if(shortPermission && kNow > MiddleBand)
   {
      shortPermission = false;
      Print("SHORT PERMISSION OFF | K=", NormalizeDouble(kNow, 2), " rose above ", MiddleBand);
   }
}

//+------------------------------------------------------------------+
//| Pick an order filling mode the symbol supports                     |
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
//| Long entry: fresh bullish EMA cross + long permission              |
//+------------------------------------------------------------------+
bool CheckLongEntry()
{
   if(!bullCrossNow) return false;
   
   if(!longPermission)
   {
      Print("LONG REJECTED | EMA bullish cross but Stoch RSI long permission not active | K=", NormalizeDouble(kNow, 2));
      return false;
   }
   
   Print("LONG ENTRY APPROVED | Fast=", NormalizeDouble(fastE[0], _Digits), " crossed above Slow=", NormalizeDouble(slowE[0], _Digits),
         " | K=", NormalizeDouble(kNow, 2), " D=", NormalizeDouble(dNow, 2), " RSI=", NormalizeDouble(rsiNow, 2));
   return true;
}

//+------------------------------------------------------------------+
//| Short entry: fresh bearish EMA cross + short permission            |
//+------------------------------------------------------------------+
bool CheckShortEntry()
{
   if(!bearCrossNow) return false;
   
   if(!shortPermission)
   {
      Print("SHORT REJECTED | EMA bearish cross but Stoch RSI short permission not active | K=", NormalizeDouble(kNow, 2));
      return false;
   }
   
   Print("SHORT ENTRY APPROVED | Fast=", NormalizeDouble(fastE[0], _Digits), " crossed below Slow=", NormalizeDouble(slowE[0], _Digits),
         " | K=", NormalizeDouble(kNow, 2), " D=", NormalizeDouble(dNow, 2), " RSI=", NormalizeDouble(rsiNow, 2));
   return true;
}

//+------------------------------------------------------------------+
//| Exit signal: opposite EMA cross                                    |
//+------------------------------------------------------------------+
bool CheckExitSignal(int posType)
{
   if(posType == POSITION_TYPE_BUY && bearCrossAny)
   {
      Print("EXIT SIGNAL | LONG -> Fast EMA crossed below Slow EMA | Fast=", NormalizeDouble(fastE[0], _Digits),
            " Slow=", NormalizeDouble(slowE[0], _Digits));
      return true;
   }
   
   if(posType == POSITION_TYPE_SELL && bullCrossAny)
   {
      Print("EXIT SIGNAL | SHORT -> Fast EMA crossed above Slow EMA | Fast=", NormalizeDouble(fastE[0], _Digits),
            " Slow=", NormalizeDouble(slowE[0], _Digits));
      return true;
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| Get current position type (-1 = none)                              |
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
//| Open a position with fixed stop loss (-FixedStopLoss dollars)      |
//+------------------------------------------------------------------+
bool OpenPosition(ENUM_ORDER_TYPE orderType)
{
   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);
   
   double price = (orderType == ORDER_TYPE_BUY) ?
                  SymbolInfoDouble(_Symbol, SYMBOL_ASK) :
                  SymbolInfoDouble(_Symbol, SYMBOL_BID);
   
   //--- XAUUSD: 1 lot = $100 per $1 move, so 0.10 lot = $10 per $1
   //--- Loss of $50 at 0.10 lot = $5 price move (50 / 10)
   double dollarValuePerLot = 100.0;
   double dollarValueForPosition = dollarValuePerLot * LotSize;
   
   if(dollarValueForPosition <= 0 || FixedStopLoss <= 0)
   {
      Print("ERROR: Cannot calculate SL. Check LotSize / FixedStopLoss.");
      return false;
   }
   
   double priceDistance = FixedStopLoss / dollarValueForPosition;
   double sl = (orderType == ORDER_TYPE_BUY) ?
               NormalizeDouble(price - priceDistance, _Digits) :
               NormalizeDouble(price + priceDistance, _Digits);
   
   //--- Respect broker minimum stop distance
   double minStopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(minStopLevel > 0 && MathAbs(price - sl) < minStopLevel)
   {
      Print("WARNING: SL distance ", NormalizeDouble(MathAbs(price - sl), _Digits), " below broker minimum ",
            NormalizeDouble(minStopLevel, _Digits), " - adjusting (loss may exceed $", FixedStopLoss, ")");
      sl = (orderType == ORDER_TYPE_BUY) ?
           NormalizeDouble(price - minStopLevel, _Digits) :
           NormalizeDouble(price + minStopLevel, _Digits);
   }
   
   if(sl <= 0 || MathAbs(price - sl) < 0.01)
   {
      Print("ERROR: Stop loss not calculated properly - trade aborted. Price=", NormalizeDouble(price, _Digits),
            " SL=", NormalizeDouble(sl, _Digits));
      return false;
   }
   
   request.action = TRADE_ACTION_DEAL;
   request.symbol = _Symbol;
   request.volume = LotSize;
   request.type = orderType;
   request.price = price;
   request.sl = sl;       // set on the broker server
   request.tp = 0;        // no take profit, exit on EMA cross
   request.deviation = 10;
   request.magic = MagicNumber;
   request.comment = StringFormat("%ds EMA+StochRSI", BarSeconds);
   request.type_filling = GetFillingMode();
   
   if(!OrderSend(request, result))
   {
      Print("ERROR OPENING POSITION: ", GetLastError(), " - ", result.comment, " | retcode=", result.retcode);
      return false;
   }
   
   if(result.retcode != TRADE_RETCODE_DONE && result.retcode != TRADE_RETCODE_PLACED)
   {
      Print("ORDER WARNING: retcode ", result.retcode, " - ", result.comment);
      return false;
   }
   
   Print("POSITION OPENED | ", (orderType == ORDER_TYPE_BUY ? "BUY" : "SELL"), " ", LotSize, " lots @ ",
         NormalizeDouble(result.price > 0 ? result.price : price, _Digits),
         " | SL ", NormalizeDouble(sl, _Digits), " (-$", FixedStopLoss, ")");
   
   //--- Confirm the SL really exists on the position
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            if(PositionGetDouble(POSITION_SL) <= 0.0001)
               Print("CRITICAL: Stop loss missing on position #", ticket, " - set it manually or close the trade!");
            break;
         }
      }
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Close current position(s) of this EA                               |
//+------------------------------------------------------------------+
bool ClosePosition(string reason)
{
   bool allClosed = true;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      
      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      
      double profit = PositionGetDouble(POSITION_PROFIT);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      ENUM_POSITION_TYPE pType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double posVolume = PositionGetDouble(POSITION_VOLUME);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      
      MqlTradeRequest request;
      MqlTradeResult result;
      ZeroMemory(request);
      ZeroMemory(result);
      
      request.action = TRADE_ACTION_DEAL;
      request.position = ticket;
      request.symbol = _Symbol;
      request.volume = posVolume;
      request.type = (pType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      request.price = (request.type == ORDER_TYPE_SELL) ?
                      SymbolInfoDouble(_Symbol, SYMBOL_BID) :
                      SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      request.deviation = 10;
      request.magic = MagicNumber;
      request.comment = reason;
      request.type_filling = GetFillingMode();
      
      if(OrderSend(request, result) &&
         (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
      {
         Print("POSITION CLOSED | ", (pType == POSITION_TYPE_BUY ? "LONG" : "SHORT"), " #", ticket,
               " | Reason: ", reason,
               " | Entry ", NormalizeDouble(openPrice, _Digits), " -> Exit ", NormalizeDouble(request.price, _Digits),
               " | P/L ~ ", (profit >= 0 ? "+" : ""), "$", NormalizeDouble(profit, 2),
               " | Duration ", (int)(TimeCurrent() - openTime), "s");
      }
      else
      {
         allClosed = false;
         Print("ERROR CLOSING POSITION #", ticket, ": ", GetLastError(), " - ", result.comment, " | retcode=", result.retcode);
      }
   }
   
   return allClosed;
}

//+------------------------------------------------------------------+
//| Check if current time is within trading session                    |
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
      // Overnight sessions (e.g., 22:00 to 06:00)
      return (currentHour >= SessionStartHour || currentHour < SessionEndHour);
   }
}
//+------------------------------------------------------------------+
