export const Stat = ({ label, value, tone }) => (
  <div className="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2">
    <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
    <div className={"text-sm font-medium tabular-nums " + (tone === "up" ? "text-emerald-400" : tone === "down" ? "text-rose-400" : "text-zinc-100")}>{value}</div>
  </div>
);

export const NumField = ({ label, value, onChange, min = 0, max = Infinity, step }) => (
  <label className="text-[11px] text-zinc-400">
    {label}
    <input
      type="number" value={value} min={min} max={max === Infinity ? undefined : max} step={step}
      onChange={(e) => {
        const n = e.target.valueAsNumber;
        if (!Number.isNaN(n)) onChange(Math.min(max, Math.max(min, n)));
      }}
      className="mt-0.5 block w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-100 tabular-nums"
    />
  </label>
);

export const Select = ({ label, value, onChange, options }) => (
  <label className="text-[11px] text-zinc-400">
    {label}
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="mt-0.5 block w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-100"
    >
      {options.map(([v, l]) => (
        <option key={v} value={v}>{l}</option>
      ))}
    </select>
  </label>
);

export const Check = ({ checked, onChange, children }) => (
  <label className="flex items-center gap-1.5 text-xs text-zinc-400">
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    {children}
  </label>
);

export const Group = ({ title, children }) => (
  <div className="mt-3 pt-3 border-t border-zinc-800/60">
    <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">{title}</div>
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 items-end">{children}</div>
  </div>
);

export const Toggle = ({ on, set, color, children }) => (
  <button
    onClick={() => set(!on)}
    className={"px-2.5 py-1 rounded text-xs border transition-colors " + (on ? "border-transparent text-zinc-900 font-medium" : "border-zinc-700 text-zinc-400 hover:text-zinc-200")}
    style={on ? { background: color } : {}}
  >
    {children}
  </button>
);
