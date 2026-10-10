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
  "statistical-reliability",
);

const BOOTSTRAP_ITERATIONS = 2000;
const BLOCK_LENGTH = 25;
const SEED = 20261009;
const METRICS = [25, 100];

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
    const ch = line[i];

    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        value += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      result.push(value);
      value = "";
    } else {
      value += ch;
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

      headers.forEach((header, i) => {
        row[header] = values[i] ?? "";
      });

      return row;
    });
}

function makeRandom(seed) {
  let state = seed >>> 0;

  return function random() {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentile(sortedValues, p) {
  const position = (sortedValues.length - 1) * p;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);

  if (lower === upper) return sortedValues[lower];

  const fraction = position - lower;

  return sortedValues[lower] * (1 - fraction) + sortedValues[upper] * fraction;
}

function getPeriodGroups(rows) {
  const firstEnd = Math.floor(rows.length / 3);
  const secondEnd = Math.floor((rows.length * 2) / 3);

  return [
    { period: "all", rows },
    { period: "early", rows: rows.slice(0, firstEnd) },
    { period: "middle", rows: rows.slice(firstEnd, secondEnd) },
    { period: "late", rows: rows.slice(secondEnd) },
  ];
}

/*
 * Paired circular block bootstrap.
 *
 * Resample blocks of consecutive per-target differences. The same sampled
 * target indices are used for each paired strategy comparison.
 */
function bootstrapDifference(differences, seed) {
  const n = differences.length;

  if (!n) {
    throw new Error("Cannot bootstrap an empty set of differences.");
  }

  const rng = makeRandom(seed);
  const observed = mean(differences);
  const bootstrapMeans = new Array(BOOTSTRAP_ITERATIONS);

  for (let iteration = 0; iteration < BOOTSTRAP_ITERATIONS; iteration++) {
    let sum = 0;
    let count = 0;

    while (count < n) {
      const start = Math.floor(rng() * n);

      for (let offset = 0; offset < BLOCK_LENGTH && count < n; offset++) {
        const index = (start + offset) % n;
        sum += differences[index];
        count++;
      }
    }

    bootstrapMeans[iteration] = sum / n;
  }

  bootstrapMeans.sort((a, b) => a - b);

  const lower = percentile(bootstrapMeans, 0.025);
  const upper = percentile(bootstrapMeans, 0.975);

  // This is a bootstrap sign fraction, not a formal p-value.
  const fractionNonPositive =
    bootstrapMeans.filter((value) => value <= 0).length / BOOTSTRAP_ITERATIONS;

  const fractionNonNegative =
    bootstrapMeans.filter((value) => value >= 0).length / BOOTSTRAP_ITERATIONS;

  return {
    meanDifference: observed,
    ci95Lower: lower,
    ci95Upper: upper,
    bootstrapFractionNonPositive: fractionNonPositive,
    bootstrapFractionNonNegative: fractionNonNegative,
    positiveInterval: lower > 0,
    negativeInterval: upper < 0,
  };
}

function writeCsv(filePath, rows) {
  if (!rows.length) return;

  const headers = Object.keys(rows[0]);

  const escape = (value) => {
    const text = String(value ?? "");

    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };

  const lines = [
    headers.map(escape).join(","),
    ...rows.map((row) =>
      headers.map((header) => escape(row[header])).join(","),
    ),
  ];

  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

function main() {
  if (!fs.existsSync(INPUT_FILE)) {
    console.error("Input file not found:", INPUT_FILE);
    console.error("Run backtestNextDrawStrategiesV2.js first.");
    process.exitCode = 1;
    return;
  }

  const rows = readCsv(INPUT_FILE)
    .filter((row) => Number.isFinite(Number(row.targetIndex)))
    .sort((a, b) => Number(a.targetIndex) - Number(b.targetIndex));

  if (rows.length < BLOCK_LENGTH * 3) {
    console.error("Too few prediction rows for this block-bootstrap test.");
    process.exitCode = 1;
    return;
  }

  for (const strategy of STRATEGIES) {
    for (const k of METRICS) {
      const column = `${strategy}_top${k}`;

      if (!Object.prototype.hasOwnProperty.call(rows[0], column)) {
        console.error("Required column missing:", column);
        process.exitCode = 1;
        return;
      }
    }
  }

  const groups = getPeriodGroups(rows);
  const results = [];

  for (const group of groups) {
    console.log(
      `\nAnalyzing ${group.period}: ${group.rows.length} prediction targets`,
    );

    const baselines = ["historical_frequency", "random_baseline"];

    for (const strategy of STRATEGIES) {
      for (const baseline of baselines) {
        if (strategy === baseline) continue;

        for (const k of METRICS) {
          const column = `${strategy}_top${k}`;
          const baselineColumn = `${baseline}_top${k}`;

          const differences = group.rows.map(
            (row) => Number(row[column]) - Number(row[baselineColumn]),
          );

          if (differences.some((value) => !Number.isFinite(value))) {
            throw new Error(`Invalid values in ${column} or ${baselineColumn}`);
          }

          const result = bootstrapDifference(
            differences,
            SEED + results.length * 101 + k * 7 + group.period.length,
          );

          results.push({
            period: group.period,
            targets: group.rows.length,
            strategy,
            baseline,
            metric: `top${k}`,
            meanStrategyHits: mean(
              group.rows.map((row) => Number(row[column])),
            ).toFixed(4),
            meanBaselineHits: mean(
              group.rows.map((row) => Number(row[baselineColumn])),
            ).toFixed(4),
            meanDifference: result.meanDifference.toFixed(4),
            ci95Lower: result.ci95Lower.toFixed(4),
            ci95Upper: result.ci95Upper.toFixed(4),
            bootstrapFractionNonPositive:
              result.bootstrapFractionNonPositive.toFixed(3),
            bootstrapFractionNonNegative:
              result.bootstrapFractionNonNegative.toFixed(3),
            intervalConclusion: result.positiveInterval
              ? "CI entirely above zero"
              : result.negativeInterval
                ? "CI entirely below zero"
                : "CI includes zero",
          });
        }
      }
    }
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  writeCsv(
    path.join(OUTPUT_DIR, "statistical_reliability_results.csv"),
    results,
  );

  const top25All = results
    .filter((row) => row.period === "all" && row.metric === "top25")
    .sort((a, b) => Number(b.meanDifference) - Number(a.meanDifference));

  const top100All = results
    .filter((row) => row.period === "all" && row.metric === "top100")
    .sort((a, b) => Number(b.meanDifference) - Number(a.meanDifference));

  console.log("\nALL-PERIOD TOP-25 PAIRED DIFFERENCES");
  console.log(
    "Positive meanDifference means the strategy found more hits per target.",
  );
  console.table(top25All);

  console.log("\nALL-PERIOD TOP-100 PAIRED DIFFERENCES");
  console.table(top100All);

  console.log("\nOutput directory:", OUTPUT_DIR);
  console.log("This script only reads the backtest CSV; no database changes.");
}

main();
