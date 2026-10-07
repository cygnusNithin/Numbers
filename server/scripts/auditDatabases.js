const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const PdfParse = require("pdf-parse");

const LotteryData = require("../models/LotteryData");
const LotteryDataNew = require("../models/LotteryDataNew");
const FullLotteryData = require("../models/FullLotteryData");
const AbsoluteData = require("../models/AbsoluteData");

const {
  getPrizeNumbersByAmount,
  extractSerialNumber,
} = require("../routes/utils/lotteryHelpers");

const { extractDateFromText } = require("../routes/utils/dateHelpers");

const FILES_DIR = path.join(__dirname, "..", "files");

const models = {
  LotteryData,
  LotteryDataNew,
  FullLotteryData,
  AbsoluteData,
};

function classifyLotteryCategory(serialNumber = "") {
  const serial = String(serialNumber).trim().toUpperCase();

  if (serial.startsWith("BM-")) {
    return "BM";
  }

  if (serial.startsWith("BR-")) {
    return "BR";
  }

  return "OTHER";
}

function expectedDatabases(category) {
  switch (category) {
    case "BM":
      return ["AbsoluteData", "FullLotteryData"];

    case "BR":
      return ["AbsoluteData", "LotteryDataNew"];

    case "OTHER":
      return [
        "AbsoluteData",
        "FullLotteryData",
        "LotteryDataNew",
        "LotteryData",
      ];

    default:
      return [];
  }
}

function normalizeNumbers(numbers = []) {
  return [
    ...new Set(
      numbers
        .map((n) => String(n).trim().padStart(4, "0"))
        .filter((n) => /^\d{4}$/.test(n)),
    ),
  ].sort();
}

function compareArrays(expected, actual) {
  const e = normalizeNumbers(expected);
  const a = normalizeNumbers(actual);

  const expectedSet = new Set(e);
  const actualSet = new Set(a);

  const missing = e.filter((n) => !actualSet.has(n));
  const extra = a.filter((n) => !expectedSet.has(n));

  return {
    match: missing.length === 0 && extra.length === 0,
    expectedCount: e.length,
    actualCount: a.length,
    missing,
    extra,
  };
}

function extractPrizeSection(text, fileName) {
  let extractedSection = "";

  if (fileName.toLowerCase().startsWith("tmp")) {
    const startPhrase = "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";

    const endPhrase =
      "The  prize  winners  are  advised  to  verify  the  winning  numbers  with  the  results  published  in  the  Kerala  Government";

    const startIndex = text.toLowerCase().indexOf(startPhrase.toLowerCase());

    const endIndex = text.toLowerCase().indexOf(endPhrase.toLowerCase());

    if (startIndex !== -1) {
      const start = startIndex + startPhrase.length;

      if (endIndex !== -1 && endIndex > start) {
        extractedSection = text.substring(start, endIndex).trim();
      } else {
        extractedSection = text.substring(start).trim();
      }
    }
  } else {
    let cleanText = text
      .replace(/\s+/g, " ")
      .replace(/\u0000/g, "")
      .trim();

    cleanText = cleanText.replace(
      /Page\s*\d+\s*Modernization\s*&\s*IT\s*Software\s*Division\s*:\s*Department\s*of\s*State\s*Lotteries\s*\d{2}\/\d{2}\/\d{4}\s*\d{2}:\d{2}:\d{2}/gi,
      "",
    );

    cleanText = cleanText.replace(
      /Page\s*\d+\s*IT\s*Support\s*:\s*NIC\s*Kerala\s*\d{2}\/\d{2}\/\d{4}(?:\s*\d{2}:\d{2}:\d{2})?/gi,
      "",
    );

    const startPoint = "for the tickets ending with the following numbers";

    const endPoint =
      "the prize winners are advised to verify the winning numbers with the results published in the kerala";

    const lowerText = cleanText.toLowerCase();

    const startIndex = lowerText.indexOf(startPoint);
    const endIndex = lowerText.indexOf(endPoint);

    if (startIndex !== -1) {
      const start = startIndex + startPoint.length;

      if (endIndex !== -1 && endIndex > start) {
        extractedSection = cleanText.substring(start, endIndex).trim();
      } else {
        extractedSection = cleanText.substring(start).trim();
      }
    }
  }

  return extractedSection.replace(/\s+/g, " ").trim();
}

async function auditDatabase(
  databaseName,
  model,
  serialNumber,
  expectedPrizeNumbers,
) {
  const doc = await model.findOne({ serialNumber }).lean();

  if (!doc) {
    return {
      status: "MISSING_RECORD",
      databaseName,
    };
  }

  const actualPrizeNumbers = {};

  for (const series of doc.series || []) {
    actualPrizeNumbers[Number(series.prize)] = (series.numbers || []).map(
      (item) => item.number,
    );
  }

  const prizeResults = {};

  const allPrizeAmounts = new Set([
    ...Object.keys(expectedPrizeNumbers).map(Number),
    ...Object.keys(actualPrizeNumbers).map(Number),
  ]);

  for (const prize of [...allPrizeAmounts].sort((a, b) => b - a)) {
    const expected = expectedPrizeNumbers[prize] || [];
    const actual = actualPrizeNumbers[prize] || [];

    prizeResults[prize] = compareArrays(expected, actual);
  }

  const mismatches = Object.entries(prizeResults).filter(
    ([, result]) => !result.match,
  );

  return {
    status: mismatches.length === 0 ? "MATCH" : "MISMATCH",
    databaseName,
    prizeResults,
  };
}

async function main() {
  console.log("==============================================");
  console.log("PDF → MongoDB INTEGRITY AUDIT");
  console.log("==============================================");

  console.log(`PDF directory: ${FILES_DIR}`);

  const files = fs
    .readdirSync(FILES_DIR)
    .filter((file) => file.toLowerCase().endsWith(".pdf"))
    .sort();

  console.log(`PDF files found: ${files.length}`);

  await mongoose.connect("mongodb://localhost:27017/numbergrid");

  console.log("MongoDB connected.\n");

  const summary = {
    pdfs: files.length,
    processed: 0,
    metadataErrors: 0,
    extractionErrors: 0,

    database: {
      LotteryData: {
        checked: 0,
        matched: 0,
        mismatched: 0,
        missing: 0,
      },
      LotteryDataNew: {
        checked: 0,
        matched: 0,
        mismatched: 0,
        missing: 0,
      },
      FullLotteryData: {
        checked: 0,
        matched: 0,
        mismatched: 0,
        missing: 0,
      },
      AbsoluteData: {
        checked: 0,
        matched: 0,
        mismatched: 0,
        missing: 0,
      },
    },

    collisions: [],
    mismatches: [],
  };

  for (let index = 0; index < files.length; index++) {
    const fileName = files[index];

    try {
      const filePath = path.join(FILES_DIR, fileName);
      const buffer = fs.readFileSync(filePath);

      const pdf = await PdfParse(buffer);
      const text = pdf.text || "";

      const serialNumber = extractSerialNumber(text);
      const date = extractDateFromText(text);

      if (serialNumber === "Unknown" || date === "Unknown") {
        summary.metadataErrors++;

        console.log(`[${index + 1}/${files.length}] ❌ METADATA ${fileName}`);

        continue;
      }

      const category = classifyLotteryCategory(serialNumber);

      const prizeSection = extractPrizeSection(text, fileName);

      if (!prizeSection) {
        summary.extractionErrors++;

        console.log(
          `[${index + 1}/${files.length}] ❌ PRIZE SECTION ${fileName}`,
        );

        continue;
      }

      const expectedPrizeNumbers = getPrizeNumbersByAmount(prizeSection);

      const prizeAmounts = Object.keys(expectedPrizeNumbers).map(Number);

      /*
       * ----------------------------------------------------------
       * COLLISION CHECK
       *
       * Example:
       *
       * Prize = 5000
       * Winning number = 5000
       *
       * This MUST be preserved.
       * ----------------------------------------------------------
       */

      for (const prize of prizeAmounts) {
        const numbers = expectedPrizeNumbers[prize] || [];

        if (numbers.includes(String(prize).padStart(4, "0"))) {
          summary.collisions.push({
            fileName,
            serialNumber,
            category,
            prize,
            number: String(prize).padStart(4, "0"),
          });
        }
      }

      const databases = expectedDatabases(category);

      for (const databaseName of Object.keys(models)) {
        const shouldExist = databases.includes(databaseName);

        const model = models[databaseName];

        const result = await auditDatabase(
          databaseName,
          model,
          serialNumber,
          shouldExist ? expectedPrizeNumbers : {},
        );

        summary.database[databaseName].checked++;

        if (!shouldExist) {
          if (result.status === "MISSING_RECORD") {
            summary.database[databaseName].matched++;
          } else {
            summary.database[databaseName].mismatched++;

            summary.mismatches.push({
              fileName,
              serialNumber,
              category,
              databaseName,
              issue: "Record exists in a database where it should be filtered",
            });
          }

          continue;
        }

        if (result.status === "MISSING_RECORD") {
          summary.database[databaseName].missing++;

          summary.mismatches.push({
            fileName,
            serialNumber,
            category,
            databaseName,
            issue: "Expected record is missing",
          });

          continue;
        }

        if (result.status === "MATCH") {
          summary.database[databaseName].matched++;
        } else {
          summary.database[databaseName].mismatched++;

          summary.mismatches.push({
            fileName,
            serialNumber,
            category,
            databaseName,
            issue: "Prize/number mismatch",
            details: result.prizeResults,
          });
        }
      }

      summary.processed++;

      if ((index + 1) % 100 === 0) {
        console.log(`Progress: ${index + 1}/${files.length}`);
      }
    } catch (error) {
      summary.extractionErrors++;

      console.error(
        `[${index + 1}/${files.length}] ❌ ${fileName}:`,
        error.message,
      );
    }
  }

  console.log("\n==============================================");
  console.log("AUDIT SUMMARY");
  console.log("==============================================");

  console.log(`PDFs:             ${summary.pdfs}`);

  console.log(`Processed:        ${summary.processed}`);

  console.log(`Metadata errors:  ${summary.metadataErrors}`);

  console.log(`Extraction errors:${summary.extractionErrors}`);

  for (const [databaseName, data] of Object.entries(summary.database)) {
    console.log(`\n${databaseName}`);
    console.log("------------------------------");
    console.log(`Checked:          ${data.checked}`);
    console.log(`Matched:          ${data.matched}`);
    console.log(`Mismatched:       ${data.mismatched}`);
    console.log(`Missing:          ${data.missing}`);
  }

  console.log("\n==============================================");
  console.log("PRIZE/NUMBER COLLISIONS");
  console.log("==============================================");

  console.log(`Collision cases found: ${summary.collisions.length}`);

  for (const collision of summary.collisions.slice(0, 50)) {
    console.log(
      `${collision.fileName} | ${collision.serialNumber} | ` +
        `${collision.category} | Prize ₹${collision.prize} | ` +
        `Number ${collision.number}`,
    );
  }

  console.log("\n==============================================");
  console.log("MISMATCHES");
  console.log("==============================================");

  console.log(`Total mismatches: ${summary.mismatches.length}`);

  for (const mismatch of summary.mismatches.slice(0, 100)) {
    console.log(JSON.stringify(mismatch, null, 2));
  }

  const outputPath = path.join(__dirname, "pdf-database-audit.json");

  fs.writeFileSync(outputPath, JSON.stringify(summary, null, 2), "utf8");

  console.log(`\nDetailed report written to: ${outputPath}`);

  await mongoose.disconnect();

  console.log("\nMongoDB disconnected.");
}

main().catch((error) => {
  console.error("\nFATAL AUDIT ERROR:");
  console.error(error);
  process.exit(1);
});
