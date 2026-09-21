const mongoose = require("mongoose");
const fs = require("fs");

mongoose.connect("mongodb://localhost:27017/numbergrid");

const DataSchema = new mongoose.Schema({
  userId: String,
  date: String,
  numbers: [
    {
      number: String,
      count: Number,
    },
  ],
  createdAt: { type: Date, default: Date.now },
});

const UserData = mongoose.model("UserData", DataSchema);

async function countAndSaveRepeatsByPrefix() {
  const allDocs = await UserData.find();

  const result = {};

  for (const doc of allDocs) {
    if (!doc.userId || !Array.isArray(doc.numbers)) continue;

    const prefix = doc.userId.split("-")[0];
    if (!result[prefix]) result[prefix] = {};

    for (const entry of doc.numbers) {
      const num = entry.number;
      if (!result[prefix][num]) {
        result[prefix][num] = 0;
      }
      result[prefix][num] += 1;
    }
  }

  // Sort numbers in ascending order (as strings) within each prefix
  const sortedResult = {};
  for (const prefix in result) {
    const sorted = Object.entries(result[prefix])
      .sort((a, b) => a[0].localeCompare(b[0])) // ascending by number string
      .map(([number, count]) => ({ number, count }));
    sortedResult[prefix] = sorted;
  }

  // Save to JSON file
  const filePath = "./prefix_number_repeats.json";
  fs.writeFileSync(filePath, JSON.stringify(sortedResult, null, 2), "utf-8");

  console.log(`✅ Result saved to ${filePath}`);
  mongoose.disconnect();
}

countAndSaveRepeatsByPrefix();
