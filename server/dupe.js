const { MongoClient } = require("mongodb");

const uri = "mongodb://localhost:27017"; // adjust if needed
const client = new MongoClient(uri);

const targetSequence = ["4393"];

(async () => {
  try {
    await client.connect();
    const db = client.db("numbergrid");
    const collection = db.collection("userdatas");

    // Get all documents
    const allDocs = await collection.find({}).toArray();

    const matchedDocs = [];

    for (const doc of allDocs) {
      const numArray = doc.numbers.map((n) => n.number);

      // Check if the sequence exists in order
      for (let i = 0; i < numArray.length - targetSequence.length + 1; i++) {
        const slice = numArray.slice(i, i + targetSequence.length);
        if (JSON.stringify(slice) === JSON.stringify(targetSequence)) {
          matchedDocs.push({
            userId: doc.userId,
            date: doc.date,
            matchedSequence: slice,
          });
          break;
        }
      }
    }

    if (matchedDocs.length) {
      console.log("✅ Matching sequences found:");
      console.log(matchedDocs);
    } else {
      console.log("❌ No matching sequence found.");
    }
  } catch (err) {
    console.error("Error:", err);
  } finally {
    await client.close();
  }
})();
