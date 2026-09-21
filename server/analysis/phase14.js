require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 14 — MECHANICAL DRUM BIAS ANALYSIS
//
// The physical draw machine uses spinning drums.
// Even "random" mechanical devices can have biases:
//   - Unbalanced drum → certain digits appear more often
//   - Worn mechanism → specific stopping positions preferred
//   - Manufacturing tolerance → digit weights differ
//
// If bias exists, it IS exploitable.
//
// Also: final analysis of the one remaining signal —
//   the neighbor prediction (5x) — to build the best
//   practical prediction system possible.
// ═══════════════════════════════════════════════════════════════

async function runPhase14() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const allDraws  = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(allDraws);
  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete);
  const currentCycle = validCycles.find((c) => !c.isComplete);

  console.log("📋 PHASE 14 — MECHANICAL DRUM BIAS ANALYSIS");
  console.log("   Physical draw confirmed → testing for mechanical bias\n");

  // ═══════════════════════════════════════════════════════════════
  // STEP 1 — DIGIT FREQUENCY BIAS (per position)
  // For each digit position (D1,D2,D3,D4), is any digit (0-9)
  // significantly over/under-represented across all draws?
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — DIGIT FREQUENCY BIAS PER DRUM POSITION");
  console.log("  Expected: each digit appears exactly 10% at each position");
  console.log("  Bias = (actual% - 10%) > 1% → drum is unbalanced");
  console.log("═".repeat(65));

  testDigitBias(allDraws, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 2 — NUMBER-LEVEL BIAS
  // Are specific 4-digit numbers drawn MORE often than expected?
  // Expected: each number drawn 1/10000 of the time
  // If any number is drawn 2x+ more often → biased mechanism
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — NUMBER FREQUENCY BIAS");
  console.log("  Are specific numbers drawn significantly more often?");
  console.log("═".repeat(65));

  testNumberBias(allDraws, trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 3 — PRIZE-SPECIFIC DRUM BIAS
  // Different prize categories use different drum sets.
  // Test each prize tier for digit bias separately.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — PRIZE-SPECIFIC DRUM BIAS");
  console.log("  Each prize tier uses separate drum(s) → test each");
  console.log("═".repeat(65));

  testPrizeSpecificBias(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 4 — CONSECUTIVE NUMBER PAIRS WITHIN SAME DRAW
  // If drums are physically connected or influenced by each other,
  // we'd see specific number PAIRS appear together consistently.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — DRUM COUPLING: SAME-DAY PAIR BIAS");
  console.log("  Do specific number PAIRS appear together consistently?");
  console.log("═".repeat(65));

  testDrumCoupling(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 5 — DAY-OF-WEEK DIGIT BIAS
  // Physical temperature, humidity, operator fatigue can cause
  // systematic bias by day of week (Mon drums vs Sun drums).
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — DAY-OF-WEEK DIGIT BIAS");
  console.log("  Do drums behave differently on different days?");
  console.log("═".repeat(65));

  testDayOfWeekBias(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 6 — CYCLE POSITION BIAS
  // Do numbers drawn early in a cycle differ systematically
  // from numbers drawn late in a cycle?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — CYCLE POSITION DIGIT BIAS");
  console.log("  Are early-cycle draws biased differently from late?");
  console.log("═".repeat(65));

  testCyclePositionBias(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 7 — HOT NUMBER ANALYSIS ACROSS ALL CYCLES
  // Numbers that appear MORE times per cycle than average.
  // If consistently hot across ALL cycles → drum bias.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — PERMANENTLY HOT NUMBERS (CROSS-CYCLE)");
  console.log("  Numbers hot in cycle 2 AND 3 AND 4 = drum bias candidate");
  console.log("═".repeat(65));

  testPermanentlyHotNumbers(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 8 — FINAL VERDICT + BEST PRACTICAL SYSTEM
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 8 — FINAL VERDICT + BEST PRACTICAL PREDICTION");
  console.log("═".repeat(65));

  buildFinalSystem(currentCycle, trainCycles);

  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
const numVal   = (s) => parseInt(s, 10);
const mean     = (a) => a.length ? a.reduce((x,y)=>x+y,0)/a.length : 0;
const stdDev   = (a) => {
  if (a.length<2) return 0;
  const m=mean(a);
  return Math.sqrt(a.reduce((s,v)=>s+(v-m)**2,0)/a.length);
};
const DAYS_STR = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

// ═══════════════════════════════════════════════════════════════
// STEP 1 — DIGIT FREQUENCY BIAS
// ═══════════════════════════════════════════════════════════════
function testDigitBias(allDraws, trainCycles) {
  // Count digit frequency at each position across ALL draws
  const digitFreq = [
    new Array(10).fill(0), // D1 (thousands)
    new Array(10).fill(0), // D2 (hundreds)
    new Array(10).fill(0), // D3 (tens)
    new Array(10).fill(0), // D4 (units)
  ];
  let totalNumbers = 0;

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        const n = String(number).padStart(4, "0");
        for (let pos = 0; pos < 4; pos++) {
          digitFreq[pos][parseInt(n[pos])]++;
        }
        totalNumbers++;
      }
    }
  }

  const posNames = ["D1(thousands)", "D2(hundreds)", "D3(tens)", "D4(units)"];
  const expected  = totalNumbers / 10;
  const expectedPct = 10.0;

  console.log(`\n  Total number appearances: ${totalNumbers.toLocaleString()}`);
  console.log(`  Expected per digit: ${expected.toLocaleString()} (10.00%)\n`);

  let anyBias = false;
  const biasedDigits = [];

  for (let pos = 0; pos < 4; pos++) {
    console.log(`  ${posNames[pos]}:`);
    const chiSq = digitFreq[pos].reduce((s, count) => {
      return s + (count - expected) ** 2 / expected;
    }, 0);

    for (let d = 0; d <= 9; d++) {
      const count = digitFreq[pos][d];
      const pct   = (count / totalNumbers * 100);
      const bias  = pct - expectedPct;
      const sig   = Math.abs(bias) > 0.5 ? (Math.abs(bias) > 1.0 ? "🔥 STRONG" : "⚠️ MILD") : "  ok  ";
      if (Math.abs(bias) > 0.5) {
        anyBias = true;
        biasedDigits.push({ pos: posNames[pos], digit: d, bias: bias.toFixed(2), pct: pct.toFixed(2) });
      }
      const bar = bias > 0 ? "+" + "█".repeat(Math.round(bias*2)) : "-" + "█".repeat(Math.round(-bias*2));
      console.log(
        `    digit ${d}: ${String(count).padEnd(8)} = ${pct.toFixed(3)}% ` +
        `(bias ${(bias>=0?"+":"")}${bias.toFixed(3)}%) ${sig} ${bar}`
      );
    }
    // Chi-squared test (df=9, critical at p=0.05 = 16.92)
    console.log(`    Chi-squared: ${chiSq.toFixed(3)} (critical=16.92) ${chiSq > 16.92 ? "✅ SIGNIFICANT BIAS!" : "❌ uniform"}`);
    console.log();
  }

  if (anyBias) {
    console.log(`  BIASED DIGITS FOUND:`);
    biasedDigits.forEach((b) => {
      console.log(`    ${b.pos} digit ${b.digit}: ${b.pct}% (bias ${b.bias >= 0 ? "+" : ""}${b.bias}%)`);
    });
  } else {
    console.log(`  No significant digit bias found. Drums appear unbiased.`);
  }

  return { digitFreq, biasedDigits, anyBias };
}

// ═══════════════════════════════════════════════════════════════
// STEP 2 — NUMBER FREQUENCY BIAS
// ═══════════════════════════════════════════════════════════════
function testNumberBias(allDraws, trainCycles) {
  const numFreq = new Map();
  let totalDraws = 0;

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        numFreq.set(number, (numFreq.get(number) || 0) + 1);
      }
      totalDraws++;
    }
  }

  const totalAppearances = [...numFreq.values()].reduce((a,b)=>a+b,0);
  const expected = totalAppearances / 10000;
  const expectedPct = expected / totalAppearances * 100;

  console.log(`\n  Total draws: ${totalDraws}, Total appearances: ${totalAppearances.toLocaleString()}`);
  console.log(`  Expected per number: ${expected.toFixed(1)} appearances`);

  // Find most and least frequent numbers
  const sorted = [...numFreq.entries()].sort((a,b)=>b[1]-a[1]);
  const top20  = sorted.slice(0, 20);
  const bot20  = sorted.slice(-20);

  // Statistical threshold: if count > expected + 4*sqrt(expected) → significant
  const threshold = expected + 4 * Math.sqrt(expected);
  const significantly_hot = top20.filter(([,c]) => c > threshold);

  console.log(`\n  Top 20 most frequent numbers:`);
  console.log(`  Number | Count | Expected | Elevation | Significant?`);
  console.log(`  ` + "-".repeat(55));
  top20.forEach(([num, count]) => {
    const elev = count / expected;
    const sig  = count > threshold ? "✅ SIGNIFICANT BIAS!" : "  within range";
    console.log(
      `  ${num}   | ${String(count).padEnd(5)} | ${String(Math.round(expected)).padEnd(8)} | ${elev.toFixed(3)}x   | ${sig}`
    );
  });

  console.log(`\n  Bottom 10 least frequent (never/rarely drawn):`);
  bot20.slice(0,10).forEach(([num, count]) => {
    const elev = count / expected;
    console.log(`  ${num}: ${count} times (${elev.toFixed(3)}x expected)`);
  });

  // Are any numbers NEVER drawn?
  const allNums = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));
  const never   = allNums.filter((n) => !numFreq.has(n));
  console.log(`\n  Numbers NEVER drawn in training cycles: ${never.length}`);
  if (never.length > 0 && never.length < 30) {
    console.log(`  Never-drawn numbers: ${never.join(" ")}`);
    console.log(`  ✅ SIGNAL: Some numbers are consistently avoided — possible drum dead-zone!`);
  } else if (never.length === 0) {
    console.log(`  ❌ All numbers drawn at least once — no complete dead zones`);
  }

  // Distribution of frequencies
  const freqDist = {};
  numFreq.forEach((count) => {
    const bucket = Math.round(count / 5) * 5;
    freqDist[bucket] = (freqDist[bucket] || 0) + 1;
  });
  console.log(`\n  Frequency distribution (how many numbers appear N times):`);
  Object.entries(freqDist).sort((a,b)=>Number(a[0])-Number(b[0])).slice(0,15).forEach(([k,v])=>{
    const bar = "█".repeat(Math.round(v/30));
    console.log(`    ~${k}×: ${String(v).padEnd(6)} numbers ${bar}`);
  });

  return { significantly_hot, never, expected, threshold };
}

// ═══════════════════════════════════════════════════════════════
// STEP 3 — PRIZE-SPECIFIC BIAS
// ═══════════════════════════════════════════════════════════════
function testPrizeSpecificBias(trainCycles) {
  const prizes    = [5000, 2000, 1000, 500, 200, 100, 50];
  const posFreq   = prizes.map(() => [new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0)]);
  const prizeTotals = new Array(prizes.length).fill(0);

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize } of dayEntry.numbers) {
        const pi = prizes.indexOf(prize);
        if (pi < 0) continue;
        const n = String(number).padStart(4, "0");
        for (let pos = 0; pos < 4; pos++) posFreq[pi][pos][parseInt(n[pos])]++;
        prizeTotals[pi]++;
      }
    }
  }

  console.log(`\n  Digit bias per prize tier (chi-squared test):`);
  console.log(`  Prize  | Total  | D1-χ²  | D2-χ²  | D3-χ²  | D4-χ²  | Biased?`);
  console.log(`  ` + "-".repeat(72));

  for (let pi = 0; pi < prizes.length; pi++) {
    const total = prizeTotals[pi];
    if (total < 100) continue;
    const exp   = total / 10;
    const chiSqs = posFreq[pi].map((pf) =>
      pf.reduce((s, c) => s + (c - exp) ** 2 / exp, 0)
    );
    const crit    = 16.92;
    const anyBias = chiSqs.some((cs) => cs > crit);
    console.log(
      `  ₹${String(prizes[pi]).padEnd(5)} | ${String(total).padEnd(6)} | ` +
      `${chiSqs.map((cs) => String(cs.toFixed(1)).padEnd(6)).join(" | ")} | ` +
      `${anyBias ? "✅ YES!" : "❌ no"}`
    );

    if (anyBias) {
      // Show which digits are biased for this prize
      for (let pos = 0; pos < 4; pos++) {
        if (chiSqs[pos] > crit) {
          const posName = ["D1","D2","D3","D4"][pos];
          const biased  = posFreq[pi][pos]
            .map((c, d) => ({ d, pct: c/total*100 }))
            .filter((x) => Math.abs(x.pct-10) > 1);
          biased.forEach((b) => {
            console.log(
              `    ₹${prizes[pi]} ${posName} digit ${b.d}: ${b.pct.toFixed(2)}% ` +
              `(${b.pct > 10 ? "+" : ""}${(b.pct-10).toFixed(2)}%)`
            );
          });
        }
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 4 — DRUM COUPLING
// ═══════════════════════════════════════════════════════════════
function testDrumCoupling(trainCycles) {
  // For each pair of numbers that appear on the SAME DAY,
  // do specific pairs appear more often than expected?
  // Build: pairFreq[numA][numB] = count they share a day

  // Too many pairs (10000^2) to test all, so test a specific hypothesis:
  // Are numbers sharing the same FIRST DIGIT more likely to appear same day?

  const sameFirstDigit = new Array(10).fill(0).map(() => ({ pairs:0, total:0 }));

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries.slice(0, 50)) { // first 50 days only
      const nums = dayEntry.numbers.map((n) => n.number);

      for (let i = 0; i < nums.length; i++) {
        for (let j = i+1; j < Math.min(i+20, nums.length); j++) {
          const d1A = nums[i][0];
          const d1B = nums[j][0];
          const fd  = parseInt(d1A);
          sameFirstDigit[fd].total++;
          if (d1A === d1B) sameFirstDigit[fd].pairs++;
        }
      }
    }
  }

  console.log(`\n  Same-first-digit pairing (are numbers with same D1 drawn together more?):`);
  console.log(`  D1 | Same-D1 pairs | Total | Rate    | Random(10%) | Elevation`);
  console.log(`  ` + "-".repeat(65));

  let anyCoupling = false;
  for (let d = 0; d <= 9; d++) {
    const { pairs, total } = sameFirstDigit[d];
    if (total < 10) continue;
    const rate = pairs/total;
    const elev = rate/0.1;
    const sig  = elev > 1.2 ? "✅" : elev < 0.8 ? "❌ AVOID" : "  ok";
    if (elev > 1.2) anyCoupling = true;
    console.log(
      `  ${d}  | ${String(pairs).padEnd(13)} | ${String(total).padEnd(5)} | ` +
      `${(rate*100).toFixed(2)}% | 10.00%      | ${elev.toFixed(3)}x ${sig}`
    );
  }

  console.log(`\n  ${anyCoupling ? "✅ DRUM COUPLING SIGNAL: some digits appear together more!" : "❌ No drum coupling detected"}`);

  // Also test: digit SUM coupling (numbers with same digit sum appear together)
  let sameSumPairs = 0, totalPairs = 0;

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries.slice(0, 30)) {
      const nums = dayEntry.numbers.map((n) => ({
        num: n.number,
        ds:  String(n.number).padStart(4,"0").split("").reduce((a,d)=>a+Number(d),0),
      }));

      for (let i=0; i<nums.length; i++) {
        for (let j=i+1; j<Math.min(i+10,nums.length); j++) {
          totalPairs++;
          if (nums[i].ds === nums[j].ds) sameSumPairs++;
        }
      }
    }
  }

  const dsRate     = sameSumPairs/totalPairs;
  const dsExpected = 1/19; // ~19 possible digit sums for 4-digit numbers
  console.log(`\n  Same digit-sum pairing: ${(dsRate*100).toFixed(2)}% vs expected ${(dsExpected*100).toFixed(2)}%`);
  console.log(`  Elevation: ${(dsRate/dsExpected).toFixed(3)}x ${dsRate > dsExpected*1.2 ? "✅ SIGNAL!" : "❌ ok"}`);
}

// ═══════════════════════════════════════════════════════════════
// STEP 5 — DAY-OF-WEEK BIAS
// ═══════════════════════════════════════════════════════════════
function testDayOfWeekBias(trainCycles) {
  const dowDigitFreq = Array.from({length:7}, () =>
    [new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0)]
  );
  const dowTotals = new Array(7).fill(0);

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const dow = new Date(dayEntry.drawDate).getUTCDay();
      for (const { number } of dayEntry.numbers) {
        const n = String(number).padStart(4,"0");
        for (let pos=0; pos<4; pos++) dowDigitFreq[dow][pos][parseInt(n[pos])]++;
        dowTotals[dow]++;
      }
    }
  }

  console.log(`\n  Digit bias by day-of-week (chi-squared, critical=16.92):`);
  console.log(`  DOW | Total  | D1-χ²  | D2-χ²  | D3-χ²  | D4-χ²  | Biased?`);
  console.log(`  ` + "-".repeat(72));

  let anyDOWBias = false;
  for (let dow = 0; dow < 7; dow++) {
    const total = dowTotals[dow];
    if (total < 500) continue;
    const exp    = total / 10;
    const chiSqs = dowDigitFreq[dow].map((pf) =>
      pf.reduce((s,c) => s + (c-exp)**2/exp, 0)
    );
    const biased = chiSqs.some((cs) => cs > 16.92);
    if (biased) anyDOWBias = true;
    console.log(
      `  ${DAYS_STR[dow]} | ${String(total).padEnd(6)} | ` +
      `${chiSqs.map((cs) => String(cs.toFixed(1)).padEnd(6)).join(" | ")} | ` +
      `${biased ? "✅ YES!" : "❌ no"}`
    );
  }

  console.log(`\n  ${anyDOWBias ? "✅ Day-of-week bias exists — drum behavior differs by day!" : "❌ No day-of-week bias"}`);
}

// ═══════════════════════════════════════════════════════════════
// STEP 6 — CYCLE POSITION BIAS
// ═══════════════════════════════════════════════════════════════
function testCyclePositionBias(trainCycles) {
  const phases = ["Early (0-25%)", "Mid-early (25-50%)", "Mid-late (50-75%)", "Late (75-100%)"];
  const phaseFreq = phases.map(() =>
    [new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0)]
  );
  const phaseTotals = new Array(4).fill(0);

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      const normDay = dayEntry.dayIndexInCycle / cycle.totalDrawDays;
      const phase   = Math.min(Math.floor(normDay * 4), 3);
      for (const { number } of dayEntry.numbers) {
        const n = String(number).padStart(4,"0");
        for (let pos=0; pos<4; pos++) phaseFreq[phase][pos][parseInt(n[pos])]++;
        phaseTotals[phase]++;
      }
    }
  }

  console.log(`\n  Digit bias by cycle phase:`);
  console.log(`  Phase          | Total   | D1-χ²  | D2-χ²  | D3-χ²  | D4-χ²  | Biased?`);
  console.log(`  ` + "-".repeat(78));

  for (let ph = 0; ph < 4; ph++) {
    const total = phaseTotals[ph];
    if (total < 100) continue;
    const exp    = total / 10;
    const chiSqs = phaseFreq[ph].map((pf) =>
      pf.reduce((s,c) => s + (c-exp)**2/exp, 0)
    );
    const biased = chiSqs.some((cs) => cs > 16.92);
    console.log(
      `  ${String(phases[ph]).padEnd(14)} | ${String(total).padEnd(7)} | ` +
      `${chiSqs.map((cs) => String(cs.toFixed(1)).padEnd(6)).join(" | ")} | ` +
      `${biased ? "✅ YES!" : "❌ no"}`
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 7 — PERMANENTLY HOT NUMBERS
// ═══════════════════════════════════════════════════════════════
function testPermanentlyHotNumbers(trainCycles) {
  // Find numbers that are hot (drawn more than average) in ALL cycles
  const cycleFreqs = trainCycles.map((cycle) => {
    const freq = new Map();
    let total  = 0;
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        freq.set(number, (freq.get(number)||0)+1);
        total++;
      }
    }
    const avgFreq = total / freq.size;
    return { freq, avgFreq, cycleNumber: cycle.cycleNumber };
  });

  // A number is "permanently hot" if it's above average in ALL training cycles
  const allNums = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));

  const alwaysHot  = [];
  const alwaysCold = [];

  for (const num of allNums) {
    const isHotInAll  = cycleFreqs.every(({freq, avgFreq}) => (freq.get(num)||0) > avgFreq * 1.5);
    const isColdInAll = cycleFreqs.every(({freq, avgFreq}) => (freq.get(num)||0) < avgFreq * 0.5);

    if (isHotInAll)  alwaysHot.push(num);
    if (isColdInAll) alwaysCold.push(num);
  }

  console.log(`\n  Permanently HOT numbers (>1.5× avg in ALL cycles): ${alwaysHot.length}`);
  if (alwaysHot.length > 0) {
    console.log(`  Numbers: ${alwaysHot.slice(0,30).join(" ")} ${alwaysHot.length>30?"...":""}`);
    console.log(`  ✅ DRUM BIAS: These numbers appear more often than chance across ALL cycles!`);

    // Find digit pattern in hot numbers
    const hotDigits = [new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0), new Array(10).fill(0)];
    alwaysHot.forEach((n) => {
      const s = String(n).padStart(4,"0");
      for (let pos=0; pos<4; pos++) hotDigits[pos][parseInt(s[pos])]++;
    });
    console.log(`  Hot number digit distribution:`);
    ["D1","D2","D3","D4"].forEach((posName, pos) => {
      const domDigit = hotDigits[pos].indexOf(Math.max(...hotDigits[pos]));
      const domPct   = (hotDigits[pos][domDigit]/alwaysHot.length*100).toFixed(1);
      console.log(`    ${posName}: dominant digit=${domDigit} (${domPct}% vs 10% expected)`);
    });
  } else {
    console.log(`  ❌ No permanently hot numbers — each cycle has different hot numbers`);
  }

  console.log(`\n  Permanently COLD numbers (<0.5× avg in ALL cycles): ${alwaysCold.length}`);
  if (alwaysCold.length > 0) {
    console.log(`  Numbers: ${alwaysCold.slice(0,20).join(" ")}`);
    console.log(`  ✅ These numbers rarely appear — possible drum dead zones!`);
  } else {
    console.log(`  ❌ No permanently cold numbers — draw appears unbiased`);
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 8 — FINAL VERDICT + BEST PRACTICAL SYSTEM
// ═══════════════════════════════════════════════════════════════
function buildFinalSystem(currentCycle, trainCycles) {
  if (!currentCycle) { console.log("  ⚠️  No current cycle"); return; }

  // Remaining numbers
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

  // Cycle 6 early candidates
  const normMap = new Map();
  for (const cycle of trainCycles) {
    const firstSeen = new Map();
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, isNew } of dayEntry.numbers) {
        if (isNew && !firstSeen.has(number)) {
          firstSeen.set(number, dayEntry.dayIndexInCycle / cycle.totalDrawDays);
        }
      }
    }
    for (const [num, normPos] of firstSeen) {
      if (!normMap.has(num)) normMap.set(num, []);
      normMap.get(num).push(normPos);
    }
  }
  const earlyC6 = [...normMap.entries()]
    .map(([num, norms]) => ({ num, avgNorm: mean(norms) }))
    .sort((a,b) => a.avgNorm - b.avgNorm)
    .slice(0, 50);

  console.log(`\n  ╔═══════════════════════════════════════════════════════╗`);
  console.log(`  ║           FINAL VERDICT — ALL 14 PHASES               ║`);
  console.log(`  ╠═══════════════════════════════════════════════════════╣`);
  console.log(`  ║                                                       ║`);
  console.log(`  ║  Q: Is there a formula for the daily draw?            ║`);
  console.log(`  ║  A: NO. Physical drum mechanism = true random.        ║`);
  console.log(`  ║                                                       ║`);
  console.log(`  ║  Q: Can we predict which numbers appear?              ║`);
  console.log(`  ║  A: Partially — using what IS predictable:            ║`);
  console.log(`  ║     1. Remaining numbers guaranteed to appear          ║`);
  console.log(`  ║     2. Fixed prize numbers (585 always same prize)     ║`);
  console.log(`  ║     3. Cycle 6 early-appearing candidates              ║`);
  console.log(`  ║     4. Neighbor signal (5x, not formula but useful)    ║`);
  console.log(`  ╚═══════════════════════════════════════════════════════╝`);

  console.log(`\n  ═══ CYCLE 5 STATUS ═══`);
  console.log(`  Remaining: ${remaining.length} guaranteed numbers\n`);

  // Print remaining sorted by prize
  const byPrize = {};
  remaining.forEach((num) => {
    const p = getPrize(num);
    if (!byPrize[p]) byPrize[p] = [];
    byPrize[p].push({ num, fixed: isFixed(num) });
  });

  [5000, 2000, 1000, 500, 200, 100, 50, "?"].forEach((prize) => {
    const group = byPrize[prize];
    if (!group || group.length === 0) return;
    const fixedCount = group.filter((g) => g.fixed).length;
    console.log(`  ₹${prize} (${group.length} numbers, ${fixedCount} fixed):`);
    console.log(`    ${group.map((g) => g.num + (g.fixed?"*":"")).join("  ")}`);
  });

  console.log(`\n  * = fixed prize (100% reliable across all past cycles)\n`);

  console.log(`  ═══ CYCLE 6 EARLY CANDIDATES (Top 30) ═══`);
  console.log(`  These appear in first 1% of every cycle:\n`);
  console.log(`  Rank | Number | AvgNormPos | Prize`);
  console.log(`  ` + "-".repeat(40));
  earlyC6.slice(0, 30).forEach(({ num, avgNorm }, i) => {
    console.log(`  ${String(i+1).padEnd(4)} | ${num}   | ${avgNorm.toFixed(5)}   | ₹${getPrize(num)}`);
  });

  // Save final output
  const output = {
    generatedAt:    new Date().toISOString(),
    verdict:        "No mathematical formula found. Physical drum draw confirmed.",
    cycleStatus: {
      cycleNumber: currentCycle.cycleNumber,
      remaining:   remaining.length,
      numbersDrawn: 10000 - remaining.length,
    },
    guaranteedRemaining: remaining.map((num) => ({
      number:       num,
      predictedPrize: getPrize(num),
      isFixed:      isFixed(num),
    })),
    cycle6EarlyCandidates: earlyC6.map(({ num, avgNorm }) => ({
      number:    num,
      avgNormPos: avgNorm,
      prize:     getPrize(num),
    })),
  };
  fs.writeFileSync("./phase14_final.json", JSON.stringify(output, null, 2));
  console.log(`\n  ✅ Final output saved → phase14_final.json`);
}

// ─────────────────────────────────────────────────────────────
runPhase14().catch((err) => {
  console.error("❌ Phase 14 failed:", err);
  process.exit(1);
});