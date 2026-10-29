const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const AbsoluteData = require("../models/AbsoluteData");
const AbsoluteDataV2 = require("../models/AbsoluteDataV2");

const OUTPUT_DIR = path.join(__dirname, "..", "reports");

function sortedUnique(values) {
  return [...new Set(values.map(String))].sort();
}

function csvEscape(value) {
  let text;

  if (value === null || value === undefined) {
    text = "";
  } else if (typeof value === "object") {
    text = JSON.stringify(value);
  } else {
    text = String(value);
  }

  return `"${text.replace(/"/g, '""')}"`;
}

function toCsv(rows, columns) {
  return [
    columns.map(csvEscape).join(","),
    ...rows.map((row) =>
      columns.map((column) => csvEscape(row[column])).join(","),
    ),
  ].join("\n");
}

// Aggregate original numbers by prize amount.
// V2 stores prizeCategory separately, so compare number sets
// by amount to evaluate compatibility with the original model.
function numbersByPrize(record) {
  const result = new Map();

  for (const group of record?.series || []) {
    const prize = Number(group.prize);

    if (!result.has(prize)) {
      result.set(prize, []);
    }

    const numbers = (group.numbers || []).map((item) =>
      typeof item === "string" ? item : item.number,
    );

    result.get(prize).push(...numbers.filter(Boolean).map(String));
  }

  for (const [prize, numbers] of result) {
    result.set(prize, sortedUnique(numbers));
  }

  return result;
}

function comparePrizeNumbers(original, v2) {
  const originalMap = numbersByPrize(original);
  const v2Map = numbersByPrize(v2);

  const allPrizes = [...new Set([
    ...originalMap.keys(),
    ...v2Map.keys(),
  ])].sort((a, b) => b - a);

  const differences = [];

  for (const prize of allPrizes) {
    const originalNumbers = originalMap.get(prize) || [];
    const v2Numbers = v2Map.get(prize) || [];

    const originalSet = new Set(originalNumbers);
    const v2Set = new Set(v2Numbers);

    const missingInV2 = originalNumbers.filter(
      (number) => !v2Set.has(number),
    );

    const extraInV2 = v2Numbers.filter(
      (number) => !originalSet.has(number),
    );

    if (missingInV2.length || extraInV2.length) {
      differences.push({
        type: "prizeNumbers",
        prize,
        originalCount: originalNumbers.length,
        v2Count: v2Numbers.length,
        missingInV2,
        extraInV2,
      });
    }
  }

  return differences;
}

async function main() {
  await mongoose.connect("mongodb://localhost:27017/numbergrid");

  console.log("Connected to MongoDB: numbergrid");
  console.log("Reading original and V2 collections...");

  const [originalRecords, v2Records] = await Promise.all([
    AbsoluteData.find({}).lean(),
    AbsoluteDataV2.find({}).lean(),
  ]);

  const originalBySerial = new Map();
  const v2BySerial = new Map();
  const duplicateOriginalSerials = [];
  const duplicateV2Serials = [];

  for (const record of originalRecords) {
    const serial = String(record.serialNumber || "").trim();

    if (originalBySerial.has(serial)) {
      duplicateOriginalSerials.push(serial);
    } else {
      originalBySerial.set(serial, record);
    }
  }

  for (const record of v2Records) {
    const serial = String(record.serialNumber || "").trim();

    if (v2BySerial.has(serial)) {
      duplicateV2Serials.push(serial);
    } else {
      v2BySerial.set(serial, record);
    }
  }

  const serials = [...new Set([
    ...originalBySerial.keys(),
    ...v2BySerial.keys(),
  ])].sort();

  const mismatches = [];
  const missingInV2 = [];
  const missingInOriginal = [];
  let serialsMatchedExactly = 0;

  for (const serialNumber of serials) {
    const original = originalBySerial.get(serialNumber);
    const v2 = v2BySerial.get(serialNumber);

    if (!original) {
      missingInOriginal.push({
        serialNumber,
        v2Date: v2?.date || "",
      });
      continue;
    }

    if (!v2) {
      missingInV2.push({
        serialNumber,
        originalDate: original.date || "",
      });
      continue;
    }

    const differences = [];

    if (String(original.date || "") !== String(v2.date || "")) {
      differences.push({
        type: "date",
        originalDate: original.date || "",
        v2Date: v2.date || "",
      });
    }

    differences.push(...comparePrizeNumbers(original, v2));

    // Report prize-category information separately.
    // This is new metadata in V2, not a direct field in the old model.
    const categories = (v2.series || []).map((group) => ({
      prizeCategory: group.prizeCategory,
      prize: group.prize,
      numberCount: (group.numbers || []).length,
    }));

    if (differences.length === 0) {
      serialsMatchedExactly++;
    } else {
      mismatches.push({
        serialNumber,
        originalDate: original.date || "",
        v2Date: v2.date || "",
        differences,
        v2PrizeCategories: categories,
      });
    }
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    database: "numbergrid",
    originalCollection: "absolute_data",
    v2Collection: "absolute_data_v2",
    originalRecordCount: originalRecords.length,
    v2RecordCount: v2Records.length,
    serialsMatchedExactly,
    mismatchedRecords: mismatches.length,
    missingInV2: missingInV2.length,
    missingInOriginal: missingInOriginal.length,
    duplicateOriginalSerials: sortedUnique(duplicateOriginalSerials),
    duplicateV2Serials: sortedUnique(duplicateV2Serials),
    mismatches,
    missingInV2Records: missingInV2,
    missingInOriginalRecords: missingInOriginal,
  };

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const jsonPath = path.join(
    OUTPUT_DIR,
    "absolute-data-full-audit.json",
  );

  const csvPath = path.join(
    OUTPUT_DIR,
    "absolute-data-mismatches.csv",
  );

  const summaryPath = path.join(
    OUTPUT_DIR,
    "absolute-data-audit-summary.json",
  );

  fs.writeFileSync(
    jsonPath,
    JSON.stringify(summary, null, 2),
    "utf8",
  );

  fs.writeFileSync(
    csvPath,
    toCsv(
      mismatches.map((item) => ({
        serialNumber: item.serialNumber,
        originalDate: item.originalDate,
        v2Date: item.v2Date,
        differences: item.differences,
        v2PrizeCategories: item.v2PrizeCategories,
      })),
      [
        "serialNumber",
        "originalDate",
        "v2Date",
        "differences",
        "v2PrizeCategories",
      ],
    ),
    "utf8",
  );

  const summaryOnly = { ...summary };
  delete summaryOnly.mismatches;
  delete summaryOnly.missingInV2Records;
  delete summaryOnly.missingInOriginalRecords;

  fs.writeFileSync(
    summaryPath,
    JSON.stringify(summaryOnly, null, 2),
    "utf8",
  );

  console.log("\n========== AUDIT SUMMARY ==========");
  console.log(JSON.stringify(summaryOnly, null, 2));
  console.log("\nCreated reports:");
  console.log(jsonPath);
  console.log(csvPath);
  console.log(summaryPath);
}

main()
  .catch((error) => {
    console.error("Audit failed:", error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await mongoose.disconnect();
  });
