# MT5 EA Troubleshooting Guide

## Common Issues & Solutions

### 1. **"EA not showing in Navigator"**

**Problem:** After copying the .mq5 file, the EA doesn't appear in MT5 Navigator.

**Solutions:**
- Right-click in Navigator → **Refresh**
- Restart MT5 completely
- Verify file is in correct folder: `MQL5/Experts/EMA_Crossover_Strategy.mq5`
- Check file extension is `.mq5` not `.mq5.txt`

---

### 2. **Compilation Errors**

**Problem:** EA fails to compile with errors.

**Solutions:**
- Check you're using **MetaTrader 5** (not MT4 — this is MQ5 format)
- Make sure entire code was copied (file should be ~500+ lines)
- Update MT5 to latest version (Tools → Options → Updates)
- Check the **Errors** tab in MetaEditor for specific line numbers

---

### 3. **"No trading operations allowed" in Journal**

**Problem:** EA loads but shows error: `Trade is disabled`

**Solutions:**
- In MT5, go to **Tools → Options → Expert Advisors**
- Check these boxes:
  - ✅ Allow automated trading
  - ✅ Allow DLL imports (if needed)
  - ✅ Allow WebRequest for listed URL
- Click the **AutoTrading** button in MT5 toolbar (should be GREEN)
- For Strategy Tester: no action needed (always enabled)

---

### 4. **EA Opens No Trades (0 trades in backtest)**

**Problem:** Backtest completes but shows 0 trades.

**Solutions:**

#### Check 1: Enough historical data
- Warmup period = 100 bars by default
- If testing on 1-minute data, you need at least 100+ minutes of data
- If testing on daily data, you need 100+ days
- **Solution:** Extend date range or reduce `WarmupBars` input

#### Check 2: Market conditions
- Strategy requires EMA50 to cross EMA100 (which is rare on ranging markets)
- Try different date ranges with trending markets
- Try different symbols (e.g., XAUUSD often trends more than EURUSD)

#### Check 3: Symbol data quality
- Right-click symbol → History Center → Download missing data
- Some brokers don't have M1 data for old dates — use recent dates instead

#### Check 4: Check Journal tab
- Look for `[ENTRY SIGNAL]` or `[REJECTED]` messages
- If you see `[REJECTED]`, the EMA alignment failed (this is correct behavior)

---

### 5. **Results Don't Match Python Backtest**

**Problem:** MT5 results are different from Python backtest.

**Possible Causes:**

#### Cause 1: Different data source
- Python uses Yahoo Finance or MT5 broker data
- MT5 Strategy Tester uses your broker's historical data
- **Solution:** Use same broker data in both (set Python data_source to "mt5")

#### Cause 2: Different timeframe
- Check that both use same interval (e.g., both M1 or both H1)
- 1-minute in MT5 = "1m" in Python

#### Cause 3: Different date range
- Ensure exact same start/end dates
- Python may have incomplete first/last bars — MT5 uses only complete bars

#### Cause 4: Stop loss calculation
- MT5 stop loss uses broker tick size/value
- Python uses simplified math
- Small differences are normal (±0.5% acceptable)

#### Cause 5: Spread/commission differences
- MT5 Strategy Tester applies spread automatically
- Python backtest doesn't include spread by default
- **Solution:** For exact match, set Python spread = 0 or match MT5 spread settings

---

### 6. **EA Not Closing Trades**

**Problem:** Trades open but never close (or close too late).

**Solutions:**
- Check `AllowLong` and `AllowShort` inputs — both should be `true`
- Verify exit logic in Journal: look for `[EXIT SIGNAL]` messages
- Exit requires EMA20 to cross EMA50 — this can take many bars
- If testing on small date range, exit signal may not occur before data ends

---

### 7. **Lot Size Too Large / Too Small**

**Problem:** EA uses incorrect position size.

**Solutions:**

#### If using `UseFixedLot = true`:
- Set `LotSize` input to desired value (e.g., 0.10)
- Check broker minimum lot: Tools → Symbols → [Symbol] → Properties → Volume Min

#### If using `UseFixedLot = false` (risk-based):
- EA calculates lot size from `RiskPercent`
- Formula: `lot = (balance * risk%) / (stop distance * tick value)`
- If lot = 0, your `RiskPercent` is too small
- **Solution:** Increase `RiskPercent` or use fixed lot

---

### 8. **"Invalid Stops" Error**

**Problem:** Trade rejected with "invalid stops" error.

**Solutions:**
- Stop loss is too close to entry price
- Broker minimum stop distance: check symbol properties → Stops Level
- **Solution:** Increase `RiskPercent` (larger risk = wider stop)
- Or edit code to add minimum stop distance check

---

### 9. **Spread Too Wide in Backtest**

**Problem:** Every trade loses money due to high spread.

**Solutions:**
- Strategy Tester → Settings → Use date: **Custom period**
- Spread setting: **Current** (uses current spread) or **Fixed** (set manually)
- For realistic backtest, use broker's average spread
- XAUUSD typical spread: 20–50 points (0.2–0.5 USD)

---

### 10. **Visual Mode Too Slow**

**Problem:** Backtest in visual mode takes forever.

**Solutions:**
- Increase **visualization speed** slider (bottom right of Strategy Tester)
- Disable visual mode: uncheck "Visual mode" checkbox
- Use "Open prices only" model instead of "Every tick" (much faster)

---

## How to Enable Debug Output

If EA is not working as expected, check the **Journal** and **Experts** tabs in Strategy Tester for detailed logs.

The EA prints these messages:
- `[ENTRY SIGNAL]` — when EMA crossover detected
- `[EXIT SIGNAL]` — when exit condition met
- `[REJECTED]` — when crossover found but alignment failed
- `[TRADE OPENED]` — when position opened successfully
- `[TRADE CLOSED]` — when position closed
- `[STOP LOSS]` — when stop loss hit (Python version only)

To add more debug output, edit the EA code and add `Print()` statements.

---

## Recommended Testing Process

1. **Start with small date range** (1 week) to verify EA works
2. **Check Journal tab** for signal messages
3. **Verify trades open/close correctly** (Results tab)
4. **Expand date range** once confirmed working
5. **Optimize parameters** using MT5 Optimization feature

---

## Quick Verification Checklist

Before reporting issues, verify:

- ✅ MT5 version is latest (Help → About)
- ✅ EA compiled successfully (0 errors)
- ✅ AutoTrading enabled (green button)
- ✅ Symbol has historical data (History Center)
- ✅ Date range includes 100+ bars (for warmup)
- ✅ Backtest model is "Open prices only" or "Every tick"
- ✅ Journal tab shows `[ENTRY SIGNAL]` messages (if not, extend date range)
- ✅ Both `AllowLong` and `AllowShort` are `true`

---

## Still Having Issues?

1. Check the **Experts** tab for error codes
2. Post error code/message in trading forums (search `"MT5 error [code]"`)
3. Compare with Python backtest using same symbol/dates/timeframe
4. Try different symbol (EURUSD is most reliable for testing)
5. Try different timeframe (H1 is easier than M1 for beginners)

---

## MT5 Error Codes Reference

Common error codes you might see:

| Code | Name | Solution |
|------|------|----------|
| 10004 | TRADE_RETCODE_REQUOTE | Market moved, retry automatically |
| 10006 | TRADE_RETCODE_REJECT | Broker rejected, check margin |
| 10013 | TRADE_RETCODE_INVALID_VOLUME | Lot size wrong, check symbol min/max |
| 10014 | TRADE_RETCODE_INVALID_PRICE | Price invalid, check spread |
| 10015 | TRADE_RETCODE_INVALID_STOPS | Stop loss too close, increase risk% |
| 10016 | TRADE_RETCODE_TRADE_DISABLED | Enable AutoTrading |
| 10019 | TRADE_RETCODE_MARKET_CLOSED | Testing outside market hours |
| 10027 | TRADE_RETCODE_AUTOTRADING_DISABLED | Click AutoTrading button |

For full list: https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes
