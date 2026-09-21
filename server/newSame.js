const mongoose = require("mongoose");
const LotteryData = require("./models/LotteryData"); // your schema file
const fs = require("fs");

// Connect to MongoDB
mongoose
  .connect("mongodb://localhost:27017/numbergrid", {
    useNewUrlParser: true,
    useUnifiedTopology: true,
  })
  .then(() => console.log("✅ Connected to MongoDB"))
  .catch((err) => console.error("❌ Connection error:", err));

// Function to find repeated numbers in a prize category
async function findRepeats(prizeAmount) {
  const repeats = await LotteryData.aggregate([
    { $unwind: "$series" },
    { $match: { "series.prize": prizeAmount } }, // filter only this prize (eg: 5000)
    { $unwind: "$series.numbers" },
    {
      $group: {
        _id: {
          number: "$series.numbers.number",
          prize: "$series.prize",
        },
        dates: { $addToSet: "$date" },
        count: { $sum: 1 },
      },
    },
    { $match: { count: { $gt: 1 } } }, // only repeated
    { $sort: { count: -1 } },
  ]);

  return repeats;
}

// Run the check
(async () => {
  try {
    const repeats5000 = await findRepeats(5000);

    let csv = "Number,Prize,Count,Dates\n";
    repeats5000.forEach((r) => {
      // ✅ Sort dates ascending (convert dd/mm/yyyy → Date)
      const sortedDates = r.dates.sort((a, b) => {
        const [da, ma, ya] = a.split("/").map(Number);
        const [db, mb, yb] = b.split("/").map(Number);
        return new Date(ya, ma - 1, da) - new Date(yb, mb - 1, db);
      });

      csv += `${r._id.number},${r._id.prize},${r.count},"${sortedDates.join(
        " | "
      )}"\n`;
    });

    fs.writeFileSync("repeats5001.csv", csv);
    console.log("✅ Results saved to repeats5000.csv (dates sorted ascending)");

    mongoose.connection.close();
  } catch (err) {
    console.error(err);
    mongoose.connection.close();
  }
})();
