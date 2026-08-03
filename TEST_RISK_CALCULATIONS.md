# Risk Management Test Results

## How to Test

1. **Visit test endpoint in browser:** http://localhost:8000/test-risk-calc
   - Shows example calculations for different risk percentages

2. **Run actual backtest:**
   - Initial Capital: ₹100,000
   - Risk Per Trade: 5%
   - Check "Capital Used" column in trade table

## Expected Results

### For Stocks/Indices (e.g., Nifty 50)
**Initial Capital:** ₹100,000  
**Entry Price:** ₹24,000 (example)

| Risk % | Capital Per Trade | Position Size | Example |
|--------|-------------------|---------------|---------|
| 3% | ₹3,000 | 0.125 units | Very conservative |
| 5% | ₹5,000 | 0.208 units | Recommended |
| 10% | ₹10,000 | 0.417 units | Moderate |
| 20% | ₹20,000 | 0.833 units | Aggressive |
| 100% | ₹100,000 | 4.167 units | Full capital |

### For Forex (e.g., EUR/USD)
**Initial Capital:** ₹100,000  
**Entry Price:** 1.08

| Risk % | Capital Per Trade | Units | Standard Lots |
|--------|-------------------|-------|---------------|
| 3% | ₹3,000 | 2,778 | 0.0278 |
| 5% | ₹5,000 | 4,630 | 0.0463 |
| 10% | ₹10,000 | 9,259 | 0.0926 |
| 100% | ₹100,000 | 92,593 | 0.9259 |

## Verification Steps

1. **Open browser:** http://localhost:8000
2. **Set:**
   - Symbol: Nifty 50
   - Initial Capital: 100000
   - Risk Per Trade: 5%
3. **Run backtest**
4. **Check trade table:**
   - "Capital Used" should be ~₹5,000 (5% of capital)
   - "Risk %" should show 5.0%
   - Position sizes should be small fractions, not full units

## What Should Work

✅ **Risk percentage** is applied to each trade  
✅ **Capital Used** = Current Equity × Risk%  
✅ **Position Size** = Capital Used / Entry Price  
✅ **Dynamic adjustment** - uses current equity, not initial  
✅ **Forex lot sizing** - respects risk percentage  
✅ **Visual preview** - shows capital per trade as you type

## What Changed

**Before:** Always used 100% of capital per trade  
**After:** Uses configurable percentage (default 100% for backward compatibility)

**Formula:**
```
Trade Capital = Current Equity × (Risk% / 100)
Position Size = Trade Capital / Entry Price
PnL = Position Size × (Exit Price - Entry Price)
```
