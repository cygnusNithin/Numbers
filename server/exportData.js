const mongoose = require("mongoose");
const fs = require("fs");
const LotteryData = require("./models/LotteryData"); // adjust path if needed

// 1. Connect to MongoDB
mongoose.connect("mongodb://localhost:27017/numbergrid");

async function exportData() {
  try {
    const docs = await LotteryData.find();
    const flatData = [];

    docs.forEach((doc) => {
      doc.series.forEach((prizeObj) => {
        prizeObj.numbers.forEach((numObj) => {
          flatData.push({
            date: doc.date || "", // ✅ use lowercase
            prize: prizeObj.prize,
            number: numObj.number,
            count: numObj.count,
          });
        });
      });
    });

    // Save to JSON
    fs.writeFileSync("lotteryData.json", JSON.stringify(flatData, null, 2));

    // Save to CSV
    const csvHeader = "date,prize,number,count\n";
    const csvRows = flatData.map(
      (row) => `${row.date},${row.prize},${row.number},${row.count}`
    );
    fs.writeFileSync("lotteryData.csv", csvHeader + csvRows.join("\n"));

    console.log(
      "✅ Export complete: lotteryData.json & lotteryData.csv created"
    );
    await mongoose.disconnect();
    process.exit(0);
  } catch (err) {
    console.error("❌ Error exporting:", err);
    await mongoose.disconnect();
    process.exit(1);
  }
}

exportData();
