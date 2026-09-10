// Split yearly CSV data into monthly JSON files for better performance
// Usage: node scripts/split-by-month.mjs [year]
import fs from "node:fs";
import readline from "node:readline";

const year = process.argv[2];
if (!year || !["2022", "2023", "2024", "2025"].includes(year)) {
  console.error(`Usage: node scripts/split-by-month.mjs [year]\nExample: node scripts/split-by-month.mjs 2022`);
  process.exit(1);
}

const src = `./public/data/${year}/DAT_MT_XAUUSD_M1_${year}.csv`;
const outBaseDir = `./public/data/${year}`;

if (!fs.existsSync(src)) {
  console.error(`CSV not found: ${src}`);
  process.exit(1);
}

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

const MONTHS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
const MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

// Store data by month
const monthlyData = {};
MONTHS.forEach(month => {
  monthlyData[month] = {
    m1: [],
    buckets: new Map(TIMEFRAMES.map((t) => [t.key, new Map()]))
  };
});

const round = (x) => Math.round(x * 100) / 100;

function push(map, key, iso, o, h, l, c) {
  const cur = map.get(key);
  if (!cur) map.set(key, [iso, o, h, l, c]);
  else { cur[2] = Math.max(cur[2], h); cur[3] = Math.min(cur[3], l); cur[4] = c; }
}

const pad = (n) => String(n).padStart(2, "0");
function mondayOf(Y, M, D) {
  const d = new Date(Date.UTC(+Y, +M - 1, +D));
  const shift = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - shift);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

const rl = readline.createInterface({ input: fs.createReadStream(src), crlfDelay: Infinity });
let count = 0, skipped = 0, lastKey = "";

console.log(`Processing ${year} data...`);

for await (const raw of rl) {
  const row = raw.split(",");
  if (row.length < 6) continue;
  const [date, tm] = [row[0], row[1]];
  const o = round(+row[2]), h = round(+row[3]), l = round(+row[4]), c = round(+row[5]);
  if (Number.isNaN(o)) continue;

  const key = `${date} ${tm}`;
  if (key <= lastKey) { skipped++; continue; }
  lastKey = key;

  const [Y, M, D] = date.split(".");
  const month = M;
  
  if (!monthlyData[month]) continue;

  const [hh, mm] = tm.split(":").map(Number);
  const minOfDay = hh * 60 + mm;

  // Add to m1 for this month
  monthlyData[month].m1.push([`${Y}-${M}-${D}T${tm}:00`, o, h, l, c]);

  // Aggregate into other timeframes
  for (const tf of TIMEFRAMES) {
    const map = monthlyData[month].buckets.get(tf.key);
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

console.log(`Processed ${count} rows (${skipped} skipped)`);

// Write monthly files
MONTHS.forEach((month, idx) => {
  const data = monthlyData[month];
  if (data.m1.length === 0) {
    console.log(`Skipping ${MONTH_NAMES[idx]} (no data)`);
    return;
  }

  const monthDir = `${outBaseDir}/${MONTH_NAMES[idx]}`;
  fs.mkdirSync(monthDir, { recursive: true });

  // Write m1
  fs.writeFileSync(`${monthDir}/m1.json`, JSON.stringify({ m1: data.m1 }));
  
  // Write other timeframes
  for (const tf of TIMEFRAMES) {
    const arr = [...data.buckets.get(tf.key).values()];
    fs.writeFileSync(`${monthDir}/${tf.key}.json`, JSON.stringify({ [tf.key]: arr }));
  }

  console.log(`✓ ${MONTH_NAMES[idx]}: ${data.m1.length.toLocaleString()} bars`);
});

console.log(`\nDone! Created monthly folders in ${outBaseDir}/`);
