// Run the XAUUSD strategy over every aggregated timeframe and write a report.
// Usage:
//   node scripts/backtest.mjs [--tf m1] [--no-short] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
//   node scripts/backtest.mjs --set capital=25000 --set spread=0.3 --set commissionPerLot=7
//   node scripts/backtest.mjs --set sizing=lots --set lots=0.5
//   node scripts/backtest.mjs --set stopLoss=1.5 --set stopMode=percent --set takeProfit=3 --set tpMode=r
import fs from "node:fs";
import path from "node:path";
import { runStrategy, DEFAULT_PARAMS } from "../src/lib/strategy.js";

const args = process.argv.slice(2);
const flag = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
const only = flag("--tf");
const allowShort = !args.includes("--no-short");
const from = flag("--from");
const to = flag("--to");

// --set key=value (repeatable). Values are coerced: number → Number, true/false → bool.
const sets = {};
args.forEach((a, i) => {
  if (a !== "--set") return;
  const [key, ...rest] = (args[i + 1] || "").split("=");
  let v = rest.join("=");
  if (!(key in DEFAULT_PARAMS)) { console.error(`Unknown --set key: ${key}`); process.exit(1); }
  if (v === "true") v = true;
  else if (v === "false") v = false;
  else if (v !== "" && !Number.isNaN(Number(v))) v = Number(v);
  sets[key] = v;
});

const opts = { allowShort, ...(from ? { from } : {}), ...(to ? { to } : {}), ...sets };
const stamp = (iso) => iso.slice(0, 16).replace("T", " ");

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
].filter((t) => !only || t.key === only);

const dataDir = path.join(process.cwd(), "public", "data");
const pct = (x) => (x >= 0 ? "+" : "") + (x * 100).toFixed(2) + "%";
const usd = (x) => (x < 0 ? "-$" : "$") + Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: 0 });
const load = (key) => JSON.parse(fs.readFileSync(path.join(dataDir, `${key}.json`), "utf8"))[key];

const runs = {};
for (const tf of TFS) {
  const bars = load(tf.key);
  const t0 = Date.now();
  const r = runStrategy(bars, opts);
  runs[tf.key] = { label: tf.label, bars: bars.length, ms: Date.now() - t0, r };
  console.log(
    `${tf.label.padEnd(3)} ${String(r.nBars).padStart(7)} bars  ` +
      `${r.periodStart.slice(0, 10)}→${r.periodEnd.slice(0, 10)}  ` +
      `ret ${pct(r.totalRet).padStart(9)}  B&H ${pct(r.benchRet).padStart(9)}  ` +
      `DD ${pct(r.maxDD).padStart(8)}  trades ${String(r.nTrades).padStart(4)}  ` +
      `win ${(r.winRate * 100).toFixed(0).padStart(3)}%  PF ${r.profitFactor.toFixed(2)}  (${runs[tf.key].ms}ms)`
  );
}

// ---- Monthly breakdown for the 1m run (the strategy's intended timeframe) ----
let monthly = null;
if (runs.m1) {
  const { r } = runs.m1;
  const m = {};
  for (const t of r.trades) {
    const key = t.exitTime.slice(0, 7);
    (m[key] ||= { n: 0, ret: 0, wins: 0 });
    m[key].n++;
    m[key].ret += t.ret;
    if (t.ret > 0) m[key].wins++;
  }
  monthly = Object.entries(m).sort();
}

// ---- Markdown report ----
const md = [];
md.push("# XAUUSD Strategy Backtest\n");
const anyRun = Object.values(runs)[0]?.r;
const dataSpan = anyRun ? `${stamp(anyRun.dataStart)} → ${stamp(anyRun.dataEnd)}` : "n/a";
const testSpan = anyRun ? `${stamp(anyRun.periodStart)} → ${stamp(anyRun.periodEnd)}` : "n/a";
md.push(`_Generated ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC · long/short ${allowShort ? "enabled" : "disabled"}_\n`);
md.push("## Period\n");
md.push(`- **Data available:** ${dataSpan}`);
md.push(`- **Backtest window:** ${testSpan}${from || to ? "" : "  _(full range — pass `--from` / `--to` to narrow)_"}`);
md.push("- Indicators and Stoch-RSI permission warm up on bars before the window start; any open position is closed at the window end.\n");
md.push("## Rules\n");
md.push("- **Entry LONG** — EMA20 crosses above EMA50 · Stoch-RSI long permission active · CHOP ≤ 50");
md.push("- **Entry SHORT** — EMA20 crosses below EMA50 · Stoch-RSI short permission active · CHOP ≤ 50");
md.push("- **Exit** — opposite EMA20/50 cross only (no CHOP / Stoch-RSI exit)");
md.push("- **Stoch-RSI permission** — long arms at K ≥ 79, holds while K > 50, disarms on K < 50 (mirror for short at K ≤ 21 / K < 50)");
md.push("");
const cfg = { ...DEFAULT_PARAMS, ...opts };
md.push("## Config\n");
md.push(`- **Capital:** $${cfg.capital.toLocaleString()} · **sizing:** ${sizingText(cfg)}`);
md.push(`- **Costs:** spread ${cfg.spread} pt · slippage ${cfg.slippage} pt · commission $${cfg.commissionPerLot}/lot/side` +
  (cfg.spread || cfg.slippage || cfg.commissionPerLot ? "" : "  _(frictionless — the default)_"));
md.push(`- **Risk mgmt:** ${riskText(cfg)}`);
md.push(`- **Execution:** fill on ${cfg.fillOn === "nextOpen" ? "next bar open" : "signal bar close"}` +
  `${cfg.allowFlip ? "" : " · no same-bar flips"}${cfg.sessionFilter ? ` · entries ${cfg.sessionStart}:00–${cfg.sessionEnd}:00 only` : ""}`);
md.push(`- Raw params: \`${JSON.stringify(cfg)}\`\n`);

function sizingText(c) {
  if (c.sizing === "lots") return `${c.lots} lot (${c.lots * c.contractSize} oz) fixed`;
  if (c.sizing === "cash") return `$${c.cashPerTrade.toLocaleString()} notional fixed`;
  if (c.sizing === "risk") return `${c.riskPercent}% of equity risked per trade`;
  return `${c.percentEquity}% of equity${c.percentEquity > 100 ? " (leveraged)" : ""}`;
}
function riskText(c) {
  const parts = [];
  if (c.stopLoss) parts.push(`stop ${c.stopLoss} ${c.stopMode}`);
  if (c.takeProfit) parts.push(`target ${c.takeProfit} ${c.tpMode}`);
  if (c.trailStop) parts.push(`trail ${c.trailStop} ${c.trailMode}`);
  return parts.length ? parts.join(" · ") : "none — exit on opposite EMA cross only (the spec)";
}

md.push("## Results by timeframe\n");
md.push("| TF | Bars | Period | Net P&L | Return | Buy & Hold | Max DD | Trades | Win % | Long/Short | PF | Sharpe~ | Exposure |");
md.push("|----|------|--------|---------|--------|-----------|--------|--------|-------|-----------|-----|---------|----------|");
for (const tf of TFS) {
  const { r } = runs[tf.key];
  md.push(
    `| ${runs[tf.key].label} | ${r.nBars.toLocaleString("en-US")} | ${r.periodStart.slice(0, 10)} → ${r.periodEnd.slice(0, 10)} | ${usd(r.netPnl)} | ${pct(r.totalRet)} | ${pct(r.benchRet)} | ${pct(r.maxDD)} | ${r.nTrades} | ${(r.winRate * 100).toFixed(0)}% | ${r.nLong}/${r.nShort} | ${r.profitFactor.toFixed(2)} | ${r.sharpe.toFixed(2)} | ${(r.exposure * 100).toFixed(0)}% |`
  );
}
md.push("");

if (runs.m1) {
  const { r } = runs.m1;
  md.push("## 1-minute detail\n");
  md.push(`- Window: **${stamp(r.periodStart)} → ${stamp(r.periodEnd)}** (${r.nBars.toLocaleString("en-US")} bars)`);
  md.push(`- Net P&L: **${usd(r.netPnl)}** → final equity **${usd(r.finalEquity)}** from $${cfg.capital.toLocaleString()} · max drawdown ${usd(r.maxDDdollar)} (${pct(r.maxDD)})`);
  md.push(`- Avg trade ${usd(r.avgTrade)} (${pct(r.avgTradeRet)}) · avg win ${usd(r.avgWin)} · avg loss ${usd(r.avgLoss)}`);
  md.push(`- Best ${usd(r.bestTrade)} · worst ${usd(r.worstTrade)} · avg hold ${r.avgBars.toFixed(0)} bars`);
  md.push(`- Long win rate ${(r.longWinRate * 100).toFixed(0)}% · short win rate ${(r.shortWinRate * 100).toFixed(0)}%`);
  md.push(`- Exits by reason: ${Object.entries(r.exitBreakdown).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}`);
  if (r.openTrade) md.push(`- Position still open at window end: ${r.openTrade.side} from ${r.openTrade.entryTime} (${usd(r.openTrade.pnl)})`);
  md.push("");
  if (monthly) {
    md.push("### Monthly (by exit date)\n");
    md.push("| Month | Trades | Sum of trade returns | Win % |");
    md.push("|-------|--------|----------------------|-------|");
    for (const [key, v] of monthly) {
      md.push(`| ${key} | ${v.n} | ${pct(v.ret)} | ${((v.wins / v.n) * 100).toFixed(0)}% |`);
    }
    md.push("");
  }
}

md.push("## Caveats\n");
md.push("- No spread, commission or slippage. On XAUUSD 1m a ~20–30c round-trip spread alone would swamp the average trade — treat 1m results as directional research, not a live expectancy.");
md.push("- Fully-invested sizing; a fixed-risk / ATR-stop model would change the equity curve and drawdown materially.");
md.push("- Every timeframe is bucketed from the same 1m feed by clock time (see `scripts/aggregate.mjs`); weekly bars start Monday 00:00.");
md.push("- 1D / 1W show 0 trades: EMA50 + Stoch-RSI warmup consumes most of the short series.");

const outMd = path.join(process.cwd(), "backtest-report.md");
fs.writeFileSync(outMd, md.join("\n"));

const outJson = path.join(process.cwd(), "backtest-results.json");
fs.writeFileSync(
  outJson,
  JSON.stringify(
    Object.fromEntries(
      Object.entries(runs).map(([k, v]) => [
        k,
        { label: v.label, bars: v.bars, stats: strip(v.r) },
      ])
    ),
    null,
    2
  )
);

function strip(r) {
  const { eq, marks, trades, ...rest } = r;
  return { ...rest, sampleTrades: trades.slice(0, 20) };
}

console.log(`\nWrote ${path.relative(process.cwd(), outMd)} and ${path.relative(process.cwd(), outJson)}`);
