const fs = require("fs");
const path = require("path");

const INPUT_FILE = path.join(
  __dirname,
  "..",
  "analysis-results",
  "next-draw-strategy-backtest-v2",
  "next_draw_v2_per_target.csv",
);

const OUTPUT_DIR = path.join(
  __dirname,
  "..",
  "analysis-results",
  "time-period-stability",
);

const TOP_K_VALUES = [10, 25, 50, 100];

const STRATEGIES = [
  "historical_frequency",
  "recent_25",
  "recent_50",
  "recent_100",
  "recent_250",
  "frequency_plus_recent25",
  "frequency_plus_recent50",
  "frequency_plus_recent100",
  "frequency_plus_recent250",
  "random_baseline",
];

function parseCsvLine(line) {
  const result = [];
  let value = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        value += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === "," && !inQuotes) {
      result.push(value);
      value = "";
    } else {
      value += char;
    }
  }

  result.push(value);
  return result;
}

function readCsv(filePath) {
  const content = fs
    .readFileSync(filePath, "utf8")
    .replace(/^\uFEFF/, "")
    .trim();

  if (!content) return [];

  const lines = content.split(/\r?\n/);
  const headers = parseCsvLine(lines[0]);

  return lines
    .slice(1)
    .filter(Boolean)
    .map((line) => {
      const values = parseCsvLine(line);
      const row = {};

      headers.forEach((header, index) => {
        row[header] = values[index] ?? "";
      });

      return row;
    });
}

function mean(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function summarizePeriod(rows, periodName) {
  const results = [];

  for (const strategy of STRATEGIES) {
    const result = {
      period: periodName,
      strategy,
      tests: rows.length,
    };

    let top25Total = 0;

    for (const k of TOP_K_VALUES) {
      const column = `${strategy}_top${k}`;

      const values = rows.map((row) => {
        const value = Number(row[column]);
        return Number.isFinite(value) ? value : 0;
      });

      const total = values.reduce((sum, value) => sum + value, 0);

      result[`top${k}`] = mean(values).toFixed(4);

      if (k === 25) top25Total = total;
    }

    result.top25Precision =
      rows.length > 0
        ? ((top25Total / (25 * rows.length)) * 100).toFixed(3) + "%"
        : "0.000%";

    results.push(result);
  }

  const randomResult = results.find(
    (result) => result.strategy === "random_baseline",
  );

  const randomTop25 = Number(randomResult?.top25 || 0);

  for (const result of results) {
    const top25 = Number(result.top25);

    result.top25Lift =
      randomTop25 > 0 ? (top25 / randomTop25).toFixed(3) : "N/A";
  }

  return results;
}

function main() {
  if (!fs.existsSync(INPUT_FILE)) {
    console.error("Input file not found:");
    console.error(INPUT_FILE);
    console.error("Run backtestNextDrawStrategiesV2.js first.");
    process.exitCode = 1;
    return;
  }

  const rows = readCsv(INPUT_FILE)
    .filter((row) => Number.isFinite(Number(row.targetIndex)))
    .sort((a, b) => Number(a.targetIndex) - Number(b.targetIndex));

  if (rows.length < 30) {
    console.error("Not enough prediction rows:", rows.length);
    process.exitCode = 1;
    return;
  }

  const requiredColumns = [
    ...STRATEGIES.map((strategy) => `${strategy}_top25`),
  ];

  const missing = requiredColumns.filter(
    (column) => !Object.prototype.hasOwnProperty.call(rows[0], column),
  );

  if (missing.length) {
    console.error("Missing expected columns:", missing.join(", "));
    console.error("Check that the V2 per-target CSV is being used.");
    process.exitCode = 1;
    return;
  }

  // Divide predictions chronologically into three nearly equal groups.
  const firstEnd = Math.floor(rows.length / 3);
  const secondEnd = Math.floor((rows.length * 2) / 3);

  const periods = [
    {
      name: "early",
      rows: rows.slice(0, firstEnd),
    },
    {
      name: "middle",
      rows: rows.slice(firstEnd, secondEnd),
    },
    {
      name: "late",
      rows: rows.slice(secondEnd),
    },
  ];

  const allResults = [];

  console.log("Prediction rows:", rows.length);
  console.log("First target:", rows[0].date);
  console.log("Last target:", rows[rows.length - 1].date);

  for (const period of periods) {
    const periodResults = summarizePeriod(period.rows, period.name);
    allResults.push(...periodResults);

    console.log(`\n========== ${period.name.toUpperCase()} PERIOD ==========`);
    console.log(
      `Targets: ${period.rows.length}; ` +
        `${period.rows[0].date} to ${period.rows[period.rows.length - 1].date}`,
    );

    console.table(
      periodResults.slice().sort((a, b) => Number(b.top25) - Number(a.top25)),
    );
  }

  // Show how combined strategies compare with historical frequency
  // within each period. Positive differences indicate more Top-25 hits
  // per target than the historical-frequency baseline.
  const comparisonRows = [];

  for (const period of periods) {
    const periodResults = allResults.filter(
      (result) => result.period === period.name,
    );

    const baseline = periodResults.find(
      (result) => result.strategy === "historical_frequency",
    );

    for (const result of periodResults) {
      comparisonRows.push({
        period: period.name,
        strategy: result.strategy,
        tests: result.tests,
        top25: result.top25,
        top25LiftVsRandom: result.top25Lift,
        top25DifferenceVsHistorical: (
          Number(result.top25) - Number(baseline.top25)
        ).toFixed(4),
      });
    }
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  function writeCsv(filePath, data) {
    if (!data.length) return;

    const headers = Object.keys(data[0]);

    const escape = (value) => {
      const text = String(value ?? "");
      return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };

    const content = [
      headers.map(escape).join(","),
      ...data.map((row) =>
        headers.map((header) => escape(row[header])).join(","),
      ),
    ].join("\n");

    fs.writeFileSync(filePath, content, "utf8");
  }

  writeCsv(
    path.join(OUTPUT_DIR, "time_period_stability_summary.csv"),
    allResults,
  );

  writeCsv(
    path.join(OUTPUT_DIR, "time_period_baseline_comparison.csv"),
    comparisonRows,
  );

  console.log("\nOutput directory:", OUTPUT_DIR);
  console.log("No database records were changed.");
}

main();
