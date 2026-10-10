const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";
const MIN_TRAINING_DRAWS = 300;
const WINDOWS = [25, 50, 100, 250];

function parseDate(doc) {
  if (doc.drawDate && !Number.isNaN(new Date(doc.drawDate).getTime())) {
    return new Date(doc.drawDate);
  }

  const match = String(doc.date || "").match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;

  return new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
}

function getNumbers(doc) {
  const numbers = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      if (item.number === undefined || item.number === null) continue;

      const value = String(item.number).trim();
      if (!/^\d{1,4}$/.test(value)) continue;

      numbers.add(value.padStart(4, "0"));
    }
  }

  return numbers;
}

function overlapPercent(a, b, k = 25) {
  const setB = new Set(b.slice(0, k).map((x) => x.number));
  const common = a.slice(0, k).filter((x) => setB.has(x.number)).length;
  return ((common / k) * 100).toFixed(1) + "%";
}

function rankNumbers(scores, historicalFrequency) {
  return Array.from({ length: 10000 }, (_, i) => String(i).padStart(4, "0"))
    .map((number) => ({
      number,
      score: scores.get(number) || 0,
      historical: historicalFrequency.get(number) || 0,
    }))
    .sort(
      (a, b) =>
        b.score - a.score ||
        b.historical - a.historical ||
        a.number.localeCompare(b.number),
    );
}

async function main() {
  await mongoose.connect(MONGO_URI);
  console.log("Connected to MongoDB.");

  try {
    const docs = await AbsoluteData.find({}).lean();
    const unique = new Map();

    for (const doc of docs) {
      if (!doc.serialNumber) continue;
      if (unique.has(String(doc.serialNumber))) continue;

      const date = parseDate(doc);
      const numbers = getNumbers(doc);
      if (!date || numbers.size === 0) continue;

      unique.set(String(doc.serialNumber), {
        serialNumber: String(doc.serialNumber),
        recordNumber: Number(doc.recordNumber) || 0,
        date,
        numbers,
      });
    }

    const draws = [...unique.values()].sort(
      (a, b) =>
        a.date - b.date ||
        a.recordNumber - b.recordNumber ||
        a.serialNumber.localeCompare(b.serialNumber),
    );

    console.log("Unique draw events:", draws.length);

    const checkpoints = [300, 500, 800, 1200, 1600, draws.length - 1].filter(
      (index, i, arr) =>
        index >= MIN_TRAINING_DRAWS &&
        index < draws.length &&
        arr.indexOf(index) === i,
    );

    for (const targetIndex of checkpoints) {
      const historicalFrequency = new Map();
      const recentScores = new Map(
        WINDOWS.map((windowSize) => [windowSize, new Map()]),
      );

      // Count number appearances across all prior draw events.
      for (let i = 0; i < targetIndex; i++) {
        for (const number of draws[i].numbers) {
          historicalFrequency.set(
            number,
            (historicalFrequency.get(number) || 0) + 1,
          );
        }
      }

      console.log("\n========================================");
      console.log(`Checkpoint: ${targetIndex}/${draws.length - 1} prior draws`);
      console.log("Next draw:", draws[targetIndex].serialNumber);
      console.log("Date:", draws[targetIndex].date.toISOString().slice(0, 10));

      const rankings = new Map();

      for (const windowSize of WINDOWS) {
        const start = Math.max(0, targetIndex - windowSize);
        const scores = new Map();

        for (let i = start; i < targetIndex; i++) {
          for (const number of draws[i].numbers) {
            scores.set(number, (scores.get(number) || 0) + 1);
          }
        }

        recentScores.set(windowSize, scores);
        rankings.set(windowSize, rankNumbers(scores, historicalFrequency));

        const values = [...scores.values()];
        const distinctScoreCount = new Set(values).size;
        const maxScore = values.length ? Math.max(...values) : 0;

        console.log(
          `Window ${String(windowSize).padStart(3)}: ` +
            `draws=${targetIndex - start}, ` +
            `numbersSeen=${scores.size}, ` +
            `distinctPositiveScores=${distinctScoreCount}, ` +
            `maxScore=${maxScore}`,
        );
      }

      console.log("\nTop-25 overlap between recent-only rankings:");
      for (let i = 0; i < WINDOWS.length; i++) {
        for (let j = i + 1; j < WINDOWS.length; j++) {
          const a = rankings.get(WINDOWS[i]);
          const b = rankings.get(WINDOWS[j]);

          console.log(
            `${WINDOWS[i]} vs ${WINDOWS[j]}: ${overlapPercent(a, b)}`,
          );
        }
      }

      console.log("\nTop 10 recent-only ranking for each window:");
      for (const windowSize of WINDOWS) {
        console.log(
          `${windowSize}:`,
          rankings
            .get(windowSize)
            .slice(0, 10)
            .map((x) => `${x.number}(${x.score})`)
            .join(", "),
        );
      }
    }
  } finally {
    await mongoose.disconnect();
    console.log("\nDisconnected from MongoDB.");
  }
}

main().catch((error) => {
  console.error("Diagnostic failed:", error);
  process.exitCode = 1;
});
