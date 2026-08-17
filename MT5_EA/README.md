# EMA Crossover Strategy - MetaTrader 5 Expert Advisor

Complete MT5 EA implementation of the EMA 20/50/100 crossover strategy for algorithmic trading.

---

## 📦 What's Included

| File | Description |
|------|-------------|
| `EMA_Crossover_Strategy.mq5` | Main Expert Advisor code (ready to use) |
| `HOW_TO_USE_IN_MT5.md` | Step-by-step installation and usage guide |
| `TROUBLESHOOTING.md` | Common issues and solutions |
| `STRATEGY_LOGIC_COMPARISON.md` | Python vs MT5 logic comparison (verification) |
| `README.md` | This file |

---

## 🚀 Quick Start (3 Steps)

### Step 1: Install
1. Open MT5 → **File → Open Data Folder**
2. Navigate to `MQL5 → Experts`
3. **Copy** `EMA_Crossover_Strategy.mq5` into that folder

### Step 2: Compile
1. Open **Navigator** (Ctrl+N) → Expert Advisors
2. Double-click `EMA_Crossover_Strategy` → Opens MetaEditor
3. Press **F7** to compile
4. Verify: **0 errors, 0 warnings**

### Step 3: Backtest
1. Press **Ctrl+R** → Strategy Tester
2. Select EA: `EMA_Crossover_Strategy`
3. Symbol: `XAUUSD` (or any symbol)
4. Period: `M1` (1-minute)
5. Click **Start** ▶

**Done!** Results appear in the Results, Graph, and Report tabs.

---

## 📊 Strategy Overview

### Entry Rules

**LONG (Buy):**
- EMA50 crosses **ABOVE** EMA100 (on bar close)
- Confirmed by: EMA20 > EMA50 > EMA100
- Trade opens at **next bar's OPEN** price

**SHORT (Sell):**
- EMA50 crosses **BELOW** EMA100 (on bar close)
- Confirmed by: EMA20 < EMA50 < EMA100
- Trade opens at **next bar's OPEN** price

### Exit Rules

**LONG Exit:**
- EMA20 crosses **BELOW** EMA50
- Position closes at **next bar's OPEN** price

**SHORT Exit:**
- EMA20 crosses **ABOVE** EMA50
- Position closes at **next bar's OPEN** price

### Risk Management

- **Stop Loss:** Based on % of account balance (default 1%)
- **Position Sizing:** Fixed lot (default) or risk-based
- **No Take Profit:** Exit managed by EMA signals only

---

## ⚙️ Input Parameters

Open Strategy Tester → **Settings** tab to configure:

### Risk Management
| Parameter | Default | Description |
|-----------|---------|-------------|
| `RiskPercent` | 1.0 | Risk % per trade (of account balance) |
| `LotSize` | 0.10 | Fixed lot size (for forex/commodities) |
| `UseFixedLot` | true | true = fixed lot, false = risk-based |

### EMA Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `EMA_Fast` | 20 | Fast EMA period |
| `EMA_Mid` | 50 | Mid EMA period |
| `EMA_Slow` | 100 | Slow EMA period |
| `WarmupBars` | 100 | Bars to skip at start (EMA stabilization) |

### Trade Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `TradeComment` | "EMA_Cross_EA" | Comment on each trade |
| `MagicNumber` | 202602 | Unique ID for this EA |
| `AllowLong` | true | Enable long (buy) trades |
| `AllowShort` | true | Enable short (sell) trades |

---

## 🎯 Recommended Settings

### For XAUUSD (Gold) — Scalping
```
Symbol: XAUUSD
Timeframe: M1 or M5
Deposit: 100,000 USD
Risk: 1%
Lot Size: 0.10
Model: Open prices only (fast)
```

### For EURUSD — Intraday
```
Symbol: EURUSD
Timeframe: M15 or H1
Deposit: 10,000 USD
Risk: 1-2%
Lot Size: 0.10
Model: Open prices only
```

### For Daily Swing Trading
```
Symbol: Any
Timeframe: D1
Risk: 1%
Model: Open prices only
```

---

## ✅ Verification

This EA **exactly matches** the Python backtest implementation in `app.py`.

See `STRATEGY_LOGIC_COMPARISON.md` for side-by-side code comparison.

### Expected Results Match
When using:
- Same symbol
- Same timeframe
- Same dates
- Same initial capital
- Same risk %
- Same lot size
- Python data source = "mt5"

Results should match **within ±2-5%** due to:
- Broker spread (MT5 includes it, Python doesn't by default)
- Tick-level precision differences
- Commission settings

### Verification Steps
1. Run Python backtest: symbol=XAUUSD, dates=2026-08-03 to 2026-08-10, interval=1m
2. Run MT5 backtest: same symbol, dates, period=M1
3. Compare **Total Trades** (must be exact)
4. Compare **Net Profit** (within ±5%)
5. Compare **Win Rate** (within ±2%)

---

## 🛠️ Troubleshooting

Common issues? See `TROUBLESHOOTING.md`

Quick checks:
- ✅ EA compiled without errors?
- ✅ AutoTrading button is GREEN?
- ✅ Symbol has historical data? (History Center)
- ✅ Date range includes 100+ bars?
- ✅ Both `AllowLong` and `AllowShort` = true?

---

## 📈 Performance Tips

### For Better Results
1. **Use trending markets** — Strategy works best in trends, not ranges
2. **Test different timeframes** — M1 for scalping, H1 for intraday, D1 for swing
3. **Optimize parameters** — Use MT5 Optimization feature (Forward tab)
4. **Adjust risk %** — Higher risk = larger positions = higher profit/loss
5. **Choose liquid symbols** — XAUUSD, EURUSD, GBPUSD have tight spreads

### For Faster Backtests
1. Use **"Open prices only"** model (sufficient for this strategy)
2. Disable **visual mode**
3. Use smaller date ranges during testing
4. Test on higher timeframes first (D1 faster than M1)

---

## 🔄 From Backtest to Live Trading

### Before Going Live
1. ✅ Backtest shows consistent profit over 6+ months
2. ✅ Drawdown is acceptable (<20%)
3. ✅ Win rate >50% or profit factor >1.5
4. ✅ Tested on multiple symbols
5. ✅ Forward test on demo account for 1 month

### Steps to Deploy
1. **Demo First:** Drag EA onto chart in demo account
2. **Monitor:** Watch for 1-2 weeks, verify trades match backtest
3. **Small Capital:** Start with small account (risk only what you can lose)
4. **Gradual Scale:** Increase position size gradually
5. **Risk Management:** Never risk more than 1-2% per trade

---

## 🚨 Important Warnings

⚠️ **Past performance does not guarantee future results**

⚠️ **This EA is provided for educational purposes**

⚠️ **Always test on demo account before live trading**

⚠️ **Trading carries risk of loss — only trade with funds you can afford to lose**

⚠️ **No EA is profitable in all market conditions**

---

## 📚 Additional Resources

### MT5 Documentation
- Official MQL5 Docs: https://www.mql5.com/en/docs
- Strategy Tester Guide: https://www.mql5.com/en/articles/1486
- Trade Functions: https://www.mql5.com/en/docs/trading

### Strategy Resources
- EMA Indicator: https://www.mql5.com/en/docs/indicators/ima
- Order Management: https://www.mql5.com/en/articles/211
- Risk Management: https://www.mql5.com/en/articles/2555

---

## 🤝 Support

Having issues?

1. Check `TROUBLESHOOTING.md` first
2. Verify all files are in correct folders
3. Check MT5 Journal and Experts tabs for errors
4. Post error codes in MT5 forums (include error number)
5. Compare with Python backtest results

---

## 📝 Version History

**Version 1.00** (Current)
- Initial release
- EMA 20/50/100 crossover strategy
- Risk-based stop loss
- Fixed and dynamic lot sizing
- Matches Python backtest logic exactly
- Full debug logging

---

## 📄 License

This EA is provided as-is for educational purposes.

You may:
- ✅ Use for personal trading
- ✅ Modify for your own needs
- ✅ Backtest and optimize
- ✅ Use on demo and live accounts

You may not:
- ❌ Sell or redistribute commercially
- ❌ Claim as your own work
- ❌ Remove copyright notices

---

## 🎯 Quick Reference Card

**File Location:**
```
MT5 Data Folder/MQL5/Experts/EMA_Crossover_Strategy.mq5
```

**Compilation:**
```
MetaEditor → Open EA → Press F7 → Check "0 errors"
```

**Strategy Tester:**
```
Ctrl+R → Select EA → Set Symbol/Period → Start
```

**Default Settings:**
```
Risk: 1% | Lot: 0.10 | EMA: 20/50/100 | Warmup: 100 bars
```

**Strategy Summary:**
```
Entry:  EMA50 crosses EMA100 + alignment check
Exit:   EMA20 crosses EMA50
Timing: Signal on close, execute on next open
```

---

## ✨ You're Ready!

Everything you need is in this folder:
1. **Code** — `EMA_Crossover_Strategy.mq5`
2. **Installation Guide** — `HOW_TO_USE_IN_MT5.md`
3. **Troubleshooting** — `TROUBLESHOOTING.md`
4. **Verification** — `STRATEGY_LOGIC_COMPARISON.md`

**Start with HOW_TO_USE_IN_MT5.md** for step-by-step instructions.

Good luck with your algo trading! 📊🚀
