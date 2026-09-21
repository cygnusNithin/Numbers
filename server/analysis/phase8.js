require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 8 — CLUSTER WALK ANALYSIS
//
// Key insight from Phase 7:
//   Lag-1 autocorrelation of unique draw sequence = 0.73–0.78
//   Numerically adjacent numbers appear on same day ~1.93x random
//
// Hypothesis:
//   Each draw day has a "cluster center" in number space.
//   Numbers near the center get drawn.
//   The center walks through 0000–9999 across the cycle.
//   This walk has structure we can exploit for prediction.
//
// Tests:
//   1. Measure cluster size per day (radius of drawn numbers)
//   2. Track cluster center movement day to day (the walk)
//   3. Measure walk step distribution (mean, std, direction)
//   4. Find if walk is predictable (autocorrelation of steps)
//   5. Validate: predict cluster center for day D+1 from day D
//   6. Convert cluster center prediction to number list
//   7. Predict tomorrow using today's actual draw
// ═══════════════════════════════════════════════════════════════

async function runPhase8() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  console.log("📋 Using cycles:", trainCycles.map((c) => c.cycleNumber).join(", "));
  console.log("   Lag-1 autocorrelation from Phase 7: ~0.73–0.78");
  console.log("   Neighbor same-day rate: ~1.93x random\n");

  // ═══════════════════════════════════════════════════════════════
  // STEP 1 — MEASURE CLUSTER CENTERS PER DAY
  // Cluster center = median numeric value of new numbers drawn
  // (median is more robust than mean against outliers)
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — CLUSTER CENTER MEASUREMENT PER DAY");
  console.log("═".repeat(65));

  const clusterData = buildClusterData(trainCycles);
  printClusterStats(clusterData);

  // ═══════════════════════════════════════════════════════════════
  // STEP 2 — CLUSTER WALK ANALYSIS
  // How does the center move day to day?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — CLUSTER WALK STEP DISTRIBUTION");
  console.log("═".repeat(65));

  const walkStats = analyzeWalkSteps(clusterData);
  printWalkStats(walkStats);

  // ═══════════════════════════════════════════════════════════════
  // STEP 3 — WALK AUTOCORRELATION
  // Does today's step predict tomorrow's step?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — WALK STEP AUTOCORRELATION");
  console.log("  Q: Does today's step direction predict tomorrow's?");
  console.log("═".repeat(65));

  const walkAutoCorr = analyzeWalkAutocorrelation(clusterData);
  printWalkAutocorr(walkAutoCorr);

  // ═══════════════════════════════════════════════════════════════
  // STEP 4 — CLUSTER RADIUS ANALYSIS
  // How spread are the drawn numbers around the center?
  // Is the radius consistent? Can we predict it?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — CLUSTER RADIUS ANALYSIS");
  console.log("  Q: How many numbers fall within radius R of center?");
  console.log("═".repeat(65));

  const radiusStats = analyzeClusterRadius(clusterData, trainCycles);
  printRadiusStats(radiusStats);

  // ═══════════════════════════════════════════════════════════════
  // STEP 5 — VALIDATION: PREDICT CLUSTER CENTER
  // Train on cycles 2+3, predict cycle 4 cluster centers.
  // Measure: how close is predicted center to actual center?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — VALIDATION: CLUSTER CENTER PREDICTION");
  console.log("  Train: C2+C3 walk stats → Predict: C4 day-by-day");
  console.log("═".repeat(65));

  const valResult = validateClusterPrediction(
    clusterData, trainCycles, walkStats, radiusStats
  );
  printValidation(valResult);

  // ═══════════════════════════════════════════════════════════════
  // STEP 6 — MULTI-CLUSTER ANALYSIS
  // Maybe there isn't ONE cluster per day but MULTIPLE sub-clusters.
  // Find the actual clusters within each day's draw.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — MULTI-CLUSTER DETECTION");
  console.log("  Q: Are there multiple sub-clusters within each draw?");
  console.log("═".repeat(65));

  const multiCluster = analyzeMultiCluster(trainCycles);
  printMultiCluster(multiCluster);

  // ═══════════════════════════════════════════════════════════════
  // STEP 7 — TOMORROW'S PREDICTION
  // Use today's actual cycle 5 draw to predict tomorrow
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — TOMORROW'S PREDICTION (cycle 5)");
  console.log("  Using cluster walk model on today's actual draw");
  console.log("═".repeat(65));

  predictTomorrow(currentCycle, walkStats, radiusStats);

  console.log("\n✅ Phase 8 complete");
  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function numVal(str) { return parseInt(str, 10); }
function mean(arr)   { return arr.reduce((a, b) => a + b, 0) / arr.length; }
function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function stdDev(arr) {
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
}
function pearsonCorr(xs, ys) {
  if (xs.length < 2) return 0;
  const mx = mean(xs), my = mean(ys);
  let n = 0, dx = 0, dy = 0;
  for (let i = 0; i < xs.length; i++) {
    n  += (xs[i] - mx) * (ys[i] - my);
    dx += (xs[i] - mx) ** 2;
    dy += (ys[i] - my) ** 2;
  }
  return dx && dy ? n / Math.sqrt(dx * dy) : 0;
}
function percentile(arr, p) {
  const s = [...arr].sort((a, b) => a - b);
  const i = (p / 100) * (s.length - 1);
  const lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

// ─────────────────────────────────────────────────────────────
// BUILD CLUSTER DATA
// For each cycle, for each draw day:
//   - center: median of new numbers drawn
//   - mean: mean of new numbers
//   - spread: std dev of new numbers
//   - count: how many new numbers
//   - min/max of drawn numbers
// ─────────────────────────────────────────────────────────────
function buildClusterData(trainCycles) {
  const data = {};

  for (const cycle of trainCycles) {
    data[cycle.cycleNumber] = [];

    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number));

      if (newNums.length === 0) continue;

      const allNums = dayEntry.numbers.map((n) => numVal(n.number));

      data[cycle.cycleNumber].push({
        day:         dayEntry.dayIndexInCycle,
        count:       newNums.length,
        center:      median(newNums),
        centerMean:  mean(newNums),
        spread:      stdDev(newNums),
        totalDrawn:  allNums.length,
        allCenter:   median(allNums),
        allSpread:   stdDev(allNums),
        min:         Math.min(...newNums),
        max:         Math.max(...newNums),
        p25:         percentile(newNums, 25),
        p75:         percentile(newNums, 75),
      });
    }
  }

  return data;
}

function printClusterStats(clusterData) {
  for (const [cycleNum, days] of Object.entries(clusterData)) {
    const centers  = days.map((d) => d.center);
    const spreads  = days.map((d) => d.spread);
    const counts   = days.map((d) => d.count);

    console.log(`\n  Cycle ${cycleNum} (${days.length} days with new numbers):`);
    console.log(`    Center: mean=${mean(centers).toFixed(0)} std=${stdDev(centers).toFixed(0)} min=${Math.min(...centers).toFixed(0)} max=${Math.max(...centers).toFixed(0)}`);
    console.log(`    Spread: mean=${mean(spreads).toFixed(0)} std=${stdDev(spreads).toFixed(0)}`);
    console.log(`    New numbers/day: mean=${mean(counts).toFixed(1)} std=${stdDev(counts).toFixed(1)}`);

    // Show first 10 days
    console.log(`\n    First 10 days cluster visualization (center, spread):`);
    console.log(`    Day | Count | Center | Spread | Range`);
    console.log(`    ` + "-".repeat(52));
    days.slice(0, 10).forEach((d) => {
      const bar = Math.round(d.center / 100);
      const spread = Math.round(d.spread);
      console.log(
        `    ${String(d.day).padEnd(3)} | ${String(d.count).padEnd(5)} | ` +
        `${String(Math.round(d.center)).padEnd(6)} | ${String(spread).padEnd(6)} | ` +
        `${d.min}–${d.max}`
      );
    });
  }
}

// ─────────────────────────────────────────────────────────────
// ANALYZE WALK STEPS
// step[i] = center[i+1] - center[i]
// ─────────────────────────────────────────────────────────────
function analyzeWalkSteps(clusterData) {
  const allSteps = [];
  const byDirection = { positive: 0, negative: 0, zero: 0 };
  const stepStats   = {};

  for (const [cycleNum, days] of Object.entries(clusterData)) {
    const steps = [];
    for (let i = 1; i < days.length; i++) {
      const step = days[i].center - days[i - 1].center;
      steps.push(step);
      allSteps.push(step);
      if (step > 0)      byDirection.positive++;
      else if (step < 0) byDirection.negative++;
      else               byDirection.zero++;
    }

    stepStats[cycleNum] = {
      steps,
      mean:    parseFloat(mean(steps).toFixed(2)),
      std:     parseFloat(stdDev(steps).toFixed(2)),
      abs_mean: parseFloat(mean(steps.map(Math.abs)).toFixed(2)),
      median:  parseFloat(median(steps).toFixed(2)),
    };
  }

  return {
    byDirection,
    allStepsMean:   parseFloat(mean(allSteps).toFixed(2)),
    allStepsStd:    parseFloat(stdDev(allSteps).toFixed(2)),
    allStepsAbsMean: parseFloat(mean(allSteps.map(Math.abs)).toFixed(2)),
    allStepsMedian: parseFloat(median(allSteps).toFixed(2)),
    allSteps,
    byDirection,
    perCycle: stepStats,
  };
}

function printWalkStats(ws) {
  console.log(`\n  Walk step distribution across all cycles:`);
  console.log(`    Mean step:      ${ws.allStepsMean} (bias toward positive/negative?)`);
  console.log(`    Median step:    ${ws.allStepsMedian}`);
  console.log(`    Std dev step:   ${ws.allStepsStd}`);
  console.log(`    Mean |step|:    ${ws.allStepsAbsMean} (avg distance moved per day)`);
  console.log(`    Direction: +${ws.byDirection.positive} steps | -${ws.byDirection.negative} steps | 0:${ws.byDirection.zero} steps`);

  const upPct = ((ws.byDirection.positive / (ws.byDirection.positive + ws.byDirection.negative)) * 100).toFixed(1);
  console.log(`    Up/Down ratio: ${upPct}% up, ${(100 - parseFloat(upPct)).toFixed(1)}% down`);

  for (const [cycleNum, stats] of Object.entries(ws.perCycle)) {
    console.log(`\n  Cycle ${cycleNum}: mean=${stats.mean} std=${stats.std} abs_mean=${stats.abs_mean}`);

    // Show step sequence for first 20 days
    console.log(`    First 20 steps: ${stats.steps.slice(0, 20).map((s) => (s >= 0 ? "+" : "") + Math.round(s)).join(" ")}`);
  }

  // Step size distribution (bucket)
  const buckets = {};
  ws.allSteps.forEach((s) => {
    const bucket = Math.round(Math.abs(s) / 500) * 500;
    buckets[bucket] = (buckets[bucket] || 0) + 1;
  });
  console.log(`\n  Step magnitude distribution:`);
  Object.entries(buckets)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .slice(0, 12)
    .forEach(([k, v]) => {
      const bar = "█".repeat(Math.round(v / 5));
      console.log(`    |step| ~${String(k).padEnd(5)}: ${String(v).padEnd(5)} ${bar}`);
    });
}

// ─────────────────────────────────────────────────────────────
// WALK AUTOCORRELATION
// Does today's step predict tomorrow's step?
// If positive: walk has momentum (trending)
// If negative: walk reverses (mean-reverting)
// ─────────────────────────────────────────────────────────────
function analyzeWalkAutocorrelation(clusterData) {
  const results = {};

  for (const [cycleNum, days] of Object.entries(clusterData)) {
    const steps = [];
    for (let i = 1; i < days.length; i++) {
      steps.push(days[i].center - days[i - 1].center);
    }

    // Lag-1 autocorrelation of steps
    const lag1 = pearsonCorr(steps.slice(0, -1), steps.slice(1));
    // Lag-2 autocorrelation
    const lag2 = pearsonCorr(steps.slice(0, -2), steps.slice(2));

    // Sign persistence: P(same direction as previous step)
    let samSign = 0;
    for (let i = 1; i < steps.length; i++) {
      if (Math.sign(steps[i]) === Math.sign(steps[i - 1])) samSign++;
    }
    const signPersistence = samSign / (steps.length - 1);

    results[cycleNum] = { lag1, lag2, signPersistence, steps };
  }

  return results;
}

function printWalkAutocorr(autoCorr) {
  console.log(`\n  Walk step autocorrelation:`);
  console.log(`  Cycle | Lag-1 r | Lag-2 r | Sign Persistence`);
  console.log(`  ` + "-".repeat(50));

  for (const [cycleNum, r] of Object.entries(autoCorr)) {
    const momentum = r.lag1 > 0.2 ? "trending" : r.lag1 < -0.2 ? "mean-reverting" : "random";
    console.log(
      `  ${String(cycleNum).padEnd(5)} | ${r.lag1.toFixed(4)}   | ${r.lag2.toFixed(4)}   | ` +
      `${(r.signPersistence * 100).toFixed(1)}%  (${momentum})`
    );
  }

  const avgLag1 = mean(Object.values(autoCorr).map((r) => r.lag1));
  const avgSign = mean(Object.values(autoCorr).map((r) => r.signPersistence));

  console.log(`\n  Avg lag-1 autocorrelation: ${avgLag1.toFixed(4)}`);
  console.log(`  Avg sign persistence: ${(avgSign * 100).toFixed(1)}%`);
  console.log(`  (50% = random | >60% = momentum | <40% = mean-reverting)`);

  const result =
    Math.abs(avgLag1) > 0.2 ? "SIGNAL — walk has memory" :
    Math.abs(avgLag1) > 0.1 ? "WEAK — slight memory" :
                               "NOISE — random walk";
  console.log(`\n  Walk autocorrelation result: ${result}`);
}

// ─────────────────────────────────────────────────────────────
// CLUSTER RADIUS ANALYSIS
// For each day, how many DRAWN numbers fall within radius R
// of the cluster center?
// ─────────────────────────────────────────────────────────────
function analyzeClusterRadius(clusterData, trainCycles) {
  const radii = [500, 1000, 1500, 2000, 2500, 3000];
  const results = {};

  for (const cycle of trainCycles) {
    const cycleNum = cycle.cycleNumber;
    results[cycleNum] = {};

    for (const R of radii) {
      let totalInRadius = 0;
      let totalNewNums  = 0;

      for (const dayEntry of cycle.drawEntries) {
        const clusterDay = clusterData[cycleNum]?.find(
          (d) => d.day === dayEntry.dayIndexInCycle
        );
        if (!clusterDay) continue;

        const center = clusterDay.center;
        const newNums = dayEntry.numbers
          .filter((n) => n.isNew)
          .map((n) => numVal(n.number));

        const inRadius = newNums.filter((v) => Math.abs(v - center) <= R).length;
        totalInRadius += inRadius;
        totalNewNums  += newNums.length;
      }

      const pct = totalNewNums > 0 ? (totalInRadius / totalNewNums) * 100 : 0;
      results[cycleNum][R] = { inRadius: totalInRadius, total: totalNewNums, pct };
    }
  }

  // Expected pct if random: 2R/10000 × 100
  console.log(`\n  Coverage by radius (what % of new numbers fall within R of center):`);
  console.log(`  R     | Expected% | Cycle2% | Cycle3% | Cycle4% | Elevation`);
  console.log(`  ` + "-".repeat(65));

  for (const R of radii) {
    const expected = (2 * R / 10000) * 100;
    const c = Object.entries(results).map(([cn, rs]) => rs[R].pct.toFixed(1));
    const avgActual = mean(Object.values(results).map((rs) => rs[R].pct));
    const elevation = avgActual / expected;
    console.log(
      `  ${String(R).padEnd(5)} | ${expected.toFixed(1).padEnd(9)} | ` +
      `${c.join("% | ")}%  | ${elevation.toFixed(2)}x`
    );
  }

  // Find the radius where elevation peaks
  const elevations = radii.map((R) => {
    const expected   = (2 * R / 10000) * 100;
    const avgActual  = mean(Object.values(results).map((rs) => rs[R].pct));
    return { R, elevation: avgActual / expected, avgActual };
  });
  const bestR = elevations.sort((a, b) => b.elevation - a.elevation)[0];
  console.log(`\n  Peak cluster signal at R = ${bestR.R} (${bestR.elevation.toFixed(2)}x random)`);

  return { results, elevations, bestR };
}

function printRadiusStats(rs) {
  console.log(`\n  Interpretation:`);
  console.log(`    If elevation >> 1.0: numbers concentrate near the center.`);
  console.log(`    Peak elevation at R=${rs.bestR.R}: ${rs.bestR.elevation.toFixed(2)}x`);

  if (rs.bestR.elevation > 1.5) {
    console.log(`    ✅ SIGNAL: There IS genuine clustering around the center!`);
    console.log(`    Numbers within ±${rs.bestR.R} of center are ${rs.bestR.elevation.toFixed(1)}x`);
    console.log(`    more likely to be drawn than random.`);
  } else {
    console.log(`    ⚠️  Weak or no clustering detected.`);
  }
}

// ─────────────────────────────────────────────────────────────
// VALIDATE CLUSTER PREDICTION
// Given cycle 4's previous day center, can we predict
// which numbers appear next?
// ─────────────────────────────────────────────────────────────
function validateClusterPrediction(clusterData, trainCycles, walkStats, radiusStats) {
  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle4) return null;

  const c4Days = clusterData[4];
  if (!c4Days || c4Days.length < 2) return null;

  // Use walk stats from cycles 2+3 only
  const trainWalkMean = mean([
    walkStats.perCycle[2]?.mean ?? 0,
    walkStats.perCycle[3]?.mean ?? 0,
  ]);
  const trainWalkStd = mean([
    walkStats.perCycle[2]?.std ?? 1,
    walkStats.perCycle[3]?.std ?? 1,
  ]);
  const bestR = radiusStats.bestR.R;

  console.log(`\n  Walk model (from cycles 2+3): mean step=${trainWalkMean.toFixed(1)} std=${trainWalkStd.toFixed(1)}`);
  console.log(`  Prediction radius: ±${bestR}`);

  let totalHits    = 0;
  let totalActual  = 0;
  let totalPredicted = 0;
  const dayResults = [];

  for (let i = 0; i < c4Days.length - 1; i++) {
    const todayCenter = c4Days[i].center;
    // Predict tomorrow's center = today's center + avg step
    const predictedCenter = todayCenter + trainWalkMean;

    // Find tomorrow's actual draw
    const tomorrowDay = cycle4.drawEntries.find(
      (d) => d.dayIndexInCycle === c4Days[i + 1].day
    );
    if (!tomorrowDay) continue;

    // Get actual new numbers for tomorrow
    const actualNew = new Set(
      tomorrowDay.numbers.filter((n) => n.isNew).map((n) => n.number)
    );

    // Predict: all numbers within ±bestR of predictedCenter
    const predicted = new Set();
    const lo = Math.max(0, Math.round(predictedCenter - bestR));
    const hi = Math.min(9999, Math.round(predictedCenter + bestR));
    for (let v = lo; v <= hi; v++) {
      predicted.add(String(v).padStart(4, "0"));
    }

    const hits = [...actualNew].filter((n) => predicted.has(n)).length;
    totalHits      += hits;
    totalActual    += actualNew.size;
    totalPredicted += predicted.size;

    dayResults.push({
      day:            c4Days[i + 1].day,
      predictedCenter: Math.round(predictedCenter),
      actualCenter:   c4Days[i + 1].center,
      centerError:    Math.abs(c4Days[i + 1].center - predictedCenter),
      predictedSize:  predicted.size,
      actualNewSize:  actualNew.size,
      hits,
      hitPct:         actualNew.size > 0 ? ((hits / actualNew.size) * 100).toFixed(1) : "0",
    });
  }

  const overallHitPct     = totalActual > 0 ? ((totalHits / totalActual) * 100).toFixed(2) : "0";
  const avgCenterError    = mean(dayResults.map((r) => r.centerError));
  const randomBaseline    = ((bestR * 2) / 10000 * 100).toFixed(2);

  console.log(`\n  Validation on cycle 4 (${dayResults.length} days):`);
  console.log(`    Total actual new numbers:  ${totalActual}`);
  console.log(`    Total hits (in radius):    ${totalHits}`);
  console.log(`    Overall hit rate:          ${overallHitPct}%`);
  console.log(`    Random baseline:           ~${randomBaseline}%`);
  console.log(`    Avg center prediction error: ${avgCenterError.toFixed(0)} units`);

  const improvement = parseFloat(overallHitPct) / parseFloat(randomBaseline);
  console.log(`    Improvement vs random:     ${improvement.toFixed(2)}x`);

  // Print first 10 days
  console.log(`\n  First 10 day predictions:`);
  console.log(`  Day | PredCenter | ActualCenter | Error  | PredSize | Hits | Hit%`);
  console.log(`  ` + "-".repeat(72));
  dayResults.slice(0, 10).forEach((r) => {
    console.log(
      `  ${String(r.day).padEnd(3)} | ${String(r.predictedCenter).padEnd(10)} | ` +
      `${String(Math.round(r.actualCenter)).padEnd(12)} | ${String(Math.round(r.centerError)).padEnd(6)} | ` +
      `${String(r.predictedSize).padEnd(8)} | ${String(r.hits).padEnd(4)} | ${r.hitPct}%`
    );
  });

  // Try improved model: use sign persistence (momentum)
  console.log(`\n  ── Improved model: using momentum (previous step direction) ──`);
  let totalHits2 = 0, totalActual2 = 0;
  let prevStep = 0;

  const autoCorr2 = Object.values({
    2: clusterData[2] || [],
    3: clusterData[3] || [],
  }).flatMap((days) => {
    const steps = [];
    for (let i = 1; i < days.length; i++) steps.push(days[i].center - days[i-1].center);
    return steps;
  });
  const avgAbsStep = mean(autoCorr2.map(Math.abs));

  for (let i = 0; i < c4Days.length - 1; i++) {
    const todayCenter = c4Days[i].center;
    // Momentum model: if prevStep was positive, predict positive step
    const momentumBias = Math.sign(prevStep) * avgAbsStep * 0.3;
    const predictedCenter2 = todayCenter + trainWalkMean + momentumBias;
    prevStep = c4Days[i + 1].center - c4Days[i].center; // actual step

    const tomorrowDay = cycle4.drawEntries.find(
      (d) => d.dayIndexInCycle === c4Days[i + 1].day
    );
    if (!tomorrowDay) continue;

    const actualNew2 = new Set(
      tomorrowDay.numbers.filter((n) => n.isNew).map((n) => n.number)
    );

    const predicted2 = new Set();
    const lo2 = Math.max(0, Math.round(predictedCenter2 - bestR));
    const hi2 = Math.min(9999, Math.round(predictedCenter2 + bestR));
    for (let v = lo2; v <= hi2; v++) predicted2.add(String(v).padStart(4, "0"));

    const hits2 = [...actualNew2].filter((n) => predicted2.has(n)).length;
    totalHits2   += hits2;
    totalActual2 += actualNew2.size;
  }

  const hitPct2 = ((totalHits2 / totalActual2) * 100).toFixed(2);
  const improvement2 = parseFloat(hitPct2) / parseFloat(randomBaseline);
  console.log(`    Momentum model hit rate: ${hitPct2}% (vs random ${randomBaseline}% = ${improvement2.toFixed(2)}x)`);

  return {
    overallHitPct, randomBaseline, improvement,
    avgCenterError, dayResults,
    momentumHitPct: hitPct2, momentumImprovement: improvement2,
  };
}

// ─────────────────────────────────────────────────────────────
// MULTI-CLUSTER DETECTION
// Split each day's new numbers into sub-clusters.
// Count how many clusters per day and their properties.
// ─────────────────────────────────────────────────────────────
function analyzeMultiCluster(trainCycles) {
  const GAP_THRESHOLD = 200; // numbers more than 200 apart are different clusters

  const clusterCounts = [];
  const clusterSizes  = [];

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number))
        .sort((a, b) => a - b);

      if (newNums.length < 5) continue;

      // Find clusters by large gaps
      const clusters = [[newNums[0]]];
      for (let i = 1; i < newNums.length; i++) {
        if (newNums[i] - newNums[i - 1] > GAP_THRESHOLD) {
          clusters.push([]);
        }
        clusters[clusters.length - 1].push(newNums[i]);
      }

      clusterCounts.push(clusters.length);
      clusters.forEach((c) => clusterSizes.push(c.length));
    }
  }

  const avgClusters    = mean(clusterCounts);
  const avgClusterSize = mean(clusterSizes);

  // Distribution of cluster counts per day
  const countDist = {};
  clusterCounts.forEach((c) => { countDist[c] = (countDist[c] || 0) + 1; });

  console.log(`\n  Gap threshold for sub-clusters: ${GAP_THRESHOLD}`);
  console.log(`  Avg clusters per draw day:  ${avgClusters.toFixed(2)}`);
  console.log(`  Avg cluster size:           ${avgClusterSize.toFixed(2)}`);
  console.log(`\n  Clusters-per-day distribution:`);
  Object.entries(countDist)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .forEach(([k, v]) => {
      const bar = "█".repeat(Math.round(v / 10));
      console.log(`    ${String(k).padEnd(3)} clusters: ${String(v).padEnd(5)} days  ${bar}`);
    });

  if (avgClusters < 5) {
    console.log(`\n  ✅ Few large clusters (avg ${avgClusters.toFixed(1)}) — numbers drawn in blocks!`);
  } else {
    console.log(`\n  ⚠️  Many small clusters — scattered drawing pattern.`);
  }

  return { avgClusters, avgClusterSize, countDist };
}

// ─────────────────────────────────────────────────────────────
// PREDICT TOMORROW (cycle 5)
// ─────────────────────────────────────────────────────────────
function predictTomorrow(currentCycle, walkStats, radiusStats) {
  if (!currentCycle || currentCycle.drawEntries.length === 0) {
    console.log("  ⚠️  No cycle 5 data");
    return;
  }

  // Get last draw day
  const lastDay = currentCycle.drawEntries[currentCycle.drawEntries.length - 1];
  const lastNums = lastDay.numbers.map((n) => numVal(n.number));
  const lastCenter = median(lastNums);
  const lastDate   = lastDay.drawDate;

  // Walk model params
  const avgStep  = walkStats.allStepsMean;
  const absStep  = walkStats.allStepsAbsMean;
  const bestR    = radiusStats.bestR.R;

  // Three scenarios
  const scenarios = [
    { label: "Neutral (avg step)",   center: lastCenter + avgStep },
    { label: "Up (avg |step|)",      center: lastCenter + absStep },
    { label: "Down (-avg |step|)",   center: lastCenter - absStep },
  ];

  console.log(`\n  Last draw: day ${lastDay.dayIndexInCycle}`);
  console.log(`  Last draw date: ${new Date(lastDate).toISOString().split("T")[0]}`);
  console.log(`  Last draw center (median): ${Math.round(lastCenter)}`);
  console.log(`  Last draw range: ${Math.min(...lastNums)}–${Math.max(...lastNums)}`);
  console.log(`  Walk model: avg step = ${avgStep.toFixed(1)}, avg |step| = ${absStep.toFixed(1)}`);
  console.log(`  Prediction radius: ±${bestR}\n`);

  // Remaining numbers
  const remaining = new Set();
  const allNums   = Array.from({ length: 10000 }, (_, i) => String(i).padStart(4, "0"));
  const drawn     = new Set();
  currentCycle.drawEntries.forEach((d) => {
    d.numbers.forEach((n) => { if (n.isNew) drawn.add(n.number); });
  });
  allNums.forEach((n) => { if (!drawn.has(n)) remaining.add(n); });

  console.log(`  Cycle 5 remaining: ${remaining.size} numbers\n`);

  for (const s of scenarios) {
    const center = Math.round(s.center);
    const lo     = Math.max(0, center - bestR);
    const hi     = Math.min(9999, center + bestR);

    // Candidates = numbers in radius that are still remaining
    const candidates = [];
    for (let v = lo; v <= hi; v++) {
      const num = String(v).padStart(4, "0");
      if (remaining.has(num)) candidates.push(num);
    }

    console.log(`  Scenario: ${s.label}`);
    console.log(`    Predicted center: ${center}`);
    console.log(`    Search range:     ${lo}–${hi}`);
    console.log(`    Remaining candidates in range: ${candidates.length}`);
    if (candidates.length > 0 && candidates.length <= 50) {
      console.log(`    Candidates: ${candidates.join(", ")}`);
    } else if (candidates.length > 50) {
      console.log(`    Sample: ${candidates.slice(0, 20).join(", ")} ... (${candidates.length} total)`);
    }
    console.log();
  }

  // Best bet: union of all three scenarios filtered to remaining
  const union = new Set();
  for (const s of scenarios) {
    const center = Math.round(s.center);
    const lo     = Math.max(0, center - bestR);
    const hi     = Math.min(9999, center + bestR);
    for (let v = lo; v <= hi; v++) {
      const num = String(v).padStart(4, "0");
      if (remaining.has(num)) union.add(num);
    }
  }

  console.log(`  Combined (union of all scenarios) remaining candidates: ${union.size}`);
  if (union.size <= 100) {
    console.log(`  Numbers: ${[...union].sort().join(", ")}`);
  } else {
    console.log(`  Sample: ${[...union].sort().slice(0, 30).join(", ")} ...`);
  }
}

// ─────────────────────────────────────────────────────────────
runPhase8().catch((err) => {
  console.error("❌ Phase 8 failed:", err);
  process.exit(1);
});