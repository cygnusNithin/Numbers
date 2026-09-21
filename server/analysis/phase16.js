require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 16 — DAY-OF-WEEK BASED HOME LOTTERY VALIDATION
//
// Phase 15 used lottery NAMES (AK, W, FF, NR) which changed
// to (SM, BT, DL, SK) in cycle 5.
// The underlying DAY-OF-WEEK assignment is the real formula.
//
// THIS PHASE:
//   Map each number to its home DOW (0=Sun...6=Sat)
//   Validate: does cycle 4 number appear on its home DOW?
//   Predict remaining 41 by home DOW + upcoming draw dates
// ═══════════════════════════════════════════════════════════════

async function runPhase16() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const allDraws  = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(allDraws);
  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete);
  const currentCycle = validCycles.find((c) => !c.isComplete);

  const DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

  console.log("📋 PHASE 16 — DAY-OF-WEEK HOME ASSIGNMENT\n");
  console.log("   Lottery names changed between cycles but DOW is constant.\n");

  // ═══════════════════════════════════════════════════════════════
  // STEP 1 — BUILD NUMBER → HOME DOW MAP
  // For each number, record which DOW it was drawn as NEW
  // in each training cycle. If consistent → home DOW confirmed.
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — NUMBER → HOME DAY-OF-WEEK MAPPING");
  console.log("═".repeat(65));

  const numDOW = new Map(); // number → {cycleN: dow}

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const dow = new Date(dayEntry.drawDate).getUTCDay();
      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        if (!numDOW.has(number)) numDOW.set(number, {});
        numDOW.get(number)[cycle.cycleNumber] = dow;
      }
    }
  }

  // Analyze consistency
  let sameAll=0, same2of3=0, diff=0;
  const homeDOW = new Map(); // number → home DOW (most common)
  const homeDOWConsistent = new Map(); // number → true/false

  for (const [num, cycleMap] of numDOW) {
    const dows     = Object.values(cycleMap);
    const allSame  = dows.every((d) => d === dows[0]);
    const freq     = {};
    dows.forEach((d) => { freq[d]=(freq[d]||0)+1; });
    const topDOW   = Number(Object.entries(freq).sort((a,b)=>b[1]-a[1])[0][0]);

    homeDOW.set(num, topDOW);
    homeDOWConsistent.set(num, allSame);

    if (allSame) sameAll++;
    else {
      const topCount = Math.max(...Object.values(freq));
      if (topCount >= 2) same2of3++;
      else diff++;
    }
  }

  console.log(`\n  Total numbers: ${numDOW.size.toLocaleString()}`);
  console.log(`  Same DOW in ALL 3 cycles:   ${sameAll.toLocaleString()} (${(sameAll/numDOW.size*100).toFixed(1)}%)`);
  console.log(`  Same DOW in 2 of 3 cycles:  ${same2of3.toLocaleString()} (${(same2of3/numDOW.size*100).toFixed(1)}%)`);
  console.log(`  Different DOW each cycle:    ${diff.toLocaleString()} (${(diff/numDOW.size*100).toFixed(1)}%)`);

  const consistent = sameAll + same2of3;
  console.log(`\n  Consistent (same DOW in ≥2 cycles): ${consistent.toLocaleString()} (${(consistent/numDOW.size*100).toFixed(1)}%)`);

  if (consistent/numDOW.size > 0.7) {
    console.log(`  ✅ STRONG SIGNAL: Numbers have consistent home day-of-week!`);
  } else if (consistent/numDOW.size > 0.3) {
    console.log(`  ⚠️  PARTIAL SIGNAL: Some numbers have consistent home DOW`);
  } else {
    console.log(`  ❌ WEAK: DOW assignment not consistent`);
  }

  // Distribution: how many numbers assigned to each DOW?
  const dowCounts = new Array(7).fill(0);
  const dowConsistentCounts = new Array(7).fill(0);

  for (const [num, dow] of homeDOW) {
    dowCounts[dow]++;
    if (homeDOWConsistent.get(num)) dowConsistentCounts[dow]++;
  }

  console.log(`\n  Numbers per home DOW (consistent vs total):`);
  console.log(`  DOW | Day | Consistent | Total  | % Consistent`);
  console.log(`  ` + "-".repeat(50));
  for (let d=0; d<7; d++) {
    const pct = dowCounts[d] > 0 ? (dowConsistentCounts[d]/dowCounts[d]*100).toFixed(1) : "0";
    console.log(
      `  ${d}   | ${DAYS[d]} | ${String(dowConsistentCounts[d]).padEnd(10)} | ` +
      `${String(dowCounts[d]).padEnd(6)} | ${pct}%`
    );
  }

  // ═══════════════════════════════════════════════════════════════
  // STEP 2 — VALIDATE ON CYCLE 4
  // Use home DOW from cycles 2+3 → predict cycle 4 DOW
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — VALIDATION: PREDICT CYCLE 4 DOW FROM CYCLES 2+3");
  console.log("═".repeat(65));

  // Build home DOW from cycles 2+3 only
  const numDOW_C23 = new Map();
  for (const cycle of trainCycles.filter((c) => c.cycleNumber <= 3)) {
    for (const dayEntry of cycle.drawEntries) {
      const dow = new Date(dayEntry.drawDate).getUTCDay();
      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        if (!numDOW_C23.has(number)) numDOW_C23.set(number, []);
        numDOW_C23.get(number).push(dow);
      }
    }
  }

  // For each number in C23, find home DOW
  const homeDOW_C23 = new Map();
  for (const [num, dows] of numDOW_C23) {
    if (dows.length < 2) continue;
    const freq = {};
    dows.forEach((d) => { freq[d]=(freq[d]||0)+1; });
    const top = Number(Object.entries(freq).sort((a,b)=>b[1]-a[1])[0][0]);
    homeDOW_C23.set(num, top);
  }

  // Now test against cycle 4 actuals
  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  let correct=0, total=0, noData=0;
  const confusionMatrix = {};

  for (const dayEntry of cycle4.drawEntries) {
    const actualDOW = new Date(dayEntry.drawDate).getUTCDay();
    for (const { number, isNew } of dayEntry.numbers) {
      if (!isNew) continue;
      total++;
      const predicted = homeDOW_C23.get(number);
      if (predicted === undefined) { noData++; continue; }

      const key = `${predicted}→${actualDOW}`;
      confusionMatrix[key] = (confusionMatrix[key]||0)+1;
      if (predicted === actualDOW) correct++;
    }
  }

  const accuracy  = total > 0 ? (correct/total*100).toFixed(1) : 0;
  const baseline  = (1/7*100).toFixed(1);
  const improvement = (parseFloat(accuracy)/parseFloat(baseline)).toFixed(2);

  console.log(`\n  Total new numbers in cycle 4: ${total}`);
  console.log(`  No home DOW data:             ${noData}`);
  console.log(`  Correct DOW predicted:        ${correct} (${accuracy}%)`);
  console.log(`  Random baseline (1/7):        ~${baseline}%`);
  console.log(`  Improvement:                  ${improvement}x`);

  if (parseFloat(improvement) >= 5) {
    console.log(`\n  ✅✅✅ FORMULA CONFIRMED! DOW predicts new numbers with ${accuracy}% accuracy!`);
    console.log(`  → ${improvement}x better than random`);
    console.log(`  → Each number IS assigned to a specific day of week`);
    console.log(`  → The draw formula: number → DOW → appears new on that DOW`);
  } else if (parseFloat(improvement) >= 2) {
    console.log(`\n  ✅ SIGNAL: ${improvement}x better than random`);
    console.log(`  DOW assignment is real but noisy (lottery changes may dilute signal)`);
  } else {
    console.log(`\n  ⚠️  Signal: ${improvement}x. Check confusion matrix below.`);
  }

  // Per-DOW accuracy
  console.log(`\n  Accuracy by predicted DOW:`);
  console.log(`  Pred DOW | Correct | Wrong | Accuracy`);
  console.log(`  ` + "-".repeat(42));
  for (let d=0; d<7; d++) {
    let corr=0, wrong=0;
    for (const [key, count] of Object.entries(confusionMatrix)) {
      const [pred] = key.split("→");
      if (parseInt(pred) === d) {
        if (key.split("→")[0] === key.split("→")[1]) corr += count;
        else wrong += count;
      }
    }
    const tot = corr + wrong;
    const acc = tot > 0 ? (corr/tot*100).toFixed(1) : "0";
    if (tot > 0) {
      console.log(`  ${DAYS[d]}      | ${String(corr).padEnd(7)} | ${String(wrong).padEnd(5)} | ${acc}%`);
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // STEP 3 — CLEAN PREDICTION FOR REMAINING 41
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — FINAL PREDICTION: REMAINING 41 NUMBERS BY DATE");
  console.log("═".repeat(65));

  // Get remaining numbers
  const drawn    = new Set();
  currentCycle.drawEntries.forEach((d) => {
    d.numbers.forEach((n) => { if (n.isNew) drawn.add(n.number); });
  });
  const allNums  = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));
  const remaining = allNums.filter((n) => !drawn.has(n));

  // Prize model
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
  const isFixed = (num) => {
    const arr = prizeModel.get(num) || [];
    return arr.length >= 3 && new Set(arr).size === 1;
  };

  // Next draw dates for each DOW (from today 2026-05-14 = Thursday = DOW 4)
  // Already past: today = Thu 14/05 (DOW=4)
  // Next draws:
  //   Fri 15/05: SK (DOW=5)
  //   Sat 16/05: KR (DOW=6)
  //   Sun 17/05: SM (DOW=0)
  //   Mon 18/05: BT (DOW=1)
  //   Tue 19/05: SS (DOW=2)
  //   Wed 20/05: DL (DOW=3)
  //   Thu 21/05: KN (DOW=4)

  // Map current lottery names to DOW
  const currentLotteryByDOW = {
    0: "SM", 1: "BT", 2: "SS", 3: "DL", 4: "KN", 5: "SK", 6: "KR"
  };
  const nextDrawDate = {
    5: "2026-05-15 (Fri - SK)",
    6: "2026-05-16 (Sat - KR)",
    0: "2026-05-17 (Sun - SM)",
    1: "2026-05-18 (Mon - BT)",
    2: "2026-05-19 (Tue - SS)",
    3: "2026-05-20 (Wed - DL)",
    4: "2026-05-21 (Thu - KN)",
  };

  // Group remaining by home DOW
  const byDOW = {};
  for (let d=0; d<7; d++) byDOW[d] = [];

  for (const num of remaining) {
    const dow         = homeDOW_C23.get(num) ?? homeDOW.get(num);
    const consistent  = homeDOWConsistent.get(num) ?? false;
    const prize       = getPrize(num);
    const fixed       = isFixed(num);
    byDOW[dow !== undefined ? dow : 7]?.push({ num, dow, consistent, prize, fixed }) ||
      (byDOW[7] = byDOW[7] || [], byDOW[7].push({ num, dow, consistent, prize, fixed }));
  }

  console.log(`\n  Remaining ${remaining.length} numbers — predicted draw schedule:\n`);

  // Print in draw order (Fri first, then Sat, Sun, Mon, Tue, Wed, Thu)
  const drawOrder = [5, 6, 0, 1, 2, 3, 4];

  for (const dow of drawOrder) {
    const nums = byDOW[dow] || [];
    if (nums.length === 0) continue;

    const lottery   = currentLotteryByDOW[dow];
    const drawDate  = nextDrawDate[dow];
    const confirmed = nums.filter((n) => n.consistent).length;

    console.log(`  ┌─────────────────────────────────────────────────────┐`);
    console.log(`  │ ${drawDate.padEnd(51)} │`);
    console.log(`  │ Lottery: ${String(lottery).padEnd(4)} | ${nums.length} numbers expected          │`);
    console.log(`  ├─────────────────────────────────────────────────────┤`);

    nums.sort((a,b) => (b.prize??0) - (a.prize??0));
    for (const n of nums) {
      const prizeStr = `₹${n.prize}${n.fixed?"*":""}`;
      const conf     = n.consistent ? "✅" : "⚠️ ";
      console.log(`  │  ${n.num}  ${String(prizeStr).padEnd(8)} ${conf}                                │`);
    }
    console.log(`  └─────────────────────────────────────────────────────┘\n`);
  }

  // Summary count
  const totalPredicted = drawOrder.reduce((s,d)=>s+(byDOW[d]?.length||0),0);
  console.log(`  Total predicted: ${totalPredicted}/${remaining.length} remaining numbers`);
  console.log(`  * = fixed prize (100% reliable from past cycles)\n`);

  // ═══════════════════════════════════════════════════════════════
  // STEP 4 — HOW MANY NEW NUMBERS PER LOTTERY?
  // From the tracking image: SM always draws 2.
  // Check if each lottery has a consistent count.
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 4 — NEW NUMBERS PER LOTTERY COUNT PATTERN");
  console.log("  Does each lottery draw a consistent # of new numbers?");
  console.log("═".repeat(65));

  const newCountByDOW = {};
  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const dow    = new Date(dayEntry.drawDate).getUTCDay();
      const newCount = dayEntry.numbers.filter((n) => n.isNew).length;
      if (!newCountByDOW[dow]) newCountByDOW[dow] = [];
      newCountByDOW[dow].push(newCount);
    }
  }

  const mean = (arr) => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;
  const std  = (arr) => {
    if (arr.length<2) return 0;
    const m=mean(arr);
    return Math.sqrt(arr.reduce((s,v)=>s+(v-m)**2,0)/arr.length);
  };

  console.log(`\n  DOW | Day | AvgNew | StdNew | Min | Max | Consistent?`);
  console.log(`  ` + "-".repeat(58));
  for (let d=0; d<7; d++) {
    const counts = newCountByDOW[d] || [];
    if (counts.length === 0) continue;
    const avg = mean(counts).toFixed(1);
    const s   = std(counts).toFixed(1);
    const mn  = Math.min(...counts);
    const mx  = Math.max(...counts);
    const cv  = parseFloat(s)/parseFloat(avg); // coeff of variation
    const cons = cv < 0.5 ? "✅ Consistent" : "❌ Variable";
    console.log(
      `  ${d}   | ${DAYS[d]} | ${String(avg).padEnd(6)} | ${String(s).padEnd(6)} | ` +
      `${String(mn).padEnd(3)} | ${String(mx).padEnd(3)} | ${cons}`
    );
  }

  // Save output
  const output = {
    generatedAt: new Date().toISOString(),
    validation: { accuracy: parseFloat(accuracy), baseline: parseFloat(baseline), improvement: parseFloat(improvement) },
    remainingPredictions: drawOrder.flatMap((dow) =>
      (byDOW[dow] || []).map((n) => ({
        number:        n.num,
        homeDOW:       dow,
        homeDOWName:   DAYS[dow],
        lottery:       currentLotteryByDOW[dow],
        predictedDate: nextDrawDate[dow],
        predictedPrize: n.prize,
        isFixed:        n.fixed,
        consistent:     n.consistent,
      }))
    ),
  };
  fs.writeFileSync("./phase16_predictions.json", JSON.stringify(output, null, 2));
  console.log("\n  ✅ Phase 16 complete → phase16_predictions.json");

  await mongoose.disconnect();
}

runPhase16().catch((err) => {
  console.error("❌ Phase 16 failed:", err);
  process.exit(1);
});