const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

const DATA_FILE = path.join(
  ROOT,
  "analysis-results",
  "next-draw-strategy-backtest-v2",
  "next_draw_v2_per_target.csv",
);

const SOURCE_FILE = path.join(
  ROOT,
  "scripts",
  "backtestNextDrawStrategiesV2.js",
);

const OUTPUT_DIR = path.join(ROOT, "analysis-results", "backtest-integrity");

const OUTPUT_FILE = path.join(OUTPUT_DIR, "backtest_integrity_issues.csv");

const TOP_K = [10, 25, 50, 100];

function parseCSVLine(line) {
  const result = [];
  let value = "";
  let quoted = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];

    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        value += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === "," && !quoted) {
      result.push(value);
      value = "";
    } else {
      value += ch;
    }
  }

  result.push(value);
  return result;
}

function csvEscape(value) {
  const s = String(value ?? "");
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function parseNumber(value) {
  if (value === undefined || String(value).trim() === "") {
    return null;
  }

  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

const issues = [];

function addIssue(severity, target, check, details) {
  issues.push({ severity, target, check, details });
}

if (!fs.existsSync(DATA_FILE)) {
  console.error("Backtest CSV not found:", DATA_FILE);
  process.exit(1);
}

const lines = fs
  .readFileSync(DATA_FILE, "utf8")
  .replace(/^\uFEFF/, "")
  .split(/\r?\n/)
  .filter((line) => line.trim() !== "");

const headers = parseCSVLine(lines[0]).map((h) => h.trim());
const rows = lines.slice(1).map((line) => {
  const values = parseCSVLine(line);
  return Object.fromEntries(
    headers.map((header, i) => [header, values[i] ?? ""]),
  );
});

const required = ["targetIndex", "serialNumber", "date", "winningNumberCount"];

for (const col of required) {
  if (!headers.includes(col)) {
    console.error(`Required column missing: ${col}`);
    console.error("Found columns:", headers.join(", "));
    process.exit(1);
  }
}

const strategies = [
  ...new Set(
    headers
      .filter((h) => /_top(?:10|25|50|100)$/.test(h))
      .map((h) => h.replace(/_top(?:10|25|50|100)$/, "")),
  ),
];

console.log(`Rows loaded: ${rows.length}`);
console.log(`Columns loaded: ${headers.length}`);
console.log(`Strategies found: ${strategies.length}`);
console.log(strategies.join(", "));

if (rows.length !== 1697) {
  addIssue(
    "WARNING",
    "ALL",
    "unexpected_row_count",
    `Expected 1697 rows based on previous run; found ${rows.length}`,
  );
}

// Check required fields, numeric values, date parsing and duplicates.
const seenTargets = new Set();
let previousTarget = -Infinity;
let previousDate = null;

for (let i = 0; i < rows.length; i++) {
  const row = rows[i];
  const lineNumber = i + 2;
  const target = String(row.targetIndex).trim();
  const index = parseNumber(target);
  const winningCount = parseNumber(row.winningNumberCount);
  const date = new Date(row.date);

  if (index === null || !Number.isInteger(index)) {
    addIssue("ERROR", target, "invalid_targetIndex", `CSV line ${lineNumber}`);
  } else {
    if (seenTargets.has(target)) {
      addIssue(
        "ERROR",
        target,
        "duplicate_targetIndex",
        `CSV line ${lineNumber}`,
      );
    }
    seenTargets.add(target);

    if (index <= previousTarget) {
      addIssue(
        "WARNING",
        target,
        "targetIndex_not_increasing",
        `Previous index=${previousTarget}; current=${index}`,
      );
    }
    previousTarget = index;
  }

  if (!row.serialNumber.trim()) {
    addIssue("ERROR", target, "missing_serialNumber", `CSV line ${lineNumber}`);
  }

  if (!row.date.trim() || Number.isNaN(date.getTime())) {
    addIssue("ERROR", target, "invalid_date", `Value=${row.date}`);
  } else {
    if (previousDate && date < previousDate) {
      addIssue(
        "WARNING",
        target,
        "date_not_increasing",
        `Previous=${previousDate.toISOString().slice(0, 10)}; current=${row.date}`,
      );
    }
    previousDate = date;
  }

  if (
    winningCount === null ||
    !Number.isInteger(winningCount) ||
    winningCount < 0
  ) {
    addIssue(
      "ERROR",
      target,
      "invalid_winningNumberCount",
      `Value=${row.winningNumberCount}`,
    );
  }

  // Every strategy should have all four Top-K hit-count columns.
  for (const strategy of strategies) {
    const values = TOP_K.map((k) => parseNumber(row[`${strategy}_top${k}`]));

    if (values.some((v) => v === null || !Number.isInteger(v) || v < 0)) {
      addIssue(
        "ERROR",
        target,
        "invalid_strategy_hit_count",
        `${strategy}: ${values.join(", ")}`,
      );
      continue;
    }

    // A larger top-K list must contain every member of the smaller list.
    for (let k = 1; k < values.length; k++) {
      if (values[k] < values[k - 1]) {
        addIssue(
          "ERROR",
          target,
          "topK_hits_not_monotonic",
          `${strategy}: ${TOP_K[k - 1]}=${values[k - 1]}, ` +
            `${TOP_K[k]}=${values[k]}`,
        );
      }
    }
  }
}

// Detect strategies whose recorded per-target scores are exactly identical.
console.log("\nEXACT STRATEGY OVERLAP CHECK");

const strategySignatures = new Map();

for (const strategy of strategies) {
  const signature = rows
    .map((row) => TOP_K.map((k) => row[`${strategy}_top${k}`]).join(":"))
    .join("|");

  if (!strategySignatures.has(signature)) {
    strategySignatures.set(signature, []);
  }
  strategySignatures.get(signature).push(strategy);
}

for (const group of strategySignatures.values()) {
  if (group.length > 1) {
    console.log("Identical recorded hit-count vectors:", group.join(" = "));
    addIssue(
      "INFO",
      "ALL",
      "identical_strategy_hit_counts",
      group.join(" = ") +
        "; identical counts do not prove identical selected numbers",
    );
  }
}

console.log("\nHIT-COUNT SANITY CHECK");

for (const strategy of strategies) {
  const totals = {};

  for (const k of TOP_K) {
    const col = `${strategy}_top${k}`;
    totals[`top${k}`] = rows.reduce(
      (sum, row) => sum + (parseNumber(row[col]) ?? 0),
      0,
    );
  }

  console.log(strategy, totals);
}

// Inspect source code for manual review. This is not a proof of no leakage.
console.log("\nSOURCE CODE AUDIT");

if (!fs.existsSync(SOURCE_FILE)) {
  console.log("Original script not found at:", SOURCE_FILE);
  console.log("Check the actual filename in the scripts folder.");
  addIssue("WARNING", "SOURCE", "source_file_not_found", SOURCE_FILE);
} else {
  const source = fs.readFileSync(SOURCE_FILE, "utf8");
  const sourceLines = source.split(/\r?\n/);

  const patterns = [
    /targetIndex/i,
    /recent.?250/i,
    /slice\s*\(/i,
    /sort\s*\(/i,
    /random/i,
    /winningNumberCount/i,
    /historical/i,
    /serialNumber/i,
    /\.date\b/i,
  ];

  const printed = new Set();

  for (let i = 0; i < sourceLines.length; i++) {
    if (patterns.some((pattern) => pattern.test(sourceLines[i]))) {
      // Print context around matching lines without excessive repetition.
      for (
        let j = Math.max(0, i - 1);
        j <= Math.min(sourceLines.length - 1, i + 1);
        j++
      ) {
        if (!printed.has(j)) {
          console.log(`${String(j + 1).padStart(4)} | ${sourceLines[j]}`);
          printed.add(j);
        }
      }
    }
  }

  console.log(`Source lines: ${sourceLines.length}`);
  console.log(
    "Review the target loop, training-data boundaries, recent-window " +
      "construction, ranking, and random baseline manually.",
  );
}

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const outputHeaders = ["severity", "target", "check", "details"];
const outputLines = [
  outputHeaders.join(","),
  ...issues.map((issue) =>
    outputHeaders.map((h) => csvEscape(issue[h])).join(","),
  ),
];

fs.writeFileSync(OUTPUT_FILE, outputLines.join("\n") + "\n", "utf8");

const errors = issues.filter((i) => i.severity === "ERROR").length;
const warnings = issues.filter((i) => i.severity === "WARNING").length;
const infos = issues.filter((i) => i.severity === "INFO").length;

console.log("\nFINAL SUMMARY");
console.log("Errors:", errors);
console.log("Warnings:", warnings);
console.log("Informational findings:", infos);
console.log("Issues report:", OUTPUT_FILE);

if (errors === 0) {
  console.log(
    "No basic CSV integrity errors detected. This does not establish " +
      "that the original backtest is free from data leakage.",
  );
}
