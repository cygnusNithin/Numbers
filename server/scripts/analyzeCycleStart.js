const mongoose = require("mongoose");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

const DB_NAME = "numbergrid";
const COLLECTION = "lottery_results_v2";

// A draw gap larger than this starts a new "continuous period".
const MAX_ALLOWED_GAP_DAYS = 3;

// Ignore very small periods.
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

  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();

  return `${day}/${month}/${year}`;
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
    if (!Array.isArray(series.numbers)) continue;

    for (const item of series.numbers) {
      if (!item) continue;

      let number = String(item.number ?? "").trim();

      if (/^\d+$/.test(number)) {
        number = number.padStart(4, "0");

        if (number.length === 4) {
          numbers.add(number);
        }
      }
    }
  }

  return numbers;
}

function calculateMedian(values) {
  if (!values.length) return 0;

  const sorted = [...values].sort((a, b) => a - b);

  const middle = Math.floor(sorted.length / 2);

  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  return sorted[middle];
}

function analyzePeriod(docs) {
  if (!docs.length) {
    return null;
  }

  const uniqueNumbers = new Set();

  for (const doc of docs) {
    for (const number of getNumbers(doc)) {
      uniqueNumbers.add(number);
    }
  }

  const gaps = [];

  for (let i = 1; i < docs.length; i++) {
    const previous = docs[i - 1]._parsedDate;
    const current = docs[i]._parsedDate;

    const gap = daysBetween(previous, current);

    if (gap >= 0) {
      gaps.push(gap);
    }
  }

  return {
    startDate: docs[0]._parsedDate,
    endDate: docs[docs.length - 1]._parsedDate,

    drawCount: docs.length,

    uniqueNumbers: uniqueNumbers.size,

    missingNumbers: 10000 - uniqueNumbers.size,

    averageGap:
      gaps.length > 0
        ? gaps.reduce((sum, value) => sum + value, 0) / gaps.length
        : 0,

    medianGap: calculateMedian(gaps),

    maxGap: gaps.length ? Math.max(...gaps) : 0,

    gapsGreaterThan1: gaps.filter((x) => x > 1).length,
    gapsGreaterThan2: gaps.filter((x) => x > 2).length,
    gapsGreaterThan3: gaps.filter((x) => x > 3).length,

    gaps,
  };
}

function buildContinuousPeriods(docs) {
  const periods = [];

  let currentPeriod = [];

  for (const doc of docs) {
    if (!doc._parsedDate) continue;

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

  return periods;
}

async function main() {
  try {
    console.log("");
    console.log("==============================================");
    console.log(" Cycle Start Analysis");
    console.log("==============================================");
    console.log("");

    console.log("MongoDB:", MONGO_URI);
    console.log("Database:", DB_NAME);
    console.log("Collection:", COLLECTION);
    console.log("");

    await mongoose.connect(MONGO_URI);

    console.log("MongoDB connected.");
    console.log("");

    const collection = mongoose.connection.db.collection(COLLECTION);

    const rawDocs = await collection
      .find({})
      .project({
        recordNumber: 1,
        serialNumber: 1,
        date: 1,
        drawDate: 1,
        series: 1,
      })
      .toArray();

    console.log(`Documents found: ${rawDocs.length}`);
    console.log("");

    if (!rawDocs.length) {
      console.log("No lottery data found.");
      return;
    }

    // Parse dates.
    const docs = rawDocs
      .map((doc) => {
        let parsedDate = null;

        if (doc.drawDate) {
          parsedDate = new Date(doc.drawDate);
        }

        if (!parsedDate || Number.isNaN(parsedDate.getTime())) {
          parsedDate = parseDate(doc.date);
        }

        return {
          ...doc,
          _parsedDate: parsedDate,
        };
      })
      .filter((doc) => doc._parsedDate);

    // Sort chronologically.
    docs.sort((a, b) => {
      const dateDifference = a._parsedDate.getTime() - b._parsedDate.getTime();

      if (dateDifference !== 0) {
        return dateDifference;
      }

      return Number(a.recordNumber || 0) - Number(b.recordNumber || 0);
    });

    console.log(`Documents with valid dates: ${docs.length}`);
    console.log("");

    if (!docs.length) {
      console.log("No documents with valid dates.");
      return;
    }

    // --------------------------------------------------
    // GLOBAL DATE ANALYSIS
    // --------------------------------------------------

    const allGaps = [];

    for (let i = 1; i < docs.length; i++) {
      const gap = daysBetween(docs[i - 1]._parsedDate, docs[i]._parsedDate);

      if (gap >= 0) {
        allGaps.push({
          gap,
          previous: docs[i - 1],
          current: docs[i],
        });
      }
    }

    console.log("----------------------------------------------");
    console.log(" Overall Dataset");
    console.log("----------------------------------------------");

    console.log("First draw:", formatDate(docs[0]._parsedDate));

    console.log("Last draw:", formatDate(docs[docs.length - 1]._parsedDate));

    console.log("Draws:", docs.length);

    if (allGaps.length) {
      const gapValues = allGaps.map((x) => x.gap);

      console.log(
        "Average draw gap:",
        (gapValues.reduce((a, b) => a + b, 0) / gapValues.length).toFixed(2),
        "days",
      );

      console.log("Median draw gap:", calculateMedian(gapValues), "days");

      console.log("Maximum draw gap:", Math.max(...gapValues), "days");

      console.log("Gaps > 1 day:", gapValues.filter((x) => x > 1).length);

      console.log("Gaps > 2 days:", gapValues.filter((x) => x > 2).length);

      console.log("Gaps > 3 days:", gapValues.filter((x) => x > 3).length);
    }

    console.log("");

    // --------------------------------------------------
    // LARGEST GAPS
    // --------------------------------------------------

    console.log("----------------------------------------------");
    console.log(" Largest Date Gaps");
    console.log("----------------------------------------------");

    const largestGaps = [...allGaps].sort((a, b) => b.gap - a.gap).slice(0, 20);

    for (const item of largestGaps) {
      console.log(
        `${String(item.gap).padStart(4)} days | ` +
          `${formatDate(item.previous._parsedDate)} -> ` +
          `${formatDate(item.current._parsedDate)}`,
      );
    }

    console.log("");

    // --------------------------------------------------
    // CONTINUOUS PERIODS
    // --------------------------------------------------

    const periods = buildContinuousPeriods(docs);

    console.log("----------------------------------------------");
    console.log(` Continuous Periods (max gap = ${MAX_ALLOWED_GAP_DAYS} days)`);
    console.log("----------------------------------------------");

    if (!periods.length) {
      console.log("No continuous periods found.");
      return;
    }

    const periodResults = periods
      .map((period, index) => {
        const analysis = analyzePeriod(period);

        return {
          cycleCandidate: index + 1,
          ...analysis,
        };
      })
      .sort((a, b) => b.drawCount - a.drawCount);

    periodResults.forEach((period) => {
      console.log("");

      console.log(
        `#${period.cycleCandidate}`,
        `${formatDate(period.startDate)} -> ${formatDate(period.endDate)}`,
      );

      console.log("  Draws:", period.drawCount);

      console.log("  Unique numbers:", period.uniqueNumbers, "/ 10000");

      console.log("  Missing numbers:", period.missingNumbers);

      console.log("  Average gap:", period.averageGap.toFixed(2), "days");

      console.log("  Median gap:", period.medianGap, "days");

      console.log("  Maximum gap:", period.maxGap, "days");

      console.log("  Gaps > 1:", period.gapsGreaterThan1);

      console.log("  Gaps > 2:", period.gapsGreaterThan2);

      console.log("  Gaps > 3:", period.gapsGreaterThan3);
    });

    console.log("");

    // --------------------------------------------------
    // POTENTIAL STARTING POINTS
    // --------------------------------------------------

    console.log("----------------------------------------------");
    console.log(" Potential Cycle Starting Points");
    console.log("----------------------------------------------");

    const candidates = periodResults
      .filter((period) => period.uniqueNumbers >= 5000)
      .slice(0, 10);

    if (!candidates.length) {
      console.log("No candidate periods reached 5,000 unique numbers.");
    } else {
      candidates.forEach((candidate, index) => {
        console.log("");

        console.log(`Candidate ${index + 1}`);

        console.log("  Start:", formatDate(candidate.startDate));

        console.log("  End:", formatDate(candidate.endDate));

        console.log("  Draws:", candidate.drawCount);

        console.log("  Unique numbers:", candidate.uniqueNumbers);

        console.log("  Missing numbers:", candidate.missingNumbers);

        console.log("  Max gap:", candidate.maxGap, "days");
      });
    }

    console.log("");

    console.log("==============================================");
    console.log(" Analysis complete");
    console.log("==============================================");
    console.log("");
  } catch (error) {
    console.error("");
    console.error("ERROR:");
    console.error(error);
    console.error("");
  } finally {
    await mongoose.disconnect();
  }
}

main();
