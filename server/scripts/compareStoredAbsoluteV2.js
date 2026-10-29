
const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");
const AbsoluteDataV2 = require("../models/AbsoluteDataV2");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

function normalizeSeries(series = []) {
  const byPrize = new Map();

  for (const group of series) {
    const prize = Number(group.prize);
    const numbers = (group.numbers || []).map((item) =>
      String(typeof item === "object" ? item.number : item).trim()
    );

    if (!byPrize.has(prize)) byPrize.set(prize, []);
    byPrize.get(prize).push(...numbers);
  }

  return byPrize;
}

function compareSeries(oldSeries, newSeries) {
  const oldMap = normalizeSeries(oldSeries);
  const newMap = normalizeSeries(newSeries);
  const prizes = new Set([...oldMap.keys(), ...newMap.keys()]);
  const differences = [];

  for (const prize of [...prizes].sort((a, b) => b - a)) {
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
    const serialNumbers = [
      "KR-456", "KR-457", "KR-458", "KR-459",
      "W-576", "AK-457", "NR-185", "SS-222",
      "KN-329", "W-578",
    ];

    let passed = 0;
    let failed = 0;

    for (const serialNumber of serialNumbers) {
      const [oldRecord, newRecord] = await Promise.all([
        AbsoluteData.findOne({ serialNumber }).lean(),
        AbsoluteDataV2.findOne({ serialNumber }).lean(),
      ]);

      if (!oldRecord || !newRecord) {
        failed++;
        console.log(
          `FAIL ${serialNumber}: ` +
          `original=${!!oldRecord}, V2=${!!newRecord}`
        );
        continue;
      }

      const differences = compareSeries(
        oldRecord.series,
        newRecord.series
      );

      if (differences.length === 0) {
        passed++;
        console.log(
          `PASS ${serialNumber}: saved winning numbers match`
        );
      } else {
        failed++;
        console.log(`FAIL ${serialNumber}:`);
        console.dir(differences, { depth: null });
      }
    }

    console.log(`\nStored-data comparison: ${passed}/10 passed`);

    if (failed > 0) process.exitCode = 1;
  } finally {
    await mongoose.disconnect();
  }
}

main().catch((error) => {
  console.error("Comparison failed:", error);
  process.exitCode = 1;
});
