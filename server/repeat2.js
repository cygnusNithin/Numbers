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

async function countRepeatsMinTwoAndSave() {
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

  // Filter for count >= 2 and sort
  const filteredResult = {};
  for (const prefix in result) {
    const filteredSorted = Object.entries(result[prefix])
      .filter(([_, count]) => count >= 2)
      .sort((a, b) => a[0].localeCompare(b[0])) // sort by number string
      .map(([number, count]) => ({ number, count }));

    if (filteredSorted.length > 0) {
      filteredResult[prefix] = filteredSorted;
    }
  }

  const filePath = "./prefix_number_repeats_min2.json";
  fs.writeFileSync(filePath, JSON.stringify(filteredResult, null, 2), "utf-8");

  console.log(`✅ Filtered result (min count 2) saved to ${filePath}`);
  mongoose.disconnect();
}

countRepeatsMinTwoAndSave();
