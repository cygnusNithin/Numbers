const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI =
  process.env.MONGODB_URI ||
  process.env.MONGO_URI ||
  "mongodb://localhost:27017/numbergrid";

const OUTPUT_DIR = path.join(__dirname, "..", "data", "ai-training");

const DRAW_FIELDS = [
  "event_order",
  "serialNumber",
  "date",
  "drawDate",
  "fileName",
  "series_count",
  "number_rows",
  "distinct_numbers",
];

const NUMBER_FIELDS = [
  "event_order",
  "serialNumber",
  "date",
  "drawDate",
  "prize",
  "number",
  "count",
];

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const text = String(value);

  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}

function toCsv(headers, rows) {
  return (
    [
      headers.join(","),
      ...rows.map((row) =>
        headers.map((header) => csvEscape(row[header])).join(","),
      ),
    ].join("\n") + "\n"
  );
}

function parseDate(value) {
  if (!value) return null;

  // Avoid locale-dependent parsing of DD/MM/YYYY.
  const match = String(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

  if (!match) return null;

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);

  const timestamp = Date.UTC(year, month - 1, day);
  const check = new Date(timestamp);

  if (
    check.getUTCFullYear() !== year ||
    check.getUTCMonth() !== month - 1 ||
    check.getUTCDate() !== day
  ) {
    return null;
  }

  return timestamp;
}

function compareSerials(a, b) {
  const left = String(a.serialNumber ?? "");
  const right = String(b.serialNumber ?? "");

  // Numeric ordering where both serials are integers.
  if (/^\d+$/.test(left) && /^\d+$/.test(right)) {
    const difference = BigInt(left) - BigInt(right);
    if (difference < 0n) return -1;
    if (difference > 0n) return 1;
    return 0;
  }

  return left.localeCompare(right);
}

function compareDraws(a, b) {
  const aDate = parseDate(a.date);
  const bDate = parseDate(b.date);

  if (aDate !== null && bDate !== null && aDate !== bDate) {
    return aDate - bDate;
  }

  if (aDate !== null && bDate === null) return -1;
  if (aDate === null && bDate !== null) return 1;

  const serialComparison = compareSerials(a, b);
  if (serialComparison !== 0) return serialComparison;

  return String(a._id).localeCompare(String(b._id));
}

async function main() {
  await fs.promises.mkdir(OUTPUT_DIR, { recursive: true });

  await mongoose.connect(MONGO_URI);

  console.log("Connected to MongoDB:", mongoose.connection.name);
  console.log("Collection:", AbsoluteData.collection.name);

  // Read-only query. Do not merge other collections into this dataset.
  const documents = await AbsoluteData.find({})
    .select("serialNumber date drawDate fileName series")
    .lean()
    .exec();

  documents.sort(compareDraws);

  const seenSerials = new Set();
  const drawRows = [];
  const numberRows = [];

  let invalidDates = 0;
  let invalidNumbers = 0;
  let invalidPrizes = 0;
  let duplicateSerials = 0;
  let emptyDraws = 0;

  for (let i = 0; i < documents.length; i++) {
    const doc = documents[i];
    const serialNumber = String(doc.serialNumber ?? "").trim();
    const date = String(doc.date ?? "").trim();

    if (seenSerials.has(serialNumber)) {
      duplicateSerials++;
    }
    seenSerials.add(serialNumber);

    const parsedDate = parseDate(date);
    if (parsedDate === null) {
      invalidDates++;
    }

    const series = Array.isArray(doc.series) ? doc.series : [];
    const numbersBefore = numberRows.length;
    const seenNumberKeys = new Set();

    for (const entry of series) {
      const prize = Number(entry.prize);

      if (!Number.isFinite(prize) || prize < 1 || prize > 5000) {
        invalidPrizes++;
        continue;
      }

      const winningNumbers = Array.isArray(entry.numbers) ? entry.numbers : [];

      for (const winning of winningNumbers) {
        const number = String(winning.number ?? "").trim();
        const count = Number(winning.count ?? 1);

        if (!/^\d{4}$/.test(number) || !Number.isFinite(count) || count < 1) {
          invalidNumbers++;
          continue;
        }

        numberRows.push({
          event_order: i + 1,
          serialNumber,
          date,
          drawDate: doc.drawDate ? new Date(doc.drawDate).toISOString() : "",
          prize,
          number,
          count,
        });

        seenNumberKeys.add(number);
      }
    }

    const numberRowCount = numberRows.length - numbersBefore;

    if (numberRowCount === 0) {
      emptyDraws++;
    }

    drawRows.push({
      event_order: i + 1,
      serialNumber,
      date,
      drawDate: doc.drawDate ? new Date(doc.drawDate).toISOString() : "",
      fileName: doc.fileName ?? "",
      series_count: series.length,
      number_rows: numberRowCount,
      distinct_numbers: seenNumberKeys.size,
    });
  }

  // Fail rather than silently export ambiguous event identities.
  if (duplicateSerials > 0) {
    throw new Error(
      `Found ${duplicateSerials} duplicate serialNumber values. ` +
        "Investigate before training.",
    );
  }

  const drawsPath = path.join(OUTPUT_DIR, "ai_training_draws.csv");

  const numbersPath = path.join(OUTPUT_DIR, "ai_training_draw_numbers.csv");

  await fs.promises.writeFile(drawsPath, toCsv(DRAW_FIELDS, drawRows), "utf8");

  await fs.promises.writeFile(
    numbersPath,
    toCsv(NUMBER_FIELDS, numberRows),
    "utf8",
  );

  console.log("\nExport complete");
  console.log("------------------------------");
  console.log("Draw events:", documents.length);
  console.log("Draw-number-prize rows:", numberRows.length);
  console.log("Invalid dates:", invalidDates);
  console.log("Invalid numbers/counts:", invalidNumbers);
  console.log("Invalid prizes:", invalidPrizes);
  console.log("Duplicate serials:", duplicateSerials);
  console.log("Draws with no valid number rows:", emptyDraws);
  console.log("\nFiles:");
  console.log(drawsPath);
  console.log(numbersPath);
}

main()
  .catch((error) => {
    console.error("\nExport failed:", error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await mongoose.disconnect().catch(() => {});
  });
