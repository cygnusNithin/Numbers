require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 7 — DEEP PATTERN SEARCH
//
// Ten new hypotheses tested systematically.
// Goal: find ANY mathematical structure in the draw order.
//
// Each test reports:
//   RESULT: SIGNAL / NOISE / WEAK
//   SIGNAL  = clear pattern, exploitable
//   WEAK    = slight pattern, needs more investigation
//   NOISE   = indistinguishable from random
// ═══════════════════════════════════════════════════════════════

async function runPhase7() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  console.log("📋 Using cycles:", trainCycles.map((c) => c.cycleNumber).join(", "));
  console.log("   Each cycle has ~", Math.round(
    trainCycles.reduce((a, c) => a + c.totalDrawDays, 0) / trainCycles.length
  ), "draw days\n");

  const results = {};

  // ═══════════════════════════════════════════════════════════════
  // TEST 1 — INTRA-DAY GAP ANALYSIS
  // Sort numbers drawn on each day. Look at gaps between them.
  // If every K-th number is drawn, gaps would be ~K constantly.
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("TEST 1 — INTRA-DAY GAP ANALYSIS");
  console.log("  Q: Are gaps between sorted drawn numbers consistent?");
  console.log("═".repeat(65));
  results.test1 = testIntradayGaps(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 2 — DAILY CENTROID TREND
  // Average numeric value of drawn numbers per day.
  // Does it trend up, down, or oscillate across a cycle?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 2 — DAILY CENTROID TREND");
  console.log("  Q: Does the average value of drawn numbers change");
  console.log("     predictably across days of a cycle?");
  console.log("═".repeat(65));
  results.test2 = testDailyCentroid(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 3 — REVERSE CYCLE CORRELATION
  // Read cycle N backwards. Correlate with cycle N+1 forwards.
  // If corr > 0.5, the draw order reverses each cycle.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 3 — REVERSE CYCLE CORRELATION");
  console.log("  Q: Does reading cycle N backwards predict cycle N+1?");
  console.log("═".repeat(65));
  results.test3 = testReverseCycleCorrelation(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 4 — CROSS-CYCLE POSITION LINEARITY
  // For each number, does dayC3 = a × dayC2 + b?
  // Fit a linear regression on (dayC2 → dayC3) and (dayC3 → dayC4)
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 4 — CROSS-CYCLE POSITION LINEARITY");
  console.log("  Q: Is there a linear mapping from a number's day-in-cycle");
  console.log("     across consecutive cycles?");
  console.log("═".repeat(65));
  results.test4 = testCrossCyclePositionLinearity(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 5 — CONSECUTIVE NUMBER PAIRING
  // When number N is drawn, how often is N±1, N±2, N±10 also drawn?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 5 — CONSECUTIVE NUMBER PAIRING");
  console.log("  Q: Are numerically adjacent numbers drawn on the same day?");
  console.log("═".repeat(65));
  results.test5 = testConsecutivePairing(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 6 — DIGIT POSITION DAY TRANSITION
  // For digit position D1 (or D2, D3, D4):
  // Does the most common digit at that position shift predictably
  // from day to day within a cycle?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 6 — DIGIT POSITION DAY TRANSITION");
  console.log("  Q: Does the dominant digit at each position shift");
  console.log("     systematically day by day within a cycle?");
  console.log("═".repeat(65));
  results.test6 = testDigitDayTransition(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 7 — COMPLEMENT STRUCTURE
  // On each day, look at numbers NOT drawn.
  // Do undrawn numbers share a common property?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 7 — COMPLEMENT STRUCTURE");
  console.log("  Q: Do undrawn numbers on a given day share a");
  console.log("     common digit, sum, or modular property?");
  console.log("═".repeat(65));
  results.test7 = testComplementStructure(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 8 — LAST-TO-FIRST DAY BRIDGE
  // Numbers drawn on last day of cycle N vs first day of cycle N+1.
  // Are they related? Overlap? Complementary?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 8 — LAST-TO-FIRST CYCLE BRIDGE");
  console.log("  Q: Is there a mathematical relationship between the last");
  console.log("     draw of cycle N and the first draw of cycle N+1?");
  console.log("═".repeat(65));
  results.test8 = testCycleBridge(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 9 — BACKTRACK: UNIQUE DRAW ORDER RECONSTRUCTION
  // Within a cycle, take only the FIRST appearance of each number.
  // Sort by day. Look at the numeric sequence this produces.
  // Is it sorted? Random? Does it follow a formula?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 9 — UNIQUE DRAW ORDER RECONSTRUCTION");
  console.log("  Q: If we list numbers by first-appearance order,");
  console.log("     does the sequence have mathematical structure?");
  console.log("═".repeat(65));
  results.test9 = testUniqueDrawOrder(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // TEST 10 — SAME-DAY NUMBER MODULAR CLUSTERING
  // For numbers drawn on the same day, test if they share:
  //   (a) same value mod K for various K
  //   (b) same digit sum mod K
  //   (c) same first digit combination
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("TEST 10 — SAME-DAY MODULAR CLUSTERING");
  console.log("  Q: Do numbers drawn on the same day share a modular");
  console.log("     property? (stronger test than digit-sum mod K)");
  console.log("═".repeat(65));
  results.test10 = testSameDayModular(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PHASE 7 SUMMARY — ALL TESTS");
  console.log("═".repeat(65));
  printSummary(results);

  // Export
  fs.writeFileSync(
    "./phase7_output.json",
    JSON.stringify(results, null, 2)
  );
  console.log("\n✅ Phase 7 complete → phase7_output.json");
  await mongoose.disconnect();
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════
function numVal(str) { return parseInt(str, 10); }

function mean(arr) {
  if (!arr.length) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function stdDev(arr) {
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
}

function pearsonCorr(xs, ys) {
  if (xs.length !== ys.length || xs.length === 0) return 0;
  const mx = mean(xs), my = mean(ys);
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < xs.length; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    dx  += (xs[i] - mx) ** 2;
    dy  += (ys[i] - my) ** 2;
  }
  return dx && dy ? num / Math.sqrt(dx * dy) : 0;
}

function linearRegression(xs, ys) {
  const n  = xs.length;
  const mx = mean(xs), my = mean(ys);
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  const slope     = den ? num / den : 0;
  const intercept = my - slope * mx;
  const r         = pearsonCorr(xs, ys);
  return { slope, intercept, r, r2: r * r };
}

// Build number → firstAppearanceDay map for a cycle
function buildFirstAppearance(cycle) {
  const map = new Map();
  for (const dayEntry of cycle.drawEntries) {
    for (const { number, isNew } of dayEntry.numbers) {
      if (isNew && !map.has(number)) {
        map.set(number, dayEntry.dayIndexInCycle);
      }
    }
  }
  return map;
}

// Build set of numbers drawn on each day
function buildDailySets(cycle) {
  const sets = new Map(); // dayIndex → Set<number>
  for (const dayEntry of cycle.drawEntries) {
    const s = new Set(dayEntry.numbers.map((n) => n.number));
    sets.set(dayEntry.dayIndexInCycle, s);
  }
  return sets;
}

// ═══════════════════════════════════════════════════════════════
// TEST 1 — INTRA-DAY GAPS
// ═══════════════════════════════════════════════════════════════
function testIntradayGaps(trainCycles) {
  const allGapMeans  = [];
  const allGapStdDevs = [];
  const gapFreq = {};

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const nums = dayEntry.numbers
        .map((n) => numVal(n.number))
        .sort((a, b) => a - b);

      if (nums.length < 2) continue;

      const gaps = [];
      for (let i = 1; i < nums.length; i++) {
        const g = nums[i] - nums[i - 1];
        gaps.push(g);
        // Track gap frequency (rounded to nearest 5)
        const bucket = Math.round(g / 5) * 5;
        gapFreq[bucket] = (gapFreq[bucket] || 0) + 1;
      }

      allGapMeans.push(mean(gaps));
      allGapStdDevs.push(stdDev(gaps));
    }
  }

  const overallMeanGap   = mean(allGapMeans);
  const overallStdOfMean = stdDev(allGapMeans);
  const expectedGap      = 10000 / 300; // ~33.3 if evenly distributed

  // Most common gaps
  const topGaps = Object.entries(gapFreq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k, v]) => ({ gap: Number(k), count: v }));

  console.log(`\n  Expected gap (if uniform): ~${expectedGap.toFixed(1)}`);
  console.log(`  Actual mean gap:           ${overallMeanGap.toFixed(2)}`);
  console.log(`  Std dev of mean gap:       ${overallStdOfMean.toFixed(2)}`);
  console.log(`\n  Top 10 most common gap values (rounded to ±5):`);
  topGaps.forEach((g) => {
    console.log(`    Gap ~${String(g.gap).padEnd(6)}: ${g.count} occurrences`);
  });

  // Coefficient of variation — low = consistent gaps (structured draw)
  const cv = overallStdOfMean / overallMeanGap;
  console.log(`\n  Coefficient of variation: ${cv.toFixed(3)}`);
  console.log(`  (< 0.1 = very structured | > 0.5 = random-like)`);

  const result = cv < 0.1 ? "SIGNAL" : cv < 0.3 ? "WEAK" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return { overallMeanGap, overallStdOfMean, cv, topGaps, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 2 — DAILY CENTROID TREND
// ═══════════════════════════════════════════════════════════════
function testDailyCentroid(trainCycles) {
  const cycleResults = [];

  for (const cycle of trainCycles) {
    const centroids = []; // [dayIndex, centroid]

    for (const dayEntry of cycle.drawEntries) {
      // Use first-appearance numbers only to avoid hot-number bias
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number));

      if (newNums.length === 0) continue;
      centroids.push([dayEntry.dayIndexInCycle, mean(newNums)]);
    }

    if (centroids.length < 3) continue;

    const days  = centroids.map((c) => c[0]);
    const cents = centroids.map((c) => c[1]);

    // Linear trend in centroid over the cycle
    const reg = linearRegression(days, cents);

    // Expected centroid if uniform: ~5000 (middle of 0–9999)
    const avgCentroid = mean(cents);
    const centroidStd = stdDev(cents);

    cycleResults.push({
      cycleNumber: cycle.cycleNumber,
      avgCentroid: parseFloat(avgCentroid.toFixed(1)),
      centroidStd: parseFloat(centroidStd.toFixed(1)),
      trendSlope:  parseFloat(reg.slope.toFixed(3)),
      r2:          parseFloat(reg.r2.toFixed(4)),
    });

    console.log(`\n  Cycle ${cycle.cycleNumber}:`);
    console.log(`    Avg centroid: ${avgCentroid.toFixed(1)} (expected ~5000 if uniform)`);
    console.log(`    Centroid std: ${centroidStd.toFixed(1)}`);
    console.log(`    Day→centroid trend slope: ${reg.slope.toFixed(2)} R²=${reg.r2.toFixed(4)}`);

    // Print first 10 days centroid
    console.log(`    First 10 days centroid:`);
    centroids.slice(0, 10).forEach(([d, c]) => {
      const bar = "▓".repeat(Math.round(c / 500));
      console.log(`      Day ${String(d).padEnd(3)}: ${c.toFixed(0).padStart(5)}  ${bar}`);
    });
  }

  // Is centroid trend consistent across cycles?
  const slopes = cycleResults.map((r) => r.trendSlope);
  const slopeConsistency = stdDev(slopes);
  const avgSlope         = mean(slopes);

  console.log(`\n  Across cycles — avg slope: ${avgSlope.toFixed(3)}, consistency: ${slopeConsistency.toFixed(3)}`);

  // Signal: if R² is high AND slope is consistent across cycles
  const avgR2 = mean(cycleResults.map((r) => r.r2));
  console.log(`  Avg R² of day→centroid fit: ${avgR2.toFixed(4)}`);

  const result = avgR2 > 0.5 ? "SIGNAL" : avgR2 > 0.1 ? "WEAK" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return { cycleResults, avgSlope, slopeConsistency, avgR2, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 3 — REVERSE CYCLE CORRELATION
// ═══════════════════════════════════════════════════════════════
function testReverseCycleCorrelation(trainCycles) {
  // For each number, get its firstAppearanceDay in each cycle
  // Compare: reversed position in cycle N vs position in cycle N+1

  const correlations = [];

  for (let i = 0; i < trainCycles.length - 1; i++) {
    const cycleA = trainCycles[i];
    const cycleB = trainCycles[i + 1];

    const mapA = buildFirstAppearance(cycleA);
    const mapB = buildFirstAppearance(cycleB);

    // Numbers present in both cycles
    const common = [...mapA.keys()].filter((n) => mapB.has(n));
    if (common.length < 100) continue;

    // Forward correlation: dayA vs dayB
    const daysA = common.map((n) => mapA.get(n));
    const daysB = common.map((n) => mapB.get(n));
    const rFwd  = pearsonCorr(daysA, daysB);

    // Reversed A vs B
    const totalDaysA    = cycleA.totalDrawDays;
    const daysAreversed = common.map((n) => totalDaysA + 1 - mapA.get(n));
    const rRev          = pearsonCorr(daysAreversed, daysB);

    // Normalized forward/reverse
    const normA    = common.map((n) => mapA.get(n) / cycleA.totalDrawDays);
    const normB    = common.map((n) => mapB.get(n) / cycleB.totalDrawDays);
    const normRevA = normA.map((v) => 1 - v);
    const rNormFwd = pearsonCorr(normA, normB);
    const rNormRev = pearsonCorr(normRevA, normB);

    correlations.push({
      pair:       `C${cycleA.cycleNumber}→C${cycleB.cycleNumber}`,
      numCommon:  common.length,
      rForward:   parseFloat(rFwd.toFixed(4)),
      rReversed:  parseFloat(rRev.toFixed(4)),
      rNormFwd:   parseFloat(rNormFwd.toFixed(4)),
      rNormRev:   parseFloat(rNormRev.toFixed(4)),
    });

    console.log(`\n  Cycle ${cycleA.cycleNumber} → Cycle ${cycleB.cycleNumber} (${common.length} common numbers):`);
    console.log(`    Forward correlation (raw):       r = ${rFwd.toFixed(4)}`);
    console.log(`    Reversed A correlation (raw):    r = ${rRev.toFixed(4)}`);
    console.log(`    Forward correlation (normalized): r = ${rNormFwd.toFixed(4)}`);
    console.log(`    Reversed A correlation (norm):    r = ${rNormRev.toFixed(4)}`);
    console.log(`    (r > 0.7 = strong signal, r < 0.2 = noise)`);
  }

  const maxCorr = Math.max(...correlations.flatMap((c) => [
    Math.abs(c.rForward), Math.abs(c.rReversed),
    Math.abs(c.rNormFwd), Math.abs(c.rNormRev),
  ]));

  const result = maxCorr > 0.5 ? "SIGNAL" : maxCorr > 0.2 ? "WEAK" : "NOISE";
  console.log(`\n  Max correlation found: ${maxCorr.toFixed(4)}`);
  console.log(`  RESULT: ${result}`);

  return { correlations, maxCorr, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 4 — CROSS-CYCLE POSITION LINEARITY
// ═══════════════════════════════════════════════════════════════
function testCrossCyclePositionLinearity(trainCycles) {
  const c2 = trainCycles.find((c) => c.cycleNumber === 2);
  const c3 = trainCycles.find((c) => c.cycleNumber === 3);
  const c4 = trainCycles.find((c) => c.cycleNumber === 4);

  if (!c2 || !c3 || !c4) { console.log("  ⚠️  Missing cycles"); return { result: "SKIP" }; }

  const map2 = buildFirstAppearance(c2);
  const map3 = buildFirstAppearance(c3);
  const map4 = buildFirstAppearance(c4);

  // Numbers present in all 3 cycles
  const common = [...map2.keys()].filter((n) => map3.has(n) && map4.has(n));
  console.log(`\n  Numbers in all 3 cycles: ${common.length}`);

  // Raw day positions
  const d2 = common.map((n) => map2.get(n));
  const d3 = common.map((n) => map3.get(n));
  const d4 = common.map((n) => map4.get(n));

  // Normalized positions (0–1)
  const n2 = common.map((n) => map2.get(n) / c2.totalDrawDays);
  const n3 = common.map((n) => map3.get(n) / c3.totalDrawDays);
  const n4 = common.map((n) => map4.get(n) / c4.totalDrawDays);

  // C2 → C3 regression
  const reg23_raw  = linearRegression(d2, d3);
  const reg23_norm = linearRegression(n2, n3);
  const reg34_raw  = linearRegression(d3, d4);
  const reg34_norm = linearRegression(n3, n4);

  // C2 → C4 (skip one cycle)
  const reg24_raw  = linearRegression(d2, d4);
  const reg24_norm = linearRegression(n2, n4);

  console.log(`\n  C2→C3 (raw):        slope=${reg23_raw.slope.toFixed(3)} intercept=${reg23_raw.intercept.toFixed(1)} R²=${reg23_raw.r2.toFixed(4)}`);
  console.log(`  C2→C3 (normalized): slope=${reg23_norm.slope.toFixed(3)} intercept=${reg23_norm.intercept.toFixed(3)} R²=${reg23_norm.r2.toFixed(4)}`);
  console.log(`  C3→C4 (raw):        slope=${reg34_raw.slope.toFixed(3)} intercept=${reg34_raw.intercept.toFixed(1)} R²=${reg34_raw.r2.toFixed(4)}`);
  console.log(`  C3→C4 (normalized): slope=${reg34_norm.slope.toFixed(3)} intercept=${reg34_norm.intercept.toFixed(3)} R²=${reg34_norm.r2.toFixed(4)}`);
  console.log(`  C2→C4 (raw):        slope=${reg24_raw.slope.toFixed(3)} intercept=${reg24_raw.intercept.toFixed(1)} R²=${reg24_raw.r2.toFixed(4)}`);

  // If R² > 0.5: we can predict cycle 5 position from cycle 4 position
  const bestR2 = Math.max(reg23_norm.r2, reg34_norm.r2, reg24_norm.r2);
  console.log(`\n  Best R² (normalized): ${bestR2.toFixed(4)}`);

  if (reg34_norm.r2 > 0.2) {
    // Generate C5 predictions using C4→C5 regression (same as C3→C4)
    const c5 = validCycles?.find?.((c) => !c.isComplete);
    if (c5) {
      console.log(`\n  🔮 Applying C3→C4 regression to predict C4→C5 timing...`);
      const map5    = buildFirstAppearance(c5);
      const pending = common.filter((n) => !map5.has(n));
      const sample  = pending.slice(0, 20);
      console.log(`  Pending numbers C5 sample predictions:`);
      console.log(`  Number | C4 normPos | Predicted C5 normPos | Predicted C5 day (~${c4.totalDrawDays}d est)`);
      console.log(`  ` + "-".repeat(65));
      sample.forEach((n) => {
        const n4pos   = map4.get(n) / c4.totalDrawDays;
        const predN5  = reg34_norm.slope * n4pos + reg34_norm.intercept;
        const predDay = Math.round(predN5 * c4.totalDrawDays);
        console.log(
          `  ${n}   | ${n4pos.toFixed(4)}       | ${predN5.toFixed(4)}                | ~day ${predDay}`
        );
      });
    }
  }

  const result = bestR2 > 0.5 ? "SIGNAL" : bestR2 > 0.15 ? "WEAK" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return {
    numCommon: common.length,
    reg23_norm, reg34_norm, reg24_norm,
    bestR2, result,
  };
}

// ═══════════════════════════════════════════════════════════════
// TEST 5 — CONSECUTIVE NUMBER PAIRING
// ═══════════════════════════════════════════════════════════════
function testConsecutivePairing(trainCycles) {
  let sameDayPairs1 = 0, sameDayPairs2 = 0, sameDayPairs5 = 0, sameDayPairs10 = 0;
  let totalNumbers  = 0;

  for (const cycle of trainCycles) {
    const dailySets = buildDailySets(cycle);

    for (const dayEntry of cycle.drawEntries) {
      const daySet = dailySets.get(dayEntry.dayIndexInCycle);
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => n.number);

      for (const num of newNums) {
        const v = numVal(num);
        totalNumbers++;

        const check = (delta) => {
          const neighbor = String(v + delta).padStart(4, "0");
          return daySet.has(neighbor);
        };

        if (check(1) || check(-1))   sameDayPairs1++;
        if (check(2) || check(-2))   sameDayPairs2++;
        if (check(5) || check(-5))   sameDayPairs5++;
        if (check(10) || check(-10)) sameDayPairs10++;
      }
    }
  }

  // Expected if random: P(neighbor in 300-draw from 10000) = 300/10000 = 3%
  const randomExpected = 0.03;

  const rate1  = sameDayPairs1  / totalNumbers;
  const rate2  = sameDayPairs2  / totalNumbers;
  const rate5  = sameDayPairs5  / totalNumbers;
  const rate10 = sameDayPairs10 / totalNumbers;

  console.log(`\n  Total new-number appearances tested: ${totalNumbers.toLocaleString()}`);
  console.log(`  Random baseline (300/10000):         ${(randomExpected * 100).toFixed(2)}%\n`);
  console.log(`  ±1  neighbor on same day: ${(rate1  * 100).toFixed(2)}%  ${rate1  > randomExpected * 1.5 ? "🔥 ELEVATED" : "≈ random"}`);
  console.log(`  ±2  neighbor on same day: ${(rate2  * 100).toFixed(2)}%  ${rate2  > randomExpected * 1.5 ? "🔥 ELEVATED" : "≈ random"}`);
  console.log(`  ±5  neighbor on same day: ${(rate5  * 100).toFixed(2)}%  ${rate5  > randomExpected * 1.5 ? "🔥 ELEVATED" : "≈ random"}`);
  console.log(`  ±10 neighbor on same day: ${(rate10 * 100).toFixed(2)}%  ${rate10 > randomExpected * 1.5 ? "🔥 ELEVATED" : "≈ random"}`);

  const maxElevation = Math.max(rate1, rate2, rate5, rate10) / randomExpected;
  const result = maxElevation > 2 ? "SIGNAL" : maxElevation > 1.3 ? "WEAK" : "NOISE";
  console.log(`\n  Max elevation vs random: ${maxElevation.toFixed(2)}x`);
  console.log(`  RESULT: ${result}`);

  return { rate1, rate2, rate5, rate10, randomExpected, maxElevation, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 6 — DIGIT DAY TRANSITION
// ═══════════════════════════════════════════════════════════════
function testDigitDayTransition(trainCycles) {
  // For each position (D1,D2,D3,D4), find the dominant digit each day.
  // Check if dominant digit shifts predictably (e.g., increments by 1 each day).

  const posNames = ["D1", "D2", "D3", "D4"];
  const findings = [];

  for (const pos of [0, 1, 2, 3]) {
    const cycleShifts = [];

    for (const cycle of trainCycles) {
      const dailyDominant = [];

      for (const dayEntry of cycle.drawEntries) {
        const newNums = dayEntry.numbers.filter((n) => n.isNew);
        if (newNums.length === 0) continue;

        const freq = {};
        newNums.forEach((n) => {
          const d = n.number[pos];
          freq[d] = (freq[d] || 0) + 1;
        });

        const dominant = Object.entries(freq).sort((a, b) => b[1] - a[1])[0];
        dailyDominant.push({
          day: dayEntry.dayIndexInCycle,
          digit: Number(dominant[0]),
          count: dominant[1],
          total: newNums.length,
          pct: ((dominant[1] / newNums.length) * 100).toFixed(1),
        });
      }

      // Day-to-day shift in dominant digit
      const shifts = [];
      for (let i = 1; i < dailyDominant.length; i++) {
        shifts.push(dailyDominant[i].digit - dailyDominant[i - 1].digit);
      }

      const avgShift = mean(shifts);
      const shiftStd = stdDev(shifts);
      cycleShifts.push({ cycleNumber: cycle.cycleNumber, avgShift, shiftStd, dailyDominant });
    }

    const avgShiftAcrossCycles = mean(cycleShifts.map((c) => c.avgShift));
    const shiftConsistency     = stdDev(cycleShifts.map((c) => c.avgShift));

    console.log(`\n  ${posNames[pos]}:`);
    cycleShifts.forEach((cs) => {
      console.log(
        `    Cycle ${cs.cycleNumber}: avgShift=${cs.avgShift.toFixed(3)} stdDev=${cs.shiftStd.toFixed(3)}`
      );
      // Print first 5 days
      cs.dailyDominant.slice(0, 5).forEach((d) => {
        console.log(`      Day ${String(d.day).padEnd(3)}: dominant digit ${d.digit} (${d.pct}%)`);
      });
    });
    console.log(`    Avg shift across cycles: ${avgShiftAcrossCycles.toFixed(3)}`);
    console.log(`    Consistency: ${shiftConsistency.toFixed(3)}`);

    findings.push({
      position:              posNames[pos],
      avgShiftAcrossCycles,
      shiftConsistency,
      isStructured:          shiftConsistency < 0.5 && Math.abs(avgShiftAcrossCycles) > 0.05,
    });
  }

  const anyStructured = findings.some((f) => f.isStructured);
  const result = anyStructured ? "WEAK" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return { findings, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 7 — COMPLEMENT STRUCTURE
// ═══════════════════════════════════════════════════════════════
function testComplementStructure(trainCycles) {
  // For each draw day, get numbers NOT drawn.
  // Test if undrawn numbers have lower variance in digit sum
  // vs what we'd expect from random non-selection.

  const findings = [];

  for (const cycle of trainCycles) {
    const allNums = Array.from({ length: 10000 }, (_, i) =>
      String(i).padStart(4, "0")
    );
    const allDigitSums = allNums.map((n) =>
      n.split("").reduce((a, d) => a + Number(d), 0)
    );
    const overallMean = mean(allDigitSums);
    const overallStd  = stdDev(allDigitSums);

    const dayStats = [];

    for (const dayEntry of cycle.drawEntries.slice(0, 10)) {
      const drawnSet   = new Set(dayEntry.numbers.map((n) => n.number));
      const undrawnNums = allNums.filter((n) => !drawnSet.has(n));

      // Digit sums of undrawn
      const undrawnSums = undrawnNums.map((n) =>
        n.split("").reduce((a, d) => a + Number(d), 0)
      );
      const uMean = mean(undrawnSums);
      const uStd  = stdDev(undrawnSums);

      // Digit sums of drawn
      const drawnSums = [...drawnSet].map((n) =>
        n.split("").reduce((a, d) => a + Number(d), 0)
      );
      const dMean = mean(drawnSums);
      const dStd  = stdDev(drawnSums);

      dayStats.push({
        day: dayEntry.dayIndexInCycle,
        drawnMean: parseFloat(dMean.toFixed(2)),
        drawnStd:  parseFloat(dStd.toFixed(2)),
        undrawnMean: parseFloat(uMean.toFixed(2)),
        undrawnStd:  parseFloat(uStd.toFixed(2)),
        meanDiff: parseFloat((dMean - uMean).toFixed(3)),
      });
    }

    console.log(`\n  Cycle ${cycle.cycleNumber} — First 10 days:`);
    console.log(`  Overall digit sum: mean=${overallMean.toFixed(2)} std=${overallStd.toFixed(2)}`);
    console.log(`  Day | DrawnMean | DrawnStd | UndrawnMean | UndrawnStd | MeanDiff`);
    console.log(`  ` + "-".repeat(65));
    dayStats.forEach((s) => {
      console.log(
        `  ${String(s.day).padEnd(3)} | ${String(s.drawnMean).padEnd(9)} | ` +
        `${String(s.drawnStd).padEnd(8)} | ${String(s.undrawnMean).padEnd(11)} | ` +
        `${String(s.undrawnStd).padEnd(10)} | ${s.meanDiff}`
      );
    });

    const avgMeanDiff = mean(dayStats.map((s) => Math.abs(s.meanDiff)));
    findings.push({ cycleNumber: cycle.cycleNumber, avgMeanDiff, dayStats });
  }

  // If drawn numbers consistently have different digit sum mean than undrawn,
  // that's a structural signal
  const overallAvgDiff = mean(findings.map((f) => f.avgMeanDiff));
  const expectedRandom = 0.05; // very small difference expected by chance

  console.log(`\n  Avg absolute mean diff (drawn vs undrawn digit sums): ${overallAvgDiff.toFixed(3)}`);
  console.log(`  (> 0.5 = strong structure, < 0.1 = noise)`);

  const result = overallAvgDiff > 0.5 ? "SIGNAL" : overallAvgDiff > 0.2 ? "WEAK" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return { findings, overallAvgDiff, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 8 — CYCLE BRIDGE (last day N → first day N+1)
// ═══════════════════════════════════════════════════════════════
function testCycleBridge(trainCycles) {
  const bridges = [];

  for (let i = 0; i < trainCycles.length - 1; i++) {
    const cycleA = trainCycles[i];
    const cycleB = trainCycles[i + 1];

    const lastDayA  = cycleA.drawEntries[cycleA.drawEntries.length - 1];
    const firstDayB = cycleB.drawEntries[0];

    if (!lastDayA || !firstDayB) continue;

    const lastNums  = new Set(lastDayA.numbers.map((n) => n.number));
    const firstNums = new Set(firstDayB.numbers.map((n) => n.number));

    // Overlap
    const overlap = [...lastNums].filter((n) => firstNums.has(n));

    // Expected overlap if random: |lastNums| × |firstNums| / 10000
    const expectedOverlap = (lastNums.size * firstNums.size) / 10000;

    // Digit sum comparison
    const lastSums  = [...lastNums].map((n) => n.split("").reduce((a,d)=>a+Number(d),0));
    const firstSums = [...firstNums].map((n) => n.split("").reduce((a,d)=>a+Number(d),0));

    // Numeric distance: avg |lastNum - nearestFirstNum|
    const lastArr  = [...lastNums].map((n) => numVal(n)).sort((a,b)=>a-b);
    const firstArr = [...firstNums].map((n) => numVal(n)).sort((a,b)=>a-b);

    console.log(`\n  Bridge C${cycleA.cycleNumber}→C${cycleB.cycleNumber}:`);
    console.log(`    Last day of C${cycleA.cycleNumber}:  ${lastNums.size} numbers`);
    console.log(`    First day of C${cycleB.cycleNumber}: ${firstNums.size} numbers`);
    console.log(`    Overlap:          ${overlap.length} numbers`);
    console.log(`    Expected overlap: ~${expectedOverlap.toFixed(1)}`);
    console.log(`    Last day digit sum mean:  ${mean(lastSums).toFixed(2)}`);
    console.log(`    First day digit sum mean: ${mean(firstSums).toFixed(2)}`);
    if (overlap.length > 0) {
      console.log(`    Overlapping numbers: ${overlap.slice(0,10).join(", ")}`);
    }

    bridges.push({
      pair: `C${cycleA.cycleNumber}→C${cycleB.cycleNumber}`,
      overlapCount:    overlap.length,
      expectedOverlap: parseFloat(expectedOverlap.toFixed(1)),
      overlapRatio:    parseFloat((overlap.length / expectedOverlap).toFixed(2)),
    });
  }

  const avgOverlapRatio = mean(bridges.map((b) => b.overlapRatio));
  console.log(`\n  Avg overlap ratio vs expected: ${avgOverlapRatio.toFixed(2)}x`);
  console.log(`  (1.0 = random, > 2.0 = structural pattern)`);

  const result = avgOverlapRatio > 2 ? "SIGNAL" : avgOverlapRatio > 1.3 ? "WEAK" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return { bridges, avgOverlapRatio, result };
}

// ═══════════════════════════════════════════════════════════════
// TEST 9 — UNIQUE DRAW ORDER RECONSTRUCTION
// ═══════════════════════════════════════════════════════════════
function testUniqueDrawOrder(trainCycles) {
  // List all numbers by first-appearance day (ascending).
  // This is the "unique draw sequence" for the cycle.
  // Test: does the numeric value follow any pattern across this sequence?

  for (const cycle of trainCycles) {
    const firstApp = buildFirstAppearance(cycle);

    // Sort numbers by first appearance day
    const ordered = [...firstApp.entries()]
      .sort((a, b) => a[1] - b[1])
      .map(([num, day]) => ({ num, day, val: numVal(num) }));

    const vals     = ordered.map((o) => o.val);
    const positions = ordered.map((_, i) => i);

    // Is the sequence sorted? (would mean early numbers are low-valued)
    const reg = linearRegression(positions, vals);

    // Is there autocorrelation? (each number predicts the next)
    const lagCorr = pearsonCorr(vals.slice(0, -1), vals.slice(1));

    // Range check: does numeric value oscillate, increase, or stay random?
    const firstQuarter = vals.slice(0, Math.floor(vals.length / 4));
    const lastQuarter  = vals.slice(Math.floor(vals.length * 3 / 4));
    const meanFirst    = mean(firstQuarter);
    const meanLast     = mean(lastQuarter);

    console.log(`\n  Cycle ${cycle.cycleNumber} unique draw sequence:`);
    console.log(`    Total unique numbers: ${ordered.length}`);
    console.log(`    Linear trend (position→value): slope=${reg.slope.toFixed(2)} R²=${reg.r2.toFixed(4)}`);
    console.log(`    Lag-1 autocorrelation: ${lagCorr.toFixed(4)}`);
    console.log(`    Mean value first 25%: ${meanFirst.toFixed(0)}`);
    console.log(`    Mean value last 25%:  ${meanLast.toFixed(0)}`);
    console.log(`    Difference: ${(meanLast - meanFirst).toFixed(0)}`);

    // Show first 20 numbers in sequence
    console.log(`    First 20 in unique sequence:`);
    ordered.slice(0, 20).forEach((o) => {
      process.stdout.write(`      ${o.num}(d${o.day})  `);
    });
    console.log();
  }

  // Cross-cycle: does the unique sequence correlate across cycles?
  const c2 = trainCycles.find((c) => c.cycleNumber === 2);
  const c3 = trainCycles.find((c) => c.cycleNumber === 3);
  const c4 = trainCycles.find((c) => c.cycleNumber === 4);

  if (c2 && c3 && c4) {
    const map2 = buildFirstAppearance(c2);
    const map3 = buildFirstAppearance(c3);
    const map4 = buildFirstAppearance(c4);

    const common = [...map2.keys()].filter((n) => map3.has(n) && map4.has(n));

    // Rank in each cycle
    const rank2 = new Map([...map2.entries()].sort((a,b)=>a[1]-b[1]).map(([n],i)=>[n,i]));
    const rank3 = new Map([...map3.entries()].sort((a,b)=>a[1]-b[1]).map(([n],i)=>[n,i]));
    const rank4 = new Map([...map4.entries()].sort((a,b)=>a[1]-b[1]).map(([n],i)=>[n,i]));

    const r23 = pearsonCorr(common.map((n) => rank2.get(n)), common.map((n) => rank3.get(n)));
    const r34 = pearsonCorr(common.map((n) => rank3.get(n)), common.map((n) => rank4.get(n)));

    console.log(`\n  Rank correlation (Pearson):`);
    console.log(`    C2 rank → C3 rank: r = ${r23.toFixed(4)}`);
    console.log(`    C3 rank → C4 rank: r = ${r34.toFixed(4)}`);

    const result = Math.max(Math.abs(r23), Math.abs(r34)) > 0.5
      ? "SIGNAL" : Math.max(Math.abs(r23), Math.abs(r34)) > 0.2
      ? "WEAK" : "NOISE";
    console.log(`\n  RESULT: ${result}`);
    return { r23, r34, result };
  }

  return { result: "SKIP" };
}

// ═══════════════════════════════════════════════════════════════
// TEST 10 — SAME-DAY MODULAR CLUSTERING
// ═══════════════════════════════════════════════════════════════
function testSameDayModular(trainCycles) {
  // For each draw day, check if the numeric values of drawn numbers
  // concentrate in any residue class mod K.
  // Chi-squared test: expected = drawnCount/K per class.

  const Ks = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 17, 19, 23, 100];
  const results = {};

  for (const K of Ks) {
    let totalChiSq = 0;
    let totalDays  = 0;

    for (const cycle of trainCycles) {
      for (const dayEntry of cycle.drawEntries) {
        const drawn = dayEntry.numbers
          .filter((n) => n.isNew)
          .map((n) => numVal(n.number));

        if (drawn.length < K) continue;

        const freq = new Array(K).fill(0);
        drawn.forEach((v) => { freq[v % K]++; });

        const expected = drawn.length / K;
        const chiSq    = freq.reduce((s, f) => s + (f - expected) ** 2 / expected, 0);
        totalChiSq += chiSq;
        totalDays++;
      }
    }

    const avgChiSq    = totalDays > 0 ? totalChiSq / totalDays : 0;
    const dof         = K - 1;
    // Critical value at p=0.01 for various df (approximation: chi2 > 2*dof is significant)
    const isSignificant = avgChiSq > dof * 2;

    results[K] = { K, avgChiSq: parseFloat(avgChiSq.toFixed(3)), dof, isSignificant };
  }

  console.log(`\n  Modular clustering test (avg chi-squared per draw day):`);
  console.log(`  K   | AvgChiSq | DoF | Critical(2×DoF) | Significant?`);
  console.log(`  ` + "-".repeat(60));

  let anySignificant = false;
  for (const { K, avgChiSq, dof, isSignificant } of Object.values(results)) {
    if (isSignificant) anySignificant = true;
    console.log(
      `  ${String(K).padEnd(3)} | ${String(avgChiSq).padEnd(8)} | ${String(dof).padEnd(3)} | ` +
      `${String(dof * 2).padEnd(15)} | ${isSignificant ? "✅ YES" : "❌ no"}`
    );
  }

  // Extra test: same number mod 10 (last digit clustering)
  console.log(`\n  Last digit (mod 10) distribution check:`);
  for (const cycle of trainCycles.slice(0, 1)) {
    for (const dayEntry of cycle.drawEntries.slice(0, 5)) {
      const drawn    = dayEntry.numbers.filter((n) => n.isNew).map((n) => numVal(n.number));
      const lastDigits = new Array(10).fill(0);
      drawn.forEach((v) => { lastDigits[v % 10]++; });
      console.log(
        `    Cycle ${cycle.cycleNumber} Day ${dayEntry.dayIndexInCycle}: ` +
        lastDigits.map((c, i) => `${i}:${c}`).join(" ")
      );
    }
  }

  const result = anySignificant ? "SIGNAL" : "NOISE";
  console.log(`\n  RESULT: ${result}`);

  return { results: Object.values(results), anySignificant, result };
}

// ═══════════════════════════════════════════════════════════════
// SUMMARY
// ═══════════════════════════════════════════════════════════════
function printSummary(results) {
  const tests = [
    { name: "Intra-day gap analysis",           key: "test1" },
    { name: "Daily centroid trend",             key: "test2" },
    { name: "Reverse cycle correlation",        key: "test3" },
    { name: "Cross-cycle position linearity",   key: "test4" },
    { name: "Consecutive number pairing",       key: "test5" },
    { name: "Digit position day transition",    key: "test6" },
    { name: "Complement structure",             key: "test7" },
    { name: "Last-to-first cycle bridge",       key: "test8" },
    { name: "Unique draw order reconstruction", key: "test9" },
    { name: "Same-day modular clustering",      key: "test10" },
  ];

  console.log("\n  Test                                | Result  | Key Metric");
  console.log("  " + "-".repeat(75));

  const signals = [];
  for (const t of tests) {
    const r = results[t.key];
    if (!r) continue;
    const result  = r.result ?? "SKIP";
    const emoji   = result === "SIGNAL" ? "🔥" : result === "WEAK" ? "⚠️ " : "❌";
    if (result === "SIGNAL") signals.push(t.name);

    let metric = "";
    if (t.key === "test1")  metric = `cv=${r.cv?.toFixed(3)}`;
    if (t.key === "test2")  metric = `avgR²=${r.avgR2?.toFixed(4)}`;
    if (t.key === "test3")  metric = `maxCorr=${r.maxCorr?.toFixed(4)}`;
    if (t.key === "test4")  metric = `bestR²=${r.bestR2?.toFixed(4)}`;
    if (t.key === "test5")  metric = `maxElev=${r.maxElevation?.toFixed(2)}x`;
    if (t.key === "test6")  metric = r.findings?.some((f) => f.isStructured) ? "structured" : "flat";
    if (t.key === "test7")  metric = `meanDiff=${r.overallAvgDiff?.toFixed(3)}`;
    if (t.key === "test8")  metric = `overlapRatio=${r.avgOverlapRatio?.toFixed(2)}x`;
    if (t.key === "test9")  metric = `r23=${r.r23?.toFixed(4)} r34=${r.r34?.toFixed(4)}`;
    if (t.key === "test10") metric = r.anySignificant ? "K found" : "none";

    console.log(
      `  ${emoji} ${String(t.name).padEnd(35)} | ${String(result).padEnd(7)} | ${metric}`
    );
  }

  console.log("\n" + "═".repeat(65));
  if (signals.length === 0) {
    console.log("  No strong signals found across all 10 tests.");
    console.log("  The draw appears to be genuinely well-randomized.");
    console.log("\n  NEXT STEPS TO TRY:");
    console.log("  1. Obtain more cycles (currently only 3 training cycles)");
    console.log("  2. Test if the random seed is date-based (day/month/year)");
    console.log("  3. Look for patterns in the PRIZE AMOUNT sequence per day");
    console.log("  4. Test if specific officials/machines have signatures");
    console.log("  5. Analyze the actual draw PAPER/PDF for structural clues");
  } else {
    console.log(`  🔥 SIGNALS FOUND in ${signals.length} test(s):`);
    signals.forEach((s) => console.log(`     → ${s}`));
    console.log("\n  These signals should be investigated further in Phase 8.");
  }
  console.log("═".repeat(65));
}

// ─────────────────────────────────────────────────────
runPhase7().catch((err) => {
  console.error("❌ Phase 7 failed:", err);
  process.exit(1);
});