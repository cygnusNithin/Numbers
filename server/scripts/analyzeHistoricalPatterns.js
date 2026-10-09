const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");

const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

const OUTPUT_DIR = path.join(
  __dirname,
  "..",
  "analysis-results",
  "historical-patterns",
);

const NUMBER_MIN = 0;
const NUMBER_MAX = 9999;

const NUMBER_KEYS = Array.from({ length: 10000 }, (_, index) =>
  String(index).padStart(4, "0"),
);

const MONTH_KEYS = Array.from({ length: 12 }, (_, index) => String(index + 1));

const WEEKDAY_KEYS = Array.from({ length: 7 }, (_, index) => String(index));

function ensureOutputDir() {
  fs.mkdirSync(OUTPUT_DIR, {
    recursive: true,
  });
}

function writeJson(fileName, data) {
  const filePath = path.join(OUTPUT_DIR, fileName);

  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");

  return filePath;
}

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const stringValue = String(value);

  if (
    stringValue.includes(",") ||
    stringValue.includes('"') ||
    stringValue.includes("\n")
  ) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }

  return stringValue;
}

function writeCsv(fileName, rows, columns) {
  const filePath = path.join(OUTPUT_DIR, fileName);

  const lines = [];

  lines.push(columns.map(csvEscape).join(","));

  for (const row of rows) {
    lines.push(columns.map((column) => csvEscape(row[column])).join(","));
  }

  fs.writeFileSync(filePath, lines.join("\n"), "utf8");

  return filePath;
}

function normalizeNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }

  const normalized = String(value).trim().padStart(4, "0");

  if (!/^\d{4}$/.test(normalized)) {
    return null;
  }

  return normalized;
}

function parseDate(value) {
  if (!value) {
    return null;
  }

  if (value instanceof Date) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return null;
    }

    date.setHours(0, 0, 0, 0);

    return date;
  }

  const text = String(value).trim();

  let match = text.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})$/);

  if (match) {
    const day = Number(match[1]);
    const month = Number(match[2]);
    const year = Number(match[3]);

    const date = new Date(year, month - 1, day);

    date.setHours(0, 0, 0, 0);

    return date;
  }

  match = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);

  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);

    const date = new Date(year, month - 1, day);

    date.setHours(0, 0, 0, 0);

    return date;
  }

  const parsed = new Date(text);

  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  parsed.setHours(0, 0, 0, 0);

  return parsed;
}

function formatDate(date) {
  if (!date) {
    return "";
  }

  const day = String(date.getDate()).padStart(2, "0");

  const month = String(date.getMonth() + 1).padStart(2, "0");

  const year = date.getFullYear();

  return `${day}/${month}/${year}`;
}

function dateKey(date) {
  return formatDate(date);
}

function daysBetween(dateA, dateB) {
  const milliseconds = dateB.getTime() - dateA.getTime();

  return milliseconds / (1000 * 60 * 60 * 24);
}

function mean(values) {
  if (!values.length) {
    return 0;
  }

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values) {
  if (!values.length) {
    return 0;
  }

  const sorted = [...values].sort((a, b) => a - b);

  const middle = Math.floor(sorted.length / 2);

  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  return sorted[middle];
}

function standardDeviation(values) {
  if (values.length <= 1) {
    return 0;
  }

  const average = mean(values);

  const variance =
    values.reduce((sum, value) => sum + Math.pow(value - average, 2), 0) /
    values.length;

  return Math.sqrt(variance);
}

function increment(map, key, amount = 1) {
  map[key] = (map[key] || 0) + amount;
}

function getCategory(serialNumber) {
  const serial = String(serialNumber || "")
    .trim()
    .toUpperCase();

  if (serial.startsWith("BM-")) {
    return "BM";
  }

  if (serial.startsWith("BR-")) {
    return "BR";
  }

  return "OTHER";
}

function getNumberDigits(number) {
  return number.split("").map(Number);
}

function getDigitFeatures(number) {
  const digits = getNumberDigits(number);

  const evenDigitCount = digits.filter((digit) => digit % 2 === 0).length;

  const digitSum = digits.reduce((sum, digit) => sum + digit, 0);

  return {
    d1: digits[0],
    d2: digits[1],
    d3: digits[2],
    d4: digits[3],
    digitSum,
    evenDigitCount,
  };
}

function collectNumbersFromDocument(doc) {
  const numberMap = new Map();

  for (const series of doc.series || []) {
    const prize = Number(series.prize);

    for (const item of series.numbers || []) {
      const number = normalizeNumber(item.number);

      if (!number) {
        continue;
      }

      const count = Number(item.count);

      if (!Number.isFinite(count)) {
        continue;
      }

      if (!numberMap.has(number)) {
        numberMap.set(number, {
          number,
          occurrenceCount: 0,
          prizes: {},
        });
      }

      const entry = numberMap.get(number);

      entry.occurrenceCount += count;

      if (Number.isFinite(prize) && prize >= 1 && prize <= 5000) {
        increment(entry.prizes, String(prize), count);
      }
    }
  }

  return [...numberMap.values()];
}

async function main() {
  console.log("");
  console.log("============================================================");
  console.log("HISTORICAL PATTERN ANALYSIS");
  console.log("============================================================");
  console.log("");

  ensureOutputDir();

  console.log("Connecting to MongoDB...");

  await mongoose.connect(MONGO_URI);

  console.log("MongoDB connected.");
  console.log("");

  const documents = await AbsoluteData.find({}).lean();

  console.log(`AbsoluteData documents: ${documents.length}`);

  if (!documents.length) {
    throw new Error("AbsoluteData contains no documents.");
  }

  /*
   * ----------------------------------------------------------
   * STEP 1
   * Build one event for every unique serialNumber.
   * ----------------------------------------------------------
   */

  const serialMap = new Map();

  let duplicateSerialCount = 0;

  for (const doc of documents) {
    const serialNumber = String(doc.serialNumber || "").trim();

    if (!serialNumber) {
      continue;
    }

    if (serialMap.has(serialNumber)) {
      duplicateSerialCount++;

      console.warn(`Duplicate serialNumber found: ${serialNumber}`);

      continue;
    }

    const drawDate = parseDate(doc.drawDate || doc.date);

    if (!drawDate) {
      continue;
    }

    serialMap.set(serialNumber, {
      serialNumber,
      recordNumber: doc.recordNumber,
      drawDate,
      category: getCategory(serialNumber),
      numbers: collectNumbersFromDocument(doc),
    });
  }

  /*
   * ----------------------------------------------------------
   * STEP 2
   * Sort draw events chronologically.
   *
   * Same-date draws are NOT merged.
   *
   * recordNumber is used as deterministic tie-breaker.
   * ----------------------------------------------------------
   */

  const draws = [...serialMap.values()].sort((a, b) => {
    const dateDifference = a.drawDate.getTime() - b.drawDate.getTime();

    if (dateDifference !== 0) {
      return dateDifference;
    }

    return Number(a.recordNumber || 0) - Number(b.recordNumber || 0);
  });

  /*
   * Add explicit draw sequence.
   */

  draws.forEach((draw, index) => {
    draw.drawIndex = index + 1;
  });

  /*
   * ----------------------------------------------------------
   * STEP 3
   * Duplicate calendar date analysis.
   * ----------------------------------------------------------
   */

  const dateGroups = new Map();

  for (const draw of draws) {
    const key = dateKey(draw.drawDate);

    if (!dateGroups.has(key)) {
      dateGroups.set(key, []);
    }

    dateGroups.get(key).push(draw);
  }

  const duplicateDateRows = [];

  for (const [date, dateDraws] of dateGroups.entries()) {
    if (dateDraws.length <= 1) {
      continue;
    }

    for (const draw of dateDraws) {
      duplicateDateRows.push({
        date,
        drawIndex: draw.drawIndex,
        serialNumber: draw.serialNumber,
        category: draw.category,
        recordNumber: draw.recordNumber,
        numberCount: draw.numbers.length,
      });
    }
  }

  /*
   * ----------------------------------------------------------
   * STEP 4
   * Create number-level historical structures.
   * ----------------------------------------------------------
   */

  const numberStats = new Map();

  for (const number of NUMBER_KEYS) {
    const digitFeatures = getDigitFeatures(number);

    numberStats.set(number, {
      number,

      drawHits: 0,
      occurrenceCount: 0,

      firstDrawIndex: null,
      lastDrawIndex: null,

      firstSeenDate: null,
      lastSeenDate: null,

      appearanceDrawIndices: [],
      appearanceDates: [],

      gapsInDraws: [],
      gapsInDays: [],

      prizeBreakdown: {},

      weekdayCounts: {
        0: 0,
        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
      },

      monthCounts: {
        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
        7: 0,
        8: 0,
        9: 0,
        10: 0,
        11: 0,
        12: 0,
      },

      categoryCounts: {
        BM: 0,
        BR: 0,
        OTHER: 0,
      },

      ...digitFeatures,
    });
  }

  /*
   * ----------------------------------------------------------
   * STEP 5
   * Process every draw.
   *
   * IMPORTANT:
   * A number gets ONE draw hit per serialNumber,
   * regardless of item.count.
   *
   * occurrenceCount remains separate.
   * ----------------------------------------------------------
   */

  for (const draw of draws) {
    const date = draw.drawDate;

    const weekday = String(date.getDay());

    const month = String(date.getMonth() + 1);

    for (const item of draw.numbers) {
      const number = item.number;

      const stats = numberStats.get(number);

      if (!stats) {
        continue;
      }

      stats.drawHits++;

      stats.occurrenceCount += item.occurrenceCount;

      stats.appearanceDrawIndices.push(draw.drawIndex);

      stats.appearanceDates.push(dateKey(date));

      if (stats.firstDrawIndex === null) {
        stats.firstDrawIndex = draw.drawIndex;
      }

      stats.lastDrawIndex = draw.drawIndex;

      if (!stats.firstSeenDate) {
        stats.firstSeenDate = dateKey(date);
      }

      stats.lastSeenDate = dateKey(date);

      increment(stats.weekdayCounts, weekday);

      increment(stats.monthCounts, month);

      increment(stats.categoryCounts, draw.category);

      for (const [prize, count] of Object.entries(item.prizes)) {
        increment(stats.prizeBreakdown, prize, count);
      }
    }
  }

  /*
   * ----------------------------------------------------------
   * STEP 6
   * Calculate gaps.
   * ----------------------------------------------------------
   */

  for (const stats of numberStats.values()) {
    const drawIndices = stats.appearanceDrawIndices;

    const dates = stats.appearanceDates;

    for (let i = 1; i < drawIndices.length; i++) {
      stats.gapsInDraws.push(drawIndices[i] - drawIndices[i - 1]);

      const previousDate = parseDate(dates[i - 1]);

      const currentDate = parseDate(dates[i]);

      if (previousDate && currentDate) {
        stats.gapsInDays.push(daysBetween(previousDate, currentDate));
      }
    }
  }

  /*
   * ----------------------------------------------------------
   * STEP 7
   * Build global draw statistics.
   * ----------------------------------------------------------
   */

  const allDates = draws.map((draw) => draw.drawDate);

  const uniqueDates = [...new Set(allDates.map(dateKey))];

  const globalWeekdayCounts = {
    0: 0,
    1: 0,
    2: 0,
    3: 0,
    4: 0,
    5: 0,
    6: 0,
  };

  const globalMonthCounts = {
    1: 0,
    2: 0,
    3: 0,
    4: 0,
    5: 0,
    6: 0,
    7: 0,
    8: 0,
    9: 0,
    10: 0,
    11: 0,
    12: 0,
  };

  const categoryCounts = {
    BM: 0,
    BR: 0,
    OTHER: 0,
  };

  for (const draw of draws) {
    increment(globalWeekdayCounts, String(draw.drawDate.getDay()));

    increment(globalMonthCounts, String(draw.drawDate.getMonth() + 1));

    increment(categoryCounts, draw.category);
  }

  /*
   * ----------------------------------------------------------
   * STEP 8
   * Current analysis date.
   *
   * We use the latest actual draw date,
   * not today's computer date.
   * ----------------------------------------------------------
   */

  const latestDrawDate = draws.length ? draws[draws.length - 1].drawDate : null;

  const latestDrawIndex = draws.length;

  /*
   * ----------------------------------------------------------
   * STEP 9
   * Build final number analysis.
   * ----------------------------------------------------------
   */

  const frequencyRows = [];
  const gapRows = [];
  const monthRows = [];
  const weekdayRows = [];
  const digitRows = [];
  const recentRows = [];

  for (const stats of numberStats.values()) {
    const gapsDays = stats.gapsInDays;

    const gapsDraws = stats.gapsInDraws;

    const currentGapDraws =
      stats.lastDrawIndex === null
        ? latestDrawIndex
        : latestDrawIndex - stats.lastDrawIndex;

    let currentGapDays = null;

    if (stats.lastSeenDate && latestDrawDate) {
      const lastDate = parseDate(stats.lastSeenDate);

      currentGapDays = daysBetween(lastDate, latestDrawDate);
    }

    const recentWindows = {};

    for (const window of [10, 25, 50, 100, 250, 500]) {
      const startIndex = Math.max(1, latestDrawIndex - window + 1);

      const recentHits = stats.appearanceDrawIndices.filter(
        (index) => index >= startIndex,
      ).length;

      recentWindows[`last_${window}_draws`] = recentHits;
    }

    frequencyRows.push({
      number: stats.number,

      draw_hits: stats.drawHits,

      occurrence_count: stats.occurrenceCount,

      hit_rate_per_draw: latestDrawIndex
        ? (stats.drawHits / latestDrawIndex).toFixed(8)
        : "0",

      first_seen_date: stats.firstSeenDate || "",

      last_seen_date: stats.lastSeenDate || "",

      first_draw_index: stats.firstDrawIndex ?? "",

      last_draw_index: stats.lastDrawIndex ?? "",

      category_BM: stats.categoryCounts.BM,

      category_BR: stats.categoryCounts.BR,

      category_OTHER: stats.categoryCounts.OTHER,
    });

    gapRows.push({
      number: stats.number,

      draw_hits: stats.drawHits,

      current_gap_draws: currentGapDraws,

      current_gap_days: currentGapDays === null ? "" : currentGapDays,

      avg_gap_draws: mean(gapsDraws),

      median_gap_draws: median(gapsDraws),

      min_gap_draws: gapsDraws.length ? Math.min(...gapsDraws) : "",

      max_gap_draws: gapsDraws.length ? Math.max(...gapsDraws) : "",

      gap_stddev_draws: standardDeviation(gapsDraws),

      avg_gap_days: mean(gapsDays),

      median_gap_days: median(gapsDays),

      min_gap_days: gapsDays.length ? Math.min(...gapsDays) : "",

      max_gap_days: gapsDays.length ? Math.max(...gapsDays) : "",

      gap_stddev_days: standardDeviation(gapsDays),
    });

    monthRows.push({
      number: stats.number,

      total_hits: stats.drawHits,

      january: stats.monthCounts["1"],

      february: stats.monthCounts["2"],

      march: stats.monthCounts["3"],

      april: stats.monthCounts["4"],

      may: stats.monthCounts["5"],

      june: stats.monthCounts["6"],

      july: stats.monthCounts["7"],

      august: stats.monthCounts["8"],

      september: stats.monthCounts["9"],

      october: stats.monthCounts["10"],

      november: stats.monthCounts["11"],

      december: stats.monthCounts["12"],
    });

    weekdayRows.push({
      number: stats.number,

      total_hits: stats.drawHits,

      sunday: stats.weekdayCounts["0"],

      monday: stats.weekdayCounts["1"],

      tuesday: stats.weekdayCounts["2"],

      wednesday: stats.weekdayCounts["3"],

      thursday: stats.weekdayCounts["4"],

      friday: stats.weekdayCounts["5"],

      saturday: stats.weekdayCounts["6"],
    });

    digitRows.push({
      number: stats.number,

      d1: stats.d1,

      d2: stats.d2,

      d3: stats.d3,

      d4: stats.d4,

      digit_sum: stats.digitSum,

      even_digit_count: stats.evenDigitCount,
    });

    recentRows.push({
      number: stats.number,

      total_hits: stats.drawHits,

      ...recentWindows,
    });
  }

  /*
   * ----------------------------------------------------------
   * STEP 10
   * Save raw number-level data.
   * ----------------------------------------------------------
   */

  const frequencyCsv = writeCsv("frequency_analysis.csv", frequencyRows, [
    "number",
    "draw_hits",
    "occurrence_count",
    "hit_rate_per_draw",
    "first_seen_date",
    "last_seen_date",
    "first_draw_index",
    "last_draw_index",
    "category_BM",
    "category_BR",
    "category_OTHER",
  ]);

  const gapCsv = writeCsv("gap_analysis.csv", gapRows, [
    "number",
    "draw_hits",
    "current_gap_draws",
    "current_gap_days",
    "avg_gap_draws",
    "median_gap_draws",
    "min_gap_draws",
    "max_gap_draws",
    "gap_stddev_draws",
    "avg_gap_days",
    "median_gap_days",
    "min_gap_days",
    "max_gap_days",
    "gap_stddev_days",
  ]);

  const monthCsv = writeCsv("month_analysis.csv", monthRows, [
    "number",
    "total_hits",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
  ]);

  const weekdayCsv = writeCsv("weekday_analysis.csv", weekdayRows, [
    "number",
    "total_hits",
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
  ]);

  const digitCsv = writeCsv("digit_analysis.csv", digitRows, [
    "number",
    "d1",
    "d2",
    "d3",
    "d4",
    "digit_sum",
    "even_digit_count",
  ]);

  const recentCsv = writeCsv("recent_activity_analysis.csv", recentRows, [
    "number",
    "total_hits",
    "last_10_draws",
    "last_25_draws",
    "last_50_draws",
    "last_100_draws",
    "last_250_draws",
    "last_500_draws",
  ]);

  /*
   * ----------------------------------------------------------
   * STEP 11
   * Save duplicate-date information.
   * ----------------------------------------------------------
   */

  const duplicateDateCsv = writeCsv(
    "duplicate_calendar_dates.csv",
    duplicateDateRows,
    [
      "date",
      "drawIndex",
      "serialNumber",
      "category",
      "recordNumber",
      "numberCount",
    ],
  );

  /*
   * ----------------------------------------------------------
   * STEP 12
   * Save full draw sequence.
   * ----------------------------------------------------------
   */

  const drawSequence = draws.map((draw) => ({
    drawIndex: draw.drawIndex,

    recordNumber: draw.recordNumber,

    serialNumber: draw.serialNumber,

    category: draw.category,

    drawDate: formatDate(draw.drawDate),

    numbers: draw.numbers.map((item) => ({
      number: item.number,

      occurrenceCount: item.occurrenceCount,

      prizes: item.prizes,
    })),
  }));

  const drawSequenceJson = writeJson("draw_sequence.json", drawSequence);

  /*
   * ----------------------------------------------------------
   * STEP 13
   * Save detailed number analysis.
   * ----------------------------------------------------------
   */

  const detailedNumberAnalysis = [...numberStats.values()].map((stats) => ({
    number: stats.number,

    drawHits: stats.drawHits,

    occurrenceCount: stats.occurrenceCount,

    firstSeenDate: stats.firstSeenDate,

    lastSeenDate: stats.lastSeenDate,

    firstDrawIndex: stats.firstDrawIndex,

    lastDrawIndex: stats.lastDrawIndex,

    appearanceDrawIndices: stats.appearanceDrawIndices,

    appearanceDates: stats.appearanceDates,

    gapsInDraws: stats.gapsInDraws,

    gapsInDays: stats.gapsInDays,

    prizeBreakdown: stats.prizeBreakdown,

    weekdayCounts: stats.weekdayCounts,

    monthCounts: stats.monthCounts,

    categoryCounts: stats.categoryCounts,

    d1: stats.d1,

    d2: stats.d2,

    d3: stats.d3,

    d4: stats.d4,

    digitSum: stats.digitSum,

    evenDigitCount: stats.evenDigitCount,
  }));

  const detailedJson = writeJson(
    "number_historical_details.json",
    detailedNumberAnalysis,
  );

  /*
   * ----------------------------------------------------------
   * STEP 14
   * Global summary.
   * ----------------------------------------------------------
   */

  const summary = {
    generatedAt: new Date().toISOString(),

    source: "AbsoluteData / absolute_data",

    database: "numbergrid",

    documentsLoaded: documents.length,

    uniqueSerialNumbers: draws.length,

    duplicateSerialNumbers: duplicateSerialCount,

    uniqueCalendarDates: uniqueDates.length,

    duplicateCalendarDateCount: duplicateDateRows.length,

    dateGroupsWithMultipleDraws: [...dateGroups.values()].filter(
      (group) => group.length > 1,
    ).length,

    firstDraw: draws.length
      ? {
          drawIndex: draws[0].drawIndex,
          serialNumber: draws[0].serialNumber,
          category: draws[0].category,
          date: formatDate(draws[0].drawDate),
        }
      : null,

    lastDraw: draws.length
      ? {
          drawIndex: draws[draws.length - 1].drawIndex,
          serialNumber: draws[draws.length - 1].serialNumber,
          category: draws[draws.length - 1].category,
          date: formatDate(draws[draws.length - 1].drawDate),
        }
      : null,

    globalWeekdayCounts,

    globalMonthCounts,

    categoryCounts,

    numberUniverse: {
      expected: 10000,
      actual: numberStats.size,
      missing: NUMBER_KEYS.filter((number) => !numberStats.has(number)),
    },

    outputFiles: {
      frequencyCsv,
      gapCsv,
      monthCsv,
      weekdayCsv,
      digitCsv,
      recentCsv,
      duplicateDateCsv,
      drawSequenceJson,
      detailedJson,
    },
  };

  const summaryPath = writeJson("historical_analysis_summary.json", summary);

  /*
   * ----------------------------------------------------------
   * Console report
   * ----------------------------------------------------------
   */

  console.log("");
  console.log("============================================================");
  console.log("HISTORICAL DATA SUMMARY");
  console.log("============================================================");

  console.log(`MongoDB documents       : ${documents.length}`);

  console.log(`Unique serialNumber     : ${draws.length}`);

  console.log(`Unique calendar dates   : ${uniqueDates.length}`);

  console.log(`Duplicate-date rows     : ${duplicateDateRows.length}`);

  console.log(
    `Date groups with >1 draw: ${
      [...dateGroups.values()].filter((group) => group.length > 1).length
    }`,
  );

  console.log(`Number universe         : ${numberStats.size}`);

  console.log("");
  console.log("CATEGORY DISTRIBUTION");

  console.log(`BM    : ${categoryCounts.BM}`);

  console.log(`BR    : ${categoryCounts.BR}`);

  console.log(`OTHER : ${categoryCounts.OTHER}`);

  console.log("");
  console.log("DATE RANGE");

  if (draws.length) {
    console.log(
      `${formatDate(draws[0].drawDate)} → ${formatDate(
        draws[draws.length - 1].drawDate,
      )}`,
    );
  }

  console.log("");
  console.log("OUTPUT");

  console.log(`  ${summaryPath}`);

  console.log(`  ${frequencyCsv}`);

  console.log(`  ${gapCsv}`);

  console.log(`  ${monthCsv}`);

  console.log(`  ${weekdayCsv}`);

  console.log(`  ${digitCsv}`);

  console.log(`  ${recentCsv}`);

  console.log(`  ${duplicateDateCsv}`);

  console.log(`  ${drawSequenceJson}`);

  console.log(`  ${detailedJson}`);

  console.log("");
  console.log("============================================================");
  console.log("ANALYSIS DATASET CREATED");
  console.log("============================================================");
}

main()
  .catch((error) => {
    console.error("");
    console.error("HISTORICAL ANALYSIS FAILED");
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await mongoose.disconnect();
  });
