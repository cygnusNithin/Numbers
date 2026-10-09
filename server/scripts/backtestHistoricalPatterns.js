const fs = require("fs");
const path = require("path");

const BASE_DIR = path.join(
  __dirname,
  "..",
  "analysis-results",
  "historical-patterns",
);

const DRAW_FILE = path.join(BASE_DIR, "draw_sequence.json");

const DETAIL_FILE = path.join(BASE_DIR, "number_historical_details.json");

const OUTPUT_DIR = path.join(
  __dirname,
  "..",
  "analysis-results",
  "pattern-backtest",
);

const NUMBERS = Array.from({ length: 10000 }, (_, i) =>
  String(i).padStart(4, "0"),
);

const TOP_K_VALUES = [10, 25, 50, 100];

const MIN_TRAIN_DRAWS = 300;

const RECENT_WINDOWS = [25, 50, 100, 250];

function ensureDir() {
  fs.mkdirSync(OUTPUT_DIR, {
    recursive: true,
  });
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function mean(values) {
  if (!values.length) return 0;

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values) {
  if (!values.length) return 0;

  const sorted = [...values].sort((a, b) => a - b);

  const middle = Math.floor(sorted.length / 2);

  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  return sorted[middle];
}

function standardDeviation(values) {
  if (values.length <= 1) return 0;

  const avg = mean(values);

  return Math.sqrt(mean(values.map((value) => Math.pow(value - avg, 2))));
}

function rankNumbers(scores) {
  return [...scores.entries()]
    .sort((a, b) => {
      if (b[1] !== a[1]) {
        return b[1] - a[1];
      }

      return a[0].localeCompare(a[0]);
    })
    .map(([number]) => number);
}

function topKHits(ranking, actualNumbers, k) {
  const actual = new Set(actualNumbers);

  const selected = ranking.slice(0, k);

  return selected.filter((number) => actual.has(number)).length;
}

function precision(hits, k) {
  return hits / k;
}

function recall(hits, actualCount) {
  if (!actualCount) return 0;

  return hits / actualCount;
}

function percentileRank(ranking, actualNumbers) {
  const positions = new Map();

  ranking.forEach((number, index) => {
    positions.set(number, index + 1);
  });

  const ranks = actualNumbers
    .map((number) => positions.get(number))
    .filter((rank) => Number.isFinite(rank));

  if (!ranks.length) return null;

  return mean(ranks.map((rank) => 1 - (rank - 1) / (ranking.length - 1)));
}

function getDrawNumbers(draw) {
  return [
    ...new Set(
      (draw.numbers || [])
        .map((item) => String(item.number))
        .filter((number) => /^\d{4}$/.test(number)),
    ),
  ];
}

function buildState(draws) {
  const state = new Map();

  for (const number of NUMBERS) {
    state.set(number, {
      hits: 0,
      recentHits: new Map(),
      lastDrawIndex: null,
      appearanceDraws: [],
      monthCounts: {},
      weekdayCounts: {},
    });
  }

  for (let drawIndex = 0; drawIndex < draws.length; drawIndex++) {
    const draw = draws[drawIndex];

    const dateParts = String(draw.drawDate).split("/");

    let month = null;
    let weekday = null;

    if (dateParts.length === 3) {
      const day = Number(dateParts[0]);

      const monthNumber = Number(dateParts[1]);

      const year = Number(dateParts[2]);

      const date = new Date(year, monthNumber - 1, day);

      month = monthNumber;

      weekday = date.getDay();
    }

    const numbers = getDrawNumbers(draw);

    for (const number of numbers) {
      const item = state.get(number);

      item.hits++;

      item.lastDrawIndex = drawIndex;

      item.appearanceDraws.push(drawIndex);

      if (month !== null) {
        item.monthCounts[month] = (item.monthCounts[month] || 0) + 1;
      }

      if (weekday !== null) {
        item.weekdayCounts[weekday] = (item.weekdayCounts[weekday] || 0) + 1;
      }
    }

    for (const number of NUMBERS) {
      // We intentionally do not copy complete
      // history into every number here.
      // Recent windows are calculated from
      // appearanceDraws when scoring.
    }
  }

  return state;
}

function countRecentHits(appearanceDraws, currentDrawIndex, window) {
  const start = Math.max(0, currentDrawIndex - window);

  let count = 0;

  for (let i = appearanceDraws.length - 1; i >= 0; i--) {
    const drawIndex = appearanceDraws[i];

    if (drawIndex < start) {
      break;
    }

    if (drawIndex < currentDrawIndex) {
      count++;
    }
  }

  return count;
}

function getGapDraws(state, currentDrawIndex) {
  if (state.lastDrawIndex === null) {
    return currentDrawIndex + 1;
  }

  return currentDrawIndex - state.lastDrawIndex;
}

function calculateGapScore(state, currentDrawIndex) {
  const currentGap = getGapDraws(state, currentDrawIndex);

  if (state.appearanceDraws.length < 2) {
    return 0;
  }

  const gaps = [];

  for (let i = 1; i < state.appearanceDraws.length; i++) {
    gaps.push(state.appearanceDraws[i] - state.appearanceDraws[i - 1]);
  }

  const med = median(gaps);

  const avg = mean(gaps);

  if (!med || !avg) {
    return 0;
  }

  /*
   * This is deliberately NOT "higher gap =
   * higher score".
   *
   * We measure how close the current gap is
   * to the number's historical typical gap.
   *
   * Later we can test other hazard functions.
   */

  const ratio = currentGap / med;

  const distance = Math.abs(Math.log(Math.max(ratio, 0.0001)));

  return 1 / (1 + distance);
}

function calculateOverdueScore(state, currentDrawIndex) {
  if (state.appearanceDraws.length < 2) {
    return 0;
  }

  const gaps = [];

  for (let i = 1; i < state.appearanceDraws.length; i++) {
    gaps.push(state.appearanceDraws[i] - state.appearanceDraws[i - 1]);
  }

  const avg = mean(gaps);

  if (!avg) return 0;

  const currentGap = getGapDraws(state, currentDrawIndex);

  /*
   * Ratio above 1 means the number is
   * currently beyond its historical average.
   */

  return currentGap / avg;
}

function calculateMonthScore(state, targetMonth) {
  const total = Object.values(state.monthCounts).reduce(
    (sum, value) => sum + value,
    0,
  );

  if (!total) return 0;

  return (state.monthCounts[targetMonth] || 0) / total;
}

function calculateWeekdayScore(state, targetWeekday) {
  const total = Object.values(state.weekdayCounts).reduce(
    (sum, value) => sum + value,
    0,
  );

  if (!total) return 0;

  return (state.weekdayCounts[targetWeekday] || 0) / total;
}

function calculateRecentRate(state, currentDrawIndex, window) {
  const hits = countRecentHits(state.appearanceDraws, currentDrawIndex, window);

  return hits / window;
}

function randomRanking(seed) {
  /*
   * Deterministic pseudo-random ranking.
   * We use a seed so the baseline is reproducible.
   */

  let value = seed >>> 0;

  const scores = new Map();

  for (const number of NUMBERS) {
    value = (value * 1664525 + 1013904223) >>> 0;

    scores.set(number, value);
  }

  return rankNumbers(scores);
}

function normalizeScores(scoreMap) {
  const values = [...scoreMap.values()].filter(Number.isFinite);

  if (!values.length) {
    return new Map();
  }

  const min = Math.min(...values);

  const max = Math.max(...values);

  const result = new Map();

  for (const [number, value] of scoreMap.entries()) {
    if (max === min) {
      result.set(number, 0);
    } else {
      result.set(number, (value - min) / (max - min));
    }
  }

  return result;
}

function combineScores(scoreMaps) {
  const normalized = scoreMaps.map((map) => normalizeScores(map));

  const combined = new Map();

  for (const number of NUMBERS) {
    let total = 0;

    for (const map of normalized) {
      total += map.get(number) || 0;
    }

    combined.set(number, total);
  }

  return combined;
}

function evaluateStrategy(strategyName, ranking, actualNumbers) {
  const row = {
    strategy: strategyName,

    actual_count: actualNumbers.length,

    top10_hits: topKHits(ranking, actualNumbers, 10),

    top25_hits: topKHits(ranking, actualNumbers, 25),

    top50_hits: topKHits(ranking, actualNumbers, 50),

    top100_hits: topKHits(ranking, actualNumbers, 100),

    rank_score: percentileRank(ranking, actualNumbers),
  };

  row.top10_precision = precision(row.top10_hits, 10);

  row.top25_precision = precision(row.top25_hits, 25);

  row.top50_precision = precision(row.top50_hits, 50);

  row.top100_precision = precision(row.top100_hits, 100);

  row.recall_top100 = recall(row.top100_hits, actualNumbers.length);

  return row;
}

function aggregateResults(rows) {
  const grouped = new Map();

  for (const row of rows) {
    if (!grouped.has(row.strategy)) {
      grouped.set(row.strategy, []);
    }

    grouped.get(row.strategy).push(row);
  }

  const summary = [];

  for (const [strategy, strategyRows] of grouped.entries()) {
    summary.push({
      strategy,

      tests: strategyRows.length,

      mean_top10_hits: mean(strategyRows.map((row) => row.top10_hits)),

      mean_top25_hits: mean(strategyRows.map((row) => row.top25_hits)),

      mean_top50_hits: mean(strategyRows.map((row) => row.top50_hits)),

      mean_top100_hits: mean(strategyRows.map((row) => row.top100_hits)),

      mean_top10_precision: mean(
        strategyRows.map((row) => row.top10_precision),
      ),

      mean_top25_precision: mean(
        strategyRows.map((row) => row.top25_precision),
      ),

      mean_top50_precision: mean(
        strategyRows.map((row) => row.top50_precision),
      ),

      mean_top100_precision: mean(
        strategyRows.map((row) => row.top100_precision),
      ),

      mean_recall_top100: mean(strategyRows.map((row) => row.recall_top100)),

      mean_rank_score: mean(strategyRows.map((row) => row.rank_score)),

      std_top25_hits: standardDeviation(
        strategyRows.map((row) => row.top25_hits),
      ),
    });
  }

  return summary;
}

function writeCsv(fileName, rows) {
  if (!rows.length) return;

  const filePath = path.join(OUTPUT_DIR, fileName);

  const columns = Object.keys(rows[0]);

  const lines = [columns.join(",")];

  for (const row of rows) {
    lines.push(
      columns
        .map((column) => {
          const value = row[column];

          if (typeof value === "string") {
            return `"${value.replace(/"/g, '""')}"`;
          }

          return value ?? "";
        })
        .join(","),
    );
  }

  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

function main() {
  ensureDir();

  console.log("");
  console.log("============================================================");
  console.log("HISTORICAL PATTERN BACKTEST");
  console.log("============================================================");

  const draws = readJson(DRAW_FILE);

  console.log(`Draw events loaded: ${draws.length}`);

  /*
   * Build state incrementally.
   *
   * IMPORTANT:
   * We DO NOT build the state using all draws
   * before testing. That would leak future information.
   */

  const state = new Map();

  for (const number of NUMBERS) {
    state.set(number, {
      hits: 0,
      lastDrawIndex: null,
      appearanceDraws: [],
      monthCounts: {},
      weekdayCounts: {},
    });
  }

  const detailedResults = [];

  /*
   * Start sufficiently far into history
   * so that the patterns have some data.
   *
   * We test every draw after MIN_TRAIN_DRAWS.
   */

  for (
    let targetIndex = MIN_TRAIN_DRAWS;
    targetIndex < draws.length;
    targetIndex++
  ) {
    const targetDraw = draws[targetIndex];

    const actualNumbers = getDrawNumbers(targetDraw);

    if (!actualNumbers.length) {
      continue;
    }

    /*
     * Target date is known because we're
     * evaluating a historical draw.
     */

    const parts = String(targetDraw.drawDate).split("/");

    const targetDay = Number(parts[0]);

    const targetMonth = Number(parts[1]);

    const targetYear = Number(parts[2]);

    const targetDate = new Date(targetYear, targetMonth - 1, targetDay);

    const targetWeekday = targetDate.getDay();

    /*
     * --------------------------------------------------------
     * STRATEGY 1: Historical frequency
     * --------------------------------------------------------
     */

    const frequencyScores = new Map();

    /*
     * --------------------------------------------------------
     * STRATEGY 2: Recent frequency
     * --------------------------------------------------------
     */

    const recentScores = new Map();

    /*
     * --------------------------------------------------------
     * STRATEGY 3: Gap closeness
     * --------------------------------------------------------
     */

    const gapScores = new Map();

    /*
     * --------------------------------------------------------
     * STRATEGY 4: Overdue ratio
     * --------------------------------------------------------
     */

    const overdueScores = new Map();

    /*
     * --------------------------------------------------------
     * STRATEGY 5: Month probability
     * --------------------------------------------------------
     */

    const monthScores = new Map();

    /*
     * --------------------------------------------------------
     * STRATEGY 6: Weekday probability
     * --------------------------------------------------------
     */

    const weekdayScores = new Map();

    /*
     * Recent windows
     */

    const recentScoreMaps = {};

    for (const window of RECENT_WINDOWS) {
      recentScoreMaps[window] = new Map();
    }

    for (const number of NUMBERS) {
      const item = state.get(number);

      frequencyScores.set(number, item.hits);

      monthScores.set(number, calculateMonthScore(item, targetMonth));

      weekdayScores.set(number, calculateWeekdayScore(item, targetWeekday));

      gapScores.set(number, calculateGapScore(item, targetIndex));

      overdueScores.set(number, calculateOverdueScore(item, targetIndex));

      for (const window of RECENT_WINDOWS) {
        recentScoreMaps[window].set(
          number,
          calculateRecentRate(item, targetIndex, window),
        );
      }
    }

    /*
     * Evaluate individual strategies.
     */

    const rankings = [];

    rankings.push({
      name: "historical_frequency",
      ranking: rankNumbers(frequencyScores),
    });

    rankings.push({
      name: "month_probability",
      ranking: rankNumbers(monthScores),
    });

    rankings.push({
      name: "weekday_probability",
      ranking: rankNumbers(weekdayScores),
    });

    rankings.push({
      name: "gap_closeness",
      ranking: rankNumbers(gapScores),
    });

    rankings.push({
      name: "overdue_ratio",
      ranking: rankNumbers(overdueScores),
    });

    for (const window of RECENT_WINDOWS) {
      rankings.push({
        name: `recent_${window}_draws`,
        ranking: rankNumbers(recentScoreMaps[window]),
      });
    }

    /*
     * Combined strategies.
     */

    rankings.push({
      name: "frequency_plus_month",
      ranking: rankNumbers(combineScores([frequencyScores, monthScores])),
    });

    rankings.push({
      name: "frequency_plus_gap",
      ranking: rankNumbers(combineScores([frequencyScores, gapScores])),
    });

    rankings.push({
      name: "frequency_plus_recent100",
      ranking: rankNumbers(
        combineScores([frequencyScores, recentScoreMaps[100]]),
      ),
    });

    rankings.push({
      name: "frequency_plus_month_plus_gap",
      ranking: rankNumbers(
        combineScores([frequencyScores, monthScores, gapScores]),
      ),
    });

    rankings.push({
      name: "frequency_plus_month_plus_recent",
      ranking: rankNumbers(
        combineScores([frequencyScores, monthScores, recentScoreMaps[100]]),
      ),
    });

    rankings.push({
      name: "frequency_plus_gap_plus_recent",
      ranking: rankNumbers(
        combineScores([frequencyScores, gapScores, recentScoreMaps[100]]),
      ),
    });

    /*
     * Random baseline.
     */

    rankings.push({
      name: "random_baseline",
      ranking: randomRanking(targetIndex + 12345),
    });

    for (const strategy of rankings) {
      const result = evaluateStrategy(
        strategy.name,
        strategy.ranking,
        actualNumbers,
      );

      result.target_draw_index = targetIndex;

      result.target_serial_number = targetDraw.serialNumber;

      result.target_date = targetDraw.drawDate;

      detailedResults.push(result);
    }

    /*
     * Update historical state ONLY AFTER
     * evaluating the target draw.
     *
     * This is the critical anti-leakage step.
     */

    for (const number of actualNumbers) {
      const item = state.get(number);

      item.hits++;

      item.lastDrawIndex = targetIndex;

      item.appearanceDraws.push(targetIndex);

      item.monthCounts[targetMonth] = (item.monthCounts[targetMonth] || 0) + 1;

      item.weekdayCounts[targetWeekday] =
        (item.weekdayCounts[targetWeekday] || 0) + 1;
    }

    /*
     * Progress.
     */

    if ((targetIndex - MIN_TRAIN_DRAWS) % 250 === 0) {
      console.log(`Backtested through draw ${targetIndex}/${draws.length}`);
    }
  }

  /*
   * Aggregate.
   */

  const summary = aggregateResults(detailedResults);

  /*
   * Sort by Top-25 performance.
   */

  summary.sort((a, b) => b.mean_top25_hits - a.mean_top25_hits);

  writeCsv("backtest_results.csv", detailedResults);

  writeCsv("backtest_summary.csv", summary);

  /*
   * Console output.
   */

  console.log("");
  console.log("============================================================");
  console.log("BACKTEST SUMMARY");
  console.log("============================================================");

  console.table(
    summary.map((row) => ({
      strategy: row.strategy,

      tests: row.tests,

      top10: row.mean_top10_hits.toFixed(3),

      top25: row.mean_top25_hits.toFixed(3),

      top50: row.mean_top50_hits.toFixed(3),

      top100: row.mean_top100_hits.toFixed(3),

      precision25: (row.mean_top25_precision * 100).toFixed(2) + "%",

      recall100: (row.mean_recall_top100 * 100).toFixed(2) + "%",
    })),
  );

  console.log("");
  console.log("Files:");

  console.log(path.join(OUTPUT_DIR, "backtest_results.csv"));

  console.log(path.join(OUTPUT_DIR, "backtest_summary.csv"));

  console.log("");
  console.log("============================================================");
  console.log("BACKTEST COMPLETE");
  console.log("============================================================");
}

main();
