/**
 * backtestCycleFeatures.js
 *
 * Purpose:
 *   Test whether cycle-position features improve predictions of
 *   numbers appearing for the FIRST TIME in the current cycle.
 *
 * Strategies:
 *   1. historical_frequency
 *   2. cycle_position
 *   3. frequency_plus_cycle
 *   4. frequency_plus_recent100
 *   5. frequency_plus_cycle_plus_recent
 *   6. random_baseline
 *
 * Safety:
 *   - Reads AbsoluteData only; never writes to MongoDB.
 *   - Keeps separate draw events separate, including same-date draws.
 *   - Scores a target before updating features with that target.
 *   - Uses only completed cycles for historical cycle-position features.
 *   - Estimates current cycle progress from previously completed cycles.
 *
 * Run:
 *   node .\scripts\backtestCycleFeatures.js
 */

const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const TOTAL_NUMBERS = 10000;
const MIN_TRAINING_DRAWS = 300;
const RECENT_WINDOW = 100;
const TOP_K = [10, 25, 50, 100];

const OUTPUT_DIR = path.join(
  __dirname,
  "../analysis-results/cycle-feature-backtest",
);

// ---------------------------------------------------------
// Dates and draw extraction
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

      if (!Number.isNaN(d.getTime())) {
        return d;
      }
    }
  }

  return null;
}

function extractNumbers(doc) {
  const numbers = new Set();

  if (!Array.isArray(doc.series)) {
    return numbers;
  }

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

  if (Number.isFinite(recordA) && Number.isFinite(recordB)) {
    if (recordA !== recordB) return recordA - recordB;
  }

  return String(a.serialNumber || "").localeCompare(
    String(b.serialNumber || ""),
  );
}

async function loadDraws() {
  const docs = await AbsoluteData.find({}).lean();

  const draws = [];
  const serialNumbers = new Set();
  let skipped = 0;
  let duplicateSerials = 0;

  for (const doc of docs) {
    const serial = String(doc.serialNumber || "").trim();

    if (!serial) {
      skipped++;
      continue;
    }

    if (serialNumbers.has(serial)) {
      duplicateSerials++;
      continue;
    }

    const date = parseDate(doc);
    const numbers = extractNumbers(doc);

    if (!date || numbers.size === 0) {
      skipped++;
      continue;
    }

    serialNumbers.add(serial);

    draws.push({
      serialNumber: serial,
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
// Scoring helpers
// ---------------------------------------------------------

function minMaxNormalize(values) {
  const nums = Array.from(values.values());

  if (nums.length === 0) return new Map();

  const min = Math.min(...nums);
  const max = Math.max(...nums);

  const result = new Map();

  for (const [key, value] of values) {
    result.set(key, max === min ? 0 : (value - min) / (max - min));
  }

  return result;
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function deterministicRandomScore(number, drawIndex) {
  // Stable hash-like score: no Math.random(), so reruns are reproducible.
  let hash = (Number(number) * 2654435761 + drawIndex * 1013904223) >>> 0;
  hash ^= hash >>> 16;
  hash = Math.imul(hash, 2246822519) >>> 0;
  hash ^= hash >>> 13;

  return hash / 4294967295;
}

function rankNumbers(candidates, scores) {
  return candidates
    .map((number) => ({
      number,
      score: scores.get(number) ?? 0,
    }))
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.number.localeCompare(b.number);
    })
    .map((item) => item.number);
}

// ---------------------------------------------------------
// CSV output
// ---------------------------------------------------------

function csvEscape(value) {
  const str = String(value ?? "");

  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }

  return str;
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
// Backtest
// ---------------------------------------------------------

async function runBacktest(draws) {
  const allNumbers = Array.from({ length: TOTAL_NUMBERS }, (_, index) =>
    String(index).padStart(4, "0"),
  );

  // Global historical occurrence counts.
  const historicalHits = new Map(allNumbers.map((n) => [n, 0]));

  // Most recent draw appearances, for recent-window counts.
  const recentQueue = [];
  const recentHits = new Map(allNumbers.map((n) => [n, 0]));

  // Numbers first seen in the current cycle.
  let currentCycleSeen = new Set();
  let currentCycleFirstIndex = new Map();
  let currentCycleDrawCount = 0;

  // Only completed cycles enter these histories.
  const completedCycleLengths = [];
  const historicalFirstPositions = new Map(allNumbers.map((n) => [n, []]));

  const detailedRows = [];
  const summaryStats = new Map();

  const strategies = [
    "historical_frequency",
    "cycle_position",
    "frequency_plus_cycle",
    "frequency_plus_recent100",
    "frequency_plus_cycle_plus_recent",
    "random_baseline",
  ];

  for (const strategy of strategies) {
    const stats = {
      strategy,
      tests: 0,
      candidateCountTotal: 0,
      targetHits: 0,
    };

    for (const k of TOP_K) {
      stats[`top${k}Hits`] = 0;
      stats[`top${k}Available`] = 0;
    }

    summaryStats.set(strategy, stats);
  }

  for (let i = 0; i < draws.length; i++) {
    const draw = draws[i];

    // Evaluate only after a reasonable initial history is available.
    if (i >= MIN_TRAINING_DRAWS && currentCycleSeen.size < TOTAL_NUMBERS) {
      const candidates = allNumbers.filter(
        (number) => !currentCycleSeen.has(number),
      );

      const targets = new Set(
        [...draw.numbers].filter((number) => !currentCycleSeen.has(number)),
      );

      // Historical average cycle length is estimated only from
      // completed cycles available before the current target draw.
      const estimatedCycleLength = completedCycleLengths.length
        ? average(completedCycleLengths)
        : null;

      const currentProgress = estimatedCycleLength
        ? currentCycleDrawCount / estimatedCycleLength
        : null;

      const rawFrequency = new Map();
      const rawRecent = new Map();
      const rawCyclePosition = new Map();

      for (const number of candidates) {
        rawFrequency.set(number, historicalHits.get(number) || 0);
        rawRecent.set(number, recentHits.get(number) || 0);

        const positions = historicalFirstPositions.get(number) || [];

        if (currentProgress !== null && positions.length > 0) {
          const meanFirstPosition = average(positions);

          // Higher scores when a number's historical first-appearance
          // timing is close to the current estimated cycle progress.
          rawCyclePosition.set(
            number,
            1 / (1 + Math.abs(meanFirstPosition - currentProgress)),
          );
        } else {
          rawCyclePosition.set(number, 0);
        }
      }

      const frequency = minMaxNormalize(rawFrequency);
      const recent = minMaxNormalize(rawRecent);
      const cyclePosition = minMaxNormalize(rawCyclePosition);

      const scoresByStrategy = {
        historical_frequency: new Map(),
        cycle_position: new Map(),
        frequency_plus_cycle: new Map(),
        frequency_plus_recent100: new Map(),
        frequency_plus_cycle_plus_recent: new Map(),
        random_baseline: new Map(),
      };

      for (const number of candidates) {
        const f = frequency.get(number) || 0;
        const c = cyclePosition.get(number) || 0;
        const r = recent.get(number) || 0;

        scoresByStrategy.historical_frequency.set(number, f);
        scoresByStrategy.cycle_position.set(number, c);
        scoresByStrategy.frequency_plus_cycle.set(number, f + c);
        scoresByStrategy.frequency_plus_recent100.set(number, f + r);
        scoresByStrategy.frequency_plus_cycle_plus_recent.set(
          number,
          f + c + r,
        );
        scoresByStrategy.random_baseline.set(
          number,
          deterministicRandomScore(number, i),
        );
      }

      for (const strategy of strategies) {
        const ranking = rankNumbers(candidates, scoresByStrategy[strategy]);

        const stats = summaryStats.get(strategy);
        stats.tests++;
        stats.candidateCountTotal += candidates.length;
        stats.targetHits += targets.size;

        const row = {
          targetDrawIndex: i,
          targetSerialNumber: draw.serialNumber,
          targetDate: draw.date.toISOString().slice(0, 10),
          strategy,
          currentCycleDrawsBeforeTarget: currentCycleDrawCount,
          currentCycleSeenBeforeTarget: currentCycleSeen.size,
          completedCyclesBeforeTarget: completedCycleLengths.length,
          estimatedCycleLength: estimatedCycleLength ?? "",
          estimatedCycleProgress: currentProgress ?? "",
          candidateCount: candidates.length,
          targetFirstAppearances: targets.size,
        };

        for (const k of TOP_K) {
          const topNumbers = ranking.slice(0, k);
          const availableK = topNumbers.length;
          const hits = topNumbers.filter((n) => targets.has(n)).length;

          stats[`top${k}Hits`] += hits;
          stats[`top${k}Available`] += availableK;

          row[`top${k}Hits`] = hits;
          row[`top${k}Available`] = availableK;
          row[`top${k}HitRate`] = availableK ? hits / availableK : 0;
        }

        detailedRows.push(row);
      }
    }

    // Update state only AFTER scoring this draw.
    //
    // First, record each number's first position in this cycle.
    for (const number of draw.numbers) {
      if (!currentCycleSeen.has(number)) {
        currentCycleSeen.add(number);
        currentCycleFirstIndex.set(number, currentCycleDrawCount);
      }

      historicalHits.set(number, (historicalHits.get(number) || 0) + 1);
    }

    // Update recent draw window. Each event contributes at most one
    // recent hit per number because draw.numbers is a Set.
    const eventNumbers = [...draw.numbers];
    recentQueue.push(eventNumbers);

    for (const number of eventNumbers) {
      recentHits.set(number, (recentHits.get(number) || 0) + 1);
    }

    while (recentQueue.length > RECENT_WINDOW) {
      const removed = recentQueue.shift();

      for (const number of removed) {
        recentHits.set(number, Math.max(0, (recentHits.get(number) || 0) - 1));
      }
    }

    currentCycleDrawCount++;

    // A cycle becomes known to be complete only when all 10,000
    // numbers have appeared. Its history is then available to future
    // draws, never to predictions made earlier in that cycle.
    if (currentCycleSeen.size === TOTAL_NUMBERS) {
      const completedLength = currentCycleDrawCount;

      completedCycleLengths.push(completedLength);

      for (const [number, firstIndex] of currentCycleFirstIndex) {
        const position =
          completedLength <= 1 ? 0 : firstIndex / (completedLength - 1);

        historicalFirstPositions.get(number).push(position);
      }

      console.log(
        `Completed cycle ${completedCycleLengths.length}: ` +
          `${completedLength} draw events; ` +
          `${draw.date.toISOString().slice(0, 10)}`,
      );

      currentCycleSeen = new Set();
      currentCycleFirstIndex = new Map();
      currentCycleDrawCount = 0;
    }

    if ((i + 1) % 250 === 0 || i === draws.length - 1) {
      console.log(`Processed ${i + 1}/${draws.length} draw events`);
    }
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const summaryRows = strategies.map((strategy) => {
    const stats = summaryStats.get(strategy);
    const row = {
      strategy,
      tests: stats.tests,
      meanCandidateCount: stats.tests
        ? stats.candidateCountTotal / stats.tests
        : 0,
      meanTargetFirstAppearances: stats.tests
        ? stats.targetHits / stats.tests
        : 0,
    };

    for (const k of TOP_K) {
      row[`meanTop${k}Hits`] = stats.tests
        ? stats[`top${k}Hits`] / stats.tests
        : 0;

      row[`top${k}Precision`] = stats[`top${k}Available`]
        ? stats[`top${k}Hits`] / stats[`top${k}Available`]
        : 0;
    }

    return row;
  });

  const detailColumns = [
    "targetDrawIndex",
    "targetSerialNumber",
    "targetDate",
    "strategy",
    "currentCycleDrawsBeforeTarget",
    "currentCycleSeenBeforeTarget",
    "completedCyclesBeforeTarget",
    "estimatedCycleLength",
    "estimatedCycleProgress",
    "candidateCount",
    "targetFirstAppearances",
    ...TOP_K.flatMap((k) => [
      `top${k}Hits`,
      `top${k}Available`,
      `top${k}HitRate`,
    ]),
  ];

  const summaryColumns = [
    "strategy",
    "tests",
    "meanCandidateCount",
    "meanTargetFirstAppearances",
    ...TOP_K.flatMap((k) => [`meanTop${k}Hits`, `top${k}Precision`]),
  ];

  writeCSV(
    path.join(OUTPUT_DIR, "cycle_feature_backtest_results.csv"),
    detailedRows,
    detailColumns,
  );

  writeCSV(
    path.join(OUTPUT_DIR, "cycle_feature_backtest_summary.csv"),
    summaryRows,
    summaryColumns,
  );

  console.log("\nSUMMARY");
  console.table(
    summaryRows.map((row) => ({
      strategy: row.strategy,
      tests: row.tests,
      top10: Number(row.meanTop10Hits).toFixed(4),
      top25: Number(row.meanTop25Hits).toFixed(4),
      top50: Number(row.meanTop50Hits).toFixed(4),
      top100: Number(row.meanTop100Hits).toFixed(4),
      top25Precision: `${(row.top25Precision * 100).toFixed(3)}%`,
    })),
  );

  console.log(`\nResults saved to:\n${OUTPUT_DIR}`);
  console.log(
    "\nIMPORTANT: This evaluates first appearances within a coverage-defined " +
      "cycle, not the probability of any number appearing in an ordinary draw.",
  );
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
