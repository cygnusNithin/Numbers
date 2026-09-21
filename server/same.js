const mongoose = require("mongoose");

mongoose.connect("mongodb://localhost:27017/numbergrid");

const userDataSchema = new mongoose.Schema({}, { collection: "userdatas" });
const UserData = mongoose.model("UserData", userDataSchema);

async function findSimilarSequences(minMatches = 2) {
  const allDocs = await UserData.find();
  const total = allDocs.length;

  for (let i = 0; i < total; i++) {
    const sourceDoc = allDocs[i];

    const sourceNumbers = Array.isArray(sourceDoc.numbers)
      ? sourceDoc.numbers.map((n) => n.number)
      : [];

    for (let j = i + 1; j < total; j++) {
      const targetDoc = allDocs[j];
      const targetNumbers = Array.isArray(targetDoc.numbers)
        ? targetDoc.numbers.map((n) => n.number)
        : [];

      const common = sourceNumbers.filter((num) => targetNumbers.includes(num));

      if (common.length >= minMatches) {
        console.log("🔍 Match Found:");
        console.log(`Source: ${sourceDoc.userId} (${sourceDoc.date})`);
        console.log(`Target: ${targetDoc.userId} (${targetDoc.date})`);
        console.log(`Common Numbers: ${common.join(", ")}`);
        console.log("--------------------------------------------------");
      }
    }
  }

  mongoose.disconnect();
}

findSimilarSequences(2);
