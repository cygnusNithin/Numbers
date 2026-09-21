require("dotenv").config();
const mongoose = require("mongoose");
const fs = require("fs");

const LotteryData = require("../models/FullLotteryData");

const { detectCycles, printCycleSummary, printDrawSizeStats } = require("./cycleDetector");
const {
  buildNumberProfiles,
  computeNumberStats,
  getRemainingCycle5Numbers,
  printConsistencyReport,
  printFrequencyDistribution,
} = require("./numberProfiler");
const {
  buildDigitPositionMatrix,
  buildRangeBucketMatrix,
  buildDigitSumDistribution,
  printDigitFreqByBucket,
  printModularTests,
  printRangeBucketMatrix,
} = require("./digitAnalyzer");

async function runPhase1() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log(`✅ Connected to MongoDB`);

  // ── Step 1: Load all draws sorted by drawDate ─────────────────────────
  console.log("\n📥 Loading all draws...");
  const draws = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  console.log(`   Total draw records: ${draws.length}`);

  // Sanity check for null drawDates
  const nullDates = draws.filter((d) => !d.drawDate).length;
  if (nullDates > 0) {
    console.warn(`   ⚠️  ${nullDates} records have null drawDate — check your data`);
  }

  // ── Step 2: Detect the real 5 cycles ─────────────────────────────────
  console.log("\n🔄 Detecting cycles (ends when all 10,000 numbers covered)...");
  const cycles = detectCycles(draws);

  console.log(`   ✅ Total cycles detected: ${cycles.length}`);
  if (cycles.length !== 5) {
    console.warn(
      `   ⚠️  Expected 5 cycles but found ${cycles.length}. ` +
        `Check if all 10,000 numbers truly appear in each cycle.`
    );
  }

  printCycleSummary(cycles);
  printDrawSizeStats(cycles);

  // ── Step 3: Build number profiles ─────────────────────────────────────
  console.log("\n📊 Building per-number profiles...");
  const profiles = buildNumberProfiles(cycles);
  const stats = computeNumberStats(profiles, cycles.length);

  const completedCycleCount = cycles.filter((c) => c.isComplete).length;
  console.log(`   Completed cycles: ${completedCycleCount}`);

  // Coverage stats
  const fullCoverage = stats.filter((s) => s.appearedInCycles === completedCycleCount);
  const missingFromSome = stats.filter((s) => s.appearedInCycles < completedCycleCount);
  console.log(`   Numbers appearing in ALL ${completedCycleCount} completed cycles: ${fullCoverage.length}`);
  console.log(`   Numbers missing from ≥1 completed cycle: ${missingFromSome.length}`);

  if (missingFromSome.length > 0) {
    console.log(
      `   Sample missing: ${missingFromSome.slice(0, 10).map((s) => s.number).join(", ")}`
    );
    console.log(`   ⚠️  These may indicate data gaps or lottery anomalies.`);
  }

  printFrequencyDistribution(stats, completedCycleCount);
  printConsistencyReport(stats, 20);

  // ── Step 4: Cycle 5 remaining numbers ─────────────────────────────────
  const lastCycle = cycles[cycles.length - 1];
  const remaining = getRemainingCycle5Numbers(profiles, lastCycle.cycleNumber);

  console.log(`\n🔮 CYCLE ${lastCycle.cycleNumber} STATUS (current, in progress):`);
  console.log(`   Start date:                     ${new Date(lastCycle.startDate).toISOString().split("T")[0]}`);
  console.log(`   Draw days completed:             ${lastCycle.totalDrawDays}`);
  console.log(`   Unique numbers drawn so far:     ${lastCycle.totalNumbersDrawn}`);
  console.log(`   Numbers remaining (candidates):  ${remaining.length}`);
  console.log(`   Progress:                        ${((lastCycle.totalNumbersDrawn / 10000) * 100).toFixed(1)}%`);
  console.log(`   First 20 remaining: ${remaining.slice(0, 20).join(", ")}`);

  // ── Step 5: Hot number analysis within cycles ──────────────────────────
  console.log("\n🔥 HOT NUMBER ANALYSIS (avg appearances per completed cycle):");
  const hotSorted = [...stats]
    .filter((s) => s.avgAppearances !== null)
    .sort((a, b) => b.avgAppearances - a.avgAppearances);

  console.log("   Top 20 hottest numbers (appear most times per cycle):");
  hotSorted.slice(0, 20).forEach((s) => {
    console.log(
      `     ${s.number} → avg ${s.avgAppearances}x/cycle | avgFirstDay: ${s.avgFirstDay} | prize: ${s.prizePrediction}`
    );
  });

  console.log("\n   Top 20 coldest numbers (appear least times per cycle):");
  hotSorted.slice(-20).reverse().forEach((s) => {
    console.log(
      `     ${s.number} → avg ${s.avgAppearances}x/cycle | avgFirstDay: ${s.avgFirstDay} | prize: ${s.prizePrediction}`
    );
  });

  // ── Step 6: Prize consistency ──────────────────────────────────────────
  const prizeFixed = stats.filter((s) => s.prizeIsAlwaysSame);
  const prizeVaries = stats.filter(
    (s) => !s.prizeIsAlwaysSame && s.appearedInCycles === completedCycleCount
  );
  console.log(`\n🏆 Numbers with FIXED prize across all completed cycles: ${prizeFixed.length}`);
  console.log(`   Numbers with VARYING prize across completed cycles:    ${prizeVaries.length}`);
  if (prizeFixed.length > 0) {
    console.log("   Sample fixed-prize numbers:");
    prizeFixed.slice(0, 10).forEach((s) => {
      console.log(`     ${s.number} → always ₹${s.prizePrediction}`);
    });
  }

  // ── Step 7: Digit analysis ─────────────────────────────────────────────
  console.log("\n🔢 Running digit analysis (first appearances only)...");
  const digitMatrix = buildDigitPositionMatrix(cycles);
  const rangeMatrix = buildRangeBucketMatrix(cycles);
  const digitSumDist = buildDigitSumDistribution(cycles);

  printDigitFreqByBucket(digitMatrix);
  printRangeBucketMatrix(rangeMatrix);
  printModularTests(cycles);

  // ── Step 8: Export for Phase 2 ────────────────────────────────────────
  const phase1Output = {
    totalDraws: draws.length,
    cycleCount: cycles.length,
    completedCycles: completedCycleCount,
    cycleSummary: cycles.map((c) => ({
      cycleNumber: c.cycleNumber,
      startDate: c.startDate,
      endDate: c.endDate,
      totalDrawDays: c.totalDrawDays,
      totalNumbersDrawn: c.totalNumbersDrawn,
      isComplete: c.isComplete,
      remainingNumbers: c.remainingNumbers,
    })),
    currentCycle: {
      cycleNumber: lastCycle.cycleNumber,
      totalDrawDays: lastCycle.totalDrawDays,
      totalNumbersDrawn: lastCycle.totalNumbersDrawn,
      remainingCount: remaining.length,
      remainingNumbers: remaining,
      progressPct: parseFloat(
        ((lastCycle.totalNumbersDrawn / 10000) * 100).toFixed(1)
      ),
    },
    digitMatrix,
    rangeMatrix,
    digitSumDistribution: digitSumDist,
    numberStats: stats,
  };

  fs.writeFileSync("./phase1_output.json", JSON.stringify(phase1Output, null, 2));
  console.log("\n✅ Phase 1 complete → phase1_output.json");

  await mongoose.disconnect();
}

runPhase1().catch((err) => {
  console.error("❌ Phase 1 failed:", err);
  process.exit(1);
});