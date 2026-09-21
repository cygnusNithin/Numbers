const fs = require("fs");
const path = require("path");
const PdfParse = require("pdf-parse");
const { MongoClient } = require("mongodb");

// =======================
// CONFIG
// =======================
const MONGO_URI = "mongodb://localhost:27017/";
const DB_NAME = "numbergrid";
const COLLECTION = "lotteryresults";
const FILES_FOLDER = path.join(__dirname, "files"); // folder with PDFs

// =======================
// HELPERS
// =======================
async function cleanText(text) {
  // normalize whitespace
  let cleaned = text.replace(/\s+/g, " ").trim();

  // remove "Cons Prize" block (only under 1st Prize)
  const consStart = cleaned.indexOf("Cons Prize-Rs :5000/-");
  const consEnd = cleaned.indexOf("2nd Prize");
  if (consStart !== -1 && consEnd !== -1 && consEnd > consStart) {
    cleaned = cleaned.slice(0, consStart) + cleaned.slice(consEnd);
  }

  return cleaned;
}

async function extractSinglePrizes(text) {
  const prizeMap = {};

  // Regex to capture: "1st Prize Rs :10000000/- 1) PJ 313650"
  const regex = /(\d+(st|nd|rd|th) Prize).*?([A-Z]{2}\s*\d{6})/g;

  let match;
  while ((match = regex.exec(text)) !== null) {
    const prizeName = match[1].trim(); // e.g., "1st Prize"
    const number = match[3].replace(/\s+/g, ""); // e.g., "PJ313650"
    prizeMap[prizeName] = number;
  }

  return prizeMap;
}

function extractSerialNumber(text) {
  const lotteryMatch = text.match(
    /LOTTERY\s+NO\.?\s*([A-Z0-9-]+)(?:st|nd|rd|th)?/i
  );
  return lotteryMatch
    ? lotteryMatch[1].trim().replace(/(st|nd|rd|th)$/i, "")
    : "Unknown";
}

function extractDrawDate(text) {
  const dateMatch = text.match(
    /\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})\b/i
  );
  return dateMatch ? dateMatch[0] : "Unknown";
}

// =======================
// MAIN
// =======================
async function processPDFs() {
  const client = new MongoClient(MONGO_URI);
  try {
    await client.connect();
    const db = client.db(DB_NAME);
    const coll = db.collection(COLLECTION);

    // Ensure unique index on serialNumber
    await coll.createIndex({ serialNumber: 1 }, { unique: true });

    const files = fs
      .readdirSync(FILES_FOLDER)
      .filter((f) => f.endsWith(".pdf"));
    console.log(`📂 Found ${files.length} PDF files`);

    for (const fileName of files) {
      const filePath = path.join(FILES_FOLDER, fileName);
      const buffer = fs.readFileSync(filePath);
      const data = await PdfParse(buffer);

      const serialNumber = extractSerialNumber(data.text);
      const drawDate = extractDrawDate(data.text);
      const text = await cleanText(data.text);
      const prizeData = await extractSinglePrizes(text);

      if (!prizeData || Object.keys(prizeData).length === 0) {
        console.log(`⚠️ Could not extract prizes from ${fileName}`);
        continue;
      }

      // --- Check for duplicate ---
      const exists = await coll.findOne({ serialNumber });

      if (exists) {
        console.log(`⚠️ Duplicate found → ${serialNumber} (skipped)`);
        continue;
      }

      // --- Insert new record ---
      const doc = {
        file: fileName,
        serialNumber,
        drawDate,
        prizes: prizeData,
        importedAt: new Date(),
      };

      await coll.insertOne(doc);

      console.log(`✅ Inserted results for ${serialNumber} (${fileName})`);
    }

    console.log("🎯 Extraction & save complete (duplicates skipped).");
  } catch (err) {
    console.error("❌ Error:", err.message);
  } finally {
    await client.close();
  }
}

processPDFs();
