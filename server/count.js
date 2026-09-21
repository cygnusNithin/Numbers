const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const outputPath = path.join(__dirname, "repeated_numbers.json");

mongoose.connect("mongodb://localhost:27017/numbergrid", {
  useNewUrlParser: true,
  useUnifiedTopology: true,
});

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

async function analyzeNumberRepetitionByPrefix() {
  const allDocs = await UserData.find();
  const numberStats = {}; // { '4393': { KR: 3, AK: 2, NR: 4 } }

  for (const doc of allDocs) {
    if (!doc.userId || typeof doc.userId !== "string") continue;
    const prefix = doc.userId.split("-")[0];

    if (!Array.isArray(doc.numbers)) continue;

    for (const numObj of doc.numbers) {
      const number = numObj?.number;
      if (!number) continue;

      if (!numberStats[number]) numberStats[number] = {};
      if (!numberStats[number][prefix]) numberStats[number][prefix] = 0;

      numberStats[number][prefix]++;
    }
  }

  const repeatedNumbers = Object.entries(numberStats)
    .filter(
      ([_, prefixes]) =>
        Object.keys(prefixes).length > 1 || // appears in more than 1 prefix
        Object.values(prefixes).some((count) => count > 1) // or repeats in the same prefix
    )
    .map(([number, prefixes]) => ({ number, prefixes }));

  console.log("🔁 Repeating Numbers by Prefix:");
  console.dir(repeatedNumbers, { depth: null });
  repeatedNumbers.sort((a, b) => parseInt(a.number) - parseInt(b.number));
  fs.writeFileSync(
    outputPath,
    JSON.stringify(repeatedNumbers, null, 2),
    "utf-8"
  );

  console.log(`✅ Saved output to: ${outputPath}`);

  mongoose.disconnect();
}

analyzeNumberRepetitionByPrefix();
