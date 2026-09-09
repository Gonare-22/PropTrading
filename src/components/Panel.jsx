import { useState } from "react";
import { useWidth } from "../lib/useWidth.js";
import { COLORS as C, fmt, shortDate, stamp } from "../lib/format.js";

// SVG line panel used for the equity curve. `times` (ISO strings aligned to the
// series) adds a date axis and a hover readout of every series value.
export default function Panel({ series, view, height = 120, bands, fmtY = fmt, domain, times }) {
  const [ref, W] = useWidth();
  const [hover, setHover] = useState(null); // { idx, x, mx }
  const H = height, padL = 6, padR = 58, padT = 8, padB = times ? 26 : 16;
  const [s, e] = view;
  const plotW = Math.max(W - padR - padL, 10), plotH = H - padB - padT;

  let lo = domain ? domain[0] : Infinity, hi = domain ? domain[1] : -Infinity;
  if (!domain) {
    for (const sr of series) {
      for (let i = s; i <= e; i++) {
        const v = sr.data[i];
        if (v == null) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    if (!isFinite(lo) || !isFinite(hi)) { lo = 0; hi = 1; }
  }
  if (lo === hi) { lo -= 1; hi += 1; }

  const n = e - s + 1;
  const x = (i) => padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (p) => padT + (1 - (p - lo) / (hi - lo)) * plotH;
  const step = Math.max(1, Math.ceil(n / 1500));
  const path = (data) => {
    let d = "", st = false;
    for (let i = 0; i < n; i += step) {
      const v = data[s + i];
      if (v == null) { st = false; continue; }
      d += (st ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " ";
      st = true;
    }
    return d;
  };
  const guides = bands || [lo, (lo + hi) / 2, hi];

  const onMove = (ev) => {
    const rect = ev.currentTarget.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const frac = Math.max(0, Math.min(1, (mx - padL) / plotW));
    const idx = Math.round(frac * (n - 1));
    setHover({ idx, mx });
  };

  const hi_ = hover && hover.idx;
  const abs = hover ? s + hover.idx : null;

  return (
    <div ref={ref} className="w-full relative">
      <svg
        width={W} height={H} className="block"
        style={{ cursor: "crosshair" }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {guides.map((b, i) => (
          <g key={i}>
            <line x1={padL} x2={padL + plotW} y1={y(b)} y2={y(b)} stroke={C.grid} strokeDasharray={bands ? "3 3" : ""} />
            <text x={padL + plotW + 6} y={y(b) + 3} fill={C.text} fontSize={9} fontFamily="ui-monospace,monospace">{fmtY(b, 0)}</text>
          </g>
        ))}
        {series.map((sr, i) => (
          <path key={i} d={path(sr.data)} fill="none" stroke={sr.color} strokeWidth={sr.w || 1.4} opacity={0.95} />
        ))}
        {times && Array.from({ length: Math.min(6, n) }, (_, i) => {
          const k = Math.round((i / (Math.min(6, n) - 1)) * (n - 1));
          const iso = times[s + k];
          if (!iso) return null;
          const anchor = i === 0 ? "start" : i === Math.min(6, n) - 1 ? "end" : "middle";
          return (
            <text key={i} x={x(k)} y={H - 5} fill={C.text} fontSize={9} textAnchor={anchor} fontFamily="ui-monospace,monospace">
              {shortDate(iso)}
            </text>
          );
        })}
        {hover && (
          <g pointerEvents="none">
            <line x1={x(hi_)} x2={x(hi_)} y1={padT} y2={padT + plotH} stroke={C.axis} strokeDasharray="3 3" />
            {series.map((sr, i) => {
              const v = sr.data[abs];
              return v == null ? null : <circle key={i} cx={x(hi_)} cy={y(v)} r={3} fill={sr.color} stroke="#0a0a0a" strokeWidth={1} />;
            })}
          </g>
        )}
      </svg>
      {hover && (
        <div
          className="absolute z-10 pointer-events-none rounded border border-zinc-700 bg-zinc-900/95 px-2 py-1.5 text-[11px] tabular-nums shadow-lg"
          style={{ left: Math.min(Math.max(hover.mx + 12, 4), Math.max(4, W - 210)), top: 4 }}
        >
          {times && times[abs] && <div className="text-zinc-400 mb-0.5">{stamp(times[abs])}</div>}
          {series.map((sr, i) => {
            const v = sr.data[abs];
            return (
              <div key={i} className="flex items-center gap-1.5">
                <span className="inline-block w-2 h-2 rounded-sm" style={{ background: sr.color }} />
                <span className="text-zinc-400">{sr.label || `series ${i + 1}`}</span>
                <span className="text-zinc-100 ml-auto">{v == null ? "—" : fmtY(v)}</span>
              </div>
            );
          })}
          {series.length === 2 && series[0].data[abs] != null && series[1].data[abs] != null && (() => {
            const d = series[1].data[abs] - series[0].data[abs];
            return (
              <div className={"mt-0.5 pt-0.5 border-t border-zinc-800 " + (d >= 0 ? "text-emerald-400" : "text-rose-400")}>
                {series[1].label} vs {series[0].label}: {d >= 0 ? "+" : "−"}{fmtY(Math.abs(d))}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
