require("dotenv").config();
const mongoose = require("mongoose");
const fs       = require("fs");

const LotteryData = require("../models/FullLotteryData");

// ═══════════════════════════════════════════════════════════════
// REVERSE CYCLE BUILDER
//
// Instead of: day 1 → day 2 → ... until all 10,000 seen
// We do:      latest day → previous day → ... until all 10,000 seen
//
// A "reverse cycle" completes when going backwards we've seen
// all 10,000 unique numbers for the first time.
//
// This may reveal:
//   - How cycles look from the END
//   - Whether end-of-cycle has patterns
//   - Structural information the user noticed
// ═══════════════════════════════════════════════════════════════

async function buildReverseCycles() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB\n");

  // Load ALL draws sorted DESCENDING (newest first)
  const allDraws = await LotteryData.find({}).sort({ drawDate: -1 }).lean();
  console.log(`📋 Total draws in DB: ${allDraws.length}`);
  console.log(`   Date range: ${new Date(allDraws[allDraws.length-1].drawDate).toISOString().split("T")[0]} → ${new Date(allDraws[0].drawDate).toISOString().split("T")[0]}\n`);

  // ─────────────────────────────────────────────────────────────
  // BUILD REVERSE CYCLES
  // Each "reverse cycle" = going backwards until all 10,000 seen
  // ─────────────────────────────────────────────────────────────
  const reverseCycles = [];
  let seen            = new Set();
  let cycleDraws      = [];
  let cycleNum        = 1;

  for (const draw of allDraws) {
    const date     = new Date(draw.drawDate).toISOString().split("T")[0];
    const lottery  = getLotteryCode(draw);
    const numbers  = getAllNumbers(draw);
    const newOnes  = numbers.filter((n) => !seen.has(n));

    // Add to current cycle
    cycleDraws.push({
      date,
      lottery,
      totalDrawn:  numbers.length,
      newCount:    newOnes.length,
      seenSoFar:   seen.size + newOnes.length,
      newNumbers:  newOnes,
    });

    newOnes.forEach((n) => seen.add(n));

    // Cycle complete when all 10,000 seen
    if (seen.size >= 10000) {
      reverseCycles.push({
        cycleNumber:  cycleNum,
        totalDays:    cycleDraws.length,
        startDate:    cycleDraws[0].date,    // most recent date
        endDate:      cycleDraws[cycleDraws.length-1].date, // oldest date
        draws:        cycleDraws,
      });

      console.log(`✅ Reverse Cycle ${cycleNum}: ${cycleDraws.length} draws | ${cycleDraws[0].date} ← ${cycleDraws[cycleDraws.length-1].date}`);

      // Print first 10 and last 10 draws of this reverse cycle
      console.log(`   First 5 draws (most recent):`);
      cycleDraws.slice(0,5).forEach((d) => {
        console.log(`     ${d.date} [${d.lottery}] ${d.newCount} new, seen=${d.seenSoFar}/10000`);
        if (d.newNumbers.length > 0 && d.newNumbers.length <= 10) {
          console.log(`       New: ${d.newNumbers.join(" ")}`);
        }
      });
      console.log(`   Last 5 draws (oldest):`);
      cycleDraws.slice(-5).forEach((d) => {
        console.log(`     ${d.date} [${d.lottery}] ${d.newCount} new, seen=${d.seenSoFar}/10000`);
        if (d.newNumbers.length > 0 && d.newNumbers.length <= 10) {
          console.log(`       New: ${d.newNumbers.join(" ")}`);
        }
      });
      console.log();

      // Reset for next reverse cycle
      seen       = new Set();
      cycleDraws = [];
      cycleNum++;
    }
  }

  // Handle incomplete last reverse cycle
  if (cycleDraws.length > 0) {
    console.log(`⏳ Partial reverse cycle ${cycleNum}: ${cycleDraws.length} draws | ${cycleDraws[0].date} ← ${cycleDraws[cycleDraws.length-1].date}`);
    console.log(`   Numbers seen so far: ${seen.size}/10000 (${(seen.size/100).toFixed(1)}%)`);
    reverseCycles.push({
      cycleNumber: cycleNum,
      totalDays:   cycleDraws.length,
      startDate:   cycleDraws[0].date,
      endDate:     cycleDraws[cycleDraws.length-1].date,
      isPartial:   true,
      draws:       cycleDraws,
    });
  }

  // ─────────────────────────────────────────────────────────────
  // SUMMARY TABLE
  // ─────────────────────────────────────────────────────────────
  console.log("\n" + "═".repeat(65));
  console.log("REVERSE CYCLE SUMMARY");
  console.log("═".repeat(65));
  console.log(`  Cycle | Days | Start (newest)  | End (oldest)    | Avg new/day`);
  console.log(`  ` + "-".repeat(70));

  for (const rc of reverseCycles) {
    const totalNew = rc.draws.reduce((s,d)=>s+d.newCount,0);
    const avgNew   = (totalNew / rc.draws.length).toFixed(1);
    const partial  = rc.isPartial ? " (partial)" : "";
    console.log(
      `  ${String(rc.cycleNumber).padEnd(5)} | ${String(rc.totalDays).padEnd(4)} | ` +
      `${rc.startDate}       | ${rc.endDate}    | ${avgNew}${partial}`
    );
  }

  // ─────────────────────────────────────────────────────────────
  // DETAILED ANALYSIS: LAST-DRAWN NUMBERS IN EACH REVERSE CYCLE
  // The last draws (oldest dates) = the FINAL numbers before cycle reset
  // These should match the "remaining" numbers from forward cycles
  // ─────────────────────────────────────────────────────────────
  console.log("\n" + "═".repeat(65));
  console.log("LAST 30 DRAWS OF EACH REVERSE CYCLE (oldest dates)");
  console.log("These are the numbers that COMPLETED the reverse cycle");
  console.log("= the FIRST numbers drawn in the FORWARD cycle");
  console.log("═".repeat(65));

  for (const rc of reverseCycles.filter((c) => !c.isPartial).slice(0, 3)) {
    console.log(`\n  Reverse Cycle ${rc.cycleNumber} — last 30 draws (going backward):`);
    const last30 = rc.draws.slice(-30);
    last30.forEach((d, i) => {
      console.log(
        `    ${String(rc.draws.length - 30 + i + 1).padEnd(4)} | ` +
        `${d.date} [${d.lottery}] | ` +
        `${d.newCount} new → ${d.newNumbers.slice(0,8).join(" ")}${d.newNumbers.length>8?"...":""}`
      );
    });
  }

  // ─────────────────────────────────────────────────────────────
  // KEY ANALYSIS: NEW NUMBERS PER DAY DISTRIBUTION
  // Going backwards, how many "new" numbers per draw?
  // If pattern exists: this distribution should be non-random
  // ─────────────────────────────────────────────────────────────
  console.log("\n" + "═".repeat(65));
  console.log("NEW NUMBERS PER DAY — REVERSE CYCLE DISTRIBUTION");
  console.log("═".repeat(65));

  for (const rc of reverseCycles.filter((c) => !c.isPartial).slice(0, 3)) {
    const counts = rc.draws.map((d) => d.newCount);

    // Distribution
    const dist = {};
    counts.forEach((c) => { dist[c]=(dist[c]||0)+1; });

    console.log(`\n  Reverse Cycle ${rc.cycleNumber}:`);
    console.log(`    Days with 0 new: ${dist[0]||0}`);
    console.log(`    Days with 1 new: ${dist[1]||0}`);
    console.log(`    Days with 2 new: ${dist[2]||0}`);
    console.log(`    Days with 3-5 new: ${([3,4,5].reduce((s,k)=>s+(dist[k]||0),0))}`);
    console.log(`    Days with 6-10 new: ${([6,7,8,9,10].reduce((s,k)=>s+(dist[k]||0),0))}`);
    console.log(`    Days with >10 new: ${counts.filter((c)=>c>10).length}`);
    console.log(`    Days with >100 new: ${counts.filter((c)=>c>100).length}`);
    console.log(`    Days with >200 new: ${counts.filter((c)=>c>200).length}`);

    // How long does the cycle TAIL look?
    // (last portion where few new numbers per day)
    const tailDays = rc.draws.slice(-50);
    const tailAvg  = tailDays.reduce((s,d)=>s+d.newCount,0) / tailDays.length;
    const headDays = rc.draws.slice(0,50);
    const headAvg  = headDays.reduce((s,d)=>s+d.newCount,0) / headDays.length;
    console.log(`    Head (recent 50 days) avg new: ${headAvg.toFixed(1)}`);
    console.log(`    Tail (oldest 50 days) avg new: ${tailAvg.toFixed(1)}`);
  }

  // ─────────────────────────────────────────────────────────────
  // COMPARE FORWARD VS REVERSE CYCLE LENGTHS
  // ─────────────────────────────────────────────────────────────
  console.log("\n" + "═".repeat(65));
  console.log("FORWARD vs REVERSE CYCLE COMPARISON");
  console.log("═".repeat(65));

  // Build forward cycles for comparison
  const forwardDraws = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const forwardCycles = buildForwardCycles(forwardDraws);

  console.log(`\n  Forward cycles: ${forwardCycles.length}`);
  forwardCycles.forEach((fc) => {
    console.log(`    FWD ${fc.num}: ${fc.days} days | ${fc.start} → ${fc.end}`);
  });

  console.log(`\n  Reverse cycles: ${reverseCycles.length}`);
  reverseCycles.forEach((rc) => {
    const mark = rc.isPartial ? "(partial)" : "";
    console.log(`    REV ${rc.cycleNumber}: ${rc.totalDays} days | ${rc.endDate} → ${rc.startDate} ${mark}`);
  });

  // ─────────────────────────────────────────────────────────────
  // SAVE FULL DATA
  // ─────────────────────────────────────────────────────────────
  const output = {
    generatedAt:   new Date().toISOString(),
    totalDraws:    allDraws.length,
    reverseCycles: reverseCycles.map((rc) => ({
      cycleNumber: rc.cycleNumber,
      totalDays:   rc.totalDays,
      startDate:   rc.startDate,
      endDate:     rc.endDate,
      isPartial:   rc.isPartial || false,
      // Save draw-by-draw detail
      draws: rc.draws.map((d) => ({
        date:       d.date,
        lottery:    d.lottery,
        totalDrawn: d.totalDrawn,
        newCount:   d.newCount,
        seenSoFar:  d.seenSoFar,
        newNumbers: d.newNumbers,
      })),
    })),
  };

  fs.writeFileSync("./reverse_cycles.json", JSON.stringify(output, null, 2));
  console.log(`\n✅ Saved → reverse_cycles.json`);
  console.log(`   Total reverse cycles found: ${reverseCycles.length}`);

  await mongoose.disconnect();
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function getLotteryCode(draw) {
  const code  = draw.serialNumber || draw.lotteryName || "";
  const match = code.match(/^([A-Z]{1,3})/);
  return match ? match[1] : "UNK";
}

function getAllNumbers(draw) {
  const nums = [];
  if (draw.series) {
    draw.series.forEach((s) => {
      s.numbers?.forEach((n) => { if (n.number) nums.push(n.number); });
    });
  }
  return nums;
}

function buildForwardCycles(draws) {
  const cycles = [];
  let seen     = new Set();
  let start    = null;
  let num      = 1;
  let days     = 0;

  for (const draw of draws) {
    const date    = new Date(draw.drawDate).toISOString().split("T")[0];
    const numbers = getAllNumbers(draw);
    if (!start) start = date;
    days++;
    numbers.forEach((n) => seen.add(n));

    if (seen.size >= 10000) {
      cycles.push({ num, days, start, end: date });
      seen  = new Set();
      start = null;
      days  = 0;
      num++;
    }
  }

  if (start) {
    cycles.push({ num, days, start, end: "ongoing", partial: true });
  }

  return cycles;
}

// ─────────────────────────────────────────────────────────────
buildReverseCycles().catch((err) => {
  console.error("❌ Failed:", err);
  process.exit(1);
});