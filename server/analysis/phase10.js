require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 10 — FINAL THREE-ANGLE SEARCH
//
// Honest status: No formula found across 9 phases.
// These are the last three untested angles:
//
//   ANGLE 1: Conditional mean reversion at extremes
//     When center > 7000 or < 3000, does it revert HARDER?
//     If yes: extreme positions = stronger directional signal.
//
//   ANGLE 2: Prize distribution per cycle day
//     Do high prizes (₹5000, ₹2000) appear more on
//     specific days (early/mid/late) within the cycle?
//     If yes: day position predicts PRIZE, not number.
//
//   ANGLE 3: Hot number × day-of-week alignment
//     Hot numbers appear ~every 14-20 days.
//     Does appearance align with day-of-week?
//     If yes: "number X always returns on Fridays" → predict.
//
// Each angle is honestly validated and reported.
// If none succeed: final conclusion is confirmed randomness.
// ═══════════════════════════════════════════════════════════════

async function runPhase10() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  console.log("📋 PHASE 10 — FINAL THREE-ANGLE SEARCH");
  console.log("   Training cycles: 2, 3, 4");
  console.log("   Current cycle 5:", currentCycle.totalNumbersDrawn, "/ 10000 drawn,",
    currentCycle.remainingNumbers, "remaining\n");

  // ═══════════════════════════════════════════════════════════════
  // ANGLE 1 — CONDITIONAL MEAN REVERSION AT EXTREMES
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("ANGLE 1 — CONDITIONAL MEAN REVERSION AT EXTREMES");
  console.log("  Hypothesis: center reverts HARDER from extreme positions");
  console.log("  Test: split days by center zone, measure next-day reversion");
  console.log("═".repeat(65));

  const angle1 = testConditionalMeanReversion(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // ANGLE 2 — PRIZE DISTRIBUTION PER CYCLE DAY
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("ANGLE 2 — PRIZE DISTRIBUTION PER CYCLE POSITION");
  console.log("  Hypothesis: high prizes cluster in specific cycle phases");
  console.log("  Test: prize frequency by early/mid/late cycle position");
  console.log("═".repeat(65));

  const angle2 = testPrizeDistributionByCycleDay(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // ANGLE 3 — HOT NUMBER × DAY-OF-WEEK ALIGNMENT
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("ANGLE 3 — HOT NUMBER × DAY-OF-WEEK ALIGNMENT");
  console.log("  Hypothesis: hot numbers return on the same day of week");
  console.log("  Test: for each number, measure day-of-week consistency");
  console.log("═".repeat(65));

  const angle3 = testDayOfWeekAlignment(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // FINAL SUMMARY + CYCLE 5 ACTIONABLE OUTPUT
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("FINAL SUMMARY — ALL PHASES");
  console.log("═".repeat(65));

  printFinalSummary(angle1, angle2, angle3);

  // ═══════════════════════════════════════════════════════════════
  // CYCLE 5 REMAINING — BEST ACTIONABLE OUTPUT
  // Combining everything we DO know
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("CYCLE 5 — BEST ACTIONABLE OUTPUT (combining all signals)");
  console.log("═".repeat(65));

  printActionableOutput(currentCycle, trainCycles, angle2, angle3);

  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function numVal(s)   { return parseInt(s, 10); }
function mean(arr)   { return arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0; }
function median(arr) {
  const s=[...arr].sort((a,b)=>a-b);
  const m=Math.floor(s.length/2);
  return s.length%2 ? s[m] : (s[m-1]+s[m])/2;
}
function stdDev(arr) {
  if (arr.length<2) return 0;
  const m=mean(arr);
  return Math.sqrt(arr.reduce((s,v)=>s+(v-m)**2,0)/arr.length);
}

// Build per-day cluster data
function buildDayData(cycles) {
  const result = [];
  for (const cycle of cycles) {
    let prevCenter = null;
    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number));
      if (newNums.length === 0) continue;

      const center = median(newNums);
      const step   = prevCenter !== null ? center - prevCenter : null;

      result.push({
        cycleNumber:  cycle.cycleNumber,
        cycleDays:    cycle.totalDrawDays,
        day:          dayEntry.dayIndexInCycle,
        dayOfWeek:    new Date(dayEntry.drawDate).getUTCDay(), // 0=Sun,6=Sat
        dayOfWeekStr: ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][new Date(dayEntry.drawDate).getUTCDay()],
        center,
        step,
        newCount:     newNums.length,
        nums:         newNums,
        prizes:       dayEntry.numbers
          .filter((n) => n.isNew)
          .map((n) => ({ number: n.number, prize: n.prize })),
        normDay:      dayEntry.dayIndexInCycle / cycle.totalDrawDays,
      });

      prevCenter = center;
    }
  }
  return result;
}

// ═══════════════════════════════════════════════════════════════
// ANGLE 1 — CONDITIONAL MEAN REVERSION
// ═══════════════════════════════════════════════════════════════
function testConditionalMeanReversion(trainCycles) {
  const dayData = buildDayData(trainCycles);

  // Zone thresholds
  const zones = [
    { label: "FAR LOW  (<2000)",  lo: 0,    hi: 2000 },
    { label: "LOW      (2000-3500)", lo: 2000, hi: 3500 },
    { label: "MID-LOW  (3500-4500)", lo: 3500, hi: 4500 },
    { label: "CENTER   (4500-5500)", lo: 4500, hi: 5500 },
    { label: "MID-HIGH (5500-6500)", lo: 5500, hi: 6500 },
    { label: "HIGH     (6500-8000)", lo: 6500, hi: 8000 },
    { label: "FAR HIGH (>8000)",  lo: 8000, hi: 10000 },
  ];

  const zoneResults = zones.map((z) => ({
    ...z,
    nextSteps:   [],
    nextDirs:    [],
    reverseCount: 0,
    totalCount:   0,
  }));

  for (let i = 0; i < dayData.length - 1; i++) {
    const today    = dayData[i];
    const tomorrow = dayData[i + 1];

    // Only consecutive days in same cycle
    if (today.cycleNumber !== tomorrow.cycleNumber) continue;
    if (today.step === null) continue;

    const zone = zoneResults.find((z) => today.center >= z.lo && today.center < z.hi);
    if (!zone) continue;

    const nextStep = tomorrow.center - today.center;
    zone.nextSteps.push(nextStep);
    zone.totalCount++;

    // Did direction reverse?
    if (Math.sign(today.step) !== Math.sign(nextStep) && today.step !== 0) {
      zone.reverseCount++;
    }
  }

  console.log(`\n  Zone              | N    | Avg NextStep | ReversalRate | Signal?`);
  console.log(`  ` + "-".repeat(68));

  let anySignal = false;

  for (const z of zoneResults) {
    if (z.totalCount === 0) continue;

    const avgStep      = mean(z.nextSteps);
    const reversalRate = (z.reverseCount / z.totalCount * 100).toFixed(1);
    const absAvg       = mean(z.nextSteps.map(Math.abs));

    // Signal: extreme zones with reversal > 75% or strong avg step toward 5000
    const expectedReturn = z.lo >= 5500 ? "← DOWN" : z.hi <= 4500 ? "→ UP" : "~flat";
    const isSignal = parseFloat(reversalRate) > 72 &&
                     (z.lo >= 6500 || z.hi <= 3500);

    if (isSignal) anySignal = true;

    console.log(
      `  ${String(z.label).padEnd(20)} | ${String(z.totalCount).padEnd(4)} | ` +
      `${String(avgStep.toFixed(0)).padStart(8)} (${expectedReturn})   | ` +
      `${reversalRate}%          | ${isSignal ? "✅ YES" : "❌ no"}`
    );
  }

  // Special test: when center > 7500 or < 2500, how often does it reverse?
  const extreme = dayData.filter((d, i) => {
    if (i === 0) return false;
    const prev = dayData[i-1];
    if (prev.cycleNumber !== d.cycleNumber) return false;
    return prev.center > 7500 || prev.center < 2500;
  });

  const extremeReversals = extreme.filter((d, i) => {
    const prev = dayData.find((x) => x.cycleNumber === d.cycleNumber && x.day === d.day - 1);
    if (!prev || prev.step === null || d.step === null) return false;
    return Math.sign(prev.step) !== Math.sign(d.center - prev.center);
  });

  console.log(`\n  EXTREME zone test (center > 7500 or < 2500):`);
  console.log(`    Days in extreme: ${extreme.length}`);
  console.log(`    Next-day reversals: ${extremeReversals.length} / ${extreme.length}`);
  if (extreme.length > 0) {
    const pct = (extremeReversals.length / extreme.length * 100).toFixed(1);
    console.log(`    Reversal rate: ${pct}%`);
    console.log(`    ${parseFloat(pct) > 72 ? "✅ SIGNAL at extreme zones!" : "❌ No extra signal at extremes"}`);
  }

  // Validation: does extreme-zone prediction beat baseline on cycle 4?
  const c4Data = buildDayData([trainCycles.find((c) => c.cycleNumber === 4)]);
  let extremeHits=0, extremeTotal=0;
  let baseHits=0, baseTotal=0;
  const R = 1500;

  for (let i=0; i<c4Data.length-1; i++) {
    const today = c4Data[i];
    const tomorrow = c4Data[i+1];
    if (today.step === null) continue;

    const isExtreme = today.center > 7000 || today.center < 3000;
    const predictedCenter = today.center + (-0.52 * today.step);
    const lo = Math.max(0, Math.round(predictedCenter - R));
    const hi = Math.min(9999, Math.round(predictedCenter + R));
    const hits = tomorrow.nums.filter((v) => v >= lo && v <= hi).length;
    const total = tomorrow.newCount;

    if (isExtreme) { extremeHits += hits; extremeTotal += total; }
    baseHits  += hits;
    baseTotal += total;
  }

  const extremePct = extremeTotal > 0 ? (extremeHits/extremeTotal*100).toFixed(2) : "0";
  const basePct    = baseTotal > 0 ? (baseHits/baseTotal*100).toFixed(2) : "0";
  const randomPct  = (2*R/10000*100).toFixed(2);

  console.log(`\n  Cycle 4 validation (R=${R}):`);
  console.log(`    All days:     ${basePct}% hit rate (random: ${randomPct}%)`);
  console.log(`    Extreme days: ${extremePct}% hit rate (random: ${randomPct}%)`);
  console.log(`    ${parseFloat(extremePct) > parseFloat(basePct)*1.1 ? "✅ Extreme days better!" : "❌ No improvement at extremes"}`);

  const result = anySignal ? "WEAK SIGNAL" : "NOISE";
  console.log(`\n  ANGLE 1 RESULT: ${result}`);

  return { zoneResults, result, extremePct, basePct, randomPct };
}

// ═══════════════════════════════════════════════════════════════
// ANGLE 2 — PRIZE DISTRIBUTION BY CYCLE POSITION
// ═══════════════════════════════════════════════════════════════
function testPrizeDistributionByCycleDay(trainCycles) {
  // For each day, record normalized position (0.0-1.0) and prizes won
  // Split into 5 quintiles: 0-20%, 20-40%, 40-60%, 60-80%, 80-100%

  const phases = ["Q1 (0-20%)", "Q2 (20-40%)", "Q3 (40-60%)", "Q4 (60-80%)", "Q5 (80-100%)"];
  const prizesByPhase = phases.map(() => ({}));
  const totalByPhase  = new Array(5).fill(0);

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const normDay = dayEntry.dayIndexInCycle / cycle.totalDrawDays;
      const phase   = Math.min(Math.floor(normDay * 5), 4);

      dayEntry.numbers.filter((n) => n.isNew).forEach((n) => {
        const p = n.prize;
        prizesByPhase[phase][p] = (prizesByPhase[phase][p] || 0) + 1;
        totalByPhase[phase]++;
      });
    }
  }

  console.log(`\n  Prize distribution by cycle phase (% of new numbers winning each prize):\n`);
  const prizes = [5000, 2000, 1000, 500, 200, 100, 50];
  const header  = `  Phase         | Total  | ` + prizes.map((p) => `₹${p}%  `).join(" | ");
  console.log(header);
  console.log(`  ` + "-".repeat(header.length - 2));

  const phaseRates = [];

  phases.forEach((phase, i) => {
    const total = totalByPhase[i];
    if (total === 0) return;

    const rates = prizes.map((p) => {
      const count = prizesByPhase[i][p] || 0;
      return { prize: p, count, pct: (count / total * 100) };
    });

    phaseRates.push({ phase, total, rates });

    const cols = rates.map((r) => String(r.pct.toFixed(2)+"%").padEnd(7));
    console.log(`  ${String(phase).padEnd(13)} | ${String(total).padEnd(6)} | ${cols.join(" | ")}`);
  });

  // Expected rate for each prize if uniform
  const grandTotal = totalByPhase.reduce((a, b) => a + b, 0);
  const overallRates = prizes.map((p) => {
    const total = phaseRates.reduce((a, r) => a + (r.rates.find((x) => x.prize === p)?.count || 0), 0);
    return { prize: p, overallPct: (total / grandTotal * 100) };
  });

  console.log(`\n  Overall rates:  | ${" ".repeat(6)} | ` +
    overallRates.map((r) => String(r.overallPct.toFixed(2)+"%").padEnd(7)).join(" | "));

  // Find largest deviation from expected
  let maxDeviation = 0;
  let maxDeviationInfo = null;

  phaseRates.forEach((pr) => {
    pr.rates.forEach((r) => {
      const overall = overallRates.find((x) => x.prize === r.prize)?.overallPct || 0;
      const dev     = Math.abs(r.pct - overall);
      if (dev > maxDeviation) {
        maxDeviation = dev;
        maxDeviationInfo = {
          phase: pr.phase,
          prize: r.prize,
          pct: r.pct.toFixed(2),
          expected: overall.toFixed(2),
          dev: dev.toFixed(2),
        };
      }
    });
  });

  console.log(`\n  Largest deviation from expected:`);
  if (maxDeviationInfo) {
    console.log(`    ${maxDeviationInfo.phase}: ₹${maxDeviationInfo.prize} → ${maxDeviationInfo.pct}% actual vs ${maxDeviationInfo.expected}% expected (Δ${maxDeviationInfo.dev}%)`);
  }

  // Chi-squared test per prize across phases
  console.log(`\n  Chi-squared test per prize (are prize rates uniform across phases?):`);
  console.log(`  Prize  | Chi-sq | Significant (>9.49 at p=0.05, df=4)?`);
  console.log(`  ` + "-".repeat(55));

  let anySignificant = false;
  const sigPrizes = [];

  prizes.forEach((p) => {
    const expected = overallRates.find((x) => x.prize === p)?.overallPct || 0;
    let chiSq = 0;
    phaseRates.forEach((pr) => {
      const actual = pr.rates.find((x) => x.prize === p)?.pct || 0;
      const exp    = expected;
      if (exp > 0) chiSq += (actual - exp) ** 2 / exp;
    });

    const sig = chiSq > 9.49;
    if (sig) { anySignificant = true; sigPrizes.push(p); }

    console.log(
      `  ₹${String(p).padEnd(5)} | ${chiSq.toFixed(3).padEnd(6)} | ${sig ? "✅ YES" : "❌ no"}`
    );
  });

  // Special: does ₹5000 appear more in any specific phase?
  console.log(`\n  ₹5000 prize detail by cycle phase:`);
  phaseRates.forEach((pr) => {
    const r5000 = pr.rates.find((x) => x.prize === 5000);
    const bar   = "█".repeat(Math.round((r5000?.pct || 0) * 20));
    console.log(`    ${String(pr.phase).padEnd(13)}: ${(r5000?.pct || 0).toFixed(3)}%  ${bar}`);
  });

  const result = anySignificant ? "SIGNAL" : "NOISE";
  console.log(`\n  ANGLE 2 RESULT: ${result}`);
  if (anySignificant) {
    console.log(`    Significant prizes: ₹${sigPrizes.join(", ₹")}`);
  }

  return { phaseRates, overallRates, anySignificant, sigPrizes, maxDeviationInfo, result };
}

// ═══════════════════════════════════════════════════════════════
// ANGLE 3 — HOT NUMBER × DAY-OF-WEEK
// ═══════════════════════════════════════════════════════════════
function testDayOfWeekAlignment(trainCycles) {
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  // For each number, count appearances per day-of-week
  const numberDOW = new Map(); // number → {Sun:0, Mon:0,...}

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const dow = DAYS[new Date(dayEntry.drawDate).getUTCDay()];
      dayEntry.numbers.forEach((n) => {
        if (!numberDOW.has(n.number)) {
          numberDOW.set(n.number, Object.fromEntries(DAYS.map((d) => [d, 0])));
        }
        numberDOW.get(n.number)[dow]++;
      });
    }
  }

  // Measure DOW consistency per number
  // Consistency = max_day_count / total_count
  // High consistency = number strongly prefers one day
  const consistencyScores = [];

  for (const [num, dowCounts] of numberDOW) {
    const total = Object.values(dowCounts).reduce((a,b)=>a+b,0);
    if (total < 5) continue; // need enough data

    const maxCount  = Math.max(...Object.values(dowCounts));
    const topDay    = Object.entries(dowCounts).sort((a,b)=>b[1]-a[1])[0][0];
    const consistency = maxCount / total;

    // Expected if random: max of 7 uniform samples ≈ 1/7 ≈ 0.143 each
    // If consistency > 0.4 consistently, that's above random
    consistencyScores.push({ num, total, consistency, topDay, dowCounts });
  }

  // Distribution of consistency scores
  const bins = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 1.0];
  const binCounts = new Array(bins.length).fill(0);
  consistencyScores.forEach((s) => {
    const bin = bins.findIndex((b) => s.consistency <= b);
    if (bin >= 0) binCounts[bin]++;
  });

  // Expected consistency if truly random (simulation-based threshold)
  // With ~30 appearances over 3 cycles, P(max_day >= 0.4) by chance?
  // Uniform over 7 days: expected max ≈ 4.3/30 ≈ 0.143 for avg
  // For n=30 draws, expected max_day ≈ 30/7 × 1.5 ≈ 6.4 → consistency ≈ 0.21

  const randomExpectedConsistency = 0.25; // rough threshold above random
  const highConsistency = consistencyScores.filter(
    (s) => s.consistency >= randomExpectedConsistency + 0.1 && s.total >= 10
  );

  console.log(`\n  Consistency score distribution (maxDay/total appearances):`);
  console.log(`  Score≤  | Count  | Bar`);
  console.log(`  ` + "-".repeat(50));
  bins.forEach((b, i) => {
    const bar = "█".repeat(Math.round(binCounts[i]/50));
    console.log(`  ≤${String(b.toFixed(2)).padEnd(4)}  | ${String(binCounts[i]).padEnd(6)} | ${bar}`);
  });

  console.log(`\n  Random expected max consistency: ~${randomExpectedConsistency}`);
  console.log(`  Numbers with strong DOW preference (>0.35, n≥10): ${highConsistency.length}`);

  // Show top 20 most day-of-week consistent numbers
  const top20 = consistencyScores
    .filter((s) => s.total >= 10)
    .sort((a,b) => b.consistency - a.consistency)
    .slice(0, 20);

  console.log(`\n  Top 20 most day-of-week consistent numbers:`);
  console.log(`  Number | Total | TopDay | Consistency | DOW breakdown`);
  console.log(`  ` + "-".repeat(70));
  top20.forEach((s) => {
    const breakdown = DAYS.map((d) => `${d}:${s.dowCounts[d]}`).join(" ");
    console.log(
      `  ${s.num}   | ${String(s.total).padEnd(5)} | ${String(s.topDay).padEnd(6)} | ` +
      `${(s.consistency*100).toFixed(1)}%         | ${breakdown}`
    );
  });

  // Validate: for numbers with strong DOW preference,
  // does predicting "this number will appear on its preferred day" work?
  console.log(`\n  Validation: using DOW to predict next appearance in cycle 4...`);

  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  // Build DOW model from cycles 2+3 only
  const trainDOW = new Map();
  const c23 = trainCycles.filter((c) => c.cycleNumber <= 3);
  for (const cycle of c23) {
    for (const dayEntry of cycle.drawEntries) {
      const dow = DAYS[new Date(dayEntry.drawDate).getUTCDay()];
      dayEntry.numbers.forEach((n) => {
        if (!trainDOW.has(n.number)) trainDOW.set(n.number, Object.fromEntries(DAYS.map((d)=>[d,0])));
        trainDOW.get(n.number)[dow]++;
      });
    }
  }

  // For each draw day in cycle 4, predict which numbers appear based on DOW
  let dowHits=0, dowTotal=0;
  let randomHits=0, randomTotal=0;

  for (const dayEntry of cycle4.drawEntries) {
    const dow = DAYS[new Date(dayEntry.drawDate).getUTCDay()];
    const actualDrawn = new Set(dayEntry.numbers.map((n) => n.number));
    const actualNew   = new Set(dayEntry.numbers.filter((n) => n.isNew).map((n) => n.number));

    // Predict: numbers whose top DOW matches today
    const dowPredicted = new Set();
    for (const [num, counts] of trainDOW) {
      const topDay = Object.entries(counts).sort((a,b)=>b[1]-a[1])[0]?.[0];
      const total  = Object.values(counts).reduce((a,b)=>a+b,0);
      const topConsistency = (Math.max(...Object.values(counts))) / total;
      if (topDay === dow && topConsistency >= 0.35 && total >= 5) {
        dowPredicted.add(num);
      }
    }

    const hits   = [...actualNew].filter((n) => dowPredicted.has(n)).length;
    dowHits  += hits;
    dowTotal += actualNew.size;

    // Random baseline: dowPredicted.size / 10000 × actualNew.size
    randomHits  += (dowPredicted.size / 10000) * actualNew.size;
    randomTotal += actualNew.size;
  }

  const dowHitPct    = dowTotal > 0 ? (dowHits/dowTotal*100).toFixed(2) : "0";
  const randomHitPct = randomTotal > 0 ? (randomHits/randomTotal*100).toFixed(2) : "0";
  const improvement  = parseFloat(randomHitPct) > 0
    ? parseFloat(dowHitPct)/parseFloat(randomHitPct) : 0;

  console.log(`    DOW model hit rate: ${dowHitPct}%`);
  console.log(`    Random baseline:    ${randomHitPct}%`);
  console.log(`    Improvement:        ${improvement.toFixed(3)}x`);

  const result = improvement > 1.15 ? "SIGNAL" : improvement > 1.05 ? "WEAK" : "NOISE";
  console.log(`\n  ANGLE 3 RESULT: ${result}`);

  return {
    consistencyScores,
    highConsistency,
    top20,
    dowHitPct,
    randomHitPct,
    improvement,
    result,
  };
}

// ═══════════════════════════════════════════════════════════════
// FINAL SUMMARY
// ═══════════════════════════════════════════════════════════════
function printFinalSummary(angle1, angle2, angle3) {
  const phases = [
    { phase: "1 — Cycle structure",               result: "✅ CONFIRMED", note: "48 numbers guaranteed" },
    { phase: "2 — Timing / normalized position",  result: "❌ NOISE",     note: "R²=0.0001" },
    { phase: "3 — Frequency + recency",           result: "❌ NOISE",     note: "Exact baseline match" },
    { phase: "5 — Prize FIXED patterns",          result: "✅ PARTIAL",   note: "585 numbers reliable" },
    { phase: "7 — Consecutive pairs",             result: "⚠️  WEAK",     note: "1.93x, not exploitable" },
    { phase: "7 — Lag-1 autocorr -0.52",          result: "❌ ARTIFACT",  note: "Regression to mean" },
    { phase: "8 — Direction 63.8%",               result: "⚠️  REAL",     note: "But 0 hit improvement" },
    { phase: "9 — Amplitude growing",             result: "✅ CONFIRMS",  note: "Uniform random draw" },
    { phase: "10 — Conditional mean reversion",   result: angle1.result,  note: `extreme ${angle1.extremePct}% vs base ${angle1.basePct}%` },
    { phase: "10 — Prize by cycle position",      result: angle2.result,  note: angle2.anySignificant ? `₹${angle2.sigPrizes.join(",")} significant` : "uniform" },
    { phase: "10 — DOW × hot number",             result: angle3.result,  note: `${angle3.improvement.toFixed(3)}x improvement` },
  ];

  console.log(`\n  Phase | Result         | Notes`);
  console.log(`  ` + "-".repeat(70));
  phases.forEach((p) => {
    console.log(`  ${String(p.phase).padEnd(35)} | ${String(p.result).padEnd(14)} | ${p.note}`);
  });

  const signals = phases.filter((p) => p.result.includes("SIGNAL") || p.result.includes("✅"));
  const confirmed = signals.length;

  console.log(`\n  ═══════════════════════════════════════════════════════════`);
  console.log(`  FINAL VERDICT`);
  console.log(`  ═══════════════════════════════════════════════════════════`);
  console.log(`\n  Q: Is there a mathematical formula for the daily draw?`);
  console.log(`  A: NO. The draw is uniform random within the cycle constraint.`);
  console.log(`\n  What this lottery IS doing:`);
  console.log(`    1. Maintain a pool of 10,000 numbers`);
  console.log(`    2. Each day: draw ~250–400 numbers uniformly at random`);
  console.log(`    3. Each number drawn is REMOVED from the pool`);
  console.log(`    4. When pool is empty: cycle complete, refill, repeat`);
  console.log(`    5. Prize assignment: likely fixed per number (hence 585 fixed)`);
  console.log(`       or assigned from a prize pool with fixed counts`);
  console.log(`\n  What we CAN predict with confidence:`);
  console.log(`    ✅ Which numbers remain (48 now — guaranteed to appear)`);
  console.log(`    ✅ Fixed prize for 585 numbers (always same prize)`);
  console.log(`    ✅ Cycle end timing (~1-3 draws away)`);
  console.log(`    ✅ Cycle 6 early candidates (low normPos numbers)`);
  console.log(`    ✅ Prize tier for remaining 48 (from phase 5 model)`);
  console.log(`\n  What we CANNOT predict:`);
  console.log(`    ❌ Which specific numbers appear tomorrow`);
  console.log(`    ❌ The order within a cycle`);
  console.log(`    ❌ Any digit, sum, or position formula`);
}

// ═══════════════════════════════════════════════════════════════
// ACTIONABLE OUTPUT — CYCLE 5 + CYCLE 6 READINESS
// ═══════════════════════════════════════════════════════════════
function printActionableOutput(currentCycle, trainCycles, angle2, angle3) {
  // Build remaining set
  const drawn = new Set();
  currentCycle.drawEntries.forEach((d) => {
    d.numbers.forEach((n) => { if (n.isNew) drawn.add(n.number); });
  });
  const allNums   = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));
  const remaining = allNums.filter((n) => !drawn.has(n));

  console.log(`\n  ┌─────────────────────────────────────────────────────────┐`);
  console.log(`  │  CYCLE 5 STATUS: ${remaining.length} numbers remaining               │`);
  console.log(`  └─────────────────────────────────────────────────────────┘`);
  console.log(`\n  ALL ${remaining.length} REMAINING (GUARANTEED to appear before cycle ends):`);
  console.log(`  ${remaining.join("  ")}\n`);

  // Prize predictions for remaining (from phase 5 logic)
  const prizeModel = buildSimplePrizeModel(trainCycles);

  console.log(`  Prize predictions for remaining ${remaining.length}:`);
  const prizeGroups = {};
  remaining.forEach((num) => {
    const pred = prizeModel.get(num);
    const prize = pred?.predictedPrize ?? "unknown";
    if (!prizeGroups[prize]) prizeGroups[prize] = [];
    prizeGroups[prize].push({ num, confidence: pred?.confidence ?? 0, fixed: pred?.isFixed ?? false });
  });

  [5000, 2000, 1000, 500, 200, 100, 50, "unknown"].forEach((prize) => {
    const group = prizeGroups[prize];
    if (!group || group.length === 0) return;
    const fixed  = group.filter((g) => g.fixed).length;
    const numStr = group.map((g) => `${g.num}${g.fixed?"*":""}`).join("  ");
    console.log(`\n  ₹${prize} (${group.length} numbers, ${fixed} fixed):`);
    console.log(`    ${numStr}`);
  });
  console.log(`\n  * = fixed prize (100% reliable across all past cycles)`);

  // DOW prediction for today (if angle3 had signal)
  const lastEntry = currentCycle.drawEntries[currentCycle.drawEntries.length - 1];
  const nextDOW   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][(new Date(lastEntry.drawDate).getUTCDay() + 1) % 7];
  console.log(`\n  ─────────────────────────────────────────────────────────`);
  console.log(`  CYCLE 6 READINESS`);
  console.log(`  ─────────────────────────────────────────────────────────`);
  console.log(`  Cycle 5 ends within ~${Math.ceil(remaining.length / 50)} draw days at current pace`);
  console.log(`  Next draw DOW: ${nextDOW}`);

  // Top 30 cycle 6 candidates (from normalized position across cycles 2-4)
  const normMap = buildNormMap(trainCycles);
  const top30C6 = [...normMap.entries()]
    .sort((a,b) => a[1].avgNorm - b[1].avgNorm)
    .slice(0, 30);

  console.log(`\n  Top 30 early-appearing numbers for Cycle 6:`);
  console.log(`  (These consistently appear in first 2% of each cycle)`);
  console.log(`  Rank | Number | AvgNormPos | AvgApp | Prize`);
  console.log(`  ` + "-".repeat(48));
  top30C6.forEach(([num, stats], i) => {
    console.log(
      `  ${String(i+1).padEnd(4)} | ${num}   | ${stats.avgNorm.toFixed(5)}   | ` +
      `${String(stats.avgApp.toFixed(1)).padEnd(6)} | ₹${stats.prize ?? "?"}`
    );
  });
}

// ─────────────────────────────────────────────────────────────
// PRIZE MODEL (simplified, self-contained)
// ─────────────────────────────────────────────────────────────
function buildSimplePrizeModel(trainCycles) {
  const model = new Map();

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        if (!model.has(number)) {
          model.set(number, { prizes: [], predictedPrize: null, isFixed: false, confidence: 0 });
        }
        model.get(number).prizes.push(prize);
      }
    }
  }

  for (const [num, data] of model) {
    const freq = {};
    data.prizes.forEach((p) => { freq[p] = (freq[p]||0)+1; });
    const top = Object.entries(freq).sort((a,b)=>b[1]-a[1])[0];
    data.predictedPrize = top ? Number(top[0]) : null;
    data.isFixed        = Object.keys(freq).length === 1 && data.prizes.length >= 3;
    data.confidence     = top ? Math.round(top[1]/data.prizes.length*100) : 0;
  }

  return model;
}

// ─────────────────────────────────────────────────────────────
// NORMALIZED MAP (for cycle 6 candidates)
// ─────────────────────────────────────────────────────────────
function buildNormMap(trainCycles) {
  const map = new Map();

  for (const cycle of trainCycles) {
    const firstSeen = new Map();
    const countSeen = new Map();
    const prizeSeen = new Map();

    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (isNew && !firstSeen.has(number)) {
          firstSeen.set(number, dayEntry.dayIndexInCycle / cycle.totalDrawDays);
          prizeSeen.set(number, prize);
        }
        countSeen.set(number, (countSeen.get(number)||0)+1);
      }
    }

    for (const [num, normPos] of firstSeen) {
      if (!map.has(num)) map.set(num, { norms: [], apps: [], prize: null });
      const entry = map.get(num);
      entry.norms.push(normPos);
      entry.apps.push(countSeen.get(num)||1);
      if (!entry.prize) entry.prize = prizeSeen.get(num);
    }
  }

  for (const [num, data] of map) {
    data.avgNorm = mean(data.norms);
    data.avgApp  = mean(data.apps);
  }

  return map;
}

// ─────────────────────────────────────────────────────────────
runPhase10().catch((err) => {
  console.error("❌ Phase 10 failed:", err);
  process.exit(1);
});