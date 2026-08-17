# MT5 EA Installation Checklist

Use this checklist to ensure your EA is installed and working correctly.

---

## Pre-Installation Requirements

- [ ] MetaTrader 5 installed (not MT4)
- [ ] MT5 version is up-to-date (Help → About → Check version)
- [ ] You have a demo or live account connected
- [ ] You can see price charts (if not, connect to a broker)

---

## Installation Steps

### Step 1: Locate Data Folder
- [ ] Open MT5
- [ ] Click **File → Open Data Folder**
- [ ] Data folder opens in Windows Explorer

### Step 2: Copy EA File
- [ ] Navigate to `MQL5 → Experts` folder
- [ ] Copy `EMA_Crossover_Strategy.mq5` into this folder
- [ ] File is visible in the folder (not hidden)
- [ ] File extension is `.mq5` (not `.mq5.txt`)

### Step 3: Refresh MT5
- [ ] In MT5, open **Navigator** panel (Ctrl+N or View → Navigator)
- [ ] Right-click anywhere in Navigator → **Refresh**
- [ ] Under **Expert Advisors**, you see `EMA_Crossover_Strategy`

---

## Compilation Steps

### Step 4: Open MetaEditor
- [ ] In Navigator, under Expert Advisors, **double-click** `EMA_Crossover_Strategy`
- [ ] MetaEditor opens with the EA code visible
- [ ] Code has syntax highlighting (colors)

### Step 5: Compile EA
- [ ] Press **F7** (or click Compile button ▶ in toolbar)
- [ ] Bottom panel shows "Compilation" tab
- [ ] Result shows: **0 errors, 0 warnings** ✅
- [ ] If errors → Check TROUBLESHOOTING.md

### Step 6: Verify Compiled File
- [ ] In MetaEditor: File → Open Data Folder
- [ ] Navigate to `MQL5 → Experts`
- [ ] You see TWO files:
  - `EMA_Crossover_Strategy.mq5` (source code)
  - `EMA_Crossover_Strategy.ex5` (compiled, auto-generated)

---

## First Backtest

### Step 7: Open Strategy Tester
- [ ] In MT5, press **Ctrl+R** (or View → Strategy Tester)
- [ ] Strategy Tester panel opens at bottom of screen
- [ ] You see tabs: Settings, Inputs, Optimization, etc.

### Step 8: Configure Test
- [ ] **Expert Advisor** dropdown: Select `EMA_Crossover_Strategy`
- [ ] **Symbol**: Select `XAUUSD` (or `EURUSD` if XAUUSD not available)
- [ ] **Period**: Select `M1` (1-minute) or `H1` (1-hour)
- [ ] **Date Range**: Select recent dates (last 1 week for M1, last 3 months for H1)
- [ ] **Model**: Select `Open prices only` (fastest)
- [ ] **Deposit**: Enter `100000`
- [ ] **Currency**: `USD`
- [ ] **Leverage**: `1:100` (or your broker's default)

### Step 9: Check Inputs (Optional)
- [ ] Click **Inputs** tab in Strategy Tester
- [ ] Verify default values:
  - `RiskPercent = 1.0`
  - `LotSize = 0.10`
  - `UseFixedLot = true`
  - `EMA_Fast = 20`
  - `EMA_Mid = 50`
  - `EMA_Slow = 100`
  - `WarmupBars = 100`
  - `AllowLong = true`
  - `AllowShort = true`
- [ ] If values wrong, change them and click OK

### Step 10: Run Backtest
- [ ] In Strategy Tester Settings tab, click **Start** button ▶
- [ ] Progress bar starts moving
- [ ] Wait for completion (may take 30 seconds to 5 minutes depending on date range)
- [ ] Progress bar reaches 100%
- [ ] "Backtest completed" message appears

---

## Verify Results

### Step 11: Check Results Tab
- [ ] Click **Results** tab in Strategy Tester
- [ ] You see a list of trades (if any)
- [ ] Each trade shows: Time, Deal, Symbol, Type, Volume, Price, S/L, T/P, Profit
- [ ] If 0 trades → See troubleshooting section below

### Step 12: Check Graph Tab
- [ ] Click **Graph** tab in Strategy Tester
- [ ] You see equity curve (green line)
- [ ] Balance line (blue) shows step changes at each trade
- [ ] If graph is flat → No trades occurred (see troubleshooting)

### Step 13: Check Report Tab
- [ ] Click **Report** tab in Strategy Tester
- [ ] You see detailed statistics:
  - Total Net Profit
  - Gross Profit / Gross Loss
  - Profit Factor
  - Total Trades
  - Winning Trades / Losing Trades
  - Win Rate %
  - Maximum Drawdown
- [ ] Take screenshot for your records

### Step 14: Check Journal Tab
- [ ] Click **Journal** tab in Strategy Tester
- [ ] Look for EA initialization message:
  ```
  ==============================================
  EMA Crossover Strategy EA Initialised
  Symbol:    XAUUSD
  Timeframe: M1
  ==============================================
  ```
- [ ] If you see errors → Note error code and check TROUBLESHOOTING.md

---

## Troubleshooting

### If 0 Trades Generated

**Possible Causes:**
1. **Not enough data:** Need minimum 100 bars (WarmupBars setting)
   - **Fix:** Extend date range (e.g., 1 week for M1, 3 months for H1)

2. **No EMA crossovers in date range:** Strategy requires EMA50/100 crossover (rare event)
   - **Fix:** Try different dates or different symbol (XAUUSD trends more than EURUSD)

3. **Missing historical data:** Symbol doesn't have data for selected dates
   - **Fix:** Tools → History Center → Select symbol → Download
   - **Or:** Use more recent dates (last 30 days)

4. **EMA alignment filter rejected signals:** Strategy requires specific EMA order
   - **Fix:** This is correct behavior — check Journal for `[REJECTED]` messages
   - Try longer date range to find valid signals

### If Compilation Errors

**Error:** `'something' - undeclared identifier`
- **Fix:** Code file is incomplete — re-copy entire .mq5 file

**Error:** `'OnTick' - function not defined`
- **Fix:** You're using MT4, not MT5 — download MetaTrader 5

**Error:** `unexpected end of file`
- **Fix:** Code file was truncated — ensure all 500+ lines copied

### If EA Not Showing in Navigator

- **Fix 1:** Right-click in Navigator → Refresh
- **Fix 2:** Restart MT5 completely
- **Fix 3:** Check file is in correct folder: `MQL5/Experts/` (not `MQL5/Scripts/` or `MQL5/Indicators/`)
- **Fix 4:** Check file extension is `.mq5` (Windows may hide extensions — enable "Show file extensions")

---

## Optional: Visual Backtest

Want to watch the EA trade in real-time?

### Enable Visual Mode
- [ ] In Strategy Tester Settings tab, check **Visual mode** checkbox
- [ ] Click **Start** button ▶
- [ ] Chart appears showing price action
- [ ] EA trades appear as arrows on chart
- [ ] Adjust speed with slider (bottom right)

**Note:** Visual mode is MUCH slower but useful for learning how the strategy works.

---

## Optional: Forward Testing (Demo Account)

After backtesting, test on demo account:

### Deploy to Chart
- [ ] Open a chart: File → New Chart → Select symbol (e.g., XAUUSD)
- [ ] Set timeframe: Click timeframe button (M1, M5, H1, etc.)
- [ ] In Navigator, drag `EMA_Crossover_Strategy` onto the chart
- [ ] EA settings dialog appears
- [ ] Configure inputs (RiskPercent, LotSize, etc.)
- [ ] Check "Allow AutoTrading" checkbox
- [ ] Click **OK**
- [ ] EA appears in top-right corner of chart with smiley face 😊
- [ ] Click **AutoTrading** button in MT5 toolbar (must be GREEN)

### Monitor EA
- [ ] Check **Terminal** panel (Ctrl+T or View → Terminal)
- [ ] **Trade** tab shows open positions (if any)
- [ ] **History** tab shows closed trades
- [ ] **Journal** tab shows EA messages (`[ENTRY SIGNAL]`, etc.)
- [ ] **Experts** tab shows EA logs

**Let EA run for 1-2 weeks to verify it works as expected before considering live trading.**

---

## Success Criteria

Your EA is working correctly if:

✅ Compiles with 0 errors  
✅ Backtest generates trades (>0 trades)  
✅ Equity curve is not flat  
✅ Journal shows `[ENTRY SIGNAL]` messages  
✅ Results tab shows trade details  
✅ Report tab shows statistics  

---

## Next Steps

After completing this checklist:

1. **Read README.md** — Overview of strategy and features
2. **Try different settings** — Optimize RiskPercent, EMA periods, etc.
3. **Test multiple symbols** — EURUSD, GBPUSD, BTCUSD, etc.
4. **Test multiple timeframes** — M1, M5, M15, H1, D1
5. **Compare with Python backtest** — See STRATEGY_LOGIC_COMPARISON.md
6. **Forward test on demo** — Run for 1+ month before live
7. **Read TROUBLESHOOTING.md** — Common issues and solutions

---

## Verification Complete ✅

If all checkboxes above are checked, your EA is:
- ✅ Correctly installed
- ✅ Successfully compiled
- ✅ Working in Strategy Tester
- ✅ Ready for optimization and forward testing

**Congratulations!** You're ready to backtest and optimize your EMA Crossover Strategy. 🎉

---

## Support Resources

- **MT5 Official Docs:** https://www.mql5.com/en/docs
- **Strategy Tester Guide:** https://www.mql5.com/en/articles/1486
- **MQL5 Forum:** https://www.mql5.com/en/forum
- **Troubleshooting:** See `TROUBLESHOOTING.md` in this folder

---

**Pro Tip:** Save this checklist and reuse it whenever you install a new EA or update this one.
