export const fmt = (n, d = 2) =>
  n == null ? "\u2014" : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (n) => (n >= 0 ? "+" : "") + (n * 100).toFixed(1) + "%";
export const usd = (n, d = 0) =>
  (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const shortDate = (iso) =>
  new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

const INTRADAY = new Set(["m1", "m5", "m15", "m30", "h1", "h2", "h4"]);

// Axis tick label — drops the time on daily/weekly, keeps HH:MM intraday.
export const axisLabel = (iso, tf) => {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  if (!INTRADAY.has(tf)) return day;
  return `${day} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
};

// Full crosshair / "as of" stamp.
export const stamp = (iso, tf) => {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
  if (!tf || !INTRADAY.has(tf)) return date;
  return `${date}  ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
};

export const COLORS = {
  up: "#34d399", down: "#f87171", grid: "#1f2430", axis: "#3f4654", text: "#8b93a3",
  sma: "#fbbf24", ema: "#60a5fa", bb: "#a78bfa", bench: "#6b7280", strat: "#fbbf24",
  emaFast: "#38bdf8", emaSlow: "#f472b6", stochK: "#fbbf24", stochD: "#60a5fa", chop: "#a3e635",
  entry: "#34d399", exit: "#f87171",
};
