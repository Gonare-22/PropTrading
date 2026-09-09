// Aggregate a DAT_MT 1-minute CSV into a full set of timeframe JSON files.
// Usage: node scripts/aggregate.mjs [path/to/data.csv] [outputDir]
// CSV format (no header): DATE(YYYY.MM.DD),TIME(HH:MM),OPEN,HIGH,LOW,CLOSE,VOLUME
import fs from "node:fs";
import readline from "node:readline";

const src = process.argv[2] || "./raw.csv";
const outDir = process.argv[3] || "./public/data";
if (!fs.existsSync(src)) {
  console.error(`CSV not found: ${src}\nPass the path, e.g. node scripts/aggregate.mjs ./DAT_MT_XAUUSD_M1_2025.csv`);
  process.exit(1);
}

// key = short name used in the app + JSON top-level key.
// minutes = intraday bucket size; "D" / "W" are calendar day / ISO-week.
const TIMEFRAMES = [
  { key: "m5", minutes: 5 },
  { key: "m15", minutes: 15 },
  { key: "m30", minutes: 30 },
  { key: "h1", minutes: 60 },
  { key: "h2", minutes: 120 },
  { key: "h4", minutes: 240 },
  { key: "daily", span: "D" },
  { key: "weekly", span: "W" },
];

const buckets = new Map(TIMEFRAMES.map((t) => [t.key, new Map()]));
const m1 = [];
const round = (x) => Math.round(x * 100) / 100;

function push(map, key, iso, o, h, l, c) {
  const cur = map.get(key);
  if (!cur) map.set(key, [iso, o, h, l, c]);
  else { cur[2] = Math.max(cur[2], h); cur[3] = Math.min(cur[3], l); cur[4] = c; }
}

const pad = (n) => String(n).padStart(2, "0");
function mondayOf(Y, M, D) {
  const d = new Date(Date.UTC(+Y, +M - 1, +D));
  const shift = (d.getUTCDay() + 6) % 7; // 0 = Monday
  d.setUTCDate(d.getUTCDate() - shift);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

const rl = readline.createInterface({ input: fs.createReadStream(src), crlfDelay: Infinity });
let count = 0, skipped = 0, lastKey = "";
for await (const raw of rl) {
  const row = raw.split(",");
  if (row.length < 6) continue;
  const [date, tm] = [row[0], row[1]];
  const o = round(+row[2]), h = round(+row[3]), l = round(+row[4]), c = round(+row[5]);
  if (Number.isNaN(o)) continue;

  // Drop non-increasing rows. DAT/HistData files repeat the whole DST fall-back
  // hour verbatim (e.g. 2025-10-26 19:00-19:59 twice); charts need strictly
  // ascending time, and the duplicate hour is not real second-pass trading.
  const key = `${date} ${tm}`;
  if (key <= lastKey) { skipped++; continue; }
  lastKey = key;

  const [Y, M, D] = date.split(".");
  const [hh, mm] = tm.split(":").map(Number);
  const minOfDay = hh * 60 + mm;

  m1.push([`${Y}-${M}-${D}T${tm}:00`, o, h, l, c]);

  for (const tf of TIMEFRAMES) {
    const map = buckets.get(tf.key);
    if (tf.minutes) {
      const b = Math.floor(minOfDay / tf.minutes) * tf.minutes;
      const bhh = pad(Math.floor(b / 60)), bmm = pad(b % 60);
      push(map, `${date} ${bhh}:${bmm}`, `${Y}-${M}-${D}T${bhh}:${bmm}:00`, o, h, l, c);
    } else if (tf.span === "D") {
      push(map, date, `${Y}-${M}-${D}T00:00:00`, o, h, l, c);
    } else {
      const wk = mondayOf(Y, M, D);
      push(map, wk, `${wk}T00:00:00`, o, h, l, c);
    }
  }
  count++;
}

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(`${outDir}/m1.json`, JSON.stringify({ m1 }));
const sizes = [`1m:${m1.length}`];
for (const tf of TIMEFRAMES) {
  const arr = [...buckets.get(tf.key).values()];
  fs.writeFileSync(`${outDir}/${tf.key}.json`, JSON.stringify({ [tf.key]: arr }));
  sizes.push(`${tf.key}:${arr.length}`);
}
console.log(`Processed ${count} rows (${skipped} non-increasing rows dropped) -> ${sizes.join(" ")}`);
console.log(`Wrote ${TIMEFRAMES.length + 1} JSON files to ${outDir}/`);
