/**
 * backtestNextDrawStrategies.js
 *
 * Goal:
 *   Test rankings against ALL winning numbers in the next draw.
 *   Unlike the cycle-feature test, previously seen numbers remain
 *   eligible candidates.
 *
 * Strategies:
 *   1. historical_frequency
 *   2. recent_25
 *   3. recent_50
 *   4. recent_100
 *   5. recent_250
 *   6. frequency_plus_recent100
 *   7. frequency_plus_recent50
 *   8. frequency_plus_recent25
 *   9. frequency_plus_recent250
 *  10. random_baseline
 *
 * Features are calculated before the target draw is added.
 * Database is read-only.
 *
 * Run:
 *   node .\scripts\backtestNextDrawStrategies.js
 */

const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const TOTAL_NUMBERS = 10000;
const MIN_TRAINING_DRAWS = 300;
const TOP_K = [10, 25, 50, 100];

const OUTPUT_DIR = path.join(
  __dirname,
  "../analysis-results/next-draw-strategy-backtest",
);

const RECENT_WINDOWS = [25, 50, 100, 250];

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

// ---------------------------------------------------------
// Parse dates
// ---------------------------------------------------------

function parseDate(doc) {
  if (doc.drawDate) {
    const d = new Date(doc.drawDate);

    if (!Number.isNaN(d.getTime())) {
      return new Date(
        Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()),
      );
    }
  }

  if (typeof doc.date === "string") {
    const match = doc.date.trim().match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);

    if (match) {
      const [, day, month, year] = match;

      const d = new Date(
        Date.UTC(Number(year), Number(month) - 1, Number(day)),
      );

      if (!Number.isNaN(d.getTime())) return d;
    }
  }

  return null;
}

// ---------------------------------------------------------
// Extract unique numbers per draw
// ---------------------------------------------------------

function extractNumbers(doc) {
  const numbers = new Set();

  if (!Array.isArray(doc.series)) return numbers;

  for (const series of doc.series) {
    if (!Array.isArray(series.numbers)) continue;

    for (const item of series.numbers) {
      if (!item || item.number == null) continue;

      const number = String(item.number).trim().padStart(4, "0");

      if (/^\d{4}$/.test(number)) {
        numbers.add(number);
      }
    }
  }

  return numbers;
}

function compareDraws(a, b) {
  const dateDifference = a.date - b.date;
  if (dateDifference !== 0) return dateDifference;

  const recordA = Number(a.recordNumber);
  const recordB = Number(b.recordNumber);

  if (
    Number.isFinite(recordA) &&
    Number.isFinite(recordB) &&
    recordA !== recordB
  ) {
    return recordA - recordB;
  }

  return String(a.serialNumber).localeCompare(String(b.serialNumber));
}

async function loadDraws() {
  const docs = await AbsoluteData.find({}).lean();
  const seenSerials = new Set();
  const draws = [];

  let skipped = 0;
  let duplicateSerials = 0;

  for (const doc of docs) {
    const serialNumber = String(doc.serialNumber || "").trim();

    if (!serialNumber) {
      skipped++;
      continue;
    }

    if (seenSerials.has(serialNumber)) {
      duplicateSerials++;
      continue;
    }

    const date = parseDate(doc);
    const numbers = extractNumbers(doc);

    if (!date || numbers.size === 0) {
      skipped++;
      continue;
    }

    seenSerials.add(serialNumber);

    draws.push({
      serialNumber,
      recordNumber: doc.recordNumber,
      date,
      numbers,
    });
  }

  draws.sort(compareDraws);

  console.log(`MongoDB documents: ${docs.length}`);
  console.log(`Unique draw events loaded: ${draws.length}`);
  console.log(`Skipped invalid/empty documents: ${skipped}`);
  console.log(`Duplicate serial numbers skipped: ${duplicateSerials}`);

  return draws;
}

// ---------------------------------------------------------
// Score helpers
// ---------------------------------------------------------

function minMaxNormalize(map) {
  const values = [...map.values()];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const normalized = new Map();

  for (const [key, value] of map) {
    normalized.set(key, max === min ? 0 : (value - min) / (max - min));
  }

  return normalized;
}

function deterministicTieBreaker(number, drawIndex) {
  let hash = (Number(number) * 2654435761 + drawIndex * 1013904223) >>> 0;

  hash ^= hash >>> 16;
  hash = Math.imul(hash, 2246822519) >>> 0;
  hash ^= hash >>> 13;

  return hash / 4294967295;
}

function rankNumbers(numbers, scores, drawIndex) {
  return numbers
    .map((number) => ({
      number,
      score: scores.get(number) ?? 0,
      tie: deterministicTieBreaker(number, drawIndex),
    }))
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (b.tie !== a.tie) return b.tie - a.tie;
      return a.number.localeCompare(b.number);
    })
    .map((item) => item.number);
}

function csvEscape(value) {
  const text = String(value ?? "");

  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}

function writeCSV(filePath, rows, columns) {
  const lines = [
    columns.map(csvEscape).join(","),
    ...rows.map((row) =>
      columns.map((column) => csvEscape(row[column])).join(","),
    ),
  ];

  fs.writeFileSync(filePath, lines.join("\n") + "\n", "utf8");
}

// ---------------------------------------------------------
// Walk-forward backtest
// ---------------------------------------------------------

async function runBacktest(draws) {
  const allNumbers = Array.from({ length: TOTAL_NUMBERS }, (_, index) =>
    String(index).padStart(4, "0"),
  );

  // Count how many prior draw events each number appeared in.
  const frequency = new Map(allNumbers.map((n) => [n, 0]));

  // Each queue entry is a Set of numbers from one draw event.
  const recentQueue = [];

  // Counts within the queue, maintained incrementally.
  const recentCounts = new Map(allNumbers.map((n) => [n, 0]));

  const detailRows = [];

  const stats = new Map();

  for (const strategy of STRATEGIES) {
    const row = {
      strategy,
      tests: 0,
      totalTargetNumbers: 0,
    };

    for (const k of TOP_K) {
      row[`hitsTop${k}`] = 0;
    }

    stats.set(strategy, row);
  }

  for (let i = 0; i < draws.length; i++) {
    const targetDraw = draws[i];

    if (i >= MIN_TRAINING_DRAWS) {
      // All 10,000 numbers remain eligible, even if seen before.
      const rawFrequency = new Map(frequency);
      const normalizedFrequency = minMaxNormalize(rawFrequency);

      const recentNormalized = {};

      for (const windowSize of RECENT_WINDOWS) {
        const raw = new Map();

        for (const number of allNumbers) {
          raw.set(number, recentCounts.get(number) || 0);
        }

        recentNormalized[windowSize] = minMaxNormalize(raw);
      }

      const scoreMaps = {
        historical_frequency: normalizedFrequency,
        recent_25: recentNormalized[25],
        recent_50: recentNormalized[50],
        recent_100: recentNormalized[100],
        recent_250: recentNormalized[250],
      };

      for (const windowSize of RECENT_WINDOWS) {
        const combined = new Map();

        for (const number of allNumbers) {
          const f = normalizedFrequency.get(number) || 0;
          const r = recentNormalized[windowSize].get(number) || 0;

          combined.set(number, f + r);
        }

        scoreMaps[`frequency_plus_recent${windowSize}`] = combined;
      }

      const randomScores = new Map();

      for (const number of allNumbers) {
        randomScores.set(number, deterministicTieBreaker(number, i));
      }

      scoreMaps.random_baseline = randomScores;

      const actualNumbers = targetDraw.numbers;

      for (const strategy of STRATEGIES) {
        const ranking = rankNumbers(allNumbers, scoreMaps[strategy], i);

        const result = {
          drawIndex: i,
          serialNumber: targetDraw.serialNumber,
          date: targetDraw.date.toISOString().slice(0, 10),
          strategy,
          actualUniqueNumbers: actualNumbers.size,
        };

        const strategyStats = stats.get(strategy);

        strategyStats.tests++;
        strategyStats.totalTargetNumbers += actualNumbers.size;

        for (const k of TOP_K) {
          const topNumbers = ranking.slice(0, k);
          const hits = topNumbers.filter((number) =>
            actualNumbers.has(number),
          ).length;

          result[`hitsTop${k}`] = hits;
          result[`precisionTop${k}`] = hits / k;

          strategyStats[`hitsTop${k}`] += hits;
        }

        detailRows.push(result);
      }
    }

    // Update historical frequency only AFTER evaluating this draw.
    for (const number of targetDraw.numbers) {
      frequency.set(number, (frequency.get(number) || 0) + 1);
    }

    // Add the current draw to the recent-event window.
    const currentNumbers = [...targetDraw.numbers];
    recentQueue.push(currentNumbers);

    for (const number of currentNumbers) {
      recentCounts.set(number, (recentCounts.get(number) || 0) + 1);
    }

    // Keep enough history for the largest window.
    while (recentQueue.length > Math.max(...RECENT_WINDOWS)) {
      const removedNumbers = recentQueue.shift();

      for (const number of removedNumbers) {
        recentCounts.set(
          number,
          Math.max(0, (recentCounts.get(number) || 0) - 1),
        );
      }
    }

    if ((i + 1) % 250 === 0 || i === draws.length - 1) {
      console.log(`Processed ${i + 1}/${draws.length} draws`);
    }
  }

  const summaryRows = STRATEGIES.map((strategy) => {
    const item = stats.get(strategy);
    const row = {
      strategy,
      tests: item.tests,
      meanActualNumbersPerDraw: item.tests
        ? item.totalTargetNumbers / item.tests
        : 0,
    };

    for (const k of TOP_K) {
      row[`meanHitsTop${k}`] = item.tests
        ? item[`hitsTop${k}`] / item.tests
        : 0;

      row[`precisionTop${k}`] = item.tests
        ? item[`hitsTop${k}`] / (item.tests * k)
        : 0;
    }

    return row;
  });

  const randomRow = summaryRows.find(
    (row) => row.strategy === "random_baseline",
  );

  for (const row of summaryRows) {
    for (const k of TOP_K) {
      const baseline = randomRow[`meanHitsTop${k}`];

      row[`liftTop${k}`] = baseline > 0 ? row[`meanHitsTop${k}`] / baseline : 0;
    }
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  writeCSV(
    path.join(OUTPUT_DIR, "next_draw_backtest_results.csv"),
    detailRows,
    [
      "drawIndex",
      "serialNumber",
      "date",
      "strategy",
      "actualUniqueNumbers",
      ...TOP_K.flatMap((k) => [`hitsTop${k}`, `precisionTop${k}`]),
    ],
  );

  writeCSV(
    path.join(OUTPUT_DIR, "next_draw_backtest_summary.csv"),
    summaryRows,
    [
      "strategy",
      "tests",
      "meanActualNumbersPerDraw",
      ...TOP_K.flatMap((k) => [
        `meanHitsTop${k}`,
        `precisionTop${k}`,
        `liftTop${k}`,
      ]),
    ],
  );

  console.log("\nSUMMARY — ALL NUMBERS IN EACH NEXT DRAW");
  console.table(
    summaryRows
      .slice()
      .sort((a, b) => b.meanHitsTop25 - a.meanHitsTop25)
      .map((row) => ({
        strategy: row.strategy,
        tests: row.tests,
        top10: row.meanHitsTop10.toFixed(4),
        top25: row.meanHitsTop25.toFixed(4),
        top50: row.meanHitsTop50.toFixed(4),
        top100: row.meanHitsTop100.toFixed(4),
        top25Precision: `${(row.precisionTop25 * 100).toFixed(3)}%`,
        top25Lift: row.liftTop25.toFixed(3),
      })),
  );

  console.log(`\nOutput directory: ${OUTPUT_DIR}`);
  console.log("No database records were changed.");
}

// ---------------------------------------------------------
// Main
// ---------------------------------------------------------

async function main() {
  try {
    await mongoose.connect(MONGO_URI);
    console.log("Connected to MongoDB.");

    const draws = await loadDraws();

    if (draws.length <= MIN_TRAINING_DRAWS) {
      throw new Error(
        `Need more than ${MIN_TRAINING_DRAWS} valid draw events; found ${draws.length}.`,
      );
    }

    await runBacktest(draws);
  } catch (error) {
    console.error("\nBacktest failed:", error);
    process.exitCode = 1;
  } finally {
    await mongoose.disconnect().catch(() => {});
  }
}

main();
