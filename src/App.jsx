import { useState, useEffect, useMemo, useCallback } from "react";
import TVChart from "./components/TVChart.jsx";
import Panel from "./components/Panel.jsx";
import { Stat, Toggle, NumField, Select, Check, Group } from "./components/ui.jsx";
import { sma, ema, bollinger, stochRsi, chop } from "./lib/indicators.js";
import { runStrategy, DEFAULT_PARAMS } from "./lib/strategy.js";
import { COLORS as C, fmt, pct, usd, stamp } from "./lib/format.js";

const TFS = [
  { key: "m1", label: "1m" },
  { key: "m5", label: "5m" },
  { key: "m15", label: "15m" },
  { key: "m30", label: "30m" },
  { key: "h1", label: "1H" },
  { key: "h2", label: "2H" },
  { key: "h4", label: "4H" },
  { key: "daily", label: "1D" },
  { key: "weekly", label: "1W" },
];

const DATASETS = [
  { key: "2022", label: "2022", path: "/data/2022", hasMonths: true },
  { key: "2023", label: "2023", path: "/data/2023", hasMonths: true },
  { key: "2024", label: "2024", path: "/data/2024", hasMonths: true },
  { key: "2025", label: "2025", path: "/data/2025", hasMonths: true },
  { key: "aug2026", label: "Aug 2026", path: "/data/aug2026", hasMonths: false },
];

const MONTHS = [
  { key: "jan", label: "Jan" },
  { key: "feb", label: "Feb" },
  { key: "mar", label: "Mar" },
  { key: "apr", label: "Apr" },
  { key: "may", label: "May" },
  { key: "jun", label: "Jun" },
  { key: "jul", label: "Jul" },
  { key: "aug", label: "Aug" },
  { key: "sep", label: "Sep" },
  { key: "oct", label: "Oct" },
  { key: "nov", label: "Nov" },
  { key: "dec", label: "Dec" },
];

const cache = {};

function loadTf(key, dataset = "2025", month = null) {
  const cacheKey = month ? `${dataset}-${month}-${key}` : `${dataset}-${key}`;
  if (cache[cacheKey]) return Promise.resolve(cache[cacheKey]);
  const dataPath = DATASETS.find((d) => d.key === dataset)?.path || "/data";
  const fullPath = month ? `${dataPath}/${month}/${key}.json` : `${dataPath}/${key}.json`;
  
  console.log(`Loading data: ${fullPath} (cache key: ${cacheKey})`);
  
  return fetch(fullPath)
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to fetch ${fullPath}: ${r.status} ${r.statusText}`);
      return r.json();
    })
    .then((j) => {
      const data = j[key];
      if (!data || !Array.isArray(data)) {
        throw new Error(`Invalid data structure in ${fullPath} - expected array at key "${key}"`);
      }
      console.log(`Loaded ${data.length} bars from ${fullPath}`);
      cache[cacheKey] = data;
      return data;
    })
    .catch((err) => {
      console.error(`Error loading ${fullPath}:`, err);
      throw err;
    });
}

export default function App() {
  const [tf, setTf] = useState("m15");
  const [dataset, setDataset] = useState("2025");
  const [month, setMonth] = useState(null);
  const [bars, setBars] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [show, setShow] = useState({ emaFast: true, emaSlow: true, stoch: true, chop: true, sma: false, bb: false });
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [bt, setBt] = useState(null);
  const [mtf, setMtf] = useState(null);
  const [mtfBusy, setMtfBusy] = useState(false);
  const [tradePage, setTradePage] = useState(1);

  const setP = (k) => (v) => setParams((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    let alive = true;
    setBars(null);
    setLoadError(null);
    loadTf(tf, dataset, month)
      .then((b) => {
        if (!alive) return;
        setBars(b);
        // keep the panel populated across timeframe switches
        setBt(runStrategy(b, params));
      })
      .catch((err) => {
        if (!alive) return;
        console.error('Failed to load data:', err);
        setLoadError(err.message);
      });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tf, dataset, month]);

  const close = useMemo(() => (bars ? bars.map((b) => b[4]) : []), [bars]);
  const emaFastArr = useMemo(() => ema(close, params.emaFast), [close, params.emaFast]);
  const emaSlowArr = useMemo(() => ema(close, params.emaSlow), [close, params.emaSlow]);
  const smaArr = useMemo(() => (show.sma ? sma(close, 20) : null), [close, show.sma]);
  const bbArr = useMemo(() => (show.bb ? bollinger(close, 20, 2) : null), [close, show.bb]);
  const stochArr = useMemo(
    () => (bars ? stochRsi(close, params.rsiLength, params.stochLength, params.kSmooth, params.dSmooth) : null),
    [close, bars, params.rsiLength, params.stochLength, params.kSmooth, params.dSmooth]
  );
  const chopArr = useMemo(() => (bars ? chop(bars, params.chopLength) : null), [bars, params.chopLength]);

  const runBt = useCallback(() => {
    if (bars) {
      setBt(runStrategy(bars, params));
      setTradePage(1); // reset to first page on new backtest
    }
  }, [bars, params]);

  const compareTf = useCallback(async () => {
    setMtfBusy(true);
    const out = [];
    for (const t of TFS) {
      const b = await loadTf(t.key, dataset, month);
      out.push({ ...t, bars: b.length, r: runStrategy(b, params) });
    }
    setMtf(out);
    setMtfBusy(false);
  }, [params, dataset, month]);

  if (loadError) {
    return (
      <div className="min-h-full bg-zinc-950 text-zinc-100 flex items-center justify-center p-4" style={{ fontFamily: "Inter,system-ui,sans-serif" }}>
        <div className="max-w-2xl">
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-6">
            <div className="flex items-start gap-3">
              <svg className="w-6 h-6 text-rose-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-rose-300 mb-2">Failed to Load Data</h3>
                <p className="text-sm text-rose-200/90 mb-3">{loadError}</p>
                <div className="text-xs text-rose-200/70 space-y-1">
                  <p><strong>Dataset:</strong> {dataset}{month ? ` / ${month}` : ''}</p>
                  <p><strong>Timeframe:</strong> {tf}</p>
                  <p><strong>Expected path:</strong> {DATASETS.find((d) => d.key === dataset)?.path || "/data"}{month ? `/${month}` : ''}/{tf}.json</p>
                </div>
                <div className="mt-4 flex gap-2">
                  <button 
                    onClick={() => { setMonth(null); setLoadError(null); }} 
                    className="px-4 py-2 rounded bg-rose-500 text-white text-sm font-medium hover:bg-rose-400"
                  >
                    Try Full Year
                  </button>
                  <button 
                    onClick={() => { setDataset("2024"); setMonth(null); setLoadError(null); }} 
                    className="px-4 py-2 rounded border border-rose-500 text-rose-300 text-sm hover:bg-rose-500/20"
                  >
                    Switch to 2024
                  </button>
                  <button 
                    onClick={() => window.location.reload()} 
                    className="px-4 py-2 rounded border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800"
                  >
                    Reload Page
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-4 text-xs text-zinc-500 text-center">
            Check browser console (F12) for detailed error logs
          </div>
        </div>
      </div>
    );
  }

  if (!bars) {
    return (
      <div className="min-h-full bg-zinc-950 text-zinc-500 flex items-center justify-center" style={{ fontFamily: "Inter,system-ui,sans-serif" }}>
        Loading market data…
      </div>
    );
  }

  const overlays = {
    emaFast: show.emaFast ? emaFastArr : null,
    emaSlow: show.emaSlow ? emaSlowArr : null,
    sma: smaArr,
    bb: bbArr,
  };
  const last = bars[bars.length - 1], first = bars[0];
  const yearChg = (last[4] - first[1]) / first[1];
  const li = bars.length - 1;
  const dataFrom = first[0].slice(0, 10);
  const dataTo = last[0].slice(0, 10);
  const px = last[4];
  const posOz =
    params.sizing === "lots" ? params.lots * params.contractSize
    : params.sizing === "cash" ? params.cashPerTrade / px
    : params.sizing === "percent" ? (params.capital * params.percentEquity) / 100 / px
    : null; // "risk" depends on the stop
  const posHint =
    posOz != null
      ? `≈ ${posOz.toFixed(posOz < 10 ? 3 : 1)} oz · ${usd(posOz * px)} notional at $${fmt(px)}` +
        (posOz * px > params.capital * 1.05 ? `  (${(posOz * px / params.capital).toFixed(1)}× capital)` : "")
      : "sized from stop distance";

  return (
    <div className="min-h-full bg-zinc-950 text-zinc-100" style={{ fontFamily: "Inter,ui-sans-serif,system-ui,sans-serif" }}>
      <div className="max-w-6xl mx-auto p-4 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
          <div>
            <div className="flex items-baseline gap-3">
              <h1 className="text-2xl font-semibold tracking-tight">XAU<span className="text-amber-400">/</span>USD</h1>
              <span className="text-zinc-500 text-sm">Gold spot · EMA 20/50 + Stoch-RSI + CHOP</span>
            </div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-3xl font-semibold tabular-nums text-amber-300">${fmt(last[4])}</span>
              <span className={"text-sm tabular-nums " + (yearChg >= 0 ? "text-emerald-400" : "text-rose-400")}>{pct(yearChg)} YTD</span>
            </div>
            <div className="mt-0.5 text-xs text-zinc-500 tabular-nums">
              {TFS.find((t) => t.key === tf)?.label} · last bar {stamp(last[0], tf)}
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex gap-1 rounded-md border border-zinc-800 p-0.5 bg-zinc-900">
              {DATASETS.map((d) => (
                <button key={d.key} onClick={() => { setDataset(d.key); setMonth(null); }} className={"px-3 py-1.5 rounded text-sm font-medium " + (dataset === d.key ? "bg-amber-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200")}>{d.label}</button>
              ))}
            </div>
            {DATASETS.find((d) => d.key === dataset)?.hasMonths && (
              <div className="flex gap-1 rounded-md border border-zinc-800 p-0.5 bg-zinc-900 flex-wrap">
                <button onClick={() => setMonth(null)} className={"px-2 py-1 rounded text-xs font-medium " + (!month ? "bg-emerald-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200")}>Full Year</button>
                {MONTHS.map((m) => (
                  <button key={m.key} onClick={() => setMonth(m.key)} className={"px-2 py-1 rounded text-xs font-medium " + (month === m.key ? "bg-emerald-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200")}>{m.label}</button>
                ))}
              </div>
            )}
            <div className="flex gap-1 rounded-md border border-zinc-800 p-0.5 bg-zinc-900">
              {TFS.map((t) => (
                <button key={t.key} onClick={() => setTf(t.key)} className={"px-3 py-1.5 rounded text-sm font-medium " + (tf === t.key ? "bg-amber-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200")}>{t.label}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-2">
          <span className="text-xs text-zinc-500 mr-1">Overlays</span>
          <Toggle on={show.emaFast} set={(v) => setShow((s) => ({ ...s, emaFast: v }))} color={C.emaFast}>EMA {params.emaFast}</Toggle>
          <Toggle on={show.emaSlow} set={(v) => setShow((s) => ({ ...s, emaSlow: v }))} color={C.emaSlow}>EMA {params.emaSlow}</Toggle>
          <Toggle on={show.stoch} set={(v) => setShow((s) => ({ ...s, stoch: v }))} color={C.stochK}>Stoch RSI</Toggle>
          <Toggle on={show.chop} set={(v) => setShow((s) => ({ ...s, chop: v }))} color={C.chop}>CHOP</Toggle>
          <Toggle on={show.sma} set={(v) => setShow((s) => ({ ...s, sma: v }))} color={C.sma}>SMA 20</Toggle>
          <Toggle on={show.bb} set={(v) => setShow((s) => ({ ...s, bb: v }))} color={C.bb}>Bollinger</Toggle>
          <span className="ml-auto text-[11px] text-zinc-600">strategy spec targets 1m</span>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-2">
          <TVChart
            bars={bars}
            overlays={overlays}
            marks={bt ? bt.marks : null}
            stoch={show.stoch ? stochArr : null}
            chop={show.chop ? chopArr : null}
            params={params}
            showStoch={show.stoch}
            showChop={show.chop}
            showSMA={show.sma}
            showBB={show.bb}
            showEmaFast={show.emaFast}
            showEmaSlow={show.emaSlow}
            height={show.stoch && show.chop ? 620 : show.stoch || show.chop ? 540 : 440}
          />
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 mt-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-zinc-200">Strategy backtest</div>
              <div className="text-xs text-zinc-500">
                {usd(params.capital)} · {params.sizing === "percent" ? `${params.percentEquity}% equity` : params.sizing === "lots" ? `${params.lots} lot` : params.sizing === "cash" ? `${usd(params.cashPerTrade)}/trade` : `${params.riskPercent}% risk`}
                {(params.spread || params.commissionPerLot || params.slippage) ? " · costs on" : " · frictionless"}
                {(params.stopLoss || params.takeProfit || params.trailStop) ? " · SL/TP on" : " · exit on opposite cross only"}
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setParams(DEFAULT_PARAMS)} className="px-3 py-2 rounded border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800">Reset</button>
              <button onClick={runBt} className="px-4 py-2 rounded bg-amber-500 text-zinc-950 text-sm font-medium hover:bg-amber-400">Run backtest</button>
            </div>
          </div>

          <Group title="Signal — EMA cross + Stoch-RSI permission + Choppiness">
            <NumField label="EMA fast" value={params.emaFast} onChange={setP("emaFast")} min={2} max={100} />
            <NumField label="EMA slow" value={params.emaSlow} onChange={setP("emaSlow")} min={3} max={200} />
            <NumField label="RSI length" value={params.rsiLength} onChange={setP("rsiLength")} min={2} max={100} />
            <NumField label="Stoch length" value={params.stochLength} onChange={setP("stochLength")} min={2} max={100} />
            <NumField label="K smooth" value={params.kSmooth} onChange={setP("kSmooth")} min={1} max={20} />
            <NumField label="D smooth" value={params.dSmooth} onChange={setP("dSmooth")} min={1} max={20} />
            <NumField label="Long level" value={params.longLevel} onChange={setP("longLevel")} min={50} max={100} />
            <NumField label="Short level" value={params.shortLevel} onChange={setP("shortLevel")} min={0} max={50} />
            <NumField label="Tolerance" value={params.tolerance} onChange={setP("tolerance")} min={0} max={10} />
            <NumField label="CHOP length" value={params.chopLength} onChange={setP("chopLength")} min={2} max={100} />
            <NumField label="CHOP max" value={params.chopMax} onChange={setP("chopMax")} min={0} max={100} />
            <div className="flex flex-col justify-end gap-1">
              <Check checked={params.allowLong} onChange={setP("allowLong")}>Longs</Check>
              <Check checked={params.allowShort} onChange={setP("allowShort")}>Shorts</Check>
            </div>
          </Group>

          <Group title="Capital & position sizing">
            <NumField label="Capital $" value={params.capital} onChange={setP("capital")} min={100} max={100000000} step={100} />
            <Select label="Sizing" value={params.sizing} onChange={setP("sizing")} options={[
              ["percent", "% of equity"], ["lots", "Fixed lots"], ["cash", "Fixed $ notional"], ["risk", "% risk / trade"],
            ]} />
            {params.sizing === "percent" && (
              <NumField label="% of equity" value={params.percentEquity} onChange={setP("percentEquity")} min={1} max={1000} step={5} />
            )}
            {params.sizing === "lots" && (
              <>
                <NumField label="Lots" value={params.lots} onChange={setP("lots")} min={0.01} max={100} step={0.01} />
                <NumField label="Oz / lot" value={params.contractSize} onChange={setP("contractSize")} min={1} max={1000} />
              </>
            )}
            {params.sizing === "cash" && (
              <NumField label="$ / trade" value={params.cashPerTrade} onChange={setP("cashPerTrade")} min={100} max={100000000} step={100} />
            )}
            {params.sizing === "risk" && (
              <NumField label="% risk / trade" value={params.riskPercent} onChange={setP("riskPercent")} min={0.1} max={20} step={0.1} />
            )}
            <div className="col-span-2 sm:col-span-4 lg:col-span-3 text-[11px] text-zinc-500 self-center">
              Position size {posHint}
              {params.sizing === "lots" && params.contractSize === 1 && (
                <span className="text-amber-400/90"> — XAUUSD standard is 100 oz/lot</span>
              )}
            </div>
          </Group>

          <Group title="Transaction costs (price points)">
            <NumField label="Spread" value={params.spread} onChange={setP("spread")} min={0} max={20} step={0.05} />
            <NumField label="Slippage" value={params.slippage} onChange={setP("slippage")} min={0} max={20} step={0.05} />
            <NumField label="Commission $/lot" value={params.commissionPerLot} onChange={setP("commissionPerLot")} min={0} max={200} step={0.5} />
          </Group>

          <Group title="Risk management (0 = off, spec exit stays on opposite cross)">
            <NumField label="Stop loss" value={params.stopLoss} onChange={setP("stopLoss")} min={0} max={100000} step={0.1} />
            <Select label="Stop unit" value={params.stopMode} onChange={setP("stopMode")} options={[["points", "points"], ["percent", "%"], ["atr", "× ATR"], ["fixed", "$ fixed"]]} />
            <NumField label="Take profit" value={params.takeProfit} onChange={setP("takeProfit")} min={0} max={100000} step={0.1} />
            <Select label="TP unit" value={params.tpMode} onChange={setP("tpMode")} options={[["points", "points"], ["percent", "%"], ["atr", "× ATR"], ["r", "× stop (R)"]]} />
            <NumField label="Trailing stop" value={params.trailStop} onChange={setP("trailStop")} min={0} max={100000} step={0.1} />
            <Select label="Trail unit" value={params.trailMode} onChange={setP("trailMode")} options={[["points", "points"], ["atr", "× ATR"]]} />
            <NumField label="ATR length" value={params.atrLength} onChange={setP("atrLength")} min={2} max={100} />
          </Group>

          <Group title="Execution">
            <Select label="Fill on" value={params.fillOn} onChange={setP("fillOn")} options={[["close", "Signal bar close"], ["nextOpen", "Next bar open"]]} />
            <div className="flex flex-col justify-end gap-1">
              <Check checked={params.allowFlip} onChange={setP("allowFlip")}>Same-bar flip</Check>
              <Check checked={params.sessionFilter} onChange={setP("sessionFilter")}>Session filter</Check>
            </div>
            {params.sessionFilter && (
              <>
                <NumField label="Session start h" value={params.sessionStart} onChange={setP("sessionStart")} min={0} max={23} />
                <NumField label="Session end h" value={params.sessionEnd} onChange={setP("sessionEnd")} min={1} max={24} />
              </>
            )}
          </Group>

          <div className="flex flex-wrap items-end gap-3 mt-3 pt-3 border-t border-zinc-800/60">
            <div className="text-xs text-zinc-400">
              Backtest window
              <div className="text-[10px] text-zinc-600 tabular-nums">data {dataFrom} → {dataTo}</div>
            </div>
            <label className="text-[11px] text-zinc-400">From
              <input type="date" min={dataFrom} max={dataTo} value={params.from || dataFrom}
                onChange={(e) => setP("from")(e.target.value || null)}
                className="mt-0.5 block bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-100 tabular-nums" />
            </label>
            <label className="text-[11px] text-zinc-400">To
              <input type="date" min={dataFrom} max={dataTo} value={params.to || dataTo}
                onChange={(e) => setP("to")(e.target.value || null)}
                className="mt-0.5 block bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-100 tabular-nums" />
            </label>
            <div className="flex gap-1.5">
              {[["Q1", "01-01", "03-31"], ["Q2", "04-01", "06-30"], ["Q3", "07-01", "09-30"], ["Q4", "10-01", "12-31"], ["H1", "01-01", "06-30"], ["H2", "07-01", "12-31"]].map(([lbl, a, b]) => {
                const yr = dataFrom.slice(0, 4);
                return (
                  <button key={lbl} onClick={() => setParams((p) => ({ ...p, from: `${yr}-${a}`, to: `${yr}-${b}` }))}
                    className="px-2 py-1 rounded border border-zinc-700 text-[11px] text-zinc-400 hover:text-zinc-200 hover:border-zinc-600">{lbl}</button>
                );
              })}
              {(params.from || params.to) && (
                <button onClick={() => setParams((p) => ({ ...p, from: null, to: null }))}
                  className="px-2 py-1 rounded text-[11px] text-amber-400/80 hover:text-amber-300">Full range</button>
              )}
            </div>
          </div>

          {bt ? (
            <>
              {bt.nTrades === 0 && (
                <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs text-amber-200">
                  <div className="font-medium text-amber-300">No trades in this run</div>
                  <div className="mt-1 text-amber-200/90">{bt.diagnostics.note}</div>
                  <div className="mt-1.5 text-amber-200/70 tabular-nums">
                    window {bt.nBars.toLocaleString("en-US")} bars · indicators warm up after ~{bt.diagnostics.warmupNeeded} bars
                    {bt.diagnostics.warmedAt ? ` (done ${bt.diagnostics.warmedAt.slice(0, 10)}, ${bt.diagnostics.barsAfterWarmup.toLocaleString("en-US")} bars left)` : " — not reached in this window"}
                    {" · "}{bt.diagnostics.emaCrosses} EMA crosses, {bt.diagnostics.crossesPassingFilters} passed the filters
                  </div>
                  {tf !== "m1" && (
                    <button onClick={() => setTf("m1")} className="mt-2 px-2.5 py-1 rounded bg-amber-500 text-zinc-950 text-[11px] font-medium hover:bg-amber-400">
                      Switch to 1m — the strategy's timeframe
                    </button>
                  )}
                </div>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 mt-4">
                <Stat label="Net P&L" value={usd(bt.netPnl)} tone={bt.netPnl >= 0 ? "up" : "down"} />
                <Stat label="Return" value={pct(bt.totalRet)} tone={bt.totalRet >= 0 ? "up" : "down"} />
                <Stat label="Buy & hold" value={pct(bt.benchRet)} tone={bt.benchRet >= 0 ? "up" : "down"} />
                <Stat label="Final equity" value={usd(bt.finalEquity)} />
                <Stat label="Max drawdown" value={`${usd(bt.maxDDdollar)} · ${pct(bt.maxDD)}`} tone="down" />
                <Stat label="Trades" value={`${bt.nTrades}`} />
                <Stat label="Win rate" value={(bt.winRate * 100).toFixed(0) + "%"} />
                <Stat label="Profit factor" value={bt.profitFactor === Infinity ? "∞" : bt.profitFactor.toFixed(2)} tone={bt.profitFactor >= 1 ? "up" : "down"} />
                <Stat label="Long / short" value={`${bt.nLong} / ${bt.nShort}`} />
                <Stat label="Avg trade" value={`${usd(bt.avgTrade)} · ${pct(bt.avgTradeRet)}`} tone={bt.avgTrade >= 0 ? "up" : "down"} />
                <Stat label="Avg win / loss" value={`${usd(bt.avgWin)} / ${usd(bt.avgLoss)}`} />
                <Stat label="Best / worst" value={`${usd(bt.bestTrade)} / ${usd(bt.worstTrade)}`} />
                <Stat label="Exposure" value={(bt.exposure * 100).toFixed(0) + "%"} />
                <Stat label="Sharpe ~" value={bt.sharpe.toFixed(2)} tone={bt.sharpe >= 0 ? "up" : "down"} />
              </div>

              {Object.keys(bt.exitBreakdown).length > 0 && (
                <div className="mt-2 text-xs text-zinc-500">
                  Exits — {Object.entries(bt.exitBreakdown).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                  {bt.openTrade && ` · still open: ${bt.openTrade.side} (${usd(bt.openTrade.pnl)})`}
                </div>
              )}

              <div className="mt-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-400 mb-1 px-1">
                  <span className="text-zinc-500 tabular-nums">
                    Tested {stamp(bt.periodStart, tf)} → {stamp(bt.periodEnd, tf)} · {bt.nBars.toLocaleString("en-US")} bars
                  </span>
                  <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5" style={{ background: C.strat }} />Strategy equity</span>
                  <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5" style={{ background: C.bench }} />Buy &amp; hold</span>
                </div>
                <Panel view={[0, bt.eq.length - 1]} height={160}
                  series={[
                    { data: bt.eq.map((e) => e.bench), color: C.bench, w: 1.2, label: "Buy & hold" },
                    { data: bt.eq.map((e) => e.equity), color: C.strat, w: 1.6, label: "Strategy" },
                  ]}
                  times={bt.eq.map((e) => e.t)}
                  fmtY={(v, d) => "$" + Math.round(v).toLocaleString("en-US", { maximumFractionDigits: d ?? 0 })} />
              </div>

              {bt.trades.length > 0 && (() => {
                const tradesPerPage = 15;
                const totalPages = Math.ceil(bt.trades.length / tradesPerPage);
                const startIdx = (tradePage - 1) * tradesPerPage;
                const endIdx = Math.min(startIdx + tradesPerPage, bt.trades.length);
                const pageTrades = bt.trades.slice(startIdx, endIdx);
                
                const downloadExcel = () => {
                  // Create CSV content (Excel-compatible)
                  const headers = ["Side", "Entry Time", "Entry Price", "Exit Time", "Exit Price", "Lots", "Bars", "Exit By", "P&L", "Return"];
                  const rows = bt.trades.map(t => [
                    t.side + (t.open ? " (open)" : ""),
                    t.entryTime,
                    t.entryPx,
                    t.exitTime,
                    t.exitPx,
                    t.lots.toFixed(2),
                    t.bars,
                    t.reason,
                    t.pnl.toFixed(2),
                    (t.ret * 100).toFixed(2) + "%"
                  ]);
                  
                  const csvContent = [
                    headers.join(","),
                    ...rows.map(row => row.map(cell => {
                      const cellStr = String(cell);
                      return cellStr.includes(",") ? `"${cellStr}"` : cellStr;
                    }).join(","))
                  ].join("\n");
                  
                  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
                  const link = document.createElement("a");
                  const url = URL.createObjectURL(blob);
                  link.setAttribute("href", url);
                  link.setAttribute("download", `trades_${new Date().toISOString().slice(0, 10)}.csv`);
                  link.style.visibility = "hidden";
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                };
                
                return (
                  <div className="mt-4 overflow-x-auto">
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs text-zinc-500">
                        Showing {startIdx + 1}-{endIdx} of {bt.trades.length} trades
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={downloadExcel}
                          className="px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-500 flex items-center gap-1.5"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          Download Excel
                        </button>
                        {totalPages > 1 && (
                          <>
                            <button
                              onClick={() => setTradePage(Math.max(1, tradePage - 1))}
                              disabled={tradePage === 1}
                              className="px-2 py-1 rounded border border-zinc-700 text-zinc-300 text-xs hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
                            >
                              Previous
                            </button>
                            <span className="text-xs text-zinc-400 tabular-nums">
                              Page {tradePage} of {totalPages}
                            </span>
                            <button
                              onClick={() => setTradePage(Math.min(totalPages, tradePage + 1))}
                              disabled={tradePage === totalPages}
                              className="px-2 py-1 rounded border border-zinc-700 text-zinc-300 text-xs hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
                            >
                              Next
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    <table className="w-full text-xs tabular-nums">
                      <thead className="text-zinc-500 text-left">
                        <tr><th className="py-1 pr-3">Side</th><th className="pr-3">Entry Time</th><th className="pr-3">Entry</th><th className="pr-3">Exit Time</th><th className="pr-3">Exit</th><th className="pr-3">Lots</th><th className="pr-3">Bars</th><th className="pr-3">Exit by</th><th className="pr-3">P&L</th><th className="pr-3">Return</th></tr>
                      </thead>
                      <tbody className="text-zinc-300">
                        {pageTrades.map((t, i) => (
                          <tr key={i} className="border-t border-zinc-800/60">
                            <td className={"py-1 pr-3 font-medium " + (t.side === "long" ? "text-emerald-400" : "text-rose-400")}>{t.side}{t.open ? " (open)" : ""}</td>
                            <td className="pr-3 text-zinc-400">{stamp(t.entryTime, tf)}</td>
                            <td className="pr-3">{fmt(t.entryPx)}</td>
                            <td className="pr-3 text-zinc-400">{stamp(t.exitTime, tf)}</td>
                            <td className="pr-3">{fmt(t.exitPx)}</td>
                            <td className="pr-3">{t.lots.toFixed(2)}</td>
                            <td className="pr-3">{t.bars}</td>
                            <td className="pr-3 text-zinc-500">{t.reason}</td>
                            <td className={"pr-3 " + (t.pnl >= 0 ? "text-emerald-400" : "text-rose-400")}>{usd(t.pnl)}</td>
                            <td className={"pr-3 " + (t.ret >= 0 ? "text-emerald-400" : "text-rose-400")}>{pct(t.ret)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </>
          ) : (
            <div className="mt-4 text-sm text-zinc-500">Adjust parameters and run to see stats, an equity curve, and entry/exit marks on the chart above.</div>
          )}

          <div className="mt-4 border-t border-zinc-800 pt-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-zinc-300">
                Across timeframes
                <span className="ml-2 text-[11px] text-zinc-600 tabular-nums font-normal">
                  {(params.from || dataFrom)} → {(params.to || dataTo)}
                </span>
              </div>
              <button onClick={compareTf} disabled={mtfBusy} className="px-3 py-1.5 rounded border border-zinc-700 text-zinc-300 text-xs hover:bg-zinc-800 disabled:opacity-50">
                {mtfBusy ? "Running…" : "Run all timeframes"}
              </button>
            </div>
            {mtf && (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-xs tabular-nums">
                  <thead className="text-zinc-500 text-left">
                    <tr><th className="py-1 pr-3">TF</th><th className="pr-3">Bars</th><th className="pr-3">Period</th><th className="pr-3">Net P&amp;L</th><th className="pr-3">Return</th><th className="pr-3">B&amp;H</th><th className="pr-3">Max DD</th><th className="pr-3">Trades</th><th className="pr-3">Win</th><th className="pr-3">L/S</th><th className="pr-3">PF</th></tr>
                  </thead>
                  <tbody className="text-zinc-300">
                    {mtf.map((m) => (
                      <tr key={m.key} className="border-t border-zinc-800/60">
                        <td className="py-1 pr-3 font-medium text-zinc-200">{m.label}</td>
                        <td className="pr-3">{m.r.nBars.toLocaleString("en-US")}</td>
                        <td className="pr-3 text-zinc-500">{m.r.periodStart.slice(0, 10)} → {m.r.periodEnd.slice(0, 10)}</td>
                        <td className={"pr-3 " + (m.r.netPnl >= 0 ? "text-emerald-400" : "text-rose-400")}>{usd(m.r.netPnl)}</td>
                        <td className={"pr-3 " + (m.r.totalRet >= 0 ? "text-emerald-400" : "text-rose-400")}>{pct(m.r.totalRet)}</td>
                        <td className="pr-3 text-zinc-400">{pct(m.r.benchRet)}</td>
                        <td className="pr-3 text-rose-400">{pct(m.r.maxDD)}</td>
                        <td className="pr-3">{m.r.nTrades}</td>
                        <td className="pr-3">{(m.r.winRate * 100).toFixed(0)}%</td>
                        <td className="pr-3">{m.r.nLong}/{m.r.nShort}</td>
                        <td className="pr-3">{m.r.profitFactor === Infinity ? "∞" : m.r.profitFactor.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="text-[11px] text-zinc-600 mt-4">
          {bars.length.toLocaleString("en-US")} bars · {TFS.find((t) => t.key === tf)?.label} timeframe · {DATASETS.find((d) => d.key === dataset)?.label}.
          Scroll or pinch to zoom the chart, drag to pan. Charts by{" "}
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer" className="text-zinc-500 hover:text-zinc-300 underline">TradingView</a>{" "}
          (Lightweight Charts). Educational demo — configure costs for a live-relevant backtest. Not financial advice.
        </div>
      </div>
    </div>
  );
}
