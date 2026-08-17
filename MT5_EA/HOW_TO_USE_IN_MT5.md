# How to Run EMA Crossover Strategy in MT5

## Step 1 — Copy the EA file into MT5

1. Open **MetaTrader 5**
2. Click top menu: **File → Open Data Folder**
3. Navigate to: `MQL5 → Experts`
4. **Copy** the file `EMA_Crossover_Strategy.mq5` into that folder
5. Go back to MT5, press **Ctrl+R** (or View → Strategy Tester) to open the tester

---

## Step 2 — Compile the EA

1. In MT5, open the **Navigator** panel (Ctrl+N)
2. Under **Expert Advisors**, right-click → **Refresh**
3. Double-click `EMA_Crossover_Strategy` to open the **MetaEditor**
4. Press **F7** (or click the Compile button ▶)
5. You should see **0 errors, 0 warnings** in the Errors tab at the bottom

   > If you see errors, make sure you saved the `.mq5` file correctly and the file is in the `MQL5/Experts/` folder.

---

## Step 3 — Run in Strategy Tester (Backtesting)

1. Press **Ctrl+R** in MT5 to open the **Strategy Tester**
2. Set these fields:

   | Field              | Value                          |
   |--------------------|-------------------------------|
   | Expert Advisor     | `EMA_Crossover_Strategy`      |
   | Symbol             | `XAUUSD` (or any symbol)      |
   | Period/Timeframe   | `M1` (1-minute) or `H1`      |
   | Model              | **Every tick based on real ticks** (most accurate) or **Open prices only** (faster) |
   | Date Range         | Your desired backtest dates   |
   | Deposit            | Your initial capital (e.g. 100000) |
   | Currency           | USD                           |
   | Leverage           | 1:100 (or your broker's)      |

3. Click the **Settings** tab and set your inputs:

   | Input Parameter    | Default | Description                       |
   |--------------------|---------|-----------------------------------|
   | `RiskPercent`      | `1.0`   | % of balance to risk per trade    |
   | `LotSize`          | `0.10`  | Fixed lot size (if UseFixedLot=true) |
   | `UseFixedLot`      | `true`  | true = fixed lot, false = risk-based |
   | `EMA_Fast`         | `20`    | EMA 20 period                     |
   | `EMA_Mid`          | `50`    | EMA 50 period                     |
   | `EMA_Slow`         | `100`   | EMA 100 period                    |
   | `WarmupBars`       | `100`   | Bars to skip at start             |
   | `AllowLong`        | `true`  | Allow buy trades                  |
   | `AllowShort`       | `true`  | Allow sell trades                 |

4. Click **Start** ▶

---

## Step 4 — View Results

After the backtest completes, check these tabs in the Strategy Tester:

- **Results** tab — list of all trades
- **Graph** tab — equity curve
- **Report** tab — full statistics (profit factor, drawdown, win rate, etc.)

---

## Strategy Logic (matches Python backtest exactly)

```
LONG ENTRY:
  → EMA50 crosses ABOVE EMA100 (on bar close)
  → AND EMA20 > EMA50 > EMA100 (alignment confirmed)
  → Trade opens at NEXT bar's OPEN price

SHORT ENTRY:
  → EMA50 crosses BELOW EMA100 (on bar close)
  → AND EMA20 < EMA50 < EMA100 (alignment confirmed)
  → Trade opens at NEXT bar's OPEN price

LONG EXIT:
  → EMA20 crosses BELOW EMA50
  → Position closes at NEXT bar's OPEN price

SHORT EXIT:
  → EMA20 crosses ABOVE EMA50
  → Position closes at NEXT bar's OPEN price

STOP LOSS:
  → Calculated as RiskPercent % of account balance
  → Example: 1% risk, $100,000 balance → max loss = $1,000 per trade
```

---

## Recommended Backtesting Settings

### For XAUUSD (Gold) — 1-minute scalping
- Symbol: `XAUUSD`
- Timeframe: `M1` or `M5`
- Model: `Open prices only` (fast) or `Every tick` (accurate)
- Deposit: 100,000 USD
- Risk per trade: 1%
- Lot size: 0.10

### For EURUSD / Forex — Intraday
- Symbol: `EURUSD`
- Timeframe: `M15` or `H1`
- Model: `Open prices only`
- Deposit: 10,000 USD
- Risk per trade: 1–2%
- Lot size: 0.10

### For Daily swing trading
- Symbol: Any
- Timeframe: `D1`
- Model: `Open prices only`
- Risk per trade: 1%

---

## Tips for New MT5 Users

- **"Open prices only"** model is fastest and sufficient because this strategy only acts on bar OPEN prices (no intrabar logic needed)
- Make sure the symbol you test has **historical data** downloaded. Right-click the symbol → History Center → Download
- After backtesting, you can drag the EA onto a live chart to run it in **Demo mode** (paper trading)
- The `MagicNumber` (202602) uniquely identifies trades from this EA — don't change it unless running multiple EAs on the same account

---

## File Location Summary

```
MT5 Data Folder/
└── MQL5/
    └── Experts/
        └── EMA_Crossover_Strategy.mq5   ← copy this file here
```

To find your MT5 Data Folder:
- MT5 menu → File → Open Data Folder
