//+------------------------------------------------------------------+
//|                                  XAUUSD_10S_EMA_ATR_CHOP_TSL.mq5 |
//|   EMA 20/50 cross + CHOP filter | ATR initial SL | Profit ladder   |
//+------------------------------------------------------------------+
#property copyright "EMA + ATR + CHOP (10s)"
#property link      ""
#property version   "5.00"
#property description "10-second bars are built inside the EA from ticks (MT5 has no native 10s chart)"
#property description "Entry : EMA 20/50 cross (live on every tick, also confirmed at bar close), only when CHOP < 50"
#property description "STRICT entry: a trade is opened only on the exact tick its conditions are true (cross + CHOP<50). One attempt, no pending signals, no retries."
#property description "Init SL: ATR(14, RMA) x 1.5 stop line (low - ATR / high + ATR) pushed a further 0.50 away"
#property description "Trail  : profit +50 -> SL +40 | +100 -> +80 | +150 -> +120 | +200 -> +160 ... (every +50)"

//--- Capital & Risk
input group "Trade"
input double LotSize = 0.10;               // Lot Size
input int    MagicNumber = 123457;         // Magic Number
input bool   AllowLong = true;             // Allow Long
input bool   AllowShort = true;            // Allow Short
input bool   ExitOnOppositeCross = false;  // Also close on opposite EMA cross (Pine has no exit)
input int    Deviation = 50;               // Max slippage in points (raise if orders get requoted)
input bool   EntryOnTickCross = true;      // Enter the moment the cross happens (not only at 10s bar close)
input bool   ExitCheckLastBarCross = true;  // At an SL/TP exit tick, also accept the cross that closed on the last completed bar (checked once, that second only)

//--- Timeframe
input group "Timeframe (built from ticks)"
input int BarSeconds = 10;                 // Bar length in seconds
input int WarmupMinutes = 180;             // Minutes of tick history used to pre-fill bars at start

//--- EMA
input group "EMA"
input int FastEMA = 20;                    // Fast EMA
input int SlowEMA = 50;                    // Slow EMA

//--- CHOP
input group "CHOP filter"
input bool   UseChop = true;               // Only take crosses when CHOP is below threshold
input double ChopThreshold = 50.0;         // CHOP threshold
input int    ChopLength = 14;              // CHOP length

//--- ATR initial stop
input group "ATR initial stop loss"
input int    ATRLength = 14;               // ATR length (RMA smoothing, as Pine default)
input double ATRMultiplier = 1.5;          // ATR multiplier
input double ATROffset = 0.50;             // Extra price distance added to the ATR stop (0.50 = 0.500)
input bool   UseSignalBarExtreme = true;   // true: SL from signal-bar low/high (as Pine) | false: from entry price

//--- Profit ladder
input group "Profit ladder (in $ profit)"
input double TrailStepProfit = 50.0;       // Every +$50 profit ...
input double TrailStepLock = 40.0;         // ... SL locks +$40 per step (50->40, 100->80, 150->120 ...)

input group "Logging"
input bool VerboseLog = false;             // Print one line per 10s bar

#define MAX_BARS 600
#define MIN_BARS 200

//--- completed 10s bars, oldest first
double highs[], lows[], closes[];
int    barCount = 0;
datetime curBarTime = 0;
double curHigh = 0, curLow = 0, curClose = 0;

//--- indicator values (latest completed bar = 0, previous = 1)
double fast0, fast1, slow0, slow1;
double atrRaw = 0;       // RMA(TR, ATRLength) without multiplier
double chopVal = 100;      // CHOP on last COMPLETED bar
double chopLive = 100;     // CHOP including the forming bar (updated every tick)
ulong  lastDiagMs = 0;

bool bullCross = false, bearCross = false;
bool indReady = false;
datetime lastBarTime = 0;          // open time of the last COMPLETED bar
//--- strict-entry bookkeeping (no pending signals)
int      lastCrossDir = 0;         // last bar-close cross that passed CHOP (+1 / -1)
datetime lastCrossTime = 0;        // bar time of that cross
datetime consumedBull = 0, consumedBear = 0;   // crosses already attempted: one attempt per cross, ever
bool     hadPosition = false;
bool warmupLogged = false;
int  lastTrailStep = 0;
ulong lastTrailTicket = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   if(BarSeconds < 1 || FastEMA < 1 || SlowEMA < 1 || ChopLength < 2 || ATRLength < 1)
   {
      Print("ERROR: invalid input parameters");
      return(INIT_PARAMETERS_INCORRECT);
   }
   ArrayResize(highs, MAX_BARS);
   ArrayResize(lows, MAX_BARS);
   ArrayResize(closes, MAX_BARS);
   barCount = 0;
   curBarTime = 0;
   warmupLogged = false;

   WarmupFromHistory();

   Print("=== XAUUSD ", BarSeconds, "s EMA+ATR+CHOP EA ===");
   Print("EMA ", FastEMA, "/", SlowEMA, " | CHOP<", ChopThreshold, " (len ", ChopLength, ", ", (UseChop ? "ON" : "OFF"), ")");
   Print("Init SL: ATR(", ATRLength, ") x ", ATRMultiplier, " + ", ATROffset, " | Ladder: every +$", TrailStepProfit, " profit -> SL +$", TrailStepLock, " per step");
   Print("Bars ready: ", barCount, " / ", MIN_BARS);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { Print("EA stopped. Reason: ", reason); }

//+------------------------------------------------------------------+
void OnTick()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return;
   if(tick.bid <= 0) return;

   bool newBar = BuildBarFromTick(tick.bid, (datetime)(tick.time_msc / 1000));

   if(newBar) OnNewBar();                 // bar-close cross -> one immediate attempt
   ManageTrailing();                      // every tick
   UpdateLiveChop();                      // CHOP incl. forming bar, same as a live chart shows
   TrackExit();                           // detects SL / TP exit -> one check on that tick
   if(EntryOnTickCross) CheckLiveCross(tick.bid);
}

//+------------------------------------------------------------------+
//| Tick -> 10s bar builder. Returns true when a new bar has started  |
//+------------------------------------------------------------------+
bool BuildBarFromTick(double price, datetime tickTime)
{
   long t = (long)tickTime;
   datetime barStart = (datetime)((t / BarSeconds) * BarSeconds);

   if(curBarTime == 0)
   {
      curBarTime = barStart;
      curHigh = curLow = curClose = price;
      return false;
   }
   if(barStart == curBarTime)
   {
      if(price > curHigh) curHigh = price;
      if(price < curLow)  curLow = price;
      curClose = price;
      return false;
   }
   if(barStart < curBarTime) return false;

   PushBar(curHigh, curLow, curClose);
   lastBarTime = curBarTime;
   curBarTime = barStart;
   curHigh = curLow = curClose = price;
   return true;
}

void PushBar(double h, double l, double c)
{
   if(barCount < MAX_BARS)
   {
      highs[barCount] = h; lows[barCount] = l; closes[barCount] = c;
      barCount++;
   }
   else
   {
      ArrayCopy(highs,  highs,  0, 1, MAX_BARS - 1);
      ArrayCopy(lows,   lows,   0, 1, MAX_BARS - 1);
      ArrayCopy(closes, closes, 0, 1, MAX_BARS - 1);
      highs[MAX_BARS - 1] = h; lows[MAX_BARS - 1] = l; closes[MAX_BARS - 1] = c;
   }
}

void WarmupFromHistory()
{
   if(WarmupMinutes <= 0) return;
   long toMsc = (long)TimeCurrent() * 1000;
   long fromMsc = toMsc - (long)WarmupMinutes * 60 * 1000;

   MqlTick ticks[];
   int got = CopyTicksRange(_Symbol, ticks, COPY_TICKS_INFO, (ulong)fromMsc, (ulong)toMsc);
   if(got <= 0)
   {
      Print("Warm-up: no tick history. Trading starts after ", MIN_BARS, " live bars (", (MIN_BARS * BarSeconds) / 60, " min).");
      return;
   }
   for(int i = 0; i < got; i++)
   {
      if(ticks[i].bid <= 0) continue;
      BuildBarFromTick(ticks[i].bid, (datetime)(ticks[i].time_msc / 1000));
   }
   Print("Warm-up: ", got, " ticks -> ", barCount, " completed ", BarSeconds, "s bars");
}

//+------------------------------------------------------------------+
//| EMA, ATR (RMA of True Range) and Choppiness Index on stored bars |
//+------------------------------------------------------------------+
bool CalculateIndicators()
{
   int n = barCount;
   if(n < MIN_BARS || n < ChopLength + 1 || n < ATRLength + 1) return false;

   double fe = closes[0], se = closes[0], fePrev = fe, sePrev = se;
   double af = 2.0 / (FastEMA + 1.0);
   double as = 2.0 / (SlowEMA + 1.0);
   for(int i = 1; i < n; i++)
   {
      fePrev = fe; sePrev = se;
      fe = closes[i] * af + fe * (1.0 - af);
      se = closes[i] * as + se * (1.0 - as);
   }
   fast0 = fe; fast1 = fePrev;
   slow0 = se; slow1 = sePrev;

   //--- True Range array
   double tr[];
   ArrayResize(tr, n);
   tr[0] = highs[0] - lows[0];
   for(int i = 1; i < n; i++)
   {
      double a = highs[i] - lows[i];
      double b = MathAbs(highs[i] - closes[i - 1]);
      double c = MathAbs(lows[i] - closes[i - 1]);
      tr[i] = MathMax(a, MathMax(b, c));
   }

   //--- ATR = RMA(TR, len), seeded with SMA (same as ta.rma)
   double sum = 0;
   for(int i = 0; i < ATRLength; i++) sum += tr[i];
   double rma = sum / ATRLength;
   for(int i = ATRLength; i < n; i++)
      rma = (rma * (ATRLength - 1) + tr[i]) / ATRLength;
   atrRaw = rma;

   //--- Choppiness Index
   double trSum = 0;
   double hh = highs[n - 1], ll = lows[n - 1];
   for(int i = n - ChopLength; i < n; i++)
   {
      trSum += tr[i];
      if(highs[i] > hh) hh = highs[i];
      if(lows[i] < ll)  ll = lows[i];
   }
   double range = hh - ll;
   if(range > 0 && trSum > 0)
      chopVal = 100.0 * MathLog10(trSum / range) / MathLog10((double)ChopLength);
   else
      chopVal = 100.0;

   return true;
}

//+------------------------------------------------------------------+
void OnNewBar()
{
   if(barCount < MIN_BARS)
   {
      if(barCount % 20 == 0) Print("Warming up: ", barCount, " / ", MIN_BARS, " bars");
      return;
   }
   if(!warmupLogged) { warmupLogged = true; Print("Warm-up complete - trading enabled"); }

   if(!CalculateIndicators()) return;

   indReady = true;

   bool trending = (!UseChop || chopVal < ChopThreshold);
   bool rawBull = (fast1 <= slow1 && fast0 > slow0);
   bool rawBear = (fast1 >= slow1 && fast0 < slow0);
   bullCross = rawBull && trending;
   bearCross = rawBear && trending;

   if(VerboseLog)
      Print("BAR ", TimeToString(curBarTime, TIME_DATE | TIME_SECONDS), " | Fast=", NormalizeDouble(fast0, _Digits),
            " Slow=", NormalizeDouble(slow0, _Digits), " | ATR=", NormalizeDouble(atrRaw, 3),
            " | CHOP=", NormalizeDouble(chopVal, 1), " | bull=", bullCross, " bear=", bearCross);

   if(rawBull && !trending) Print("BULL CROSS IGNORED | CHOP=", NormalizeDouble(chopVal, 1), " >= ", ChopThreshold);
   if(rawBear && !trending) Print("BEAR CROSS IGNORED | CHOP=", NormalizeDouble(chopVal, 1), " >= ", ChopThreshold);

   //--- remember the last bar-close cross (only used by the one-time check at an exit tick)
   if(bullCross)      { lastCrossDir = 1;  lastCrossTime = lastBarTime; }
   else if(bearCross) { lastCrossDir = -1; lastCrossTime = lastBarTime; }

   //--- optional exit on opposite cross (ignores CHOP); entry below is evaluated on this same tick
   int posType = GetCurrentPosition();
   if(posType != -1 && ExitOnOppositeCross)
   {
      if((posType == POSITION_TYPE_BUY && rawBear) || (posType == POSITION_TYPE_SELL && rawBull))
         ClosePosition("EMA Cross Exit");
   }

   //--- STRICT: act only now, on this bar-close tick. Not flat / condition false -> nothing, nothing stored.
   if(bullCross)      TryOpen(1, lastBarTime, "bar-close cross");
   else if(bearCross) TryOpen(-1, lastBarTime, "bar-close cross");
}

//+------------------------------------------------------------------+
//| Entry handling - a trade is opened ONLY on the tick its condition |
//| is true. One attempt per cross. Nothing is stored or retried.      |
//+------------------------------------------------------------------+
//--- live EMA values using the current tick as the forming bar's close
void LiveEMA(double price, double &fL, double &sL)
{
   double af = 2.0 / (FastEMA + 1.0);
   double as = 2.0 / (SlowEMA + 1.0);
   fL = price * af + fast0 * (1.0 - af);
   sL = price * as + slow0 * (1.0 - as);
}

//--- Choppiness Index with the forming bar as the newest bar
void UpdateLiveChop()
{
   if(!indReady || barCount < ChopLength + 1) { chopLive = chopVal; return; }
   int n = barCount;
   double lastClose = closes[n - 1];
   double trF = MathMax(curHigh - curLow, MathMax(MathAbs(curHigh - lastClose), MathAbs(curLow - lastClose)));
   double trSum = trF, hh = curHigh, ll = curLow;
   for(int i = n - (ChopLength - 1); i < n; i++)
   {
      double pc = closes[i - 1];
      double tr = MathMax(highs[i] - lows[i], MathMax(MathAbs(highs[i] - pc), MathAbs(lows[i] - pc)));
      trSum += tr;
      if(highs[i] > hh) hh = highs[i];
      if(lows[i] < ll)  ll = lows[i];
   }
   double range = hh - ll;
   if(range > 0 && trSum > 0)
      chopLive = 100.0 * MathLog10(trSum / range) / MathLog10((double)ChopLength);
   else
      chopLive = 100.0;
}

//--- single attempt, right now. Returns true only if the order was placed.
bool TryOpen(int dir, datetime crossTime, string why)
{
   if(!indReady) return false;
   if(GetCurrentPosition() != -1) return false;                    // in a trade: crosses are simply ignored
   if(dir == 1 && !AllowLong) return false;
   if(dir == -1 && !AllowShort) return false;
   if(crossTime != 0)
   {
      if(dir == 1  && crossTime == consumedBull) return false;     // this cross was already attempted
      if(dir == -1 && crossTime == consumedBear) return false;
      if(dir == 1) consumedBull = crossTime; else consumedBear = crossTime;   // mark BEFORE the order: a failed order is never retried
   }
   Print("ENTRY NOW | ", (dir == 1 ? "BUY" : "SELL"), " | ", why, " | cross bar ", TimeToString(crossTime, TIME_DATE | TIME_SECONDS),
         " | CHOP live=", NormalizeDouble(chopLive, 1));
   bool ok = OpenPosition(dir == 1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   if(!ok) Print("ENTRY FAILED - not retried (condition was only valid at that moment)");
   return ok;
}

//--- cross happening right now on the forming bar (vs. last completed bar)
void CheckLiveCross(double price)
{
   if(!indReady) return;
   if(GetCurrentPosition() != -1) return;
   double fL, sL;
   LiveEMA(price, fL, sL);
   int dir = 0;
   if(fast0 <= slow0 && fL > sL)      dir = 1;
   else if(fast0 >= slow0 && fL < sL) dir = -1;
   if(dir == 0) return;

   if(UseChop && chopLive >= ChopThreshold)
   {
      if(GetTickCount64() - lastDiagMs > 2000)
      {
         lastDiagMs = GetTickCount64();
         Print("LIVE ", (dir == 1 ? "BULL" : "BEAR"), " CROSS ignored | live CHOP=", NormalizeDouble(chopLive, 1), " >= ", ChopThreshold);
      }
      return;
   }
   TryOpen(dir, curBarTime, "live cross");
}

void DiagState(string tag)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double fL = 0, sL = 0;
   if(indReady) LiveEMA(bid, fL, sL);
   Print(tag, " | doneBar fast/slow=", NormalizeDouble(fast0, _Digits), "/", NormalizeDouble(slow0, _Digits),
         " | live fast/slow=", NormalizeDouble(fL, _Digits), "/", NormalizeDouble(sL, _Digits),
         " | CHOP bar/live=", NormalizeDouble(chopVal, 1), "/", NormalizeDouble(chopLive, 1),
         " | last bar-close cross=", lastCrossDir, " @ ", TimeToString(lastCrossTime, TIME_SECONDS));
}

//--- position just closed (SL / TP / manual): evaluate the entry condition ONCE, on this tick
void TrackExit()
{
   bool has = (GetCurrentPosition() != -1);
   if(hadPosition && !has)
   {
      LogLastExit();
      DiagState("AT EXIT");
      //--- (a live cross on this same tick is handled right after by CheckLiveCross)
      if(ExitCheckLastBarCross && indReady && lastCrossDir != 0 && lastCrossTime == lastBarTime)
      {
         bool aligned = (lastCrossDir == 1) ? (fast0 > slow0) : (fast0 < slow0);
         bool chopOk  = (!UseChop || chopLive < ChopThreshold);
         if(aligned && chopOk) TryOpen(lastCrossDir, lastCrossTime, "cross on last bar, at exit tick");
         else Print("AT EXIT: no entry | aligned=", aligned, " chopOk=", chopOk);
      }
   }
   hadPosition = has;
}

void LogLastExit()
{
   if(!HistorySelect(TimeCurrent() - 600, TimeCurrent() + 60)) return;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != MagicNumber) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      Print("EXIT detected | reason=", EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(d, DEAL_REASON)),
            " | P/L $", NormalizeDouble(HistoryDealGetDouble(d, DEAL_PROFIT), 2));
      return;
   }
   Print("EXIT detected");
}

//+------------------------------------------------------------------+
//| $ profit per 1.00 price move for a given volume                   |
//+------------------------------------------------------------------+
double DollarsPerPriceUnit(double volume)
{
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0) return 100.0 * volume;   // XAUUSD fallback: 1 lot = $100 per $1
   return (tv / ts) * volume;
}

//+------------------------------------------------------------------+
//| Open with ATR initial stop loss                                    |
//+------------------------------------------------------------------+
bool OpenPosition(ENUM_ORDER_TYPE type)
{
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);

   bool isBuy = (type == ORDER_TYPE_BUY);
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   //--- Pine: atr = RMA(TR) * mult ; shortStop = high + atr ; longStop = low - atr
   double atrDist = atrRaw * ATRMultiplier + ATROffset;
   double sigHigh = MathMax(highs[barCount - 1], curHigh);   // last completed bar + forming bar
   double sigLow  = MathMin(lows[barCount - 1],  curLow);

   double sl;
   if(isBuy)
      sl = (UseSignalBarExtreme ? MathMin(sigLow, price) : price) - atrDist;
   else
      sl = (UseSignalBarExtreme ? MathMax(sigHigh, price) : price) + atrDist;
   sl = NormalizeDouble(sl, _Digits);

   //--- broker minimum stop distance
   double minStop = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(minStop > 0 && MathAbs(price - sl) < minStop)
      sl = NormalizeDouble(isBuy ? price - minStop : price + minStop, _Digits);

   if(sl <= 0 || (isBuy && sl >= price) || (!isBuy && sl <= price))
   {
      Print("ERROR: invalid SL - trade aborted. Price=", price, " SL=", sl);
      return false;
   }

   req.action = TRADE_ACTION_DEAL;
   req.symbol = _Symbol;
   req.volume = LotSize;
   req.type = type;
   req.price = price;
   req.sl = sl;
   req.tp = 0;
   req.deviation = Deviation;
   req.magic = MagicNumber;
   req.comment = StringFormat("%ds EMA+ATR+CHOP", BarSeconds);
   req.type_filling = GetFillingMode();

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED))
   {
      Print("ORDER FAILED | retcode=", res.retcode, " - ", res.comment);
      return false;
   }

   double riskUsd = MathAbs(price - sl) * DollarsPerPriceUnit(LotSize);
   Print("OPENED ", (isBuy ? "BUY" : "SELL"), " ", LotSize, " @ ", NormalizeDouble(res.price > 0 ? res.price : price, _Digits),
         " | SL ", sl, " (dist ", NormalizeDouble(MathAbs(price - sl), _Digits), " ~ -$", NormalizeDouble(riskUsd, 2), ")",
         " | ATR=", NormalizeDouble(atrRaw, 3), " CHOP=", NormalizeDouble(chopVal, 1));
   lastTrailStep = 0;
   lastTrailTicket = 0;
   return true;
}

//+------------------------------------------------------------------+
//| Profit ladder: every +TrailStepProfit -> SL locks +TrailStepLock   |
//| per step (+50->+40, +100->+80, +150->+120, +200->+160, ...)        |
//+------------------------------------------------------------------+
void ManageTrailing()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      ENUM_POSITION_TYPE pt = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double vol = PositionGetDouble(POSITION_VOLUME);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double dpu = DollarsPerPriceUnit(vol);
      if(dpu <= 0 || TrailStepProfit <= 0) return;

      bool isBuy = (pt == POSITION_TYPE_BUY);
      double profitUsd = (isBuy ? (bid - open) : (open - ask)) * dpu;

      int steps = (int)MathFloor(profitUsd / TrailStepProfit);
      if(steps < 1) continue;

      double lockUsd = steps * TrailStepLock;
      double lockPrice = lockUsd / dpu;
      double newSL = NormalizeDouble(isBuy ? open + lockPrice : open - lockPrice, _Digits);

      double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
      double minStop = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;

      bool better = isBuy ? (curSL <= 0 || newSL > curSL + point) : (curSL <= 0 || newSL < curSL - point);
      bool valid  = isBuy ? (newSL < bid - minStop) : (newSL > ask + minStop);
      if(!better || !valid) continue;

      MqlTradeRequest req; MqlTradeResult res;
      ZeroMemory(req); ZeroMemory(res);
      req.action = TRADE_ACTION_SLTP;
      req.position = ticket;
      req.symbol = _Symbol;
      req.sl = newSL;
      req.tp = tp;
      req.magic = MagicNumber;

      if(OrderSend(req, res) && (res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED))
      {
         Print("LADDER | profit +$", NormalizeDouble(profitUsd, 2), " (step ", steps, ") -> SL moved to ", newSL, " (locks +$", lockUsd, ")");
      }
      else
         Print("LADDER FAILED | retcode=", res.retcode, " - ", res.comment);
   }
}

//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING GetFillingMode()
{
   long flags = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((flags & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   if((flags & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

int GetCurrentPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket) &&
         PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         return (int)PositionGetInteger(POSITION_TYPE);
   }
   return -1;
}

bool ClosePosition(string reason)
{
   bool ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      ENUM_POSITION_TYPE pt = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      MqlTradeRequest req; MqlTradeResult res;
      ZeroMemory(req); ZeroMemory(res);
      req.action = TRADE_ACTION_DEAL;
      req.position = ticket;
      req.symbol = _Symbol;
      req.volume = PositionGetDouble(POSITION_VOLUME);
      req.type = (pt == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      req.price = (req.type == ORDER_TYPE_SELL) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      req.deviation = Deviation;
      req.magic = MagicNumber;
      req.comment = reason;
      req.type_filling = GetFillingMode();

      if(OrderSend(req, res) && (res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED))
         Print("CLOSED #", ticket, " | ", reason, " | P/L ~ $", NormalizeDouble(PositionGetDouble(POSITION_PROFIT), 2));
      else
      {
         ok = false;
         Print("CLOSE FAILED #", ticket, " | retcode=", res.retcode, " - ", res.comment);
      }
   }
   return ok;
}
//+------------------------------------------------------------------+
