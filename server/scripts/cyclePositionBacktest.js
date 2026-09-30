/**
 * Cycle Position Backtest
 *
 * C1 = reference only
 * C2-C5 = historical out-of-sample tests
 * C6 = current cycle
 *
 * We test whether historical first-appearance timing inside a cycle
 * helps identify numbers that will appear in the NEXT 10% of a cycle.
 *
 * IMPORTANT:
 * No future data from the test cycle is used as a feature.
 */

const fs = require("fs");
const path = require("path");
const csv = require("csv-parser");

const INPUT = path.join(__dirname, "../absolute_data_number_patterns.csv");

const OUTPUT_DIR = path.join(__dirname, "cycle-position-results");

const TOTAL_NUMBERS = 10000;
const CHECKPOINTS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];

const TOP_K = [10, 25, 50, 100];

// ---------------------------------------------------------
// Load CSV
// ---------------------------------------------------------

function loadCSV() {
  return new Promise((resolve, reject) => {
    const rows = [];

    fs.createReadStream(INPUT)
      .pipe(csv())
      .on("data", (row) => rows.push(row))
      .on("end", () => resolve(rows))
      .on("error", reject);
  });
}

// ---------------------------------------------------------
// Parse dates field
// ---------------------------------------------------------

function parseDates(value) {
  if (!value) return [];

  return String(value)
    .split("|")
    .map((v) => v.trim())
    .filter(Boolean)
    .map((value) => {
      const parts = value.split("/");

      if (parts.length !== 3) {
        return null;
      }

      const day = Number(parts[0]);
      const month = Number(parts[1]);
      const year = Number(parts[2]);

      if (
        !Number.isInteger(day) ||
        !Number.isInteger(month) ||
        !Number.isInteger(year)
      ) {
        return null;
      }

      // Use UTC so timezone differences cannot change the date.
      return new Date(Date.UTC(year, month - 1, day));
    })
    .filter(Boolean)
    .sort((a, b) => a - b);
}

// ---------------------------------------------------------
// Build date -> numbers map
// ---------------------------------------------------------

function buildDateMap(rows) {
  const map = new Map();

  for (const row of rows) {
    const number = String(row.number).padStart(4, "0");
    const dates = parseDates(row.dates);

    for (const date of dates) {
      const key = date.toISOString().slice(0, 10);

      if (!map.has(key)) {
        map.set(key, new Set());
      }

      map.get(key).add(number);
    }
  }

  return map;
}

// ---------------------------------------------------------
// Discover cycles
//
// SAME CONCEPT AS cycleAnalysis.js:
//
// Keep collecting unique numbers.
// When all 10,000 have appeared,
// the cycle is complete.
// ---------------------------------------------------------

function discoverCycles(dateMap) {
  const dates = [...dateMap.keys()].sort();

  const cycles = [];

  let seen = new Set();
  let cycleDates = [];
  let cycleStart = dates[0];

  for (const date of dates) {
    cycleDates.push(date);

    for (const number of dateMap.get(date)) {
      seen.add(number);
    }

    if (seen.size === TOTAL_NUMBERS) {
      cycles.push({
        cycle: cycles.length + 1,
        start: cycleStart,
        end: date,
        dates: [...cycleDates],
        complete: true,
      });

      seen = new Set();
      cycleDates = [];
      cycleStart = null;
    }
  }

  if (cycleDates.length > 0) {
    cycles.push({
      cycle: cycles.length + 1,
      start: cycleStart,
      end: cycleDates[cycleDates.length - 1],
      dates: [...cycleDates],
      complete: false,
    });
  }

  return cycles;
}

// ---------------------------------------------------------
// Build information for every cycle
//
// firstPosition[number]
// = position from 0 -> 1 where number first appeared.
//
// Example:
//
// 0.10 = appeared near beginning
// 0.80 = appeared late
// ---------------------------------------------------------

function buildCycleInfo(cycles, dateMap) {
  const result = {};

  for (const cycle of cycles) {
    const counts = new Map();
    const firstIndex = new Map();

    cycle.dates.forEach((date, index) => {
      const numbers = dateMap.get(date);

      for (const number of numbers) {
        counts.set(number, (counts.get(number) || 0) + 1);

        if (!firstIndex.has(number)) {
          firstIndex.set(number, index);
        }
      }
    });

    const firstPosition = new Map();

    const denominator = Math.max(cycle.dates.length - 1, 1);

    for (const number of firstIndex.keys()) {
      firstPosition.set(number, firstIndex.get(number) / denominator);
    }

    result[cycle.cycle] = {
      counts,
      firstPosition,
    };
  }

  return result;
}

// ---------------------------------------------------------
// Historical features
//
// For test cycle T:
//
// use ONLY cycles 1 -> T-1.
//
// C1 can be used as historical reference,
// but C1 itself is never evaluated as a test cycle.
// ---------------------------------------------------------

function historicalFeatures(testCycle, cycleInfo) {
  const meanFirst = new Map();
  const medianFirst = new Map();
  const stdFirst = new Map();

  const meanCount = new Map();

  for (let n = 0; n < TOTAL_NUMBERS; n++) {
    const number = String(n).padStart(4, "0");

    const positions = [];
    const counts = [];

    for (let c = 1; c < testCycle; c++) {
      const info = cycleInfo[c];

      positions.push(info.firstPosition.get(number));

      counts.push(info.counts.get(number) || 0);
    }

    const validPositions = positions.filter((v) => v !== undefined);

    const mean =
      validPositions.reduce((sum, v) => sum + v, 0) / validPositions.length;

    const sorted = [...validPositions].sort((a, b) => a - b);

    const middle = Math.floor(sorted.length / 2);

    const median =
      sorted.length % 2 === 0
        ? (sorted[middle - 1] + sorted[middle]) / 2
        : sorted[middle];

    const variance =
      validPositions.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) /
      validPositions.length;

    meanFirst.set(number, mean);
    medianFirst.set(number, median);
    stdFirst.set(number, Math.sqrt(variance));

    meanCount.set(number, counts.reduce((a, b) => a + b, 0) / counts.length);
  }

  return {
    meanFirst,
    medianFirst,
    stdFirst,
    meanCount,
  };
}

// ---------------------------------------------------------
// Create checkpoint
// ---------------------------------------------------------

function createCheckpoint(cycle, cycleInfo, dateMap, checkpointFraction) {
  const dates = cycle.dates;

  const checkpointIndex = Math.min(
    dates.length - 2,
    Math.max(0, Math.round((dates.length - 1) * checkpointFraction)),
  );

  const visibleDates = dates.slice(0, checkpointIndex + 1);

  const futureWindowLength = Math.max(1, Math.round(dates.length * 0.1));

  const futureDates = dates.slice(
    checkpointIndex + 1,
    checkpointIndex + 1 + futureWindowLength,
  );

  // Numbers already seen.
  const seen = new Set();

  for (const date of visibleDates) {
    for (const number of dateMap.get(date)) {
      seen.add(number);
    }
  }

  // Candidates = numbers not yet seen.
  const candidates = [];

  for (let n = 0; n < TOTAL_NUMBERS; n++) {
    const number = String(n).padStart(4, "0");

    if (!seen.has(number)) {
      candidates.push(number);
    }
  }

  // Target:
  // did the number appear in the next 10%?
  const target = new Set();

  for (const date of futureDates) {
    for (const number of dateMap.get(date)) {
      target.add(number);
    }
  }

  const historical = historicalFeatures(cycle.cycle, cycleInfo);

  const rows = [];

  for (const number of candidates) {
    const meanFirst = historical.meanFirst.get(number);

    const stdFirst = historical.stdFirst.get(number);

    const meanCount = historical.meanCount.get(number);

    const lateness = meanFirst - checkpointFraction;

    const consistency = 1 / (1 + stdFirst);

    rows.push({
      number,

      checkpointFraction,

      historicalMeanFirst: meanFirst,

      historicalMedianFirst: historical.medianFirst.get(number),

      historicalFirstStd: stdFirst,

      historicalMeanCount: meanCount,

      latenessScore: lateness,

      consistencyScore: consistency,

      lateConsistencyScore: lateness * consistency,

      target: target.has(number),
    });
  }

  return {
    rows,
    futureDates,
    candidateCount: candidates.length,
    targetCount: target.size,
    checkpointDate: visibleDates[visibleDates.length - 1],
  };
}

// ---------------------------------------------------------
// Evaluate strategy
// ---------------------------------------------------------

function evaluate(rows, strategy, topK) {
  const sorted = [...rows];

  if (strategy === "historical_lateness") {
    sorted.sort((a, b) => b.latenessScore - a.latenessScore);
  } else if (strategy === "late_consistency") {
    sorted.sort((a, b) => b.lateConsistencyScore - a.lateConsistencyScore);
  } else if (strategy === "historical_frequency") {
    sorted.sort((a, b) => b.historicalMeanCount - a.historicalMeanCount);
  } else if (strategy === "random") {
    sorted.sort(() => Math.random() - 0.5);
  }

  const selected = sorted.slice(0, Math.min(topK, sorted.length));

  const hits = selected.filter((row) => row.target).length;

  const targetCount = rows.filter((row) => row.target).length;

  const candidateCount = rows.length;

  const expectedRandom = (topK * targetCount) / candidateCount;

  return {
    hits,

    precision: hits / selected.length,

    recall: targetCount > 0 ? hits / targetCount : 0,

    expectedRandom,

    lift: expectedRandom > 0 ? hits / expectedRandom : 0,
  };
}

// ---------------------------------------------------------
// Main
// ---------------------------------------------------------

async function main() {
  console.log("\nLoading CSV...");

  const rows = await loadCSV();

  console.log(`Loaded ${rows.length} numbers`);

  const dateMap = buildDateMap(rows);

  console.log(`Unique dates: ${dateMap.size}`);

  const cycles = discoverCycles(dateMap);

  console.log("\nCycles:");

  for (const cycle of cycles) {
    console.log(
      `C${cycle.cycle}: ` +
        `${cycle.start} -> ${cycle.end} ` +
        `(${cycle.dates.length} dates) ` +
        `${cycle.complete ? "COMPLETE" : "INCOMPLETE"}`,
    );
  }

  const cycleInfo = buildCycleInfo(cycles, dateMap);

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const results = [];

  // -------------------------------------------------------
  // C2 -> C5
  // -------------------------------------------------------

  for (let testCycle = 2; testCycle <= 5; testCycle++) {
    const cycle = cycles[testCycle - 1];

    console.log(`\nTesting C${testCycle}...`);

    for (const checkpoint of CHECKPOINTS) {
      const checkpointData = createCheckpoint(
        cycle,
        cycleInfo,
        dateMap,
        checkpoint,
      );

      for (const strategy of [
        "random",
        "historical_lateness",
        "late_consistency",
        "historical_frequency",
      ]) {
        for (const topK of TOP_K) {
          const score = evaluate(checkpointData.rows, strategy, topK);

          results.push({
            testCycle,

            checkpoint,

            checkpointDate: checkpointData.checkpointDate,

            futureStart: checkpointData.futureDates[0],

            futureEnd:
              checkpointData.futureDates[checkpointData.futureDates.length - 1],

            candidateCount: checkpointData.candidateCount,

            targetCount: checkpointData.targetCount,

            strategy,

            topK,

            hits: score.hits,

            precision: score.precision,

            recall: score.recall,

            expectedRandom: score.expectedRandom,

            lift: score.lift,
          });
        }
      }
    }
  }

  // -------------------------------------------------------
  // Save detailed results
  // -------------------------------------------------------

  const detailPath = path.join(OUTPUT_DIR, "cycle_position_backtest.csv");

  writeCSV(detailPath, results);

  // -------------------------------------------------------
  // Summary
  // -------------------------------------------------------

  const summary = [];

  const groups = new Map();

  for (const row of results) {
    const key = `${row.strategy}|${row.topK}`;

    if (!groups.has(key)) {
      groups.set(key, []);
    }

    groups.get(key).push(row);
  }

  for (const [key, group] of groups) {
    const [strategy, topK] = key.split("|");

    summary.push({
      strategy,

      topK: Number(topK),

      meanHits: average(group.map((r) => r.hits)),

      meanPrecision: average(group.map((r) => r.precision)),

      meanRecall: average(group.map((r) => r.recall)),

      meanLift: average(group.map((r) => r.lift)),

      medianLift: median(group.map((r) => r.lift)),

      positiveLiftRate: group.filter((r) => r.lift > 1).length / group.length,
    });
  }

  writeCSV(path.join(OUTPUT_DIR, "cycle_position_summary.csv"), summary);

  // -------------------------------------------------------
  // Current C6 ranking
  // -------------------------------------------------------

  console.log("\nRanking current C6...");

  const current = cycles[5];

  const currentCheckpoint = createCheckpoint(current, cycleInfo, dateMap, 1);

  const currentRows = currentCheckpoint.rows;

  currentRows.sort((a, b) => b.lateConsistencyScore - a.lateConsistencyScore);

  currentRows.forEach((row, index) => {
    row.rank = index + 1;
  });

  writeCSV(
    path.join(OUTPUT_DIR, "current_c6_position_ranking.csv"),
    currentRows,
  );

  // -------------------------------------------------------
  // Print useful summary
  // -------------------------------------------------------

  console.log("\n======================================");

  console.log("CYCLE POSITION BACKTEST COMPLETE");

  console.log("======================================\n");

  console.table(summary.sort((a, b) => b.meanLift - a.meanLift));

  console.log(`\nCurrent C6 candidates: ` + `${currentRows.length}`);

  console.log("\nTop 30 C6 candidates:");

  console.table(
    currentRows.slice(0, 30).map((row) => ({
      rank: row.rank,

      number: row.number,

      historicalMeanFirst: row.historicalMeanFirst.toFixed(4),

      firstStd: row.historicalFirstStd.toFixed(4),

      lateConsistency: row.lateConsistencyScore.toFixed(4),

      historicalMeanCount: row.historicalMeanCount.toFixed(2),
    })),
  );

  console.log("\nOutput files:");

  console.log(detailPath);

  console.log(path.join(OUTPUT_DIR, "cycle_position_summary.csv"));

  console.log(path.join(OUTPUT_DIR, "current_c6_position_ranking.csv"));
}

// ---------------------------------------------------------
// CSV writer
// ---------------------------------------------------------

function writeCSV(filePath, rows) {
  if (!rows.length) {
    fs.writeFileSync(filePath, "");

    return;
  }

  const columns = Object.keys(rows[0]);

  const lines = [columns.join(",")];

  for (const row of rows) {
    lines.push(columns.map((column) => csvEscape(row[column])).join(","));
  }

  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const string = String(value);

  if (string.includes(",") || string.includes('"') || string.includes("\n")) {
    return `"${string.replace(/"/g, '""')}"`;
  }

  return string;
}

function average(values) {
  if (!values.length) return 0;

  return values.reduce((a, b) => a + b, 0) / values.length;
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

main().catch((error) => {
  console.error("\nBACKTEST ERROR:\n", error);

  process.exit(1);
});
