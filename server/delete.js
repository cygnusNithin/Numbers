const { MongoClient } = require("mongodb");

const uri = "mongodb://localhost:27017"; // adjust if your port is different
const dbName = "numbergrid";
const collectionName = "userdatas";

async function deleteWrongEntries() {
  const client = new MongoClient(uri);

  try {
    await client.connect();
    console.log("✅ Connected to MongoDB");

    const db = client.db(dbName);
    const collection = db.collection(collectionName);

    // Get the 109th document (index 108)
    const docs = await collection
      .find()
      .sort({ _id: 1 })
      .skip(108)
      .limit(1)
      .toArray();

    if (!docs.length) {
      console.log("⚠️ Couldn't find the 109th document.");
      return;
    }

    const cutoffId = docs[0]._id;
    console.log("📍 Cutoff _id:", cutoffId);

    // Delete all documents with _id greater than cutoffId
    const result = await collection.deleteMany({ _id: { $gt: cutoffId } });
    console.log(`🗑️ Deleted ${result.deletedCount} documents after index 108`);
  } catch (error) {
    console.error("❌ Error:", error);
  } finally {
    await client.close();
    console.log("🔌 MongoDB connection closed.");
  }
}

//deleteWrongEntries();
