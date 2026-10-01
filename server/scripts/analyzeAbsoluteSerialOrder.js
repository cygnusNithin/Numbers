const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

function parseDate(doc) {
  if (doc.drawDate) {
    const d = new Date(doc.drawDate);

    if (!Number.isNaN(d.getTime())) {
      return d;
    }
  }

  if (typeof doc.date === "string") {
    const match = doc.date.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

    if (match) {
      const [, day, month, year] = match;

      return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
    }
  }

  return null;
}

function dateKey(date) {
  return date.toISOString().slice(0, 10);
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

async function main() {
  try {
    await mongoose.connect(MONGO_URI);

    console.log("==============================================");
    console.log("ABSOLUTE DATA SERIAL ORDER ANALYSIS");
    console.log("==============================================\n");

    const docs = await AbsoluteData.find({})
      .sort({
        serialNumber: 1,
      })
      .lean();

    console.log(`Documents: ${docs.length}`);

    if (docs.length === 0) {
      console.log("No data.");
      return;
    }

    // ------------------------------------------------
    // Basic serial information
    // ------------------------------------------------

    console.log("\nFIRST 30 SERIALS");
    console.log("================\n");

    console.table(
      docs.slice(0, 30).map((doc, index) => {
        const date = parseDate(doc);

        return {
          index,
          serialNumber: doc.serialNumber,
          date: date ? dateKey(date) : "INVALID",
          recordNumber: doc.recordNumber,
          fileName: doc.fileName,
        };
      }),
    );

    console.log("\nLAST 30 SERIALS");
    console.log("================\n");

    console.table(
      docs.slice(-30).map((doc, relativeIndex) => {
        const index = docs.length - 30 + relativeIndex;

        const date = parseDate(doc);

        return {
          index,
          serialNumber: doc.serialNumber,
          date: date ? dateKey(date) : "INVALID",
          recordNumber: doc.recordNumber,
          fileName: doc.fileName,
        };
      }),
    );

    // ------------------------------------------------
    // Check whether serials are numeric
    // ------------------------------------------------

    const numericSerials = docs.filter((doc) =>
      /^\d+$/.test(String(doc.serialNumber)),
    );

    console.log("\nSERIAL FORMAT");
    console.log("=============");

    console.log(`Numeric serials: ${numericSerials.length}/${docs.length}`);

    // ------------------------------------------------
    // Check serial ordering against dates
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("SERIAL → DATE ORDER CHECK");
    console.log("==============================================\n");

    let backwards = 0;

    const backwardsRows = [];

    let previousDate = null;
    let previousSerial = null;

    for (const doc of docs) {
      const date = parseDate(doc);

      if (!date) {
        continue;
      }

      if (previousDate && date.getTime() < previousDate.getTime()) {
        backwards++;

        if (backwardsRows.length < 50) {
          backwardsRows.push({
            previousSerial,
            previousDate: dateKey(previousDate),
            currentSerial: doc.serialNumber,
            currentDate: dateKey(date),
          });
        }
      }

      previousDate = date;
      previousSerial = doc.serialNumber;
    }

    console.log(
      `Date-order violations while walking serial order: ${backwards}`,
    );

    if (backwardsRows.length > 0) {
      console.log("\nFirst violations:");

      console.table(backwardsRows);
    }

    // ------------------------------------------------
    // Serial increments
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("SERIAL SEQUENCE CHECK");
    console.log("==============================================\n");

    let numericGaps = 0;

    const serialGaps = [];

    for (let i = 1; i < docs.length; i++) {
      const previous = Number(docs[i - 1].serialNumber);
      const current = Number(docs[i].serialNumber);

      if (Number.isFinite(previous) && Number.isFinite(current)) {
        const difference = current - previous;

        if (difference !== 1) {
          numericGaps++;

          if (serialGaps.length < 100) {
            serialGaps.push({
              previousSerial: docs[i - 1].serialNumber,
              currentSerial: docs[i].serialNumber,
              difference,
            });
          }
        }
      }
    }

    console.log(`Non-consecutive serial transitions: ${numericGaps}`);

    if (serialGaps.length > 0) {
      console.table(serialGaps);
    }

    // ------------------------------------------------
    // Same date / multiple serials
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("MULTIPLE SERIALS ON SAME DATE");
    console.log("==============================================\n");

    const dateMap = new Map();

    for (const doc of docs) {
      const date = parseDate(doc);

      if (!date) continue;

      const key = dateKey(date);

      if (!dateMap.has(key)) {
        dateMap.set(key, []);
      }

      dateMap.get(key).push(doc);
    }

    const duplicateDates = [];

    for (const [date, records] of dateMap) {
      if (records.length > 1) {
        duplicateDates.push({
          date,
          serials: records.map((doc) => doc.serialNumber),
          records: records.length,
        });
      }
    }

    console.table(duplicateDates);

    // ------------------------------------------------
    // Draw-event cycle reconstruction
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("SERIAL-BASED CYCLE RECONSTRUCTION");
    console.log("==============================================\n");

    const TOTAL_NUMBERS = 10000;

    const seen = new Set();

    let cycle = 1;
    let cycleStart = null;
    let cycleDraws = 0;

    const cycles = [];

    for (const doc of docs) {
      const date = parseDate(doc);

      if (!date) continue;

      if (cycleDraws === 0) {
        cycleStart = {
          serialNumber: doc.serialNumber,
          date,
        };
      }

      cycleDraws++;

      const numbers = extractNumbers(doc);

      for (const number of numbers) {
        seen.add(number);
      }

      if (seen.size === TOTAL_NUMBERS) {
        cycles.push({
          cycle,
          startSerial: cycleStart.serialNumber,
          startDate: dateKey(cycleStart.date),
          endSerial: doc.serialNumber,
          endDate: dateKey(date),
          draws: cycleDraws,
          uniqueNumbers: seen.size,
          complete: true,
        });

        cycle++;

        seen.clear();
        cycleDraws = 0;
        cycleStart = null;
      }
    }

    if (cycleDraws > 0) {
      cycles.push({
        cycle,
        startSerial: cycleStart.serialNumber,
        startDate: dateKey(cycleStart.date),
        endSerial: docs[docs.length - 1].serialNumber,
        endDate: dateKey(parseDate(docs[docs.length - 1])),
        draws: cycleDraws,
        uniqueNumbers: seen.size,
        complete: false,
      });
    }

    console.table(cycles);

    // ------------------------------------------------
    // Final
    // ------------------------------------------------

    console.log("\n==============================================");
    console.log("SUMMARY");
    console.log("==============================================");

    console.log(`Documents:                 ${docs.length}`);

    console.log(`Numeric serials:           ${numericSerials.length}`);

    console.log(`Date-order violations:     ${backwards}`);

    console.log(`Serial sequence gaps:      ${numericGaps}`);

    console.log(`Multiple-draw dates:       ${duplicateDates.length}`);

    console.log(`Cycles discovered:         ${cycles.length}`);

    console.log("\n✅ Analysis complete.");
    console.log("ℹ️ No database records were modified.");
  } catch (error) {
    console.error("\n❌ ERROR");
    console.error(error);
    process.exitCode = 1;
  } finally {
    await mongoose.disconnect();
    console.log("\nMongoDB disconnected.");
  }
}

main();
