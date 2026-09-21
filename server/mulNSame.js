const mongoose = require("mongoose");
const LotteryData = require("./models/LotteryData");
const fs = require("fs");

// =======================
// CONFIG
// =======================
const MIN_SIZE = 2;
const MAX_SIZE = 3; // ✅ pairs + triplets

mongoose
  .connect("mongodb://localhost:27017/numbergrid", {
    useNewUrlParser: true,
    useUnifiedTopology: true,
  })
  .then(() => console.log("✅ Connected to MongoDB"))
  .catch((err) => console.error("❌ Connection error:", err));

// Utility: generate combinations
function getCombinations(array, size) {
  if (size > array.length) return [];
  if (size === 1) return array.map((el) => [el]);

  let combos = [];
  for (let i = 0; i < array.length; i++) {
    const head = array[i];
    const tailCombos = getCombinations(array.slice(i + 1), size - 1);
    for (const tail of tailCombos) {
      combos.push([head, ...tail]);
    }
  }
  return combos;
}

async function findNumberSets(prizeAmount) {
  const draws = await LotteryData.aggregate([
    { $unwind: "$series" },
    { $match: { "series.prize": prizeAmount } },
    { $unwind: "$series.numbers" },
    {
      $group: {
        _id: { date: "$date", code: "$serialNumber" },
        numbers: { $addToSet: "$series.numbers.number" },
      },
    },
  ]);

  const comboMap = new Map();

  for (const draw of draws) {
    const nums = draw.numbers.sort();

    for (let size = MIN_SIZE; size <= MAX_SIZE; size++) {
      const subsets = getCombinations(nums, size);
      for (const subset of subsets) {
        const key = subset.join("|");
        if (!comboMap.has(key)) {
          comboMap.set(key, []);
        }
        comboMap.get(key).push(`${draw._id.date} (${draw._id.code})`);
      }
    }
  }

  const results = [];
  comboMap.forEach((appearances, combo) => {
    if (appearances.length > 1) {
      results.push({
        prize: prizeAmount,
        count: appearances.length,
        numbers: combo,
        draws: appearances.join("|"),
      });
    }
  });

  return results;
}

(async () => {
  try {
    const combos = await findNumberSets(5000);

    let csv = "Prize,Count,Numbers,Dates+Codes\n";
    combos.forEach((c) => {
      csv += `${c.prize},${c.count},${c.numbers},${c.draws}\n`;
    });

    fs.writeFileSync("number_N_combos.csv", csv);
    console.log("✅ Saved to number_combos.csv");

    mongoose.connection.close();
  } catch (err) {
    console.error(err);
    mongoose.connection.close();
  }
})();
