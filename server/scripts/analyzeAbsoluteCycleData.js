const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const TOTAL_NUMBERS = 10000;

// --------------------------------------------------
// Helpers
// --------------------------------------------------

function parseDate(doc) {
  // Prefer native drawDate
  if (doc.drawDate) {
    const d = new Date(doc.drawDate);

    if (!Number.isNaN(d.getTime())) {
      return d;
    }
  }

  // Fallback: DD/MM/YYYY
  if (typeof doc.date === "string") {
    const match = doc.date.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

    if (match) {
      const [, day, month, year] = match;

      const d = new Date(
        Date.UTC(Number(year), Number(month) - 1, Number(day)),
      );

      if (!Number.isNaN(d.getTime())) {
        return d;
      }
    }
  }

  return null;
}

function dateKey(date) {
  return date.toISOString().slice(0, 10);
}

function formatDate(date) {
  if (!date) return "N/A";

  return date.toISOString().slice(0, 10);
}

function daysBetween(a, b) {
  const MS_PER_DAY = 24 * 60 * 60 * 1000;

  return Math.round((b.getTime() - a.getTime()) / MS_PER_DAY);
}

function extractNumbers(doc) {
  const numbers = new Set();

  if (!Array.isArray(doc.series)) {
    return numbers;
  }

  for (const series of doc.series) {
    if (!Array.isArray(series.numbers)) {
      continue;
    }

    for (const item of series.numbers) {
      if (!item || item.number == null) {
        continue;
      }

      const number = String(item.number).trim().padStart(4, "0");

      if (/^\d{4}$/.test(number)) {
        numbers.add(number);
      }
    }
  }

  return numbers;
}

// --------------------------------------------------
// Consecutive observed-date runs
// --------------------------------------------------

function buildDateRuns(dates) {
  if (dates.length === 0) {
    return [];
  }

  const runs = [];

  let start = dates[0];
  let previous = dates[0];

  for (let i = 1; i < dates.length; i++) {
    const current = dates[i];

    const gap = daysBetween(previous, current);

    if (gap === 1) {
      previous = current;
      continue;
    }

    runs.push({
      start,
      end: previous,
      days: daysBetween(start, previous) + 1,
    });

    start = current;
    previous = current;
  }

  runs.push({
    start,
    end: previous,
    days: daysBetween(start, previous) + 1,
  });

  return runs;
}

// --------------------------------------------------
// Cycle discovery
// --------------------------------------------------

function discoverCycles(dateRecords) {
  const cycles = [];

  let cycleNumber = 1;
  let cycleStart = null;

  let seen = new Set();
  let cycleDates = [];

  for (const record of dateRecords) {
    const { date, numbers } = record;

    if (cycleDates.length === 0) {
      cycleStart = date;
    }

    cycleDates.push(date);

    for (const number of numbers) {
      seen.add(number);
    }

    if (seen.size === TOTAL_NUMBERS) {
      cycles.push({
        cycle: cycleNumber,
        start: cycleStart,
        end: date,
        dates: cycleDates.length,
        complete: true,
      });

      cycleNumber += 1;
      seen = new Set();
      cycleDates = [];
      cycleStart = null;
    }
  }

  // Current incomplete cycle
  if (cycleDates.length > 0) {
    cycles.push({
      cycle: cycleNumber,
      start: cycleStart,
      end: cycleDates[cycleDates.length - 1],
      dates: cycleDates.length,
      complete: false,
      uniqueNumbers: seen.size,
      remaining: TOTAL_NUMBERS - seen.size,
    });
  }

  return cycles;
}

// --------------------------------------------------
// Analyze possible starting points
// --------------------------------------------------

function analyzeStartingPoints(dateRecords) {
  console.log("\n==============================================");
  console.log("POSSIBLE C1 STARTING POINT ANALYSIS");
  console.log("==============================================");

  if (dateRecords.length === 0) {
    return;
  }

  const results = [];

  /*
   * We test each observed date as a possible starting point.
   *
   * For each start:
   * - begin with an empty set
   * - move forward chronologically
   * - stop when all 10,000 numbers are seen
   *
   * This does NOT modify the real cycle data.
   */

  for (let startIndex = 0; startIndex < dateRecords.length; startIndex++) {
    const startRecord = dateRecords[startIndex];

    const seen = new Set();

    let completionIndex = -1;

    for (let i = startIndex; i < dateRecords.length; i++) {
      for (const number of dateRecords[i].numbers) {
        seen.add(number);
      }

      if (seen.size === TOTAL_NUMBERS) {
        completionIndex = i;
        break;
      }
    }

    if (completionIndex !== -1) {
      const endRecord = dateRecords[completionIndex];

      const spanDays = daysBetween(startRecord.date, endRecord.date) + 1;

      const observedDates = completionIndex - startIndex + 1;

      results.push({
        startIndex,
        start: startRecord.date,
        end: endRecord.date,
        spanDays,
        observedDates,
      });
    }
  }

  if (results.length === 0) {
    console.log("No possible starting point completed a full cycle.");
    return;
  }

  // Shortest calendar span first
  results.sort((a, b) => {
    if (a.spanDays !== b.spanDays) {
      return a.spanDays - b.spanDays;
    }

    return a.observedDates - b.observedDates;
  });

  console.log("\nTop 20 possible starts by shortest calendar span:");

  console.table(
    results.slice(0, 20).map((item) => ({
      start: formatDate(item.start),
      end: formatDate(item.end),
      spanDays: item.spanDays,
      observedDates: item.observedDates,
    })),
  );

  console.log("\nTop 20 possible starts by fewest observed draw dates:");

  const byObservedDates = [...results].sort((a, b) => {
    if (a.observedDates !== b.observedDates) {
      return a.observedDates - b.observedDates;
    }

    return a.spanDays - b.spanDays;
  });

  console.table(
    byObservedDates.slice(0, 20).map((item) => ({
      start: formatDate(item.start),
      end: formatDate(item.end),
      observedDates: item.observedDates,
      spanDays: item.spanDays,
    })),
  );
}

// --------------------------------------------------
// Main
// --------------------------------------------------

async function main() {
  console.log("==============================================");
  console.log("ABSOLUTE DATA CYCLE DIAGNOSTIC");
  console.log("==============================================");

  console.log(`MongoDB: ${MONGO_URI}`);
  console.log("Database: numbergrid");
  console.log("Collection: absolute_data");

  try {
    await mongoose.connect(MONGO_URI);

    console.log("\n✅ MongoDB connected");

    // ------------------------------------------------
    // Load AbsoluteData
    // ------------------------------------------------

    const docs = await AbsoluteData.find({})
      .sort({
        drawDate: 1,
        recordNumber: 1,
      })
      .lean();

    console.log(`\n📦 Documents loaded: ${docs.length}`);

    if (docs.length === 0) {
      console.log("⚠️ absolute_data is empty.");
      return;
    }

    // ------------------------------------------------
    // Parse documents
    // ------------------------------------------------

    let invalidDates = 0;
    let drawDateVsStringMismatch = 0;

    const parsedDocs = [];

    for (const doc of docs) {
      const parsedDate = parseDate(doc);

      if (!parsedDate) {
        invalidDates++;
        continue;
      }

      // Check drawDate vs string date if both exist
      if (doc.drawDate && doc.date) {
        const drawDate = new Date(doc.drawDate);

        if (!Number.isNaN(drawDate.getTime())) {
          const drawDateKey = dateKey(drawDate);

          const match = doc.date.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

          if (match) {
            const [, day, month, year] = match;

            const stringDateKey = `${year}-${month}-${day}`;

            if (drawDateKey !== stringDateKey) {
              drawDateVsStringMismatch++;
            }
          }
        }
      }

      parsedDocs.push({
        doc,
        date: parsedDate,
        key: dateKey(parsedDate),
        numbers: extractNumbers(doc),
      });
    }

    console.log(`Valid dates: ${parsedDocs.length}`);
    console.log(`Invalid dates: ${invalidDates}`);

    if (drawDateVsStringMismatch > 0) {
      console.log(`⚠️ drawDate/date mismatches: ${drawDateVsStringMismatch}`);
    } else {
      console.log("✅ No drawDate/date mismatches detected");
    }

    // ------------------------------------------------
    // Group by calendar date
    // ------------------------------------------------

    const dateMap = new Map();

    for (const item of parsedDocs) {
      if (!dateMap.has(item.key)) {
        dateMap.set(item.key, {
          date: item.date,
          numbers: new Set(),
          documents: 0,
        });
      }

      const record = dateMap.get(item.key);

      record.documents++;

      for (const number of item.numbers) {
        record.numbers.add(number);
      }
    }

    const dateRecords = [...dateMap.values()].sort(
      (a, b) => a.date.getTime() - b.date.getTime(),
    );

    console.log(`\n📅 Unique calendar draw dates: ${dateRecords.length}`);

    // ------------------------------------------------
    // Overall date range
    // ------------------------------------------------

    const firstDate = dateRecords[0]?.date;
    const lastDate = dateRecords[dateRecords.length - 1]?.date;

    console.log(`Earliest date: ${formatDate(firstDate)}`);

    console.log(`Latest date:   ${formatDate(lastDate)}`);

    if (firstDate && lastDate) {
      console.log(
        `Calendar span: ${daysBetween(firstDate, lastDate) + 1} days`,
      );
    }

    // ------------------------------------------------
    // Multiple documents on same date
    // ------------------------------------------------

    const multiDocumentDates = dateRecords.filter(
      (record) => record.documents > 1,
    );

    console.log(
      `\nDates with multiple documents/draws: ${multiDocumentDates.length}`,
    );

    if (multiDocumentDates.length > 0) {
      console.log("\nFirst 20 dates with multiple documents:");

      console.table(
        multiDocumentDates.slice(0, 20).map((record) => ({
          date: formatDate(record.date),
          documents: record.documents,
          uniqueNumbers: record.numbers.size,
        })),
      );
    }

    // ------------------------------------------------
    // Gap analysis
    // ------------------------------------------------

    const gaps = [];

    for (let i = 1; i < dateRecords.length; i++) {
      const previous = dateRecords[i - 1];
      const current = dateRecords[i];

      const gapDays = daysBetween(previous.date, current.date);

      if (gapDays > 1) {
        gaps.push({
          from: previous.date,
          to: current.date,
          gapDays,
          missingCalendarDays: gapDays - 1,
        });
      }
    }

    gaps.sort((a, b) => b.gapDays - a.gapDays);

    console.log(`\n🕳️ Gaps between observed draw dates: ${gaps.length}`);

    if (gaps.length > 0) {
      console.log("\nLargest 30 gaps:");

      console.table(
        gaps.slice(0, 30).map((gap) => ({
          from: formatDate(gap.from),
          to: formatDate(gap.to),
          gapDays: gap.gapDays,
          missingCalendarDays: gap.missingCalendarDays,
        })),
      );
    }

    // ------------------------------------------------
    // Consecutive date runs
    // ------------------------------------------------

    const runs = buildDateRuns(dateRecords.map((record) => record.date));

    runs.sort((a, b) => b.days - a.days);

    console.log(`\n📈 Consecutive observed-date runs: ${runs.length}`);

    console.log("\nLongest 20 consecutive runs:");

    console.table(
      runs.slice(0, 20).map((run) => ({
        start: formatDate(run.start),
        end: formatDate(run.end),
        consecutiveCalendarDays: run.days,
      })),
    );

    // ------------------------------------------------
    // Numbers per date
    // ------------------------------------------------

    const numberStats = dateRecords.map((record) => ({
      date: record.date,
      uniqueNumbers: record.numbers.size,
      documents: record.documents,
    }));

    const totalNumbersOnDates = numberStats.reduce(
      (sum, item) => sum + item.uniqueNumbers,
      0,
    );

    const averageNumbersPerDate = totalNumbersOnDates / numberStats.length;

    const minNumbersDate = [...numberStats].sort(
      (a, b) => a.uniqueNumbers - b.uniqueNumbers,
    )[0];

    const maxNumbersDate = [...numberStats].sort(
      (a, b) => b.uniqueNumbers - a.uniqueNumbers,
    )[0];

    console.log("\n🎯 Numbers per observed date");

    console.log(
      `Average unique numbers/date: ${averageNumbersPerDate.toFixed(2)}`,
    );

    console.log(
      `Minimum: ${minNumbersDate.uniqueNumbers} on ${formatDate(minNumbersDate.date)}`,
    );

    console.log(
      `Maximum: ${maxNumbersDate.uniqueNumbers} on ${formatDate(maxNumbersDate.date)}`,
    );

    // ------------------------------------------------
    // Cumulative unique numbers
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("CUMULATIVE UNIQUE NUMBER ANALYSIS");
    console.log("==============================================");

    const cumulativeSeen = new Set();

    let firstFullCoverageDate = null;
    let firstFullCoverageIndex = -1;

    const cumulativeRows = [];

    for (let i = 0; i < dateRecords.length; i++) {
      const record = dateRecords[i];

      for (const number of record.numbers) {
        cumulativeSeen.add(number);
      }

      cumulativeRows.push({
        date: record.date,
        uniqueNumbers: record.numbers.size,
        cumulativeUnique: cumulativeSeen.size,
      });

      if (
        firstFullCoverageDate === null &&
        cumulativeSeen.size === TOTAL_NUMBERS
      ) {
        firstFullCoverageDate = record.date;
        firstFullCoverageIndex = i;
      }
    }

    console.log(`Unique numbers after entire dataset: ${cumulativeSeen.size}`);

    if (firstFullCoverageDate) {
      console.log(
        `First 10,000-number completion: ${formatDate(firstFullCoverageDate)}`,
      );

      console.log(`Observed dates required: ${firstFullCoverageIndex + 1}`);
    } else {
      console.log("⚠️ Dataset never reaches all 10,000 numbers.");
    }

    // ------------------------------------------------
    // Cumulative checkpoints
    // ------------------------------------------------

    const checkpoints = [
      1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 9500, 9900, 9990,
      9999, 10000,
    ];

    console.log("\nCumulative coverage checkpoints:");

    const checkpointRows = [];

    for (const target of checkpoints) {
      const row = cumulativeRows.find(
        (item) => item.cumulativeUnique >= target,
      );

      checkpointRows.push({
        target,
        date: row ? formatDate(row.date) : "NOT REACHED",
        cumulativeUnique: row ? row.cumulativeUnique : cumulativeSeen.size,
      });
    }

    console.table(checkpointRows);

    // ------------------------------------------------
    // Standard cycle discovery
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("CURRENT DATE-BASED CYCLE DISCOVERY");
    console.log("==============================================");

    const cycles = discoverCycles(dateRecords);

    for (const cycle of cycles) {
      console.log(
        `${cycle.complete ? "✅" : "⏳"} C${cycle.cycle}: ` +
          `${formatDate(cycle.start)} -> ` +
          `${formatDate(cycle.end)} ` +
          `(${cycle.dates} observed dates)` +
          (cycle.complete
            ? " COMPLETE"
            : ` INCOMPLETE | ${cycle.uniqueNumbers}/10000`),
      );
    }

    // ------------------------------------------------
    // Cycle gap summary
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("CYCLE BOUNDARY GAP ANALYSIS");
    console.log("==============================================");

    for (let i = 0; i < cycles.length; i++) {
      const cycle = cycles[i];

      console.log(
        `C${cycle.cycle}: ` +
          `${formatDate(cycle.start)} -> ${formatDate(cycle.end)}`,
      );

      if (i > 0) {
        const previous = cycles[i - 1];

        const gap = daysBetween(previous.end, cycle.start);

        console.log(`   Gap from previous cycle end: ${gap} day(s)`);
      }
    }

    // ------------------------------------------------
    // Possible C1 starts
    // ------------------------------------------------

    analyzeStartingPoints(dateRecords);

    // ------------------------------------------------
    // Dates around current C1 boundary
    // ------------------------------------------------

    if (cycles.length > 0) {
      const c1 = cycles[0];

      console.log("\n==============================================");
      console.log("C1 BOUNDARY CONTEXT");
      console.log("==============================================");

      const c1EndIndex = dateRecords.findIndex(
        (record) => dateKey(record.date) === dateKey(c1.end),
      );

      const contextStart = Math.max(0, c1EndIndex - 10);

      const contextEnd = Math.min(dateRecords.length, c1EndIndex + 11);

      console.table(
        dateRecords
          .slice(contextStart, contextEnd)
          .map((record, relativeIndex) => {
            const actualIndex = contextStart + relativeIndex;

            return {
              index: actualIndex,
              date: formatDate(record.date),
              documents: record.documents,
              uniqueNumbers: record.numbers.size,
            };
          }),
      );
    }

    // ------------------------------------------------
    // Final summary
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("DIAGNOSTIC SUMMARY");
    console.log("==============================================");

    console.log(`Documents:                 ${docs.length}`);
    console.log(`Valid dated documents:      ${parsedDocs.length}`);
    console.log(`Invalid dates:              ${invalidDates}`);
    console.log(`Unique calendar dates:      ${dateRecords.length}`);
    console.log(`Date gaps (>1 day):         ${gaps.length}`);
    console.log(`Multiple-doc dates:         ${multiDocumentDates.length}`);
    console.log(`Final unique numbers:       ${cumulativeSeen.size}/10000`);

    if (firstFullCoverageDate) {
      console.log(
        `First complete cycle date:  ${formatDate(firstFullCoverageDate)}`,
      );
    }

    console.log("\n✅ Diagnostic complete.");
    console.log("ℹ️ No database records were modified.");
  } catch (error) {
    console.error("\n❌ ERROR:");
    console.error(error);
    process.exitCode = 1;
  } finally {
    await mongoose.disconnect();
    console.log("\nMongoDB disconnected.");
  }
}

main();
