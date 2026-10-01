const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

const TOTAL_NUMBERS = 10000;
const SAMPLE_SIZE = 20;

/* -------------------------------------------------------
   Helpers
------------------------------------------------------- */

function pad4(value) {
  return String(value).padStart(4, "0");
}

function extractNumbers(draw) {
  const numbers = new Set();

  if (!Array.isArray(draw.series)) {
    return numbers;
  }

  for (const series of draw.series) {
    if (!Array.isArray(series.numbers)) {
      continue;
    }

    for (const item of series.numbers) {
      if (!item || item.number == null) {
        continue;
      }

      const number = pad4(item.number);

      if (/^\d{4}$/.test(number)) {
        numbers.add(number);
      }
    }
  }

  return numbers;
}

function drawLabel(draw) {
  return `${draw.drawDate?.toISOString().slice(0, 10)} | ${draw.serialNumber}`;
}

function printDraw(draw, index = null) {
  const numbers = extractNumbers(draw);

  const prefix = index !== null ? `${String(index).padStart(4, " ")} ` : "";

  console.log(
    `${prefix}` +
      `record=${String(draw.recordNumber).padStart(5, " ")} | ` +
      `date=${draw.date} | ` +
      `drawDate=${draw.drawDate?.toISOString().slice(0, 10)} | ` +
      `serial=${String(draw.serialNumber).padEnd(10, " ")} | ` +
      `numbers=${String(numbers.size).padStart(4, " ")} | ` +
      `file=${draw.fileName || ""}`,
  );
}

/* -------------------------------------------------------
   Cycle reconstruction
------------------------------------------------------- */

function reconstructCycles(draws) {
  const cycles = [];

  let cycleNumber = 1;
  let seen = new Set();

  let cycleStartDraw = null;
  let cycleStartIndex = null;

  for (let i = 0; i < draws.length; i++) {
    const draw = draws[i];

    if (cycleStartDraw === null) {
      cycleStartDraw = draw;
      cycleStartIndex = i;
    }

    const numbers = extractNumbers(draw);

    for (const number of numbers) {
      seen.add(number);
    }

    if (seen.size === TOTAL_NUMBERS) {
      cycles.push({
        cycleNumber,
        startIndex: cycleStartIndex,
        endIndex: i,
        startDraw: cycleStartDraw,
        endDraw: draw,
        drawCount: i - cycleStartIndex + 1,
        uniqueNumbers: seen.size,
        complete: true,
      });

      cycleNumber++;
      seen = new Set();
      cycleStartDraw = null;
      cycleStartIndex = null;
    }
  }

  // Current incomplete cycle
  if (cycleStartDraw !== null) {
    const remaining = [];

    for (let i = 0; i < TOTAL_NUMBERS; i++) {
      const number = pad4(i);

      if (!seen.has(number)) {
        remaining.push(number);
      }
    }

    cycles.push({
      cycleNumber,
      startIndex: cycleStartIndex,
      endIndex: draws.length - 1,
      startDraw: cycleStartDraw,
      endDraw: draws[draws.length - 1],
      drawCount: draws.length - cycleStartIndex,
      uniqueNumbers: seen.size,
      remainingCount: remaining.length,
      remaining,
      complete: false,
    });
  }

  return cycles;
}

/* -------------------------------------------------------
   Duplicate date analysis
------------------------------------------------------- */

function analyzeDuplicateDates(draws) {
  const byDate = new Map();

  for (const draw of draws) {
    const date = draw.drawDate?.toISOString().slice(0, 10);

    if (!date) {
      continue;
    }

    if (!byDate.has(date)) {
      byDate.set(date, []);
    }

    byDate.get(date).push(draw);
  }

  const duplicates = [...byDate.entries()]
    .filter(([, records]) => records.length > 1)
    .sort(([a], [b]) => a.localeCompare(b));

  console.log("\n======================================================");
  console.log("DUPLICATE DRAW DATES");
  console.log("======================================================");

  if (duplicates.length === 0) {
    console.log("No duplicate draw dates found.");
    return;
  }

  for (const [date, records] of duplicates) {
    console.log(`\n${date} — ${records.length} draws`);

    for (const draw of records) {
      printDraw(draw);
    }
  }
}

/* -------------------------------------------------------
   Date/serial ordering validation
------------------------------------------------------- */

function validateOrdering(draws) {
  console.log("\n======================================================");
  console.log("ORDERING VALIDATION");
  console.log("======================================================");

  let violations = 0;

  for (let i = 1; i < draws.length; i++) {
    const previous = draws[i - 1];
    const current = draws[i];

    const previousDate = previous.drawDate?.getTime();
    const currentDate = current.drawDate?.getTime();

    if (previousDate == null || currentDate == null) {
      continue;
    }

    // Date must never go backwards.
    if (currentDate < previousDate) {
      violations++;

      console.log(
        `DATE VIOLATION:\n` +
          `  previous: ${drawLabel(previous)}\n` +
          `  current:  ${drawLabel(current)}`,
      );

      continue;
    }

    // If dates are equal, serialNumber must be ascending.
    if (
      currentDate === previousDate &&
      current.serialNumber.localeCompare(previous.serialNumber) < 0
    ) {
      violations++;

      console.log(
        `SERIAL VIOLATION ON SAME DATE:\n` +
          `  previous: ${drawLabel(previous)}\n` +
          `  current:  ${drawLabel(current)}`,
      );
    }
  }

  console.log(`\nOrdering violations: ${violations}`);

  if (violations === 0) {
    console.log("✓ drawDate → serialNumber ordering is valid.");
  }
}

/* -------------------------------------------------------
   Boundary inspection
------------------------------------------------------- */

function printAroundDate(draws, targetDate, radius = 5) {
  const targetIndex = draws.findIndex(
    (draw) => draw.drawDate?.toISOString().slice(0, 10) === targetDate,
  );

  console.log("\n======================================================");
  console.log(`RECORDS AROUND ${targetDate}`);
  console.log("======================================================");

  if (targetIndex === -1) {
    console.log("Date not found.");
    return;
  }

  const start = Math.max(0, targetIndex - radius);
  const end = Math.min(draws.length, targetIndex + radius + 1);

  for (let i = start; i < end; i++) {
    printDraw(draws[i], i);
  }
}

/* -------------------------------------------------------
   Cycle summary
------------------------------------------------------- */

function printCycleSummary(cycles) {
  console.log("\n======================================================");
  console.log("DRAW-LEVEL CYCLE RECONSTRUCTION");
  console.log("======================================================");

  for (const cycle of cycles) {
    const startDate = cycle.startDraw.drawDate?.toISOString().slice(0, 10);

    const endDate = cycle.endDraw.drawDate?.toISOString().slice(0, 10);

    console.log(
      `\nC${cycle.cycleNumber}` +
        ` | ${cycle.complete ? "COMPLETE" : "INCOMPLETE"}`,
    );

    console.log(`  Start : ${startDate} | ${cycle.startDraw.serialNumber}`);

    console.log(`  End   : ${endDate} | ${cycle.endDraw.serialNumber}`);

    console.log(`  Draws : ${cycle.drawCount}`);

    console.log(`  Unique: ${cycle.uniqueNumbers}`);

    if (!cycle.complete) {
      console.log(`  Missing: ${cycle.remainingCount}`);

      if (cycle.remainingCount <= 100) {
        console.log(`  Missing numbers: ${cycle.remaining.join(", ")}`);
      }
    }
  }
}

/* -------------------------------------------------------
   Detailed cycle boundaries
------------------------------------------------------- */

function printCycleBoundaries(cycles) {
  console.log("\n======================================================");
  console.log("CYCLE BOUNDARIES");
  console.log("======================================================");

  for (const cycle of cycles) {
    const startDate = cycle.startDraw.drawDate?.toISOString().slice(0, 10);

    const endDate = cycle.endDraw.drawDate?.toISOString().slice(0, 10);

    console.log(
      `C${cycle.cycleNumber}: ` +
        `${startDate} ${cycle.startDraw.serialNumber}` +
        `  →  ` +
        `${endDate} ${cycle.endDraw.serialNumber}` +
        ` | draws=${cycle.drawCount}` +
        ` | unique=${cycle.uniqueNumbers}` +
        ` | ${cycle.complete ? "COMPLETE" : "INCOMPLETE"}`,
    );
  }
}

/* -------------------------------------------------------
   Main
------------------------------------------------------- */

async function main() {
  try {
    console.log("Connecting to MongoDB...");
    await mongoose.connect(MONGO_URI);

    console.log("Connected.");
    console.log(`Database: ${mongoose.connection.name}`);

    console.log("\nLoading AbsoluteData...");

    const draws = await AbsoluteData.find({})
      .sort({
        drawDate: 1,
        serialNumber: 1,
      })
      .lean();

    console.log(`Documents loaded: ${draws.length}`);

    if (draws.length === 0) {
      console.log("No AbsoluteData records found.");
      return;
    }

    /* ---------------------------------------------------
       Basic statistics
    --------------------------------------------------- */

    const validDates = draws.filter((draw) => draw.drawDate);

    const uniqueSerials = new Set(
      draws.map((draw) => draw.serialNumber).filter(Boolean),
    );

    const uniqueDates = new Set(
      validDates.map((draw) => draw.drawDate.toISOString().slice(0, 10)),
    );

    console.log("\n======================================================");
    console.log("BASIC DATA");
    console.log("======================================================");

    console.log(`Documents       : ${draws.length}`);
    console.log(`Unique serials  : ${uniqueSerials.size}`);
    console.log(`Unique dates    : ${uniqueDates.size}`);
    console.log(`Valid drawDates : ${validDates.length}`);

    /* ---------------------------------------------------
       First records
    --------------------------------------------------- */

    console.log("\n======================================================");
    console.log(`FIRST ${SAMPLE_SIZE} DRAWS`);
    console.log("======================================================");

    for (let i = 0; i < Math.min(SAMPLE_SIZE, draws.length); i++) {
      printDraw(draws[i], i);
    }

    /* ---------------------------------------------------
       Last records
    --------------------------------------------------- */

    console.log("\n======================================================");
    console.log(`LAST ${SAMPLE_SIZE} DRAWS`);
    console.log("======================================================");

    const lastStart = Math.max(0, draws.length - SAMPLE_SIZE);

    for (let i = lastStart; i < draws.length; i++) {
      printDraw(draws[i], i);
    }

    /* ---------------------------------------------------
       Duplicate dates
    --------------------------------------------------- */

    analyzeDuplicateDates(draws);

    /* ---------------------------------------------------
       Boundary inspection
    --------------------------------------------------- */

    printAroundDate(draws, "2023-01-30", 7);

    printAroundDate(draws, "2025-10-07", 7);

    printAroundDate(draws, "2026-06-07", 7);

    /* ---------------------------------------------------
       Ordering validation
    --------------------------------------------------- */

    validateOrdering(draws);

    /* ---------------------------------------------------
       Cycle reconstruction
    --------------------------------------------------- */

    console.log("\nReconstructing cycles...");

    const cycles = reconstructCycles(draws);

    printCycleSummary(cycles);

    printCycleBoundaries(cycles);

    /* ---------------------------------------------------
       Final
    --------------------------------------------------- */

    console.log("\n======================================================");
    console.log("ANALYSIS COMPLETE");
    console.log("======================================================");

    console.log(`Cycles discovered: ${cycles.length}`);

    const completed = cycles.filter((cycle) => cycle.complete).length;

    console.log(`Completed cycles: ${completed}`);

    const current = cycles.find((cycle) => !cycle.complete);

    if (current) {
      console.log(`Current cycle: C${current.cycleNumber}`);

      console.log(
        `Current coverage: ${current.uniqueNumbers}/${TOTAL_NUMBERS}`,
      );

      console.log(`Current missing: ${current.remainingCount}`);
    }
  } catch (error) {
    console.error("\nERROR:");
    console.error(error);
  } finally {
    await mongoose.disconnect();
    console.log("\nMongoDB disconnected.");
  }
}

main();
