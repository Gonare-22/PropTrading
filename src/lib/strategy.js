import { ema, stochRsi, chop, atr } from "./indicators.js";

// XAUUSD strategy engine (shared by the app and the CLI backtester).
//
// SIGNAL (unchanged from the spec)
//   LONG entry  = EMA fast crosses above EMA slow  + Stoch-RSI long permission  + CHOP <= chopMax
//   SHORT entry = EMA fast crosses below EMA slow  + Stoch-RSI short permission + CHOP <= chopMax
//   Exit        = opposite EMA cross (CHOP / Stoch-RSI never close a position)
//   Stoch-RSI permission is stateful: long arms at K >= longLevel-tolerance, holds while K > 50,
//   disarms when K crosses below 50 (short mirrors it).
//
// Everything else below is configurable and OFF by default, so the bare engine
// reproduces the spec: 100%-equity sizing, no costs, no stop / target.
//
// bars: [iso, open, high, low, close].

export const DEFAULT_PARAMS = {
  // signal
  emaFast: 20,
  emaSlow: 50,
  rsiLength: 28,
  stochLength: 28,
  kSmooth: 6,
  dSmooth: 6,
  longLevel: 80,
  shortLevel: 20,
  tolerance: 1,
  chopLength: 14,
  chopMax: 50,
  allowLong: true,
  allowShort: true,

  // date window (YYYY-MM-DD, inclusive) — null = data start / end
  from: null,
  to: null,

  // capital & position sizing
  capital: 10000,
  sizing: "percent",     // "percent" | "lots" | "cash" | "risk"
  percentEquity: 100,    // sizing="percent": notional = equity * pct/100  (>100 = leverage)
  lots: 0.1,             // sizing="lots"
  contractSize: 100,     // oz per lot (XAUUSD standard = 100)
  cashPerTrade: 10000,   // sizing="cash": fixed notional per trade
  riskPercent: 1.0,      // sizing="risk": $ risked per trade = equity * pct/100  (needs a stop)

  // transaction costs (price points unless noted)
  spread: 0,             // full spread; half is paid on each fill
  slippage: 0,           // added to every fill, against you
  commissionPerLot: 0,   // $ per lot, charged on entry and on exit

  // risk management (0 = off)
  stopLoss: 0,
  stopMode: "points",    // "points" | "percent" | "atr"
  takeProfit: 0,
  tpMode: "points",      // "points" | "percent" | "atr" | "r"  (r = multiple of stop distance)
  trailStop: 0,
  trailMode: "points",   // "points" | "atr"
  atrLength: 14,

  // execution
  fillOn: "close",       // "close" (this bar close) | "nextOpen" (next bar open)
  allowFlip: true,       // open the opposite side on the same bar an exit happens
  sessionFilter: false,  // restrict *entries* to an intraday hour window
  sessionStart: 0,       // hour 0-23 (local to the data's timestamps), inclusive
  sessionEnd: 24,        // hour 0-24, exclusive
};

const day = (iso) => iso.slice(0, 10);
const hourOf = (iso) => +iso.slice(11, 13);

export function runStrategy(bars, overrides = {}) {
  const p = { ...DEFAULT_PARAMS, ...overrides };
  const n = bars.length;
  const close = bars.map((b) => b[4]);

  const ef = ema(close, p.emaFast);
  const es = ema(close, p.emaSlow);
  const { k } = stochRsi(close, p.rsiLength, p.stochLength, p.kSmooth, p.dSmooth);
  const ci = chop(bars, p.chopLength);
  const needATR =
    (p.stopLoss && p.stopMode === "atr") ||
    (p.takeProfit && p.tpMode === "atr") ||
    (p.trailStop && p.trailMode === "atr");
  const av = needATR ? atr(bars, p.atrLength) : null;

  // trading window → bar indices
  let startIdx = 0;
  if (p.from) while (startIdx < n - 1 && day(bars[startIdx][0]) < p.from) startIdx++;
  let endIdx = n - 1;
  if (p.to) while (endIdx > 0 && day(bars[endIdx][0]) > p.to) endIdx--;
  if (endIdx < startIdx) endIdx = startIdx;

  const longOn = p.longLevel - p.tolerance;
  const shortOn = p.shortLevel + p.tolerance;
  const halfSpread = p.spread / 2;
  const cap0 = p.capital;

  let cash = cap0;         // realized $ (starts at capital; costs & realized PnL flow through)
  let pos = 0;             // +1 long, -1 short, 0 flat
  let units = 0;           // oz of gold in the open position
  let entryFill = 0, entryI = 0;
  let stopPx = null, tpPx = null, trailPx = null, extreme = 0;
  let longPerm = false, shortPerm = false;

  const eq = [];
  const trades = [];
  const marks = [];
  let nCross = 0, nCrossFiltered = 0, warmIdx = -1;
  // buy & hold: one unit-normalised long from the window start close
  const bhUnits = cap0 / close[startIdx];

  const commission = (u) => p.commissionPerLot * Math.abs(u) / p.contractSize;

  // fill price for a market order in `dir` (+1 buy, -1 sell) around base price
  const fillAt = (base, dir) => base + dir * (halfSpread + p.slippage);

  const sizeUnits = (equity, fillPx, stopDist) => {
    let notional;
    if (p.sizing === "lots") return Math.max(0, p.lots) * p.contractSize;
    if (p.sizing === "cash") notional = Math.max(0, p.cashPerTrade);
    else if (p.sizing === "risk") {
      if (!stopDist || stopDist <= 0) notional = equity; // no stop -> fall back to full equity
      else return Math.max(0, (equity * p.riskPercent) / 100 / stopDist);
    } else notional = equity * Math.max(0, p.percentEquity) / 100; // "percent"
    return fillPx > 0 ? notional / fillPx : 0;
  };

  const stopDistance = (refPx, i) => {
    if (!p.stopLoss) return 0;
    if (p.stopMode === "percent") return (refPx * p.stopLoss) / 100;
    if (p.stopMode === "atr") return (av && av[i] != null ? av[i] : 0) * p.stopLoss;
    return p.stopLoss; // points
  };
  const tpDistance = (refPx, i, stopDist) => {
    if (!p.takeProfit) return 0;
    if (p.tpMode === "percent") return (refPx * p.takeProfit) / 100;
    if (p.tpMode === "atr") return (av && av[i] != null ? av[i] : 0) * p.takeProfit;
    if (p.tpMode === "r") return stopDist * p.takeProfit;
    return p.takeProfit; // points
  };
  const trailDistance = (i) => {
    if (!p.trailStop) return 0;
    if (p.trailMode === "atr") return (av && av[i] != null ? av[i] : 0) * p.trailStop;
    return p.trailStop; // points
  };

  const openPosition = (side, i, basePx) => {
    const fp = fillAt(basePx, side);
    const sd = stopDistance(fp, i);
    const u = sizeUnits(equityNow(basePx), fp, sd);
    if (!(u > 0)) return;
    cash -= commission(u);
    pos = side; units = u; entryFill = fp; entryI = i;
    extreme = fp;
    stopPx = sd > 0 ? fp - side * sd : null;
    const td = tpDistance(fp, i, sd);
    tpPx = td > 0 ? fp + side * td : null;
    trailPx = null;
    marks.push({ i, type: "entry", px: fp, side: side > 0 ? "long" : "short", action: side > 0 ? "buy" : "sell" });
  };

  const closePosition = (i, basePx, reason, isOpen = false) => {
    const fp = fillAt(basePx, -pos);
    const grossPnl = pos * units * (fp - entryFill);
    const entryComm = commission(units), exitComm = commission(units);
    cash += grossPnl - exitComm;
    const ret = pos * (fp - entryFill) / entryFill;
    const t = {
      side: pos > 0 ? "long" : "short",
      entryI, exitI: i, entryPx: entryFill, exitPx: fp,
      units, lots: units / p.contractSize,
      pnl: grossPnl - entryComm - exitComm, // round-trip net of costs
      ret, reason,
      bars: i - entryI,
      entryTime: bars[entryI][0], exitTime: bars[i][0],
    };
    if (isOpen) t.open = true;
    trades.push(t);
    if (!isOpen)
      marks.push({
        i, type: "exit", px: fp,
        side: pos > 0 ? "long" : "short",
        action: pos > 0 ? "sell" : "buy", // closing a long = sell; closing a short = buy back
        reason, pnl: t.pnl, ret: t.ret,
      });
    pos = 0; units = 0; stopPx = tpPx = trailPx = null;
    return t;
  };

  // equity marked to the given price
  function equityNow(px) {
    return pos === 0 ? cash : cash + pos * units * (px - entryFill);
  }

  for (let i = 0; i <= endIdx; i++) {
    const c = close[i], hi = bars[i][2], lo = bars[i][3];
    const kv = k[i];

    // permission FSM runs over the whole series (correct warm-up)
    if (kv != null) {
      if (kv >= longOn) longPerm = true;
      if (kv < 50) longPerm = false;
      if (kv <= shortOn) shortPerm = true;
      if (kv > 50) shortPerm = false;
    }
    if (i < startIdx) continue;

    if (warmIdx < 0 && ef[i] != null && es[i] != null && k[i] != null && ci[i] != null) warmIdx = i;

    // 1) intrabar stop / target / trail on an existing position (uses this bar's H/L)
    if (pos !== 0) {
      // update trailing stop from the favourable extreme
      const td = trailDistance(i);
      if (td > 0) {
        extreme = pos > 0 ? Math.max(extreme, hi) : Math.min(extreme, lo);
        const newTrail = extreme - pos * td;
        trailPx = trailPx == null ? newTrail : pos > 0 ? Math.max(trailPx, newTrail) : Math.min(trailPx, newTrail);
      }
      const effStop = [stopPx, trailPx].filter((v) => v != null);
      const stopLevel = effStop.length ? (pos > 0 ? Math.max(...effStop) : Math.min(...effStop)) : null;
      const stopHit = stopLevel != null && (pos > 0 ? lo <= stopLevel : hi >= stopLevel);
      const tpHit = tpPx != null && (pos > 0 ? hi >= tpPx : lo <= tpPx);
      // conservative: if both could hit in one bar, assume the stop went first
      if (stopHit) closePosition(i, stopLevel, "stop");
      else if (tpHit) closePosition(i, tpPx, "target");
    }

    // 2) signals on confirmed close; optionally filled at next bar's open
    const ready = i > 0 && ef[i - 1] != null && es[i - 1] != null && ef[i] != null && es[i] != null;
    const crossUp = ready && ef[i - 1] <= es[i - 1] && ef[i] > es[i];
    const crossDn = ready && ef[i - 1] >= es[i - 1] && ef[i] < es[i];
    const chopOk = ci[i] != null && ci[i] <= p.chopMax;
    const nextOpen = p.fillOn === "nextOpen" && i + 1 < n;
    const basePx = nextOpen ? bars[i + 1][1] : c;
    const inSession =
      !p.sessionFilter || (hourOf(bars[i][0]) >= p.sessionStart && hourOf(bars[i][0]) < p.sessionEnd);

    if (crossUp || crossDn) {
      nCross++;
      const passLong = crossUp && p.allowLong && longPerm && chopOk && inSession;
      const passShort = crossDn && p.allowShort && shortPerm && chopOk && inSession;
      if (passLong || passShort) nCrossFiltered++;
    }

    if (pos > 0 && crossDn) closePosition(i, basePx, "signal");
    else if (pos < 0 && crossUp) closePosition(i, basePx, "signal");

    if (pos === 0) {
      const goLong = crossUp && p.allowLong && longPerm && chopOk && inSession;
      const goShort = crossDn && p.allowShort && shortPerm && chopOk && inSession;
      if (goLong || goShort) {
        // don't open on the exit bar unless flips are allowed
        const justExited = trades.length && trades[trades.length - 1].exitI === i && trades[trades.length - 1].reason === "signal";
        if (!justExited || p.allowFlip) openPosition(goLong ? 1 : -1, i, basePx);
      }
    }

    const equity = equityNow(c);
    eq.push({ i, t: bars[i][0], equity, bench: bhUnits * c });
  }

  let openTrade = null;
  if (pos !== 0) openTrade = closePosition(endIdx, close[endIdx], "window end", true);

  const nBars = endIdx - startIdx + 1;
  const closedN = trades.filter((t) => !t.open).length;
  const warmupNeeded = Math.max(p.emaSlow, p.rsiLength + p.stochLength + p.kSmooth, p.chopLength);
  const barsAfterWarmup = warmIdx < 0 ? 0 : endIdx - warmIdx + 1;
  const diagnostics = {
    warmupNeeded,
    warmedAt: warmIdx < 0 ? null : bars[warmIdx][0],
    barsAfterWarmup,
    emaCrosses: nCross,
    crossesPassingFilters: nCrossFiltered,
    note: buildNote({ closedN, nBars, warmIdx, barsAfterWarmup, warmupNeeded, nCross, nCrossFiltered, p }),
  };

  return {
    ...stats(eq, trades, cap0, p),
    eq,
    trades,
    marks,
    openTrade,
    diagnostics,
    params: p,
    startIdx,
    endIdx,
    periodStart: bars[startIdx][0],
    periodEnd: bars[endIdx][0],
    dataStart: bars[0][0],
    dataEnd: bars[n - 1][0],
    nBars,
  };
}

function buildNote({ closedN, nBars, warmIdx, barsAfterWarmup, warmupNeeded, nCross, nCrossFiltered, p }) {
  if (closedN > 0) return null;
  const tooFewOverall = warmIdx < 0 || barsAfterWarmup < 40;
  if (tooFewOverall)
    return `Not enough data. The ${p.emaFast}/${p.emaSlow} EMA and Stoch-RSI need about ${warmupNeeded} bars to warm up, and this window only leaves ${Math.max(0, barsAfterWarmup)} tradeable bar${barsAfterWarmup === 1 ? "" : "s"} after that. This strategy is written for the 1-minute timeframe — switch to 1m, or widen the date range on a higher timeframe.`;
  if (nCross === 0)
    return `The ${p.emaFast}/${p.emaSlow} EMA never crossed in this window. Use a lower timeframe (1m is what the strategy targets) or a wider date range.`;
  if (nCrossFiltered === 0)
    return `${nCross} EMA cross${nCross === 1 ? "" : "es"} occurred, but none while the Stoch-RSI permission was armed and CHOP ≤ ${p.chopMax}${p.sessionFilter ? " and inside the session" : ""}. On higher timeframes signals are too sparse to line up — run this on 1m, or loosen CHOP max / widen the Stoch-RSI levels.`;
  return `${nCrossFiltered} of ${nCross} EMA crosses passed the filters, but none while flat and permitted to enter (check the Longs / Shorts toggles and same-bar flip).`;
}

function stats(eq, trades, cap0, p) {
  const last = eq[eq.length - 1] || { equity: cap0, bench: cap0 };
  const totalRet = (last.equity - cap0) / cap0;
  const benchRet = (last.bench - cap0) / cap0;

  let peak = -Infinity, maxDD = 0, maxDD$ = 0;
  for (const e of eq) {
    if (e.equity > peak) peak = e.equity;
    const dd = (e.equity - peak) / peak;
    if (dd < maxDD) { maxDD = dd; maxDD$ = e.equity - peak; }
  }

  const closed = trades.filter((t) => !t.open);
  const wins = closed.filter((t) => t.pnl > 0);
  const losses = closed.filter((t) => t.pnl <= 0);
  const grossWin = wins.reduce((s, t) => s + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
  const longs = closed.filter((t) => t.side === "long");
  const shorts = closed.filter((t) => t.side === "short");
  const avg$ = (a) => (a.length ? a.reduce((s, t) => s + t.pnl, 0) / a.length : 0);
  const netPnl = trades.reduce((s, t) => s + t.pnl, 0);

  const rets = [];
  for (let i = 1; i < eq.length; i++) rets.push(eq[i].equity / eq[i - 1].equity - 1);
  const mean = rets.reduce((s, r) => s + r, 0) / (rets.length || 1);
  const sd = Math.sqrt(rets.reduce((s, r) => s + (r - mean) ** 2, 0) / (rets.length || 1));
  let periodsPerYear = eq.length;
  if (eq.length > 1) {
    const years = (new Date(eq[eq.length - 1].t) - new Date(eq[0].t)) / (365.25 * 24 * 3600 * 1000);
    if (years > 0) periodsPerYear = eq.length / years;
  }
  const sharpe = sd > 0 ? (mean / sd) * Math.sqrt(periodsPerYear) : 0;

  const inMarket = trades.reduce((s, t) => s + t.bars, 0);
  const byReason = {};
  for (const t of closed) byReason[t.reason] = (byReason[t.reason] || 0) + 1;

  return {
    totalRet,
    benchRet,
    netPnl,
    finalEquity: last.equity,
    maxDD,
    maxDDdollar: maxDD$,
    nTrades: closed.length,
    winRate: closed.length ? wins.length / closed.length : 0,
    profitFactor: grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0,
    avgTrade: avg$(closed),
    avgWin: avg$(wins),
    avgLoss: avg$(losses),
    avgTradeRet: closed.length ? closed.reduce((s, t) => s + t.ret, 0) / closed.length : 0,
    bestTrade: closed.reduce((m, t) => Math.max(m, t.pnl), 0),
    worstTrade: closed.reduce((m, t) => Math.min(m, t.pnl), 0),
    nLong: longs.length,
    nShort: shorts.length,
    longWinRate: longs.length ? longs.filter((t) => t.pnl > 0).length / longs.length : 0,
    shortWinRate: shorts.length ? shorts.filter((t) => t.pnl > 0).length / shorts.length : 0,
    avgBars: closed.length ? inMarket / closed.length : 0,
    exposure: eq.length ? inMarket / eq.length : 0,
    exitBreakdown: byReason,
    sharpe,
  };
}
