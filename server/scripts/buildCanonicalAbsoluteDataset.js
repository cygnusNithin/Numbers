const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

const OUTPUT_DIR = path.join(__dirname, "..", "analysis-results");

const OUTPUT_CSV = path.join(OUTPUT_DIR, "absolute_data_canonical.csv");

const OUTPUT_JSON = path.join(OUTPUT_DIR, "absolute_data_canonical.json");

const START_NUMBER = 0;
const END_NUMBER = 9999;

/* ============================================================
   DATE HELPERS
============================================================ */

function parseDDMMYYYY(value) {
  if (!value) {
    return null;
  }

  const match = String(value)
    .trim()
    .match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

  if (!match) {
    return null;
  }

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);

  const date = new Date(Date.UTC(year, month - 1, day));

  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }

  return date;
}

function formatDDMMYYYY(date) {
  if (!date) {
    return "";
  }

  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const year = date.getUTCFullYear();

  return `${day}/${month}/${year}`;
}

function daysBetween(a, b) {
  const MS_PER_DAY = 24 * 60 * 60 * 1000;

  return Math.round((b - a) / MS_PER_DAY);
}

function getWeekday(date) {
  return date.getUTCDay();
}

/* ============================================================
   STATISTICS
============================================================ */

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

  const avg = mean(values);

  const variance =
    values.reduce((sum, value) => {
      return sum + Math.pow(value - avg, 2);
    }, 0) / values.length;

  return Math.sqrt(variance);
}

/* ============================================================
   NUMBER FEATURES
============================================================ */

function buildDigitFeatures(number) {
  const padded = String(number).padStart(4, "0");

  const digits = padded.split("").map(Number);

  return {
    d1: digits[0],
    d2: digits[1],
    d3: digits[2],
    d4: digits[3],

    digit_sum: digits.reduce((sum, digit) => sum + digit, 0),

    even_digit_count: digits.filter((digit) => digit % 2 === 0).length,
  };
}

/* ============================================================
   MONTH COUNTS
   IMPORTANT:
   Month counts are derived from the final UNIQUE draw dates.
   This prevents duplicate prize/number entries on the same
   draw date from inflating the month count.
============================================================ */

function buildMonthCountsFromDates(dates) {
  const monthCounts = {};

  for (const dateString of dates) {
    const date = parseDDMMYYYY(dateString);

    if (!date) {
      continue;
    }

    const month = String(date.getUTCMonth() + 1);

    monthCounts[month] = (monthCounts[month] || 0) + 1;
  }

  return monthCounts;
}

/* ============================================================
   CSV
============================================================ */

function escapeCsv(value) {
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

function objectToCsvValue(value) {
  return JSON.stringify(value);
}

/* ============================================================
   MAIN
============================================================ */

async function main() {
  console.log("");
  console.log("==============================================");
  console.log("BUILD CANONICAL ABSOLUTE DATASET");
  console.log("==============================================");
  console.log("");

  await mongoose.connect(MONGO_URI);

  console.log("MongoDB connected.");
  console.log("");

  const records = await AbsoluteData.find({})
    .sort({
      drawDate: 1,
      recordNumber: 1,
    })
    .lean();

  console.log(`AbsoluteData records: ${records.length}`);

  if (records.length === 0) {
    throw new Error("AbsoluteData contains zero records. Aborting.");
  }

  /*
   * Create all 10,000 numbers first.
   *
   * This guarantees that numbers which have never appeared
   * are still represented in the canonical dataset.
   */

  const stats = new Map();

  for (let i = START_NUMBER; i <= END_NUMBER; i++) {
    const number = String(i).padStart(4, "0");

    stats.set(number, {
      number,

      total_hits: 0,

      /*
       * Unique draw dates on which this number appeared.
       */
      dates: new Set(),

      first_seen_date: null,
      last_seen_date: null,

      prize_breakdown: {},

      weekday_counts: {
        Sunday: 0,
        Monday: 0,
        Tuesday: 0,
        Wednesday: 0,
        Thursday: 0,
        Friday: 0,
        Saturday: 0,
      },

      /*
       * IMPORTANT:
       *
       * Do NOT build month_counts here.
       *
       * It is derived later from the final unique dates.
       */

      features: buildDigitFeatures(number),
    });
  }

  /*
   * Process every AbsoluteData draw.
   */

  let processedRecords = 0;
  let processedSeries = 0;
  let processedNumbers = 0;

  const weekdayNames = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ];

  for (const record of records) {
    processedRecords++;

    const date = parseDDMMYYYY(record.date);

    if (!date) {
      console.warn(
        `⚠️ Invalid date: record ${record.recordNumber} | ${record.date}`,
      );

      continue;
    }

    const weekday = weekdayNames[getWeekday(date)];

    for (const series of record.series || []) {
      processedSeries++;

      const prize = Number(series.prize);

      /*
       * Only prizes from ₹1 to ₹5000 belong in the
       * canonical analysis dataset.
       */

      if (!Number.isFinite(prize) || prize < 1 || prize > 5000) {
        continue;
      }

      for (const winningNumber of series.numbers || []) {
        const number = String(winningNumber.number).padStart(4, "0");

        if (!/^\d{4}$/.test(number)) {
          console.warn(`⚠️ Invalid number: ${winningNumber.number}`);

          continue;
        }

        const item = stats.get(number);

        if (!item) {
          console.warn(`⚠️ Number outside 0000-9999: ${number}`);

          continue;
        }

        /*
         * The model contains a count field.
         *
         * Keep that count in total_hits.
         *
         * However, dates are stored as a Set so a draw
         * date is counted only once.
         */

        const count = Number(winningNumber.count) || 1;

        item.total_hits += count;

        item.dates.add(formatDDMMYYYY(date));

        if (!item.first_seen_date || date < item.first_seen_date) {
          item.first_seen_date = date;
        }

        if (!item.last_seen_date || date > item.last_seen_date) {
          item.last_seen_date = date;
        }

        /*
         * Prize distribution.
         */

        const prizeKey = String(prize);

        item.prize_breakdown[prizeKey] =
          (item.prize_breakdown[prizeKey] || 0) + count;

        /*
         * Weekday distribution.
         *
         * Keep the existing behaviour because this matches
         * the validated historical dataset.
         */

        item.weekday_counts[weekday] += count;

        processedNumbers++;
      }
    }
  }

  console.log("");
  console.log("Processing complete.");
  console.log(`Records processed: ${processedRecords}`);
  console.log(`Series processed:  ${processedSeries}`);
  console.log(`Number entries:    ${processedNumbers}`);
  console.log("");

  /*
   * Determine the latest draw date in the entire database.
   */

  let latestDrawDate = null;

  for (const record of records) {
    const date = parseDDMMYYYY(record.date);

    if (!date) {
      continue;
    }

    if (!latestDrawDate || date > latestDrawDate) {
      latestDrawDate = date;
    }
  }

  if (!latestDrawDate) {
    throw new Error("Could not determine latest draw date.");
  }

  console.log(`Latest draw date: ${formatDDMMYYYY(latestDrawDate)}`);

  /*
   * Convert raw statistics into final rows.
   */

  const rows = [];

  let numbersNeverSeen = 0;
  let numbersSeen = 0;

  for (let i = START_NUMBER; i <= END_NUMBER; i++) {
    const number = String(i).padStart(4, "0");

    const item = stats.get(number);

    /*
     * Convert the Set into sorted unique dates.
     */

    const sortedDates = [...item.dates]
      .map(parseDDMMYYYY)
      .filter(Boolean)
      .sort((a, b) => a - b);

    const dateStrings = sortedDates.map(formatDDMMYYYY);

    /*
     * IMPORTANT:
     *
     * month_counts MUST be derived from the final unique
     * dateStrings array.
     *
     * This fixes cases such as:
     *
     * 3551
     * 9000
     *
     * where the same number appeared more than once during
     * a month because of multiple prize/series entries.
     */

    const monthCounts = buildMonthCountsFromDates(dateStrings);

    /*
     * Calculate gaps between unique draw dates.
     */

    const gaps = [];

    for (let j = 1; j < sortedDates.length; j++) {
      gaps.push(daysBetween(sortedDates[j - 1], sortedDates[j]));
    }

    const firstSeen = item.first_seen_date;

    const lastSeen = item.last_seen_date;

    const daysSinceLastHit = lastSeen
      ? daysBetween(lastSeen, latestDrawDate)
      : null;

    const row = {
      number,

      total_hits: item.total_hits,

      draw_count: sortedDates.length,

      first_seen_date: firstSeen ? formatDDMMYYYY(firstSeen) : "",

      last_seen_date: lastSeen ? formatDDMMYYYY(lastSeen) : "",

      days_since_last_hit: daysSinceLastHit,

      avg_gap_days: gaps.length ? Number(mean(gaps).toFixed(4)) : null,

      median_gap_days: gaps.length ? Number(median(gaps).toFixed(4)) : null,

      min_gap_days: gaps.length ? Math.min(...gaps) : null,

      max_gap_days: gaps.length ? Math.max(...gaps) : null,

      gap_stddev_days:
        gaps.length > 1 ? Number(standardDeviation(gaps).toFixed(4)) : 0,

      dates: dateStrings,

      prize_breakdown: item.prize_breakdown,

      weekday_counts: item.weekday_counts,

      /*
       * Month counts derived from unique dates.
       */
      month_counts: monthCounts,

      d1: item.features.d1,
      d2: item.features.d2,
      d3: item.features.d3,
      d4: item.features.d4,

      digit_sum: item.features.digit_sum,

      even_digit_count: item.features.even_digit_count,
    };

    rows.push(row);

    if (item.total_hits === 0) {
      numbersNeverSeen++;
    } else {
      numbersSeen++;
    }
  }

  /*
   * Sort by numeric number.
   */

  rows.sort((a, b) => Number(a.number) - Number(b.number));

  fs.mkdirSync(OUTPUT_DIR, {
    recursive: true,
  });

  /*
   * JSON output.
   */

  fs.writeFileSync(
    OUTPUT_JSON,
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),

        source: {
          database: "numbergrid",
          collection: "absolute_data",
          records: records.length,
          latestDrawDate: formatDDMMYYYY(latestDrawDate),
        },

        summary: {
          totalNumbers: 10000,
          numbersSeen,
          numbersNeverSeen,
        },

        rows,
      },
      null,
      2,
    ),
    "utf8",
  );

  /*
   * CSV output.
   */

  const headers = [
    "number",
    "total_hits",
    "draw_count",
    "first_seen_date",
    "last_seen_date",
    "days_since_last_hit",
    "avg_gap_days",
    "median_gap_days",
    "min_gap_days",
    "max_gap_days",
    "gap_stddev_days",
    "dates",
    "prize_breakdown",
    "weekday_counts",
    "month_counts",
    "d1",
    "d2",
    "d3",
    "d4",
    "digit_sum",
    "even_digit_count",
  ];

  const csvLines = [];

  csvLines.push(headers.join(","));

  for (const row of rows) {
    csvLines.push(
      headers
        .map((header) => {
          if (
            header === "dates" ||
            header === "prize_breakdown" ||
            header === "weekday_counts" ||
            header === "month_counts"
          ) {
            return escapeCsv(objectToCsvValue(row[header]));
          }

          return escapeCsv(row[header]);
        })
        .join(","),
    );
  }

  fs.writeFileSync(OUTPUT_CSV, csvLines.join("\n"), "utf8");

  /*
   * Final report.
   */

  console.log("");
  console.log("==============================================");
  console.log("CANONICAL DATASET COMPLETE");
  console.log("==============================================");
  console.log("");

  console.log(`Numbers:             ${rows.length}`);

  console.log(`Numbers seen:        ${numbersSeen}`);

  console.log(`Numbers never seen:  ${numbersNeverSeen}`);

  console.log("");

  console.log(`CSV:  ${OUTPUT_CSV}`);

  console.log(`JSON: ${OUTPUT_JSON}`);

  console.log("");

  await mongoose.disconnect();
}

main()
  .then(() => {
    console.log("Done.");
  })
  .catch(async (error) => {
    console.error("");
    console.error("❌ BUILD FAILED");
    console.error(error);
    console.error("");

    try {
      await mongoose.disconnect();
    } catch (_) {}

    process.exit(1);
  });
