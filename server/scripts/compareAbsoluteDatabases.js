const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const AbsoluteData = require("../models/AbsoluteData");
const AbsoluteDataV2 = require("../models/AbsoluteDataV2");

// ------------------------------------------------------------
// CONFIGURATION
// ------------------------------------------------------------

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

const OUTPUT_PATH = path.resolve(
  __dirname,
  "../../absolute-database-comparison.json",
);

const VALID_DRAW_CATEGORIES = ["BM", "BR", "OTHER", "UNKNOWN"];

// ------------------------------------------------------------
// HELPERS
// ------------------------------------------------------------

function normalize(value) {
  return String(value ?? "").trim();
}

function normalizePrize(value) {
  return Number(value);
}

function getNumberEntries(group) {
  return (group?.numbers || [])
    .map((item) => {
      if (typeof item === "string") {
        return { number: normalize(item), count: 1 };
      }

      return {
        number: normalize(item?.number),
        count: Number(item?.count ?? 1),
      };
    })
    .filter((item) => item.number);
}

function groupByPrize(series = []) {
  const result = new Map();

  for (const group of series) {
    const prize = normalizePrize(group.prize);

    if (!Number.isFinite(prize)) continue;

    if (!result.has(prize)) {
      result.set(prize, {
        numbers: [],
        countByNumber: new Map(),
        prizeCategories: new Set(),
      });
    }

    const target = result.get(prize);

    for (const item of getNumberEntries(group)) {
      target.numbers.push(item.number);

      target.countByNumber.set(
        item.number,
        (target.countByNumber.get(item.number) || 0) + item.count,
      );
    }

    if (group.prizeCategory) {
      target.prizeCategories.add(normalize(group.prizeCategory));
    }
  }

  for (const group of result.values()) {
    group.numbers.sort();
  }

  return result;
}

function findDifferences(expected, actual) {
  const expectedCounts = new Map();
  const actualCounts = new Map();

  for (const number of expected) {
    expectedCounts.set(number, (expectedCounts.get(number) || 0) + 1);
  }

  for (const number of actual) {
    actualCounts.set(number, (actualCounts.get(number) || 0) + 1);
  }

  const missing = [];
  const extra = [];

  for (const [number, count] of expectedCounts) {
    const actualCount = actualCounts.get(number) || 0;

    for (let i = actualCount; i < count; i++) {
      missing.push(number);
    }
  }

  for (const [number, count] of actualCounts) {
    const expectedCount = expectedCounts.get(number) || 0;

    for (let i = expectedCount; i < count; i++) {
      extra.push(number);
    }
  }

  return { missing, extra };
}

function findCountDifferences(expected, actual) {
  const differences = [];

  const allNumbers = new Set([...expected.keys(), ...actual.keys()]);

  for (const number of [...allNumbers].sort()) {
    const expectedCount = expected.get(number) || 0;
    const actualCount = actual.get(number) || 0;

    if (expectedCount !== actualCount) {
      differences.push({
        number,
        originalCount: expectedCount,
        v2Count: actualCount,
      });
    }
  }

  return differences;
}

function findDuplicateNumbers(series = []) {
  const duplicates = [];

  for (const group of series) {
    const prize = normalizePrize(group.prize);
    const entries = getNumberEntries(group);
    const counts = new Map();

    for (const item of entries) {
      counts.set(item.number, (counts.get(item.number) || 0) + 1);
    }

    for (const [number, count] of counts) {
      if (count > 1) {
        duplicates.push({ prize, number, occurrences: count });
      }
    }
  }

  return duplicates;
}

function getCategorySummary(records) {
  const drawCategories = {};
  const prizeCategories = {};
  const invalidDrawCategories = [];
  const missingPrizeCategories = [];

  for (const record of records) {
    const drawCategory = normalize(record.drawCategory || "UNKNOWN");

    drawCategories[drawCategory] = (drawCategories[drawCategory] || 0) + 1;

    if (!VALID_DRAW_CATEGORIES.includes(drawCategory)) {
      invalidDrawCategories.push({
        serialNumber: record.serialNumber,
        drawCategory,
      });
    }

    for (const group of record.series || []) {
      const category = normalize(group.prizeCategory);

      if (!category) {
        missingPrizeCategories.push({
          serialNumber: record.serialNumber,
          prize: group.prize,
        });
      } else {
        prizeCategories[category] = (prizeCategories[category] || 0) + 1;
      }
    }
  }

  return {
    drawCategories,
    prizeCategories,
    invalidDrawCategories,
    missingPrizeCategories,
  };
}

// ------------------------------------------------------------
// COMPARE ONE RECORD
// ------------------------------------------------------------

function compareRecords(original, v2) {
  const differences = [];

  if (normalize(original.date) !== normalize(v2.date)) {
    differences.push({
      type: "DATE_MISMATCH",
      original: original.date,
      v2: v2.date,
    });
  }

  const originalGroups = groupByPrize(original.series);
  const v2Groups = groupByPrize(v2.series);

  const allPrizeAmounts = new Set([
    ...originalGroups.keys(),
    ...v2Groups.keys(),
  ]);

  const prizeComparisons = [];

  for (const prize of [...allPrizeAmounts].sort((a, b) => b - a)) {
    const expected = originalGroups.get(prize) || {
      numbers: [],
      countByNumber: new Map(),
    };

    const actual = v2Groups.get(prize) || {
      numbers: [],
      countByNumber: new Map(),
    };

    const numberDifferences = findDifferences(expected.numbers, actual.numbers);

    const countDifferences = findCountDifferences(
      expected.countByNumber,
      actual.countByNumber,
    );

    const exactMatch =
      numberDifferences.missing.length === 0 &&
      numberDifferences.extra.length === 0 &&
      countDifferences.length === 0;

    const result = {
      prize,
      originalCount: expected.numbers.length,
      v2Count: actual.numbers.length,
      exactMatch,
      missingNumbers: numberDifferences.missing,
      extraNumbers: numberDifferences.extra,
      countDifferences,
      v2PrizeCategories: [...(actual.prizeCategories || [])],
    };

    prizeComparisons.push(result);

    if (!exactMatch) {
      differences.push({
        type: "PRIZE_DATA_MISMATCH",
        ...result,
      });
    }
  }

  return {
    exactMatch: differences.length === 0,
    originalPrizeGroups: original.series.length,
    v2PrizeGroups: v2.series.length,
    prizeComparisons,
    differences,
  };
}

// ------------------------------------------------------------
// MAIN
// ------------------------------------------------------------

async function main() {
  console.log("========================================");
  console.log("ABSOLUTE DATABASE COMPARISON");
  console.log("========================================");

  console.log("Connecting to MongoDB...");

  await mongoose.connect(MONGO_URI);

  console.log("Connected.");

  // Read-only: no insert, update, delete, or replacement.
  const [originalRecords, v2Records] = await Promise.all([
    AbsoluteData.find({}).lean(),
    AbsoluteDataV2.find({}).lean(),
  ]);

  console.log("\nRecords loaded.");
  console.log("Original:", originalRecords.length);
  console.log("V2:", v2Records.length);

  const summary = {
    originalRecordCount: originalRecords.length,
    v2RecordCount: v2Records.length,

    originalUniqueSerialNumbers: 0,
    v2UniqueSerialNumbers: 0,

    recordsCompared: 0,
    exactMatches: 0,
    mismatches: 0,

    missingFromV2: 0,
    extraInV2: 0,

    duplicateSerialNumbersOriginal: [],
    duplicateSerialNumbersV2: [],

    duplicateNumbersOriginal: 0,
    duplicateNumbersV2: 0,

    prizeGroupsChecked: 0,
    prizeGroupsMatched: 0,
    prizeGroupsMismatched: 0,

    totalMissingNumbers: 0,
    totalExtraNumbers: 0,
    countDifferences: 0,

    comparisons: [],
    missingRecords: [],
    extraRecords: [],
    duplicateNumbers: [],
  };

  // ----------------------------------------------------------
  // INDEX RECORDS BY SERIAL NUMBER
  // ----------------------------------------------------------

  const originalMap = new Map();
  const v2Map = new Map();

  function buildMap(records, map, duplicateList, source) {
    for (const record of records) {
      const serial = normalize(record.serialNumber);

      if (!serial) continue;

      if (map.has(serial)) {
        duplicateList.push(serial);
      } else {
        map.set(serial, record);
      }

      const duplicates = findDuplicateNumbers(record.series);

      if (duplicates.length > 0) {
        summary.duplicateNumbers.push({
          source,
          serialNumber: serial,
          duplicates,
        });

        if (source === "absolute_data") {
          summary.duplicateNumbersOriginal += duplicates.length;
        } else {
          summary.duplicateNumbersV2 += duplicates.length;
        }
      }
    }
  }

  buildMap(
    originalRecords,
    originalMap,
    summary.duplicateSerialNumbersOriginal,
    "absolute_data",
  );

  buildMap(
    v2Records,
    v2Map,
    summary.duplicateSerialNumbersV2,
    "absolute_data_v2",
  );

  summary.originalUniqueSerialNumbers = originalMap.size;
  summary.v2UniqueSerialNumbers = v2Map.size;

  // ----------------------------------------------------------
  // CHECK RECORDS MISSING FROM V2
  // ----------------------------------------------------------

  for (const [serial, original] of originalMap) {
    const v2 = v2Map.get(serial);

    if (!v2) {
      summary.missingFromV2++;

      summary.missingRecords.push({
        serialNumber: serial,
        date: original.date,
        fileName: original.fileName,
      });

      continue;
    }

    summary.recordsCompared++;

    const comparison = compareRecords(original, v2);

    if (comparison.exactMatch) {
      summary.exactMatches++;
    } else {
      summary.mismatches++;
    }

    for (const prize of comparison.prizeComparisons) {
      summary.prizeGroupsChecked++;

      if (prize.exactMatch) {
        summary.prizeGroupsMatched++;
      } else {
        summary.prizeGroupsMismatched++;
      }

      summary.totalMissingNumbers += prize.missingNumbers.length;
      summary.totalExtraNumbers += prize.extraNumbers.length;
      summary.countDifferences += prize.countDifferences.length;
    }

    summary.comparisons.push({
      serialNumber: serial,
      date: original.date,
      status: comparison.exactMatch ? "EXACT_MATCH" : "MISMATCH",
      ...comparison,
    });

    console.log(`${comparison.exactMatch ? "MATCH" : "MISMATCH"}: ${serial}`);
  }

  // ----------------------------------------------------------
  // CHECK EXTRA RECORDS IN V2
  // ----------------------------------------------------------

  for (const [serial, v2] of v2Map) {
    if (!originalMap.has(serial)) {
      summary.extraInV2++;

      summary.extraRecords.push({
        serialNumber: serial,
        date: v2.date,
        fileName: v2.fileName,
      });
    }
  }

  // ----------------------------------------------------------
  // V2 CATEGORY VALIDATION
  // ----------------------------------------------------------

  const categorySummary = getCategorySummary(v2Records);

  // ----------------------------------------------------------
  // FINAL RESULT
  // ----------------------------------------------------------

  const passed =
    summary.originalRecordCount === summary.v2RecordCount &&
    summary.missingFromV2 === 0 &&
    summary.extraInV2 === 0 &&
    summary.mismatches === 0 &&
    summary.duplicateSerialNumbersOriginal.length === 0 &&
    summary.duplicateSerialNumbersV2.length === 0 &&
    summary.duplicateNumbersOriginal === 0 &&
    summary.duplicateNumbersV2 === 0 &&
    categorySummary.invalidDrawCategories.length === 0 &&
    categorySummary.missingPrizeCategories.length === 0;

  const output = {
    generatedAt: new Date().toISOString(),
    database: "numbergrid",
    originalCollection: "absolute_data",
    v2Collection: "absolute_data_v2",
    readOnly: true,
    passed,
    summary,
    categorySummary,
  };

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2), "utf8");

  // ----------------------------------------------------------
  // CONSOLE REPORT
  // ----------------------------------------------------------

  console.log("\n========================================");
  console.log("COMPARISON SUMMARY");
  console.log("========================================");

  console.log("Original records:", summary.originalRecordCount);
  console.log("V2 records:", summary.v2RecordCount);

  console.log("----------------------------------------");

  console.log("Unique original serials:", summary.originalUniqueSerialNumbers);
  console.log("Unique V2 serials:", summary.v2UniqueSerialNumbers);

  console.log("----------------------------------------");

  console.log("Records compared:", summary.recordsCompared);
  console.log("Exact matches:", summary.exactMatches);
  console.log("Mismatches:", summary.mismatches);
  console.log("Missing from V2:", summary.missingFromV2);
  console.log("Extra in V2:", summary.extraInV2);

  console.log("----------------------------------------");

  console.log(
    "Duplicate serials in original:",
    summary.duplicateSerialNumbersOriginal.length,
  );

  console.log(
    "Duplicate serials in V2:",
    summary.duplicateSerialNumbersV2.length,
  );

  console.log(
    "Duplicate numbers in original:",
    summary.duplicateNumbersOriginal,
  );
  console.log("Duplicate numbers in V2:", summary.duplicateNumbersV2);

  console.log("----------------------------------------");

  console.log("Prize groups checked:", summary.prizeGroupsChecked);
  console.log("Prize groups matched:", summary.prizeGroupsMatched);
  console.log("Prize groups mismatched:", summary.prizeGroupsMismatched);
  console.log("Missing numbers:", summary.totalMissingNumbers);
  console.log("Extra numbers:", summary.totalExtraNumbers);
  console.log("Count differences:", summary.countDifferences);

  console.log("----------------------------------------");

  console.log("V2 draw categories:", categorySummary.drawCategories);
  console.log("V2 prize categories:", categorySummary.prizeCategories);
  console.log(
    "Invalid draw categories:",
    categorySummary.invalidDrawCategories.length,
  );
  console.log(
    "Missing prize categories:",
    categorySummary.missingPrizeCategories.length,
  );

  console.log("----------------------------------------");

  console.log("FINAL RESULT:", passed ? "PASS" : "FAIL");

  console.log("\nReport saved to:");
  console.log(OUTPUT_PATH);

  await mongoose.disconnect();

  if (!passed) {
    process.exitCode = 1;
  }
}

main().catch(async (error) => {
  console.error("\nComparison failed:", error);

  if (mongoose.connection.readyState !== 0) {
    await mongoose.disconnect();
  }

  process.exitCode = 1;
});
