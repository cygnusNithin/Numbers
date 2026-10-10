const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const MIN_TRAINING_DRAWS = 300;
const WINDOWS = [25, 50, 100, 250];
const TOP_K_VALUES = [10, 25, 50, 100];

// Equal weighting of long-run and recent appearance rates.
const HISTORICAL_WEIGHT = 0.5;
const RECENT_WEIGHT = 0.5;

const OUTPUT_DIR = path.join(
  __dirname,
  "..",
  "analysis-results",
  "next-draw-strategy-backtest-v2",
);

function parseDate(doc) {
  if (doc.drawDate && !Number.isNaN(new Date(doc.drawDate).getTime())) {
    return new Date(doc.drawDate);
  }

  const match = String(doc.date || "").match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);

  if (!match) return null;

  return new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
}

function getNumbers(doc) {
  const numbers = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      if (item.number === undefined || item.number === null) continue;

      const value = String(item.number).trim();
      if (!/^\d{1,4}$/.test(value)) continue;

      numbers.add(value.padStart(4, "0"));
    }
  }

  return numbers;
}

function stableHash(text) {
  let hash = 2166136261;

  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  return hash >>> 0;
}

function randomScore(targetIndex, number) {
  // Deterministic pseudo-random score; no future results are used.
  return stableHash(`${targetIndex}:${number}`) / 4294967296;
}

function rankScores(scoreMap, frequencyMap, recentMap, targetIndex) {
  const ranked = [];

  for (let i = 0; i < 10000; i++) {
    const number = String(i).padStart(4, "0");

    ranked.push({
      number,
      score: scoreMap.get(number) || 0,
      historicalCount: frequencyMap.get(number) || 0,
      recentCount: recentMap ? recentMap.get(number) || 0 : 0,
      random: randomScore(targetIndex, number),
    });
  }

  ranked.sort(
    (a, b) =>
      b.score - a.score ||
      b.historicalCount - a.historicalCount ||
      b.recentCount - a.recentCount ||
      a.number.localeCompare(b.number),
  );

  return ranked;
}

function makeCountMap() {
  return new Map();
}

function incrementMap(map, number) {
  map.set(number, (map.get(number) || 0) + 1);
}

function topKHits(ranking, winningNumbers, k) {
  let hits = 0;

  for (let i = 0; i < Math.min(k, ranking.length); i++) {
    if (winningNumbers.has(ranking[i].number)) hits++;
  }

  return hits;
}

function topKOverlap(a, b, k) {
  const bSet = new Set(b.slice(0, k).map((x) => x.number));
  return a.slice(0, k).filter((x) => bSet.has(x.number)).length;
}

function writeCsv(filePath, rows) {
  if (!rows.length) {
    fs.writeFileSync(filePath, "", "utf8");
    return;
  }

  const headers = Object.keys(rows[0]);

  const escape = (value) => {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };

  const lines = [
    headers.map(escape).join(","),
    ...rows.map((row) => headers.map((key) => escape(row[key])).join(",")),
  ];

  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

async function main() {
  await mongoose.connect(MONGO_URI);
  console.log("Connected to MongoDB.");

  try {
    const docs = await AbsoluteData.find({}).lean();
    console.log("MongoDB documents:", docs.length);

    const unique = new Map();
    let skipped = 0;
    let duplicateSerials = 0;

    for (const doc of docs) {
      if (!doc.serialNumber) {
        skipped++;
        continue;
      }

      const serialNumber = String(doc.serialNumber);
      if (unique.has(serialNumber)) {
        duplicateSerials++;
        continue;
      }

      const date = parseDate(doc);
      const numbers = getNumbers(doc);

      if (!date || numbers.size === 0) {
        skipped++;
        continue;
      }

      unique.set(serialNumber, {
        serialNumber,
        recordNumber: Number(doc.recordNumber) || 0,
        date,
        numbers,
      });
    }

    const draws = [...unique.values()].sort(
      (a, b) =>
        a.date - b.date ||
        a.recordNumber - b.recordNumber ||
        a.serialNumber.localeCompare(b.serialNumber),
    );

    console.log("Unique draw events loaded:", draws.length);
    console.log("Skipped invalid/empty documents:", skipped);
    console.log("Duplicate serial numbers skipped:", duplicateSerials);

    if (draws.length <= MIN_TRAINING_DRAWS) {
      throw new Error(
        `Need more than ${MIN_TRAINING_DRAWS} valid draw events.`,
      );
    }

    const frequency = makeCountMap();
    const history = [];

    const strategyNames = [
      "historical_frequency",
      ...WINDOWS.map((w) => `recent_${w}`),
      ...WINDOWS.map((w) => `frequency_plus_recent${w}`),
      "random_baseline",
    ];

    const totals = new Map();
    for (const strategy of strategyNames) {
      const metrics = {};
      for (const k of TOP_K_VALUES) metrics[`top${k}`] = 0;
      totals.set(strategy, {
        tests: 0,
        ...metrics,
      });
    }

    const rankingDifferences = [];
    const perTargetRows = [];

    for (
      let targetIndex = MIN_TRAINING_DRAWS;
      targetIndex < draws.length;
      targetIndex++
    ) {
      const target = draws[targetIndex];
      const priorDrawCount = targetIndex;

      const recentCountsByWindow = new Map();
      const recentRatesByWindow = new Map();
      const rankings = new Map();

      for (const windowSize of WINDOWS) {
        const recentCounts = makeCountMap();
        const start = Math.max(0, targetIndex - windowSize);
        const actualWindowSize = targetIndex - start;

        for (let i = start; i < targetIndex; i++) {
          for (const number of draws[i].numbers) {
            incrementMap(recentCounts, number);
          }
        }

        const recentRates = makeCountMap();
        for (let i = 0; i < 10000; i++) {
          const number = String(i).padStart(4, "0");
          recentRates.set(
            number,
            (recentCounts.get(number) || 0) / actualWindowSize,
          );
        }

        recentCountsByWindow.set(windowSize, recentCounts);
        recentRatesByWindow.set(windowSize, recentRates);

        rankings.set(
          `recent_${windowSize}`,
          rankScores(recentRates, frequency, recentCounts, targetIndex),
        );

        const combined = makeCountMap();
        for (let i = 0; i < 10000; i++) {
          const number = String(i).padStart(4, "0");
          const historicalRate = (frequency.get(number) || 0) / priorDrawCount;
          const recentRate = recentRates.get(number) || 0;

          combined.set(
            number,
            HISTORICAL_WEIGHT * historicalRate + RECENT_WEIGHT * recentRate,
          );
        }

        rankings.set(
          `frequency_plus_recent${windowSize}`,
          rankScores(combined, frequency, recentCounts, targetIndex),
        );
      }

      const historicalRates = makeCountMap();
      for (let i = 0; i < 10000; i++) {
        const number = String(i).padStart(4, "0");
        historicalRates.set(
          number,
          (frequency.get(number) || 0) / priorDrawCount,
        );
      }

      rankings.set(
        "historical_frequency",
        rankScores(historicalRates, frequency, null, targetIndex),
      );

      // Use a seeded deterministic ordering for a reproducible random baseline.
      const randomRanking = Array.from({ length: 10000 }, (_, i) => {
        const number = String(i).padStart(4, "0");
        return {
          number,
          score: randomScore(targetIndex, number),
          historicalCount: frequency.get(number) || 0,
          recentCount: 0,
        };
      }).sort((a, b) => b.score - a.score || a.number.localeCompare(b.number));

      rankings.set("random_baseline", randomRanking);

      const winners = target.numbers;

      for (const strategy of strategyNames) {
        const ranking = rankings.get(strategy);
        const metric = totals.get(strategy);

        for (const k of TOP_K_VALUES) {
          metric[`top${k}`] += topKHits(ranking, winners, k);
        }

        metric.tests++;
      }

      const row = {
        targetIndex,
        serialNumber: target.serialNumber,
        date: target.date.toISOString().slice(0, 10),
        winningNumberCount: winners.size,
      };

      for (const strategy of strategyNames) {
        for (const k of TOP_K_VALUES) {
          row[`${strategy}_top${k}`] = topKHits(
            rankings.get(strategy),
            winners,
            k,
          );
        }
      }

      perTargetRows.push(row);

      rankingDifferences.push({
        targetIndex,
        date: target.date.toISOString().slice(0, 10),
        overlap_recent_25_vs_50: topKOverlap(
          rankings.get("recent_25"),
          rankings.get("recent_50"),
          25,
        ),
        overlap_recent_25_vs_100: topKOverlap(
          rankings.get("recent_25"),
          rankings.get("recent_100"),
          25,
        ),
        overlap_recent_25_vs_250: topKOverlap(
          rankings.get("recent_25"),
          rankings.get("recent_250"),
          25,
        ),
        overlap_combo_25_vs_50: topKOverlap(
          rankings.get("frequency_plus_recent25"),
          rankings.get("frequency_plus_recent50"),
          25,
        ),
        overlap_combo_25_vs_100: topKOverlap(
          rankings.get("frequency_plus_recent25"),
          rankings.get("frequency_plus_recent100"),
          25,
        ),
        overlap_combo_25_vs_250: topKOverlap(
          rankings.get("frequency_plus_recent25"),
          rankings.get("frequency_plus_recent250"),
          25,
        ),
      });

      // Update history only AFTER predicting the current target draw.
      history.push(winners);
      for (const number of winners) incrementMap(frequency, number);

      if ((targetIndex + 1) % 250 === 0 || targetIndex === draws.length - 1) {
        console.log(`Processed ${targetIndex + 1}/${draws.length} draws`);
      }
    }

    const summary = [...totals.entries()]
      .map(([strategy, metric]) => {
        const tests = metric.tests;
        const result = {
          strategy,
          tests,
        };

        for (const k of TOP_K_VALUES) {
          const meanHits = metric[`top${k}`] / tests;
          result[`top${k}`] = meanHits.toFixed(4);
        }

        result.top25Precision =
          ((metric.top25 / (25 * tests)) * 100).toFixed(3) + "%";

        const random = totals.get("random_baseline");
        const randomMeanTop25 = random.top25 / random.tests;
        const thisMeanTop25 = metric.top25 / tests;

        result.top25Lift =
          strategy === "random_baseline"
            ? "1.000"
            : (thisMeanTop25 / randomMeanTop25).toFixed(3);

        return result;
      })
      .sort((a, b) => Number(b.top25) - Number(a.top25));

    fs.mkdirSync(OUTPUT_DIR, { recursive: true });

    writeCsv(path.join(OUTPUT_DIR, "next_draw_v2_summary.csv"), summary);

    writeCsv(
      path.join(OUTPUT_DIR, "next_draw_v2_per_target.csv"),
      perTargetRows,
    );

    writeCsv(
      path.join(OUTPUT_DIR, "next_draw_v2_ranking_overlap.csv"),
      rankingDifferences,
    );

    console.log("\nSUMMARY — NORMALIZED NEXT-DRAW STRATEGIES");
    console.table(summary);

    console.log("\nRecent-window Top-25 overlap averages:");
    for (const key of [
      "overlap_recent_25_vs_50",
      "overlap_recent_25_vs_100",
      "overlap_recent_25_vs_250",
      "overlap_combo_25_vs_50",
      "overlap_combo_25_vs_100",
      "overlap_combo_25_vs_250",
    ]) {
      const average =
        rankingDifferences.reduce((sum, row) => sum + row[key], 0) /
        rankingDifferences.length;

      console.log(`${key}: ${average.toFixed(2)} / 25`);
    }

    console.log("\nOutput directory:", OUTPUT_DIR);
    console.log("No database records were changed.");
  } finally {
    await mongoose.disconnect();
    console.log("Disconnected from MongoDB.");
  }
}

main().catch((error) => {
  console.error("Backtest failed:", error);
  process.exitCode = 1;
});
