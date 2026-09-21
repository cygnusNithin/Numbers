require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 5 — PRIZE CYCLES
//
// Core question: Does each number's prize follow a pattern
// across cycles? If so, can we predict cycle 5's prize?
//
// Patterns we look for:
//   FIXED      — same prize every cycle (e.g. always ₹100)
//   ALTERNATING — two prizes that swap (e.g. ₹500 → ₹100 → ₹500)
//   ASCENDING   — prize goes up each cycle
//   DESCENDING  — prize goes down each cycle
//   ROTATING    — 3+ prizes in a repeating sequence
//   STABLE      — varies but within one tier
//   VARIABLE    — no detectable pattern
// ═══════════════════════════════════════════════════════════════

const PRIZE_RANKS = { 5000: 6, 2000: 5, 1000: 4, 500: 3, 200: 2, 100: 1, 50: 0 };
const PRIZES_DESC = [5000, 2000, 1000, 500, 200, 100, 50];

async function runPhase5() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const draws      = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles  = detectCycles(draws);

  // Exclude cycle 1 — data gaps confirmed
  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete); // 2, 3, 4
  const currentCycle = validCycles.find((c) => !c.isComplete);  // 5

  console.log("📋 CYCLE OVERVIEW:");
  console.log(`   Excluded: Cycle 1 (data gaps)`);
  validCycles.forEach((c) => {
    console.log(
      `   Cycle ${c.cycleNumber}: ${c.totalDrawDays} days | ` +
      `${c.isComplete
        ? "complete"
        : `IN PROGRESS (${c.totalNumbersDrawn}/10000, ${c.remainingNumbers} remaining)`}`
    );
  });

  // ═══════════════════════════════════════════════════════
  // STEP 1 — BUILD PRIZE HISTORY PER NUMBER PER CYCLE
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 1 — PRIZE HISTORY (first-appearance prize per cycle)");
  console.log("═".repeat(65));

  const prizeHistory = buildPrizeHistory(validCycles);
  printPrizeHistoryStats(prizeHistory, trainCycles, currentCycle);

  // ═══════════════════════════════════════════════════════
  // STEP 2 — DETECT PRIZE PATTERNS
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — PRIZE PATTERN DETECTION");
  console.log("═".repeat(65));

  const patterns = detectPrizePatterns(prizeHistory, trainCycles);
  printPatternSummary(patterns);

  // ═══════════════════════════════════════════════════════
  // STEP 3 — PRIZE TIER ROTATION ANALYSIS
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — PRIZE TIER ROTATION ANALYSIS");
  console.log("  (Which numbers win each prize tier, cycle by cycle?)");
  console.log("═".repeat(65));

  const tierRotation = analyzePrizeTierRotation(trainCycles);
  printTierRotation(tierRotation);

  // ═══════════════════════════════════════════════════════
  // STEP 4 — VALIDATION (Train C2+C3 → Test C4)
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — PRIZE PREDICTION VALIDATION (Train: C2+C3 → Test: C4)");
  console.log("═".repeat(65));

  const c23       = trainCycles.filter((c) => c.cycleNumber <= 3);
  const cycle4    = trainCycles.find((c) => c.cycleNumber === 4);
  const valResult = validatePrizePrediction(prizeHistory, c23, cycle4);
  printValidationResult(valResult);

  // ═══════════════════════════════════════════════════════
  // STEP 5 — CYCLE 5 PRIZE PREDICTIONS
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — CYCLE 5 PRIZE PREDICTIONS (all 10,000 numbers)");
  console.log("═".repeat(65));

  const cycle5Predictions = predictCycle5Prizes(prizeHistory, patterns, trainCycles);
  printCycle5PrizePredictions(cycle5Predictions);

  // ═══════════════════════════════════════════════════════
  // STEP 6 — HIGH-VALUE PRIZE FOCUS (₹1000+)
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — HIGH-VALUE PRIZE PREDICTIONS (₹1000+)");
  console.log("═".repeat(65));

  const remaining = getRemainingNumbers(currentCycle);
  printHighValuePredictions(cycle5Predictions, remaining);

  // ═══════════════════════════════════════════════════════
  // STEP 7 — GUARANTEED 53 + PRIZE PREDICTION
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — GUARANTEED REMAINING 53 + PRIZE PREDICTION");
  console.log("═".repeat(65));

  printRemainingWithPrize(remaining, cycle5Predictions, prizeHistory);

  // ═══════════════════════════════════════════════════════
  // STEP 8 — PRIZE CYCLE TABLE (top 100 interesting numbers)
  // ═══════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 8 — PRIZE CYCLE TABLE (non-₹100 or clearly patterned)");
  console.log("═".repeat(65));

  printPrizeCycleTable(prizeHistory, cycle5Predictions, patterns, trainCycles);

  // ═══════════════════════════════════════════════════════
  // EXPORT
  // ═══════════════════════════════════════════════════════
  const output = {
    generatedAt:     new Date().toISOString(),
    trainingCycles:  [2, 3, 4],
    patternSummary:  summarizePatterns(patterns),
    validationAccuracy: valResult.summary,
    cycle5Predictions: cycle5Predictions.map((p) => ({
      number:         p.number,
      predictedPrize: p.predictedPrize,
      patternType:    p.patternType,
      confidence:     p.confidence,
      prizeSequence:  p.prizeSequence,
    })),
    highValueTargets: cycle5Predictions
      .filter((p) => (p.predictedPrize ?? 0) >= 1000)
      .map((p) => ({
        number:         p.number,
        predictedPrize: p.predictedPrize,
        patternType:    p.patternType,
        confidence:     p.confidence,
        prizeSequence:  p.prizeSequence,
        isRemaining:    remaining.includes(p.number),
      })),
    remaining53WithPrize: remaining.map((num) => {
      const pred = cycle5Predictions.find((p) => p.number === num);
      return {
        number:         num,
        predictedPrize: pred?.predictedPrize ?? null,
        patternType:    pred?.patternType ?? null,
        confidence:     pred?.confidence ?? null,
        prizeSequence:  pred?.prizeSequence ?? [],
      };
    }),
  };

  fs.writeFileSync("./phase5_output.json", JSON.stringify(output, null, 2));
  console.log("\n✅ Phase 5 complete → phase5_output.json");
  await mongoose.disconnect();
}

// ═══════════════════════════════════════════════════════════════
// BUILD PRIZE HISTORY
// For each number, what prize did it win FIRST in each cycle?
// Returns: Map<number_string, Map<cycleNumber, prize>>
// ═══════════════════════════════════════════════════════════════
function buildPrizeHistory(cycles) {
  const history = new Map();

  for (const cycle of cycles) {
    const firstPrize = new Map(); // number → prize on first appearance this cycle

    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (isNew && !firstPrize.has(number)) {
          firstPrize.set(number, prize);
        }
      }
    }

    for (const [number, prize] of firstPrize) {
      if (!history.has(number)) history.set(number, new Map());
      history.get(number).set(cycle.cycleNumber, prize);
    }
  }

  return history;
}

function printPrizeHistoryStats(history, trainCycles, currentCycle) {
  const trainNums = new Set(trainCycles.map((c) => c.cycleNumber));
  let allThree = 0, twoOf3 = 0, oneOf3 = 0;

  for (const [, cycleMap] of history) {
    const count = [...cycleMap.keys()].filter((cn) => trainNums.has(cn)).length;
    if (count === 3) allThree++;
    else if (count === 2) twoOf3++;
    else if (count === 1) oneOf3++;
  }

  let drawnInC5 = 0;
  for (const [, cycleMap] of history) {
    if (cycleMap.has(currentCycle.cycleNumber)) drawnInC5++;
  }

  console.log(`\n  Total numbers with prize data:                ${history.size}`);
  console.log(`  Prize data in all 3 training cycles (2,3,4):  ${allThree}`);
  console.log(`  Prize data in 2 of 3 training cycles:         ${twoOf3}`);
  console.log(`  Prize data in 1 of 3 training cycles:         ${oneOf3}`);
  console.log(`  Numbers drawn in cycle 5 so far:              ${drawnInC5}`);

  console.log(`\n  Prize distribution per cycle:`);
  console.log(`  Prize  | Cycle 2 | Cycle 3 | Cycle 4 | Cycle 5`);
  console.log(`  ` + "-".repeat(50));

  const c5Num = currentCycle.cycleNumber;
  for (const prize of PRIZES_DESC) {
    const counts = [2, 3, 4, c5Num].map((cn) => {
      let n = 0;
      for (const [, cycleMap] of history) {
        if (cycleMap.get(cn) === prize) n++;
      }
      return n;
    });
    const row = counts.map((c) => String(c).padEnd(7)).join(" | ");
    console.log(`  ₹${String(prize).padEnd(5)} | ${row}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// PATTERN DETECTION
// ═══════════════════════════════════════════════════════════════
function classifyPattern(sequence) {
  if (!sequence || sequence.length === 0) return "NO_DATA";
  if (sequence.length === 1) return "SINGLE";

  const unique = [...new Set(sequence)];
  if (unique.length === 1) return "FIXED";

  if (sequence.length >= 3 && unique.length === 2) {
    const isAlt = sequence.every((v, i) => i < 2 || v === sequence[i % 2]);
    if (isAlt) return "ALTERNATING";
  }

  if (sequence.length === 3 && unique.length === 3) return "ROTATING";

  const ranks      = sequence.map((p) => PRIZE_RANKS[p] ?? -1);
  const strictAsc  = ranks.every((r, i) => i === 0 || r > ranks[i - 1]);
  const strictDesc = ranks.every((r, i) => i === 0 || r < ranks[i - 1]);
  if (strictAsc)  return "ASCENDING";
  if (strictDesc) return "DESCENDING";

  const maxR = Math.max(...ranks);
  const minR = Math.min(...ranks);
  if (maxR - minR <= 1) return "STABLE";

  return "VARIABLE";
}

function predictNextPrize(sequence, patternType) {
  if (!sequence || sequence.length === 0) return null;
  const last = sequence[sequence.length - 1];

  switch (patternType) {
    case "FIXED":
      return sequence[0];

    case "ALTERNATING": {
      const idx = sequence.length % 2;
      return sequence[idx];
    }

    case "ROTATING": {
      const idx = sequence.length % 3;
      return sequence[idx];
    }

    case "ASCENDING": {
      const lastRank = PRIZE_RANKS[last] ?? 0;
      const nextRank = Math.min(lastRank + 1, 6);
      return PRIZES_DESC.find((p) => PRIZE_RANKS[p] === nextRank) ?? last;
    }

    case "DESCENDING": {
      const lastRank = PRIZE_RANKS[last] ?? 0;
      const nextRank = Math.max(lastRank - 1, 0);
      return PRIZES_DESC.find((p) => PRIZE_RANKS[p] === nextRank) ?? last;
    }

    case "STABLE":
    case "VARIABLE":
    case "SINGLE":
    default: {
      // Return mode (most common prize)
      const freq = {};
      sequence.forEach((p) => { freq[p] = (freq[p] || 0) + 1; });
      return Number(Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0]);
    }
  }
}

function computePatternConfidence(sequence, patternType) {
  if (!sequence || sequence.length === 0) return 0;
  const base = {
    FIXED:       100,
    ALTERNATING:  85,
    ROTATING:     80,
    ASCENDING:    70,
    DESCENDING:   70,
    STABLE:       50,
    SINGLE:       40,
    VARIABLE:     25,
    NO_DATA:       0,
  };
  const dataBoost = Math.min((sequence.length - 1) * 5, 15);
  return Math.min((base[patternType] ?? 25) + dataBoost, 100);
}

function detectPrizePatterns(history, trainCycles) {
  const trainNums = trainCycles.map((c) => c.cycleNumber).sort((a, b) => a - b);
  const patterns  = new Map();

  for (const [number, cycleMap] of history) {
    const sequence = trainNums
      .map((cn) => cycleMap.get(cn))
      .filter((p) => p !== undefined && p !== null);

    if (sequence.length === 0) continue;

    const patternType    = classifyPattern(sequence);
    const predictedPrize = predictNextPrize(sequence, patternType);
    const confidence     = computePatternConfidence(sequence, patternType);

    patterns.set(number, {
      number,
      prizeSequence:  sequence,
      cyclesPresent:  sequence.length,
      patternType,
      predictedPrize,
      confidence,
    });
  }

  return patterns;
}

function printPatternSummary(patterns) {
  const counts = {};
  let totalConf = 0;

  for (const p of patterns.values()) {
    counts[p.patternType] = (counts[p.patternType] || 0) + 1;
    totalConf += p.confidence;
  }

  const total   = patterns.size;
  const avgConf = total > 0 ? (totalConf / total).toFixed(1) : 0;

  console.log(`\n  Total numbers classified: ${total}`);
  console.log(`  Average prediction confidence: ${avgConf}%\n`);
  console.log("  Pattern Type       | Count  | %      | Avg Confidence");
  console.log("  " + "-".repeat(57));

  const ordered = [
    "FIXED", "ALTERNATING", "ROTATING",
    "ASCENDING", "DESCENDING",
    "STABLE", "SINGLE", "VARIABLE",
  ];

  for (const type of ordered) {
    const count = counts[type] || 0;
    if (count === 0) continue;
    const pct = ((count / total) * 100).toFixed(1);

    let confSum = 0, confN = 0;
    for (const p of patterns.values()) {
      if (p.patternType === type) { confSum += p.confidence; confN++; }
    }
    const avgC = confN > 0 ? (confSum / confN).toFixed(1) : "0";

    console.log(
      `  ${String(type).padEnd(18)} | ${String(count).padEnd(6)} | ` +
      `${String(pct + "%").padEnd(6)} | ${avgC}%`
    );
  }

  // Sample of each interesting pattern
  const showTypes = ["FIXED", "ALTERNATING", "ROTATING", "ASCENDING", "DESCENDING"];
  console.log(`\n  Samples per pattern:`);
  for (const type of showTypes) {
    const samples = [...patterns.values()]
      .filter((p) => p.patternType === type)
      .slice(0, 5);
    if (samples.length === 0) continue;
    console.log(`\n  ${type}:`);
    samples.forEach((p) => {
      const seq = p.prizeSequence.map((v) => `₹${v}`).join(" → ");
      console.log(
        `    ${p.number}: ${seq} → predict ₹${p.predictedPrize} (${p.confidence}% conf)`
      );
    });
  }
}

function summarizePatterns(patterns) {
  const counts = {};
  for (const p of patterns.values()) {
    counts[p.patternType] = (counts[p.patternType] || 0) + 1;
  }
  return counts;
}

// ═══════════════════════════════════════════════════════════════
// PRIZE TIER ROTATION ANALYSIS
// ═══════════════════════════════════════════════════════════════
function analyzePrizeTierRotation(trainCycles) {
  const tierData = {};
  for (const prize of PRIZES_DESC) {
    tierData[prize] = {};
    for (const cycle of trainCycles) {
      tierData[prize][cycle.cycleNumber] = new Set();
    }
  }

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (isNew && tierData[prize] && tierData[prize][cycle.cycleNumber]) {
          tierData[prize][cycle.cycleNumber].add(number);
        }
      }
    }
  }

  const rotation = {};

  for (const prize of PRIZES_DESC) {
    const cycleSets = Object.entries(tierData[prize])
      .sort((a, b) => Number(a[0]) - Number(b[0]))
      .map(([cn, set]) => ({ cycleNumber: Number(cn), numbers: set }));

    if (cycleSets.length < 2) continue;

    const overlaps = [];
    for (let i = 0; i < cycleSets.length - 1; i++) {
      for (let j = i + 1; j < cycleSets.length; j++) {
        const setA  = cycleSets[i].numbers;
        const setB  = cycleSets[j].numbers;
        const inter = [...setA].filter((n) => setB.has(n));
        const union = new Set([...setA, ...setB]);
        overlaps.push({
          cycles:       [cycleSets[i].cycleNumber, cycleSets[j].cycleNumber],
          shared:       inter.length,
          totalA:       setA.size,
          totalB:       setB.size,
          jaccardSim:   union.size > 0
            ? parseFloat((inter.length / union.size).toFixed(4))
            : 0,
          sharedNumbers: inter.slice(0, 10),
        });
      }
    }

    let inAll = null;
    for (const cs of cycleSets) {
      inAll = inAll === null
        ? new Set([...cs.numbers])
        : new Set([...inAll].filter((n) => cs.numbers.has(n)));
    }
    inAll = inAll ?? new Set();

    rotation[prize] = {
      prize,
      countPerCycle:    cycleSets.map((cs) => ({ cycle: cs.cycleNumber, count: cs.numbers.size })),
      overlaps,
      inAllCycles:      [...inAll],
      inAllCyclesCount: inAll.size,
    };
  }

  return rotation;
}

function printTierRotation(tierRotation) {
  console.log(`\n  Prize | C2     | C3     | C4     | InAll3 | C2∩C3 | C3∩C4 | Overlap%`);
  console.log(`  ` + "-".repeat(72));

  for (const prize of PRIZES_DESC) {
    const data = tierRotation[prize];
    if (!data) continue;

    const c2    = data.countPerCycle.find((c) => c.cycle === 2)?.count ?? 0;
    const c3    = data.countPerCycle.find((c) => c.cycle === 3)?.count ?? 0;
    const c4    = data.countPerCycle.find((c) => c.cycle === 4)?.count ?? 0;
    const inAll = data.inAllCyclesCount;

    const ov23  = data.overlaps.find((o) => o.cycles[0] === 2 && o.cycles[1] === 3);
    const ov34  = data.overlaps.find((o) => o.cycles[0] === 3 && o.cycles[1] === 4);

    const pct23 = ov23 && Math.min(c2, c3) > 0
      ? ((ov23.shared / Math.min(c2, c3)) * 100).toFixed(1)
      : "0";
    const pct34 = ov34 && Math.min(c3, c4) > 0
      ? ((ov34.shared / Math.min(c3, c4)) * 100).toFixed(1)
      : "0";
    const avgPct = ((parseFloat(pct23) + parseFloat(pct34)) / 2).toFixed(1);

    console.log(
      `  ₹${String(prize).padEnd(5)} | ${String(c2).padEnd(6)} | ` +
      `${String(c3).padEnd(6)} | ${String(c4).padEnd(6)} | ` +
      `${String(inAll).padEnd(6)} | ${String(ov23?.shared ?? 0).padEnd(5)} | ` +
      `${String(ov34?.shared ?? 0).padEnd(5)} | ~${avgPct}%`
    );
  }

  // Detail for high-value prizes
  for (const prize of [5000, 2000, 1000]) {
    const data = tierRotation[prize];
    if (!data) continue;

    console.log(`\n  ₹${prize} DETAIL:`);
    console.log(
      `    Count per cycle: ` +
      data.countPerCycle.map((c) => `C${c.cycle}=${c.count}`).join(", ")
    );

    if (data.inAllCyclesCount > 0) {
      console.log(`    Numbers in ALL 3 cycles (${data.inAllCyclesCount}):`);
      const chunks = data.inAllCycles.slice(0, 30);
      for (let i = 0; i < chunks.length; i += 10) {
        console.log(`      ${chunks.slice(i, i + 10).join("  ")}`);
      }
    } else {
      console.log(`    No numbers won ₹${prize} in ALL 3 cycles.`);
    }

    data.overlaps.forEach((ov) => {
      const denom = Math.min(ov.totalA, ov.totalB);
      const pct   = denom > 0 ? ((ov.shared / denom) * 100).toFixed(1) : "0";
      console.log(
        `    C${ov.cycles[0]}∩C${ov.cycles[1]}: ` +
        `${ov.shared} shared / sizes ${ov.totalA} & ${ov.totalB} (${pct}% overlap)`
      );
      if (ov.shared > 0) {
        console.log(`    Shared: ${ov.sharedNumbers.join(", ")}`);
      }
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// VALIDATION — Train C2+C3 → Predict C4 → Measure Accuracy
// ═══════════════════════════════════════════════════════════════
function validatePrizePrediction(history, trainCycles, testCycle) {
  if (!testCycle) return { summary: { error: "Test cycle not found" } };

  const trainNums = trainCycles.map((c) => c.cycleNumber).sort((a, b) => a - b);

  let total = 0, exactMatch = 0, withinOne = 0;
  let hvTotal = 0, hvCorrect = 0;
  const confusionMatrix = {};
  const byPattern = {};

  for (const [number, cycleMap] of history) {
    const actualPrize = cycleMap.get(testCycle.cycleNumber);
    if (actualPrize === undefined) continue;

    const trainSeq = trainNums
      .map((cn) => cycleMap.get(cn))
      .filter((p) => p !== undefined && p !== null);

    if (trainSeq.length === 0) continue;

    const patternType    = classifyPattern(trainSeq);
    const predictedPrize = predictNextPrize(trainSeq, patternType);

    total++;
    if (predictedPrize === actualPrize) exactMatch++;

    const actualRank    = PRIZE_RANKS[actualPrize] ?? -1;
    const predictedRank = PRIZE_RANKS[predictedPrize] ?? -1;
    if (Math.abs(actualRank - predictedRank) <= 1) withinOne++;

    if (actualPrize >= 1000) {
      hvTotal++;
      if (predictedPrize >= 1000) hvCorrect++;
    }

    // Confusion matrix
    const ak = String(actualPrize);
    const pk = String(predictedPrize);
    if (!confusionMatrix[ak]) confusionMatrix[ak] = {};
    confusionMatrix[ak][pk] = (confusionMatrix[ak][pk] || 0) + 1;

    // By pattern
    if (!byPattern[patternType]) byPattern[patternType] = { total: 0, correct: 0 };
    byPattern[patternType].total++;
    if (predictedPrize === actualPrize) byPattern[patternType].correct++;
  }

  return {
    summary: {
      total,
      exactMatch,
      exactMatchPct:    total > 0 ? parseFloat(((exactMatch / total) * 100).toFixed(2)) : 0,
      withinOneTierPct: total > 0 ? parseFloat(((withinOne / total) * 100).toFixed(2)) : 0,
      highValueTotal:   hvTotal,
      highValueCorrect: hvCorrect,
      highValueAccuracy: hvTotal > 0 ? parseFloat(((hvCorrect / hvTotal) * 100).toFixed(2)) : 0,
    },
    byPattern,
    confusionMatrix,
  };
}

function printValidationResult(result) {
  if (result.summary.error) {
    console.log(`  ⚠️  ${result.summary.error}`);
    return;
  }

  const s = result.summary;
  console.log(`\n  Test: ${s.total} numbers (cycle 4 actuals vs C2+C3 pattern predictions)\n`);
  console.log(`  Exact prize match:             ${s.exactMatch}/${s.total} = ${s.exactMatchPct}%`);
  console.log(`  Random baseline (always ₹100): ~74%`);
  console.log(`  Within one prize tier:         ${s.withinOneTierPct}%`);
  console.log(`  High-value (≥₹1000) accuracy:  ${s.highValueCorrect}/${s.highValueTotal} = ${s.highValueAccuracy}%`);

  console.log(`\n  Accuracy by pattern type:`);
  console.log(`  Pattern Type       | Total  | Correct | Accuracy`);
  console.log(`  ` + "-".repeat(52));

  const ordered = [
    "FIXED", "ALTERNATING", "ROTATING",
    "ASCENDING", "DESCENDING",
    "STABLE", "SINGLE", "VARIABLE",
  ];
  for (const type of ordered) {
    const d = result.byPattern[type];
    if (!d || d.total === 0) continue;
    const acc = ((d.correct / d.total) * 100).toFixed(1);
    const bar = "█".repeat(Math.round(parseFloat(acc) / 10));
    console.log(
      `  ${String(type).padEnd(18)} | ${String(d.total).padEnd(6)} | ` +
      `${String(d.correct).padEnd(7)} | ${acc}%  ${bar}`
    );
  }

  console.log(`\n  Confusion matrix (actual → predicted):`);
  console.log(`  Actual  | →₹5000 | →₹2000 | →₹1000 | →₹500  | →₹200  | →₹100`);
  console.log(`  ` + "-".repeat(64));
  for (const actual of ["5000", "2000", "1000", "500", "200", "100"]) {
    const row = result.confusionMatrix[actual];
    if (!row) continue;
    const cells = ["5000", "2000", "1000", "500", "200", "100"]
      .map((pred) => String(row[pred] || 0).padEnd(6));
    console.log(`  ₹${String(actual).padEnd(5)} | ${cells.join(" | ")}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// CYCLE 5 PRIZE PREDICTIONS (using cycles 2,3,4 as training)
// ═══════════════════════════════════════════════════════════════
function predictCycle5Prizes(history, patterns, trainCycles) {
  const trainNums = trainCycles.map((c) => c.cycleNumber).sort((a, b) => a - b);
  const results   = [];

  for (const [number, cycleMap] of history) {
    const trainSeq = trainNums
      .map((cn) => cycleMap.get(cn))
      .filter((p) => p !== undefined && p !== null);

    if (trainSeq.length === 0) continue;

    const pat = patterns.get(number);
    const patternType    = pat?.patternType ?? classifyPattern(trainSeq);
    const predictedPrize = predictNextPrize(trainSeq, patternType);
    const confidence     = computePatternConfidence(trainSeq, patternType);
    const cycle5Actual   = cycleMap.get(5) ?? null;

    results.push({
      number,
      prizeSequence:  trainSeq,
      patternType,
      predictedPrize,
      confidence,
      cycle5Actual,
    });
  }

  return results.sort((a, b) => b.confidence - a.confidence);
}

function printCycle5PrizePredictions(predictions) {
  const dist = {};
  let totalConf = 0;

  for (const p of predictions) {
    const k = String(p.predictedPrize ?? "unknown");
    dist[k] = (dist[k] || 0) + 1;
    totalConf += p.confidence;
  }

  console.log(`\n  Total predictions: ${predictions.length}`);
  console.log(`  Avg confidence: ${(totalConf / predictions.length).toFixed(1)}%\n`);
  console.log(`  Predicted Prize | Count | %`);
  console.log(`  ` + "-".repeat(35));

  for (const prize of PRIZES_DESC) {
    const count = dist[String(prize)] || 0;
    if (count === 0) continue;
    const pct = ((count / predictions.length) * 100).toFixed(1);
    const bar = "█".repeat(Math.round(parseFloat(pct) / 2));
    console.log(
      `  ₹${String(prize).padEnd(5)}         | ${String(count).padEnd(5)} | ${pct}% ${bar}`
    );
  }

  // Confidence tiers
  const c100 = predictions.filter((p) => p.confidence === 100).length;
  const c90  = predictions.filter((p) => p.confidence >= 90).length;
  const c75  = predictions.filter((p) => p.confidence >= 75).length;
  const c50  = predictions.filter((p) => p.confidence >= 50).length;

  console.log(`\n  Confidence tiers:`);
  console.log(`    100% (FIXED pattern):  ${c100}`);
  console.log(`    ≥90% confidence:       ${c90}`);
  console.log(`    ≥75% confidence:       ${c75}`);
  console.log(`    ≥50% confidence:       ${c50}`);

  // Live accuracy check against already-drawn cycle 5 numbers
  const known = predictions.filter((p) => p.cycle5Actual !== null);
  if (known.length > 0) {
    const correct = known.filter((p) => p.cycle5Actual === p.predictedPrize).length;
    const pct     = ((correct / known.length) * 100).toFixed(1);
    console.log(`\n  ✅ LIVE ACCURACY (vs already-drawn cycle 5 numbers):`);
    console.log(`     ${correct} / ${known.length} correct = ${pct}%`);
    console.log(`     (Random baseline ≈ 74% if always guessing ₹100)`);

    // By prize tier
    console.log(`\n  Live accuracy by prize tier:`);
    for (const prize of PRIZES_DESC) {
      const tier    = known.filter((p) => p.cycle5Actual === prize);
      if (tier.length === 0) continue;
      const tCorrect = tier.filter((p) => p.predictedPrize === prize).length;
      const tPct     = ((tCorrect / tier.length) * 100).toFixed(1);
      console.log(`    ₹${String(prize).padEnd(5)}: ${tCorrect}/${tier.length} = ${tPct}%`);
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// HIGH-VALUE PRIZE PREDICTIONS (₹1000+)
// ═══════════════════════════════════════════════════════════════
function printHighValuePredictions(predictions, remaining) {
  const remainSet = new Set(remaining);

  const highValue = predictions
    .filter((p) => (p.predictedPrize ?? 0) >= 1000)
    .sort((a, b) =>
      b.predictedPrize - a.predictedPrize || b.confidence - a.confidence
    );

  console.log(`\n  Numbers predicted to win ₹1000+ in cycle 5: ${highValue.length}\n`);
  console.log(
    "  Number | Prize  | Conf | Pattern       | Sequence                | Status   | C5 Actual"
  );
  console.log("  " + "-".repeat(95));

  for (const p of highValue) {
    const seq    = p.prizeSequence.map((v) => `₹${v}`).join("→");
    const status = remainSet.has(p.number) ? "PENDING" : "drawn";
    const actual = p.cycle5Actual ? `₹${p.cycle5Actual}` : "—";
    const tick   = p.cycle5Actual
      ? (p.cycle5Actual === p.predictedPrize ? "✅" : "❌")
      : "";

    console.log(
      `  ${p.number}   | ₹${String(p.predictedPrize).padEnd(5)} | ` +
      `${String(p.confidence + "%").padEnd(4)} | ` +
      `${String(p.patternType).padEnd(13)} | ` +
      `${String(seq).padEnd(25)} | ${String(status).padEnd(8)} | ${actual} ${tick}`
    );
  }

  // Per-tier summary
  for (const prize of [5000, 2000, 1000]) {
    const tier    = highValue.filter((p) => p.predictedPrize === prize);
    const pending = tier.filter((p) => remainSet.has(p.number));
    const drawn   = tier.filter((p) => !remainSet.has(p.number));
    const correct = drawn.filter((p) => p.cycle5Actual === prize);

    console.log(`\n  ₹${prize} summary:`);
    console.log(`    Total predicted: ${tier.length}`);
    console.log(`    Already drawn:   ${drawn.length} (correct: ${correct.length})`);
    console.log(`    Still pending:   ${pending.length}`);
    if (pending.length > 0) {
      console.log(`    Pending: ${pending.map((p) => p.number).join(", ")}`);
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// GUARANTEED REMAINING 53 + PRIZE PREDICTION
// ═══════════════════════════════════════════════════════════════
function printRemainingWithPrize(remaining, predictions, history) {
  console.log(`\n  ${remaining.length} guaranteed remaining numbers + predicted prizes:\n`);

  const predMap = new Map(predictions.map((p) => [p.number, p]));

  const enriched = remaining
    .map((num) => {
      const pred = predMap.get(num);
      const hist = history.get(num);
      const seq  = hist
        ? [2, 3, 4]
            .map((cn) => hist.get(cn))
            .filter((p) => p !== undefined && p !== null)
        : [];
      return {
        number:         num,
        predictedPrize: pred?.predictedPrize ?? null,
        confidence:     pred?.confidence ?? 0,
        patternType:    pred?.patternType ?? "UNKNOWN",
        sequence:       seq,
      };
    })
    .sort(
      (a, b) =>
        (b.predictedPrize ?? 0) - (a.predictedPrize ?? 0) ||
        b.confidence - a.confidence
    );

  console.log(
    "  Number | PredictedPrize | Confidence | Pattern       | C2→C3→C4 Sequence"
  );
  console.log("  " + "-".repeat(82));

  for (const e of enriched) {
    const seq = e.sequence.map((v) => `₹${v}`).join("→") || "no data";
    console.log(
      `  ${e.number}   | ₹${String(e.predictedPrize ?? "?").padEnd(14)} | ` +
      `${String(e.confidence + "%").padEnd(10)} | ` +
      `${String(e.patternType).padEnd(13)} | ${seq}`
    );
  }

  // Prize breakdown
  const breakdown = {};
  enriched.forEach((e) => {
    const k = String(e.predictedPrize ?? "unknown");
    breakdown[k] = (breakdown[k] || 0) + 1;
  });

  console.log(`\n  Prize breakdown for remaining ${remaining.length}:`);
  for (const prize of PRIZES_DESC) {
    const count = breakdown[String(prize)] || 0;
    if (count > 0) console.log(`    ₹${prize}: ${count} numbers`);
  }
  if (breakdown["unknown"]) {
    console.log(`    Unknown: ${breakdown["unknown"]} numbers`);
  }
}

// ═══════════════════════════════════════════════════════════════
// PRIZE CYCLE TABLE — top 100 interesting numbers
// ═══════════════════════════════════════════════════════════════
function printPrizeCycleTable(history, predictions, patterns, trainCycles) {
  const trainNums = trainCycles.map((c) => c.cycleNumber).sort((a, b) => a - b);
  const predMap   = new Map(predictions.map((p) => [p.number, p]));

  const interesting = [];

  for (const [number, cycleMap] of history) {
    const seq     = trainNums
      .map((cn) => cycleMap.get(cn))
      .filter((p) => p !== undefined && p !== null);
    const hasHigh = seq.some((p) => p >= 500);
    const pat     = patterns.get(number);
    const isGood  = [
      "FIXED", "ALTERNATING", "ROTATING", "ASCENDING", "DESCENDING",
    ].includes(pat?.patternType);

    if (!hasHigh && !isGood) continue;

    interesting.push({
      number,
      c2:       cycleMap.get(2) ?? null,
      c3:       cycleMap.get(3) ?? null,
      c4:       cycleMap.get(4) ?? null,
      c5actual: cycleMap.get(5) ?? null,
      pred:     predMap.get(number),
    });
  }

  // Sort: highest max prize first
  interesting.sort((a, b) => {
    const maxA = Math.max(a.c2 || 0, a.c3 || 0, a.c4 || 0);
    const maxB = Math.max(b.c2 || 0, b.c3 || 0, b.c4 || 0);
    return maxB - maxA;
  });

  const showCount = Math.min(interesting.length, 100);
  console.log(`\n  Found ${interesting.length} interesting numbers — showing top ${showCount}:\n`);
  console.log(
    "  Number | C2      | C3      | C4      | C5Actual | C5Predict  | Pattern       | Conf"
  );
  console.log("  " + "-".repeat(95));

  for (const e of interesting.slice(0, 100)) {
    const fmt    = (v) => (v ? `₹${v}` : "—");
    const actual = e.c5actual ? `₹${e.c5actual}` : "pending";
    const pred   = e.pred?.predictedPrize ? `₹${e.pred.predictedPrize}` : "?";
    const tick   =
      e.c5actual && e.pred?.predictedPrize === e.c5actual ? "✅" :
      e.c5actual ? "❌" : "";

    console.log(
      `  ${e.number}   | ` +
      `${String(fmt(e.c2)).padEnd(7)} | ` +
      `${String(fmt(e.c3)).padEnd(7)} | ` +
      `${String(fmt(e.c4)).padEnd(7)} | ` +
      `${String(actual).padEnd(8)} | ` +
      `${String(pred).padEnd(10)} | ` +
      `${String(e.pred?.patternType ?? "?").padEnd(13)} | ` +
      `${e.pred?.confidence ?? 0}% ${tick}`
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// HELPER — Get remaining (not-yet-drawn) numbers in cycle 5
// ═══════════════════════════════════════════════════════════════
function getRemainingNumbers(currentCycle) {
  const drawn = new Set();
  for (const dayEntry of currentCycle.drawEntries) {
    for (const { number, isNew } of dayEntry.numbers) {
      if (isNew) drawn.add(number);
    }
  }
  return Array.from({ length: 10000 }, (_, i) => String(i).padStart(4, "0"))
    .filter((n) => !drawn.has(n))
    .sort();
}

// ─────────────────────────────────────────────────────
runPhase5().catch((err) => {
  console.error("❌ Phase 5 failed:", err);
  process.exit(1);
});