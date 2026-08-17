# Live Algo Trading Setup Guide (Demo Account)

This guide will help you run the EMA Crossover Strategy as a live algo trading bot on your MT5 demo account.

---

## 🎯 What You'll Achieve

After following this guide:
- ✅ EA will run 24/7 on your demo account
- ✅ Automatically detect EMA crossover signals
- ✅ Open and close trades based on strategy rules
- ✅ Manage risk with stop loss
- ✅ Monitor trades in real-time

---

## ⚠️ Important Prerequisites

Before starting:
- ✅ MT5 installed and running
- ✅ Demo account created and logged in
- ✅ EA file compiled successfully (0 errors)
- ✅ EA visible in Navigator panel

---

## 📋 Step-by-Step Setup

### STEP 1: Prepare Your Chart

1. **Open MT5**

2. **Create a new chart for your symbol:**
   - Click **File → New Chart**
   - Select your symbol (e.g., **XAUUSD** for Gold)
   - Or drag symbol from Market Watch to create chart

3. **Set your timeframe:**
   - Click timeframe buttons in toolbar
   - Recommended: **M5** (5-minute) or **M15** (15-minute) for active trading
   - Or **H1** (1-hour) for slower trading
   - Or **M1** (1-minute) for very active scalping

4. **Add EMA indicators (optional - for visual confirmation):**
   - Click **Insert → Indicators → Trend → Moving Average**
   - Set: Period=20, Method=Exponential, Apply to=Close, Color=Red
   - Repeat for EMA 50 (Color=Blue) and EMA 100 (Color=Green)

---

### STEP 2: Attach EA to Chart

1. **Open Navigator panel:**
   - Press **Ctrl+N** or click **View → Navigator**

2. **Find your EA:**
   - In Navigator, expand **"Expert Advisors"** section
   - Look for **"EMA_Crossover_Strategy"**
   - If not visible → Right-click → Refresh

3. **Drag EA onto chart:**
   - Click and hold **"EMA_Crossover_Strategy"**
   - Drag it onto your chart (the one with XAUUSD or your symbol)
   - Release mouse button
   - Settings window will appear

---

### STEP 3: Configure EA Settings

When the settings window opens, configure these parameters:

#### **Common Tab:**
- ✅ Check **"Allow Algo Trading"** (IMPORTANT!)
- ✅ Check **"Allow DLL imports"** (if using external libraries)
- ✅ Check **"Allow imports of external experts"**

#### **Inputs Tab - Risk Management:**
```
RiskPercent:    1.0     → Risk 1% of balance per trade
                         (Increase to 2.0 for more aggressive, 0.5 for conservative)

LotSize:        0.10    → Fixed lot size for forex
                         (0.01 = micro lot, 0.10 = mini lot, 1.0 = standard lot)

UseFixedLot:    true    → true = use fixed LotSize
                         → false = calculate lot based on risk %
```

#### **Inputs Tab - EMA Settings:**
```
EMA_Fast:       20      → Fast EMA period (don't change)
EMA_Mid:        50      → Mid EMA period (don't change)
EMA_Slow:       100     → Slow EMA period (don't change)
WarmupBars:     100     → Skip first 100 bars (don't change)
```

#### **Inputs Tab - Trade Settings:**
```
TradeComment:   "EMA_Cross_EA"  → Comment for your trades
MagicNumber:    202602          → Unique ID (don't change)
AllowLong:      true            → Allow BUY trades
AllowShort:     true            → Allow SELL trades
```

#### **Recommended Settings for Different Symbols:**

**For XAUUSD (Gold) - Scalping:**
```
Timeframe:      M5 or M15
RiskPercent:    1.0
LotSize:        0.10
UseFixedLot:    true
```

**For EURUSD - Intraday:**
```
Timeframe:      M15 or H1
RiskPercent:    1.5
LotSize:        0.10
UseFixedLot:    true
```

**For Conservative Trading:**
```
Timeframe:      H1 or H4
RiskPercent:    0.5
LotSize:        0.05
UseFixedLot:    true
```

4. **Click OK** to apply settings

---

### STEP 4: Enable Auto Trading

1. **Enable AutoTrading in MT5:**
   - Look at the top toolbar
   - Find the **"AutoTrading"** button (looks like a traffic light)
   - Click it until it turns **GREEN** ✅
   - If it's RED, the EA won't trade!

2. **Verify EA is running:**
   - Look at top-right corner of your chart
   - You should see:
     ```
     EMA_Crossover_Strategy
     😊 (smiley face = EA is active and happy)
     ```
   - If you see 😟 (sad face) → EA has error, check Journal tab

---

### STEP 5: Monitor EA Activity

#### **Open Terminal Panel:**
- Press **Ctrl+T** or click **View → Terminal**
- The terminal panel appears at the bottom

#### **Check These Tabs:**

1. **Trade Tab:**
   - Shows **currently open positions**
   - You'll see: Symbol, Type (Buy/Sell), Volume, Price, S/L, T/P, Profit
   - Initially empty until EA opens a trade

2. **History Tab:**
   - Shows **closed trades**
   - Right-click → Select time period (Today, Last Week, Last Month, etc.)
   - You'll see: Time, Order, Symbol, Type, Volume, Price, S/L, T/P, Profit

3. **Journal Tab:**
   - Shows **EA log messages**
   - Look for:
     ```
     ==============================================
     EMA Crossover Strategy EA Initialised
     Symbol:    XAUUSD
     Timeframe: M5
     ==============================================
     ```
   - Later you'll see `[ENTRY SIGNAL]`, `[EXIT SIGNAL]`, `[TRADE OPENED]`, etc.

4. **Experts Tab:**
   - Shows **detailed EA logs**
   - All Print() statements from EA appear here
   - Very useful for debugging

---

### STEP 6: Wait for Signals

The EA will now:
1. ✅ Monitor EMA 20/50/100 on every new bar
2. ✅ Wait for EMA50 to cross EMA100
3. ✅ Verify alignment (EMA20 > EMA50 > EMA100 for long)
4. ✅ Open trade at next bar's open price
5. ✅ Set stop loss based on risk %
6. ✅ Monitor for exit signal (EMA20 crosses EMA50)
7. ✅ Close trade at next bar's open price

**How long to wait?**
- M1 (1-minute): May see signal within hours
- M5 (5-minute): May see signal within 1-2 days
- M15 (15-minute): May see signal within 2-3 days
- H1 (1-hour): May see signal within 1 week
- H4 (4-hour): May see signal within 2-3 weeks

**EMA crossovers are RARE events** — be patient!

---

### STEP 7: Monitor First Trade

When EA opens first trade:

1. **Journal Tab will show:**
   ```
   [ENTRY SIGNAL] LONG: EMA50 crossed above EMA100
     prev50=2385.50 prev100=2385.80 curr50=2386.20 curr100=2386.00
     EMA Alignment: EMA20=2387.00 EMA50=2386.20 EMA100=2386.00
   
   [TRADE OPENED] LONG | Price=2386.50 | Lots=0.10 | SL=2380.00 | Ticket=12345678
   ```

2. **Trade Tab will show:**
   ```
   Symbol: XAUUSD
   Type: Buy
   Volume: 0.10
   Price: 2386.50
   S/L: 2380.00
   T/P: 0.00 (no take profit)
   Profit: -2.50 (current unrealized P/L)
   ```

3. **Chart will show:**
   - Blue arrow ↑ (for buy) or Red arrow ↓ (for sell)
   - Horizontal line at entry price
   - Horizontal line at stop loss price

---

## 🔧 Troubleshooting

### EA Not Trading / No Signals

**Problem:** EA is running but not opening any trades.

**Solutions:**

1. **Be patient:**
   - Strategy requires EMA50/100 crossover (rare event)
   - Check Journal for `[REJECTED]` messages — means crossover detected but alignment failed (correct behavior)
   - Try running on multiple symbols: XAUUSD, EURUSD, GBPUSD simultaneously

2. **Check warmup period:**
   - EA skips first 100 bars
   - If you just attached EA, it needs 100 bars to pass first
   - M1: 100 minutes = 1.5 hours
   - M5: 500 minutes = 8 hours
   - M15: 1500 minutes = 25 hours
   - H1: 100 hours = 4 days

3. **Verify AutoTrading is enabled:**
   - Check toolbar button is GREEN
   - Check EA has smiley face 😊 in chart corner

4. **Check account settings:**
   - Tools → Options → Expert Advisors
   - Verify "Allow automated trading" is checked
   - Verify "Allow WebRequest for listed URL" is checked (if needed)

### EA Shows Sad Face 😟

**Problem:** EA has ⚠️ or 😟 in chart corner.

**Solutions:**
- Check **Experts** tab for error messages
- Common errors:
  - "Not enough money" → Reduce lot size or increase demo balance
  - "Invalid stops" → Broker minimum stop distance issue, reduce risk %
  - "Trade disabled" → Enable AutoTrading button
  - "Off quotes" → Market closed or no prices available

### Trades Losing Money

**Problem:** EA opens trades but they all lose.

**Analysis:**
- This is NORMAL during ranging markets (strategy works in trends)
- Check recent market: trending or ranging?
- EMA crossover strategies perform poorly in sideways markets
- Consider:
  - Running EA only during trending periods
  - Adding trend filter (manual oversight)
  - Reducing risk % to 0.5%

### Stop Loss Hit Immediately

**Problem:** Trade opens and stop loss hits right away.

**Solutions:**
- Market is too volatile for your risk %
- Increase `RiskPercent` to 2% (wider stop)
- Or reduce `LotSize` to 0.05 or 0.01
- Or trade on higher timeframe (H1 instead of M5)

---

## 📊 Performance Monitoring

### Daily Checks

Every day, check:

1. **Account Balance:**
   - Terminal → Trade tab → Top shows Balance, Equity, Margin
   - Is equity growing or shrinking?

2. **Open Trades:**
   - How many trades open?
   - Are stop losses being respected?
   - Is EA closing trades properly?

3. **Journal Messages:**
   - Any errors?
   - Are entry/exit signals logical?

### Weekly Analysis

Every week, analyze:

1. **Win Rate:**
   - History tab → Right-click → "Last Week"
   - Count winning vs losing trades
   - Target: >50% win rate

2. **Profit Factor:**
   - Sum of winning trades / Sum of losing trades
   - Target: >1.5

3. **Max Drawdown:**
   - Lowest equity point from peak
   - Target: <10% of balance

4. **Strategy Performance:**
   - Is EA following rules correctly?
   - Are there any unexpected behaviors?

---

## 🚀 Advanced: Running EA on Multiple Symbols

To maximize opportunities, run EA on multiple charts:

### Multi-Symbol Setup

1. **Create chart for XAUUSD:**
   - File → New Chart → XAUUSD → Set M5
   - Attach EA with RiskPercent=1.0, LotSize=0.10

2. **Create chart for EURUSD:**
   - File → New Chart → EURUSD → Set M15
   - Attach EA with RiskPercent=1.0, LotSize=0.10

3. **Create chart for GBPUSD:**
   - File → New Chart → GBPUSD → Set M15
   - Attach EA with RiskPercent=1.0, LotSize=0.10

**Note:** Each EA instance is independent. MagicNumber ensures they don't interfere.

**Risk Management:**
- Total risk = RiskPercent × Number of symbols
- If running 3 EAs with 1% each, total risk = 3%
- Reduce individual RiskPercent to 0.5% if running many symbols

---

## 📱 Remote Monitoring (Optional)

### Enable MT5 Mobile Notifications

1. **Download MT5 mobile app** (iOS/Android)

2. **In desktop MT5:**
   - Tools → Options → Notifications
   - Enter your MetaQuotes ID (from mobile app)
   - Check "Enable push notifications"

3. **Test notification:**
   - Click "Test" button
   - Check phone for notification

4. **Now you'll receive:**
   - Trade opened notifications
   - Trade closed notifications
   - Stop loss hit notifications

### Email Notifications (Alternative)

You can modify EA code to send emails on trade events (advanced).

---

## 🔒 Safety Guidelines

### Risk Management

- ✅ **Never risk more than 1-2% per trade**
- ✅ **Start with 0.5% risk for first week**
- ✅ **Use demo account for at least 1 month before live**
- ✅ **Monitor daily for first week**
- ✅ **Don't increase lot size after wins (stick to plan)**

### When to Stop EA

Stop EA immediately if:
- ⚠️ Drawdown exceeds 20%
- ⚠️ Win rate drops below 40% after 20+ trades
- ⚠️ EA behaves unexpectedly
- ⚠️ You see errors in Journal/Experts tabs
- ⚠️ Account balance drops 10%+ in one day

**To stop EA:**
- Right-click on chart → Expert Advisors → Remove
- Or click AutoTrading button to turn RED (disables all EAs)

---

## 🎓 What to Expect

### First Week
- **Trades:** 0-5 (depending on market and timeframe)
- **Win Rate:** Unknown (too few trades)
- **Profit:** May be positive or negative (variance)
- **Goal:** Verify EA works correctly, no errors

### First Month
- **Trades:** 10-30 (depending on timeframe)
- **Win Rate:** 45-55% (strategy typical)
- **Profit:** 0-10% gain (or small loss if market ranging)
- **Goal:** Build confidence, understand strategy behavior

### After 3 Months
- **Trades:** 50-100+
- **Win Rate:** Should stabilize around 50-55%
- **Profit:** Positive if market had trends
- **Goal:** Decide if strategy fits your goals

---

## 📋 Quick Checklist

Before leaving EA to run:

- [ ] Demo account with adequate balance ($10,000+ recommended)
- [ ] EA attached to chart
- [ ] AutoTrading button is GREEN
- [ ] EA shows 😊 in chart corner
- [ ] Journal shows "EA Initialised" message
- [ ] Risk % is conservative (1% or less)
- [ ] Lot size is appropriate for account
- [ ] Stop loss is enabled (RiskPercent < 100)
- [ ] Both AllowLong and AllowShort = true
- [ ] Terminal panel open to monitor trades
- [ ] You understand strategy rules
- [ ] You know how to stop EA if needed

---

## 🎯 Summary

**You've just set up a fully automated algo trading bot!**

The EA will now:
✅ Monitor markets 24/7  
✅ Detect EMA crossover signals  
✅ Open trades automatically  
✅ Manage stop losses  
✅ Close trades at exit signals  
✅ Log all activity to Journal  

**Remember:**
- Be patient (signals are rare)
- Monitor daily for first week
- Don't panic on first losing trade
- Strategy works best in trending markets
- Always use demo account for 1+ month before live

**Good luck with your algo trading! 🚀📊**

---

## 📞 Need Help?

Check these if issues arise:
1. **TROUBLESHOOTING.md** — Common problems and solutions
2. **Journal tab** — Error messages and EA logs
3. **Experts tab** — Detailed debugging info
4. **MT5 Community** — https://www.mql5.com/en/forum
