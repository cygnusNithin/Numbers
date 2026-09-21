require("dotenv").config();
const mongoose = require("mongoose");
const fs = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");
const {
  buildNumberProfiles,
  computeNumberStats,
  getRemainingCycle5Numbers,
} = require("./numberProfiler");

async function runPhase3() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  // Exclude cycle 1 — data gaps confirmed
  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  const profiles    = buildNumberProfiles(validCycles);
  const stats       = computeNumberStats(profiles, validCycles.length);
  const statsMap    = new Map(stats.map((s) => [s.number, s]));
  const remaining   = getRemainingCycle5Numbers(profiles, currentCycle.cycleNumber);

  console.log("📋 CURRENT STATE:");
  console.log(`   Training cycles:  2, 3, 4`);
  console.log(`   Current cycle 5:  ${currentCycle.totalDrawDays} draw days`);
  console.log(`   Numbers drawn:    ${currentCycle.totalNumbersDrawn}/10000`);
  console.log(`   Remaining:        ${remaining.length} numbers`);
  console.log(`   Last draw date:   ${new Date(currentCycle.endDate).toISOString().split("T")[0]}\n`);

  // ═══════════════════════════════════════════════════════
  // STEP 1 — FREQUENCY TABLE
  // ═══════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — FREQUENCY TABLE (daily draw probability)");
  console.log("═".repeat(65));
  const freqTable = buildFrequencyTable(trainCycles, statsMap);
  printFrequencyDistribution(freqTable);

  // ═══════════════════════════════════════════════════════
  // STEP 2 — RECENCY TABLE
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — RECENCY ANALYSIS (cycle 5)");
  console.log("═".repeat(65));
  const recencyTable = buildRecencyTable(currentCycle, freqTable);
  printRecencyStats(recencyTable, currentCycle);

  // ═══════════════════════════════════════════════════════
  // STEP 3 — DAILY PROBABILITY SCORES
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — DAILY PROBABILITY SCORES");
  console.log("═".repeat(65));
  const dailyScores = buildDailyScores(freqTable, recencyTable, remaining, statsMap);
  printTopDailyScores(dailyScores, 50);

  // ═══════════════════════════════════════════════════════
  // STEP 4 — BACKTEST VALIDATION
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — BACKTEST VALIDATION (frequency+recency on cycle 4)");
  console.log("═".repeat(65));
  const cycle4  = trainCycles.find((c) => c.cycleNumber === 4);
  const c23     = trainCycles.filter((c) => c.cycleNumber <= 3);
  backtestFrequencyModel(c23, cycle4);

  // ═══════════════════════════════════════════════════════
  // STEP 5 — GUARANTEED NUMBERS (cycle 5 remaining)
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — GUARANTEED NUMBERS (cycle 5 must-draws)");
  console.log("═".repeat(65));
  printGuaranteed(remaining, dailyScores, statsMap);

  // ═══════════════════════════════════════════════════════
  // STEP 6 — PRIZE PREDICTION LAYER
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — PRIZE PREDICTION LAYER");
  console.log("═".repeat(65));
  const prizeModel = buildPrizeModel(statsMap);
  printPrizeModelSummary(prizeModel);

  // ═══════════════════════════════════════════════════════
  // STEP 7 — TOMORROW'S DRAW PREDICTION
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — TOMORROW'S DRAW PREDICTION");
  console.log("═".repeat(65));
  const tomorrowPrediction = buildTomorrowPrediction(
    dailyScores, remaining, prizeModel, statsMap, 100
  );
  printTomorrowPrediction(tomorrowPrediction);

  // ═══════════════════════════════════════════════════════
  // STEP 8 — CYCLE TRANSITION DETECTOR
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 8 — CYCLE TRANSITION STATUS");
  console.log("═".repeat(65));
  detectCycleTransition(currentCycle, remaining);

  // ═══════════════════════════════════════════════════════
  // EXPORT
  // ═══════════════════════════════════════════════════════
  const output = {
    generatedAt:       new Date().toISOString(),
    currentCycleDay:   currentCycle.totalDrawDays,
    numbersDrawn:      currentCycle.totalNumbersDrawn,
    remaining,
    remainingCount:    remaining.length,
    tomorrowPrediction,
    topDailyScores:    dailyScores.slice(0, 500),
    prizeModel:        [...prizeModel.entries()].map(([k, v]) => ({
      number: k, ...v,
    })),
  };

  fs.writeFileSync("./phase3_output.json", JSON.stringify(output, null, 2));
  console.log("\n✅ Phase 3 complete → phase3_output.json");
  await mongoose.disconnect();
}

// ═══════════════════════════════════════════════════════
// FREQUENCY TABLE
// baseRatePerDay = avgAppearances / avgCycleDays
// avgGapDays     = avgCycleDays / avgAppearances
// ═══════════════════════════════════════════════════════
function buildFrequencyTable(trainCycles, statsMap) {
  const avgCycleDays =
    trainCycles.reduce((a, c) => a + c.totalDrawDays, 0) / trainCycles.length;

  const table = new Map();

  for (const [number, stat] of statsMap) {
    if ((stat.appearedInCycles ?? 0) < 2) continue;

    const avgApp     = stat.avgAppearances ?? 1;
    const baseRate   = avgApp / avgCycleDays;
    const avgGapDays = avgCycleDays / avgApp;

    table.set(number, {
      number,
      avgAppearances:  avgApp,
      avgCycleDays,
      baseRatePerDay:  parseFloat(baseRate.toFixed(6)),
      avgGapDays:      parseFloat(avgGapDays.toFixed(2)),
      predictedPrize:  stat.prizePrediction,
      prizeIsFixed:    stat.prizeIsAlwaysSame,
      preferredDOW:    stat.preferredDOW,
    });
  }

  return table;
}

function printFrequencyDistribution(freqTable) {
  const buckets = { veryHigh: 0, high: 0, medium: 0, low: 0, veryLow: 0 };
  let maxRate = 0, minRate = Infinity;

  for (const e of freqTable.values()) {
    const r = e.baseRatePerDay;
    if (r > maxRate) maxRate = r;
    if (r < minRate) minRate = r;
    if (r >= 0.08)      buckets.veryHigh++;
    else if (r >= 0.06) buckets.high++;
    else if (r >= 0.04) buckets.medium++;
    else if (r >= 0.02) buckets.low++;
    else                buckets.veryLow++;
  }

  console.log(`\n  Numbers in frequency table: ${freqTable.size}`);
  console.log(`  Base rate range: ${minRate.toFixed(6)} – ${maxRate.toFixed(6)} per day`);
  console.log(`\n  Distribution:`);
  console.log(`    Very High (≥8%/day):   ${buckets.veryHigh}`);
  console.log(`    High      (6-8%/day):  ${buckets.high}`);
  console.log(`    Medium    (4-6%/day):  ${buckets.medium}`);
  console.log(`    Low       (2-4%/day):  ${buckets.low}`);
  console.log(`    Very Low  (<2%/day):   ${buckets.veryLow}`);

  const sorted = [...freqTable.values()].sort(
    (a, b) => b.baseRatePerDay - a.baseRatePerDay
  );

  console.log(`\n  Top 20 highest daily probability numbers:`);
  console.log("  Number | BaseRate/Day | AvgApp | AvgGapDays | Prize | Fixed");
  console.log("  " + "-".repeat(62));
  sorted.slice(0, 20).forEach((e) => {
    console.log(
      `  ${e.number}   | ${String(e.baseRatePerDay.toFixed(5)).padEnd(12)} | ` +
      `${String(e.avgAppearances).padEnd(6)} | ` +
      `${String(e.avgGapDays).padEnd(10)} | ` +
      `${String(e.predictedPrize ?? "?").padEnd(5)} | ${e.prizeIsFixed ? "YES" : "no"}`
    );
  });
}

// ═══════════════════════════════════════════════════════
// RECENCY TABLE
// overdueScore = daysSinceSeen / avgGapDays
// recencyMultiplier = min(overdueScore, 3.0)  — capped to avoid outlier explosion
// ═══════════════════════════════════════════════════════
function buildRecencyTable(currentCycle, freqTable) {
  // Last seen day per number in cycle 5
  const lastSeenDay = new Map();
  for (const dayEntry of currentCycle.drawEntries) {
    for (const { number } of dayEntry.numbers) {
      lastSeenDay.set(number, dayEntry.dayIndexInCycle);
    }
  }

  const currentDay = currentCycle.totalDrawDays;
  const recency    = new Map();

  for (const [number, freq] of freqTable) {
    const lastDay       = lastSeenDay.get(number) ?? 0;
    const daysSinceSeen = currentDay - lastDay;
    const overdueScore  = freq.avgGapDays > 0
      ? daysSinceSeen / freq.avgGapDays
      : 1;

    recency.set(number, {
      number,
      lastSeenDay:       lastDay === 0 ? null : lastDay,
      daysSinceSeen,
      avgGapDays:        freq.avgGapDays,
      overdueScore:      parseFloat(overdueScore.toFixed(3)),
      recencyMultiplier: parseFloat(Math.min(overdueScore, 3.0).toFixed(3)),
    });
  }

  return recency;
}

function printRecencyStats(recencyTable, currentCycle) {
  const vals       = [...recencyTable.values()];
  const overdue2x  = vals.filter((r) => r.overdueScore >= 2).length;
  const overdue15  = vals.filter((r) => r.overdueScore >= 1.5).length;
  const overdue1   = vals.filter((r) => r.overdueScore >= 1).length;
  const fresh      = vals.filter((r) => r.overdueScore < 0.5).length;

  console.log(`\n  Current cycle 5 day: ${currentCycle.totalDrawDays}`);
  console.log(`\n  Overdue score distribution:`);
  console.log(`    Very overdue (≥2x avg gap):   ${overdue2x} numbers`);
  console.log(`    Overdue      (≥1.5x avg gap): ${overdue15} numbers`);
  console.log(`    Past avg gap (≥1x avg gap):   ${overdue1} numbers`);
  console.log(`    Fresh        (<0.5x avg gap): ${fresh} numbers`);

  const sorted = [...vals].sort((a, b) => b.overdueScore - a.overdueScore);
  console.log(`\n  Top 20 most overdue numbers in cycle 5:`);
  console.log("  Number | LastSeenDay | DaysSince | AvgGap | OverdueScore");
  console.log("  " + "-".repeat(60));
  sorted.slice(0, 20).forEach((r) => {
    console.log(
      `  ${r.number}   | ${String(r.lastSeenDay ?? "never").padEnd(11)} | ` +
      `${String(r.daysSinceSeen).padEnd(9)} | ` +
      `${String(r.avgGapDays).padEnd(6)} | ${r.overdueScore}x`
    );
  });
}

// ═══════════════════════════════════════════════════════
// DAILY PROBABILITY SCORES
//
// FinalScore(N) = baseRatePerDay × recencyMultiplier × certaintyBoost
//
// certaintyBoost = 10.0  if number is in cycle 5 remaining (guaranteed)
//               = 1.0   otherwise
// ═══════════════════════════════════════════════════════
function buildDailyScores(freqTable, recencyTable, remaining, statsMap) {
  const remainingSet = new Set(remaining);

  return [...freqTable.values()]
    .map((freq) => {
      const recency   = recencyTable.get(freq.number);
      const isCertain = remainingSet.has(freq.number);

      const baseRate    = freq.baseRatePerDay;
      const recencyMult = recency?.recencyMultiplier ?? 1.0;
      const certainty   = isCertain ? 10.0 : 1.0;
      const finalScore  = baseRate * recencyMult * certainty;

      return {
        number:         freq.number,
        finalScore:     parseFloat(finalScore.toFixed(8)),
        baseRate:       freq.baseRatePerDay,
        recencyMult:    recency?.recencyMultiplier ?? 1.0,
        overdueScore:   recency?.overdueScore ?? 1.0,
        daysSinceSeen:  recency?.daysSinceSeen ?? 0,
        avgGapDays:     freq.avgGapDays,
        isCertain,
        predictedPrize: freq.predictedPrize,
        prizeIsFixed:   freq.prizeIsFixed,
        preferredDOW:   freq.preferredDOW,
        avgAppearances: freq.avgAppearances,
      };
    })
    .sort((a, b) => b.finalScore - a.finalScore);
}

function printTopDailyScores(scores, topN) {
  const certainCount = scores.filter((s) => s.isCertain).length;

  console.log(`\n  Certain (cycle 5 remaining): ${certainCount}`);
  console.log(`  Top ${topN} combined (certain first, then highest probability):\n`);
  console.log(
    "  Rank | Number | Score    | BaseRate | OverdueScore | Gap   | Prize | Certain"
  );
  console.log("  " + "-".repeat(80));

  scores.slice(0, topN).forEach((s, i) => {
    console.log(
      `  ${String(i + 1).padEnd(4)} | ${s.number}   | ` +
      `${String(s.finalScore.toFixed(6)).padEnd(9)} | ` +
      `${String(s.baseRate.toFixed(5)).padEnd(8)} | ` +
      `${String(s.overdueScore + "x").padEnd(12)} | ` +
      `${String(s.avgGapDays).padEnd(5)} | ` +
      `${String(s.predictedPrize ?? "?").padEnd(5)} | ` +
      `${s.isCertain ? "✅ YES" : "no"}`
    );
  });
}

// ═══════════════════════════════════════════════════════
// BACKTEST VALIDATION
// Trains on cycles 2+3, tests on every draw day of cycle 4.
// Scores each number by frequency × recency each day,
// checks how many top-N predictions actually appeared.
// ═══════════════════════════════════════════════════════
function backtestFrequencyModel(trainCycles, cycle4) {
  if (!cycle4) { console.log("  ⚠️  Cycle 4 not found"); return; }

  const avgCycleDays =
    trainCycles.reduce((a, c) => a + c.totalDrawDays, 0) / trainCycles.length;

  // Build per-number appearance count across training cycles
  const appMap     = new Map();
  const cycleCount = new Map();

  for (const cycle of trainCycles) {
    const seenThisCycle = new Map();
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        seenThisCycle.set(number, (seenThisCycle.get(number) || 0) + 1);
      }
    }
    for (const [num, cnt] of seenThisCycle) {
      appMap.set(num, (appMap.get(num) || 0) + cnt);
      cycleCount.set(num, (cycleCount.get(num) || 0) + 1);
    }
  }

  // Build base rates for numbers appearing in both training cycles
  const baseRates = new Map();
  for (const [num, totalApp] of appMap) {
    if ((cycleCount.get(num) || 0) >= 2) {
      const avgApp = totalApp / trainCycles.length;
      baseRates.set(num, avgApp / avgCycleDays);
    }
  }

  const topNList   = [50, 100, 200, 300];
  const hits       = Object.fromEntries(topNList.map((n) => [n, 0]));
  const totalActual = { count: 0 };
  const lastSeenInC4 = new Map();

  for (const dayEntry of cycle4.drawEntries) {
    const currentDay = dayEntry.dayIndexInCycle;
    const actualSet  = new Set(dayEntry.numbers.map((n) => n.number));
    totalActual.count += actualSet.size;

    // Score each number: baseRate × recencyMultiplier
    const scored = [...baseRates.entries()].map(([num, rate]) => {
      const lastDay   = lastSeenInC4.get(num) ?? 0;
      const daysSince = currentDay - lastDay;
      const avgGap    = rate > 0 ? 1 / rate : 9999;
      const overdue   = Math.min(daysSince / avgGap, 3.0);
      return { num, score: rate * overdue };
    }).sort((a, b) => b.score - a.score);

    for (const topN of topNList) {
      const predictedSet = new Set(scored.slice(0, topN).map((s) => s.num));
      hits[topN] += [...actualSet].filter((n) => predictedSet.has(n)).length;
    }

    // Update last seen
    for (const { number } of dayEntry.numbers) {
      lastSeenInC4.set(number, currentDay);
    }
  }

  console.log(`\n  Backtest on cycle 4 (${cycle4.totalDrawDays} days):`);
  console.log(`  Total actual number appearances: ${totalActual.count.toLocaleString()}`);
  console.log(`\n  ⚠️  NOTE: Hit rate = hits / total appearances across ALL days`);
  console.log(`  Better metric: per-day hit rate (hits per draw day)\n`);
  console.log("  TopN | Total Hits | PerDay Hits | PerDay Hit% | Random Baseline");
  console.log("  " + "-".repeat(68));

  for (const topN of topNList) {
    const totalHits   = hits[topN];
    const perDayHits  = (totalHits / cycle4.totalDrawDays).toFixed(1);
    const perDayActual = (totalActual.count / cycle4.totalDrawDays).toFixed(1);
    const perDayPct   = ((totalHits / totalActual.count) * 100).toFixed(2);
    const randBase    = ((topN / 10000) * 100).toFixed(2);
    const beat        = parseFloat(perDayPct) > parseFloat(randBase) ? "✅ BEATS" : "❌ same";

    console.log(
      `  ${String(topN).padEnd(4)} | ${String(totalHits).padEnd(10)} | ` +
      `${String(perDayHits).padEnd(11)} | ` +
      `${String(perDayPct + "%").padEnd(11)} | ~${randBase}%  ${beat}`
    );
  }

  // Per-day breakdown: what % of each draw's numbers were predicted?
  console.log(`\n  Per-draw-day accuracy sample (first 10 days of cycle 4):`);
  console.log("  Day | Drawn | Top100 hits | Hit%  | Random%");
  console.log("  " + "-".repeat(48));

  const lastSeenSample = new Map();
  let sampleDay = 0;

  for (const dayEntry of cycle4.drawEntries) {
    if (sampleDay >= 10) break;
    sampleDay++;

    const currentDay = dayEntry.dayIndexInCycle;
    const actualSet  = new Set(dayEntry.numbers.map((n) => n.number));

    const scored = [...baseRates.entries()].map(([num, rate]) => {
      const lastDay   = lastSeenSample.get(num) ?? 0;
      const daysSince = currentDay - lastDay;
      const avgGap    = rate > 0 ? 1 / rate : 9999;
      const overdue   = Math.min(daysSince / avgGap, 3.0);
      return { num, score: rate * overdue };
    }).sort((a, b) => b.score - a.score);

    const top100Set = new Set(scored.slice(0, 100).map((s) => s.num));
    const dayHits   = [...actualSet].filter((n) => top100Set.has(n)).length;
    const dayPct    = ((dayHits / actualSet.size) * 100).toFixed(1);

    console.log(
      `  ${String(currentDay).padEnd(3)} | ${String(actualSet.size).padEnd(5)} | ` +
      `${String(dayHits).padEnd(11)} | ${String(dayPct + "%").padEnd(5)} | ~1.0%`
    );

    for (const { number } of dayEntry.numbers) {
      lastSeenSample.set(number, currentDay);
    }
  }
}

// ═══════════════════════════════════════════════════════
// GUARANTEED NUMBERS (cycle 5 remaining)
// All 53 numbers that MUST appear — sorted by urgency
// ═══════════════════════════════════════════════════════
function printGuaranteed(remaining, dailyScores, statsMap) {
  console.log(`\n  ${remaining.length} numbers GUARANTEED to appear before cycle 5 ends.\n`);

  // Enrich remaining with score data
  const scoreMap = new Map(dailyScores.map((s) => [s.number, s]));
  const enriched = remaining
    .map((num) => {
      const score = scoreMap.get(num);
      const stat  = statsMap.get(num);
      return {
        number:         num,
        overdueScore:   score?.overdueScore ?? 0,
        avgGapDays:     score?.avgGapDays ?? 0,
        predictedPrize: score?.predictedPrize ?? stat?.prizePrediction ?? "?",
        prizeIsFixed:   score?.prizeIsFixed ?? stat?.prizeIsAlwaysSame ?? false,
        preferredDOW:   score?.preferredDOW ?? stat?.preferredDOW ?? "?",
        baseRate:       score?.baseRate ?? 0,
        daysSinceSeen:  score?.daysSinceSeen ?? 0,
      };
    })
    .sort((a, b) => b.overdueScore - a.overdueScore);

  console.log("  Number | Prize | Fixed | PrefDOW | OverdueScore | DaysSince | Urgency");
  console.log("  " + "-".repeat(72));

  for (const e of enriched) {
    const urgency =
      e.overdueScore >= 4 ? "🔴 CRITICAL" :
      e.overdueScore >= 2 ? "🔴 HIGH"     :
      e.overdueScore >= 1 ? "🟡 MED"      :
                            "🟢 LOW";

    console.log(
      `  ${e.number}   | ${String(e.predictedPrize).padEnd(5)} | ` +
      `${e.prizeIsFixed ? "YES" : "no "} | ` +
      `${String(e.preferredDOW ?? "?").padEnd(7)} | ` +
      `${String(e.overdueScore + "x").padEnd(12)} | ` +
      `${String(e.daysSinceSeen).padEnd(9)} | ${urgency}`
    );
  }

  // Summary
  const critical = enriched.filter((e) => e.overdueScore >= 4).length;
  const high     = enriched.filter((e) => e.overdueScore >= 2 && e.overdueScore < 4).length;
  const med      = enriched.filter ((e) => e.overdueScore >= 1 && e.overdueScore < 2).length;
  const low      = enriched.filter((e) => e.overdueScore < 1).length;

  console.log(`\n  Urgency summary:`);
  console.log(`    🔴 CRITICAL (≥4x overdue): ${critical}`);
  console.log(`    🔴 HIGH     (≥2x overdue): ${high}`);
  console.log(`    🟡 MED      (≥1x overdue): ${med}`);
  console.log(`    🟢 LOW      (<1x overdue): ${low}`);

  // Prize breakdown for guaranteed numbers
  const prizeBreakdown = {};
  enriched.forEach((e) => {
    const p = String(e.predictedPrize ?? "unknown");
    prizeBreakdown[p] = (prizeBreakdown[p] || 0) + 1;
  });
  console.log(`\n  Prize breakdown for ${remaining.length} guaranteed numbers:`);
  for (const [prize, count] of Object.entries(prizeBreakdown).sort(
    (a, b) => Number(b[0]) - Number(a[0])
  )) {
    console.log(`    ₹${prize}: ${count} numbers`);
  }
}

// ═══════════════════════════════════════════════════════
// PRIZE MODEL
// Confidence = (topPrizeCount / totalPrizeDraws) × 100
// ═══════════════════════════════════════════════════════
function buildPrizeModel(statsMap) {
  const prizeMap = new Map();

  for (const [number, stat] of statsMap) {
    if (!stat.prizePrediction) continue;

    const history    = stat.prizeHistory ?? {};
    const totalDraws = Object.values(history).reduce((a, b) => a + b, 0);
    const topCount   = history[stat.prizePrediction] ?? 0;
    const confidence = totalDraws > 0
      ? parseFloat(((topCount / totalDraws) * 100).toFixed(1))
      : 0;

    prizeMap.set(number, {
      predictedPrize: stat.prizePrediction,
      isFixed:        stat.prizeIsAlwaysSame,
      confidence,
      prizeHistory:   history,
    });
  }

  return prizeMap;
}

function printPrizeModelSummary(prizeModel) {
  const vals    = [...prizeModel.values()];
  const fixed   = vals.filter((p) => p.isFixed).length;
  const conf90  = vals.filter((p) => p.confidence >= 90).length;
  const conf75  = vals.filter((p) => p.confidence >= 75).length;
  const conf50  = vals.filter((p) => p.confidence >= 50).length;

  const dist = {};
  vals.forEach((p) => {
    dist[p.predictedPrize] = (dist[p.predictedPrize] || 0) + 1;
  });

  console.log(`\n  Prize model coverage: ${prizeModel.size} numbers`);
  console.log(`\n  Confidence tiers:`);
  console.log(`    Fixed (100% consistent): ${fixed}`);
  console.log(`    ≥90% confidence:         ${conf90}`);
  console.log(`    ≥75% confidence:         ${conf75}`);
  console.log(`    ≥50% confidence:         ${conf50}`);

  console.log(`\n  Predicted prize distribution:`);
  const prizes = [5000, 2000, 1000, 500, 200, 100, 50];
  for (const prize of prizes) {
    const count = dist[prize] || 0;
    if (count === 0) continue;
    const bar = "█".repeat(Math.round(count / 100));
    console.log(
      `    ₹${String(prize).padEnd(5)}: ${String(count).padEnd(5)} numbers  ${bar}`
    );
  }

  // Fixed-prize sample
  const fixedSample = [...prizeModel.entries()]
    .filter(([, v]) => v.isFixed)
    .slice(0, 10);
  if (fixedSample.length > 0) {
    console.log(`\n  Sample fixed-prize numbers (always win same prize):`);
    fixedSample.forEach(([num, v]) => {
      console.log(`    ${num} → always ₹${v.predictedPrize}`);
    });
  }
}

// ═══════════════════════════════════════════════════════
// TOMORROW'S PREDICTION
// Layer 1 — Certain (remaining 53)
// Layer 2 — High probability (top non-certain by score)
// ═══════════════════════════════════════════════════════
function buildTomorrowPrediction(dailyScores, remaining, prizeModel, statsMap, topN) {
  const remainingSet = new Set(remaining);

  const certain = dailyScores
    .filter((s) => s.isCertain)
    .map((s) => ({
      ...s,
      layer:           1,
      layerLabel:      "CERTAIN",
      prizeConfidence: prizeModel.get(s.number)?.confidence ?? null,
    }));

  const highProb = dailyScores
    .filter((s) => !s.isCertain)
    .slice(0, Math.max(topN - certain.length, 0))
    .map((s) => ({
      ...s,
      layer:           2,
      layerLabel:      "HIGH PROB",
      prizeConfidence: prizeModel.get(s.number)?.confidence ?? null,
    }));

  return [...certain, ...highProb];
}

function printTomorrowPrediction(prediction) {
  const certain  = prediction.filter((p) => p.layer === 1);
  const highProb = prediction.filter((p) => p.layer === 2);

  console.log(
    `\n  ┌────────────────────────────────────────────────────────────┐`
  );
  console.log(
    `  │  LAYER 1 — CERTAIN (${certain.length} numbers, guaranteed before cycle ends)   │`
  );
  console.log(
    `  └────────────────────────────────────────────────────────────┘`
  );
  console.log(
    "  Number | Prize  | Fixed | PrefDOW | Overdue | DaysSince | Urgency"
  );
  console.log("  " + "-".repeat(68));

  certain.forEach((p) => {
    const urgency =
      p.overdueScore >= 4   ? "🔴 CRITICAL" :
      p.overdueScore >= 2   ? "🔴 HIGH"     :
      p.overdueScore >= 1   ? "🟡 MED"      :
                              "🟢 LOW";
    console.log(
      `  ${p.number}   | ${String(p.predictedPrize ?? "?").padEnd(6)} | ` +
      `${p.prizeIsFixed ? "YES" : "no "} | ` +
      `${String(p.preferredDOW ?? "?").padEnd(7)} | ` +
      `${String(p.overdueScore + "x").padEnd(7)} | ` +
      `${String(p.daysSinceSeen).padEnd(9)} | ${urgency}`
    );
  });

  console.log(
    `\n  ┌────────────────────────────────────────────────────────────┐`
  );
  console.log(
    `  │  LAYER 2 — HIGH PROBABILITY (top ${highProb.length} by frequency × recency)   │`
  );
  console.log(
    `  └────────────────────────────────────────────────────────────┘`
  );
  console.log(
    "  Rank | Number | Score    | BaseRate | Overdue | Prize  | Fixed | DOW"
  );
  console.log("  " + "-".repeat(72));

  highProb.slice(0, 50).forEach((p, i) => {
    console.log(
      `  ${String(i + 1).padEnd(4)} | ${p.number}   | ` +
      `${String(p.finalScore.toFixed(5)).padEnd(9)} | ` +
      `${String(p.baseRate.toFixed(4)).padEnd(8)} | ` +
      `${String(p.overdueScore + "x").padEnd(7)} | ` +
      `${String(p.predictedPrize ?? "?").padEnd(6)} | ` +
      `${p.prizeIsFixed ? "YES" : "no "} | ${p.preferredDOW ?? "?"}`
    );
  });

  if (highProb.length > 50) {
    console.log(`  ... and ${highProb.length - 50} more in phase3_output.json`);
  }
}

// ═══════════════════════════════════════════════════════
// CYCLE TRANSITION DETECTOR
// ═══════════════════════════════════════════════════════
function detectCycleTransition(currentCycle, remaining) {
  const remainingCount = remaining.length;

  const sizes = currentCycle.drawEntries.map((d) => d.numberCount);
  const avgDrawSize = sizes.reduce((a, b) => a + b, 0) / sizes.length;

  // Recent 7-day pace for new numbers
  const recentEntries = currentCycle.drawEntries.slice(-7);
  const recentNew     = recentEntries.map((d) => d.newNumbersAdded);
  const recentAvgNew  = recentNew.reduce((a, b) => a + b, 0) / recentNew.length;

  const estimatedDaysLeft = recentAvgNew > 0
    ? Math.ceil(remainingCount / recentAvgNew)
    : "unknown";

  console.log(`\n  Current cycle 5:`);
  console.log(`    Draw day:          ${currentCycle.totalDrawDays}`);
  console.log(`    Numbers drawn:     ${currentCycle.totalNumbersDrawn}/10000`);
  console.log(`    Remaining:         ${remainingCount}`);
  console.log(`    Avg draw size:     ${avgDrawSize.toFixed(0)} numbers/draw`);
  console.log(
    `    Recent new/day:    ${recentAvgNew.toFixed(1)} (last ${recentEntries.length} draws)`
  );
  console.log(`\n  🔮 Cycle 5 completion estimate:`);
  console.log(`    At recent pace → cycle 5 ends in ~${estimatedDaysLeft} more draw day(s)`);
  console.log(`\n  ⚡ Cycle 6 start signals:`);
  console.log(`    → When remaining = 0, cycle 6 begins on the SAME draw`);
  console.log(
    `    → Expect ~${Math.round(avgDrawSize * 0.7)}–${Math.round(avgDrawSize)} numbers on cycle 6 day 1`
  );

  if (remainingCount <= Math.ceil(avgDrawSize)) {
    console.log(`\n  🚨 ALERT: Only ${remainingCount} numbers remain!`);
    console.log(`    Average draw size is ~${avgDrawSize.toFixed(0)}.`);
    console.log(`    Cycle 5 WILL complete on the NEXT draw.`);
    console.log(`    Cycle 6 begins within that same draw day.`);
  }

  if (remainingCount <= 10) {
    console.log(`\n  ✅ IMMINENT: Cycle 5 ending NOW. Remaining numbers:`);
    remaining.forEach((n) => console.log(`    → ${n}`));
  }
}

// ─────────────────────────────────────────────────────
runPhase3().catch((err) => {
  console.error("❌ Phase 3 failed:", err);
  process.exit(1);
});