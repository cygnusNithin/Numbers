const mongoose = require("mongoose");
const fs = require("fs");
const cliProgress = require("cli-progress");
const LotteryData = require("./models/LotteryData");

mongoose
  .connect("mongodb://localhost:27017/numbergrid", {
    useNewUrlParser: true,
    useUnifiedTopology: true,
  })
  .then(async () => {
    console.log("✅ Connected to MongoDB");
    await exportSummaryToCSV();
    console.log("\n🚀 Task Complete!");
    process.exit();
  })
  .catch((err) => console.error("❌ Connection error:", err));

async function exportSummaryToCSV() {
  const progressBar = new cliProgress.SingleBar({
    format:
      "Exporting Training Data |" +
      "{bar}" +
      "| {percentage}% || {value}/{total} Tasks",
    barCompleteChar: "\u2588",
    barIncompleteChar: "\u2591",
    hideCursor: true,
  });

  progressBar.start(4, 0); // 4 steps now

  try {
    // STEP 1: Get Total Draw Count (to calculate Gaps)
    const totalDraws = await LotteryData.countDocuments();
    progressBar.update(1);

    // STEP 2: Deep Aggregation
    // This finds the count, avg prize, AND the highest entryNumber (most recent) for every number
    const stats = await LotteryData.aggregate([
      { $unwind: "$series" },
      { $unwind: "$series.numbers" },
      {
        $group: {
          _id: "$series.numbers.number",
          totalHits: { $sum: "$series.numbers.count" },
          avgPrize: { $avg: "$series.prize" },
          lastEntry: { $max: "$entryNumber" }, // Latest entryNumber it appeared in
          lastDate: { $max: "$date" }, // Latest date string it appeared in
        },
      },
      { $sort: { totalHits: -1 } },
    ]);
    progressBar.update(2);

    // STEP 3: Format CSV with Training Metrics
    // We calculate "Current Gap" = Total Draws minus the Last Entry it appeared in
    let csvContent =
      "Number,TotalHits,AvgPrize,LastSeenDate,CurrentGap,ThousandsDigit\n";

    stats.forEach((row) => {
      const currentGap = totalDraws - row.lastEntry;
      const thousandsDigit = row._id.padStart(4, "0").charAt(0); // Extracts '4' from '4500'

      csvContent += `${row._id},${row.totalHits},${row.avgPrize.toFixed(2)},${
        row.lastDate
      },${currentGap},${thousandsDigit}\n`;
    });
    progressBar.update(3);

    // STEP 4: Write to File
    fs.writeFileSync("project_charlie_training_set.csv", csvContent);
    progressBar.update(4);
    progressBar.stop();

    console.log(`\n📂 File saved: project_charlie_training_set.csv`);
    console.log(
      `📊 Summary: ${stats.length} unique numbers analyzed from ${totalDraws} draws.`
    );
  } catch (error) {
    progressBar.stop();
    console.error("\n❌ Export Failed:", error);
  }
}
