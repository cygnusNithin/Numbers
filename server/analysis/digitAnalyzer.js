/**
 * Note: dayIndexInCycle now refers to day within the REAL cycle
 * (e.g. day 1 to ~364), not a micro-cycle.
 * We bucket days into THIRDS of cycle for practical analysis:
 *   Early  = days 1 to ~121
 *   Mid    = days ~122 to ~243
 *   Late   = days ~244 to end
 */
function buildDigitPositionMatrix(cycles, completedOnly = true) {
  const matrix = {};
  const targetCycles = completedOnly
    ? cycles.filter((c) => c.isComplete)
    : cycles;

  for (const cycle of targetCycles) {
    const totalDays = cycle.totalDrawDays;
    const third = Math.ceil(totalDays / 3);

    for (const dayEntry of cycle.drawEntries) {
      // Use bucketed day: early/mid/late
      const bucket =
        dayEntry.dayIndexInCycle <= third
          ? "early"
          : dayEntry.dayIndexInCycle <= 2 * third
          ? "mid"
          : "late";

      if (!matrix[bucket]) {
        matrix[bucket] = [
          newDigitFreq(),
          newDigitFreq(),
          newDigitFreq(),
          newDigitFreq(),
        ];
      }

      for (const { number, isNew } of dayEntry.numbers) {
        // Only count NEW numbers (first appearances) to avoid hot-number bias
        if (!isNew) continue;
        for (let pos = 0; pos < 4; pos++) {
          matrix[bucket][pos][number[pos]]++;
        }
      }
    }
  }
  return matrix;
}

function newDigitFreq() {
  const f = {};
  for (let d = 0; d <= 9; d++) f[String(d)] = 0;
  return f;
}

/**
 * Digit sum distribution per cycle bucket (early/mid/late).
 * Uses FIRST appearances only to avoid hot-number skew.
 */
function buildDigitSumDistribution(cycles) {
  const distribution = { early: {}, mid: {}, late: {} };
  for (const cycle of cycles.filter((c) => c.isComplete)) {
    const third = Math.ceil(cycle.totalDrawDays / 3);
    for (const dayEntry of cycle.drawEntries) {
      const bucket =
        dayEntry.dayIndexInCycle <= third
          ? "early"
          : dayEntry.dayIndexInCycle <= 2 * third
          ? "mid"
          : "late";
      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        const sum = number.split("").reduce((a, d) => a + Number(d), 0);
        distribution[bucket][sum] = (distribution[bucket][sum] || 0) + 1;
      }
    }
  }
  return distribution;
}

/**
 * Test if digit sum modulo K correlates with cycle bucket.
 */
function testModularHypothesis(cycles, K = 7) {
  let hits = 0;
  let total = 0;
  for (const cycle of cycles.filter((c) => c.isComplete)) {
    for (const dayEntry of cycle.drawEntries) {
      const expectedMod = dayEntry.dayIndexInCycle % K;
      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        const sum = number.split("").reduce((a, d) => a + Number(d), 0);
        if (sum % K === expectedMod) hits++;
        total++;
      }
    }
  }
  const hitRate = total ? ((hits / total) * 100).toFixed(2) : "0";
  const expected = (100 / K).toFixed(2);
  return {
    K,
    hits,
    total,
    hitRate: `${hitRate}%`,
    expectedIfRandom: `${expected}%`,
    isSignificant: parseFloat(hitRate) > parseFloat(expected) * 1.15,
  };
}

/**
 * Number range bucket (0-999, 1000-1999, ...) vs cycle bucket (early/mid/late).
 * Detects if certain number ranges appear earlier or later in cycles.
 */
function buildRangeBucketMatrix(cycles) {
  const matrix = {};
  for (const cycle of cycles.filter((c) => c.isComplete)) {
    const third = Math.ceil(cycle.totalDrawDays / 3);
    for (const dayEntry of cycle.drawEntries) {
      const cycleBucket =
        dayEntry.dayIndexInCycle <= third
          ? "early"
          : dayEntry.dayIndexInCycle <= 2 * third
          ? "mid"
          : "late";
      if (!matrix[cycleBucket]) matrix[cycleBucket] = {};
      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        const rangeBucket = number[0]; // first digit → 0-9 range
        matrix[cycleBucket][rangeBucket] =
          (matrix[cycleBucket][rangeBucket] || 0) + 1;
      }
    }
  }
  return matrix;
}

function printDigitFreqByBucket(matrix) {
  const positions = ["D1", "D2", "D3", "D4"];
  for (const bucket of ["early", "mid", "late"]) {
    if (!matrix[bucket]) continue;
    console.log(`\n===== Digit Frequency (First Appearances) — ${bucket.toUpperCase()} cycle phase =====`);
    for (let pos = 0; pos < 4; pos++) {
      const freq = matrix[bucket][pos];
      const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]);
      console.log(
        `  ${positions[pos]}: ` + sorted.map(([d, c]) => `${d}:${c}`).join(" | ")
      );
    }
  }
}

function printModularTests(cycles) {
  console.log("\n===== MODULAR HYPOTHESIS TESTS (on first appearances) =====");
  console.log("K   | HitRate   | Expected (random)  | Significant?");
  console.log("-".repeat(58));
  for (let k = 2; k <= 13; k++) {
    const r = testModularHypothesis(cycles, k);
    console.log(
      `K=${String(k).padEnd(3)} | ${r.hitRate.padEnd(10)} | ${r.expectedIfRandom.padEnd(19)} | ${r.isSignificant ? "✅ YES" : "❌ no"}`
    );
  }
}

function printRangeBucketMatrix(matrix) {
  console.log("\n===== NUMBER RANGE vs CYCLE PHASE =====");
  console.log("Range  | early  | mid    | late");
  console.log("-".repeat(40));
  for (let r = 0; r <= 9; r++) {
    const e = matrix?.early?.[String(r)] || 0;
    const m = matrix?.mid?.[String(r)] || 0;
    const l = matrix?.late?.[String(r)] || 0;
    console.log(
      `${r}000s  | ${String(e).padEnd(7)}| ${String(m).padEnd(7)}| ${String(l).padEnd(7)}`
    );
  }
}

module.exports = {
  buildDigitPositionMatrix,
  buildDigitSumDistribution,
  testModularHypothesis,
  buildRangeBucketMatrix,
  printDigitFreqByBucket,
  printModularTests,
  printRangeBucketMatrix,
};