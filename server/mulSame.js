const mongoose = require("mongoose");
const LotteryData = require("./models/LotteryData");
const fs = require("fs");

mongoose
  .connect("mongodb://localhost:27017/numbergrid", {
    useNewUrlParser: true,
    useUnifiedTopology: true,
  })
  .then(() => console.log("✅ Connected to MongoDB"))
  .catch((err) => console.error("❌ Connection error:", err));

async function findNumberSets(prizeAmount) {
  // Step 1: Collect all numbers by date + code
  const draws = await LotteryData.aggregate([
    { $unwind: "$series" },
    { $match: { "series.prize": prizeAmount } },
    { $unwind: "$series.numbers" },
    {
      $group: {
        _id: { date: "$date", code: "$serialNumber" }, // include code
        numbers: { $addToSet: "$series.numbers.number" },
      },
    },
  ]);

  // Step 2: Map numbers → (date+code)
  const comboMap = new Map();

  draws.forEach((draw) => {
    const nums = draw.numbers.sort(); // keep sorted
    for (let i = 0; i < nums.length; i++) {
      for (let j = i + 1; j < nums.length; j++) {
        const key = `${nums[i]}|${nums[j]}`;
        if (!comboMap.has(key)) {
          comboMap.set(key, []);
        }
        comboMap.get(key).push(`${draw._id.date} (${draw._id.code})`); // attach code with date
      }
    }
  });

  // Step 3: Only keep combos that repeat (appear in >1 draw)
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

    fs.writeFileSync("number_combos.csv", csv);
    console.log("✅ Saved to number_combos.csv");

    mongoose.connection.close();
  } catch (err) {
    console.error(err);
    mongoose.connection.close();
  }
})();
