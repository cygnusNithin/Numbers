require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 15 — HOME LOTTERY DISCOVERY
//
// USER'S KEY INSIGHT:
//   7 daily lotteries share ONE pool of 10,000 numbers.
//   Each number has a "home lottery" (SS, DL, KN, KR, SM, BT, SK).
//   Within a cycle, each number appears in its home lottery's
//   draw EVERY time EXCEPT ONE — and that ONE exception = 
//   its "new" (first appearance) day for that cycle.
//
// IF VERIFIED:
//   → We can predict WHICH lottery draws each remaining number
//   → We can predict WHEN each remaining number appears
//   → FORMULA FOUND: remaining(N) → homeLottery(N) → nextDraw
// ═══════════════════════════════════════════════════════════════

async function runPhase15() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const allDraws  = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(allDraws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete);
  const currentCycle = validCycles.find((c) => !c.isComplete);

  console.log("📋 PHASE 15 — HOME LOTTERY DISCOVERY\n");
  console.log("   Testing: does each number always appear as 'new'");
  console.log("   in the SAME lottery across multiple cycles?\n");

  // ═══════════════════════════════════════════════════════════════
  // STEP 1 — IDENTIFY LOTTERY CODES IN DATABASE
  // Find all unique lottery series codes and their draw days
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — IDENTIFY ALL LOTTERY CODES");
  console.log("═".repeat(65));

  const lotteryInfo = identifyLotteries(allDraws);

  // ═══════════════════════════════════════════════════════════════
  // STEP 2 — BUILD NUMBER → HOME LOTTERY MAP
  // For each number, which lottery series drew it as "new"
  // in cycles 2, 3, and 4?
  // If SAME lottery all 3 cycles → confirmed home lottery
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — NUMBER → HOME LOTTERY MAPPING");
  console.log("  For each number: which lottery drew it as 'new'?");
  console.log("  Consistent = same lottery in all training cycles");
  console.log("═".repeat(65));

  const homeLotteryMap = buildHomeLotteryMap(allDraws, trainCycles, lotteryInfo);

  // ═══════════════════════════════════════════════════════════════
  // STEP 3 — VERIFY CONSISTENCY
  // What % of numbers have the SAME home lottery across all cycles?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — HOME LOTTERY CONSISTENCY");
  console.log("  % of numbers with same lottery in ALL training cycles");
  console.log("═".repeat(65));

  verifyConsistency(homeLotteryMap, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 4 — VERIFY USER'S INSIGHT
  // For each number: count how many draws of its home lottery
  // it was ABSENT from (should be exactly 1 per cycle).
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — VERIFY: EACH NUMBER ABSENT FROM EXACTLY 1 DRAW");
  console.log("  'each unique number drawn except ONE day per cycle'");
  console.log("═".repeat(65));

  verifyAbsencePattern(allDraws, trainCycles, homeLotteryMap, lotteryInfo);

  // ═══════════════════════════════════════════════════════════════
  // STEP 5 — PREDICT REMAINING 41 NUMBERS
  // For each remaining number in cycle 5:
  // → Find its home lottery
  // → Predict which draw date it appears next
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — PREDICT REMAINING 41 NUMBERS");
  console.log("  For each remaining: home lottery → next draw date");
  console.log("═".repeat(65));

  predictRemaining(currentCycle, homeLotteryMap, lotteryInfo, allDraws);

  // ═══════════════════════════════════════════════════════════════
  // STEP 6 — VALIDATE ON CYCLE 4
  // Use home lottery map from cycles 2+3 to predict cycle 4.
  // Did numbers appear in their predicted home lottery? 
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — VALIDATE: PREDICT CYCLE 4 FROM CYCLES 2+3");
  console.log("  If home lottery is consistent → this should be near 100%");
  console.log("═".repeat(65));

  validateHomeLottery(allDraws, trainCycles, homeLotteryMap, lotteryInfo);

  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// STEP 1 — IDENTIFY LOTTERIES
// ─────────────────────────────────────────────────────────────
function identifyLotteries(allDraws) {
  const lotteryDOW   = new Map(); // lotteryCode → Set of DOW
  const lotteryCount = new Map(); // lotteryCode → draw count
  const lotteryDates = new Map(); // lotteryCode → [dates]

  for (const draw of allDraws) {
    const code = draw.serialNumber || draw.lotteryName || "UNKNOWN";

    // Extract lottery prefix (first 2-3 letters before number)
    const match = code.match(/^([A-Z]{1,3})/);
    const prefix = match ? match[1] : "UNK";

    const dow  = new Date(draw.drawDate).getUTCDay();
    const date = new Date(draw.drawDate).toISOString().split("T")[0];

    if (!lotteryDOW.has(prefix))   lotteryDOW.set(prefix, new Set());
    if (!lotteryCount.has(prefix)) lotteryCount.set(prefix, 0);
    if (!lotteryDates.has(prefix)) lotteryDates.set(prefix, []);

    lotteryDOW.get(prefix).add(dow);
    lotteryCount.set(prefix, lotteryCount.get(prefix) + 1);
    lotteryDates.get(prefix).push(date);
  }

  const DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  console.log(`\n  Lottery codes found in database:`);
  console.log(`  Code | Draws | Primary DOW | Day Name`);
  console.log(`  ` + "-".repeat(45));

  const lotteryInfo = new Map();
  for (const [prefix, count] of [...lotteryCount.entries()].sort((a,b)=>b[1]-a[1])) {
    const dows    = [...lotteryDOW.get(prefix)];
    const primaryDOW = dows.sort((a,b) => {
      // Find most common DOW
      const aCount = lotteryDates.get(prefix).filter(d =>
        new Date(d).getUTCDay() === a).length;
      const bCount = lotteryDates.get(prefix).filter(d =>
        new Date(d).getUTCDay() === b).length;
      return bCount - aCount;
    })[0];

    lotteryInfo.set(prefix, { primaryDOW, count });
    console.log(
      `  ${String(prefix).padEnd(4)} | ${String(count).padEnd(5)} | ` +
      `${String(primaryDOW).padEnd(11)} | ${DAYS[primaryDOW]}`
    );
  }

  console.log(`\n  Total unique lottery codes: ${lotteryInfo.size}`);
  console.log(`  (Expected: 7 for Mon-Sun daily lotteries)`);

  return lotteryInfo;
}

// ─────────────────────────────────────────────────────────────
// STEP 2 — BUILD HOME LOTTERY MAP
// ─────────────────────────────────────────────────────────────
function buildHomeLotteryMap(allDraws, trainCycles, lotteryInfo) {
  // Build map: draw_date → lottery_code
  const dateToLottery = new Map();
  for (const draw of allDraws) {
    const date   = new Date(draw.drawDate).toISOString().split("T")[0];
    const code   = draw.serialNumber || draw.lotteryName || "UNK";
    const match  = code.match(/^([A-Z]{1,3})/);
    const prefix = match ? match[1] : "UNK";
    dateToLottery.set(date, prefix);
  }

  // For each number, find which lottery drew it as NEW in each training cycle
  const numHomeByC = new Map(); // number → {cycle: lotteryCode}

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const date    = new Date(dayEntry.drawDate).toISOString().split("T")[0];
      const lottery = dateToLottery.get(date) || "UNK";

      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        if (!numHomeByC.has(number)) numHomeByC.set(number, {});
        numHomeByC.get(number)[cycle.cycleNumber] = lottery;
      }
    }
  }

  // Determine home lottery for each number
  const homeLotteryMap = new Map();
  for (const [number, cycleMap] of numHomeByC) {
    const lotteries = Object.values(cycleMap);
    const allSame   = lotteries.every((l) => l === lotteries[0]);
    const mostCommon = [...lotteries].sort((a,b) =>
      lotteries.filter(x=>x===b).length - lotteries.filter(x=>x===a).length
    )[0];

    homeLotteryMap.set(number, {
      byCycle:    cycleMap,
      consistent: allSame,
      homeLottery: allSame ? lotteries[0] : mostCommon,
      cyclesPresent: lotteries.length,
    });
  }

  return homeLotteryMap;
}

// ─────────────────────────────────────────────────────────────
// STEP 3 — VERIFY CONSISTENCY
// ─────────────────────────────────────────────────────────────
function verifyConsistency(homeLotteryMap, trainCycles) {
  let total=0, consistent=0, twoOf3=0, oneOf3=0;
  const byLottery = {};

  for (const [num, data] of homeLotteryMap) {
    total++;
    if (data.consistent) {
      consistent++;
      byLottery[data.homeLottery] = (byLottery[data.homeLottery]||0)+1;
    } else if (data.cyclesPresent >= 2) {
      twoOf3++;
    } else {
      oneOf3++;
    }
  }

  console.log(`\n  Total numbers with home lottery data: ${total.toLocaleString()}`);
  console.log(`  Same lottery in ALL training cycles:   ${consistent.toLocaleString()} (${(consistent/total*100).toFixed(1)}%)`);
  console.log(`  Same in 2 of 3 cycles:                ${twoOf3.toLocaleString()} (${(twoOf3/total*100).toFixed(1)}%)`);
  console.log(`  Only 1 cycle data:                    ${oneOf3.toLocaleString()} (${(oneOf3/total*100).toFixed(1)}%)`);

  if (consistent/total > 0.7) {
    console.log(`\n  ✅ STRONG SIGNAL: ${(consistent/total*100).toFixed(1)}% of numbers have a FIXED home lottery!`);
    console.log(`  → The draw is NOT random across lotteries`);
    console.log(`  → Each number is assigned to one specific lottery`);
  } else if (consistent/total > 0.3) {
    console.log(`\n  ⚠️  PARTIAL SIGNAL: ${(consistent/total*100).toFixed(1)}% consistent`);
  } else {
    console.log(`\n  ❌ WEAK: Only ${(consistent/total*100).toFixed(1)}% consistent`);
  }

  console.log(`\n  Consistent numbers per lottery:`);
  Object.entries(byLottery)
    .sort((a,b)=>b[1]-a[1])
    .forEach(([lottery, count]) => {
      const bar = "█".repeat(Math.round(count/50));
      console.log(`    ${String(lottery).padEnd(5)}: ${String(count).padEnd(6)} numbers ${bar}`);
    });

  return { consistent, total, byLottery };
}

// ─────────────────────────────────────────────────────────────
// STEP 4 — VERIFY ABSENCE PATTERN
// ─────────────────────────────────────────────────────────────
function verifyAbsencePattern(allDraws, trainCycles, homeLotteryMap, lotteryInfo) {
  // For each number in its home lottery:
  // Count how many draws of that lottery it APPEARED in
  // Count how many draws it was ABSENT from
  // Expected: absent from EXACTLY 1 draw per cycle

  // Build: lotteryCode → [draw dates]
  const lotteryDrawDates = new Map();
  for (const draw of allDraws) {
    const date   = new Date(draw.drawDate).toISOString().split("T")[0];
    const code   = draw.serialNumber || draw.lotteryName || "UNK";
    const match  = code.match(/^([A-Z]{1,3})/);
    const prefix = match ? match[1] : "UNK";
    if (!lotteryDrawDates.has(prefix)) lotteryDrawDates.set(prefix, []);
    lotteryDrawDates.get(prefix).push(date);
  }

  // Build: (lottery, date) → Set of numbers drawn
  const drawNumbers = new Map();
  for (const draw of allDraws) {
    const date   = new Date(draw.drawDate).toISOString().split("T")[0];
    const code   = draw.serialNumber || draw.lotteryName || "UNK";
    const match  = code.match(/^([A-Z]{1,3})/);
    const prefix = match ? match[1] : "UNK";
    const key    = `${prefix}:${date}`;
    if (!drawNumbers.has(key)) drawNumbers.set(key, new Set());
    draw.series?.forEach((s) => {
      s.numbers?.forEach((n) => drawNumbers.get(key).add(n.number));
    });
  }

  // Test for a sample of numbers with consistent home lottery
  const consistent = [...homeLotteryMap.entries()]
    .filter(([, d]) => d.consistent && d.cyclesPresent >= 2)
    .slice(0, 100);

  let exactlyOne=0, moreThanOne=0, zeroAbsence=0, total=0;
  const absenceCounts = [];

  for (const [num, data] of consistent) {
    const lottery = data.homeLottery;
    const dates   = lotteryDrawDates.get(lottery) || [];
    if (dates.length < 5) continue;

    // For this lottery, how many draws contains this number?
    let present=0, absent=0;
    for (const date of dates.slice(0, 50)) { // check last 50 draws
      const key    = `${lottery}:${date}`;
      const numsOnDay = drawNumbers.get(key);
      if (!numsOnDay) continue;
      if (numsOnDay.has(num)) present++;
      else absent++;
    }

    total++;
    absenceCounts.push(absent);
    if (absent === 1) exactlyOne++;
    else if (absent === 0) zeroAbsence++;
    else moreThanOne++;
  }

  const avgAbsence = absenceCounts.length > 0 ?
    (absenceCounts.reduce((a,b)=>a+b,0)/absenceCounts.length).toFixed(2) : "?";

  console.log(`\n  Testing: does each number appear in home lottery EVERY draw except 1?`);
  console.log(`  Sample tested: ${total} consistent numbers\n`);
  console.log(`  Absent from exactly 1 draw: ${exactlyOne} (${total>0?(exactlyOne/total*100).toFixed(1):0}%)`);
  console.log(`  Absent from 0 draws:        ${zeroAbsence}`);
  console.log(`  Absent from >1 draws:       ${moreThanOne}`);
  console.log(`  Average absences per number: ${avgAbsence}`);

  if (total > 0 && exactlyOne/total > 0.5) {
    console.log(`\n  ✅ CONFIRMED: Most numbers absent from exactly 1 home lottery draw!`);
    console.log(`  → USER'S PATTERN IS VERIFIED`);
    console.log(`  → The "missing" draw = when the number becomes NEW in that cycle`);
  } else {
    console.log(`\n  Results summary printed above. Check absence count distribution.`);
  }

  // Distribution of absence counts
  const absDist = {};
  absenceCounts.forEach((c) => { absDist[c]=(absDist[c]||0)+1; });
  console.log(`\n  Absence count distribution:`);
  Object.entries(absDist).sort((a,b)=>Number(a[0])-Number(b[0])).forEach(([k,v]) => {
    const bar = "█".repeat(Math.round(v/2));
    console.log(`    Absent ${k}×: ${String(v).padEnd(5)} numbers ${bar}`);
  });
}

// ─────────────────────────────────────────────────────────────
// STEP 5 — PREDICT REMAINING
// ─────────────────────────────────────────────────────────────
function predictRemaining(currentCycle, homeLotteryMap, lotteryInfo, allDraws) {
  if (!currentCycle) { console.log("  ⚠️  No current cycle"); return; }

  // Get remaining numbers
  const drawn    = new Set();
  currentCycle.drawEntries.forEach((d) => {
    d.numbers.forEach((n) => { if (n.isNew) drawn.add(n.number); });
  });
  const allNums  = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));
  const remaining = allNums.filter((n) => !drawn.has(n));

  // Find home lottery for each remaining number
  const DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

  // Next draws per lottery (after today: 14/05/2026)
  // 14/05 = Thursday → KN
  // 15/05 = Friday   → SK
  // 16/05 = Saturday → KR
  // 17/05 = Sunday   → SM
  // 18/05 = Monday   → BT
  // 19/05 = Tuesday  → SS
  // 20/05 = Wednesday→ DL

  // Build lottery → primary DOW map
  const lotteryByDOW = new Map();
  for (const [prefix, info] of lotteryInfo) {
    if (!lotteryByDOW.has(info.primaryDOW)) lotteryByDOW.set(info.primaryDOW, prefix);
  }

  console.log(`\n  Remaining ${remaining.length} numbers → home lottery → predicted draw:\n`);
  console.log(`  Number | Home Lottery | Consistent? | Predicted DOW | Next Draw Date`);
  console.log(`  ` + "-".repeat(68));

  const predictionsByLottery = {};

  for (const num of remaining) {
    const data = homeLotteryMap.get(num);
    if (!data) {
      console.log(`  ${num}   | UNKNOWN      | —           | ?             | ?`);
      continue;
    }

    const lottery    = data.homeLottery;
    const consistent = data.consistent ? "✅ YES" : `⚠️  ~${Math.round(data.cyclesPresent*33)}%`;
    const lottInfo   = lotteryInfo.get(lottery);
    const primaryDOW = lottInfo?.primaryDOW;
    const dayName    = primaryDOW !== undefined ? DAYS[primaryDOW] : "?";

    // Calculate next draw date for this lottery
    let nextDate = "?";
    if (primaryDOW !== undefined) {
      const today = new Date("2026-05-14"); // current date
      const daysUntil = (primaryDOW - today.getUTCDay() + 7) % 7 || 7;
      const next = new Date(today);
      next.setDate(today.getDate() + daysUntil);
      nextDate = next.toISOString().split("T")[0];
    }

    if (!predictionsByLottery[lottery]) predictionsByLottery[lottery] = [];
    predictionsByLottery[lottery].push({ num, nextDate, consistent: data.consistent });

    console.log(
      `  ${num}   | ${String(lottery).padEnd(12)} | ${String(consistent).padEnd(11)} | ` +
      `${String(dayName).padEnd(13)} | ${nextDate}`
    );
  }

  // Summary by lottery
  console.log(`\n  PREDICTION SUMMARY BY LOTTERY:`);
  console.log(`  Lottery | Count | Next Draw  | Numbers predicted`);
  console.log(`  ` + "-".repeat(75));

  for (const [lottery, preds] of Object.entries(predictionsByLottery)
    .sort((a,b) => a[1][0]?.nextDate?.localeCompare(b[1][0]?.nextDate))) {

    const nextDate = preds[0]?.nextDate || "?";
    const nums     = preds.map((p) => p.num).join(" ");
    const conf     = preds.filter((p) => p.consistent).length;
    console.log(
      `  ${String(lottery).padEnd(7)} | ${String(preds.length).padEnd(5)} | ` +
      `${String(nextDate).padEnd(10)} | ${nums}`
    );
    console.log(`         | conf: ${conf}/${preds.length} consistent`);
  }
}

// ─────────────────────────────────────────────────────────────
// STEP 6 — VALIDATE ON CYCLE 4
// ─────────────────────────────────────────────────────────────
function validateHomeLottery(allDraws, trainCycles, homeLotteryMap, lotteryInfo) {
  // Build home lottery from cycles 2+3 only
  const dateToLottery = new Map();
  for (const draw of allDraws) {
    const date   = new Date(draw.drawDate).toISOString().split("T")[0];
    const code   = draw.serialNumber || draw.lotteryName || "UNK";
    const match  = code.match(/^([A-Z]{1,3})/);
    const prefix = match ? match[1] : "UNK";
    dateToLottery.set(date, prefix);
  }

  const c23    = trainCycles.filter((c) => c.cycleNumber <= 3);
  const cycle4 = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle4) { console.log("  ⚠️  No cycle 4"); return; }

  // Build home from C2+C3
  const homeFromC23 = new Map();
  for (const cycle of c23) {
    for (const dayEntry of cycle.drawEntries) {
      const date    = new Date(dayEntry.drawDate).toISOString().split("T")[0];
      const lottery = dateToLottery.get(date) || "UNK";
      for (const { number, isNew } of dayEntry.numbers) {
        if (!isNew) continue;
        if (!homeFromC23.has(number)) homeFromC23.set(number, {});
        homeFromC23.get(number)[cycle.cycleNumber] = lottery;
      }
    }
  }

  // Now check cycle 4: for each new number, did it appear in its predicted home lottery?
  let correct=0, total=0, noData=0;

  for (const dayEntry of cycle4.drawEntries) {
    const date    = new Date(dayEntry.drawDate).toISOString().split("T")[0];
    const actualLottery = dateToLottery.get(date) || "UNK";

    for (const { number, isNew } of dayEntry.numbers) {
      if (!isNew) continue;
      total++;

      const data = homeFromC23.get(number);
      if (!data) { noData++; continue; }

      const lotteries  = Object.values(data);
      const allSame    = lotteries.every((l) => l === lotteries[0]);
      const predicted  = lotteries[0]; // use first cycle's lottery as prediction

      if (predicted === actualLottery) correct++;
    }
  }

  const accuracy = total > 0 ? (correct/total*100).toFixed(1) : 0;
  const baseline = 100 / (lotteryInfo.size || 7); // random baseline if 7 lotteries

  console.log(`\n  Validation on cycle 4 (using cycles 2+3 home data):`);
  console.log(`  Total new numbers in cycle 4: ${total}`);
  console.log(`  No home lottery data:         ${noData}`);
  console.log(`  Correct lottery predicted:    ${correct} (${accuracy}%)`);
  console.log(`  Random baseline:              ~${baseline.toFixed(1)}%`);
  console.log(`  Improvement:                  ${(parseFloat(accuracy)/baseline).toFixed(2)}x`);

  if (parseFloat(accuracy) > baseline * 3) {
    console.log(`\n  ✅✅ FORMULA CONFIRMED: Home lottery predicts draw with ${accuracy}% accuracy!`);
    console.log(`  → ${(parseFloat(accuracy)/baseline).toFixed(1)}x better than random`);
    console.log(`  → The draw is NOT random — numbers are assigned to lotteries!`);
  } else if (parseFloat(accuracy) > baseline * 1.5) {
    console.log(`\n  ⚠️  PARTIAL SIGNAL: ${accuracy}% accuracy (${(parseFloat(accuracy)/baseline).toFixed(1)}x random)`);
  } else {
    console.log(`\n  ❌ Accuracy ${accuracy}% ≈ random ${baseline.toFixed(1)}%`);
    console.log(`  Home lottery assignment may not be the mechanism`);
  }
}

// ─────────────────────────────────────────────────────────────
runPhase15().catch((err) => {
  console.error("❌ Phase 15 failed:", err);
  process.exit(1);
});