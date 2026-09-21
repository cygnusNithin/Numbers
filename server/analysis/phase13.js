require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");

// ═══════════════════════════════════════════════════════════════
// PHASE 13 — FORMULA DISCOVERY: FULL SEQUENCE ANALYSIS
//
// NOW WE UNDERSTAND THE STRUCTURE:
//   - 374 unique 4-digit numbers drawn EVERY day
//   - 10,000/374 = 26.7 days for full coverage
//   - Cycles 138-401 days → each number drawn ~5-15× per cycle
//
// THREE POSSIBLE FORMULA TYPES TO TEST:
//   A. seed(date) → PRNG → 374 numbers today
//   B. master_list[day × 374 : (day+1) × 374] (pre-shuffled)
//   C. transform(previous_day) → next_day (chain formula)
//
// STEPS:
//   1. Verify 374/day structure in full data
//   2. Test: is today's 374 = sort(yesterday's 374 + offset)?
//   3. Test: is today's 374 derivable from date (date-seeded PRNG)?
//   4. Test: does slot-by-slot tracking reveal formula?
//   5. Test: master list — is the full sequence a sorted permutation?
//   6. Find the actual REPEAT pattern (hot number intervals)
//   7. Build best prediction from all evidence
// ═══════════════════════════════════════════════════════════════

async function runPhase13() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  const allDraws  = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles = detectCycles(allDraws);

  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete);
  const currentCycle = validCycles.find((c) => !c.isComplete);

  console.log("📋 PHASE 13 — FULL SEQUENCE FORMULA SEARCH");
  console.log("   Goal: find f(date/prev) → 374 numbers drawn today\n");

  // ═══════════════════════════════════════════════════════════════
  // STEP 1 — VERIFY 374/DAY STRUCTURE
  // Count TOTAL draws per day (including hot number repeats)
  // ═══════════════════════════════════════════════════════════════
  console.log("═".repeat(65));
  console.log("STEP 1 — VERIFY DRAW SIZE STRUCTURE");
  console.log("  Count total numbers drawn per day (inc. repeats)");
  console.log("═".repeat(65));

  verifyDrawSize(allDraws);

  // ═══════════════════════════════════════════════════════════════
  // STEP 2 — FULL DAY-TO-DAY TRANSFORMATION TEST
  // Does today's FULL draw (374 numbers) transform into tomorrow?
  // Test: shift, complement, sort+offset, reverse
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 2 — FULL DAY-TO-DAY TRANSFORMATION (all 374 numbers)");
  console.log("  Q: tomorrow_draw = T(today_draw) for some transform T?");
  console.log("═".repeat(65));

  testFullDayTransformation(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 3 — DATE-SEEDED PRNG TEST
  // If the lottery seeds a PRNG with the date each day,
  // then: seed = f(year, month, day) → generate 374 numbers
  // Test common date encodings as seeds
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 3 — DATE-SEEDED PRNG TEST");
  console.log("  Q: seed = encode(date) → LCG → first 374 outputs = draw?");
  console.log("═".repeat(65));

  testDateSeededPRNG(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 4 — MASTER LIST HYPOTHESIS
  // Hypothesis: the full cycle is a pre-shuffled list of numbers.
  // Each day draws the next 374 from this list.
  // Find: what ORDER would produce our observed sequence?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 4 — MASTER LIST HYPOTHESIS");
  console.log("  Q: Is the cycle a pre-shuffled list, 374/day?");
  console.log("═".repeat(65));

  testMasterListHypothesis(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 5 — HOT NUMBER INTERVAL ANALYSIS
  // For each number, find the gaps between consecutive appearances.
  // Is the interval constant? Formula-based? Random?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 5 — HOT NUMBER INTERVAL ANALYSIS");
  console.log("  Q: Does number N always reappear every K days?");
  console.log("═".repeat(65));

  analyzeHotNumberIntervals(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 6 — SLOT TRACKING
  // Prize categories have fixed counts: 20, 6, 30, 76, 92, 150
  // Track each "prize slot" across days.
  // Do the 20 ₹5000 slots always contain the same numbers?
  // If slot 1 = number X on day 1, what is slot 1 on day 2?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 6 — PRIZE SLOT TRACKING");
  console.log("  Q: Do the 374 prize slots have fixed or formula-based numbers?");
  console.log("═".repeat(65));

  trackPrizeSlots(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 7 — NUMBER FREQUENCY FORMULA
  // Each number appears ~5-15× per cycle.
  // Is the frequency determined by a formula?
  // e.g., freq(N) = f(N) for some f?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 7 — NUMBER FREQUENCY FORMULA");
  console.log("  Q: Is the number of times N appears per cycle = f(N)?");
  console.log("═".repeat(65));

  analyzeFrequencyFormula(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 8 — SORTED FULL SEQUENCE: BLOCK ANALYSIS
  // Take ALL draws for a full cycle (including repeats).
  // Is there a formula for which BLOCK of numbers appears each day?
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 8 — BLOCK STRUCTURE IN FULL SEQUENCE");
  console.log("  Q: Does the daily draw follow a block pattern in 0-9999?");
  console.log("═".repeat(65));

  analyzeBlockStructure(trainCycles);

  // ═══════════════════════════════════════════════════════════════
  // STEP 9 — BEST PREDICTION SYSTEM (using what works)
  // Neighbor prediction = 5x better than random.
  // Build a practical prediction for cycle 6 day 1.
  // ═══════════════════════════════════════════════════════════════
  console.log("\n" + "═".repeat(65));
  console.log("STEP 9 — BEST CURRENT PREDICTION SYSTEM");
  console.log("  Using neighbor signal (5x) + cycle 6 early numbers");
  console.log("═".repeat(65));

  buildBestPrediction(currentCycle, trainCycles);

  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
const numVal   = (s) => parseInt(s, 10);
const digitSum = (s) => String(s).padStart(4,"0").split("").reduce((a,d)=>a+Number(d),0);
const mean     = (a)  => a.length ? a.reduce((x,y)=>x+y,0)/a.length : 0;
const stdDev   = (a)  => {
  if (a.length<2) return 0;
  const m=mean(a);
  return Math.sqrt(a.reduce((s,v)=>s+(v-m)**2,0)/a.length);
};

// ═══════════════════════════════════════════════════════════════
// STEP 1 — VERIFY DRAW SIZE
// ═══════════════════════════════════════════════════════════════
function verifyDrawSize(allDraws) {
  const sizes = [];

  for (const draw of allDraws) {
    // Count unique 4-digit numbers in this draw
    const nums = new Set();
    if (draw.series) {
      draw.series.forEach((s) => {
        s.numbers?.forEach((n) => nums.add(n.number));
      });
    }
    if (nums.size > 0) sizes.push(nums.size);
  }

  if (sizes.length === 0) {
    console.log("\n  ⚠️  No series data found — using drawEntries instead");
    // Try using the draw entries from cycles
    return;
  }

  const avg    = mean(sizes);
  const std    = stdDev(sizes);
  const minS   = Math.min(...sizes);
  const maxS   = Math.max(...sizes);

  // Distribution
  const buckets = {};
  sizes.forEach((s) => {
    const bucket = Math.round(s / 10) * 10;
    buckets[bucket] = (buckets[bucket] || 0) + 1;
  });

  console.log(`\n  Total draw days analyzed: ${sizes.length}`);
  console.log(`  Numbers per draw: avg=${avg.toFixed(1)} std=${std.toFixed(1)} min=${minS} max=${maxS}`);
  console.log(`  Expected: 374 (from prize structure: 20+6+30+76+92+150)`);
  console.log(`\n  Distribution:`);
  Object.entries(buckets).sort((a,b)=>Number(a[0])-Number(b[0])).forEach(([k,v])=>{
    const bar = "█".repeat(Math.round(v/5));
    console.log(`    ~${k}: ${String(v).padEnd(5)} ${bar}`);
  });

  const near374 = sizes.filter((s) => Math.abs(s-374) <= 10).length;
  console.log(`\n  Days with 364-384 numbers: ${near374}/${sizes.length} (${(near374/sizes.length*100).toFixed(1)}%)`);
  console.log(`  ${near374/sizes.length > 0.8 ? "✅ CONFIRMED: ~374 numbers per draw" : "⚠️  Draw size varies significantly"}`);
}

// ═══════════════════════════════════════════════════════════════
// STEP 2 — FULL DAY-TO-DAY TRANSFORMATION
// ═══════════════════════════════════════════════════════════════
function testFullDayTransformation(trainCycles) {
  const cycle = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle) return;

  // Build full daily draw sets (ALL numbers, not just new)
  const dailySets = [];
  for (const dayEntry of cycle.drawEntries.slice(0, 30)) {
    const all = new Set(dayEntry.numbers.map((n) => n.number));
    dailySets.push({ day: dayEntry.dayIndexInCycle, nums: all });
  }

  console.log(`\n  Testing transforms on ${dailySets.length} consecutive days...\n`);

  // For each consecutive pair, test transforms
  const transformResults = {
    rawOverlap:       { hits:0, total:0 },
    shiftPlus1:       { hits:0, total:0 },
    shiftPlus37:      { hits:0, total:0 },
    complement:       { hits:0, total:0 },
    reverse:          { hits:0, total:0 },
    sortedShift:      { hits:0, total:0 },
    prizeRotation:    { hits:0, total:0 },
  };

  for (let i = 0; i < dailySets.length - 1; i++) {
    const today    = [...dailySets[i].nums];
    const tomorrow = dailySets[i+1].nums;
    const n        = tomorrow.size;

    // Raw overlap: same numbers tomorrow
    const rawHits = today.filter((x) => tomorrow.has(x)).length;
    transformResults.rawOverlap.hits  += rawHits;
    transformResults.rawOverlap.total += n;

    // Shift +1 mod 10000
    const shifted1 = new Set(today.map((x) => String((numVal(x)+1)%10000).padStart(4,"0")));
    transformResults.shiftPlus1.hits  += [...shifted1].filter((x) => tomorrow.has(x)).length;
    transformResults.shiftPlus1.total += n;

    // Shift +37 mod 10000
    const shifted37 = new Set(today.map((x) => String((numVal(x)+37)%10000).padStart(4,"0")));
    transformResults.shiftPlus37.hits  += [...shifted37].filter((x) => tomorrow.has(x)).length;
    transformResults.shiftPlus37.total += n;

    // Complement 9999-N
    const compl = new Set(today.map((x) => String(9999-numVal(x)).padStart(4,"0")));
    transformResults.complement.hits  += [...compl].filter((x) => tomorrow.has(x)).length;
    transformResults.complement.total += n;

    // Digit reverse
    const rev = new Set(today.map((x) => x.split("").reverse().join("")));
    transformResults.reverse.hits  += [...rev].filter((x) => tomorrow.has(x)).length;
    transformResults.reverse.total += n;
  }

  // Random baseline: |today| / 10000 = ~374/10000 = 3.74%
  const randomBaseline = 374 / 10000 * 100;

  console.log(`  Transform              | Hit Rate | Random | Improvement`);
  console.log(`  ` + "-".repeat(60));

  for (const [name, r] of Object.entries(transformResults)) {
    if (r.total === 0) continue;
    const pct   = (r.hits/r.total*100).toFixed(2);
    const improv= (r.hits/r.total*100/randomBaseline).toFixed(2);
    const sig   = parseFloat(improv) > 1.5 ? "✅" : "❌";
    console.log(`  ${String(name).padEnd(22)} | ${String(pct+"%").padEnd(8)} | ${randomBaseline.toFixed(2)}% | ${improv}x ${sig}`);
  }

  // NEW: test if today SORTED + step → tomorrow
  console.log(`\n  Testing sorted-order transforms:`);
  for (const step of [1, 2, 5, 10, 37, 374]) {
    let hits=0, total=0;
    for (let i=0; i<dailySets.length-1; i++) {
      const todaySorted = [...dailySets[i].nums].map(numVal).sort((a,b)=>a-b);
      const tomorrow    = dailySets[i+1].nums;
      const predicted   = new Set(todaySorted.map((v) => String((v+step)%10000).padStart(4,"0")));
      hits  += [...predicted].filter((x) => tomorrow.has(x)).length;
      total += tomorrow.size;
    }
    const pct    = total > 0 ? (hits/total*100).toFixed(2) : "0";
    const improv = (parseFloat(pct)/randomBaseline).toFixed(2);
    console.log(`    sorted+step(${String(step).padEnd(3)}): ${pct}% → ${improv}x ${parseFloat(improv)>1.5?"✅":"❌"}`);
  }

  // NEW: test if tomorrow = f(today, dayIndex)
  console.log(`\n  Testing day-indexed transforms:`);
  for (let i=0; i<Math.min(dailySets.length-1, 5); i++) {
    const today    = [...dailySets[i].nums];
    const tomorrow = dailySets[i+1].nums;
    const dayIdx   = dailySets[i+1].day;

    // Are they the same set shifted by dayIdx?
    const shifted = new Set(today.map((x) => String((numVal(x)+dayIdx)%10000).padStart(4,"0")));
    const hits    = [...shifted].filter((x) => tomorrow.has(x)).length;
    console.log(`    Day ${dailySets[i].day}→${dailySets[i+1].day}: shift by day=${dayIdx}: ${hits}/${tomorrow.size} (${(hits/tomorrow.size*100).toFixed(1)}%)`);
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 3 — DATE-SEEDED PRNG TEST
// ═══════════════════════════════════════════════════════════════
function testDateSeededPRNG(trainCycles) {
  const cycle = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle) return;

  // Simple LCG: x[n+1] = (a*x[n] + c) % 10000
  function lcg(seed, a, c, n) {
    const out = [];
    let x = seed;
    for (let i=0; i<n; i++) {
      x = (a*x + c) % 10000;
      out.push(String(x).padStart(4,"0"));
    }
    return out;
  }

  // Date encoding functions
  function dateToSeeds(dateStr) {
    const d   = new Date(dateStr);
    const y   = d.getUTCFullYear();
    const m   = d.getUTCMonth()+1;
    const day = d.getUTCDate();
    const doy = Math.floor((d - new Date(y,0,0))/(1000*60*60*24));
    return {
      YYYYMMDD:  parseInt(`${y}${String(m).padStart(2,"0")}${String(day).padStart(2,"0")}`),
      MMDD:      m*100 + day,
      DayOfYear: doy,
      Timestamp: Math.floor(d.getTime()/1000/86400), // days since epoch
      Simple:    y + m + day,
      Product:   y * m * day,
      Mod10000:  (y*10000 + m*100 + day) % 10000,
    };
  }

  // Test parameters
  const a_values = [1103515245, 214013, 6364136223846793005, 1664525, 22695477, 1140671485,
                    // Smaller values for mod 10000
                    3, 7, 11, 13, 17, 19, 21, 23, 41, 43, 47];
  const c_values = [0, 1, 12345, 6789, 31337];

  console.log(`\n  Testing date → seed → LCG → 374 numbers on cycle 4 days 1-5...\n`);

  let bestResult = { accuracy: 0, a:0, c:0, seedType:"", day:0 };

  for (const dayEntry of cycle.drawEntries.slice(0, 5)) {
    const actualNums = new Set(dayEntry.numbers.map((n) => n.number));
    const seeds      = dateToSeeds(dayEntry.drawDate);

    for (const [seedType, seedVal] of Object.entries(seeds)) {
      const seed = Math.abs(seedVal) % 10000;

      for (const a of [3, 7, 13, 17, 21, 41, 101, 201, 1001]) {
        for (const c of [0, 1, 7, 37, 100, 1000]) {
          // Generate 374 numbers from seed
          const generated = new Set(lcg(seed, a, c, 374));
          const hits      = [...generated].filter((x) => actualNums.has(x)).length;
          const accuracy  = hits / actualNums.size;

          if (accuracy > bestResult.accuracy) {
            bestResult = { accuracy, a, c, seedType, seedVal, day: dayEntry.dayIndexInCycle, hits, total: actualNums.size };
          }
        }
      }
    }
  }

  const randomBaseline = 374/10000;
  console.log(`  Best date-seeded LCG found:`);
  console.log(`    Seed type: ${bestResult.seedType} = ${bestResult.seedVal}`);
  console.log(`    LCG params: a=${bestResult.a}, c=${bestResult.c}`);
  console.log(`    Hits: ${bestResult.hits}/${bestResult.total} (${(bestResult.accuracy*100).toFixed(2)}%)`);
  console.log(`    Random baseline: ${(randomBaseline*100).toFixed(2)}%`);
  console.log(`    Improvement: ${(bestResult.accuracy/randomBaseline).toFixed(2)}x`);
  console.log(`    ${bestResult.accuracy > randomBaseline*2 ? "✅ SIGNAL!" : "❌ No date-seeded formula"}`);

  // Also test: is today's draw predictable from yesterday's draw + date?
  console.log(`\n  Testing: draw(date D) = LCG(draw(date D-1), date_seed)?`);
  // This would mean the draw is a Markov chain seeded by date
  // Beyond current scope — would need to test many chains
}

// ═══════════════════════════════════════════════════════════════
// STEP 4 — MASTER LIST HYPOTHESIS
// ═══════════════════════════════════════════════════════════════
function testMasterListHypothesis(trainCycles) {
  // Hypothesis: there is one master list for the full cycle.
  // Day 1 draws positions 1-374, day 2 draws 375-748, etc.
  // The master list is a permutation of numbers 0000-9999 (possibly with repeats).

  const cycle = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle) return;

  // Build the "master sequence": all numbers in draw order (including repeats)
  const masterSeq = [];
  for (const dayEntry of cycle.drawEntries) {
    dayEntry.numbers.forEach((n) => {
      masterSeq.push({ number: n.number, val: numVal(n.number), day: dayEntry.dayIndexInCycle, prize: n.prize });
    });
  }

  console.log(`\n  Full cycle 4 master sequence: ${masterSeq.length} total draws`);
  console.log(`  Days: ${cycle.totalDrawDays}, avg per day: ${(masterSeq.length/cycle.totalDrawDays).toFixed(1)}`);
  console.log(`  Expected: 374/day × ${cycle.totalDrawDays} days = ${374*cycle.totalDrawDays}`);

  // Test 1: Is the master sequence sorted?
  const vals = masterSeq.map((x) => x.val);
  const diffs = vals.slice(1).map((v,i) => v-vals[i]);
  const posDiffs = diffs.filter((d)=>d>0).length;
  const negDiffs = diffs.filter((d)=>d<0).length;
  console.log(`\n  Direction: ${posDiffs} ascending, ${negDiffs} descending out of ${diffs.length} steps`);
  console.log(`  ${posDiffs/(posDiffs+negDiffs) > 0.7 ? "✅ Mostly ascending — sorted list hypothesis likely!" : "Mixed — not a simple sorted list"}`);

  // Test 2: If we sort the master sequence, do days become block-sequential?
  // i.e., all low numbers drawn early, high numbers drawn late
  const dayByVal = new Array(10000).fill(null);
  for (const {val, day} of masterSeq) {
    if (dayByVal[val] === null) dayByVal[val] = day; // first appearance
  }

  // Check correlation: is val and firstDay correlated?
  const valArr  = [];
  const dayArr  = [];
  dayByVal.forEach((d, v) => {
    if (d !== null) { valArr.push(v); dayArr.push(d); }
  });

  const pearson = (() => {
    const mv=mean(valArr), md=mean(dayArr);
    let num=0,dv=0,dd=0;
    for (let i=0;i<valArr.length;i++) {
      num+=(valArr[i]-mv)*(dayArr[i]-md);
      dv+=(valArr[i]-mv)**2;
      dd+=(dayArr[i]-md)**2;
    }
    return dv&&dd ? num/Math.sqrt(dv*dd) : 0;
  })();

  console.log(`\n  Correlation(number_value, first_appearance_day): r = ${pearson.toFixed(4)}`);
  console.log(`  ${Math.abs(pearson) > 0.3 ? "✅ SIGNAL: value predicts first-appearance day!" : "❌ No value-day correlation"}`);

  // Test 3: Block structure — does each "block" of 374 consecutive numbers
  // (in VALUE order) tend to appear on the same day?
  console.log(`\n  Block structure test (blocks of 374 by value):`);
  console.log(`  Block       | Numbers    | Days span  | Avg day | Concentrated?`);
  console.log(`  ` + "-".repeat(70));

  for (let block=0; block<10; block++) {
    const lo = block * 1000;
    const hi = lo + 999;
    const days = dayByVal.slice(lo, hi+1).filter((d)=>d!==null);
    if (days.length === 0) continue;
    const avgDay  = mean(days);
    const dayStd  = stdDev(days);
    const dayMin  = Math.min(...days);
    const dayMax  = Math.max(...days);
    const conc    = dayStd < cycle.totalDrawDays / 3;
    console.log(
      `  ${String(`${lo}-${hi}`).padEnd(11)} | ${days.length} numbers | ` +
      `d${dayMin}-d${dayMax} (span=${dayMax-dayMin}) | ` +
      `avg=d${avgDay.toFixed(0)} | ${conc ? "✅ YES" : "❌ spread"}`
    );
  }

  // Test 4: Is there a SPECIFIC ORDERING within each day?
  // Sort each day's numbers and check if they form an arithmetic progression
  console.log(`\n  Within-day sorted sequence analysis (first 10 days):`);
  for (const dayEntry of cycle.drawEntries.slice(0,10)) {
    const sorted = dayEntry.numbers.map((n)=>numVal(n.number)).sort((a,b)=>a-b);
    const diffs2  = sorted.slice(1).map((v,i)=>v-sorted[i]);
    const uniqD  = [...new Set(diffs2)].length;
    const avgD   = mean(diffs2);
    const minD   = Math.min(...diffs2);
    const maxD   = Math.max(...diffs2);
    // Check if it's a near-arithmetic progression
    const isArith = stdDev(diffs2) < 5;
    console.log(
      `  Day ${String(dayEntry.dayIndexInCycle).padEnd(3)}: ` +
      `n=${sorted.length} min=${sorted[0]} max=${sorted[sorted.length-1]} ` +
      `gaps: avg=${avgD.toFixed(0)} min=${minD} max=${maxD} uniq=${uniqD} ` +
      `${isArith?"✅ ARITHMETIC!":""}`
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 5 — HOT NUMBER INTERVALS
// ═══════════════════════════════════════════════════════════════
function analyzeHotNumberIntervals(trainCycles) {
  // For each number, find ALL days it appeared (not just first)
  const numberDays = new Map(); // number → [days it appeared]

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        if (!numberDays.has(number)) numberDays.set(number, []);
        numberDays.get(number).push({
          cycle: cycle.cycleNumber,
          day:   dayEntry.dayIndexInCycle,
          abs:   cycle.cycleNumber * 10000 + dayEntry.dayIndexInCycle,
        });
      }
    }
  }

  // For numbers that appear multiple times within a SINGLE cycle:
  // what are the intervals between appearances?
  const intervals = [];
  const consistentNumbers = []; // numbers where interval is constant

  for (const [num, appearances] of numberDays) {
    // Group by cycle
    const byCycle = {};
    appearances.forEach((a) => {
      if (!byCycle[a.cycle]) byCycle[a.cycle] = [];
      byCycle[a.cycle].push(a.day);
    });

    for (const [cn, days] of Object.entries(byCycle)) {
      const sorted = days.sort((a,b)=>a-b);
      if (sorted.length < 2) continue;

      const gaps = sorted.slice(1).map((d,i)=>d-sorted[i]);
      intervals.push(...gaps);

      // Is the interval constant? (all gaps same)
      const uniqueGaps = [...new Set(gaps)];
      if (uniqueGaps.length === 1 && gaps.length >= 2) {
        consistentNumbers.push({ num, cycle: cn, gap: uniqueGaps[0], count: sorted.length });
      }
    }
  }

  const avgInterval = mean(intervals);
  const stdInterval = stdDev(intervals);

  // Distribution
  const gapDist = {};
  intervals.forEach((g) => {
    if (g <= 50) { gapDist[g] = (gapDist[g]||0)+1; }
  });

  console.log(`\n  Total intervals analyzed: ${intervals.length.toLocaleString()}`);
  console.log(`  Avg interval: ${avgInterval.toFixed(1)} days`);
  console.log(`  Std interval: ${stdInterval.toFixed(1)} days`);
  console.log(`  Numbers with CONSTANT interval (≥2 gaps same): ${consistentNumbers.length}`);

  if (consistentNumbers.length > 0) {
    console.log(`\n  Sample constant-interval numbers:`);
    consistentNumbers.slice(0,20).forEach((c) => {
      console.log(`    ${c.num}: appears every ${c.gap} days in cycle ${c.cycle} (${c.count}× total)`);
    });
  }

  console.log(`\n  Most common intervals between appearances:`);
  const topGaps = Object.entries(gapDist).sort((a,b)=>b[1]-a[1]).slice(0,15);
  topGaps.forEach(([gap, count]) => {
    const bar = "█".repeat(Math.round(count/100));
    console.log(`    Gap = ${String(gap).padEnd(4)}: ${String(count).padEnd(7)} occurrences  ${bar}`);
  });

  // KEY: Is the most common interval = 374/374 = 1? or related to 374?
  const mode = topGaps[0]?.[0];
  console.log(`\n  Mode interval: ${mode} days`);
  console.log(`  374 / ${mode} = ${(374/Number(mode)).toFixed(2)}`);
  console.log(`  10000 / 374 = ${(10000/374).toFixed(2)}`);
  console.log(`  ${Number(mode) === 1 ? "→ Numbers reappear EVERY day (very hot)" : `→ Numbers repeat every ~${mode} days`}`);
}

// ═══════════════════════════════════════════════════════════════
// STEP 6 — PRIZE SLOT TRACKING
// ═══════════════════════════════════════════════════════════════
function trackPrizeSlots(trainCycles) {
  // Prize structure: 20×₹5000, 6×₹2000, 30×₹1000, 76×₹500, 92×₹200, 150×₹100
  // For each prize tier, track which numbers fill each slot across days.
  // Slot = sorted position within that prize tier for that day.

  const prizeSlotDist = {
    5000: [], 2000: [], 1000: [], 500: [], 200: [], 100: []
  };

  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries.slice(0, 20)) {
      for (const [prize, slots] of Object.entries(prizeSlotDist)) {
        const numsForPrize = dayEntry.numbers
          .filter((n) => n.prize === Number(prize))
          .map((n) => numVal(n.number))
          .sort((a,b) => a-b);
        if (numsForPrize.length > 0) slots.push(numsForPrize);
      }
    }
  }

  console.log(`\n  Prize slot analysis (sorted position → number value):\n`);
  for (const [prize, days] of Object.entries(prizeSlotDist)) {
    if (days.length === 0) continue;
    const slotCount = days[0]?.length || 0;
    if (slotCount === 0) continue;

    console.log(`  ₹${prize} (${slotCount} slots per day, ${days.length} day-samples):`);

    // For each slot position, what's the distribution of number values?
    const slotStats = [];
    for (let slot=0; slot<Math.min(slotCount, 5); slot++) {
      const vals = days.map((d) => d[slot]).filter((v)=>v!==undefined);
      if (vals.length === 0) continue;
      slotStats.push({
        slot, avg: mean(vals), std: stdDev(vals),
        min: Math.min(...vals), max: Math.max(...vals),
      });
    }

    slotStats.forEach((s) => {
      console.log(
        `    Slot ${String(s.slot+1).padEnd(2)}: avg=${Math.round(s.avg)} ` +
        `std=${Math.round(s.std)} range=[${s.min}-${s.max}]`
      );
    });

    // Is slot 1 always the same number? (deterministic slots)
    const slot1vals = days.map((d) => d[0]).filter((v)=>v!==undefined);
    const uniqueSlot1 = new Set(slot1vals).size;
    console.log(`    Slot 1 unique values: ${uniqueSlot1}/${slot1vals.length} (${uniqueSlot1===1?"✅ FIXED!":"varied"})`);
  }

  // KEY: For ₹5000 (20 slots), are the same 20 numbers ALWAYS drawn?
  console.log(`\n  ── Are the same 20 numbers ALWAYS drawn for ₹5000? ──`);
  const cycle4   = trainCycles.find((c) => c.cycleNumber === 4);
  const fiveKByDay = new Map(); // day → Set of ₹5000 numbers

  if (cycle4) {
    for (const dayEntry of cycle4.drawEntries) {
      const nums5k = new Set(
        dayEntry.numbers.filter((n) => n.prize === 5000).map((n) => n.number)
      );
      fiveKByDay.set(dayEntry.dayIndexInCycle, nums5k);
    }

    // Find numbers that appear as ₹5000 in EVERY day
    let commonSet = null;
    for (const [, nums] of fiveKByDay) {
      commonSet = commonSet === null ? new Set([...nums]) : new Set([...commonSet].filter((x) => nums.has(x)));
    }
    commonSet = commonSet ?? new Set();
    console.log(`  Numbers winning ₹5000 EVERY day in cycle 4: ${commonSet.size}`);
    if (commonSet.size > 0) {
      console.log(`  Numbers: ${[...commonSet].join(", ")}`);
      console.log(`  ✅ THESE ARE ALWAYS-₹5000 NUMBERS — FIXED IN SYSTEM`);
    }

    // How many unique ₹5000 numbers appear per day?
    const dailyCounts = [...fiveKByDay.values()].map((s) => s.size);
    console.log(`  ₹5000 numbers per day: avg=${mean(dailyCounts).toFixed(1)} min=${Math.min(...dailyCounts)} max=${Math.max(...dailyCounts)}`);
    console.log(`  Expected from prize structure: 20`);
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 7 — NUMBER FREQUENCY FORMULA
// ═══════════════════════════════════════════════════════════════
function analyzeFrequencyFormula(trainCycles) {
  // How many times does each number appear per cycle?
  const freqByCycle = new Map();

  for (const cycle of trainCycles) {
    const freq = new Map();
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        freq.set(number, (freq.get(number) || 0) + 1);
      }
    }
    freqByCycle.set(cycle.cycleNumber, freq);
  }

  // Compare frequencies across cycles: is freq(N, cycle2) ≈ freq(N, cycle3)?
  const c2freq = freqByCycle.get(2);
  const c3freq = freqByCycle.get(3);
  const c4freq = freqByCycle.get(4);

  if (!c2freq || !c3freq || !c4freq) return;

  // Correlation between frequencies across cycles
  const nums    = [...c2freq.keys()].filter((n) => c3freq.has(n) && c4freq.has(n));
  const f2      = nums.map((n) => c2freq.get(n));
  const f3      = nums.map((n) => c3freq.get(n));
  const f4      = nums.map((n) => c4freq.get(n));

  const pearson23 = (() => {
    const m2=mean(f2), m3=mean(f3);
    let num=0,d2=0,d3=0;
    for(let i=0;i<f2.length;i++){num+=(f2[i]-m2)*(f3[i]-m3);d2+=(f2[i]-m2)**2;d3+=(f3[i]-m3)**2;}
    return d2&&d3?num/Math.sqrt(d2*d3):0;
  })();

  const pearson34 = (() => {
    const m3=mean(f3), m4=mean(f4);
    let num=0,d3=0,d4=0;
    for(let i=0;i<f3.length;i++){num+=(f3[i]-m3)*(f4[i]-m4);d3+=(f3[i]-m3)**2;d4+=(f4[i]-m4)**2;}
    return d3&&d4?num/Math.sqrt(d3*d4):0;
  })();

  console.log(`\n  Cross-cycle frequency correlation:`);
  console.log(`    C2↔C3: r=${pearson23.toFixed(4)}`);
  console.log(`    C3↔C4: r=${pearson34.toFixed(4)}`);
  console.log(`    ${Math.max(Math.abs(pearson23),Math.abs(pearson34))>0.5?"✅ SIGNAL: frequency is stable across cycles!":"❌ Frequency changes each cycle"}`);

  // Distribution of frequencies
  const allFreqs = [...c4freq.values()];
  const freqDist = {};
  allFreqs.forEach((f) => { freqDist[f]=(freqDist[f]||0)+1; });

  console.log(`\n  Cycle 4 frequency distribution:`);
  console.log(`  Times drawn | Count of numbers`);
  Object.entries(freqDist).sort((a,b)=>Number(a[0])-Number(b[0])).forEach(([f,c])=>{
    const bar = "█".repeat(Math.round(c/50));
    console.log(`  ${String(f+"×").padEnd(12)}: ${String(c).padEnd(6)} ${bar}`);
  });

  // Are high-frequency numbers always the same across cycles?
  const hotNums = [...c4freq.entries()].filter(([,f])=>f>20).map(([n])=>n);
  const alsoHotInC2 = hotNums.filter((n) => (c2freq.get(n)||0) > 15);
  const alsoHotInC3 = hotNums.filter((n) => (c3freq.get(n)||0) > 15);

  console.log(`\n  Hot numbers (freq>20 in C4): ${hotNums.length}`);
  console.log(`  Also hot in C2: ${alsoHotInC2.length} (${(alsoHotInC2.length/hotNums.length*100).toFixed(1)}%)`);
  console.log(`  Also hot in C3: ${alsoHotInC3.length} (${(alsoHotInC3.length/hotNums.length*100).toFixed(1)}%)`);
  console.log(`  ${alsoHotInC2.length/hotNums.length > 0.5 ? "✅ Hot numbers are CONSISTENT across cycles!" : "❌ Hot numbers change each cycle"}`);

  if (alsoHotInC2.length > 0) {
    console.log(`  Consistent hot numbers (sample): ${alsoHotInC2.slice(0,10).join(", ")}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// STEP 8 — BLOCK STRUCTURE
// ═══════════════════════════════════════════════════════════════
function analyzeBlockStructure(trainCycles) {
  const cycle = trainCycles.find((c) => c.cycleNumber === 4);
  if (!cycle) return;

  // For each day, which "block" (range of 374 values) dominates?
  // Block 0: 0000-0373, Block 1: 0374-0747, etc.
  const blockSize = 374;
  const numBlocks = Math.ceil(10000/blockSize);

  console.log(`\n  Testing if daily draws concentrate in specific 374-value blocks:`);
  console.log(`  Day | DomBlock | NumInBlock | % of day | Block range`);
  console.log(`  ` + "-".repeat(65));

  for (const dayEntry of cycle.drawEntries.slice(0,15)) {
    const nums = dayEntry.numbers.map((n)=>numVal(n.number));
    const blockCounts = new Array(numBlocks).fill(0);
    nums.forEach((v) => blockCounts[Math.min(Math.floor(v/blockSize), numBlocks-1)]++);
    const maxBlock = blockCounts.indexOf(Math.max(...blockCounts));
    const maxCount = blockCounts[maxBlock];
    const pct = (maxCount/nums.length*100).toFixed(1);
    const lo  = maxBlock*blockSize;
    const hi  = Math.min(lo+blockSize-1, 9999);
    const expected = nums.length/numBlocks;
    const conc = maxCount > expected * 1.5;
    console.log(
      `  ${String(dayEntry.dayIndexInCycle).padEnd(3)} | ${String(maxBlock).padEnd(8)} | ${String(maxCount).padEnd(10)} | ${String(pct+"%").padEnd(8)} | ` +
      `${lo}-${hi} ${conc?"✅ concentrated!":""}`
    );
  }

  // Expected if random: 1/27 = 3.7% per block
  const randomExpected = nums_per_day / numBlocks;
  function nums_per_day() { return 374; }
  console.log(`\n  Random expected per block: ~${(100/numBlocks).toFixed(1)}%`);
  console.log(`  If >10%: blocks are concentrated on specific days`);
}

// ═══════════════════════════════════════════════════════════════
// STEP 9 — BEST PREDICTION SYSTEM
// ═══════════════════════════════════════════════════════════════
function buildBestPrediction(currentCycle, trainCycles) {
  if (!currentCycle) { console.log("  ⚠️  No current cycle"); return; }

  // Get last draw day
  const lastDay = currentCycle.drawEntries[currentCycle.drawEntries.length - 1];
  if (!lastDay) return;

  const lastNums = new Set(lastDay.numbers.map((n) => n.number));
  const allNums  = Array.from({length:10000}, (_,i) => String(i).padStart(4,"0"));

  // Remaining undrawn in cycle 5
  const drawnSoFar = new Set();
  currentCycle.drawEntries.forEach((d) => d.numbers.forEach((n) => { if(n.isNew) drawnSoFar.add(n.number); }));
  const remaining = new Set(allNums.filter((n) => !drawnSoFar.has(n)));

  console.log(`\n  Cycle 5 status: ${remaining.size} remaining to complete cycle`);
  console.log(`  Last draw: day ${lastDay.dayIndexInCycle}, ${lastNums.size} numbers drawn`);

  // Prediction 1: Neighbors of last draw (±5)
  const neighbors = new Set();
  for (const num of lastNums) {
    const v = numVal(num);
    for (let k=-5; k<=5; k++) {
      if (k!==0) neighbors.add(String((v+k+10000)%10000).padStart(4,"0"));
    }
  }
  const neighborRemaining = [...neighbors].filter((n) => remaining.has(n));

  // Prediction 2: Consistent hot numbers from training cycles
  const hotFreq = new Map();
  for (const cycle of trainCycles) {
    for (const dayEntry of cycle.drawEntries) {
      for (const { number } of dayEntry.numbers) {
        hotFreq.set(number, (hotFreq.get(number)||0)+1);
      }
    }
  }
  const hotNums = [...hotFreq.entries()]
    .filter(([,f]) => f > 30)
    .sort((a,b) => b[1]-a[1])
    .map(([n]) => n);

  // Prediction 3: Numbers not drawn recently (overdue)
  const lastDrawnDay = new Map();
  currentCycle.drawEntries.forEach((d) => {
    d.numbers.forEach((n) => lastDrawnDay.set(n.number, d.dayIndexInCycle));
  });
  const mostOverdue = [...lastDrawnDay.entries()]
    .sort((a,b) => a[1]-b[1])
    .slice(0, 100)
    .map(([n]) => n);

  console.log(`\n  ═══ TOMORROW'S PREDICTION (cycle 5) ═══`);
  console.log(`\n  METHOD 1: Neighbor of last draw (±5)`);
  console.log(`    Candidate count: ${neighborRemaining.length} remaining numbers`);
  console.log(`    Numbers: ${neighborRemaining.slice(0,30).join(" ")}${neighborRemaining.length>30?"...":""}`);

  console.log(`\n  METHOD 2: Consistent hot numbers (drawn >30× across training cycles)`);
  const hotRemaining = hotNums.filter((n) => !drawnSoFar.has(n));
  console.log(`    Hot numbers still remaining: ${hotRemaining.length}`);
  console.log(`    Numbers: ${hotRemaining.slice(0,20).join(" ")}`);

  console.log(`\n  METHOD 3: Most overdue numbers (drawn least recently)`);
  console.log(`    Overdue: ${mostOverdue.slice(0,20).join(" ")}`);

  // Combined prediction
  const combined = new Set([...neighborRemaining, ...hotRemaining.slice(0,20)]);
  console.log(`\n  COMBINED PREDICTION (neighbor + hot): ${combined.size} numbers`);
  console.log(`  Numbers: ${[...combined].sort().join(" ")}`);

  // Remaining 44 guaranteed numbers
  console.log(`\n  GUARANTEED remaining ${remaining.size} (all will appear before cycle ends):`);
  console.log(`  ${[...remaining].sort().join("  ")}`);
}

// ─────────────────────────────────────────────────────────────
runPhase13().catch((err) => {
  console.error("❌ Phase 13 failed:", err);
  process.exit(1);
});