import { sma } from "./indicators.js";

// Long-only moving-average crossover. bars: [iso, o, h, l, c].
export function backtest(bars, fast, slow) {
  const close = bars.map((b) => b[4]);
  const f = sma(close, fast), s = sma(close, slow);
  const cap0 = 10000;
  let cash = cap0, pos = 0, entryPx = 0, entryI = 0;
  const eq = [], trades = [], marks = [];
  const bh = cap0 / close[0];

  for (let i = 0; i < bars.length; i++) {
    const px = close[i];
    if (i > 0 && f[i - 1] != null && s[i - 1] != null && f[i] != null && s[i] != null) {
      const crossUp = f[i - 1] <= s[i - 1] && f[i] > s[i];
      const crossDn = f[i - 1] >= s[i - 1] && f[i] < s[i];
      if (crossUp && pos === 0) {
        pos = cash / px; entryPx = px; entryI = i; cash = 0;
        marks.push({ i, type: "entry", px });
      } else if (crossDn && pos > 0) {
        cash = pos * px;
        trades.push({ entryI, exitI: i, entryPx, exitPx: px, ret: (px - entryPx) / entryPx });
        marks.push({ i, type: "exit", px });
        pos = 0;
      }
    }
    eq.push({ i, equity: cash + pos * px, bench: bh * px });
  }
  if (pos > 0) {
    const px = close[close.length - 1];
    trades.push({ entryI, exitI: bars.length - 1, entryPx, exitPx: px, ret: (px - entryPx) / entryPx, open: true });
  }

  const last = eq[eq.length - 1];
  const totalRet = (last.equity - cap0) / cap0;
  const benchRet = (last.bench - cap0) / cap0;
  let peak = -Infinity, maxDD = 0;
  eq.forEach((e) => { peak = Math.max(peak, e.equity); maxDD = Math.min(maxDD, (e.equity - peak) / peak); });
  const wins = trades.filter((t) => t.ret > 0).length;

  return { eq, trades, marks, totalRet, benchRet, maxDD, winRate: trades.length ? wins / trades.length : 0, nTrades: trades.length };
}
