const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

const MIN_TRAIN_DRAWS = 300;
const TOP_K_VALUES = [10, 25, 50, 100];
const NUMBER_COUNT = 10000;

const OUTPUT_DIR = path.join(
  __dirname,
  "..",
  "analysis-results",
  "gap-strategy-backtest",
);

function toDate(value) {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (typeof value === "string") {
    const match = value.trim().match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);

    if (match) {
      const day = Number(match[1]);
      const month = Number(match[2]);
      const year = Number(match[3]);
      const date = new Date(Date.UTC(year, month - 1, day));

      if (
        date.getUTCDate() !== day ||
        date.getUTCMonth() !== month - 1 ||
        date.getUTCFullYear() !== year
      ) {
        return null;
      }

      return date;
    }
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getNumbers(doc) {
  const result = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      const number = String(item.number ?? "").trim();
      if (/^\d{4}$/.test(number)) result.add(number);
    }
  }

  return result;
}

function pad(n) {
  return String(n).padStart(4, "0");
}

function mean(values) {
  return values.length
    ? values.reduce((sum, x) => sum + x, 0) / values.length
    : 0;
}

function rank(scores) {
  return scores
    .map((score, index) => ({ number: pad(index), score }))
    .sort((a, b) => b.score - a.score || a.number.localeCompare(b.number));
}

// Fixed, reproducible pseudo-random ranking for the random baseline.
// The ranking changes by target draw, but never uses the target outcome.
function randomScore(numberIndex, targetIndex) {
  let x =
    (Math.imul(numberIndex + 1, 374761393) +
      Math.imul(targetIndex + 1, 668265263)) |
    0;

  x = Math.imul(x ^ (x >>> 13), 1274126177);
  x ^= x >>> 16;

  return (x >>> 0) / 4294967296;
}

function evaluate(strategy, ranking, actualNumbers, targetIndex) {
  const actual = actualNumbers;
  const hits = {};

  for (const k of TOP_K_VALUES) {
    const selected = ranking.slice(0, k);
    hits[`top${k}_hits`] = selected.reduce(
      (sum, row) => sum + (actual.has(row.number) ? 1 : 0),
      0,
    );
    hits[`top${k}_precision`] = hits[`top${k}_hits`] / k;
  }

  return {
    target_draw_index: targetIndex,
    strategy,
    actual_number_count: actual.size,
    ...hits,
  };
}

async function main() {
  await mongoose.connect(MONGO_URI);

  const docs = await AbsoluteData.find({})
    .select("serialNumber recordNumber date drawDate series")
    .lean();

  // A serial number identifies a draw event. Do not deduplicate by date.
  const unique = new Map();

  for (const doc of docs) {
    const serial = String(doc.serialNumber || "").trim();
    if (serial && !unique.has(serial)) unique.set(serial, doc);
  }

  const draws = [...unique.values()]
    .map((doc) => ({
      serialNumber: String(doc.serialNumber).trim(),
      recordNumber: Number(doc.recordNumber) || 0,
      date: toDate(doc.drawDate) || toDate(doc.date),
      numbers: getNumbers(doc),
    }))
    .filter((draw) => draw.date && draw.numbers.size > 0)
    .sort(
      (a, b) =>
        a.date.getTime() - b.date.getTime() ||
        a.recordNumber - b.recordNumber ||
        a.serialNumber.localeCompare(b.serialNumber),
    );

  if (draws.length <= MIN_TRAIN_DRAWS) {
    throw new Error(`Not enough valid draws: ${draws.length}`);
  }

  console.log(`Valid draw events: ${draws.length}`);

  // All features at target t are calculated from draws [0, t).
  const totalHits = Array(NUMBER_COUNT).fill(0);
  const lastSeen = Array(NUMBER_COUNT).fill(-1);
  const recentHistory = Array.from({ length: NUMBER_COUNT }, () => []);

  const rows = [];
  const strategies = [
    "historical_frequency",
    "recent_25_draws",
    "shorter_gap",
    "frequency_plus_gap",
    "random_baseline",
  ];

  for (let t = 0; t < draws.length; t++) {
    if (t >= MIN_TRAIN_DRAWS) {
      const frequencyScores = Array(NUMBER_COUNT).fill(0);
      const recentScores = Array(NUMBER_COUNT).fill(0);
      const gapScores = Array(NUMBER_COUNT).fill(0);
      const combinedScores = Array(NUMBER_COUNT).fill(0);
      const randomScores = Array(NUMBER_COUNT).fill(0);

      for (let n = 0; n < NUMBER_COUNT; n++) {
        const history = recentHistory[n];
        const recent25 = history.filter((index) => index >= t - 25).length;

        // Gap in intervening draw events since the last appearance.
        // Never-seen numbers receive gap=t.
        const gap = lastSeen[n] < 0 ? t : t - 1 - lastSeen[n];

        frequencyScores[n] = totalHits[n];
        recentScores[n] = recent25 / 25;

        // Prefer smaller gaps as suggested by the aggregate gap analysis.
        // This is a hypothesis to test, not a probability estimate.
        gapScores[n] = 1 / (1 + gap);

        // Normalize each component to avoid raw-frequency scale dominating.
        combinedScores[n] =
          normalizeValue(totalHits[n], totalHits) +
          normalizeValue(gapScores[n], gapScores);

        randomScores[n] = randomScore(n, t);
      }

      const actual = draws[t].numbers;

      const rankings = {
        historical_frequency: rank(frequencyScores),
        recent_25_draws: rank(recentScores),
        shorter_gap: rank(gapScores),
        frequency_plus_gap: rank(combinedScores),
        random_baseline: rank(randomScores),
      };

      for (const strategy of strategies) {
        rows.push(evaluate(strategy, rankings[strategy], actual, t));
      }
    }

    // Update state only after the target draw has been evaluated.
    for (const number of draws[t].numbers) {
      const n = Number(number);

      totalHits[n]++;
      lastSeen[n] = t;
      recentHistory[n].push(t);
    }

    if (t > 0 && t % 250 === 0) {
      console.log(`Processed draw ${t}/${draws.length}`);
    }
  }

  function summarize() {
    return strategies.map((strategy) => {
      const subset = rows.filter((row) => row.strategy === strategy);
      const summary = {
        strategy,
        tests: subset.length,
      };

      for (const k of TOP_K_VALUES) {
        summary[`top${k}_hits`] = mean(
          subset.map((row) => row[`top${k}_hits`]),
        );
        summary[`top${k}_precision`] = mean(
          subset.map((row) => row[`top${k}_precision`]),
        );
      }

      return summary;
    });
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  function csvEscape(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function writeCsv(file, data) {
    if (!data.length) return;

    const columns = Object.keys(data[0]);
    const content = [
      columns.join(","),
      ...data.map((row) => columns.map((key) => csvEscape(row[key])).join(",")),
    ].join("\n");

    fs.writeFileSync(path.join(OUTPUT_DIR, file), content, "utf8");
  }

  const summary = summarize();

  writeCsv("gap_backtest_results.csv", rows);
  writeCsv("gap_backtest_summary.csv", summary);

  console.log("\nBACKTEST SUMMARY");
  console.table(
    summary.map((row) => ({
      strategy: row.strategy,
      tests: row.tests,
      top10: row.top10_hits.toFixed(4),
      top25: row.top25_hits.toFixed(4),
      top50: row.top50_hits.toFixed(4),
      top100: row.top100_hits.toFixed(4),
      precision25: (row.top25_precision * 100).toFixed(3) + "%",
    })),
  );

  console.log(`\nOutput directory: ${OUTPUT_DIR}`);

  await mongoose.disconnect();
}

// Min-max normalization is calculated from the training snapshot only.
function normalizeValue(value, allValues) {
  let min = Infinity;
  let max = -Infinity;

  for (const x of allValues) {
    if (x < min) min = x;
    if (x > max) max = x;
  }

  return max > min ? (value - min) / (max - min) : 0;
}

main().catch(async (error) => {
  console.error(error);
  await mongoose.disconnect().catch(() => {});
  process.exitCode = 1;
});
