const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

function parseDate(value) {
  if (!value) return null;

  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function inspectNumbers(doc) {
  const series = doc.series;

  if (!Array.isArray(series)) {
    return {
      hasSeriesArray: false,
      seriesCount: 0,
      validNumbers: 0,
      sample: [],
    };
  }

  let validNumbers = 0;
  const sample = [];

  for (const prize of series) {
    if (!Array.isArray(prize.numbers)) continue;

    for (const item of prize.numbers) {
      const number = String(item.number ?? "").trim();

      if (/^\d{4}$/.test(number)) validNumbers++;

      if (sample.length < 5) {
        sample.push({
          number: item.number,
          count: item.count,
        });
      }
    }
  }

  return {
    hasSeriesArray: true,
    seriesCount: series.length,
    validNumbers,
    sample,
  };
}

async function main() {
  await mongoose.connect(MONGO_URI);

  const docs = await AbsoluteData.find({})
    .select("serialNumber recordNumber date drawDate series")
    .lean();

  const stats = {
    totalDocuments: docs.length,
    missingSerialNumber: 0,
    missingBothDates: 0,
    invalidDates: 0,
    missingSeriesArray: 0,
    emptySeries: 0,
    noValidFourDigitNumbers: 0,
    validDateAndNumbers: 0,
    excludedForDate: 0,
    excludedForNumbers: 0,
  };

  const samples = {
    missingDate: [],
    invalidDate: [],
    missingSeries: [],
    noValidNumbers: [],
  };

  for (const doc of docs) {
    const serial = String(doc.serialNumber || "").trim();

    if (!serial) stats.missingSerialNumber++;

    const drawDate = parseDate(doc.drawDate);
    const ordinaryDate = parseDate(doc.date);
    const date = drawDate || ordinaryDate;

    const numberInfo = inspectNumbers(doc);

    if (!doc.drawDate && !doc.date) {
      stats.missingBothDates++;
    }

    if (!date && (doc.drawDate || doc.date)) {
      stats.invalidDates++;

      if (samples.invalidDate.length < 10) {
        samples.invalidDate.push({
          serialNumber: serial,
          date: doc.date,
          drawDate: doc.drawDate,
        });
      }
    }

    if (!date) {
      stats.excludedForDate++;

      if (samples.missingDate.length < 10) {
        samples.missingDate.push({
          serialNumber: serial,
          date: doc.date,
          drawDate: doc.drawDate,
        });
      }
    }

    if (!numberInfo.hasSeriesArray) {
      stats.missingSeriesArray++;

      if (samples.missingSeries.length < 10) {
        samples.missingSeries.push({
          serialNumber: serial,
          seriesType: typeof doc.series,
          series: doc.series,
        });
      }
    } else if (numberInfo.seriesCount === 0) {
      stats.emptySeries++;
    }

    if (numberInfo.validNumbers === 0) {
      stats.noValidFourDigitNumbers++;

      if (samples.noValidNumbers.length < 10) {
        samples.noValidNumbers.push({
          serialNumber: serial,
          date: doc.date,
          drawDate: doc.drawDate,
          seriesCount: numberInfo.seriesCount,
          sample: numberInfo.sample,
        });
      }
    }

    if (numberInfo.validNumbers === 0) {
      stats.excludedForNumbers++;
    }

    if (date && numberInfo.validNumbers > 0) {
      stats.validDateAndNumbers++;
    }
  }

  console.log("\n========== GAP HAZARD DATA DIAGNOSTIC ==========");
  console.table(stats);

  console.log("\n========== SAMPLE DOCUMENTS WITH DATE ISSUES ==========");
  console.dir(samples.missingDate, { depth: 5 });

  console.log("\n========== SAMPLE INVALID DATES ==========");
  console.dir(samples.invalidDate, { depth: 5 });

  console.log("\n========== SAMPLE SERIES ISSUES ==========");
  console.dir(samples.missingSeries, { depth: 5 });

  console.log(
    "\n========== SAMPLE WITHOUT VALID FOUR-DIGIT NUMBERS ==========",
  );
  console.dir(samples.noValidNumbers, { depth: 5 });

  await mongoose.disconnect();
}

main().catch(async (error) => {
  console.error(error);

  await mongoose.disconnect().catch(() => {});
  process.exitCode = 1;
});
