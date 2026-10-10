const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

const INPUT = path.join(
  ROOT,
  "analysis-results",
  "block-length-sensitivity",
  "block_length_sensitivity.csv",
);

const OUTPUT = path.join(
  ROOT,
  "analysis-results",
  "block-length-sensitivity",
  "period_stability_summary.csv",
);

const STRATEGY = "frequency_plus_recent250";
const METRIC = "top100";

function parseCSVLine(line) {
  const result = [];
  let value = "";
  let quoted = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        value += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      result.push(value);
      value = "";
    } else {
      value += char;
    }
  }

  result.push(value);
  return result;
}

function normalize(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

function findColumn(headers, candidates, includesText) {
  for (const candidate of candidates) {
    const index = headers.findIndex(
      (header) => normalize(header) === candidate,
    );
    if (index !== -1) return index;
  }

  if (includesText) {
    const index = headers.findIndex((header) =>
      normalize(header).includes(includesText),
    );
    if (index !== -1) return index;
  }

  return -1;
}

function numberValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

if (!fs.existsSync(INPUT)) {
  console.error("Input file not found:");
  console.error(INPUT);
  process.exit(1);
}

const lines = fs
  .readFileSync(INPUT, "utf8")
  .replace(/^\uFEFF/, "")
  .split(/\r?\n/)
  .filter((line) => line.trim().length > 0);

if (lines.length < 2) {
  console.error("The input CSV has no result rows.");
  process.exit(1);
}

const headers = parseCSVLine(lines[0]);
const records = lines.slice(1).map((line) => {
  const values = parseCSVLine(line);
  return Object.fromEntries(
    headers.map((header, index) => [header.trim(), values[index] ?? ""]),
  );
});

const periodCol = findColumn(
  headers,
  ["period", "periodname", "timeperiod", "segment"],
  "period",
);
const strategyCol = findColumn(headers, ["strategy"], "strategy");
const baselineCol = findColumn(headers, ["baseline"], "baseline");
const metricCol = findColumn(headers, ["metric"], "metric");
const blockCol = findColumn(headers, ["blocklength", "block_length"], "block");
const meanCol = findColumn(
  headers,
  ["meandifference", "mean_difference"],
  "mean",
);
const lowerCol = findColumn(headers, ["ci95lower", "ci95_lower"], "lower");
const upperCol = findColumn(headers, ["ci95upper", "ci95_upper"], "upper");

const required = {
  periodCol,
  strategyCol,
  baselineCol,
  metricCol,
  blockCol,
  meanCol,
  lowerCol,
  upperCol,
};

const missing = Object.entries(required)
  .filter(([, index]) => index === -1)
  .map(([name]) => name);

if (missing.length) {
  console.error("Could not identify required CSV columns:", missing.join(", "));
  console.error("Actual headers:", headers.join(" | "));
  process.exit(1);
}

const filtered = records
  .map((row) => ({
    period: row[headers[periodCol]],
    strategy: row[headers[strategyCol]],
    baseline: row[headers[baselineCol]],
    metric: row[headers[metricCol]],
    blockLength: numberValue(row[headers[blockCol]]),
    meanDifference: numberValue(row[headers[meanCol]]),
    ci95Lower: numberValue(row[headers[lowerCol]]),
    ci95Upper: numberValue(row[headers[upperCol]]),
  }))
  .filter(
    (row) =>
      normalize(row.strategy) === normalize(STRATEGY) &&
      normalize(row.metric) === normalize(METRIC),
  )
  .sort((a, b) => {
    const periodOrder = ["all", "early", "middle", "late"];
    const ai = periodOrder.indexOf(normalize(a.period));
    const bi = periodOrder.indexOf(normalize(b.period));

    if (ai !== -1 && bi !== -1 && ai !== bi) return ai - bi;

    return (
      normalize(a.period).localeCompare(normalize(b.period)) ||
      normalize(a.baseline).localeCompare(normalize(b.baseline)) ||
      (a.blockLength ?? 0) - (b.blockLength ?? 0)
    );
  });

if (!filtered.length) {
  console.error(`No rows found for strategy=${STRATEGY}, metric=${METRIC}.`);
  console.error("Check the strategy and metric values in the CSV.");
  process.exit(1);
}

console.log(`Loaded ${records.length} bootstrap result rows.`);
console.log(`Selected ${filtered.length} Top 100 result rows.`);
console.log("\nTOP 100: RESULTS BY PERIOD AND BLOCK LENGTH\n");

console.table(
  filtered.map((row) => ({
    period: row.period,
    baseline: row.baseline,
    blockLength: row.blockLength,
    meanDifference: row.meanDifference?.toFixed(4),
    ci95Lower: row.ci95Lower?.toFixed(4),
    ci95Upper: row.ci95Upper?.toFixed(4),
    ciAboveZero: row.ci95Lower !== null && row.ci95Lower > 0,
  })),
);

const groups = new Map();

for (const row of filtered) {
  const key = `${row.period}|||${row.baseline}`;

  if (!groups.has(key)) {
    groups.set(key, []);
  }

  groups.get(key).push(row);
}

const summary = [];

for (const rows of groups.values()) {
  const first = rows[0];

  const valid = rows.filter(
    (row) =>
      row.ci95Lower !== null &&
      row.ci95Upper !== null &&
      row.meanDifference !== null,
  );

  const positiveCI = valid.filter((row) => row.ci95Lower > 0).length;
  const zeroIncluded = valid.filter(
    (row) => row.ci95Lower <= 0 && row.ci95Upper >= 0,
  ).length;

  summary.push({
    period: first.period,
    strategy: STRATEGY,
    baseline: first.baseline,
    metric: METRIC,
    blockLengthsTested: valid.length,
    positiveConfidenceIntervals: positiveCI,
    intervalsIncludingZero: zeroIncluded,
    allBlockLengthsPositive: valid.length > 0 && positiveCI === valid.length,
    averageObservedDifference:
      valid.length > 0
        ? valid.reduce((sum, row) => sum + row.meanDifference, 0) / valid.length
        : null,
    interpretation:
      valid.length === 0
        ? "No valid confidence intervals"
        : positiveCI === valid.length
          ? "Positive CI across every tested block length"
          : positiveCI > 0
            ? "Positive CI for some block lengths only"
            : "No tested block length has a CI entirely above zero",
  });
}

summary.sort((a, b) => {
  const order = ["all", "early", "middle", "late"];
  const ai = order.indexOf(normalize(a.period));
  const bi = order.indexOf(normalize(b.period));

  if (ai !== -1 && bi !== -1 && ai !== bi) return ai - bi;
  return normalize(a.period).localeCompare(normalize(b.period));
});

console.log("\nPERIOD STABILITY SUMMARY\n");

console.table(
  summary.map((row) => ({
    period: row.period,
    baseline: row.baseline,
    blockLengthsTested: row.blockLengthsTested,
    positiveCIs: row.positiveConfidenceIntervals,
    includesZero: row.intervalsIncludingZero,
    averageDifference: row.averageObservedDifference?.toFixed(4),
    interpretation: row.interpretation,
  })),
);

fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });

const outputHeaders = [
  "period",
  "strategy",
  "baseline",
  "metric",
  "blockLengthsTested",
  "positiveConfidenceIntervals",
  "intervalsIncludingZero",
  "allBlockLengthsPositive",
  "averageObservedDifference",
  "interpretation",
];

const outputLines = [
  outputHeaders.join(","),
  ...summary.map((row) =>
    outputHeaders.map((header) => csvEscape(row[header])).join(","),
  ),
];

fs.writeFileSync(OUTPUT, outputLines.join("\n") + "\n", "utf8");

console.log("\nSummary saved to:");
console.log(OUTPUT);
