const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const AbsoluteData = require("../models/AbsoluteData");

// ------------------------------------------------------------
// CONFIGURATION
// ------------------------------------------------------------

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

const REPORT_PATH = path.resolve(
  __dirname,
  "../reports/absolute-v2-20-pdf-dry-run.json",
);

const OUTPUT_PATH = path.resolve(
  __dirname,
  "../../absolute-v2-20-pdf-comparison.json",
);

// ------------------------------------------------------------
// HELPERS
// ------------------------------------------------------------

function normalizeDate(value) {
  return String(value || "").trim();
}

function getNumbers(group) {
  return (group?.numbers || [])
    .map((item) =>
      String(typeof item === "string" ? item : item?.number || "").trim(),
    )
    .filter(Boolean)
    .sort();
}

function groupByPrize(series = []) {
  const result = new Map();

  for (const group of series) {
    const prize = Number(group.prize);

    if (!result.has(prize)) {
      result.set(prize, []);
    }

    result.get(prize).push(...getNumbers(group));
  }

  for (const [prize, numbers] of result) {
    result.set(prize, numbers.sort());
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

// ------------------------------------------------------------
// MAIN COMPARISON
// ------------------------------------------------------------

async function main() {
  if (!fs.existsSync(REPORT_PATH)) {
    throw new Error(`Dry-run report not found: ${REPORT_PATH}`);
  }

  const rawReport = fs.readFileSync(REPORT_PATH, "utf8").replace(/^\uFEFF/, "");

  const report = JSON.parse(rawReport);

  if (!report.dryRun || !Array.isArray(report.results)) {
    throw new Error("Invalid report or report is not a dry run.");
  }

  console.log("Connecting to MongoDB...");

  await mongoose.connect(MONGO_URI);

  const summary = {
    reportFiles: report.totalFiles,
    dryRunResults: report.results.length,
    originalRecordsFound: 0,
    exactMatches: 0,
    mismatches: 0,
    invalidDryRunResults: 0,
    missingOriginalRecords: 0,
    skippedResults: 0,
    comparisons: [],
  };

  for (const parsed of report.results) {
    if (parsed.status !== "dry-run-valid" || parsed.valid !== true) {
      summary.invalidDryRunResults++;

      summary.comparisons.push({
        fileName: parsed.fileName,
        serialNumber: parsed.serialNumber,
        status: "DRY_RUN_NOT_VALID",
        reason: parsed.reason || parsed.validationErrors,
      });

      continue;
    }

    const serialNumber = String(parsed.serialNumber || "").trim();

    const original = await AbsoluteData.findOne({
      serialNumber,
    }).lean();

    if (!original) {
      summary.missingOriginalRecords++;

      summary.comparisons.push({
        fileName: parsed.fileName,
        serialNumber,
        status: "ORIGINAL_RECORD_NOT_FOUND",
      });

      continue;
    }

    summary.originalRecordsFound++;

    const differences = [];

    // Compare dates
    if (normalizeDate(parsed.date) !== normalizeDate(original.date)) {
      differences.push({
        type: "DATE_MISMATCH",
        expected: original.date,
        actual: parsed.date,
      });
    }

    // Compare prize amounts and all winning numbers
    const originalGroups = groupByPrize(original.series);
    const parsedGroups = groupByPrize(parsed.series);

    const allPrizeAmounts = new Set([
      ...originalGroups.keys(),
      ...parsedGroups.keys(),
    ]);

    const prizeComparisons = [];

    for (const prize of [...allPrizeAmounts].sort((a, b) => b - a)) {
      const expected = originalGroups.get(prize) || [];
      const actual = parsedGroups.get(prize) || [];

      const numberDifferences = findDifferences(expected, actual);

      const exactMatch =
        numberDifferences.missing.length === 0 &&
        numberDifferences.extra.length === 0;

      const prizeResult = {
        prize,
        originalCount: expected.length,
        parsedCount: actual.length,
        exactMatch,
        missingNumbers: numberDifferences.missing,
        extraNumbers: numberDifferences.extra,
      };

      prizeComparisons.push(prizeResult);

      if (!exactMatch) {
        differences.push({
          type: "PRIZE_NUMBERS_MISMATCH",
          ...prizeResult,
        });
      }
    }

    const exactMatch = differences.length === 0;

    if (exactMatch) {
      summary.exactMatches++;
    } else {
      summary.mismatches++;
    }

    summary.comparisons.push({
      fileName: parsed.fileName,
      serialNumber,
      date: parsed.date,
      status: exactMatch ? "EXACT_MATCH" : "MISMATCH",
      originalPrizeGroups: original.series.length,
      parsedPrizeGroups: parsed.series.length,
      prizeComparisons,
      differences,
    });

    console.log(`${exactMatch ? "MATCH" : "MISMATCH"}: ${serialNumber}`);
  }

  const output = {
    generatedAt: new Date().toISOString(),
    sourceCollection: "absolute_data",
    dryRunReport: REPORT_PATH,
    summary,
  };

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2), "utf8");

  console.log("\n==================================");
  console.log("COMPARISON SUMMARY");
  console.log("==================================");
  console.log("PDFs in report:", summary.reportFiles);
  console.log("Results checked:", summary.dryRunResults);
  console.log("Original records found:", summary.originalRecordsFound);
  console.log("Exact matches:", summary.exactMatches);
  console.log("Mismatches:", summary.mismatches);
  console.log("Missing original records:", summary.missingOriginalRecords);
  console.log("Invalid dry runs:", summary.invalidDryRunResults);

  console.log("\nReport saved to:");
  console.log(OUTPUT_PATH);

  await mongoose.disconnect();
}

main().catch(async (error) => {
  console.error("Comparison failed:", error);

  if (mongoose.connection.readyState !== 0) {
    await mongoose.disconnect();
  }

  process.exitCode = 1;
});
