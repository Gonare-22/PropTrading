# XAU/USD Terminal

A gold (XAUUSD) analytics terminal built with **React + Vite + Tailwind CSS**,
charting on **TradingView Lightweight Charts**. Candlesticks, technical overlays,
Stoch-RSI / Choppiness panes, and a long/short strategy backtester — all running
on 2025 spot-gold price data.

## Features

- **TradingView Lightweight Charts** — real crosshair, scroll/pinch zoom, drag
  pan, price + time scales, an OHLC / indicator legend, and backtest markers on
  the candles: **▲ BUY** (open long) / **▼ SELL** (open short) arrows, and **EXIT**
  circles coloured green (win) / red (loss) with the trade's $ P&L. Zoom in and
  each marker shows its BUY / SELL / EXIT label.
- **Timeframes:** 1m, 5m, 15m, 30m, 1H, 2H, 4H, 1D, 1W — all aggregated from the
  ~354k-bar 2025 one-minute series.
- **Overlays:** EMA 20 / EMA 50 (the strategy pair), SMA 20, Bollinger Bands.
- **Indicator panes:** Stoch RSI (K/D with configurable levels) and Choppiness
  Index with its trade-permission threshold, stacked under the price pane.
- **Strategy backtester** — the EMA 20/50 crossover strategy with a stateful
  Stoch-RSI entry-permission filter and a Choppiness Index filter, long **and**
  short. Every indicator parameter is an input. Reports total return,
  buy-and-hold benchmark, max drawdown, win rate, profit factor, long/short
  split, average trade, exposure and a rough Sharpe, plus a date-stamped equity
  curve (hover for strategy vs buy-and-hold value on any date), a trade blotter,
  BUY/SELL/EXIT marks on the chart, a **From / To date window** (with
  quarter/half-year shortcuts), and a one-click **run-across-all-timeframes**
  comparison.

Indicators and the backtest all run in the browser. The price chart is
TradingView's [Lightweight Charts](https://github.com/tradingview/lightweight-charts)
(`src/components/TVChart.jsx`); the equity curve is a small SVG panel
(`src/components/Panel.jsx`).

## The strategy

`src/lib/strategy.js` (shared by the app and the CLI backtester):

| | Long | Short |
|---|---|---|
| **Entry** | EMA20 crosses **above** EMA50 · Stoch-RSI long permission on · CHOP ≤ 50 | EMA20 crosses **below** EMA50 · Stoch-RSI short permission on · CHOP ≤ 50 |
| **Exit** | EMA20 crosses below EMA50 | EMA20 crosses above EMA50 |

**Stoch-RSI permission** is stateful: long permission arms when K reaches ≥ 79
(80 − 1 tolerance), stays armed while K > 50, and disarms when K crosses below
50. Short permission mirrors it (K ≤ 21, disarms above 50). Stoch-RSI and CHOP
are **never** used to close an open position. Defaults: EMA 20/50, Stoch RSI
K 6 / D 6 / RSI 28 / Stoch 28, CHOP 14.

## Backtest configuration

Every knob is a param on `runStrategy(bars, params)` (see `DEFAULT_PARAMS` in
`src/lib/strategy.js`), a field in the app's backtest panel, and a `--set
key=value` on the CLI. The bare defaults reproduce the spec: $10,000, 100 % of
equity per trade, no costs, spec exits only.

| Group | Params |
|---|---|
| **Capital & sizing** | `capital` · `sizing` = `percent` / `lots` / `cash` / `risk` · `percentEquity` · `lots` + `contractSize` (oz/lot) · `cashPerTrade` · `riskPercent` (needs a stop) |
| **Costs** (price points) | `spread` (half per fill) · `slippage` (per fill) · `commissionPerLot` ($/lot/side) |
| **Risk management** (0 = off) | `stopLoss` + `stopMode` (`points`/`percent`/`atr`) · `takeProfit` + `tpMode` (`points`/`percent`/`atr`/`r`) · `trailStop` + `trailMode` (`points`/`atr`) · `atrLength`. Checked intrabar against each bar's high/low; stop wins ties. |
| **Execution** | `fillOn` = `close` / `nextOpen` · `allowFlip` · `sessionFilter` + `sessionStart` / `sessionEnd` (entry hours) |
| **Window** | `from` / `to` (YYYY-MM-DD, inclusive) |

Results report net P&L ($), drawdown in dollars, an exit-reason breakdown, and
per-trade P&L / lots alongside the percentage figures.

## Command-line backtest

```bash
npm run backtest                                   # all 9 timeframes -> backtest-report.md + .json
npm run backtest -- --tf m15                       # one timeframe
npm run backtest -- --from 2025-04-01 --to 2025-06-30   # date window (inclusive)
npm run backtest -- --no-short
npm run backtest -- --set capital=25000 --set sizing=lots --set lots=0.5
npm run backtest -- --set spread=0.3 --set commissionPerLot=7 --set stopLoss=1.5 --set stopMode=percent --set takeProfit=3 --set tpMode=r
```

The date window restricts *trading* to that span; indicators and the Stoch-RSI
permission state still warm up on earlier bars, and any position open at the
window's end is marked to market and closed. In the app the same window is set
with the **From / To** date fields (plus Q1–Q4 / H1 / H2 shortcuts) in the
backtest panel, and every result shows its tested period.

## Getting started

```bash
npm install
npm run dev
```

Then open the URL Vite prints (usually http://localhost:5173).

To build for production:

```bash
npm run build
npm run preview
```

## Using your own data

Price data lives in `public/data/*.json` — one file per timeframe
(`m1, m5, m15, m30, h1, h2, h4, daily, weekly`); the `m1` file is the full
~20 MB one-minute series and the rest are bucketed from it. The source CSV and
the strategy spec sit in `strategy-source/` (kept out of `public/` so they don't
ship in the build). To regenerate every timeframe from a DAT_MT 1-minute CSV
(format `DATE,TIME,OPEN,HIGH,LOW,CLOSE,VOLUME`, no header):

```bash
npm run data -- strategy-source/DAT_MT_XAUUSD_M1_2025.csv
```

The app fetches each timeframe's JSON on demand and caches it, so a refresh
picks up new data.

## Project structure

```
src/
  App.jsx                 state, layout, data loading
  lib/
    indicators.js         SMA, EMA, Bollinger, RSI, Stoch-RSI, Choppiness, ATR
    strategy.js           full backtest engine: signal + sizing + costs + SL/TP/trail + window
    backtest.js           legacy long-only MA-crossover engine (unused by the app)
    format.js             number/date/currency formatting + color palette
    useWidth.js           responsive-width hook for the equity-curve SVG
  components/
    TVChart.jsx           TradingView Lightweight Charts: candles, overlays, panes, markers
    Panel.jsx             SVG line panel (equity curve)
    ui.jsx                Stat cards, toggles, number/select/checkbox fields
scripts/
  aggregate.mjs           CSV -> 9 timeframe JSON files
  backtest.mjs            headless backtest -> backtest-report.md + .json
strategy-source/          the raw CSV + the strategy spec .txt files
public/data/              generated OHLC data (m1, m5, m15, m30, h1, h2, h4, daily, weekly)
```

## Note

This is an educational tool for exploring historical data. It is **not
financial advice**. Costs default to zero — turn on `spread` / `commissionPerLot`
/ `slippage` for a live-relevant number, because on the 1-minute timeframe the
EMA crossover fires thousands of trades a year and a realistic ~20–30c XAUUSD
round-trip spread alone swamps the average trade. Intrabar stop/target fills use
the bar's high/low with no assumption about the path within the bar.
