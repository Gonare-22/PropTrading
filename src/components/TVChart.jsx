import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import { COLORS as C, fmt } from "../lib/format.js";

// TradingView Lightweight Charts wrapper — candles + EMA/SMA/Bollinger overlays,
// a Stoch-RSI pane, a Choppiness pane, and backtest entry/exit markers.
// bars: [iso, o, h, l, c]. Indicator arrays are aligned to bars (null = no value).
// Tuned to stay responsive on the full 354k-bar 1-minute series: timestamps and
// candle rows are memoised, series data is set once per change, and markers are
// windowed to what's on screen (Lightweight Charts is not built for thousands).

// Fast UTC epoch (seconds) for "YYYY-MM-DDTHH:MM:SS" — ~5x faster than Date.parse.
const toEpoch = (s) =>
  Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +s.slice(11, 13) || 0, +s.slice(14, 16) || 0, +s.slice(17, 19) || 0) / 1000;

// Lightweight Charts requires strictly ascending, unique times. `keep` is the
// index set already accepted for the candle series so every series stays aligned.
const lineData = (arr, ts, keep) => {
  const out = [];
  if (!arr) return out;
  for (let i = 0; i < arr.length; i++) {
    if (arr[i] == null) continue;
    if (keep && !keep.has(i)) continue;
    out.push({ time: ts[i], value: arr[i] });
  }
  return out;
};

function chartTheme(h) {
  return {
    autoSize: true,
    height: h,
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: "#8b93a3",
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      attributionLogo: false,
      panes: { separatorColor: "#1f2430", separatorHoverColor: "#2b3040" },
    },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.04)" },
      horzLines: { color: "rgba(255,255,255,0.04)" },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: "#3f4654", labelBackgroundColor: "#2b3040" },
      horzLine: { color: "#3f4654", labelBackgroundColor: "#2b3040" },
    },
    rightPriceScale: { borderColor: "#1f2430" },
    timeScale: { borderColor: "#1f2430", timeVisible: true, secondsVisible: false, rightOffset: 4 },
  };
}

export default function TVChart({
  bars, overlays, marks, stoch, chop, params,
  showStoch, showChop, showSMA, showBB, showEmaFast, showEmaSlow,
  height = 460,
}) {
  const boxRef = useRef(null);
  const api = useRef({});
  const [hud, setHud] = useState(null);

  const ts = useMemo(() => bars.map((b) => toEpoch(b[0])), [bars]);

  // Candle rows filtered to strictly ascending unique time; `keep` keeps the
  // overlay/pane series aligned to exactly the same bars.
  const { candleData, keep } = useMemo(() => {
    const rows = [];
    const keep = new Set();
    let prev = -Infinity;
    for (let i = 0; i < bars.length; i++) {
      const t = ts[i];
      if (!(t > prev)) continue;
      prev = t;
      keep.add(i);
      rows.push({ time: t, open: bars[i][1], high: bars[i][2], low: bars[i][3], close: bars[i][4] });
    }
    return { candleData: rows, keep: keep.size === bars.length ? null : keep };
  }, [bars, ts]);

  // Recreate the chart only when the pane/overlay layout or the bar set changes.
  const layoutKey = [
    bars.length, bars[0]?.[0], showStoch, showChop, showSMA, showBB, showEmaFast, showEmaSlow, height,
  ].join("|");

  useEffect(() => {
    if (!boxRef.current) return;
    const chart = createChart(boxRef.current, chartTheme(height));

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a", downColor: "#ef5350",
      wickUpColor: "#26a69a", wickDownColor: "#ef5350", borderVisible: false,
      priceLineVisible: false,
    }, 0);

    const overlay = (color, w = 1.5) =>
      chart.addSeries(LineSeries, { color, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }, 0);

    const lines = {};
    if (showEmaFast) lines.emaFast = overlay(C.emaFast);
    if (showEmaSlow) lines.emaSlow = overlay(C.emaSlow);
    if (showSMA) lines.sma = overlay(C.sma, 1.2);
    if (showBB) {
      lines.bbU = overlay("rgba(167,139,250,0.9)", 1);
      lines.bbL = overlay("rgba(167,139,250,0.9)", 1);
      lines.bbM = overlay("rgba(196,181,253,0.6)", 1);
    }

    const markers = createSeriesMarkers(candle, []);

    let paneIdx = 1;
    let stochK, stochD, chopLine;
    if (showStoch) {
      stochK = chart.addSeries(LineSeries, { color: C.stochK, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true }, paneIdx);
      stochD = chart.addSeries(LineSeries, { color: C.stochD, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, paneIdx);
      for (const [lvl, col] of [[params.shortLevel, "#3f4654"], [50, "#2b3040"], [params.longLevel, "#3f4654"]])
        stochK.createPriceLine({ price: lvl, color: col, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true });
      paneIdx++;
    }
    if (showChop) {
      chopLine = chart.addSeries(LineSeries, { color: C.chop, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true }, paneIdx);
      chopLine.createPriceLine({ price: params.chopMax, color: "#8b93a3", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "no-trade" });
      paneIdx++;
    }

    const panes = chart.panes();
    if (panes.length > 1) {
      panes[0].setStretchFactor(4);
      for (let i = 1; i < panes.length; i++) panes[i].setStretchFactor(1);
    }

    const move = (p) => {
      const c = p.time && p.seriesData?.get(candle);
      if (!c) { setHud(null); return; }
      setHud({
        o: c.open, h: c.high, l: c.low, c: c.close,
        chg: (c.close - c.open) / c.open,
        k: stochK ? p.seriesData.get(stochK)?.value : null,
        chop: chopLine ? p.seriesData.get(chopLine)?.value : null,
      });
    };
    chart.subscribeCrosshairMove(move);

    api.current = { chart, candle, markers, lines, stochK, stochD, chopLine, firstDataDone: false, applyMarkers: null };
    return () => { chart.unsubscribeCrosshairMove(move); chart.remove(); api.current = {}; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  // Series data — one setData pass per change (also the first fill after a rebuild).
  useEffect(() => {
    const a = api.current;
    if (!a.chart) return;
    a.candle.setData(candleData);
    a.lines.emaFast?.setData(lineData(overlays.emaFast, ts, keep));
    a.lines.emaSlow?.setData(lineData(overlays.emaSlow, ts, keep));
    a.lines.sma?.setData(lineData(overlays.sma, ts, keep));
    if (overlays.bb) {
      a.lines.bbU?.setData(lineData(overlays.bb.up, ts, keep));
      a.lines.bbL?.setData(lineData(overlays.bb.lo, ts, keep));
      a.lines.bbM?.setData(lineData(overlays.bb.mid, ts, keep));
    }
    a.stochK?.setData(lineData(stoch?.k, ts, keep));
    a.stochD?.setData(lineData(stoch?.d, ts, keep));
    a.chopLine?.setData(lineData(chop, ts, keep));

    if (!a.firstDataDone) {
      a.firstDataDone = true;
      const shown = Math.min(candleData.length, 350);
      a.chart.timeScale().setVisibleLogicalRange({ from: candleData.length - shown, to: candleData.length + 2 });
      a.needsTradeFocus = true; // let the markers effect re-centre on the last trades
    }
  }, [candleData, keep, overlays, stoch, chop, ts]);

  // Backtest markers — kept to whatever slice of the series is on screen.
  useEffect(() => {
    const a = api.current;
    if (!a.chart || !a.markers) return;

    const GREEN = "#26a69a", RED = "#ef5350";
    const all = (marks || [])
      .filter((x) => x.i < bars.length && (!keep || keep.has(x.i)))
      .map((x) => {
        const buy = x.action === "buy";
        if (x.type === "entry") {
          // opening a position: bright arrow, BUY (long) / SELL (short)
          return {
            i: x.i, time: ts[x.i],
            position: buy ? "belowBar" : "aboveBar",
            shape: buy ? "arrowUp" : "arrowDown",
            color: buy ? GREEN : RED,
            size: 2,
            label: buy ? "BUY" : "SELL",
          };
        }
        // closing a position: circle coloured by the trade's result
        const win = (x.pnl ?? x.ret ?? 0) >= 0;
        const reason = x.reason && x.reason !== "signal" ? ` (${x.reason})` : "";
        return {
          i: x.i, time: ts[x.i],
          position: "inBar",
          shape: "circle",
          color: win ? GREEN : RED,
          size: 1.1,
          label: `EXIT${reason} ${win ? "+" : ""}${(x.pnl ?? 0).toFixed(0)}`,
        };
      })
      .sort((p, q) => p.time - q.time);

    const apply = () => {
      if (!api.current.chart) return;
      const lr = a.chart.timeScale().getVisibleLogicalRange();
      let win = all;
      if (lr) {
        const lo = Math.max(0, Math.floor(lr.from) - 60);
        const hi = Math.min(candleData.length - 1, Math.ceil(lr.to) + 60);
        win = all.filter((m) => m.i >= lo && m.i <= hi);
      }
      if (win.length > 400) {
        const step = Math.ceil(win.length / 400);
        win = win.filter((_, k) => k % step === 0);
      }
      // only print BUY/SELL text when the chart isn't crowded
      const withText = win.length <= 24;
      a.markers.setMarkers(win.map(({ i, label, ...m }) => (withText ? { ...m, text: label } : m)));
    };

    // After a fresh backtest, jump the view to the last cluster of trades so
    // markers are on screen immediately (a 350-bar window can otherwise land on
    // a quiet stretch, especially on 1m).
    if (a.needsTradeFocus && all.length) {
      a.needsTradeFocus = false;
      const lastI = all[all.length - 1].i;
      const span = Math.min(candleData.length, 340);
      a.chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, lastI - span + 40),
        to: Math.min(candleData.length + 2, lastI + 40),
      });
    }

    apply();
    a.chart.timeScale().subscribeVisibleLogicalRangeChange(apply);
    return () => {
      api.current.chart?.timeScale().unsubscribeVisibleLogicalRangeChange(apply);
    };
  }, [marks, candleData, ts, keep]);

  const li = bars.length - 1;
  const show = hud || {
    o: bars[li][1], h: bars[li][2], l: bars[li][3], c: bars[li][4],
    chg: (bars[li][4] - bars[li][1]) / bars[li][1],
    k: stoch?.k[li], chop: chop?.[li],
  };
  const hasMarks = marks && marks.length > 0;

  return (
    <div className="relative">
      <div className="absolute z-10 left-2 top-1.5 text-[11px] font-mono tabular-nums text-zinc-400 pointer-events-none flex flex-wrap gap-x-3">
        <span>O <span className="text-zinc-200">{fmt(show.o)}</span></span>
        <span>H <span className="text-zinc-200">{fmt(show.h)}</span></span>
        <span>L <span className="text-zinc-200">{fmt(show.l)}</span></span>
        <span>C <span className="text-zinc-200">{fmt(show.c)}</span></span>
        <span className={show.chg >= 0 ? "text-emerald-400" : "text-rose-400"}>{(show.chg * 100).toFixed(2)}%</span>
        {show.k != null && <span style={{ color: C.stochK }}>K {fmt(show.k, 1)}</span>}
        {show.chop != null && <span style={{ color: C.chop }}>CHOP {fmt(show.chop, 1)}</span>}
      </div>
      <div ref={boxRef} style={{ height }} className="w-full" />
      {hasMarks && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-zinc-500">
          <span className="flex items-center gap-1"><span style={{ color: "#26a69a" }}>▲ BUY</span> open long</span>
          <span className="flex items-center gap-1"><span style={{ color: "#ef5350" }}>▼ SELL</span> open short</span>
          <span className="flex items-center gap-1"><span style={{ color: "#26a69a" }}>●</span><span style={{ color: "#ef5350" }}>●</span> EXIT (green = win / red = loss, label shows $)</span>
          <span className="text-zinc-600">zoom in for on-chart labels</span>
        </div>
      )}
    </div>
  );
}
