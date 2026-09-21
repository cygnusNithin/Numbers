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

// ─────────────────────────────────────────────────────
// SCORING WEIGHTS
// W1: earlier normalized position → higher score
// W2: lower std dev (consistent timing) → higher score
// W3: more appearances per cycle (hotter) → higher score
// W4: appeared in all training cycles → higher score
// ─────────────────────────────────────────────────────
const W1 = 2.5;
const W2 = 1.5;
const W3 = 0.8;
const W4 = 0.3;

// ─────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────
async function runPhase2() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  // ── Load all draws ──────────────────────────────────────────────────
  const draws     = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(draws);

  // ── Identify cycles ─────────────────────────────────────────────────
  const cycle1       = allCycles.find((c) => c.cycleNumber === 1);
  const currentCycle = allCycles.find((c) => !c.isComplete); // cycle 5

  // ── EXCLUDE CYCLE 1 ─────────────────────────────────────────────────
  // Cycle 1: 666 days vs 267–401 for cycles 2–4.
  // User confirmed data gaps — structurally incompatible.
  const validCycles    = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles    = validCycles.filter((c) => c.isComplete); // cycles 2, 3, 4
  const allValidCycles = validCycles;                             // cycles 2, 3, 4, 5

  // ── Overview ────────────────────────────────────────────────────────
  console.log("📋 CYCLE OVERVIEW:");
  console.log(
    `   Cycle 1: EXCLUDED (${cycle1?.totalDrawDays} days — data gaps confirmed)`
  );
  for (const c of validCycles) {
    const news   = c.drawEntries.map((d) => d.newNumbersAdded);
    const avgNew = (news.reduce((a, b) => a + b, 0) / news.length).toFixed(1);
    console.log(
      `   Cycle ${c.cycleNumber}: ${c.totalDrawDays} days | avg ${avgNew} new/day | ` +
        (c.isComplete
          ? "complete"
          : `IN PROGRESS (${c.totalNumbersDrawn}/10000, ${c.remainingNumbers} remaining)`)
    );
  }

  // ═══════════════════════════════════════════════════════════════════
  // STEP 1 — ERA ANALYSIS
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 1 — ERA ANALYSIS (cycles 2–5, cycle 1 excluded)");
  console.log("═".repeat(65));
  analyzeEras(validCycles);

  // ═══════════════════════════════════════════════════════════════════
  // STEP 2 — NORMALIZED PROFILES  (cycles 2, 3, 4)
  // firstAppearanceDay ÷ cycleTotalDays → 0.0 to 1.0
  // Makes cycle-2 (349d) and cycle-4 (267d) directly comparable
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — NORMALIZED POSITION PROFILES (cycles 2–4)");
  console.log("  Metric: firstAppearanceDay ÷ cycleTotalDays → 0.0 to 1.0");
  console.log("═".repeat(65));

  const normProfiles = buildNormalizedProfiles(allValidCycles);
  const normMap234   = buildNormStatsMap(normProfiles, trainCycles);
  const maxApp234    = Math.max(
    ...[...normMap234.values()].map((v) => v.avgAppearances)
  );

  printTopNormalizedNumbers(normMap234, 20);

  // ═══════════════════════════════════════════════════════════════════
  // STEP 3 — TRAIN / VALIDATE / TEST
  //   Train:    Cycle 2        → build model
  //   Validate: Cycle 3        → sanity check
  //   Test:     Cycle 4        → honest final accuracy
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — VALIDATION (Train: C2 | Validate: C3 | Test: C4)");
  console.log("═".repeat(65));

  // ── Train on cycle 2 → validate on cycle 3 ─────────────────────────
  const c2Only    = trainCycles.filter((c) => c.cycleNumber === 2);
  const normC2    = buildNormalizedProfiles([...c2Only, currentCycle]);
  const normMapC2 = buildNormStatsMap(normC2, c2Only);
  const maxAppC2  = Math.max(...[...normMapC2.values()].map((v) => v.avgAppearances));
  const modelC2   = buildNormScoringModel(normMapC2, c2Only.length, maxAppC2);

  const cycle3 = trainCycles.find((c) => c.cycleNumber === 3);
  validateWithWindows(modelC2, cycle3, "Cycle 3 (VALIDATE — trained on C2)");

  // ── Train on cycles 2+3 → test on cycle 4 ──────────────────────────
  const c23Only    = trainCycles.filter((c) => c.cycleNumber <= 3);
  const normC23    = buildNormalizedProfiles([...c23Only, currentCycle]);
  const normMapC23 = buildNormStatsMap(normC23, c23Only);
  const maxAppC23  = Math.max(...[...normMapC23.values()].map((v) => v.avgAppearances));
  const modelC23   = buildNormScoringModel(normMapC23, c23Only.length, maxAppC23);

  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  validateWithWindows(modelC23, cycle4, "Cycle 4 (TEST — trained on C2+C3)");

  // ═══════════════════════════════════════════════════════════════════
  // STEP 4 — WINDOW PERCENTAGE ACCURACY ON CYCLE 4
  // At what % through the cycle do our predictions first appear?
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — WINDOW PERCENTAGE ACCURACY ON CYCLE 4");
  console.log("  (what % of cycle passes before our top-N predictions appear?)");
  console.log("═".repeat(65));
  validateWindowPercentages(modelC23, cycle4);

  // ═══════════════════════════════════════════════════════════════════
  // STEP 5 — CYCLE 5 REMAINING (guaranteed to appear)
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — CYCLE 5 REMAINING (guaranteed to appear soon)");
  console.log("═".repeat(65));

  const rawProfiles = buildNumberProfiles(allValidCycles);
  const rawStats    = computeNumberStats(rawProfiles, allValidCycles.length);
  const rawStatsMap = new Map(rawStats.map((s) => [s.number, s]));
  const remaining   = getRemainingCycle5Numbers(rawProfiles, currentCycle.cycleNumber);

  printCycle5Remaining(remaining, normMap234, rawStatsMap);

  // ═══════════════════════════════════════════════════════════════════
  // STEP 6 — CYCLE 6 PREDICTION  (full model: cycles 2+3+4)
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — CYCLE 6 PREDICTION (trained on cycles 2–4)");
  console.log("═".repeat(65));

  const fullModel = buildNormScoringModel(normMap234, trainCycles.length, maxApp234);
  // normMap234 passed explicitly — no out-of-scope reference
  printCycle6Prediction(fullModel, trainCycles, normMap234, 500);

  // ═══════════════════════════════════════════════════════════════════
  // STEP 7 — CYCLE LENGTH PROJECTION
  // ═══════════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — CYCLE LENGTH PROJECTION");
  console.log("═".repeat(65));
  const projection = projectCycle6Length(validCycles);

  // ═══════════════════════════════════════════════════════════════════
  // EXPORT
  // ═══════════════════════════════════════════════════════════════════
  const output = {
    generatedAt:     new Date().toISOString(),
    excludedCycle:   1,
    trainingCycles:  [2, 3, 4],
    cycle5Remaining: remaining,
    cycle5RemainingCount: remaining.length,
    cycle6Prediction: fullModel.slice(0, 500).map((p) => ({
      number:          p.number,
      score:           p.score,
      avgNormFirstDay: p.avgNormFirstDay,
      stdNormFirstDay: p.stdNormFirstDay,
      avgAppearances:  p.avgAppearances,
      predictedPrize:  p.predictedPrize,
      preferredDOW:    p.preferredDOW,
    })),
    projection,
  };

  fs.writeFileSync("./phase2_v2_output.json", JSON.stringify(output, null, 2));
  console.log("\n✅ Phase 2 v2 complete → phase2_v2_output.json");
  await mongoose.disconnect();
}

// ═══════════════════════════════════════════════════════════════════
// ERA ANALYSIS
// ═══════════════════════════════════════════════════════════════════
function analyzeEras(cycles) {
  console.log("\n  Cycle | Days | AvgNew/Day | AvgDrawSize | Era");
  console.log("  " + "-".repeat(60));

  for (const c of cycles) {
    const news    = c.drawEntries.map((d) => d.newNumbersAdded);
    const sizes   = c.drawEntries.map((d) => d.numberCount);
    const avgNew  = news.reduce((a, b) => a + b, 0) / news.length;
    const avgSize = sizes.reduce((a, b) => a + b, 0) / sizes.length;
    const era =
      avgNew < 30 ? "ERA-2 (medium)" :
      avgNew < 60 ? "ERA-3 (fast)"   :
                    "ERA-4 (rapid)";

    console.log(
      `  ${String(c.cycleNumber).padEnd(5)} | ${String(c.totalDrawDays).padEnd(4)} | ` +
        `${String(avgNew.toFixed(1)).padEnd(10)} | ` +
        `${String(avgSize.toFixed(1)).padEnd(11)} | ${era}`
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
// NORMALIZED PROFILES
// For each number, record normFirstDay = actualFirstDay / cycleTotalDays
// This makes positions comparable across cycles of different lengths.
// ═══════════════════════════════════════════════════════════════════
function buildNormalizedProfiles(cycles) {
  const profiles = new Map();

  for (const cycle of cycles) {
    const cycleDays = cycle.totalDrawDays;
    const firstSeen = new Map(); // number → first dayIndex in this cycle
    const countSeen = new Map(); // number → total appearances in this cycle
    const metaFirst = new Map(); // number → { prize, dow } on first appearance

    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (!firstSeen.has(number)) {
          firstSeen.set(number, dayEntry.dayIndexInCycle);
          metaFirst.set(number, { prize, dow: dayEntry.dayOfWeek });
        }
        countSeen.set(number, (countSeen.get(number) || 0) + 1);
      }
    }

    for (const [number, firstDay] of firstSeen) {
      if (!profiles.has(number)) profiles.set(number, []);
      const meta = metaFirst.get(number);
      profiles.get(number).push({
        cycleNumber:    cycle.cycleNumber,
        actualFirstDay: firstDay,
        normFirstDay:   cycleDays > 0 ? firstDay / cycleDays : 0,
        cycleDays,
        appearances:    countSeen.get(number) || 1,
        prize:          meta.prize,
        dow:            meta.dow,
        isComplete:     cycle.isComplete,
      });
    }
  }

  return profiles;
}

// ═══════════════════════════════════════════════════════════════════
// BUILD NORMALIZED STATS MAP
// Computes per-number stats using only the specified training cycles.
// ═══════════════════════════════════════════════════════════════════
function buildNormStatsMap(profiles, trainCycles) {
  const trainNums = new Set(
    (Array.isArray(trainCycles) ? trainCycles : [trainCycles]).map(
      (c) => c.cycleNumber
    )
  );

  const map = new Map();

  for (const [number, history] of profiles) {
    // Only use completed training cycles
    const used = history.filter(
      (h) => h.isComplete && trainNums.has(h.cycleNumber)
    );
    if (used.length === 0) continue;

    // Normalized first-day stats
    const norms  = used.map((h) => h.normFirstDay);
    const avgN   = norms.reduce((a, b) => a + b, 0) / norms.length;
    const varN   = norms.reduce((s, d) => s + (d - avgN) ** 2, 0) / norms.length;
    const stdN   = Math.sqrt(varN);

    // Appearance stats
    const apps   = used.map((h) => h.appearances);
    const avgApp = apps.reduce((a, b) => a + b, 0) / apps.length;

    // Prize mode (most common first-appearance prize)
    const prizeFreq = {};
    used.forEach((h) => {
      prizeFreq[h.prize] = (prizeFreq[h.prize] || 0) + 1;
    });
    const topPrize = Object.entries(prizeFreq).sort((a, b) => b[1] - a[1])[0]?.[0];

    // Day-of-week mode
    const dowFreq = {};
    used.forEach((h) => {
      if (h.dow) dowFreq[h.dow] = (dowFreq[h.dow] || 0) + 1;
    });
    const topDOW = Object.entries(dowFreq).sort((a, b) => b[1] - a[1])[0]?.[0];

    map.set(number, {
      number,
      avgNormFirstDay:  parseFloat(avgN.toFixed(5)),
      stdNormFirstDay:  parseFloat(stdN.toFixed(5)),
      avgAppearances:   parseFloat(avgApp.toFixed(2)),
      appearedInCycles: used.length,
      totalTrainCycles: trainNums.size,
      predictedPrize:   topPrize ? Number(topPrize) : null,
      preferredDOW:     topDOW,
      prizeHistory:     prizeFreq,
    });
  }

  return map;
}

// ═══════════════════════════════════════════════════════════════════
// NORMALIZED SCORING MODEL
//
// Score(N) = (1 - avgNorm)^W1         ← earlier = higher
//          × (1/(stdNorm+0.01))^W2    ← consistent = higher
//          × (avgApp/maxApp)^W3       ← hotter = higher
//          × (appearedIn/total)^W4    ← full coverage = higher
// ═══════════════════════════════════════════════════════════════════
function buildNormScoringModel(normMap, totalCycles, maxAppearances) {
  return [...normMap.values()]
    .map((s) => {
      const w1 = Math.pow(1 - s.avgNormFirstDay, W1);
      const w2 = Math.pow(1 / (s.stdNormFirstDay + 0.01), W2);
      const w3 =
        maxAppearances > 0
          ? Math.pow(s.avgAppearances / maxAppearances, W3)
          : 0;
      const w4 = Math.pow(s.appearedInCycles / totalCycles, W4);
      const score = w1 * w2 * w3 * w4;

      return {
        number:           s.number,
        score:            parseFloat(score.toFixed(8)),
        avgNormFirstDay:  s.avgNormFirstDay,
        stdNormFirstDay:  s.stdNormFirstDay,
        avgAppearances:   s.avgAppearances,
        appearedInCycles: s.appearedInCycles,
        predictedPrize:   s.predictedPrize,
        preferredDOW:     s.preferredDOW,
      };
    })
    .sort((a, b) => b.score - a.score);
}

// ═══════════════════════════════════════════════════════════════════
// PRINT TOP NORMALIZED NUMBERS
// ═══════════════════════════════════════════════════════════════════
function printTopNormalizedNumbers(normMap, topN) {
  const sorted = [...normMap.values()]
    .filter((s) => s.avgNormFirstDay !== null)
    .sort((a, b) => a.avgNormFirstDay - b.avgNormFirstDay);

  console.log(`\n  Top ${topN} earliest numbers (by avg normalized position across cycles 2–4):`);
  console.log("  Number | AvgNormPos | StdNorm | AvgApp | Prize | PrefDOW");
  console.log("  " + "-".repeat(60));

  for (const s of sorted.slice(0, topN)) {
    console.log(
      `  ${s.number}   | ${String(s.avgNormFirstDay).padEnd(10)} | ` +
        `${String(s.stdNormFirstDay).padEnd(7)} | ` +
        `${String(s.avgAppearances).padEnd(6)} | ` +
        `${String(s.predictedPrize ?? "?").padEnd(5)} | ${s.preferredDOW ?? "?"}`
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
// VALIDATE WITH WINDOWS
// Hit rate at day-1, days 1-3, 1-5, 1-7, 1-14 for multiple topN.
// Also shows the random baseline for each topN.
// ═══════════════════════════════════════════════════════════════════
function validateWithWindows(model, targetCycle, label) {
  if (!targetCycle) {
    console.log(`  ⚠️  ${label}: cycle not found`);
    return null;
  }

  // Collect new numbers per draw day
  const newByDay = new Map();
  for (const dayEntry of targetCycle.drawEntries) {
    newByDay.set(
      dayEntry.dayIndexInCycle,
      dayEntry.numbers.filter((n) => n.isNew).map((n) => n.number)
    );
  }

  // Build cumulative sets at each window boundary
  const windows    = [1, 2, 3, 5, 7, 14];
  const cumSets    = {};
  const cumulative = new Set();

  for (let d = 1; d <= targetCycle.totalDrawDays; d++) {
    (newByDay.get(d) || []).forEach((n) => cumulative.add(n));
    if (windows.includes(d)) cumSets[d] = new Set([...cumulative]);
  }
  // Fill any window beyond cycle length with the final set
  windows.forEach((w) => {
    if (!cumSets[w]) cumSets[w] = new Set([...cumulative]);
  });

  console.log(`\n  ${label} (${targetCycle.totalDrawDays} draw days):`);
  windows.forEach((w) =>
    console.log(`    Day 1–${w} actual new numbers: ${cumSets[w].size}`)
  );

  console.log(
    `\n  TopN  | Day1 H/%   | D1-3 H/%   | D1-5 H/%   | D1-7 H/%   | D1-14 H/%  | Random%`
  );
  console.log("  " + "-".repeat(92));

  const results = [];
  for (const topN of [258, 300, 400, 500, 750, 1000, 2000]) {
    const predicted = new Set(model.slice(0, topN).map((p) => p.number));

    const cells = windows.slice(0, 5).map((w) => {
      const actual = cumSets[w];
      const hits   = [...actual].filter((n) => predicted.has(n)).length;
      const pct    = actual.size > 0
        ? ((hits / actual.size) * 100).toFixed(1)
        : "0";
      return `${hits}/${pct}%`;
    });

    const randomBaseline = ((topN / 10000) * 100).toFixed(1);

    console.log(
      `  ${String(topN).padEnd(5)} | ${cells[0].padEnd(11)} | ` +
        `${cells[1].padEnd(11)} | ${cells[2].padEnd(11)} | ` +
        `${cells[3].padEnd(11)} | ${cells[4].padEnd(11)} | ${randomBaseline}%`
    );

    results.push({ topN, cells, randomBaseline });
  }

  return results;
}

// ═══════════════════════════════════════════════════════════════════
// WINDOW PERCENTAGE ACCURACY ON CYCLE 4
// Shows hit rate as we move through each % of the cycle.
// ═══════════════════════════════════════════════════════════════════
function validateWindowPercentages(model, targetCycle) {
  if (!targetCycle) return;

  const newByDay = new Map();
  for (const dayEntry of targetCycle.drawEntries) {
    newByDay.set(
      dayEntry.dayIndexInCycle,
      dayEntry.numbers.filter((n) => n.isNew).map((n) => n.number)
    );
  }

  const topNList      = [300, 400, 500];
  const predictedSets = {};
  topNList.forEach((n) => {
    predictedSets[n] = new Set(model.slice(0, n).map((p) => p.number));
  });

  const pctPoints = [1, 2, 5, 10, 15, 20, 30, 50, 75, 100];
  const cycleDays = targetCycle.totalDrawDays;

  console.log(`\n  Cycle 4: ${cycleDays} draw days`);
  console.log(
    `\n  CyclePct | ActualNew | Top300 H/%  | Top400 H/%  | Top500 H/%  | Random`
  );
  console.log("  " + "-".repeat(82));

  const cumulative = new Set();
  let lastDayLimit = 0;

  for (const pct of pctPoints) {
    const dayLimit = Math.ceil((pct / 100) * cycleDays);
    for (let d = lastDayLimit + 1; d <= dayLimit; d++) {
      (newByDay.get(d) || []).forEach((n) => cumulative.add(n));
    }
    lastDayLimit = dayLimit;

    const actual = cumulative.size;
    const cols   = topNList.map((n) => {
      const hits = [...cumulative].filter((num) => predictedSets[n].has(num)).length;
      const hp   = actual > 0 ? ((hits / actual) * 100).toFixed(1) : "0";
      return `${hits}/${hp}%`;
    });

    const randomPct = actual > 0
      ? ((300 / 10000) * 100).toFixed(1)
      : "0";

    console.log(
      `  ${String(pct + "%").padEnd(8)} | ${String(actual).padEnd(9)} | ` +
        `${cols[0].padEnd(12)} | ${cols[1].padEnd(12)} | ` +
        `${cols[2].padEnd(12)} | ~4.0%`
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
// CYCLE 5 REMAINING
// Urgency based on normalized position:
//   🔴 HIGH  — normally appears in first 10% of cycle (overdue)
//   🟡 MED   — normally appears in first 25% of cycle
//   🟢 LOW   — normally appears in second half of cycle
// ═══════════════════════════════════════════════════════════════════
function printCycle5Remaining(remaining, normMap, rawStatsMap) {
  console.log(`\n  ${remaining.length} numbers guaranteed in upcoming draws.\n`);
  console.log(
    "  Number | NormPos | StdNorm | AvgApp | Prize | Fixed | PrefDOW | Urgency"
  );
  console.log("  " + "-".repeat(78));

  const enriched = remaining
    .map((n) => {
      const norm = normMap.get(n);
      const raw  = rawStatsMap.get(n);
      const urgency = norm
        ? norm.avgNormFirstDay < 0.1  ? "🔴 HIGH"
        : norm.avgNormFirstDay < 0.25 ? "🟡 MED"
        :                               "🟢 LOW"
        : "?";
      return { number: n, norm, raw, urgency };
    })
    .sort(
      (a, b) => (a.norm?.avgNormFirstDay ?? 9) - (b.norm?.avgNormFirstDay ?? 9)
    );

  for (const { number, norm, raw, urgency } of enriched) {
    console.log(
      `  ${number}   | ${String(norm?.avgNormFirstDay ?? "?").padEnd(7)} | ` +
        `${String(norm?.stdNormFirstDay ?? "?").padEnd(7)} | ` +
        `${String(norm?.avgAppearances ?? "?").padEnd(6)} | ` +
        `${String(raw?.prizePrediction ?? "?").padEnd(5)} | ` +
        `${raw?.prizeIsAlwaysSame ? "YES" : "no "} | ` +
        `${String(norm?.preferredDOW ?? "?").padEnd(7)} | ${urgency}`
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
// CYCLE 6 PREDICTION PRINT
// normMap passed explicitly — no out-of-scope reference
// ═══════════════════════════════════════════════════════════════════
function printCycle6Prediction(model, trainCycles, normMap, topN) {
  // Average new numbers in first 7 days across training cycles
  const first7AvgList = trainCycles.map((c) => {
    const seen = new Set();
    c.drawEntries
      .slice(0, 7)
      .forEach((d) =>
        d.numbers.filter((n) => n.isNew).forEach((n) => seen.add(n.number))
      );
    return seen.size;
  });
  const avgFirst7 = Math.round(
    first7AvgList.reduce((a, b) => a + b, 0) / first7AvgList.length
  );

  console.log(`\n  Avg new numbers in first 7 days of cycles 2–4: ~${avgFirst7}`);
  console.log(`  Top ${topN} predictions for cycle 6 (ranked by normalized score)\n`);
  console.log(
    "  Rank | Number | NormPos | StdNorm | AvgApp | Prize  | Fixed | PrefDOW"
  );
  console.log("  " + "-".repeat(72));

  model.slice(0, 50).forEach((p, i) => {
    // Prize fixed: look up from passed normMap (no out-of-scope reference)
    const entry      = normMap.get(p.number);
    const prizeFixed =
      entry && Object.keys(entry.prizeHistory).length === 1 ? "YES" : "no ";

    console.log(
      `  ${String(i + 1).padEnd(4)} | ${p.number}   | ` +
        `${String(p.avgNormFirstDay).padEnd(7)} | ` +
        `${String(p.stdNormFirstDay).padEnd(7)} | ` +
        `${String(p.avgAppearances).padEnd(6)} | ` +
        `${String(p.predictedPrize ?? "?").padEnd(6)} | ` +
        `${prizeFixed} | ${p.preferredDOW ?? "?"}`
    );
  });

  console.log(`\n  ... full list of ${topN} numbers saved to phase2_v2_output.json`);
}

// ═══════════════════════════════════════════════════════════════════
// CYCLE LENGTH PROJECTION
// Linear regression on avg new/day across cycles 2, 3, 4
// Also shows projection if cycle 6 matches cycle 5's pace
// ═══════════════════════════════════════════════════════════════════
function projectCycle6Length(cycles) {
  const completed = cycles.filter((c) => c.isComplete);
  const current   = cycles.find((c) => !c.isComplete);

  const data = completed.map((c) => {
    const news   = c.drawEntries.map((d) => d.newNumbersAdded);
    const avgNew = news.reduce((a, b) => a + b, 0) / news.length;
    return { cycleNumber: c.cycleNumber, days: c.totalDrawDays, avgNew };
  });

  // Linear regression
  const n      = data.length;
  const xMean  = (n - 1) / 2;
  const yMean  = data.reduce((a, b) => a + b.avgNew, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) {
    num += (i - xMean) * (data[i].avgNew - yMean);
    den += (i - xMean) ** 2;
  }
  const slope     = den ? num / den : 0;
  const intercept = yMean - slope * xMean;
  const projNew   = Math.max(intercept + slope * n, 1);
  const projDays  = Math.ceil(10000 / projNew);

  // Cycle 5 actual pace
  const c5News = current.drawEntries.map((d) => d.newNumbersAdded);
  const c5Avg  = c5News.reduce((a, b) => a + b, 0) / c5News.length;
  const c5Proj = Math.ceil(10000 / c5Avg);

  console.log("\n  Completed cycle data (cycles 2–4):");
  data.forEach((d) =>
    console.log(
      `    Cycle ${d.cycleNumber}: ${d.days} days | ${d.avgNew.toFixed(1)} new/day`
    )
  );

  console.log(`\n  Trend slope:               +${slope.toFixed(2)} new/day per cycle`);
  console.log(`  Projected cycle 6 new/day: ~${projNew.toFixed(1)}`);
  console.log(`  Projected cycle 6 length:  ~${projDays} days`);
  console.log(`\n  Cycle 5 actual pace:        ${c5Avg.toFixed(1)} new/day`);
  console.log(`  If cycle 6 = cycle 5 pace:  ~${c5Proj} days`);
  console.log(
    `\n  ⚠️  Cycle 5 is running much faster than cycles 2–4.` +
    `\n      Cycle 6 is likely ${c5Proj}–${projDays} days long.`
  );

  return {
    trendSlope:            parseFloat(slope.toFixed(2)),
    projectedNewPerDay:    parseFloat(projNew.toFixed(1)),
    projectedCycleDays:    projDays,
    cycle5ActualNewPerDay: parseFloat(c5Avg.toFixed(1)),
    cycle5ProjDays:        c5Proj,
  };
}

// ─────────────────────────────────────────────────────
runPhase2().catch((err) => {
  console.error("❌ Phase 2 v2 failed:", err);
  process.exit(1);
});