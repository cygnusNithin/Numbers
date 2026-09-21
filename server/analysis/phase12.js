require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 12 — COMPLEMENT PAIRING + NEIGHBORHOOD STRUCTURE
//
// Phase 11 found:
//   1. N and (9999-N) appear same day: 4.7x elevated (Z=24)
//   2. Small gaps (1,2,3,4,5) dominant — local neighborhoods
//   3. digitSum%10: 2x elevated within a day
//
// Phase 12 investigates:
//   A. How strong/consistent is complement pairing per cycle?
//   B. What fraction of each day's draw are complement pairs?
//   C. Are prize tiers correlated between N and 9999-N?
//   D. If we know N was drawn, does (9999-N) predict tomorrow?
//   E. Neighborhood structure — what radius clusters the draw?
//   F. Combined formula attempt: complement + neighborhood
//   G. Validation: can we use these signals to predict?
// ═══════════════════════════════════════════════════════════════

async function runPhase12() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  console.log("📋 PHASE 12 — COMPLEMENT PAIRING + NEIGHBORHOOD STRUCTURE\n");
  console.log("   From Phase 11:");
  console.log("   → N and 9999-N same-day: 4.7x elevated (Z-score ~24)");
  console.log("   → Small gaps (1-5) most common within a day");
  console.log("   → digitSum%10: 2x elevated within a day\n");

  // ═══════════════════════════════════════════════════════════════
  // PART A — COMPLEMENT PAIRING PER CYCLE (deep dive)
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("PART A — COMPLEMENT PAIRING PER CYCLE");
  console.log("  For each draw day: what % of drawn numbers have their");
  console.log("  complement (9999-N) ALSO drawn on the same day?");
  console.log("═".repeat(65));

  const complementStats = analyzeComplementPairing(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // PART B — COMPLEMENT PRIZE CORRELATION
  // Does prize(N) predict prize(9999-N)?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PART B — COMPLEMENT PRIZE CORRELATION");
  console.log("  Q: If prize(N) = ₹X, what is prize(9999-N)?");
  console.log("═".repeat(65));

  analyzeComplementPrizePairs(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // PART C — NEIGHBORHOOD STRUCTURE
  // What radius R maximizes the complement/cluster pairing signal?
  // Build a profile of each day's "cluster structure"
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PART C — NEIGHBORHOOD CLUSTER PROFILE");
  console.log("  Find the actual cluster structure within each day");
  console.log("═".repeat(65));

  analyzeNeighborhoodClusters(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // PART D — PREDICT USING COMPLEMENT SIGNAL
  // If N is drawn today (new), is (9999-N) drawn tomorrow?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PART D — COMPLEMENT AS NEXT-DAY PREDICTOR");
  console.log("  Q: If N was drawn today, is (9999-N) drawn soon?");
  console.log("═".repeat(65));

  analyzeComplementNextDay(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // PART E — DIGIT SUM GROUPING WITHIN DAYS
  // Which digit sum values dominate on specific days?
  // Is it the same digit sum across multiple days of a cycle?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PART E — DIGIT SUM GROUPING WITHIN DRAW DAYS");
  console.log("  Q: Do drawn numbers share digit sum patterns?");
  console.log("═".repeat(65));

  analyzeDigitSumGrouping(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // PART F — COMBINED FORMULA ATTEMPT
  // Use complement + neighborhood + digit sum together
  // Build a prediction score for each number
  // Validate on cycle 4 using cycle 2+3 data
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PART F — COMBINED FORMULA VALIDATION");
  console.log("  Using all signals: complement + neighborhood + digitSum");
  console.log("═".repeat(65));

  validateCombinedFormula(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // PART G — CYCLE 5 COMPLEMENT ANALYSIS
  // Among remaining 48 numbers, which have their complement already drawn?
  // These are the ones that DON'T follow complement pairing.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("PART G — CYCLE 5 COMPLEMENT STATUS");
  console.log("  For each remaining number: is its complement drawn?");
  console.log("  Same day? Different day? Not drawn yet?");
  console.log("═".repeat(65));

  analyzeCycle5Complements(currentCycle, trainCycles);

  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
const numVal   = (s) => parseInt(s, 10);
const comp     = (s) => String(9999 - numVal(s)).padStart(4, "0");
const digitSum = (s) => s.split("").reduce((a, d) => a + Number(d), 0);
const mean     = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
const stdDev   = (arr) => {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
};

// ═══════════════════════════════════════════════════════════════
// PART A — COMPLEMENT PAIRING
// ═══════════════════════════════════════════════════════════════
function analyzeComplementPairing(trainCycles) {
  const results = {};

  for (const cycle of trainCycles) {
    let totalSameDayPairs   = 0;
    let totalExpectedPairs  = 0;
    let totalNumbers        = 0;
    const dayStats = [];

    // Build first-appearance day map
    const firstDay = new Map();
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, isNew } of dayEntry.numbers) {
        if (isNew && !firstDay.has(number)) {
          firstDay.set(number, dayEntry.dayIndexInCycle);
        }
      }
    }

    // For each draw day, check complement pairing rate
    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers.filter((n) => n.isNew).map((n) => n.number);
      if (newNums.length < 5) continue;

      const daySet = new Set(newNums);
      let sameDayCount = 0;
      let totalWithComp = 0;

      for (const num of newNums) {
        const c = comp(num);
        if (firstDay.has(c)) {
          totalWithComp++;
          if (daySet.has(c)) sameDayCount++;
        }
      }

      const sameDayRate    = totalWithComp > 0 ? sameDayCount / totalWithComp : 0;
      const expectedRate   = newNums.length / 10000; // random baseline

      totalSameDayPairs  += sameDayCount;
      totalExpectedPairs += totalWithComp * expectedRate;
      totalNumbers       += newNums.length;

      dayStats.push({
        day: dayEntry.dayIndexInCycle,
        newCount: newNums.length,
        withComp: totalWithComp,
        sameDayCount,
        sameDayRate: parseFloat((sameDayRate * 100).toFixed(2)),
        expected: parseFloat((expectedRate * 100).toFixed(2)),
      });
    }

    const overallRate     = totalNumbers > 0 ? (totalSameDayPairs / totalNumbers * 100).toFixed(3) : 0;
    const overallExpected = totalNumbers > 0 ? (totalExpectedPairs / totalNumbers * 100).toFixed(3) : 0;
    const elevation       = parseFloat(overallExpected) > 0
      ? (parseFloat(overallRate) / parseFloat(overallExpected)).toFixed(2)
      : 0;

    results[cycle.cycleNumber] = { overallRate, overallExpected, elevation, dayStats };

    console.log(`\n  Cycle ${cycle.cycleNumber}:`);
    console.log(`    Same-day complement rate: ${overallRate}% (expected: ${overallExpected}%)`);
    console.log(`    Elevation: ${elevation}x random`);
    console.log(`    Total same-day complement pairs: ${totalSameDayPairs}`);

    // Top 5 days with highest complement rate
    const topDays = dayStats
      .filter((d) => d.withComp > 10)
      .sort((a, b) => b.sameDayRate - a.sameDayRate)
      .slice(0, 5);
    console.log(`    Top 5 days by complement rate:`);
    topDays.forEach((d) => {
      console.log(
        `      Day ${String(d.day).padEnd(4)}: ${d.sameDayCount}/${d.withComp} = ${d.sameDayRate}% (expected ${d.expected}%)`
      );
    });

    // Distribution of same-day rates across days
    const rates = dayStats.filter((d) => d.withComp > 5).map((d) => d.sameDayRate);
    console.log(`    Avg same-day rate: ${mean(rates).toFixed(2)}% ± ${stdDev(rates).toFixed(2)}%`);
  }

  // Statistical significance
  console.log(`\n  ─── Statistical significance ───`);
  for (const [cn, r] of Object.entries(results)) {
    const signal = parseFloat(r.elevation) > 2 ? "✅ STRONG" :
                   parseFloat(r.elevation) > 1.3 ? "⚠️  WEAK" : "❌ NOISE";
    console.log(`  Cycle ${cn}: elevation ${r.elevation}x → ${signal}`);
  }

  return results;
}

// ═══════════════════════════════════════════════════════════════
// PART B — COMPLEMENT PRIZE CORRELATION
// ═══════════════════════════════════════════════════════════════
function analyzeComplementPrizePairs(trainCycles) {
  // For complement pairs that appear same day: are their prizes correlated?
  const prizePairCounts = {}; // "prizeN:prizeComp" → count

  let totalSameDayPairs = 0;
  let samePrizeCount    = 0;
  const examples        = [];

  for (const cycle of trainCycles) {
    // Build day → numbers map with prizes
    const dayNumberPrize = new Map(); // dayIndex → Map<number, prize>

    for (const dayEntry of cycle.drawEntries) {
      if (!dayNumberPrize.has(dayEntry.dayIndexInCycle)) {
        dayNumberPrize.set(dayEntry.dayIndexInCycle, new Map());
      }
      const dayMap = dayNumberPrize.get(dayEntry.dayIndexInCycle);
      dayEntry.numbers.filter((n) => n.isNew).forEach((n) => {
        dayMap.set(n.number, n.prize);
      });
    }

    // Find same-day complement pairs
    for (const [day, dayMap] of dayNumberPrize) {
      const nums = [...dayMap.keys()];
      for (const num of nums) {
        const c = comp(num);
        if (numVal(num) >= 5000) continue; // avoid double counting
        if (dayMap.has(c)) {
          totalSameDayPairs++;
          const p1 = dayMap.get(num);
          const p2 = dayMap.get(c);
          const key = `${p1}:${p2}`;
          prizePairCounts[key] = (prizePairCounts[key] || 0) + 1;
          if (p1 === p2) {
            samePrizeCount++;
            if (examples.length < 15) {
              examples.push({ num, c, prize: p1, cycle: cycle.cycleNumber, day });
            }
          }
        }
      }
    }
  }

  console.log(`\n  Total same-day complement pairs found: ${totalSameDayPairs}`);
  console.log(`  Same prize: ${samePrizeCount} (${(samePrizeCount/totalSameDayPairs*100).toFixed(1)}%)`);

  // Expected same prize by chance
  // P(same prize) ≈ 0.667^2 + 0.289^2 + ... ≈ 31.7%
  console.log(`  Expected same prize (random): ~31.7%`);
  console.log(`  ${samePrizeCount/totalSameDayPairs > 0.4 ? "✅ SIGNAL: complements share prize more than random!" : "❌ Prize pairing not significant"}`);

  console.log(`\n  Prize pair distribution (N prize → complement prize):`);
  const sorted = Object.entries(prizePairCounts).sort((a, b) => b[1] - a[1]);
  sorted.slice(0, 15).forEach(([key, count]) => {
    const [p1, p2] = key.split(":");
    const pct = (count / totalSameDayPairs * 100).toFixed(1);
    const same = p1 === p2 ? "✅ same" : "";
    console.log(`    ₹${String(p1).padEnd(5)} ↔ ₹${String(p2).padEnd(5)}: ${count} pairs (${pct}%) ${same}`);
  });

  console.log(`\n  Same-prize complement examples:`);
  examples.forEach((e) => {
    console.log(`    C${e.cycle} Day ${e.day}: ${e.num} ↔ ${e.c} = ₹${e.prize}`);
  });
}

// ═══════════════════════════════════════════════════════════════
// PART C — NEIGHBORHOOD CLUSTER PROFILE
// ═══════════════════════════════════════════════════════════════
function analyzeNeighborhoodClusters(trainCycles) {
  // For each draw day, find contiguous runs of drawn numbers
  // A run = consecutive or near-consecutive numbers (gap ≤ threshold)

  const thresholds = [1, 2, 5, 10, 20, 50];
  const cycleClusterStats = {};

  for (const cycle of trainCycles) {
    const clusterSizes = { 1:[], 2:[], 5:[], 10:[], 20:[], 50:[] };

    for (const dayEntry of cycle.drawEntries) {
      const sorted = dayEntry.numbers
        .filter((n) => n.isNew)
        .map((n) => numVal(n.number))
        .sort((a, b) => a - b);

      if (sorted.length < 5) continue;

      for (const thresh of thresholds) {
        const clusters = [[sorted[0]]];
        for (let i = 1; i < sorted.length; i++) {
          if (sorted[i] - sorted[i - 1] <= thresh) {
            clusters[clusters.length - 1].push(sorted[i]);
          } else {
            clusters.push([sorted[i]]);
          }
        }
        const sizes = clusters.map((c) => c.length);
        clusterSizes[thresh].push(...sizes);
      }
    }

    console.log(`\n  Cycle ${cycle.cycleNumber} cluster analysis:`);
    console.log(`  Thresh | NumClusters/day | AvgClusterSize | MaxCluster | Runs>5`);
    console.log(`  ` + "-".repeat(60));

    for (const thresh of thresholds) {
      const sizes     = clusterSizes[thresh];
      const numDays   = cycle.drawEntries.length;
      const avgPerDay = sizes.length / numDays;
      const avgSize   = mean(sizes);
      const maxSize   = Math.max(...sizes);
      const bigRuns   = sizes.filter((s) => s > 5).length;

      console.log(
        `  ≤${String(thresh).padEnd(3)}  | ${avgPerDay.toFixed(1).padEnd(16)} | ` +
        `${avgSize.toFixed(2).padEnd(14)} | ${String(maxSize).padEnd(10)} | ${bigRuns}`
      );
    }

    // Find the most common cluster size for thresh=5
    const sizes5 = clusterSizes[5];
    const freq = {};
    sizes5.forEach((s) => { freq[s] = (freq[s] || 0) + 1; });
    const topSizes = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8);
    console.log(`  Most common cluster sizes (thresh=5): ${topSizes.map(([s, c]) => `${s}(×${c})`).join(" ")}`);

    cycleClusterStats[cycle.cycleNumber] = clusterSizes;
  }

  // Show an example day with clusters highlighted
  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  if (cycle4) {
    console.log(`\n  Cycle 4 Day 1 — clusters at threshold=5:`);
    const day1 = cycle4.drawEntries[0];
    const sorted = day1.numbers.filter((n) => n.isNew).map((n) => numVal(n.number)).sort((a,b)=>a-b);
    const clusters = [[sorted[0]]];
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i] - sorted[i-1] <= 5) clusters[clusters.length-1].push(sorted[i]);
      else clusters.push([sorted[i]]);
    }
    const bigClusters = clusters.filter((c) => c.length >= 3).slice(0, 10);
    console.log(`  Large clusters (≥3 members):`);
    bigClusters.forEach((c) => {
      console.log(`    [${c.join(", ")}] — ${c.length} numbers, range ${c[0]}-${c[c.length-1]}`);
    });
  }

  return cycleClusterStats;
}

// ═══════════════════════════════════════════════════════════════
// PART D — COMPLEMENT AS NEXT-DAY PREDICTOR
// ═══════════════════════════════════════════════════════════════
function analyzeComplementNextDay(trainCycles) {
  // If number N is drawn on day D (first time),
  // how many days later does complement(N) first appear?

  const gapDist  = {}; // gap in days → count
  let totalPairs = 0;
  let sameDay    = 0;
  let nextDay    = 0;
  let within3    = 0;
  let within7    = 0;
  let never      = 0;

  for (const cycle of trainCycles) {
    const firstDay = new Map();
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, isNew } of dayEntry.numbers) {
        if (isNew && !firstDay.has(number)) {
          firstDay.set(number, dayEntry.dayIndexInCycle);
        }
      }
    }

    for (const [num, day] of firstDay) {
      if (numVal(num) >= 5000) continue; // avoid double counting
      const c = comp(num);
      if (firstDay.has(c)) {
        const gap = firstDay.get(c) - day;
        gapDist[gap] = (gapDist[gap] || 0) + 1;
        totalPairs++;
        if (gap === 0)           sameDay++;
        if (gap === 1 || gap === -1) nextDay++;
        if (Math.abs(gap) <= 3)  within3++;
        if (Math.abs(gap) <= 7)  within7++;
      } else {
        never++;
      }
    }
  }

  console.log(`\n  Complement gap distribution (day(N) vs day(9999-N)):`);
  console.log(`  Total complement pairs: ${totalPairs}`);
  console.log(`\n  Same day (gap=0):     ${sameDay} (${(sameDay/totalPairs*100).toFixed(1)}%)`);
  console.log(`  Adjacent (|gap|=1):   ${nextDay} (${(nextDay/totalPairs*100).toFixed(1)}%)`);
  console.log(`  Within 3 days:        ${within3} (${(within3/totalPairs*100).toFixed(1)}%)`);
  console.log(`  Within 7 days:        ${within7} (${(within7/totalPairs*100).toFixed(1)}%)`);

  // Show gap distribution (near 0)
  console.log(`\n  Gap distribution (|gap| ≤ 30):`);
  const nearGaps = Object.entries(gapDist)
    .map(([k, v]) => ({ gap: Number(k), count: v }))
    .filter((g) => Math.abs(g.gap) <= 30)
    .sort((a, b) => a.gap - b.gap);

  nearGaps.forEach(({ gap, count }) => {
    const bar = "█".repeat(Math.min(Math.round(count / 5), 40));
    const pct = (count / totalPairs * 100).toFixed(1);
    console.log(`    gap=${String(gap).padStart(4)}: ${String(count).padEnd(5)} (${pct}%) ${bar}`);
  });

  // Expected distribution if random (symmetric around 0)
  const expectedSameDay = totalPairs / 350; // ~1/cycle_length
  console.log(`\n  Expected same-day count (random): ~${expectedSameDay.toFixed(0)}`);
  console.log(`  Actual same-day count: ${sameDay}`);
  console.log(`  Elevation: ${(sameDay / expectedSameDay).toFixed(2)}x`);

  // Is the gap distribution symmetric? (tests if there's a pairing rule)
  let symmetricPairs = 0;
  for (const [gap, count] of Object.entries(gapDist)) {
    const g = Number(gap);
    if (g > 0 && gapDist[-g]) {
      const diff = Math.abs(count - gapDist[-g]);
      if (diff / Math.max(count, gapDist[-g]) < 0.2) symmetricPairs++;
    }
  }
  console.log(`\n  Gap distribution symmetry (|gap=+k| ≈ |gap=-k|): ${symmetricPairs} symmetric pairs`);
  console.log(`  ${symmetricPairs > 10 ? "✅ Symmetric — no directional bias" : "⚠️  Asymmetric"}`);
}

// ═══════════════════════════════════════════════════════════════
// PART E — DIGIT SUM GROUPING
// ═══════════════════════════════════════════════════════════════
function analyzeDigitSumGrouping(trainCycles) {
  // For each draw day, what is the distribution of digit sums?
  // Is there a dominant digit sum that concentrates numbers?

  let domDSumElevation = []; // how much above random is the max digit sum?

  for (const cycle of trainCycles.slice(0, 1)) {
    console.log(`\n  Cycle ${cycle.cycleNumber} — digit sum distribution per day:`);
    console.log(`  Day | TopDS | TopCount | % | Expected% | Elevation`);
    console.log(`  ` + "-".repeat(60));

    for (const dayEntry of cycle.drawEntries.slice(0, 15)) {
      const newNums = dayEntry.numbers.filter((n) => n.isNew).map((n) => n.number);
      if (newNums.length < 10) continue;

      const dsCounts = {};
      newNums.forEach((n) => {
        const ds = digitSum(n);
        dsCounts[ds] = (dsCounts[ds] || 0) + 1;
      });

      const topDS      = Object.entries(dsCounts).sort((a, b) => b[1] - a[1])[0];
      const topPct     = (topDS[1] / newNums.length * 100).toFixed(1);

      // Expected: digit sums 0-36, but most numbers have DS 1-35
      // The expected max concentration for n draws from distribution
      // Most common DS is 18 (4*9/2 average), expected ~5.7% per DS value
      const expectedPct = (1/19 * 100).toFixed(1); // roughly 1 in 19 possible DS values are common
      const elevation   = (parseFloat(topPct) / parseFloat(expectedPct)).toFixed(2);
      domDSumElevation.push(parseFloat(elevation));

      console.log(
        `  ${String(dayEntry.dayIndexInCycle).padEnd(3)} | ${String(topDS[0]).padEnd(5)} | ` +
        `${String(topDS[1]).padEnd(8)} | ${topPct}% | ${expectedPct}%  | ${elevation}x`
      );
    }
  }

  const avgElevation = mean(domDSumElevation);
  console.log(`\n  Avg digit-sum elevation: ${avgElevation.toFixed(2)}x`);

  // Key test: does today's dominant digit sum predict tomorrow's?
  console.log(`\n  Digit sum autocorrelation (does dominant DS repeat?):`);
  for (const cycle of trainCycles.slice(0, 2)) {
    const domDS = [];
    for (const dayEntry of cycle.drawEntries) {
      const newNums = dayEntry.numbers.filter((n) => n.isNew).map((n) => n.number);
      if (newNums.length < 5) continue;
      const dsCounts = {};
      newNums.forEach((n) => { const ds=digitSum(n); dsCounts[ds]=(dsCounts[ds]||0)+1; });
      const top = Object.entries(dsCounts).sort((a,b)=>b[1]-a[1])[0];
      domDS.push(Number(top[0]));
    }

    // How often does tomorrow's dominant DS = today's?
    let same=0, adjacent=0, total=0;
    for (let i=0; i<domDS.length-1; i++) {
      if (domDS[i+1] === domDS[i]) same++;
      if (Math.abs(domDS[i+1] - domDS[i]) <= 1) adjacent++;
      total++;
    }
    const expectedSame = 1/19; // ~5.3%
    console.log(`  Cycle ${cycle.cycleNumber}: same DS next day: ${same}/${total} = ${(same/total*100).toFixed(1)}% (expected ~${(expectedSame*100).toFixed(1)}%)`);
    console.log(`  Adjacent DS (±1): ${adjacent}/${total} = ${(adjacent/total*100).toFixed(1)}%`);
  }
}

// ═══════════════════════════════════════════════════════════════
// PART F — COMBINED FORMULA VALIDATION
// ═══════════════════════════════════════════════════════════════
function validateCombinedFormula(trainCycles) {
  // Strategy: given today's draw, predict tomorrow using:
  //   1. Complement of today's numbers (complement signal)
  //   2. Neighbors ±K of today's numbers (neighborhood signal)
  //   3. Numbers with similar digit sum (DS signal)
  //
  // Validate on cycle 4 using cycles 2+3 statistics

  const cycle4  = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle4) { console.log("  ⚠️  No cycle 4"); return; }

  // Strategy: predict tomorrow's NEW numbers = complement of today's new numbers
  // that haven't appeared yet
  let compHits=0, compTotal=0;
  let neighborHits=0, neighborTotal=0;
  let randomHits=0, randomTotal=0;

  // Track drawn set within cycle 4
  const drawnInC4 = new Set();

  for (let i = 0; i < cycle4.drawEntries.length - 1; i++) {
    const today    = cycle4.drawEntries[i];
    const tomorrow = cycle4.drawEntries[i + 1];

    const todayNew   = today.numbers.filter((n) => n.isNew).map((n) => n.number);
    const tomorrowNew = new Set(tomorrow.numbers.filter((n) => n.isNew).map((n) => n.number));

    // Update drawn set
    today.numbers.forEach((n) => drawnInC4.add(n.number));

    // Prediction 1: complements of today's new numbers not yet drawn
    const compPredicted = new Set(
      todayNew
        .map((n) => comp(n))
        .filter((c) => !drawnInC4.has(c))
    );
    const compHit = [...tomorrowNew].filter((n) => compPredicted.has(n)).length;
    compHits  += compHit;
    compTotal += tomorrowNew.size;

    // Prediction 2: neighbors ±5 of today's numbers
    const neighborPredicted = new Set();
    todayNew.forEach((n) => {
      const v = numVal(n);
      for (let k = -5; k <= 5; k++) {
        if (k === 0) continue;
        const neighbor = String((v + k + 10000) % 10000).padStart(4, "0");
        if (!drawnInC4.has(neighbor)) neighborPredicted.add(neighbor);
      }
    });
    const neighborHit = [...tomorrowNew].filter((n) => neighborPredicted.has(n)).length;
    neighborHits  += neighborHit;
    neighborTotal += tomorrowNew.size;
  }

  const compHitPct      = (compHits / compTotal * 100).toFixed(2);
  const neighborHitPct  = (neighborHits / neighborTotal * 100).toFixed(2);

  // Random baseline: ~250/9500 ≈ 2.6% (remaining pool / draw size)
  const randomBaseline = (250 / 9500 * 100).toFixed(2);

  console.log(`\n  Prediction validation on cycle 4:\n`);
  console.log(`  Strategy                     | HitRate | RandomBaseline | Improvement`);
  console.log(`  ` + "-".repeat(68));
  console.log(
    `  Complement prediction        | ${compHitPct}%   | ~${randomBaseline}%          | ${(parseFloat(compHitPct)/parseFloat(randomBaseline)).toFixed(3)}x`
  );
  console.log(
    `  Neighbor (±5) prediction     | ${neighborHitPct}%   | ~${randomBaseline}%          | ${(parseFloat(neighborHitPct)/parseFloat(randomBaseline)).toFixed(3)}x`
  );

  // Combined: complement OR neighbor
  let combHits=0, combTotal=0;
  const drawnInC4b = new Set();

  for (let i = 0; i < cycle4.drawEntries.length - 1; i++) {
    const today     = cycle4.drawEntries[i];
    const tomorrow  = cycle4.drawEntries[i + 1];
    const todayNew  = today.numbers.filter((n) => n.isNew).map((n) => n.number);
    const tomorrowNew = new Set(tomorrow.numbers.filter((n) => n.isNew).map((n) => n.number));
    today.numbers.forEach((n) => drawnInC4b.add(n.number));

    const combined = new Set();
    todayNew.forEach((n) => {
      combined.add(comp(n));
      const v = numVal(n);
      for (let k = -3; k <= 3; k++) {
        if (k !== 0) combined.add(String((v+k+10000)%10000).padStart(4,"0"));
      }
    });
    const undrawn    = [...combined].filter((n) => !drawnInC4b.has(n));
    const combHit    = [...tomorrowNew].filter((n) => new Set(undrawn).has(n)).length;
    combHits  += combHit;
    combTotal += tomorrowNew.size;
  }

  const combPct = (combHits / combTotal * 100).toFixed(2);
  console.log(
    `  Combined (comp + neighbor±3)  | ${combPct}%   | ~${randomBaseline}%          | ${(parseFloat(combPct)/parseFloat(randomBaseline)).toFixed(3)}x`
  );

  console.log(`\n  KEY: If improvement > 1.5x → we have an exploitable formula.`);
}

// ═══════════════════════════════════════════════════════════════
// PART G — CYCLE 5 COMPLEMENT STATUS
// ═══════════════════════════════════════════════════════════════
function analyzeCycle5Complements(currentCycle, trainCycles) {
  // Build drawn set and first-day map for cycle 5
  const drawn   = new Map(); // number → dayDrawn
  const allNums = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));

  for (const dayEntry of currentCycle.drawEntries) {
    for (const { number, isNew } of dayEntry.numbers) {
      if (isNew && !drawn.has(number)) {
        drawn.set(number, dayEntry.dayIndexInCycle);
      }
    }
  }

  const remaining = allNums.filter((n) => !drawn.has(n));

  // Prize model from training cycles
  const prizeModel = new Map();
  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        if (!prizeModel.has(number)) prizeModel.set(number, []);
        prizeModel.get(number).push(prize);
      }
    }
  }
  const getPrize = (num) => {
    const arr = prizeModel.get(num) || [];
    if (!arr.length) return "?";
    const freq = {};
    arr.forEach((p) => { freq[p]=(freq[p]||0)+1; });
    return Number(Object.entries(freq).sort((a,b)=>b[1]-a[1])[0][0]);
  };

  console.log(`\n  Cycle 5 remaining ${remaining.length} numbers — complement status:\n`);
  console.log(`  Number | Prize | Complement | Comp Status  | Comp Prize | Gap`);
  console.log(`  ` + "-".repeat(72));

  // Sort remaining by prize (high first)
  const enriched = remaining.map((num) => {
    const c          = comp(num);
    const compDrawn  = drawn.has(c);
    const compDay    = compDrawn ? drawn.get(c) : null;
    const numPrize   = getPrize(num);
    const compPrize  = getPrize(c);
    const compStatus = !compDrawn ? "NOT DRAWN" :
                       compDay !== null ? `drawn day ${compDay}` : "drawn";
    return { num, numPrize, c, compDrawn, compDay, compPrize, compStatus };
  }).sort((a, b) => (b.numPrize ?? 0) - (a.numPrize ?? 0));

  enriched.forEach((e) => {
    console.log(
      `  ${e.num}   | ₹${String(e.numPrize).padEnd(5)} | ${e.c}       | ${String(e.compStatus).padEnd(12)} | ₹${String(e.compPrize).padEnd(9)} | ${e.compDay ?? "—"}`
    );
  });

  // Summary
  const bothRemaining = enriched.filter((e) => !e.compDrawn);
  const compDrawn     = enriched.filter((e) => e.compDrawn);

  console.log(`\n  Summary:`);
  console.log(`    Numbers where complement is ALSO remaining: ${bothRemaining.length}`);
  console.log(`    Numbers where complement is DRAWN:         ${compDrawn.length}`);

  if (bothRemaining.length > 0) {
    console.log(`\n  ✅ Both N and 9999-N still remaining (likely to appear together):`);
    bothRemaining.forEach((e) => {
      console.log(`    ${e.num}(₹${e.numPrize}) ↔ ${e.c}(₹${e.compPrize})`);
    });
  }

  // Prize correlation for same-day complement pairs in cycle 5
  console.log(`\n  Cycle 5 actual same-day complement pairs found so far:`);
  let sameDayPairs = 0;
  for (const [num, day] of drawn) {
    if (numVal(num) >= 5000) continue;
    const c = comp(num);
    if (drawn.has(c) && drawn.get(c) === day) {
      sameDayPairs++;
      const p1 = getPrize(num);
      const p2 = getPrize(c);
      // Only print first 20
      if (sameDayPairs <= 20) {
        console.log(`    Day ${day}: ${num}(₹${p1}) ↔ ${c}(₹${p2})`);
      }
    }
  }
  console.log(`  Total same-day complement pairs in cycle 5: ${sameDayPairs}`);

  // Expected
  const expectedPairs = drawn.size / 10000 * drawn.size / 2;
  console.log(`  Expected (random): ~${expectedPairs.toFixed(0)}`);
  const elevation = sameDayPairs / expectedPairs;
  console.log(`  Elevation: ${elevation.toFixed(2)}x`);
  console.log(`  ${elevation > 2 ? "✅ SIGNAL confirmed in cycle 5!" : "⚠️  Check data"}`);
}

// ─────────────────────────────────────────────────────────────
runPhase12().catch((err) => {
  console.error("❌ Phase 12 failed:", err);
  process.exit(1);
});