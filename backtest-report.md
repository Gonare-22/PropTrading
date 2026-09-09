# XAUUSD Strategy Backtest

_Generated 2026-09-09 11:31 UTC · long/short enabled_

## Period

- **Data available:** 2025-01-01 18:00 → 2025-12-31 16:57
- **Backtest window:** 2025-01-01 18:00 → 2025-12-31 16:57  _(full range — pass `--from` / `--to` to narrow)_
- Indicators and Stoch-RSI permission warm up on bars before the window start; any open position is closed at the window end.

## Rules

- **Entry LONG** — EMA20 crosses above EMA50 · Stoch-RSI long permission active · CHOP ≤ 50
- **Entry SHORT** — EMA20 crosses below EMA50 · Stoch-RSI short permission active · CHOP ≤ 50
- **Exit** — opposite EMA20/50 cross only (no CHOP / Stoch-RSI exit)
- **Stoch-RSI permission** — long arms at K ≥ 79, holds while K > 50, disarms on K < 50 (mirror for short at K ≤ 21 / K < 50)

## Config

- **Capital:** $10,000 · **sizing:** 100% of equity
- **Costs:** spread 0 pt · slippage 0 pt · commission $0/lot/side  _(frictionless — the default)_
- **Risk mgmt:** none — exit on opposite EMA cross only (the spec)
- **Execution:** fill on signal bar close
- Raw params: `{"emaFast":20,"emaSlow":50,"rsiLength":28,"stochLength":28,"kSmooth":6,"dSmooth":6,"longLevel":80,"shortLevel":20,"tolerance":1,"chopLength":14,"chopMax":50,"allowLong":true,"allowShort":true,"from":null,"to":null,"capital":10000,"sizing":"percent","percentEquity":100,"lots":0.1,"contractSize":100,"cashPerTrade":10000,"riskPercent":1,"spread":0,"slippage":0,"commissionPerLot":0,"stopLoss":0,"stopMode":"points","takeProfit":0,"tpMode":"points","trailStop":0,"trailMode":"points","atrLength":14,"fillOn":"close","allowFlip":true,"sessionFilter":false,"sessionStart":0,"sessionEnd":24}`

## Results by timeframe

| TF | Bars | Period | Net P&L | Return | Buy & Hold | Max DD | Trades | Win % | Long/Short | PF | Sharpe~ | Exposure |
|----|------|--------|---------|--------|-----------|--------|--------|-------|-----------|-----|---------|----------|
| 1m | 353,951 | 2025-01-01 → 2025-12-31 | $328 | +3.28% | +64.51% | -14.85% | 3321 | 31% | 1692/1629 | 1.01 | 0.31 | 53% |
| 5m | 70,810 | 2025-01-01 → 2025-12-31 | $1,636 | +16.36% | +64.52% | -11.99% | 655 | 30% | 313/342 | 1.15 | 1.18 | 53% |
| 15m | 23,606 | 2025-01-01 → 2025-12-31 | $1,898 | +18.98% | +64.53% | -11.34% | 190 | 35% | 97/93 | 1.31 | 1.38 | 49% |
| 30m | 11,804 | 2025-01-01 → 2025-12-31 | $285 | +2.85% | +64.61% | -17.36% | 101 | 28% | 44/57 | 0.98 | 0.28 | 48% |
| 1H | 5,905 | 2025-01-01 → 2025-12-31 | $2,135 | +21.35% | +64.60% | -6.99% | 36 | 44% | 18/18 | 1.94 | 1.53 | 44% |
| 2H | 3,082 | 2025-01-01 → 2025-12-31 | $16 | +0.16% | +64.50% | -12.20% | 21 | 29% | 8/13 | 0.99 | 0.08 | 39% |
| 4H | 1,593 | 2025-01-01 → 2025-12-31 | -$260 | -2.60% | +64.50% | -21.96% | 18 | 17% | 9/9 | 0.88 | -0.10 | 60% |
| 1D | 312 | 2025-01-01 → 2025-12-31 | $0 | +0.00% | +63.96% | +0.00% | 0 | 0% | 0/0 | 0.00 | 0.00 | 0% |
| 1W | 53 | 2024-12-30 → 2025-12-29 | $0 | +0.00% | +63.87% | +0.00% | 0 | 0% | 0/0 | 0.00 | 0.00 | 0% |

## 1-minute detail

- Window: **2025-01-01 18:00 → 2025-12-31 16:57** (353,951 bars)
- Net P&L: **$328** → final equity **$10,328** from $10,000 · max drawdown -$1,779 (-14.85%)
- Avg trade $0 (+0.00%) · avg win $23 · avg loss -$10
- Best $280 · worst -$109 · avg hold 57 bars
- Long win rate 35% · short win rate 27%
- Exits by reason: signal 3321
- Position still open at window end: long from 2025-12-31T16:40:00 ($7)

### Monthly (by exit date)

| Month | Trades | Sum of trade returns | Win % |
|-------|--------|----------------------|-------|
| 2025-01 | 255 | +2.31% | 31% |
| 2025-02 | 238 | +2.35% | 34% |
| 2025-03 | 274 | -1.29% | 33% |
| 2025-04 | 285 | +4.64% | 29% |
| 2025-05 | 265 | +5.53% | 32% |
| 2025-06 | 250 | +3.34% | 36% |
| 2025-07 | 311 | -2.66% | 31% |
| 2025-08 | 303 | -1.08% | 29% |
| 2025-09 | 296 | +0.50% | 30% |
| 2025-10 | 295 | -7.98% | 29% |
| 2025-11 | 268 | +0.43% | 31% |
| 2025-12 | 282 | -2.08% | 28% |

## Caveats

- No spread, commission or slippage. On XAUUSD 1m a ~20–30c round-trip spread alone would swamp the average trade — treat 1m results as directional research, not a live expectancy.
- Fully-invested sizing; a fixed-risk / ATR-stop model would change the equity curve and drawdown materially.
- Every timeframe is bucketed from the same 1m feed by clock time (see `scripts/aggregate.mjs`); weekly bars start Monday 00:00.
- 1D / 1W show 0 trades: EMA50 + Stoch-RSI warmup consumes most of the short series.