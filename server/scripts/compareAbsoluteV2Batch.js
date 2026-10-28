
const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const API_URL =
  "http://127.0.0.1:5000/api/absolute-v2/import-folder?dryRun=true";

function normalizeSeries(series = []) {
  const result = new Map();

  for (const group of series) {
    const prize = Number(group.prize);
    const numbers = (group.numbers || []).map((item) =>
      String(typeof item === "object" ? item.number : item).trim()
    );

    result.set(prize, numbers);
  }

  return result;
}

function compareSeries(oldSeries, newSeries) {
  const oldMap = normalizeSeries(oldSeries);
  const newMap = normalizeSeries(newSeries);

  const prizes = [...new Set([...oldMap.keys(), ...newMap.keys()])]
    .sort((a, b) => b - a);

  const differences = [];

  for (const prize of prizes) {
    const oldNumbers = oldMap.get(prize) || [];
    const newNumbers = newMap.get(prize) || [];

    const oldSet = new Set(oldNumbers);
    const newSet = new Set(newNumbers);

    const missing = [...oldSet].filter((n) => !newSet.has(n));
    const extra = [...newSet].filter((n) => !oldSet.has(n));

    const duplicateOld = oldNumbers.filter(
      (n, i) => oldNumbers.indexOf(n) !== i
    );
    const duplicateNew = newNumbers.filter(
      (n, i) => newNumbers.indexOf(n) !== i
    );

    if (
      missing.length ||
      extra.length ||
      duplicateOld.length ||
      duplicateNew.length ||
      oldNumbers.length !== newNumbers.length
    ) {
      differences.push({
        prize,
        oldCount: oldNumbers.length,
        newCount: newNumbers.length,
        missing,
        extra,
        duplicateOld,
        duplicateNew,
      });
    }
  }

  return differences;
}

async function main() {
  await mongoose.connect(MONGO_URI);

  try {
    const response = await fetch(API_URL, { method: "POST" });
    const body = await response.text();

    if (!response.ok) {
      throw new Error(`Dry-run HTTP ${response.status}: ${body.slice(0, 500)}`);
    }

    const payload = JSON.parse(body);

    if (!payload.success || !payload.dryRun) {
      throw new Error("API did not return a successful dry-run response.");
    }

    const parsedRecords = payload.results.filter(
      (item) => item.status === "dry-run" && item.serialNumber
    );

    const serialNumbers = parsedRecords.map((item) => item.serialNumber);

    const oldRecords = await AbsoluteData.find({
      serialNumber: { $in: serialNumbers },
    }).lean();

    const oldBySerial = new Map(
      oldRecords.map((record) => [record.serialNumber, record])
    );

    console.log(`\nDry-run PDFs: ${payload.totalFiles}`);
    console.log(`Parsed records: ${parsedRecords.length}`);
    console.log(`Existing database matches: ${oldRecords.length}\n`);

    let exactMatches = 0;
    let differencesFound = 0;
    let noReference = 0;

    for (const parsed of parsedRecords) {
      const oldRecord = oldBySerial.get(parsed.serialNumber);

      if (!oldRecord) {
        noReference++;
        console.log(
          `[NO REFERENCE] ${parsed.fileName} | ${parsed.serialNumber} | ` +
          `${parsed.date} | parsed ${parsed.totalNumbers} numbers`
        );
        continue;
      }

      const differences = compareSeries(oldRecord.series, parsed.series);

      if (differences.length === 0) {
        exactMatches++;
        console.log(
          `[MATCH] ${parsed.fileName} | ${parsed.serialNumber} | ` +
          `${parsed.totalNumbers} numbers`
        );
      } else {
        differencesFound++;
        console.log(
          `\n[MISMATCH] ${parsed.fileName} | ${parsed.serialNumber}`
        );

        for (const d of differences) {
          console.log(
            `  Prize ${d.prize}: old=${d.oldCount}, V2=${d.newCount}`
          );
          if (d.missing.length) console.log("    Missing in V2:", d.missing);
          if (d.extra.length) console.log("    Extra in V2:", d.extra);
          if (d.duplicateOld.length) console.log("    Old duplicates:", d.duplicateOld);
          if (d.duplicateNew.length) console.log("    V2 duplicates:", d.duplicateNew);
        }
      }
    }

    console.log("\n=== COMPARISON SUMMARY ===");
    console.log("Exact matches:", exactMatches);
    console.log("Mismatches:", differencesFound);
    console.log("No existing reference:", noReference);
    console.log("Failed PDF parses:", payload.failed);
    console.log("Skipped results:", payload.skipped);
    console.log("\nNo database records were written by this script.");
  } finally {
    await mongoose.disconnect();
  }
}

main().catch((error) => {
  console.error("Batch comparison failed:", error.message);
  process.exitCode = 1;
});
