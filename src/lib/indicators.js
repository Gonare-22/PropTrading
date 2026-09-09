// Technical indicators. Each takes an array of close prices.
// SMA and Bollinger use rolling windows (O(n)) so they stay fast on
// hundreds of thousands of 1-minute bars.

export function sma(v, p) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < v.length; i++) {
    sum += v[i];
    if (i >= p) sum -= v[i - p];
    out.push(i >= p - 1 ? sum / p : null);
  }
  return out;
}

export function ema(v, p) {
  const k = 2 / (p + 1);
  const out = [];
  let prev;
  v.forEach((x, i) => {
    prev = i === 0 ? x : x * k + prev * (1 - k);
    out.push(prev);
  });
  return out;
}

export function bollinger(v, p, m) {
  const mid = [], up = [], lo = [];
  let s = 0, s2 = 0;
  for (let i = 0; i < v.length; i++) {
    s += v[i]; s2 += v[i] * v[i];
    if (i >= p) { s -= v[i - p]; s2 -= v[i - p] * v[i - p]; }
    if (i >= p - 1) {
      const mean = s / p;
      const sd = Math.sqrt(Math.max(0, s2 / p - mean * mean));
      mid.push(mean); up.push(mean + m * sd); lo.push(mean - m * sd);
    } else { mid.push(null); up.push(null); lo.push(null); }
  }
  return { mid, up, lo };
}

// SMA that tolerates leading nulls (used for Stoch RSI smoothing).
// Emits a value once `p` consecutive non-null inputs are available.
export function smaN(v, p) {
  const out = [];
  let sum = 0, cnt = 0;
  for (let i = 0; i < v.length; i++) {
    const x = v[i];
    if (x == null) { out.push(null); sum = 0; cnt = 0; continue; }
    sum += x; cnt++;
    if (cnt > p) { sum -= v[i - p]; cnt = p; }
    out.push(cnt >= p ? sum / p : null);
  }
  return out;
}

// Wilder's RSI
export function rsi(v, p) {
  const out = [null];
  let ag = 0, al = 0;
  for (let i = 1; i <= p; i++) {
    const d = v[i] - v[i - 1];
    ag += Math.max(d, 0); al += Math.max(-d, 0);
  }
  ag /= p; al /= p;
  for (let i = 1; i < v.length; i++) {
    if (i < p) { out.push(null); continue; }
    if (i > p) {
      const d = v[i] - v[i - 1];
      ag = (ag * (p - 1) + Math.max(d, 0)) / p;
      al = (al * (p - 1) + Math.max(-d, 0)) / p;
    }
    out.push(al === 0 ? 100 : 100 - 100 / (1 + ag / al));
  }
  return out;
}

// Stochastic RSI (TradingView-style): stochastic of RSI, then %K = SMA(stoch, kSmooth),
// %D = SMA(%K, dSmooth). Returns { k, d } as 0-100 arrays aligned to `v`.
export function stochRsi(v, rsiLen, stochLen, kSmooth, dSmooth) {
  const r = rsi(v, rsiLen);
  const raw = [];
  for (let i = 0; i < r.length; i++) {
    const start = i - stochLen + 1;
    if (start < 0 || r[i] == null || r[start] == null) { raw.push(null); continue; }
    let lo = Infinity, hi = -Infinity, ok = true;
    for (let j = start; j <= i; j++) {
      if (r[j] == null) { ok = false; break; }
      if (r[j] < lo) lo = r[j];
      if (r[j] > hi) hi = r[j];
    }
    if (!ok) { raw.push(null); continue; }
    raw.push(hi === lo ? 0 : ((r[i] - lo) / (hi - lo)) * 100);
  }
  const k = smaN(raw, kSmooth);
  const d = smaN(k, dSmooth);
  return { k, d, raw };
}

// Average True Range (Wilder / RMA smoothing). bars: [iso, o, h, l, c].
export function atr(bars, n) {
  const out = new Array(bars.length).fill(null);
  let prev = null, sum = 0;
  for (let i = 0; i < bars.length; i++) {
    const h = bars[i][2], l = bars[i][3];
    const tr = i === 0 ? h - l : Math.max(h - l, Math.abs(h - bars[i - 1][4]), Math.abs(l - bars[i - 1][4]));
    if (i < n) { sum += tr; if (i === n - 1) { prev = sum / n; out[i] = prev; } }
    else { prev = (prev * (n - 1) + tr) / n; out[i] = prev; }
  }
  return out;
}

// Choppiness Index. bars: [iso, o, h, l, c]. n = lookback (default 14).
// CHOP = 100 * log10( sum(TR, n) / (highestHigh(n) - lowestLow(n)) ) / log10(n)
export function chop(bars, n) {
  const tr = [];
  for (let i = 0; i < bars.length; i++) {
    const h = bars[i][2], l = bars[i][3];
    if (i === 0) { tr.push(h - l); continue; }
    const pc = bars[i - 1][4];
    tr.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }
  const out = [];
  const logN = Math.log10(n);
  let trSum = 0;
  for (let i = 0; i < bars.length; i++) {
    trSum += tr[i];
    if (i >= n) trSum -= tr[i - n];
    if (i < n - 1) { out.push(null); continue; }
    let hi = -Infinity, lo = Infinity;
    for (let j = i - n + 1; j <= i; j++) {
      if (bars[j][2] > hi) hi = bars[j][2];
      if (bars[j][3] < lo) lo = bars[j][3];
    }
    const range = hi - lo;
    out.push(range > 0 ? (100 * Math.log10(trSum / range)) / logN : null);
  }
  return out;
}
