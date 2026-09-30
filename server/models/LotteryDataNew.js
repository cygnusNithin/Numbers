// server/scripts/analyzeAbsoluteCycleStart.js

const mongoose = require("mongoose");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

const COLLECTION = "absolute_data";

const MAX_ALLOWED_GAP_DAYS = 3;
const MIN_DRAWS = 50;

function parseDate(dateString) {
  if (!dateString) return null;

  const match = String(dateString).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

  if (!match) return null;

  const [, day, month, year] = match;

  return new Date(Number(year), Number(month) - 1, Number(day));
}

function formatDate(date) {
  if (!date) return "-";

  return [
    String(date.getDate()).padStart(2, "0"),
    String(date.getMonth() + 1).padStart(2, "0"),
    date.getFullYear(),
  ].join("/");
}

function daysBetween(a, b) {
  return Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}

function getNumbers(doc) {
  const numbers = new Set();

  if (!Array.isArray(doc.series)) {
    return numbers;
  }

  for (const series of doc.series) {
    if (!Array.isArray(series.numbers)) {
      continue;
    }

    for (const item of series.numbers) {
      if (!item) continue;

      let number = String(item.number ?? "").trim();

      if (!/^\d+$/.test(number)) {
        continue;
      }

      number = number.padStart(4, "0");

      if (number.length === 4) {
        numbers.add(number);
      }
    }
  }

  return numbers;
}

function median(values) {
  if (!values.length) return 0;

  const sorted = [...values].sort((a, b) => a - b);

  const middle = Math.floor(sorted.length / 2);

  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  return sorted[middle];
}

async function main() {
  try {
    console.log("");
    console.log("======================================");
    console.log(" AbsoluteData Cycle Analysis");
    console.log("======================================");
    console.log("");

    await mongoose.connect(MONGO_URI);

    console.log("MongoDB connected");
    console.log("Database:", mongoose.connection.name);
    console.log("Collection:", COLLECTION);
    console.log("");

    const collection = mongoose.connection.db.collection(COLLECTION);

    const documents = await collection.find({}).toArray();

    console.log("Documents found:", documents.length);

    if (!documents.length) {
      console.log("");
      console.log("absolute_data contains no documents.");
      return;
    }

    // --------------------------------------
    // DATE NORMALIZATION
    // --------------------------------------

    const docs = documents
      .map((doc) => {
        let date = null;

        if (doc.drawDate) {
          date = new Date(doc.drawDate);

          if (Number.isNaN(date.getTime())) {
            date = null;
          }
        }

        if (!date && doc.date) {
          date = parseDate(doc.date);
        }

        return {
          ...doc,
          _parsedDate: date,
        };
      })
      .filter((doc) => doc._parsedDate !== null);

    // --------------------------------------
    // SORT
    // --------------------------------------

    docs.sort((a, b) => {
      const difference = a._parsedDate.getTime() - b._parsedDate.getTime();

      if (difference !== 0) {
        return difference;
      }

      return Number(a.recordNumber || 0) - Number(b.recordNumber || 0);
    });

    console.log("Documents with valid dates:", docs.length);

    console.log("");

    // --------------------------------------
    // BASIC DATE INFORMATION
    // --------------------------------------

    console.log("--------------------------------------");
    console.log("DATE RANGE");
    console.log("--------------------------------------");

    console.log("First:", formatDate(docs[0]._parsedDate));

    console.log("Last:", formatDate(docs[docs.length - 1]._parsedDate));

    console.log("Documents:", docs.length);

    console.log("");

    // --------------------------------------
    // DRAW GAPS
    // --------------------------------------

    const gaps = [];

    for (let i = 1; i < docs.length; i++) {
      const gap = daysBetween(docs[i - 1]._parsedDate, docs[i]._parsedDate);

      gaps.push({
        gap,
        previous: docs[i - 1],
        current: docs[i],
      });
    }

    const gapValues = gaps.map((item) => item.gap);

    if (gapValues.length) {
      console.log("--------------------------------------");
      console.log("DRAW GAP ANALYSIS");
      console.log("--------------------------------------");

      console.log(
        "Average:",
        (
          gapValues.reduce((sum, value) => sum + value, 0) / gapValues.length
        ).toFixed(2),
        "days",
      );

      console.log("Median:", median(gapValues), "days");

      console.log("Maximum:", Math.max(...gapValues), "days");

      console.log("Gaps > 1 day:", gapValues.filter((x) => x > 1).length);

      console.log("Gaps > 2 days:", gapValues.filter((x) => x > 2).length);

      console.log("Gaps > 3 days:", gapValues.filter((x) => x > 3).length);

      console.log("");
    }

    // --------------------------------------
    // LARGEST GAPS
    // --------------------------------------

    console.log("--------------------------------------");
    console.log("LARGEST GAPS");
    console.log("--------------------------------------");

    const largestGaps = [...gaps].sort((a, b) => b.gap - a.gap).slice(0, 20);

    for (const item of largestGaps) {
      console.log(
        `${String(item.gap).padStart(3, " ")} days | ` +
          `${formatDate(item.previous._parsedDate)} -> ` +
          `${formatDate(item.current._parsedDate)}`,
      );
    }

    console.log("");

    // --------------------------------------
    // BUILD CONTINUOUS PERIODS
    // --------------------------------------

    console.log("--------------------------------------");
    console.log(`CONTINUOUS PERIODS (MAX GAP ${MAX_ALLOWED_GAP_DAYS} DAYS)`);
    console.log("--------------------------------------");

    const periods = [];

    let currentPeriod = [];

    for (const doc of docs) {
      if (!currentPeriod.length) {
        currentPeriod.push(doc);
        continue;
      }

      const previous = currentPeriod[currentPeriod.length - 1];

      const gap = daysBetween(previous._parsedDate, doc._parsedDate);

      if (gap <= MAX_ALLOWED_GAP_DAYS) {
        currentPeriod.push(doc);
      } else {
        if (currentPeriod.length >= MIN_DRAWS) {
          periods.push(currentPeriod);
        }

        currentPeriod = [doc];
      }
    }

    if (currentPeriod.length >= MIN_DRAWS) {
      periods.push(currentPeriod);
    }

    console.log("Periods found:", periods.length);

    console.log("");

    // --------------------------------------
    // ANALYZE EACH PERIOD
    // --------------------------------------

    periods.forEach((period, index) => {
      const uniqueNumbers = new Set();

      for (const doc of period) {
        const numbers = getNumbers(doc);

        for (const number of numbers) {
          uniqueNumbers.add(number);
        }
      }

      const periodGaps = [];

      for (let i = 1; i < period.length; i++) {
        periodGaps.push(
          daysBetween(period[i - 1]._parsedDate, period[i]._parsedDate),
        );
      }

      console.log(`PERIOD ${index + 1}`);

      console.log("Start:", formatDate(period[0]._parsedDate));

      console.log("End:", formatDate(period[period.length - 1]._parsedDate));

      console.log("Draws:", period.length);

      console.log("Unique numbers:", uniqueNumbers.size, "/ 10000");

      console.log("Missing numbers:", 10000 - uniqueNumbers.size);

      console.log(
        "Maximum gap:",
        periodGaps.length ? Math.max(...periodGaps) : 0,
        "days",
      );

      console.log("");
    });

    console.log("======================================");
    console.log("Analysis complete");
    console.log("======================================");
    console.log("");
  } catch (error) {
    console.error("");
    console.error("Analysis failed:");
    console.error(error);
    console.error("");
  } finally {
    await mongoose.disconnect();
  }
}

main();
