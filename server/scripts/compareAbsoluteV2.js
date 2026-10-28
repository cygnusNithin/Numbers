
const mongoose = require("mongoose");

// Adjust this path only if your existing model lives elsewhere.
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const PDF_FILE = "draw-72893.pdf";
const SERIAL_NUMBER = "W-642";

const API_URL =
  "http://127.0.0.1:5000/api/absolute-v2/import-folder" +
  `?file=${encodeURIComponent(PDF_FILE)}&dryRun=true`;

function normalizeSeries(series = []) {
  const result = new Map();

  for (const group of series) {
    const prize = Number(group.prize ?? group.prizeAmount);
    const numbers = (group.numbers || []).map((item) =>
      String(typeof item === "object" ? item.number : item).trim()
    );

    result.set(prize, numbers);
  }

  return result;
}

function compareNumbers(expected, actual) {
  const expectedSet = new Set(expected);
  const actualSet = new Set(actual);

  return {
    expectedCount: expected.length,
    actualCount: actual.length,
    missing: [...expectedSet].filter((n) => !actualSet.has(n)),
    extra: [...actualSet].filter((n) => !expectedSet.has(n)),
    duplicateExpected: expected.filter(
      (n, i) => expected.indexOf(n) !== i
    ),
    duplicateActual: actual.filter(
      (n, i) => actual.indexOf(n) !== i
    ),
  };
}

async function main() {
  await mongoose.connect(MONGO_URI);

  try {
    const oldRecord = await AbsoluteData.findOne({
      serialNumber: SERIAL_NUMBER,
    }).lean();

    if (!oldRecord) {
      throw new Error(`Existing record ${SERIAL_NUMBER} was not found.`);
    }

    const response = await fetch(API_URL, {
  method: "POST",
  headers: {
    Accept: "application/json",
  },
});

const responseText = await response.text();

if (!response.ok) {
  throw new Error(
    `Dry-run API failed: HTTP ${response.status}\n` +
    `URL: ${API_URL}\n` +
    `Response: ${responseText.slice(0, 1000)}`
  );
}

let payload;

try {
  payload = JSON.parse(responseText);
} catch {
  throw new Error(
    `API returned invalid JSON:\n${responseText.slice(0, 1000)}`
  );
}
    const dryRun = payload.results?.find(
      (item) => item.serialNumber === SERIAL_NUMBER
    );

    if (!dryRun?.series) {
      throw new Error(
        "Dry-run result was not found. Check the API response structure."
      );
    }

    const oldSeries = normalizeSeries(oldRecord.series);
    const newSeries = normalizeSeries(dryRun.series);
    const prizes = [...new Set([
      ...oldSeries.keys(),
      ...newSeries.keys(),
    ])].sort((a, b) => b - a);

    let allMatch = true;

    console.log(`\nComparing ${SERIAL_NUMBER} (${PDF_FILE})\n`);

    for (const prize of prizes) {
      const oldNumbers = oldSeries.get(prize) || [];
      const newNumbers = newSeries.get(prize) || [];
      const comparison = compareNumbers(oldNumbers, newNumbers);

      const matches =
        comparison.missing.length === 0 &&
        comparison.extra.length === 0 &&
        comparison.duplicateExpected.length === 0 &&
        comparison.duplicateActual.length === 0;

      if (!matches) allMatch = false;

      console.log(`Prize ₹${prize}: ${matches ? "MATCH" : "MISMATCH"}`);
      console.log(
        `  Existing: ${comparison.expectedCount}, V2: ${comparison.actualCount}`
      );

      if (!matches) {
        console.log("  Missing from V2:", comparison.missing);
        console.log("  Extra in V2:", comparison.extra);
        console.log("  Existing duplicates:", comparison.duplicateExpected);
        console.log("  V2 duplicates:", comparison.duplicateActual);
      }
    }

    console.log(
      `\nFINAL RESULT: ${allMatch ? "ALL PRIZE GROUPS MATCH" : "DIFFERENCES FOUND"}`
    );
  } finally {
    await mongoose.disconnect();
  }
}

main().catch((error) => {
  console.error("Comparison failed:", error.message);
  process.exitCode = 1;
});
