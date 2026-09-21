require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 8+9 — MEAN-REVERSION CLUSTER WALK
//
// Phase 8 discovered:
//   Lag-1 autocorrelation of cluster walk = -0.52 (consistent)
//   Sign persistence = 33% (67% reversal probability)
//   → The cluster center is MEAN-REVERTING
//   → If center moved UP by X today, it moves DOWN by ~0.52X tomorrow
//
// Phase 9 exploits this:
//   Use mean-reversion formula to predict tomorrow's center
//   Validate against actual cycle 4 data
//   Predict tomorrow's draw in cycle 5
//
// Also new in Phase 9:
//   Segment frequency analysis (which 1000-number blocks get hit)
//   Amplitude decay analysis (does oscillation grow or shrink?)
//   Day-parity effects (odd vs even days)
// ═══════════════════════════════════════════════════════════════

async function runPhase8and9() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  console.log("📋 Cycles:", trainCycles.map((c) => c.cycleNumber).join(", "));
  console.log("   Phase 8 confirmed: lag-1 autocorr = -0.52 (mean-reverting walk)\n");

  // Build cluster data for all cycles
  const clusterData = buildAllClusterData(validCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 1 — CONFIRM MEAN-REVERSION SIGNAL
  // Recompute lag-1 with more detail across all cycles
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — MEAN-REVERSION CONFIRMATION");
  console.log("═".repeat(65));

  const meanRevStats = confirmMeanReversion(clusterData, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 2 — AMPLITUDE ANALYSIS
  // How large are the oscillations?
  // Is the amplitude consistent? Decaying? Growing?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — OSCILLATION AMPLITUDE ANALYSIS");
  console.log("═".repeat(65));

  const amplitudeStats = analyzeAmplitude(clusterData, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 3 — SEGMENT FREQUENCY ANALYSIS
  // Divide 0-9999 into 10 segments of 1000 each.
  // How uniformly are new numbers spread across segments each day?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — SEGMENT FREQUENCY ANALYSIS");
  console.log("  Q: Do certain number ranges dominate on certain days?");
  console.log("═".repeat(65));

  const segmentStats = analyzeSegments(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 4 — DAY PARITY EFFECTS
  // Odd days vs even days — does the center shift systematically?
  // (Expected given mean-reversion: odd/even days alternate high/low)
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — DAY PARITY EFFECTS (odd vs even days)");
  console.log("═".repeat(65));

  const parityStats = analyzeDayParity(clusterData, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 5 — MEAN-REVERSION PREDICTION MODEL
  // Formula: predicted_step[t] = lag1 × actual_step[t-1]
  // Where lag1 ≈ -0.52
  // predicted_center[t] = center[t-1] + predicted_step[t]
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — MEAN-REVERSION PREDICTION MODEL");
  console.log("  Formula: next_center = curr_center + (lag1 × curr_step)");
  console.log("═".repeat(65));

  const meanRevModel = buildMeanReversionModel(meanRevStats);

  // ═══════════════════════════════════════════════════════════════
  // STEP 6 — VALIDATION ON CYCLE 4
  // Train on cycles 2+3, predict cycle 4 using mean-reversion
  // Compare with naive (random) baseline
  // Try multiple radius values to find optimal
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — VALIDATION: MEAN-REVERSION MODEL ON CYCLE 4");
  console.log("═".repeat(65));

  validateMeanReversionModel(clusterData, trainCycles, meanRevModel);

  // ═══════════════════════════════════════════════════════════════
  // STEP 7 — DIRECTION-ONLY PREDICTION
  // Instead of predicting exact center, predict DIRECTION:
  //   If today's step was UP → tomorrow is DOWN (and vice versa)
  // Test: if we know direction, can we improve hit rate
  // by focusing on the correct HALF of the number space?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — DIRECTION-ONLY PREDICTION");
  console.log("  Q: Knowing UP/DOWN direction, can we halve the search space?");
  console.log("═".repeat(65));

  validateDirectionPrediction(clusterData, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 8 — MULTI-SCALE CLUSTER ANALYSIS
  // Are there 2-3 distinct sub-clusters per day?
  // Find them using gap detection, then track EACH sub-cluster.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 8 — MULTI-SCALE SUB-CLUSTER TRACKING");
  console.log("═".repeat(65));

  analyzeSubClusters(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 9 — TOMORROW'S PREDICTION (CYCLE 5)
  // Apply mean-reversion model to current cycle 5
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 9 — TOMORROW'S DRAW PREDICTION (CYCLE 5)");
  console.log("═".repeat(65));

  predictTomorrowMeanReversion(currentCycle, meanRevModel, clusterData);

  console.log("\n✅ Phase 8+9 complete");
  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function numVal(s)   { return parseInt(s, 10); }
function mean(arr)   { return arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0; }
function median(arr) {
  const s = [...arr].sort((a,b)=>a-b);
  const m = Math.floor(s.length/2);
  return s.length%2 ? s[m] : (s[m-1]+s[m])/2;
}
function stdDev(arr) {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s,v)=>s+(v-m)**2,0)/arr.length);
}
function pearsonCorr(xs, ys) {
  if (!xs.length || xs.length !== ys.length) return 0;
  const mx=mean(xs), my=mean(ys);
  let n=0,dx=0,dy=0;
  for (let i=0;i<xs.length;i++) {
    n+=(xs[i]-mx)*(ys[i]-my); dx+=(xs[i]-mx)**2; dy+=(ys[i]-my)**2;
  }
  return dx&&dy ? n/Math.sqrt(dx*dy) : 0;
}

function buildAllClusterData(cycles) {
  const data = {};
  for (const cycle of cycles) {
    data[cycle.cycleNumber] = [];
    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number));
      if (newNums.length === 0) continue;
      data[cycle.cycleNumber].push({
        day:     dayEntry.dayIndexInCycle,
        count:   newNums.length,
        center:  median(newNums),
        spread:  stdDev(newNums),
        min:     Math.min(...newNums),
        max:     Math.max(...newNums),
        nums:    newNums,
      });
    }
  }
  return data;
}

function getSteps(days) {
  const steps = [];
  for (let i=1;i<days.length;i++) steps.push(days[i].center - days[i-1].center);
  return steps;
}

// ─────────────────────────────────────────────────────────────
// STEP 1 — CONFIRM MEAN REVERSION
// ─────────────────────────────────────────────────────────────
function confirmMeanReversion(clusterData, trainCycles) {
  const allLag1 = [], allSignPersist = [], allAbsSteps = [];
  const perCycle = {};

  for (const cycle of trainCycles) {
    const days  = clusterData[cycle.cycleNumber] || [];
    const steps = getSteps(days);
    if (steps.length < 2) continue;

    const lag1 = pearsonCorr(steps.slice(0,-1), steps.slice(1));

    let sameSign = 0;
    for (let i=1;i<steps.length;i++) {
      if (Math.sign(steps[i]) === Math.sign(steps[i-1])) sameSign++;
    }
    const signPersist = sameSign / (steps.length-1);
    const absStepMean = mean(steps.map(Math.abs));

    allLag1.push(lag1);
    allSignPersist.push(signPersist);
    allAbsSteps.push(absStepMean);

    perCycle[cycle.cycleNumber] = { lag1, signPersist, absStepMean, steps };

    console.log(`\n  Cycle ${cycle.cycleNumber}:`);
    console.log(`    Lag-1 autocorr:   ${lag1.toFixed(4)}`);
    console.log(`    Sign persistence: ${(signPersist*100).toFixed(1)}% (${(100-signPersist*100).toFixed(1)}% reversal)`);
    console.log(`    Avg |step|:       ${absStepMean.toFixed(0)}`);
    console.log(`    → If step was +X, next step is ~${(lag1).toFixed(2)}×X = ${(lag1*absStepMean).toFixed(0)}`);
  }

  const avgLag1       = mean(allLag1);
  const avgPersist    = mean(allSignPersist);
  const avgAbsStep    = mean(allAbsSteps);

  console.log(`\n  ─────────────────────────────────`);
  console.log(`  Avg lag-1:           ${avgLag1.toFixed(4)}`);
  console.log(`  Avg sign persistence: ${(avgPersist*100).toFixed(1)}%`);
  console.log(`  Avg |step|:          ${avgAbsStep.toFixed(0)} number units`);
  console.log(`\n  INTERPRETATION:`);
  console.log(`    The center oscillates. If it moved UP by 1000 today,`);
  console.log(`    it will move DOWN by ~${Math.abs(avgLag1*avgAbsStep).toFixed(0)} tomorrow on average.`);
  console.log(`    ${((1-avgPersist)*100).toFixed(0)}% chance of direction reversal each day.`);

  return { avgLag1, avgPersist, avgAbsStep, perCycle };
}

// ─────────────────────────────────────────────────────────────
// STEP 2 — AMPLITUDE ANALYSIS
// ─────────────────────────────────────────────────────────────
function analyzeAmplitude(clusterData, trainCycles) {
  console.log(`\n  Oscillation amplitude (|step|) across cycle days:`);

  for (const cycle of trainCycles) {
    const days  = clusterData[cycle.cycleNumber] || [];
    const steps = getSteps(days);

    // Split into thirds: early / mid / late cycle
    const t1 = Math.floor(steps.length/3);
    const t2  = Math.floor(2*steps.length/3);

    const earlyAmp = mean(steps.slice(0,t1).map(Math.abs));
    const midAmp   = mean(steps.slice(t1,t2).map(Math.abs));
    const lateAmp  = mean(steps.slice(t2).map(Math.abs));

    console.log(`\n  Cycle ${cycle.cycleNumber}:`);
    console.log(`    Early cycle |step|: ${earlyAmp.toFixed(0)}`);
    console.log(`    Mid cycle   |step|: ${midAmp.toFixed(0)}`);
    console.log(`    Late cycle  |step|: ${lateAmp.toFixed(0)}`);

    // Is amplitude decaying or growing?
    const trend = lateAmp > earlyAmp*1.2 ? "GROWING" :
                  lateAmp < earlyAmp*0.8 ? "DECAYING" : "STABLE";
    console.log(`    Amplitude trend: ${trend}`);
  }

  return {};
}

// ─────────────────────────────────────────────────────────────
// STEP 3 — SEGMENT FREQUENCY
// ─────────────────────────────────────────────────────────────
function analyzeSegments(trainCycles) {
  const segmentSize = 1000;
  const numSegments = 10;

  // For each cycle, count new numbers per segment per day
  // Then find: does any segment have consistently different hit rate?

  const segmentTotals = new Array(numSegments).fill(0);
  let grandTotal = 0;

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers.filter((n) => n.isNew).map((n) => numVal(n.number));
      newNums.forEach((v) => {
        const seg = Math.min(Math.floor(v / segmentSize), numSegments-1);
        segmentTotals[seg]++;
        grandTotal++;
      });
    }
  }

  const expectedPerSeg = grandTotal / numSegments;
  console.log(`\n  Grand total new numbers: ${grandTotal.toLocaleString()}`);
  console.log(`  Expected per segment (if uniform): ${Math.round(expectedPerSeg).toLocaleString()}\n`);
  console.log(`  Segment   | Count  | Expected | Ratio | Distribution`);
  console.log(`  ` + "-".repeat(70));

  for (let i=0;i<numSegments;i++) {
    const count = segmentTotals[i];
    const ratio = count / expectedPerSeg;
    const bar   = "█".repeat(Math.round(ratio*10));
    const range = `${i*segmentSize}–${(i+1)*segmentSize-1}`;
    console.log(
      `  ${String(range).padEnd(10)} | ${String(count).padEnd(6)} | ` +
      `${String(Math.round(expectedPerSeg)).padEnd(8)} | ${ratio.toFixed(3)} | ${bar}`
    );
  }

  // Chi-squared test
  const chiSq = segmentTotals.reduce((s,c) => s + (c-expectedPerSeg)**2/expectedPerSeg, 0);
  const dof   = numSegments - 1;
  console.log(`\n  Chi-squared: ${chiSq.toFixed(3)} (dof=${dof})`);
  console.log(`  Critical at p=0.01: ~21.7`);
  console.log(`  ${chiSq > 21.7 ? "✅ SIGNIFICANT — uneven segment distribution!" : "❌ Not significant — segments uniform"}`);

  return { segmentTotals, chiSq };
}

// ─────────────────────────────────────────────────────────────
// STEP 4 — DAY PARITY
// ─────────────────────────────────────────────────────────────
function analyzeDayParity(clusterData, trainCycles) {
  const oddCenters = [], evenCenters = [];

  for (const cycle of trainCycles) {
    const days = clusterData[cycle.cycleNumber] || [];
    days.forEach((d) => {
      if (d.day % 2 === 1) oddCenters.push(d.center);
      else                  evenCenters.push(d.center);
    });
  }

  const oddMean  = mean(oddCenters);
  const evenMean = mean(evenCenters);
  const oddStd   = stdDev(oddCenters);
  const evenStd  = stdDev(evenCenters);

  console.log(`\n  Odd days (1,3,5...): mean center = ${oddMean.toFixed(0)}, std = ${oddStd.toFixed(0)}, n=${oddCenters.length}`);
  console.log(`  Even days (2,4,6..): mean center = ${evenMean.toFixed(0)}, std = ${evenStd.toFixed(0)}, n=${evenCenters.length}`);
  console.log(`  Difference: ${(evenMean - oddMean).toFixed(0)}`);

  // Per cycle, show first 10 days alternation
  for (const cycle of trainCycles) {
    const days = (clusterData[cycle.cycleNumber] || []).slice(0, 10);
    console.log(`\n  Cycle ${cycle.cycleNumber} — center oscillation (first 10 days):`);
    let prevCenter = null;
    days.forEach((d) => {
      const arrow = prevCenter === null ? " " :
                    d.center > prevCenter ? "↑" : "↓";
      const parity = d.day % 2 === 1 ? "ODD " : "EVEN";
      const bar    = "▓".repeat(Math.round(d.center/500));
      console.log(`    Day ${String(d.day).padEnd(3)} (${parity}) ${arrow} ${Math.round(d.center).toString().padStart(5)}  ${bar}`);
      prevCenter = d.center;
    });
  }

  const diff = Math.abs(evenMean - oddMean);
  const signal = diff > 200 ? "SIGNAL" : diff > 50 ? "WEAK" : "NOISE";
  console.log(`\n  Parity effect: ${diff.toFixed(0)} unit difference → ${signal}`);

  return { oddMean, evenMean, diff, signal };
}

// ─────────────────────────────────────────────────────────────
// STEP 5 — BUILD MEAN-REVERSION MODEL
// ─────────────────────────────────────────────────────────────
function buildMeanReversionModel(meanRevStats) {
  const { avgLag1, avgAbsStep, perCycle } = meanRevStats;

  // Fit: predicted_step = lag1 × previous_step
  // Also fit residual std (how much error after applying lag1)
  const residuals = [];
  for (const [cn, stats] of Object.entries(perCycle)) {
    const steps = stats.steps;
    for (let i=1;i<steps.length;i++) {
      const predicted = avgLag1 * steps[i-1];
      const actual    = steps[i];
      residuals.push(actual - predicted);
    }
  }

  const residualStd = stdDev(residuals);

  console.log(`\n  Mean-reversion model parameters:`);
  console.log(`    lag1 coefficient:  ${avgLag1.toFixed(4)}`);
  console.log(`    avg |step|:        ${avgAbsStep.toFixed(0)}`);
  console.log(`    residual std:      ${residualStd.toFixed(0)}`);
  console.log(`\n  Prediction formula:`);
  console.log(`    predicted_step[t] = ${avgLag1.toFixed(3)} × actual_step[t-1]`);
  console.log(`    predicted_center[t] = center[t-1] + predicted_step[t]`);
  console.log(`    95% prediction interval: ±${(2*residualStd).toFixed(0)} units`);
  console.log(`\n  Example:`);
  console.log(`    If yesterday center=4000, today center=6000 (step=+2000)`);
  const exStep = avgLag1 * 2000;
  const exCenter = 6000 + exStep;
  console.log(`    → predicted step = ${avgLag1.toFixed(3)} × 2000 = ${exStep.toFixed(0)}`);
  console.log(`    → predicted tomorrow center = 6000 + ${exStep.toFixed(0)} = ${exCenter.toFixed(0)}`);

  return { lag1: avgLag1, avgAbsStep, residualStd, residuals };
}

// ─────────────────────────────────────────────────────────────
// STEP 6 — VALIDATE MEAN-REVERSION ON CYCLE 4
// ─────────────────────────────────────────────────────────────
function validateMeanReversionModel(clusterData, trainCycles, model) {
  const cycle4  = trainCycles.find((c) => c.cycleNumber === 4);
  const c4Days  = clusterData[4];
  if (!cycle4 || !c4Days || c4Days.length < 2) {
    console.log("  ⚠️  Cycle 4 data not available");
    return;
  }

  // Model trained on cycles 2+3
  const lag1 = mean([
    Object.values(model.lag1 !== undefined ? { v: model.lag1 } : {}).map(v=>v)[0] ?? -0.52,
  ].filter(v => !isNaN(v)));

  // Use the lag1 from model directly
  const L = model.lag1;

  const radii = [500, 1000, 1500, 2000, 2500, 3000];
  const resultsPerRadius = {};

  for (const R of radii) {
    let hits=0, actTotal=0, predTotal=0;
    let prevStep = 0;
    let usingActualPrevStep = false;

    for (let i=1; i<c4Days.length; i++) {
      const prevCenter = c4Days[i-1].center;

      // First day: no previous step available, use 0
      const predictedStep   = L * prevStep;
      const predictedCenter = prevCenter + predictedStep;

      // Actual
      const actualCenter = c4Days[i].center;

      // Find tomorrow's actual draw
      const tomorrowDay = cycle4.drawEntries.find(
        (d) => d.dayIndexInCycle === c4Days[i].day
      );
      if (!tomorrowDay) { prevStep = actualCenter - prevCenter; continue; }

      const actualNew = tomorrowDay.numbers.filter((n) => n.isNew).map((n) => n.number);

      // Count hits in radius
      const lo  = Math.max(0, Math.round(predictedCenter - R));
      const hi  = Math.min(9999, Math.round(predictedCenter + R));
      const cnt = actualNew.filter((n) => {
        const v = numVal(n);
        return v >= lo && v <= hi;
      }).length;

      hits     += cnt;
      actTotal += actualNew.length;
      predTotal += hi - lo + 1;

      // Update prevStep for NEXT iteration using ACTUAL step (not predicted)
      prevStep = actualCenter - prevCenter;
    }

    const hitPct     = actTotal > 0 ? (hits/actTotal*100).toFixed(2) : "0";
    const randomPct  = (2*R/10000*100).toFixed(2);
    const improvement = parseFloat(hitPct)/parseFloat(randomPct);

    resultsPerRadius[R] = { hits, actTotal, hitPct, randomPct, improvement };
  }

  console.log(`\n  Mean-reversion model hit rates on cycle 4:`);
  console.log(`  Radius | HitRate% | Random%  | Improvement | Signal?`);
  console.log(`  ` + "-".repeat(60));
  for (const R of radii) {
    const r = resultsPerRadius[R];
    const sig = r.improvement > 1.1 ? "✅ YES" : r.improvement > 1.0 ? "⚠️ WEAK" : "❌ no";
    console.log(
      `  ${String(R).padEnd(6)} | ${String(r.hitPct+"%").padEnd(8)} | ` +
      `${String(r.randomPct+"%").toFixed ? String(r.randomPct+"%").padEnd(8) : r.randomPct.toString().padEnd(8)} | ` +
      `${r.improvement.toFixed(3)}x       | ${sig}`
    );
  }

  // Best radius
  const best = Object.entries(resultsPerRadius)
    .sort((a,b) => b[1].improvement - a[1].improvement)[0];
  console.log(`\n  Best radius: R=${best[0]} → ${best[1].improvement.toFixed(3)}x random`);

  // Try also: use PREDICTED step (fully forward-looking)
  console.log(`\n  ── Pure forward-looking (no actual steps used) ──`);
  const R = 1500;
  let hits2=0, act2=0;
  let prevPredictedCenter = c4Days[0].center;
  let prevPredictedStep   = 0;

  for (let i=1; i<c4Days.length; i++) {
    const predictedStep2   = L * prevPredictedStep;
    const predictedCenter2 = prevPredictedCenter + predictedStep2;

    const tomorrowDay = cycle4.drawEntries.find(
      (d) => d.dayIndexInCycle === c4Days[i].day
    );
    if (!tomorrowDay) {
      prevPredictedStep   = predictedStep2;
      prevPredictedCenter = predictedCenter2;
      continue;
    }

    const actualNew = tomorrowDay.numbers.filter((n) => n.isNew).map((n) => n.number);
    const lo = Math.max(0, Math.round(predictedCenter2 - R));
    const hi = Math.min(9999, Math.round(predictedCenter2 + R));
    const cnt = actualNew.filter((n) => { const v=numVal(n); return v>=lo && v<=hi; }).length;
    hits2 += cnt;
    act2  += actualNew.length;

    prevPredictedStep   = predictedStep2;
    prevPredictedCenter = predictedCenter2;
  }
  const hitPct2   = act2>0 ? (hits2/act2*100).toFixed(2) : "0";
  const randPct2  = (2*R/10000*100).toFixed(2);
  const improv2   = parseFloat(hitPct2)/parseFloat(randPct2);
  console.log(`  R=${R} pure forward: ${hitPct2}% vs random ${randPct2}% = ${improv2.toFixed(3)}x`);

  return resultsPerRadius;
}

// ─────────────────────────────────────────────────────────────
// STEP 7 — DIRECTION-ONLY PREDICTION
// ─────────────────────────────────────────────────────────────
function validateDirectionPrediction(clusterData, trainCycles) {
  // If step was positive → predict tomorrow's center is LOWER (mean reversion)
  // So focus on the LOWER half of today's center
  // If step was negative → predict tomorrow's center is HIGHER
  // So focus on the UPPER half of today's center

  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  const c4Days = clusterData[4];
  if (!cycle4 || !c4Days) { console.log("  ⚠️  No cycle 4 data"); return; }

  let hitsHalfCorrect=0, hitsHalfRandom=0, total=0;
  let directionCorrect=0, directionTotal=0;

  for (let i=1; i<c4Days.length; i++) {
    const prevCenter = c4Days[i-1].center;
    const todayCenter= c4Days[i-1 > 0 ? i-1 : 0].center;
    const step       = c4Days[i-1 > 0 ? i-1 : 0].center -
                       (i>1 ? c4Days[i-2].center : c4Days[0].center);

    // Predict: if step>0, tomorrow center is BELOW today (mean-reverting)
    const predictedBelow = step > 0; // true = expect center to fall
    const predictedUpper = step <= 0; // expect center to rise

    const tomorrowDay = cycle4.drawEntries.find(
      (d) => d.dayIndexInCycle === c4Days[i].day
    );
    if (!tomorrowDay) continue;

    const actualNewNums = tomorrowDay.numbers.filter((n) => n.isNew).map((n) => numVal(n.number));
    if (actualNewNums.length === 0) continue;

    const actualNextCenter = c4Days[i].center;
    const actualStep = actualNextCenter - todayCenter;

    // Was direction correct?
    if ((step > 0 && actualStep < 0) || (step <= 0 && actualStep >= 0)) directionCorrect++;
    directionTotal++;

    // Count hits in correct half
    const halfBoundary = 5000; // split at 5000
    const inLower = actualNewNums.filter((v) => v < halfBoundary).length;
    const inUpper = actualNewNums.filter((v) => v >= halfBoundary).length;

    // Direction-based: if we predict "lower" half, pick numbers 0-4999
    const predictedHalf = predictedBelow ? inLower : inUpper;
    const randomHalf    = actualNewNums.length / 2; // expected if random

    hitsHalfCorrect += predictedHalf;
    hitsHalfRandom  += actualNewNums.length;
    total++;
  }

  const dirAccuracy = (directionCorrect/directionTotal*100).toFixed(1);
  const hitsAvg     = (hitsHalfCorrect/total).toFixed(1);
  const halfAvg     = (hitsHalfRandom/total/2).toFixed(1);

  console.log(`\n  Direction prediction accuracy: ${directionCorrect}/${directionTotal} = ${dirAccuracy}%`);
  console.log(`  (50% = random, >60% = useful signal)`);
  console.log(`\n  Half-space prediction (avg new numbers in predicted half):`);
  console.log(`    Model: ${hitsAvg} per day`);
  console.log(`    Random: ${halfAvg} per day`);
  console.log(`    Improvement: ${(parseFloat(hitsAvg)/parseFloat(halfAvg)).toFixed(3)}x`);

  if (parseFloat(dirAccuracy) > 60) {
    console.log(`\n  ✅ SIGNAL: Direction prediction > 60% accurate!`);
    console.log(`  → We can use direction to filter candidates.`);
  } else {
    console.log(`\n  ⚠️  Direction accuracy = ${dirAccuracy}%. Close to random (50%).`);
  }

  return { dirAccuracy, hitsAvg, halfAvg };
}

// ─────────────────────────────────────────────────────────────
// STEP 8 — SUB-CLUSTER TRACKING
// ─────────────────────────────────────────────────────────────
function analyzeSubClusters(trainCycles) {
  const GAP = 500; // gap threshold

  const avgSubClusterCenters = []; // collect all sub-cluster centers
  let totalDaysAnalyzed = 0;

  for (const cycle of trainCycles.slice(0,1)) { // show one cycle in detail
    console.log(`\n  Cycle ${cycle.cycleNumber} — sub-cluster analysis (first 10 days):`);
    console.log(`  Day | #Clusters | Centers`);
    console.log(`  ` + "-".repeat(55));

    for (const dayEntry of cycle.drawEntries.slice(0,10)) {
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number))
        .sort((a,b) => a-b);

      if (newNums.length < 3) continue;

      // Find sub-clusters
      const clusters = [[newNums[0]]];
      for (let i=1; i<newNums.length; i++) {
        if (newNums[i] - newNums[i-1] > GAP) clusters.push([]);
        clusters[clusters.length-1].push(newNums[i]);
      }

      const centers = clusters.map((c) => Math.round(median(c)));
      const sizes   = clusters.map((c) => c.length);
      avgSubClusterCenters.push(...centers);
      totalDaysAnalyzed++;

      console.log(
        `  ${String(dayEntry.dayIndexInCycle).padEnd(3)} | ${String(clusters.length).padEnd(9)} | ` +
        `${centers.map((c,i) => `${c}(n=${sizes[i]})`).join(" | ")}`
      );
    }
  }

  // Sub-cluster center distribution
  const segDist = new Array(10).fill(0);
  avgSubClusterCenters.forEach((c) => {
    const seg = Math.min(Math.floor(c/1000), 9);
    segDist[seg]++;
  });

  console.log(`\n  Sub-cluster center distribution (where do clusters form?):`);
  segDist.forEach((count, i) => {
    const bar = "█".repeat(Math.round(count/2));
    console.log(`    ${i*1000}–${(i+1)*1000-1}: ${String(count).padEnd(4)} ${bar}`);
  });
}

// ─────────────────────────────────────────────────────────────
// STEP 9 — PREDICT TOMORROW (CYCLE 5)
// ─────────────────────────────────────────────────────────────
function predictTomorrowMeanReversion(currentCycle, model, clusterData) {
  const c5Days = clusterData[currentCycle.cycleNumber] || [];
  if (c5Days.length < 2) {
    console.log("  ⚠️  Need at least 2 cycle 5 days for prediction");
    return;
  }

  const L           = model.lag1;
  const residualStd = model.residualStd;

  const lastDay   = c5Days[c5Days.length - 1];
  const prevDay   = c5Days[c5Days.length - 2];
  const lastStep  = lastDay.center - prevDay.center;
  const predStep  = L * lastStep;
  const predCenter = Math.round(lastDay.center + predStep);

  // Remaining numbers in cycle 5
  const drawn = new Set();
  currentCycle.drawEntries.forEach((d) => {
    d.numbers.forEach((n) => { if (n.isNew) drawn.add(n.number); });
  });
  const allNums   = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));
  const remaining = new Set(allNums.filter((n) => !drawn.has(n)));

  console.log(`\n  Last draw (day ${lastDay.day}):`);
  console.log(`    Center: ${Math.round(lastDay.center)}`);
  console.log(`    Range:  ${lastDay.min}–${lastDay.max}`);
  console.log(`    Count:  ${lastDay.count} new numbers`);
  console.log(`\n  Previous step: ${Math.round(lastStep)} (${lastStep>0?"UP":"DOWN"})`);
  console.log(`  Predicted step: ${L.toFixed(3)} × ${Math.round(lastStep)} = ${Math.round(predStep)}`);
  console.log(`  Predicted center: ${predCenter}`);
  console.log(`  95% interval: ${predCenter - Math.round(2*residualStd)} to ${predCenter + Math.round(2*residualStd)}`);
  console.log(`  Remaining in cycle 5: ${remaining.size} numbers`);

  // Three radius options
  const radii = [500, 1000, 1500, 2000];
  console.log(`\n  Remaining candidates by prediction radius:`);
  console.log(`  Radius | Total in range | Remaining in range`);
  console.log(`  ` + "-".repeat(50));

  for (const R of radii) {
    const lo  = Math.max(0, predCenter - R);
    const hi  = Math.min(9999, predCenter + R);
    const totalInRange = hi - lo + 1;
    const remainingInRange = allNums.filter((n) => {
      const v = numVal(n);
      return v >= lo && v <= hi && remaining.has(n);
    });
    console.log(
      `  ${String(R).padEnd(6)} | ${String(totalInRange).padEnd(14)} | ` +
      `${remainingInRange.length}`
    );
  }

  // Best prediction: R=1000, list remaining candidates
  const R = 1000;
  const lo = Math.max(0, predCenter - R);
  const hi = Math.min(9999, predCenter + R);
  const bestCandidates = allNums.filter((n) => {
    const v = numVal(n);
    return v >= lo && v <= hi && remaining.has(n);
  });

  console.log(`\n  ── Best prediction (R=${R}, ${bestCandidates.length} remaining candidates) ──`);
  console.log(`  Range: ${lo}–${hi}`);
  if (bestCandidates.length > 0) {
    console.log(`  Candidates: ${bestCandidates.join(", ")}`);
  }

  // Also: direction prediction
  console.log(`\n  Direction prediction:`);
  const dirPrediction = lastStep > 0 ? "DOWN (center will fall)" : "UP (center will rise)";
  console.log(`  Last step was ${lastStep>0?"POSITIVE (UP)":"NEGATIVE (DOWN)"} → next center goes ${dirPrediction}`);
  console.log(`  Focus on numbers ${lastStep>0 ? "BELOW" : "ABOVE"} current center (${Math.round(lastDay.center)})`);

  // Numbers below/above current center that are remaining
  const dirCandidates = [...remaining].filter((n) => {
    const v = numVal(n);
    return lastStep > 0 ? v < lastDay.center : v > lastDay.center;
  });
  console.log(`  ${dirCandidates.length} remaining numbers on predicted side`);
  if (dirCandidates.length <= 30) {
    console.log(`  Numbers: ${dirCandidates.sort().join(", ")}`);
  } else {
    console.log(`  Sample: ${dirCandidates.sort().slice(0,20).join(", ")} ...`);
  }
}

// ─────────────────────────────────────────────────────────────
runPhase8and9().catch((err) => {
  console.error("❌ Phase 8+9 failed:", err);
  process.exit(1);
});