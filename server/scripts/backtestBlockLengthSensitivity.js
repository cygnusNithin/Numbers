const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------
// Configuration
// ---------------------------------------------------------

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
  "block-length-sensitivity",
);

const BLOCK_LENGTHS = [10, 25, 50, 100];
const BOOTSTRAP_ITERATIONS = 5000;
const RANDOM_SEED = 20261010;

const COMPARISONS = [
  {
    strategy: "frequency_plus_recent250",
    baseline: "random_baseline",
  },
  {
    strategy: "frequency_plus_recent250",
    baseline: "historical_frequency",
  },
];

const METRICS = ["top25", "top100"];

// ---------------------------------------------------------
// CSV parsing
// ---------------------------------------------------------

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

function loadCSV(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Input CSV not found: ${filePath}`);
  }

  const content = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");

  const lines = content.split(/\r?\n/).filter((line) => line.trim() !== "");

  if (lines.length < 2) {
    throw new Error("Input CSV contains no data rows.");
  }

  const headers = parseCSVLine(lines[0]);
  const index = new Map(headers.map((header, i) => [header, i]));

  const required = [
    "targetIndex",
    "date",
    ...COMPARISONS.flatMap(({ strategy, baseline }) =>
      METRICS.flatMap((metric) => [
        `${strategy}_${metric}`,
        `${baseline}_${metric}`,
      ]),
    ),
  ];

  const missing = required.filter((column) => !index.has(column));

  if (missing.length) {
    throw new Error(`Missing required columns:\n${missing.join("\n")}`);
  }

  const rows = lines.slice(1).map((line, rowIndex) => {
    const values = parseCSVLine(line);

    const row = {
      targetIndex: Number(values[index.get("targetIndex")]),
      date: values[index.get("date")],
    };

    for (const { strategy, baseline } of COMPARISONS) {
      for (const metric of METRICS) {
        const strategyColumn = `${strategy}_${metric}`;
        const baselineColumn = `${baseline}_${metric}`;

        row[strategyColumn] = Number(values[index.get(strategyColumn)]);
        row[baselineColumn] = Number(values[index.get(baselineColumn)]);

        if (
          !Number.isFinite(row[strategyColumn]) ||
          !Number.isFinite(row[baselineColumn])
        ) {
          throw new Error(
            `Invalid numeric value at CSV data row ${rowIndex + 2}`,
          );
        }
      }
    }

    if (!Number.isFinite(row.targetIndex) || !row.date) {
      throw new Error(`Invalid target metadata at row ${rowIndex + 2}`);
    }

    return row;
  });

  rows.sort((a, b) => a.targetIndex - b.targetIndex);

  for (let i = 1; i < rows.length; i++) {
    if (rows[i].targetIndex === rows[i - 1].targetIndex) {
      throw new Error(`Duplicate targetIndex found: ${rows[i].targetIndex}`);
    }
  }

  return rows;
}

// ---------------------------------------------------------
// Deterministic PRNG
// ---------------------------------------------------------

function createRandom(seed) {
  let state = seed >>> 0;

  return function random() {
    state = (state + 0x6d2b79f5) >>> 0;

    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);

    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------
// Statistics
// ---------------------------------------------------------

function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function quantile(sortedValues, probability) {
  const position = (sortedValues.length - 1) * probability;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);

  if (lower === upper) return sortedValues[lower];

  const fraction = position - lower;

  return sortedValues[lower] * (1 - fraction) + sortedValues[upper] * fraction;
}

function getPeriodRows(rows, period) {
  if (period === "all") return rows;

  const start = period === "early" ? 0 : period === "middle" ? 1 : 2;
  const groups = [
    rows.slice(0, Math.floor(rows.length / 3)),
    rows.slice(Math.floor(rows.length / 3), Math.floor((2 * rows.length) / 3)),
    rows.slice(Math.floor((2 * rows.length) / 3)),
  ];

  return groups[start];
}

function bootstrapDifference(differences, blockLength, seed) {
  const n = differences.length;

  if (!n) {
    throw new Error("Cannot bootstrap an empty period.");
  }

  const random = createRandom(seed);
  const observedMean = mean(differences);
  const bootstrapMeans = new Array(BOOTSTRAP_ITERATIONS);

  for (let iteration = 0; iteration < BOOTSTRAP_ITERATIONS; iteration++) {
    let total = 0;
    let sampled = 0;

    while (sampled < n) {
      const start = Math.floor(random() * n);
      const length = Math.min(blockLength, n - sampled);

      for (let j = 0; j < length; j++) {
        total += differences[(start + j) % n];
      }

      sampled += length;
    }

    bootstrapMeans[iteration] = total / n;
  }

  bootstrapMeans.sort((a, b) => a - b);

  const lower = quantile(bootstrapMeans, 0.025);
  const upper = quantile(bootstrapMeans, 0.975);

  return {
    observedMean,
    ci95Lower: lower,
    ci95Upper: upper,
    fractionNonPositive:
      bootstrapMeans.filter((value) => value <= 0).length /
      BOOTSTRAP_ITERATIONS,
    fractionNonNegative:
      bootstrapMeans.filter((value) => value >= 0).length /
      BOOTSTRAP_ITERATIONS,
    conclusion:
      lower > 0
        ? "CI entirely above zero"
        : upper < 0
          ? "CI entirely below zero"
          : "CI includes zero",
  };
}

// ---------------------------------------------------------
// Main
// ---------------------------------------------------------

function main() {
  const rows = loadCSV(INPUT_FILE);

  if (rows.length !== 1697) {
    console.warn(`Warning: expected 1697 targets, loaded ${rows.length}.`);
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log(`Loaded ${rows.length} targets.`);
  console.log(`Bootstrap iterations: ${BOOTSTRAP_ITERATIONS}`);
  console.log(`Block lengths: ${BLOCK_LENGTHS.join(", ")}`);

  const periods = ["all", "early", "middle", "late"];
  const output = [];

  for (const period of periods) {
    const periodRows = getPeriodRows(rows, period);

    console.log(`\nAnalyzing ${period}: ${periodRows.length} targets`);

    for (const comparison of COMPARISONS) {
      for (const metric of METRICS) {
        const strategyColumn = `${comparison.strategy}_${metric}`;
        const baselineColumn = `${comparison.baseline}_${metric}`;

        const differences = periodRows.map(
          (row) => row[strategyColumn] - row[baselineColumn],
        );

        const observedMean = mean(differences);

        for (const blockLength of BLOCK_LENGTHS) {
          // Keep runs reproducible and separate across settings.
          const seed =
            RANDOM_SEED +
            blockLength * 100003 +
            periods.indexOf(period) * 1009 +
            COMPARISONS.indexOf(comparison) * 101 +
            METRICS.indexOf(metric) * 17;

          const result = bootstrapDifference(differences, blockLength, seed);

          output.push({
            period,
            targets: periodRows.length,
            strategy: comparison.strategy,
            baseline: comparison.baseline,
            metric,
            blockLength,
            meanDifference: observedMean,
            ci95Lower: result.ci95Lower,
            ci95Upper: result.ci95Upper,
            bootstrapFractionNonPositive: result.fractionNonPositive,
            bootstrapFractionNonNegative: result.fractionNonNegative,
            intervalConclusion: result.conclusion,
          });
        }
      }
    }
  }

  const headers = Object.keys(output[0]);

  function escapeCSV(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  const csv = [
    headers.join(","),
    ...output.map((row) =>
      headers.map((header) => escapeCSV(row[header])).join(","),
    ),
  ].join("\n");

  const outputFile = path.join(OUTPUT_DIR, "block_length_sensitivity.csv");

  fs.writeFileSync(outputFile, csv, "utf8");

  console.log("\nALL-PERIOD RESULTS");
  console.table(
    output
      .filter((row) => row.period === "all")
      .map((row) => ({
        strategy: row.strategy,
        baseline: row.baseline,
        metric: row.metric,
        blockLength: row.blockLength,
        meanDifference: row.meanDifference.toFixed(4),
        ci95Lower: row.ci95Lower.toFixed(4),
        ci95Upper: row.ci95Upper.toFixed(4),
        conclusion: row.intervalConclusion,
      })),
  );

  console.log("\nOutput:");
  console.log(outputFile);
  console.log("No database changes were made.");
}

try {
  main();
} catch (error) {
  console.error("\nTEST FAILED");
  console.error(error.message);
  process.exitCode = 1;
}
