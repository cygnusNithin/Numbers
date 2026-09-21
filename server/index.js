const express = require("express");
const mongoose = require("mongoose");
const cors = require("cors");
const { default: axios } = require("axios");
const cheerio = require("cheerio");
const multer = require("multer");
const PdfParse = require("pdf-parse");
const fs = require("fs");
const path = require("path");
const { default: Results } = require("./models/Results");
const LotteryData = require("./models/LotteryData");
const LotteryDataNew = require("./models/LotteryDataNew");
const FullLotteryData = require("./models/FullLotteryData");
const AbsoluteData = require("./models/AbsoluteData");

const { buildCycleAnalysisByDay } = require("./utils/cycleAnalysis");
const forwardCyclesRouter = require("./routes/forwardCycles");
const reverseCyclesRouter = require("./routes/reverseCycles");

// Import all helper functions
const {
  extractSerialNumber,
  getPrizeNumbersByAmount,
} = require("./utils/lotteryHelpers");

const {
  extractDateFromText,
  ddmmyyyyToUTCDate,
} = require("./utils/dateHelpers");

const FILES_DIR = path.join(__dirname, "files"); // adjust if files are elsewhere

const app = express();
app.use(cors());
app.use(express.json());

mongoose.connect("mongodb://localhost:27017/numbergrid", {
  useNewUrlParser: true,
  useUnifiedTopology: true,
});

const DataSchema = new mongoose.Schema({
  userId: String,
  date: String, // format: DD.MM.YYYY
  numbers: [
    {
      number: String,
      count: Number,
    },
  ],
  createdAt: { type: Date, default: Date.now },
});

const UserData = mongoose.model("UserData", DataSchema);

// app.get("/all", async (req, res) => {
//   try {
//     const entries = await UserData.find({});
//     const allNumbers = entries.flatMap((entry) =>
//       entry.numbers.map((n) => n.number)
//     );
//     res.json({ numbers: allNumbers });
//   } catch (err) {
//     res.status(500).json({ message: "Server error", error: err.message });
//   }
// });

app.get("/all", async (req, res) => {
  try {
    const entries = await UserData.find({}).sort({ createdAt: -1 });
    res.json({ entries }); // NOT just numbers!
  } catch (err) {
    res.status(500).json({ message: "Server error", error: err.message });
  }
});

app.get("/mainall", async (req, res) => {
  try {
    const entries = await LotteryData.find({}).sort({ createdAt: -1 });
    res.json({ entries }); // send full entries
  } catch (err) {
    res.status(500).json({ message: "Server error", error: err.message });
  }
});

app.post("/submit", async (req, res) => {
  const { userId, counts, date } = req.body;

  if (!userId || !date || !counts || Object.keys(counts).length === 0) {
    return res.status(400).json({ message: "Missing userId, date, or counts" });
  }

  const numbers = Object.entries(counts).map(([number, count]) => ({
    number,
    count,
  }));

  const data = new UserData({ userId, date, numbers });
  await data.save();

  res.json({ message: "Data saved successfully" });
});

const upload = multer({ storage: multer.memoryStorage() });

function cleanBlock(block) {
  return block
    .split("\n")
    .filter((line) => {
      return (
        !line.includes("Page") &&
        !line.includes("Department of State Lotteries") &&
        !line.match(/\d{2}\/\d{2}\/\d{4}/) && // dates
        !line.match(/\d{2}:\d{2}:\d{2}/) // times
      );
    })
    .join("\n");
}

app.post("/api/upload", upload.single("file"), async (req, res) => {
  try {
    const buffer = req.file.buffer;
    const data = await PdfParse(buffer);

    const text = data.text;
    //console.log("💣 Full: ",text);

    // robust pattern that allows spaces after /-

    // const thirdToFourth = text.match(/3rd Prize[\s\S]*?4th Prize/);
    // const fourthToFifth = text.match(/4th Prize[\s\S]*?5th Prize/);
    let block = null;

    const thirdToFourth = text.match(/3rd\s*Prize[\s\S]*?4th\s*Prize/i);
    const fourthToFifth = text.match(/4th\s*Prize[\s\S]*?5th\s*Prize/i);
    const fifthToSixth = text.match(/5th\s*Prize[\s\S]*?6th\s*Prize/i);

    if (thirdToFourth && /5000\/-/.test(thirdToFourth[0])) {
      block = thirdToFourth[0];
      console.log("🏆 Using 3rd Prize block:");
    } else if (fourthToFifth && /5000\/-/.test(fourthToFifth[0])) {
      block = fourthToFifth[0];
      console.log("🏆 Using 4th Prize block:", block);
    } else if (fifthToSixth && /5000\/-/.test(fifthToSixth[0])) {
      block = fifthToSixth[0];
      console.log("🏆 Using 5th Prize block:");
    }

    let numbers = [];

    if (block) {
      const cleanedBlock = cleanBlock(block);
      numbers = cleanedBlock.match(/\d{4}/g) || [];
      console.log("✨ Numbers:", numbers);

      //numbers = numbers.filter((n) => n !== "5000"); // filter only if needed
      const first5000Index = numbers.indexOf("5000");
      if (first5000Index !== -1) {
        numbers.splice(first5000Index, 1);
      }
    }

    console.log("🔥 Datas: ", numbers);

    // extract lottery number with optional 'th'
    let lotteryNo = "Unknown";
    const lotteryMatch = text.match(
      /LOTTERY NO\.([A-Z0-9-]+)(?:st|nd|rd|th)?/i,
    );
    if (lotteryMatch) {
      lotteryNo = lotteryMatch[1];
      lotteryNo = lotteryNo.replace(/(st|nd|rd|th)$/i, ""); // remove any ordinal suffix at the end
    }

    // Extract draw date and replace / with .
    let drawDate = "Unknown";
    const dateMatch = text.match(/held on:-\s*([0-9/]+)/i);
    if (dateMatch) {
      drawDate = dateMatch[1].replace(/\//g, ".");
    }

    console.log("🎯 Extracted Prize Numbers:", numbers);
    console.log("📝 Lottery No:", lotteryNo);
    console.log("📅 Draw Date:", drawDate);

    res.json({
      message: "Parsed PDF and extracted prize numbers.",
      lotteryNo,
      drawDate,
      numbers,
    });
  } catch (err) {
    console.error("❌ Error parsing PDF:", err);
    res.status(500).json({ error: "Failed to parse PDF" });
  }
});

app.get("/api/auto-upload", async (req, res) => {
  // try {
  //   const files = fs.readdirSync(FILES_DIR).filter((f) => f.endsWith(".pdf"));
  //   const results = [];
  //   for (const file of files) {
  //     const buffer = fs.readFileSync(path.join(FILES_DIR, file));
  //     const data = await PdfParse(buffer);
  //     const text = data.text;
  //     const thirdToFourth = text.match(/3rd\s*Prize[\s\S]*?4th\s*Prize/i);
  //     const fourthToFifth = text.match(/4th\s*Prize[\s\S]*?5th\s*Prize/i);
  //     const fifthToSixth = text.match(/5th\s*Prize[\s\S]*?6th\s*Prize/i);
  //     const sixthToSeventh = text.match(/6th\s*Prize[\s\S]*?7th\s*Prize/i);
  //     let block = null;
  //     if (thirdToFourth && /5000\/-/.test(thirdToFourth[0]))
  //       block = thirdToFourth[0];
  //     else if (fourthToFifth && /5000\/-/.test(fourthToFifth[0]))
  //       block = fourthToFifth[0];
  //     else if (fifthToSixth && /5000\/-/.test(fifthToSixth[0]))
  //       block = fifthToSixth[0];
  //     else if (sixthToSeventh && /5000\/-/.test(sixthToSeventh[0]))
  //       block = sixthToSeventh[0];
  //     let numbers = [];
  //     if (block) {
  //       const cleanedBlock = cleanBlock(block);
  //       numbers = cleanedBlock.match(/\d{4}/g) || [];
  //       numbers = numbers.filter((n) => n !== "5000"); // filter only if needed
  //     }
  //     const lotteryMatch = text.match(
  //       /LOTTERY NO\.([A-Z0-9-]+)(?:st|nd|rd|th)?/i,
  //     );
  //     let lotteryNo = lotteryMatch
  //       ? lotteryMatch[1].replace(/(st|nd|rd|th)$/i, "")
  //       : "Unknown";
  //     const dateMatch = text.match(/held on:-\s*([0-9/]+)/i);
  //     const drawDate = dateMatch ? dateMatch[1].replace(/\//g, ".") : "Unknown";
  //     const exists = await UserData.findOne({ userId: lotteryNo });
  //     results.push({
  //       file,
  //       lotteryNo,
  //       drawDate,
  //       numbers,
  //       status: exists ? "Duplicate" : "New",
  //     });
  //     // Optional: save to MongoDB if not duplicate
  //     if (!exists) {
  //       await UserData.create({
  //         userId: lotteryNo,
  //         date: drawDate,
  //         numbers: numbers.map((n) => ({ number: n, count: 1 })),
  //       });
  //     }
  //   }
  //   res.json({ results });
  // } catch (err) {
  //   console.error("Auto-upload error:", err);
  //   res.status(500).json({ error: "Failed auto-upload" });
  // }
  //new code for all lotteryresults including onam,vishu,etc..
  try {
    const folderPath = path.join(__dirname, "allfiles");
    const files = fs.readdirSync(folderPath).filter((f) => f.endsWith(".pdf"));

    let results = [];

    for (const fileName of files) {
      try {
        const filePath = path.join(folderPath, fileName);
        const buffer = fs.readFileSync(filePath);
        const data = await PdfParse(buffer);
        let text = data.text;

        let extractedSection = "";

        if (fileName.toLowerCase().startsWith("tmp")) {
          const startPhrase =
            "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";
          const endPhrase =
            "The  prize  winners  are  advised  to  verify  the  winning  numbers  with  the  results  published  in  the  Kerala  Government";

          let startIndex = text.indexOf(startPhrase);
          let endIndex = text.indexOf(endPhrase);

          if (startIndex !== -1 && endIndex !== -1) {
            extractedSection = text
              .substring(startIndex + startPhrase.length, endIndex)
              .trim();
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

          const startPoint =
            "for the tickets ending with the following numbers";
          const endPoint =
            "the prize winners are advised to verify the winning numbers with the results published in the kerala";

          let lowerText = cleanText.toLowerCase();
          let startIndex = lowerText.indexOf(startPoint);
          let endIndex = lowerText.indexOf(endPoint);

          if (startIndex !== -1 && endIndex !== -1) {
            extractedSection = cleanText
              .substring(startIndex + startPoint.length, endIndex)
              .trim();
          }
        }

        const prizeAmounts = [
          "5000",
          "3000",
          "2000",
          "1000",
          "500",
          "400",
          "300",
          "250",
          "200",
          "100",
          "50",
        ];

        const prizeNumbersByAmount = Object.fromEntries(
          prizeAmounts.map((amount) => [amount, new Set()]),
        );

        extractedSection = extractedSection.replace(/\s+/g, " ").trim();

        const dateMatch = text.match(
          /\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})\b/i,
        );
        let date = dateMatch ? dateMatch[0] : "Unknown";

        const lotteryMatch = text.match(
          /LOTTERY\s+NO\.?\s*([A-Z0-9-]+)(?:st|nd|rd|th)?/i,
        );
        let serialNumber = lotteryMatch
          ? lotteryMatch[1].trim().replace(/(st|nd|rd|th)$/i, "")
          : "Unknown";

        const normalized = normalize(extractedSection);
        let blocks;

        if (fileName.toLowerCase().startsWith("tmp")) {
          blocks = [
            normalized.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i),
            normalized.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i),
            normalized.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i),
            normalized.match(/6th\s*Prize[\s\S]*?(?=7th\s*Prize)/i),
            normalized.match(/7th\s*Prize[\s\S]*?(?=8th\s*Prize)/i) ||
              normalized.match(/7th\s*Prize[\s\S]*/i),
            normalized.match(/8th\s*Prize[\s\S]*/i),
          ].filter(Boolean);
        } else {
          blocks = [
            normalized.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i),
            normalized.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i),
            normalized.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i),
            normalized.match(/6th\s*Prize[\s\S]*?(?=7th\s*Prize)/i),
            normalized.match(/7th\s*Prize[\s\S]*?(?=8th\s*Prize)/i) ||
              normalized.match(/7th\s*Prize[\s\S]*/i),
            normalized.match(/8th\s*Prize[\s\S]*?(?=9th\s*Prize)/i) ||
              normalized.match(/8th\s*Prize[\s\S]*/i),
            normalized.match(/9th\s*Prize[\s\S]*/i),
          ].filter(Boolean);
        }

        for (const blockMatch of blocks) {
          if (!blockMatch) continue;
          const block = blockMatch[0];

          for (const amount of prizeAmounts) {
            const amountPattern = new RegExp(
              `(?:₹|Rs\\.?|\\b)\\s*${amount.replace(",", "")}\\s*/-`,
              "i",
            );

            if (amountPattern.test(block)) {
              let numbers = block.match(/\d{4}/g) || [];

              if (numbers.length === 0 && /\d{8,}/.test(block)) {
                numbers = block.replace(/[^0-9]/g, "").match(/.{1,4}/g) || [];
              }

              numbers = numbers.map((n) => n.padStart(4, "0"));

              const paddedAmount = amount.padStart(4, "0");
              const index = numbers.indexOf(paddedAmount);

              if (index !== -1) numbers.splice(index, 1);

              numbers.forEach((num) => prizeNumbersByAmount[amount].add(num));
            }
          }
        }

        const result = {};
        for (const amount in prizeNumbersByAmount) {
          const nums = Array.from(prizeNumbersByAmount[amount]);
          if (nums.length > 0) {
            result[amount] = nums;
          }
        }

        const seriesArray = Object.entries(result).map(([prize, numbers]) => ({
          prize: Number(prize),
          numbers: numbers.map((num) => ({
            number: num,
            count: 1,
          })),
        }));

        if (seriesArray.length === 0) {
          console.warn(
            `⚠️ Skipping ${fileName} (${serialNumber}) → No prize categories found`,
          );
          results.push({
            fileName,
            serialNumber,
            date,
            status: "Skipped",
            reason: "No prize categories found",
          });
          continue;
        }

        const exists = await LotteryDataNew.findOne({ serialNumber });

        if (exists) {
          console.log(`🚫 Duplicate entry for ${serialNumber}`);
          results.push({ fileName, serialNumber, date, status: "Duplicate" });
        } else {
          const newLotteryData = new LotteryDataNew({
            serialNumber,
            date,
            series: seriesArray,
          });

          await newLotteryData.save();

          console.log(`✅ Saved ${serialNumber}`);
          results.push({
            fileName,
            serialNumber,
            date,
            series: seriesArray,
            status: "Saved",
          });
        }
      } catch (err) {
        console.error(`❌ Error processing ${fileName}:`, err);
        results.push({ fileName, error: err.message });
      }
    }

    res.json({ summary: results });
  } catch (err) {
    console.error("❌ Error reading folder:", err);
    res.status(500).json({ error: "Failed to process folder" });
  }
});

app.get("/api/test", (req, res) => {
  res.send("API is working");
});

app.get("/api/results", async (req, res) => {
  const results = await Results.find();
  res.json(results);
});

app.post("/api/check-userid", async (req, res) => {
  try {
    const { userId } = req.body;
    if (!userId) return res.status(400).json({ error: "Missing userId" });

    const exists = await UserData.findOne({ userId });

    res.json({ exists: !!exists });
  } catch (err) {
    console.error("Error checking userId:", err);
    res.status(500).json({ error: "Internal server error" });
  }
});

app.listen(5000, () => {
  console.log("Server running on http://localhost:5000");
});

// app.post("/api/old-upload", upload.single("file"), async (req, res) => {
//   try {
//     const buffer = req.file.buffer;
//     const data = await PdfParse(buffer);

//     const text = data.text;

//     let block = null;

//     const thirdToFourth = text.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i);
//     const fourthToFifth = text.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i);
//     const fifthToSixth = text.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i);

//     if (thirdToFourth && /5,?0{3}\/-/.test(thirdToFourth[0])) {
//       block = thirdToFourth[0];
//       console.log("🏆 Using 3rd Prize block");
//     } else if (fourthToFifth && /5,?0{3}\/-/.test(fourthToFifth[0])) {
//       block = fourthToFifth[0];
//       console.log("🏆 Using 4th Prize block");
//     } else if (fifthToSixth && /5,?0{3}\/-/.test(fifthToSixth[0])) {
//       block = fifthToSixth[0];
//       console.log("🏆 Using 5th Prize block");
//     }

//     // Step 2: Extract numbers (remove 5000 if present as number)
//     let numbers = [];
//     if (block) {
//       const cleanedBlock = block.replace(/[^\d\s]/g, " "); // Remove non-digit/non-space
//       numbers = cleanedBlock.match(/\d{4,4}/g) || []; // Extract 4 digit numbers

//       // If "5000" appears as a number, remove only the first occurrence
//       const index = numbers.indexOf("5000");
//       if (index !== -1) numbers.splice(index, 1);

//       // Pad numbers to 4 digits
//       numbers = numbers.map((num) => num.padStart(4, "0"));
//     }
//     res.json({ numbers });
//     console.log("Extracted Numbers:", numbers);
//   } catch (err) {
//     console.error("❌ Error parsing PDF:", err);
//     res.status(500).json({ error: "Failed to parse PDF" });
//   }
// });

function normalize(text) {
  return text
    .replace(/\r?\n|\r/g, " ") // remove all line breaks
    .replace(/\s+/g, " ") // collapse multiple spaces
    .replace(/\u00A0/g, " ") // replace non-breaking spaces
    .replace(/,|\./g, "") // remove commas/dots in numbers
    .replace(/\s*-\s*/g, "-") // normalize dash spacing
    .trim();
}

app.post("/api/old-upload", upload.single("file"), async (req, res) => {
  try {
    const fileName = req.file.originalname;
    const buffer = req.file.buffer;
    const data = await PdfParse(buffer);
    let text = data.text;

    //console.log("Name: ", fileName);

    let extractedSection = "";

    if (fileName.toLowerCase().startsWith("tmp")) {
      const startPhrase = "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";
      const endPhrase =
        "The  prize  winners  are  advised  to  verify  the  winning  numbers  with  the  results  published  in  the  Kerala  Government";

      let startIndex = text.indexOf(startPhrase);
      let endIndex = text.indexOf(endPhrase);

      if (startIndex !== -1 && endIndex !== -1) {
        extractedSection = text
          .substring(startIndex + startPhrase.length, endIndex)
          .trim();
      }

      //console.log("OLD: ", extractedSection);
    } else {
      // 1️⃣ Normalize spacing and newlines
      //console.log("Basic Text:", text);

      let cleanText = text
        .replace(/\s+/g, " ")
        .replace(/\u0000/g, "")
        .trim();

      // 2️⃣ Remove unwanted repeated "Page x Modernization..." lines
      cleanText = cleanText.replace(
        /Page\s*\d+\s*Modernization\s*&\s*IT\s*Software\s*Division\s*:\s*Department\s*of\s*State\s*Lotteries\s*\d{2}\/\d{2}\/\d{4}\s*\d{2}:\d{2}:\d{2}/gi,
        "",
      );

      // 3️⃣ Remove unwanted repeated "Page x IT Support : NIC Kerala" lines
      // Remove any footer starting with "Page" and ending with a date (with or without time)
      cleanText = cleanText.replace(
        /Page\s*\d+\s*IT\s*Support\s*:\s*NIC\s*Kerala\s*\d{2}\/\d{2}\/\d{4}(?:\s*\d{2}:\d{2}:\d{2})?/gi,
        "",
      );

      // 4️⃣ Define start and end markers (lowercased for safety)
      const startPoint = "for the tickets ending with the following numbers";
      const endPoint =
        "the prize winners are advised to verify the winning numbers with the results published in the kerala";

      // 5️⃣ Find indexes
      let lowerText = cleanText.toLowerCase();
      let startIndex = lowerText.indexOf(startPoint);
      let endIndex = lowerText.indexOf(endPoint);

      if (startIndex !== -1 && endIndex !== -1) {
        extractedSection = cleanText
          .substring(startIndex + startPoint.length, endIndex) // skip startPoint text
          .trim();
      }
    }
    //console.log("🔥 DATA:", extractedSection);

    const prizeAmounts = ["5000", "2000", "1000", "500", "200", "100"];
    const prizeNumbersByAmount = {
      5000: new Set(),
      2000: new Set(),
      1000: new Set(),
      500: new Set(),
      200: new Set(),
      100: new Set(),
    };
    extractedSection = extractedSection.replace(/\s+/g, " ").trim();

    const dateMatch = text.match(
      /\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})\b/i,
    );

    //let cleanedText = extractedSection;
    const normalized = normalize(extractedSection);

    //console.log("Datas: ", normalized);

    let date = "";
    if (dateMatch) {
      date = dateMatch[0];
      //console.log("📅 Date Found:", Date);
    } else {
      console.log("❌ No date found in PDF text.");
    }

    const lotteryMatch = text.match(
      /LOTTERY\s+NO\.?\s*([A-Z0-9-]+)(?:st|nd|rd|th)?/i,
    );

    let serialNumber = lotteryMatch
      ? lotteryMatch[1].trim().replace(/(st|nd|rd|th)$/i, "")
      : "Unknown";

    //console.log("serialNumber:", serialNumber);

    let blocks;

    if (fileName.toLowerCase().startsWith("tmp")) {
      // For TMP files — last prize could be 7th or 8th
      blocks = [
        normalized.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i),
        normalized.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i),
        normalized.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i),
        normalized.match(/6th\s*Prize[\s\S]*?(?=7th\s*Prize)/i),
        // Try 7th prize first; if it's the last block, capture till the end
        normalized.match(/7th\s*Prize[\s\S]*?(?=8th\s*Prize)/i) ||
          normalized.match(/7th\s*Prize[\s\S]*/i),
        // Try 8th prize only if it exists
        normalized.match(/8th\s*Prize[\s\S]*/i),
      ].filter(Boolean); // Remove null matches
    } else {
      // For normal files — last block is 9th prize
      blocks = [
        normalized.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i),
        normalized.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i),
        normalized.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i),
        normalized.match(/6th\s*Prize[\s\S]*?(?=7th\s*Prize)/i),
        normalized.match(/7th\s*Prize[\s\S]*?(?=8th\s*Prize)/i) ||
          normalized.match(/7th\s*Prize[\s\S]*/i),
        normalized.match(/8th\s*Prize[\s\S]*?(?=9th\s*Prize)/i) ||
          normalized.match(/8th\s*Prize[\s\S]*/i),
        normalized.match(/9th\s*Prize[\s\S]*/i),
      ].filter(Boolean);
    }

    //set creation
    for (const blockMatch of blocks) {
      if (!blockMatch) continue;

      const block = blockMatch[0];

      for (const amount of prizeAmounts) {
        // Match formats like 5,000/-, 5000/-, ₹5000 etc.
        const amountPattern = new RegExp(
          `(?:₹|Rs\\.?|\\b)\\s*${amount.replace(",", "")}\\s*/-`,
          "i",
        );
        if (amountPattern.test(block)) {
          // Try to extract spaced numbers first
          let numbers = block.match(/\d{4}/g) || [];

          // If the block looks like one long glued string (no spaces, very long length)
          if (numbers.length === 0 && /\d{8,}/.test(block)) {
            // Force split into groups of 4
            numbers = block.replace(/[^0-9]/g, "").match(/.{1,4}/g) || [];
          }

          // Clean & pad
          numbers = numbers.map((n) => n.padStart(4, "0"));

          // Filter out false matches like the prize amount itself
          const paddedAmount = amount.padStart(4, "0");
          const index = numbers.indexOf(paddedAmount);
          if (index !== -1) numbers.splice(index, 1);

          // Add to set
          numbers.forEach((num) => prizeNumbersByAmount[amount].add(num));
        }
      }
    }

    // Convert sets to arrays
    const result = {};
    let allNumbers = [];
    for (const amount in prizeNumbersByAmount) {
      result[amount] = Array.from(prizeNumbersByAmount[amount]);
      allNumbers = allNumbers.concat(result[amount]);
    }

    // Sort all numbers
    allNumbers.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

    // Detect duplicates in final extracted numbers
    const duplicates = allNumbers.filter(
      (item, index) => allNumbers.indexOf(item) !== index,
    );
    //console.log("Total numbers extracted:", allNumbers.length);
    //console.log("Duplicate numbers found:", [...new Set(duplicates)]);
    //console.log("Sorted numbers:", allNumbers);
    //console.log("🏆 Extracted Numbers by Prize Amount:", result);

    // Convert result into schema structure
    const seriesArray = Object.entries(result).map(([prize, numbers]) => ({
      prize: Number(prize),
      numbers: numbers.map((num) => ({
        number: num,
        count: 1, // since Set has unique numbers, count is 1
      })),
    }));
    // ✅ Check essential prizes
    const requiredPrizes = ["5000", "1000", "500", "100"];
    for (const prize of requiredPrizes) {
      if (!result[prize] || result[prize].length === 0) {
        console.warn(
          `⚠️ Skipping ${fileName} (${serialNumber}) → Missing prize ${prize}`,
        );
        return res.json({
          status: "Skipped",
          reason: `Missing prize ${prize}`,
          serialNumber,
          date,
        });
      }
    }
    //Check duplication
    const exists = await LotteryData.findOne({ serialNumber });
    if (exists) {
      console.log(`🚫 Duplicate entry found for SerialNumber: ${serialNumber}`);
      return res.json({
        status: "Duplicate",
        serialNumber,
        date,
        series: seriesArray,
      });
    }
    // Create a new entry
    const newLotteryData = new LotteryData({
      serialNumber,
      date,
      series: seriesArray,
    });

    // Save to MongoDB
    // newLotteryData
    //   .save()
    //   .then((saved) => console.log("Saved:", saved))
    //   .catch((err) => console.error("Error:", err));

    res.json({ extracted: result }); //, sort: allNumbers
  } catch (err) {
    console.error("❌ Error parsing PDF:", err);
    res.status(500).json({ error: "Failed to parse PDF" });
  }
});

app.get("/api/all-upload-folder", async (req, res) => {
  try {
    const folderPath = path.join(__dirname, "files"); // your folder containing PDFs
    const files = fs.readdirSync(folderPath).filter((f) => f.endsWith(".pdf"));

    let results = [];

    for (const fileName of files) {
      try {
        const filePath = path.join(folderPath, fileName);
        const buffer = fs.readFileSync(filePath);
        const data = await PdfParse(buffer);
        let text = data.text;

        // --- SAME EXTRACTION LOGIC ---
        let extractedSection = "";

        if (fileName.toLowerCase().startsWith("tmp")) {
          const startPhrase =
            "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";
          const endPhrase =
            "The  prize  winners  are  advised  to  verify  the  winning  numbers  with  the  results  published  in  the  Kerala  Government";

          let startIndex = text.indexOf(startPhrase);
          let endIndex = text.indexOf(endPhrase);

          if (startIndex !== -1 && endIndex !== -1) {
            extractedSection = text
              .substring(startIndex + startPhrase.length, endIndex)
              .trim();
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

          const startPoint =
            "for the tickets ending with the following numbers";
          const endPoint =
            "the prize winners are advised to verify the winning numbers with the results published in the kerala";

          let lowerText = cleanText.toLowerCase();
          let startIndex = lowerText.indexOf(startPoint);
          let endIndex = lowerText.indexOf(endPoint);

          if (startIndex !== -1 && endIndex !== -1) {
            extractedSection = cleanText
              .substring(startIndex + startPoint.length, endIndex)
              .trim();
          }
        }

        // Prize extraction setup
        const prizeAmounts = ["5000", "2000", "1000", "500", "200", "100"];
        const prizeNumbersByAmount = {
          5000: new Set(),
          2000: new Set(),
          1000: new Set(),
          500: new Set(),
          200: new Set(),
          100: new Set(),
        };
        extractedSection = extractedSection.replace(/\s+/g, " ").trim();

        // Date extraction
        const dateMatch = text.match(
          /\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})\b/i,
        );
        let date = dateMatch ? dateMatch[0] : "Unknown";

        // Serial number
        const lotteryMatch = text.match(
          /LOTTERY\s+NO\.?\s*([A-Z0-9-]+)(?:st|nd|rd|th)?/i,
        );
        let serialNumber = lotteryMatch
          ? lotteryMatch[1].trim().replace(/(st|nd|rd|th)$/i, "")
          : "Unknown";

        // Blocks
        const normalized = normalize(extractedSection);
        let blocks;
        if (fileName.toLowerCase().startsWith("tmp")) {
          blocks = [
            normalized.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i),
            normalized.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i),
            normalized.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i),
            normalized.match(/6th\s*Prize[\s\S]*?(?=7th\s*Prize)/i),
            normalized.match(/7th\s*Prize[\s\S]*?(?=8th\s*Prize)/i) ||
              normalized.match(/7th\s*Prize[\s\S]*/i),
            normalized.match(/8th\s*Prize[\s\S]*/i),
          ].filter(Boolean);
        } else {
          blocks = [
            normalized.match(/3rd\s*Prize[\s\S]*?(?=4th\s*Prize)/i),
            normalized.match(/4th\s*Prize[\s\S]*?(?=5th\s*Prize)/i),
            normalized.match(/5th\s*Prize[\s\S]*?(?=6th\s*Prize)/i),
            normalized.match(/6th\s*Prize[\s\S]*?(?=7th\s*Prize)/i),
            normalized.match(/7th\s*Prize[\s\S]*?(?=8th\s*Prize)/i) ||
              normalized.match(/7th\s*Prize[\s\S]*/i),
            normalized.match(/8th\s*Prize[\s\S]*?(?=9th\s*Prize)/i) ||
              normalized.match(/8th\s*Prize[\s\S]*/i),
            normalized.match(/9th\s*Prize[\s\S]*/i),
          ].filter(Boolean);
        }

        for (const blockMatch of blocks) {
          if (!blockMatch) continue;
          const block = blockMatch[0];

          for (const amount of prizeAmounts) {
            const amountPattern = new RegExp(
              `(?:₹|Rs\\.?|\\b)\\s*${amount.replace(",", "")}\\s*/-`,
              "i",
            );
            if (amountPattern.test(block)) {
              let numbers = block.match(/\d{4}/g) || [];
              if (numbers.length === 0 && /\d{8,}/.test(block)) {
                numbers = block.replace(/[^0-9]/g, "").match(/.{1,4}/g) || [];
              }
              numbers = numbers.map((n) => n.padStart(4, "0"));
              const paddedAmount = amount.padStart(4, "0");
              const index = numbers.indexOf(paddedAmount);
              if (index !== -1) numbers.splice(index, 1);
              numbers.forEach((num) => prizeNumbersByAmount[amount].add(num));
            }
          }
        }

        // Final results
        const result = {};
        for (const amount in prizeNumbersByAmount) {
          result[amount] = Array.from(prizeNumbersByAmount[amount]);
        }

        const seriesArray = Object.entries(result).map(([prize, numbers]) => ({
          prize: Number(prize),
          numbers: numbers.map((num) => ({
            number: num,
            count: 1,
          })),
        }));

        // ✅ Check essential prizes
        const requiredPrizes = ["5000", "1000", "500", "100"];
        let missing = requiredPrizes.find(
          (p) => !result[p] || result[p].length === 0,
        );
        if (missing) {
          console.warn(
            `⚠️ Skipping ${fileName} (${serialNumber}) → Missing ${missing}`,
          );
          results.push({
            fileName,
            serialNumber,
            date,
            status: "Skipped",
            reason: `Missing prize ${missing}`,
          });
          continue;
        }

        // Check duplication before saving
        const exists = await LotteryData.findOne({ serialNumber });
        if (exists) {
          console.log(`🚫 Duplicate entry for ${serialNumber}`);
          results.push({ fileName, serialNumber, date, status: "Duplicate" });
        } else {
          const newLotteryData = new LotteryData({
            serialNumber,
            date,
            series: seriesArray,
          });
          await newLotteryData.save();
          console.log(`✅ Saved ${serialNumber}`);
          results.push({
            fileName,
            serialNumber,
            date,
            series: seriesArray,
            status: "Saved",
          });
        }
      } catch (err) {
        console.error(`❌ Error processing ${fileName}:`, err);
        results.push({ fileName, error: err.message });
      }
    }

    res.json({ summary: results });
  } catch (err) {
    console.error("❌ Error reading folder:", err);
    res.status(500).json({ error: "Failed to process folder" });
  }
});

// Add this to your server file (index.js or wherever you have your Express routes)

// Pattern Analysis Endpoint
app.get("/api/pattern-analysis", async (req, res) => {
  try {
    // Read the CSV file
    const csvPath = path.join(__dirname, "all_prizes_number_patterns30.csv");

    if (!fs.existsSync(csvPath)) {
      return res.status(404).json({ error: "CSV file not found" });
    }

    const csvContent = fs.readFileSync(csvPath, "utf-8");
    const lines = csvContent.trim().split("\n");
    const headers = lines[0].split(",");

    const data = lines.slice(1).map((line) => {
      const values = line.split(",");
      return {
        number: values[0],
        total_hits: parseInt(values[1]) || 0,
        dates: values[2] || "",
        avg_gap_days: parseFloat(values[3]) || 0,
        weekday_counts: values[4] || "{}",
        month_counts: values[5] || "{}",
        remaining_to_max: parseInt(values[6]) || 0,
      };
    });

    // Analyze each number
    const analyzed = data.map((row) => {
      // Parse dates and prizes
      const entries = row.dates
        .split("|")
        .map((entry) => {
          const match = entry.match(/(\d{2}\/\d{2}\/\d{4})\(([^)]+)\)/);
          if (!match) return null;
          const [, dateStr, prizesStr] = match;
          const prizes = prizesStr.split(",").map(Number);
          const [day, month, year] = dateStr.split("/").map(Number);
          return {
            date: new Date(year, month - 1, day),
            dateStr,
            prizes,
          };
        })
        .filter(Boolean);

      // Prize tier counts
      const tierCounts = { 5000: 0, 2000: 0, 1000: 0, 500: 0, 200: 0, 100: 0 };
      entries.forEach((e) => {
        e.prizes.forEach((p) => {
          if (tierCounts[p] !== undefined) tierCounts[p]++;
        });
      });

      // Recent momentum (last 6 months)
      const sixMonthsAgo = new Date();
      sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
      const recentEntries = entries.filter((e) => e.date >= sixMonthsAgo);
      const recentHighTier = recentEntries.filter((e) =>
        e.prizes.some((p) => p >= 1000),
      ).length;

      // Last appearance
      const lastEntry = entries.length > 0 ? entries[entries.length - 1] : null;
      const daysSinceLastHit = lastEntry
        ? Math.floor((new Date() - lastEntry.date) / (1000 * 60 * 60 * 24))
        : 999;

      // Calculate pattern score
      let score = 0;
      const factors = [];

      // High tier frequency (30 points)
      const highTierHits =
        tierCounts[5000] + tierCounts[2000] + tierCounts[1000];
      if (highTierHits >= 15) {
        score += 30;
        factors.push("Elite high-tier performer (15+)");
      } else if (highTierHits >= 10) {
        score += 25;
        factors.push("Strong high-tier history (10-14)");
      } else if (highTierHits >= 5) {
        score += 15;
        factors.push("Moderate high-tier presence (5-9)");
      }

      // Recent momentum (25 points)
      if (recentHighTier >= 3) {
        score += 25;
        factors.push("Hot streak (3+ high-tier in 6mo)");
      } else if (recentHighTier >= 2) {
        score += 20;
        factors.push("Active high-tier momentum (2)");
      } else if (recentEntries.length >= 5) {
        score += 10;
        factors.push("Frequent recent appearances");
      }

      // Gap overdue (20 points)
      const overdueRatio =
        row.avg_gap_days > 0 ? daysSinceLastHit / row.avg_gap_days : 0;
      if (overdueRatio >= 2) {
        score += 20;
        factors.push(`Severely overdue (${overdueRatio.toFixed(1)}x avg gap)`);
      } else if (overdueRatio >= 1.5) {
        score += 15;
        factors.push(`Overdue (${overdueRatio.toFixed(1)}x avg gap)`);
      } else if (overdueRatio >= 1.2) {
        score += 10;
        factors.push(`Slightly overdue (${overdueRatio.toFixed(1)}x)`);
      }

      // Tier progression (15 points)
      if (tierCounts[100] >= 20 && tierCounts[5000] >= 3) {
        score += 15;
        factors.push("Proven 100→5000 progression");
      } else if (tierCounts[500] >= 10 && tierCounts[1000] >= 2) {
        score += 10;
        factors.push("500→1000 progression pattern");
      }

      // Consistency (10 points)
      if (row.total_hits >= 80 && row.avg_gap_days < 25) {
        score += 10;
        factors.push("Ultra-consistent (<25d gap, 80+ hits)");
      } else if (row.total_hits >= 50 && row.avg_gap_days < 35) {
        score += 7;
        factors.push("Very consistent performer");
      }

      return {
        number: row.number,
        score,
        total_hits: row.total_hits,
        avg_gap_days: row.avg_gap_days,
        days_since_last: daysSinceLastHit,
        overdue_ratio: overdueRatio,
        tier_5000: tierCounts[5000],
        tier_2000: tierCounts[2000],
        tier_1000: tierCounts[1000],
        tier_500: tierCounts[500],
        tier_200: tierCounts[200],
        tier_100: tierCounts[100],
        high_tier_total: highTierHits,
        recent_high_tier: recentHighTier,
        recent_total: recentEntries.length,
        factors,
        last_date: lastEntry ? lastEntry.dateStr : "N/A",
      };
    });

    // Sort by score
    analyzed.sort((a, b) => b.score - a.score);

    // Statistics
    const stats = {
      total_numbers: analyzed.length,
      avg_score: (
        analyzed.reduce((sum, d) => sum + d.score, 0) / analyzed.length
      ).toFixed(2),
      high_score_count: analyzed.filter((d) => d.score >= 70).length,
      hot_numbers: analyzed.filter((d) => d.recent_high_tier >= 2).length,
      overdue_numbers: analyzed.filter((d) => d.overdue_ratio >= 1.5).length,
      elite_performers: analyzed.filter((d) => d.high_tier_total >= 10).length,
    };

    res.json({
      analyzed,
      stats,
    });
  } catch (err) {
    console.error("Error in pattern analysis:", err);
    res.status(500).json({ error: "Failed to analyze patterns" });
  }
});

// Add this to your Express server (index.js)

// Prediction endpoint
app.get("/api/predictions", async (req, res) => {
  try {
    const csvPath = path.join(__dirname, "all_prizes_number_patterns30.csv");

    if (!fs.existsSync(csvPath)) {
      return res.status(404).json({ error: "CSV file not found" });
    }

    const csvContent = fs.readFileSync(csvPath, "utf-8");
    const lines = csvContent.trim().split("\n");

    const data = lines.slice(1).map((line) => {
      // The dates field can contain commas inside JSON, so split carefully:
      // columns: number, total_hits, dates, avg_gap_days, weekday_counts, month_counts, remaining_to_max
      // Dates field is pipe-separated and never contains commas, so a naive split works
      // BUT weekday_counts / month_counts are JSON with commas — split on first 3 commas,
      // then rejoin the rest carefully.
      const firstComma = line.indexOf(",");
      const secondComma = line.indexOf(",", firstComma + 1);
      const thirdComma = line.indexOf(",", secondComma + 1);

      // avg_gap_days ends at next comma after dates
      // Find the closing pipe before the first "{" for the JSON block
      const jsonStart = line.indexOf(',"{"');
      // The segment before jsonStart: number, total_hits, dates, avg_gap_days
      const preJson = line.slice(0, jsonStart).split(",");
      const number = preJson[0];
      const totalHits = parseInt(preJson[1]) || 0;
      const dates = preJson.slice(2, preJson.length - 1).join(","); // dates (safe, no commas)
      const avgGap = parseFloat(preJson[preJson.length - 1]) || 0;

      // JSON tail: `,"{"weekday..."}","{"month..."}",remaining`
      const jsonTail = line.slice(jsonStart + 1); // starts with "{"Friday"...
      // Split: two JSON objects followed by a trailing number
      // Use a regex to extract both JSON blobs
      const jsonMatches = jsonTail.match(/(\{[^}]+\})/g) || [];
      const weekdayCounts = jsonMatches[0] || "{}";
      const monthCounts = jsonMatches[1] || "{}";
      const remaining = parseInt(line.split(",").pop()) || 0;

      return {
        number,
        total_hits: totalHits,
        dates,
        avg_gap_days: avgGap,
        weekday_counts: weekdayCounts,
        month_counts: monthCounts,
        remaining,
      };
    });

    const REFERENCE_DATE = new Date();

    // ── Weight table ─────────────────────────────────────────────
    const WEIGHTS = {
      gap_based: 0.2,
      frequency: 0.15,
      hot_streak: 0.15,
      tier_progression: 0.15,
      seasonality: 0.1,
      markov_chain: 0.15, // NEW Phase 2
      moving_average: 0.1, // NEW Phase 2
    };

    // ── Parse dates helper ────────────────────────────────────────
    const parseDates = (dateString) =>
      dateString
        .split("|")
        .map((entry) => {
          const match = entry.match(/(\d{2}\/\d{2}\/\d{4})\(([^)]+)\)/);
          if (!match) return null;
          const [, dateStr, prizesStr] = match;
          const prizes = prizesStr.split(",").map(Number);
          const [day, month, year] = dateStr.split("/").map(Number);
          return { date: new Date(year, month - 1, day), dateStr, prizes };
        })
        .filter(Boolean);

    const getTierCounts = (entries) => {
      const t = { 5000: 0, 2000: 0, 1000: 0, 500: 0, 200: 0, 100: 0 };
      entries.forEach((e) =>
        e.prizes.forEach((p) => {
          if (t[p] !== undefined) t[p]++;
        }),
      );
      return t;
    };

    const maxHits = Math.max(...data.map((d) => d.total_hits));
    const PRIZE_TIERS = [5000, 2000, 1000, 500, 200, 100];

    // ── Build GLOBAL Markov transition matrix ─────────────────────
    // For each number's sequence of prize appearances, tally
    // tier → tier transitions.  This tells us: given that a number
    // last appeared at tier X, what tier is it most likely to appear
    // at next?
    //
    // transition[fromTier][toTier] = count
    const transitionCounts = {};
    const transitionTotals = {};

    PRIZE_TIERS.forEach((t) => {
      transitionCounts[t] = {};
      transitionTotals[t] = 0;
      PRIZE_TIERS.forEach((t2) => {
        transitionCounts[t][t2] = 0;
      });
    });

    data.forEach(({ dates }) => {
      const entries = parseDates(dates);
      for (let i = 1; i < entries.length; i++) {
        const fromTier = entries[i - 1].prizes[0]; // use first prize of each appearance
        const toTier = entries[i].prizes[0];
        if (
          transitionCounts[fromTier] &&
          transitionCounts[fromTier][toTier] !== undefined
        ) {
          transitionCounts[fromTier][toTier]++;
          transitionTotals[fromTier]++;
        }
      }
    });

    // Convert to probabilities: P(toTier | fromTier)
    const transitionProb = {};
    PRIZE_TIERS.forEach((from) => {
      transitionProb[from] = {};
      PRIZE_TIERS.forEach((to) => {
        const total = transitionTotals[from] || 1;
        transitionProb[from][to] = transitionCounts[from][to] / total;
      });
    });

    // High-value score: weighted probability of landing on 1000+ tier next
    const markovHighValueScore = (lastPrize) => {
      if (!transitionProb[lastPrize]) return 50;
      const p5000 = transitionProb[lastPrize][5000] || 0;
      const p2000 = transitionProb[lastPrize][2000] || 0;
      const p1000 = transitionProb[lastPrize][1000] || 0;
      // Weighted by prize magnitude
      return Math.min(100, (p5000 * 100 + p2000 * 60 + p1000 * 40) * 3);
    };

    // ── Analyse each number ──────────────────────────────────────
    const predictions = data.map((row) => {
      const entries = parseDates(row.dates);
      const tierCounts = getTierCounts(entries);

      // Time windows
      const now = REFERENCE_DATE;
      const d7Ago = new Date(now);
      d7Ago.setDate(d7Ago.getDate() - 7);
      const d30Ago = new Date(now);
      d30Ago.setDate(d30Ago.getDate() - 30);
      const d90Ago = new Date(now);
      d90Ago.setDate(d90Ago.getDate() - 90);
      const d6mAgo = new Date(now);
      d6mAgo.setMonth(d6mAgo.getMonth() - 6);

      const entries7d = entries.filter((e) => e.date >= d7Ago);
      const entries30d = entries.filter((e) => e.date >= d30Ago);
      const entries90d = entries.filter((e) => e.date >= d90Ago);
      const recentEntries = entries.filter((e) => e.date >= d6mAgo);
      const recentHighTier = recentEntries.filter((e) =>
        e.prizes.some((p) => p >= 1000),
      ).length;

      // Last appearance
      const lastEntry = entries.length > 0 ? entries[entries.length - 1] : null;
      const lastPrize = lastEntry ? lastEntry.prizes[0] : 100;
      const daysSince = lastEntry
        ? Math.floor((now - lastEntry.date) / 86400000)
        : 999;
      const overdueRatio =
        row.avg_gap_days > 0 ? daysSince / row.avg_gap_days : 0;

      // ── Method 1: Gap-Based ──────────────────────────────────
      let gapScore = 20;
      if (overdueRatio >= 2.0) gapScore = 100;
      else if (overdueRatio >= 1.5) gapScore = 85;
      else if (overdueRatio >= 1.2) gapScore = 70;
      else if (overdueRatio >= 1.0) gapScore = 60;
      else if (overdueRatio >= 0.8) gapScore = 40;

      // ── Method 2: Frequency ──────────────────────────────────
      const weightedFreq =
        tierCounts[5000] * 10 +
        tierCounts[2000] * 7 +
        tierCounts[1000] * 5 +
        tierCounts[500] * 3 +
        tierCounts[200] * 2 +
        tierCounts[100] * 1;
      const frequencyScore = Math.min(
        100,
        weightedFreq / 10 + (row.total_hits / maxHits) * 50,
      );

      // ── Method 3: Hot Streak ─────────────────────────────────
      const momentum = recentHighTier / Math.max(recentEntries.length, 1);
      const recencyBonus = daysSince < 30 ? 20 : daysSince < 60 ? 10 : 0;
      const hotStreakScore = Math.min(100, momentum * 80 + recencyBonus);

      // ── Method 4: Tier Progression ───────────────────────────
      let tierScore = 0;
      const has100 = tierCounts[100] >= 10;
      const has500 = tierCounts[500] >= 5;
      const has1000 = tierCounts[1000] >= 3;
      const has5000 = tierCounts[5000] >= 1;
      if (has100 && has500 && has1000 && has5000) tierScore = 90;
      else if (has100 && has500 && has1000) tierScore = 75;
      else if (has100 && has500) tierScore = 55;
      else if (has100) tierScore = 35;
      const highTierTotal =
        tierCounts[5000] + tierCounts[2000] + tierCounts[1000];
      if (highTierTotal >= 15) tierScore = Math.min(100, tierScore + 10);

      // ── Method 5: Seasonality ────────────────────────────────
      let seasonalityScore = 0;
      try {
        const weekdayCounts = JSON.parse(row.weekday_counts);
        const monthCounts = JSON.parse(row.month_counts);
        const curWeekday = now.toLocaleDateString("en-US", { weekday: "long" });
        const curMonth = now.toLocaleDateString("en-US", { month: "long" });
        const maxWD = Math.max(...Object.values(weekdayCounts), 1);
        const maxMon = Math.max(...Object.values(monthCounts), 1);
        seasonalityScore =
          ((weekdayCounts[curWeekday] || 0) / maxWD) * 50 +
          ((monthCounts[curMonth] || 0) / maxMon) * 50;
      } catch (_) {
        /* leave at 0 */
      }

      // ── Method 6: Markov Chain (NEW) ─────────────────────────
      // Uses the global transition matrix built above.
      // Score = how likely this number transitions to a high-value tier
      // next, given its LAST recorded prize tier.
      const markovScore = markovHighValueScore(lastPrize);

      // Bonus: if the number's own personal transition history shows
      // an escalating pattern (100→500→1000→5000), boost further.
      let personalEscalation = 0;
      for (let i = 1; i < entries.length; i++) {
        if (entries[i].prizes[0] > entries[i - 1].prizes[0])
          personalEscalation++;
      }
      const escalationRate =
        personalEscalation / Math.max(entries.length - 1, 1);
      const markovFinalScore = Math.min(100, markovScore + escalationRate * 20);

      // ── Method 7: Moving Average (NEW) ───────────────────────
      // Weighted appearance rate across 3 windows.
      // Rate = appearances / window_days  (normalised per day)
      const rate7d = entries7d.length / 7;
      const rate30d = entries30d.length / 30;
      const rate90d = entries90d.length / 90;
      // Combine: short-term weighted highest
      const combinedRate = rate7d * 0.5 + rate30d * 0.3 + rate90d * 0.2;
      // Scale to 0–100: a number appearing every day would be rate=1 → score 100
      // Typical rate is ~0.05–0.15, so multiply by 400 gives useful spread
      const movingAvgScore = Math.min(100, combinedRate * 400);

      // ── Final composite score ─────────────────────────────────
      const finalScore = Math.round(
        gapScore * WEIGHTS.gap_based +
          frequencyScore * WEIGHTS.frequency +
          hotStreakScore * WEIGHTS.hot_streak +
          tierScore * WEIGHTS.tier_progression +
          seasonalityScore * WEIGHTS.seasonality +
          markovFinalScore * WEIGHTS.markov_chain +
          movingAvgScore * WEIGHTS.moving_average,
      );

      // ── Recommendation ────────────────────────────────────────
      let recommendation;
      if (finalScore >= 80 && overdueRatio >= 1.5)
        recommendation = "STRONG BUY - Highly overdue with excellent patterns";
      else if (finalScore >= 70 && recentEntries.length >= 5)
        recommendation = "BUY - Hot streak with recent momentum";
      else if (finalScore >= 60)
        recommendation = "CONSIDER - Good fundamentals, watch closely";
      else if (finalScore >= 40)
        recommendation = "WATCH - Monitor for pattern changes";
      else recommendation = "SKIP - Better opportunities available";

      return {
        number: row.number,
        finalScore,
        scores: {
          gap_based: gapScore,
          frequency: Math.round(frequencyScore),
          hot_streak: Math.round(hotStreakScore),
          tier_progression: tierScore,
          seasonality: Math.round(seasonalityScore),
          markov_chain: Math.round(markovFinalScore), // NEW
          moving_average: Math.round(movingAvgScore), // NEW
        },
        tierCounts,
        total_hits: row.total_hits,
        avg_gap_days: row.avg_gap_days,
        days_since_last: daysSince,
        overdue_ratio: overdueRatio,
        recent_activity: recentEntries.length,
        last_date: lastEntry ? lastEntry.dateStr : "N/A",
        last_prize: lastPrize,
        recommendation,
        // Moving average details (useful for debug)
        ma_detail: {
          rate_7d: +rate7d.toFixed(4),
          rate_30d: +rate30d.toFixed(4),
          rate_90d: +rate90d.toFixed(4),
        },
      };
    });

    // Sort by final score
    predictions.sort((a, b) => b.finalScore - a.finalScore);

    // ── Categories ───────────────────────────────────────────────
    const categories = {
      top_50: predictions.slice(0, 50),
      strong_buy: predictions.filter((p) =>
        p.recommendation.startsWith("STRONG BUY"),
      ),
      buy: predictions.filter((p) => p.recommendation.startsWith("BUY")),
      overdue: predictions.filter((p) => p.overdue_ratio >= 1.5).slice(0, 50),
      hot_streak: predictions
        .filter((p) => p.recent_activity >= 5 && p.scores.hot_streak >= 70)
        .slice(0, 50),
      high_tier_potential: predictions
        .filter(
          (p) =>
            p.tierCounts[5000] >= 5 ||
            (p.tierCounts[1000] >= 5 && p.scores.tier_progression >= 70),
        )
        .slice(0, 50),
      // ── Phase 2 new views ──
      markov_top: [...predictions]
        .sort((a, b) => b.scores.markov_chain - a.scores.markov_chain)
        .slice(0, 50),
      ma_momentum: [...predictions]
        .sort((a, b) => b.scores.moving_average - a.scores.moving_average)
        .slice(0, 50),
    };

    // ── Statistics ────────────────────────────────────────────────
    const statistics = {
      total_analyzed: predictions.length,
      avg_score: (
        predictions.reduce((s, p) => s + p.finalScore, 0) / predictions.length
      ).toFixed(2),
      strong_buy_count: categories.strong_buy.length,
      buy_count: categories.buy.length,
      overdue_count: predictions.filter((p) => p.overdue_ratio >= 1.5).length,
      hot_count: predictions.filter((p) => p.recent_activity >= 5).length,
      markov_signals: predictions.filter((p) => p.scores.markov_chain >= 70)
        .length, // NEW
      ma_signals: predictions.filter((p) => p.scores.moving_average >= 70)
        .length, // NEW
      phase: 2,
    };

    res.json({
      generated_at: new Date().toISOString(),
      phase: 2,
      weights: WEIGHTS,
      statistics,
      categories,
    });
  } catch (err) {
    console.error("Prediction error:", err);
    res
      .status(500)
      .json({ error: "Failed to generate predictions", detail: err.message });
  }
});

// ── Date helpers ───────────────────────────────────────────────── Validation Code with new dates after 23/02/2026
const parseDMY = (str) => {
  // "DD/MM/YYYY" → Date
  const [d, m, y] = str.split("/").map(Number);
  return new Date(y, m - 1, d);
};

const CUTOFF_DATE = new Date(2026, 1, 23); // 23 Feb 2026 — last date in CSV

// ── Reuse prediction logic (same weights as Phase 2) ─────────────
const WEIGHTS = {
  gap_based: 0.2,
  frequency: 0.15,
  hot_streak: 0.15,
  tier_progression: 0.15,
  seasonality: 0.1,
  markov_chain: 0.15,
  moving_average: 0.1,
};

function buildPredictions(csvData) {
  const REFERENCE_DATE = CUTOFF_DATE; // predict AS OF the cutoff date

  const parseDates = (dateString) =>
    dateString
      .split("|")
      .map((entry) => {
        const match = entry.match(/(\d{2}\/\d{2}\/\d{4})\(([^)]+)\)/);
        if (!match) return null;
        const [, dateStr, prizesStr] = match;
        const prizes = prizesStr.split(",").map(Number);
        const [day, month, year] = dateStr.split("/").map(Number);
        return { date: new Date(year, month - 1, day), dateStr, prizes };
      })
      .filter(Boolean);

  const getTierCounts = (entries) => {
    const t = { 5000: 0, 2000: 0, 1000: 0, 500: 0, 200: 0, 100: 0 };
    entries.forEach((e) =>
      e.prizes.forEach((p) => {
        if (t[p] !== undefined) t[p]++;
      }),
    );
    return t;
  };

  const maxHits = Math.max(...csvData.map((d) => d.total_hits));

  // Build Markov transition matrix
  const transitionCounts = {};
  const transitionTotals = {};
  const PRIZE_TIERS = [5000, 2000, 1000, 500, 200, 100];
  PRIZE_TIERS.forEach((t) => {
    transitionCounts[t] = {};
    transitionTotals[t] = 0;
    PRIZE_TIERS.forEach((t2) => {
      transitionCounts[t][t2] = 0;
    });
  });
  csvData.forEach(({ dates }) => {
    const entries = parseDates(dates);
    for (let i = 1; i < entries.length; i++) {
      const from = entries[i - 1].prizes[0];
      const to = entries[i].prizes[0];
      if (transitionCounts[from]?.[to] !== undefined) {
        transitionCounts[from][to]++;
        transitionTotals[from]++;
      }
    }
  });
  const transitionProb = {};
  PRIZE_TIERS.forEach((from) => {
    transitionProb[from] = {};
    PRIZE_TIERS.forEach((to) => {
      transitionProb[from][to] =
        transitionCounts[from][to] / (transitionTotals[from] || 1);
    });
  });

  const markovHighValue = (lastPrize) => {
    if (!transitionProb[lastPrize]) return 50;
    return Math.min(
      100,
      ((transitionProb[lastPrize][5000] || 0) * 100 +
        (transitionProb[lastPrize][2000] || 0) * 60 +
        (transitionProb[lastPrize][1000] || 0) * 40) *
        3,
    );
  };

  const now = REFERENCE_DATE;
  const d6mAgo = new Date(now);
  d6mAgo.setMonth(d6mAgo.getMonth() - 6);

  const predictions = csvData.map((row) => {
    const entries = parseDates(row.dates);
    const tierCounts = getTierCounts(entries);

    const d7Ago = new Date(now);
    d7Ago.setDate(now.getDate() - 7);
    const d30Ago = new Date(now);
    d30Ago.setDate(now.getDate() - 30);
    const d90Ago = new Date(now);
    d90Ago.setDate(now.getDate() - 90);

    const entries7d = entries.filter((e) => e.date >= d7Ago);
    const entries30d = entries.filter((e) => e.date >= d30Ago);
    const entries90d = entries.filter((e) => e.date >= d90Ago);
    const recentEntries = entries.filter((e) => e.date >= d6mAgo);
    const recentHighTier = recentEntries.filter((e) =>
      e.prizes.some((p) => p >= 1000),
    ).length;

    const lastEntry = entries.length > 0 ? entries[entries.length - 1] : null;
    const lastPrize = lastEntry ? lastEntry.prizes[0] : 100;
    const daysSince = lastEntry
      ? Math.floor((now - lastEntry.date) / 86400000)
      : 999;
    const overdueRatio =
      row.avg_gap_days > 0 ? daysSince / row.avg_gap_days : 0;

    // Method 1: Gap
    let gapScore = 20;
    if (overdueRatio >= 2.0) gapScore = 100;
    else if (overdueRatio >= 1.5) gapScore = 85;
    else if (overdueRatio >= 1.2) gapScore = 70;
    else if (overdueRatio >= 1.0) gapScore = 60;
    else if (overdueRatio >= 0.8) gapScore = 40;

    // Method 2: Frequency
    const wFreq =
      tierCounts[5000] * 10 +
      tierCounts[2000] * 7 +
      tierCounts[1000] * 5 +
      tierCounts[500] * 3 +
      tierCounts[200] * 2 +
      tierCounts[100] * 1;
    const frequencyScore = Math.min(
      100,
      wFreq / 10 + (row.total_hits / maxHits) * 50,
    );

    // Method 3: Hot Streak
    const momentum = recentHighTier / Math.max(recentEntries.length, 1);
    const recencyBonus = daysSince < 30 ? 20 : daysSince < 60 ? 10 : 0;
    const hotStreakScore = Math.min(100, momentum * 80 + recencyBonus);

    // Method 4: Tier Progression
    let tierScore = 0;
    if (
      tierCounts[100] >= 10 &&
      tierCounts[500] >= 5 &&
      tierCounts[1000] >= 3 &&
      tierCounts[5000] >= 1
    )
      tierScore = 90;
    else if (
      tierCounts[100] >= 10 &&
      tierCounts[500] >= 5 &&
      tierCounts[1000] >= 3
    )
      tierScore = 75;
    else if (tierCounts[100] >= 10 && tierCounts[500] >= 5) tierScore = 55;
    else if (tierCounts[100] >= 10) tierScore = 35;
    if (tierCounts[5000] + tierCounts[2000] + tierCounts[1000] >= 15)
      tierScore = Math.min(100, tierScore + 10);

    // Method 5: Seasonality
    let seasonalityScore = 0;
    try {
      const wdCounts = JSON.parse(row.weekday_counts);
      const monCounts = JSON.parse(row.month_counts);
      const curWD = now.toLocaleDateString("en-US", { weekday: "long" });
      const curMon = now.toLocaleDateString("en-US", { month: "long" });
      const maxWD = Math.max(...Object.values(wdCounts), 1);
      const maxMon = Math.max(...Object.values(monCounts), 1);
      seasonalityScore =
        ((wdCounts[curWD] || 0) / maxWD) * 50 +
        ((monCounts[curMon] || 0) / maxMon) * 50;
    } catch (_) {}

    // Method 6: Markov
    let personalEscalation = 0;
    for (let i = 1; i < entries.length; i++)
      if (entries[i].prizes[0] > entries[i - 1].prizes[0]) personalEscalation++;
    const escalationRate = personalEscalation / Math.max(entries.length - 1, 1);
    const markovFinalScore = Math.min(
      100,
      markovHighValue(lastPrize) + escalationRate * 20,
    );

    // Method 7: Moving Average
    const rate7d = entries7d.length / 7;
    const rate30d = entries30d.length / 30;
    const rate90d = entries90d.length / 90;
    const movingAvgScore = Math.min(
      100,
      (rate7d * 0.5 + rate30d * 0.3 + rate90d * 0.2) * 400,
    );

    const finalScore = Math.round(
      gapScore * WEIGHTS.gap_based +
        frequencyScore * WEIGHTS.frequency +
        hotStreakScore * WEIGHTS.hot_streak +
        tierScore * WEIGHTS.tier_progression +
        seasonalityScore * WEIGHTS.seasonality +
        markovFinalScore * WEIGHTS.markov_chain +
        movingAvgScore * WEIGHTS.moving_average,
    );

    let recommendation;
    if (finalScore >= 80 && overdueRatio >= 1.5) recommendation = "STRONG BUY";
    else if (finalScore >= 70 && recentEntries.length >= 5)
      recommendation = "BUY";
    else if (finalScore >= 60) recommendation = "CONSIDER";
    else if (finalScore >= 40) recommendation = "WATCH";
    else recommendation = "SKIP";

    return {
      number: row.number,
      finalScore,
      recommendation,
      scores: {
        gap_based: gapScore,
        frequency: Math.round(frequencyScore),
        hot_streak: Math.round(hotStreakScore),
        tier_progression: tierScore,
        seasonality: Math.round(seasonalityScore),
        markov_chain: Math.round(markovFinalScore),
        moving_average: Math.round(movingAvgScore),
      },
      overdue_ratio: overdueRatio,
      recent_activity: recentEntries.length,
    };
  });

  predictions.sort((a, b) => b.finalScore - a.finalScore);
  return predictions;
}

// ── Main validation route ─────────────────────────────────────────
app.get("/api/validate", async (req, res) => {
  try {
    // ── 1. Load CSV predictions ───────────────────────────────────
    const csvPath = path.join(__dirname, "all_prizes_number_patterns30.csv");
    if (!fs.existsSync(csvPath)) {
      return res.status(404).json({ error: "CSV file not found" });
    }

    const lines = fs.readFileSync(csvPath, "utf-8").trim().split("\n");
    const csvData = lines.slice(1).map((line) => {
      const jsonStart = line.indexOf(',"{"');
      const preJson = line.slice(0, jsonStart).split(",");
      const number = preJson[0];
      const total_hits = parseInt(preJson[1]) || 0;
      const dates = preJson.slice(2, preJson.length - 1).join(",");
      const avg_gap_days = parseFloat(preJson[preJson.length - 1]) || 0;
      const jsonTail = line.slice(jsonStart + 1);
      const jsonMatches = jsonTail.match(/(\{[^}]+\})/g) || [];
      return {
        number,
        total_hits,
        dates,
        avg_gap_days,
        weekday_counts: jsonMatches[0] || "{}",
        month_counts: jsonMatches[1] || "{}",
      };
    });

    const allPredictions = buildPredictions(csvData);

    // Prediction sets for comparison
    const top50Set = new Set(allPredictions.slice(0, 50).map((p) => p.number));
    const top100Set = new Set(
      allPredictions.slice(0, 100).map((p) => p.number),
    );
    const strongBuySet = new Set(
      allPredictions
        .filter((p) => p.recommendation === "STRONG BUY")
        .map((p) => p.number),
    );
    const buySet = new Set(
      allPredictions
        .filter((p) => p.recommendation === "BUY")
        .map((p) => p.number),
    );
    const considerSet = new Set(
      allPredictions
        .filter((p) => p.recommendation === "CONSIDER")
        .map((p) => p.number),
    );

    // Method-specific top 30 sets
    const methodTopSets = {};
    [
      "gap_based",
      "frequency",
      "hot_streak",
      "tier_progression",
      "seasonality",
      "markov_chain",
      "moving_average",
    ].forEach((method) => {
      const sorted = [...allPredictions].sort(
        (a, b) => b.scores[method] - a.scores[method],
      );
      methodTopSets[method] = new Set(sorted.slice(0, 30).map((p) => p.number));
    });

    // ── 2. Fetch new draws from MongoDB (after 23/02/2026) ────────
    const allDocs = await LotteryData.find({}).lean();

    const newDrawDocs = allDocs.filter((doc) => {
      const docDate = parseDMY(doc.date);
      return docDate > CUTOFF_DATE;
    });

    if (newDrawDocs.length === 0) {
      return res.json({
        message: "No new draw data found after 23/02/2026",
        new_draws: [],
        validation: null,
      });
    }

    // ── 3. Extract actual numbers from new draws ──────────────────
    // newDraws: array of { date, numbers: Set<string>, byTier: { 5000: Set, ... } }
    const newDraws = newDrawDocs.map((doc) => {
      const allNums = new Set();
      const byTier = {
        5000: new Set(),
        2000: new Set(),
        1000: new Set(),
        500: new Set(),
        200: new Set(),
        100: new Set(),
      };
      const tierList = [];

      doc.series.forEach(({ prize, numbers }) => {
        numbers.forEach(({ number }) => {
          const n = String(number).padStart(4, "0");
          allNums.add(n);
          if (byTier[prize]) byTier[prize].add(n);
          tierList.push({ number: n, prize });
        });
      });

      return {
        date: doc.date,
        entryNumber: doc.entryNumber,
        allNumbers: allNums,
        byTier,
        tierList,
        totalNumbers: allNums.size,
      };
    });

    // Sort by date ascending
    newDraws.sort((a, b) => parseDMY(a.date) - parseDMY(b.date));

    // ── 4. Validate per draw ─────────────────────────────────────
    const perDayResults = newDraws.map((draw) => {
      const hits = (predSet) =>
        [...draw.allNumbers].filter((n) => predSet.has(n));

      const hitsTop50 = hits(top50Set);
      const hitsTop100 = hits(top100Set);
      const hitsStrongBuy = hits(strongBuySet);
      const hitsBuy = hits(buySet);
      const hitsConsider = hits(considerSet);

      // Per method hits
      const methodHits = {};
      Object.entries(methodTopSets).forEach(([method, set]) => {
        const h = hits(set);
        methodHits[method] = {
          hit_count: h.length,
          hit_rate: +((h.length / 30) * 100).toFixed(1),
          numbers: h,
        };
      });

      // Detailed hit info — for each hit, show what prediction rank / score it had
      const top50HitDetails = hitsTop50
        .map((num) => {
          const pred = allPredictions.find((p) => p.number === num);
          const tier = draw.tierList.find((t) => t.number === num);
          return {
            number: num,
            rank: allPredictions.indexOf(pred) + 1,
            finalScore: pred?.finalScore,
            recommendation: pred?.recommendation,
            actual_prize: tier?.prize,
          };
        })
        .sort((a, b) => a.rank - b.rank);

      return {
        date: draw.date,
        entryNumber: draw.entryNumber,
        total_numbers_drawn: draw.totalNumbers,
        hits: {
          top_50: {
            count: hitsTop50.length,
            rate: +((hitsTop50.length / 50) * 100).toFixed(1),
            numbers: hitsTop50,
          },
          top_100: {
            count: hitsTop100.length,
            rate: +((hitsTop100.length / 100) * 100).toFixed(1),
            numbers: hitsTop100,
          },
          strong_buy: {
            count: hitsStrongBuy.length,
            rate:
              strongBuySet.size > 0
                ? +((hitsStrongBuy.length / strongBuySet.size) * 100).toFixed(1)
                : 0,
            numbers: hitsStrongBuy,
          },
          buy: {
            count: hitsBuy.length,
            rate:
              buySet.size > 0
                ? +((hitsBuy.length / buySet.size) * 100).toFixed(1)
                : 0,
            numbers: hitsBuy,
          },
          consider: {
            count: hitsConsider.length,
            rate:
              considerSet.size > 0
                ? +((hitsConsider.length / considerSet.size) * 100).toFixed(1)
                : 0,
            numbers: hitsConsider,
          },
        },
        method_hits: methodHits,
        top50_hit_details: top50HitDetails,
        // Numbers drawn that were NOT in Top 100 (missed completely)
        missed_numbers: [...draw.allNumbers].filter((n) => !top100Set.has(n))
          .length,
      };
    });

    // ── 5. Aggregate summary across all new draws ─────────────────
    const totalDraws = perDayResults.length;
    const avgTop50Rate = +(
      perDayResults.reduce((s, d) => s + d.hits.top_50.rate, 0) / totalDraws
    ).toFixed(1);
    const avgSBRate = +(
      perDayResults.reduce((s, d) => s + d.hits.strong_buy.rate, 0) / totalDraws
    ).toFixed(1);
    const avgBuyRate = +(
      perDayResults.reduce((s, d) => s + d.hits.buy.rate, 0) / totalDraws
    ).toFixed(1);

    // Best performing method overall
    const methodAvgHitRates = {};
    Object.keys(methodTopSets).forEach((method) => {
      methodAvgHitRates[method] = +(
        perDayResults.reduce((s, d) => s + d.method_hits[method].hit_rate, 0) /
        totalDraws
      ).toFixed(1);
    });
    const bestMethod = Object.entries(methodAvgHitRates).sort(
      (a, b) => b[1] - a[1],
    )[0];

    // Numbers that hit across ALL new draws (most consistent)
    const hitFrequency = {};
    perDayResults.forEach((d) => {
      d.hits.top_50.numbers.forEach((n) => {
        hitFrequency[n] = (hitFrequency[n] || 0) + 1;
      });
    });
    const consistentHits = Object.entries(hitFrequency)
      .filter(([, count]) => count >= totalDraws)
      .map(([number, count]) => {
        const pred = allPredictions.find((p) => p.number === number);
        return {
          number,
          hit_count: count,
          rank: allPredictions.indexOf(pred) + 1,
          finalScore: pred?.finalScore,
        };
      })
      .sort((a, b) => b.hit_count - a.hit_count);

    res.json({
      generated_at: new Date().toISOString(),
      cutoff_date: "23/02/2026",
      new_draw_dates: newDraws.map((d) => d.date),
      total_new_draws: totalDraws,
      prediction_set_sizes: {
        top_50: 50,
        top_100: 100,
        strong_buy: strongBuySet.size,
        buy: buySet.size,
        consider: considerSet.size,
      },
      summary: {
        avg_top50_hit_rate: avgTop50Rate,
        avg_strong_buy_rate: avgSBRate,
        avg_buy_rate: avgBuyRate,
        best_method: bestMethod[0],
        best_method_hit_rate: bestMethod[1],
        method_avg_hit_rates: methodAvgHitRates,
        consistent_hits: consistentHits,
      },
      per_day: perDayResults,
    });
  } catch (err) {
    console.error("Validation error:", err);
    res.status(500).json({ error: "Validation failed", detail: err.message });
  }
});

app.get("/api/check-prize-amounts-up-to-5000", async (req, res) => {
  try {
    const folderPath = path.join(__dirname, "allfiles");
    const files = fs.readdirSync(folderPath).filter((f) => f.endsWith(".pdf"));

    const allAmounts = new Set();
    const fileWise = [];

    for (const fileName of files) {
      try {
        const filePath = path.join(folderPath, fileName);
        const buffer = fs.readFileSync(filePath);
        const data = await PdfParse(buffer);
        const text = data.text.replace(/\s+/g, " ");

        const matches = [
          ...text.matchAll(/(?:₹|Rs\.?\s*)\s*(\d[\d,]*)\s*\/-/gi),
          ...text.matchAll(/\b(\d[\d,]*)\s*\/-/g),
        ];

        const amountsInFile = new Set();

        for (const match of matches) {
          const amount = Number(match[1].replace(/,/g, "").trim());

          if (!isNaN(amount) && amount <= 5000) {
            allAmounts.add(amount);
            amountsInFile.add(amount);
          }
        }

        fileWise.push({
          fileName,
          prizeAmountsUpTo5000: Array.from(amountsInFile).sort((a, b) => b - a),
        });
      } catch (err) {
        fileWise.push({
          fileName,
          error: err.message,
        });
      }
    }

    res.json({
      uniquePrizeAmountsUpTo5000: Array.from(allAmounts).sort((a, b) => b - a),
      files: fileWise,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/compare-collections", async (req, res) => {
  try {
    // Get all serialNumbers from both collections
    const oldData = await LotteryData.find({}, { serialNumber: 1, _id: 0 });
    const newData = await LotteryDataNew.find({}, { serialNumber: 1, _id: 0 });

    const oldSerials = new Set(oldData.map((d) => d.serialNumber));
    const newSerials = new Set(newData.map((d) => d.serialNumber));

    // In both collections
    const inBoth = [...oldSerials].filter((s) => newSerials.has(s));

    // Only in old collection
    const onlyInOld = [...oldSerials].filter((s) => !newSerials.has(s));

    // Only in new collection
    const onlyInNew = [...newSerials].filter((s) => !oldSerials.has(s));

    res.json({
      summary: {
        totalOld: oldSerials.size,
        totalNew: newSerials.size,
        inBoth: inBoth.length,
        onlyInOld: onlyInOld.length,
        onlyInNew: onlyInNew.length,
      },
      data: {
        inBoth,
        onlyInOld,
        onlyInNew,
      },
    });
  } catch (err) {
    console.error("❌ Compare error:", err);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/compare-detailed", async (req, res) => {
  try {
    // Get all data from both collections
    const oldData = await LotteryData.find({});
    const newData = await LotteryDataNew.find({});

    // Map new data by serialNumber for quick lookup
    const newDataMap = new Map(newData.map((d) => [d.serialNumber, d]));

    const comparisonResults = [];

    for (const oldRecord of oldData) {
      const serialNumber = oldRecord.serialNumber;
      const newRecord = newDataMap.get(serialNumber);

      // If no matching record in new collection
      if (!newRecord) {
        comparisonResults.push({
          serialNumber,
          status: "Only in old collection",
          date: oldRecord.date,
          prizes: [],
        });
        continue;
      }

      // Map old prizes by prize amount
      const oldPrizeMap = new Map(
        oldRecord.series.map((s) => [
          s.prize,
          new Set(s.numbers.map((n) => n.number)),
        ]),
      );

      // Map new prizes by prize amount
      const newPrizeMap = new Map(
        newRecord.series.map((s) => [
          s.prize,
          new Set(s.numbers.map((n) => n.number)),
        ]),
      );

      // Get all prize amounts from both
      const allPrizes = new Set([...oldPrizeMap.keys(), ...newPrizeMap.keys()]);

      const prizeComparisons = [];

      for (const prize of allPrizes) {
        const oldNumbers = oldPrizeMap.get(prize) || new Set();
        const newNumbers = newPrizeMap.get(prize) || new Set();

        // Numbers in both
        const inBoth = [...oldNumbers].filter((n) => newNumbers.has(n));

        // Numbers only in old
        const onlyInOld = [...oldNumbers].filter((n) => !newNumbers.has(n));

        // Numbers only in new
        const onlyInNew = [...newNumbers].filter((n) => !oldNumbers.has(n));

        prizeComparisons.push({
          prize,
          summary: {
            totalOld: oldNumbers.size,
            totalNew: newNumbers.size,
            matchedCount: inBoth.length,
            onlyInOldCount: onlyInOld.length,
            onlyInNewCount: onlyInNew.length,
          },
          numbers: {
            inBoth,
            onlyInOld,
            onlyInNew,
          },
        });
      }

      // Overall match status
      const totalOldNumbers = [...oldPrizeMap.values()].reduce(
        (acc, s) => acc + s.size,
        0,
      );
      const totalNewNumbers = [...newPrizeMap.values()].reduce(
        (acc, s) => acc + s.size,
        0,
      );
      const totalMatched = prizeComparisons.reduce(
        (acc, p) => acc + p.summary.matchedCount,
        0,
      );

      comparisonResults.push({
        serialNumber,
        status: "Matched",
        oldDate: oldRecord.date,
        newDate: newRecord.date,
        summary: {
          totalOldNumbers,
          totalNewNumbers,
          totalMatched,
          totalOnlyInOld: totalOldNumbers - totalMatched,
          totalOnlyInNew: totalNewNumbers - totalMatched,
          isExactMatch:
            totalOldNumbers === totalNewNumbers &&
            totalMatched === totalOldNumbers,
        },
        prizes: prizeComparisons,
      });
    }

    // Check for serialNumbers only in new collection
    const oldSerials = new Set(oldData.map((d) => d.serialNumber));
    for (const newRecord of newData) {
      if (!oldSerials.has(newRecord.serialNumber)) {
        comparisonResults.push({
          serialNumber: newRecord.serialNumber,
          status: "Only in new collection",
          date: newRecord.date,
          prizes: [],
        });
      }
    }

    // Overall summary
    const totalMatched = comparisonResults.filter(
      (r) => r.status === "Matched",
    ).length;
    const onlyInOld = comparisonResults.filter(
      (r) => r.status === "Only in old collection",
    ).length;
    const onlyInNew = comparisonResults.filter(
      (r) => r.status === "Only in new collection",
    ).length;
    const exactMatches = comparisonResults.filter(
      (r) => r.status === "Matched" && r.summary?.isExactMatch,
    ).length;

    res.json({
      overallSummary: {
        totalOldRecords: oldData.length,
        totalNewRecords: newData.length,
        matchedSerials: totalMatched,
        onlyInOld,
        onlyInNew,
        exactMatches,
      },
      details: comparisonResults,
    });
  } catch (err) {
    console.error("❌ Detailed compare error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * Get counts from FullLotteryData (db3)
 */
app.get("/api/counts-db3", async (req, res) => {
  try {
    const allData = await FullLotteryData.find({});

    const counts = {};
    const prizeTotals = {};

    for (const record of allData) {
      for (const series of record.series) {
        const prize = series.prize || "Unknown";

        // Count numbers
        for (const numObj of series.numbers) {
          const num = numObj.number;
          counts[num] = (counts[num] || 0) + 1;
        }

        // Count prizes
        prizeTotals[prize] = (prizeTotals[prize] || 0) + series.numbers.length;
      }
    }

    // Sort prizes by value (descending)
    const sortedPrizes = Object.entries(prizeTotals)
      .sort((a, b) => b[0] - a[0])
      .reduce((obj, [key, val]) => {
        obj[key] = val;
        return obj;
      }, {});

    res.json({
      source: "FullLotteryData (DB3)",
      numberCounts: counts,
      prizeTotals: sortedPrizes,
      totalNumbers: Object.values(counts).reduce((a, b) => a + b, 0),
      totalUniqueNumbers: Object.keys(counts).length,
    });
  } catch (err) {
    console.error("❌ Error fetching DB3 counts:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * Get counts from AbsoluteData (db4)
 */
app.get("/api/counts-db4", async (req, res) => {
  try {
    const allData = await AbsoluteData.find({});

    const counts = {};
    const prizeTotals = {};

    for (const record of allData) {
      for (const series of record.series) {
        const prize = series.prize || "Unknown";

        // Count numbers
        for (const numObj of series.numbers) {
          const num = numObj.number;
          counts[num] = (counts[num] || 0) + 1;
        }

        // Count prizes
        prizeTotals[prize] = (prizeTotals[prize] || 0) + series.numbers.length;
      }
    }

    // Sort prizes by value (descending)
    const sortedPrizes = Object.entries(prizeTotals)
      .sort((a, b) => b[0] - a[0])
      .reduce((obj, [key, val]) => {
        obj[key] = val;
        return obj;
      }, {});

    res.json({
      source: "AbsoluteData (DB4)",
      numberCounts: counts,
      prizeTotals: sortedPrizes,
      totalNumbers: Object.values(counts).reduce((a, b) => a + b, 0),
      totalUniqueNumbers: Object.keys(counts).length,
    });
  } catch (err) {
    console.error("❌ Error fetching DB4 counts:", err);
    res.status(500).json({ error: err.message });
  }
});

//working...only for new collection
app.get("/api/new-cycles", async (req, res) => {
  try {
    const allData = await LotteryDataNew.find({});

    if (!allData.length) {
      return res.json({ cycles: [] });
    }

    // Parse date helper DD/MM/YYYY
    function parseDate(str) {
      if (!str || str === "Unknown") return new Date(0);
      const parts = str.match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
      if (parts) {
        return new Date(
          parseInt(parts[3]),
          parseInt(parts[2]) - 1,
          parseInt(parts[1]),
        );
      }
      return new Date(str);
    }

    // Sort by date ascending
    allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

    const cycles = [];
    let currentCycle = {
      cycleNumber: 1,
      startDate: null,
      endDate: null,
      totalDays: 0,
      uniqueNumbers: new Set(),
      numberFirstSeen: {},
      dailyProgress: [],
    };

    for (const record of allData) {
      const date = record.date;
      const parsedDate = parseDate(date);
      if (!parsedDate || parsedDate.getTime() === 0) continue;

      // Set start date of cycle
      if (!currentCycle.startDate) {
        currentCycle.startDate = date;
      }

      let newUniqueCount = 0;
      let cycleCompleted = false;

      // Go through all prize numbers
      for (const series of record.series) {
        for (const numObj of series.numbers) {
          const num = numObj.number;

          if (!currentCycle.uniqueNumbers.has(num)) {
            currentCycle.uniqueNumbers.add(num);
            currentCycle.numberFirstSeen[num] = date;
            newUniqueCount++;

            // Cycle complete
            if (currentCycle.uniqueNumbers.size === 10000) {
              currentCycle.endDate = date;
              currentCycle.totalDays = Math.ceil(
                (parseDate(date) - parseDate(currentCycle.startDate)) /
                  (1000 * 60 * 60 * 24),
              );

              currentCycle.dailyProgress.push({
                date,
                newUnique: newUniqueCount,
                totalUnique: currentCycle.uniqueNumbers.size,
              });

              // Save completed cycle
              cycles.push({
                cycleNumber: currentCycle.cycleNumber,
                startDate: currentCycle.startDate,
                endDate: currentCycle.endDate,
                totalDays: currentCycle.totalDays,
                totalUniqueNumbers: currentCycle.uniqueNumbers.size,
                isComplete: true,
                remainingNumbers: 0,
                dailyProgress: currentCycle.dailyProgress,
              });

              // Start new cycle
              currentCycle = {
                cycleNumber: cycles.length + 1,
                startDate: date,
                endDate: null,
                totalDays: 0,
                uniqueNumbers: new Set(),
                numberFirstSeen: {},
                dailyProgress: [],
              };

              newUniqueCount = 0;
              cycleCompleted = true;
              break;
            }
          }
        }

        if (cycleCompleted) break;
      }

      if (!cycleCompleted) {
        currentCycle.dailyProgress.push({
          date,
          newUnique: newUniqueCount,
          totalUnique: currentCycle.uniqueNumbers.size,
        });
      }
    }

    // Push last incomplete cycle
    if (currentCycle.uniqueNumbers.size > 0) {
      const lastDate =
        currentCycle.dailyProgress[currentCycle.dailyProgress.length - 1]
          ?.date || null;

      cycles.push({
        cycleNumber: currentCycle.cycleNumber,
        startDate: currentCycle.startDate,
        endDate: null,
        totalDays: lastDate
          ? Math.ceil(
              (parseDate(lastDate) - parseDate(currentCycle.startDate)) /
                (1000 * 60 * 60 * 24),
            )
          : 0,
        totalUniqueNumbers: currentCycle.uniqueNumbers.size,
        isComplete: false,
        remainingNumbers: 10000 - currentCycle.uniqueNumbers.size,
        dailyProgress: currentCycle.dailyProgress,
      });
    }

    // Overall summary using sorted data
    const firstDay = allData[0]?.date || "Unknown";
    const lastDay = allData[allData.length - 1]?.date || "Unknown";

    const completedCycles = cycles.filter((c) => c.isComplete).length;
    const incompleteCycles = cycles.filter((c) => !c.isComplete).length;

    res.json({
      summary: {
        totalCycles: cycles.length,
        completedCycles,
        incompleteCycles,
        firstDay,
        lastDay,
      },
      cycles: cycles.map((c) => ({
        cycleNumber: c.cycleNumber,
        startDate: c.startDate,
        endDate: c.endDate,
        totalDays: c.totalDays,
        totalUniqueNumbers: c.totalUniqueNumbers,
        isComplete: c.isComplete,
        remainingNumbers: c.remainingNumbers || 0,
        dailyProgress: c.dailyProgress,
      })),
    });
  } catch (err) {
    console.error("❌ Cycle error:", err);
    res.status(500).json({ error: err.message });
  }
});

// routes/cycles.js (or inside your server file)

// Factory that returns the SAME handler logic, just swapping the model
function makeCyclesHandler(Model) {
  return async (req, res) => {
    try {
      const allData = await Model.find({}).lean();

      if (!allData.length) {
        return res.json({
          summary: {
            totalCycles: 0,
            completedCycles: 0,
            incompleteCycles: 0,
            firstDay: "Unknown",
            lastDay: "Unknown",
          },
          cycles: [],
        });
      }

      function parseDate(str) {
        if (!str || str === "Unknown") return new Date(0);
        const parts = String(str)
          .trim()
          .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);

        if (parts) {
          return new Date(
            parseInt(parts[3], 10),
            parseInt(parts[2], 10) - 1,
            parseInt(parts[1], 10),
          );
        }
        return new Date(str);
      }

      allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

      const cycles = [];

      let currentCycle = {
        cycleNumber: 1,
        startDate: null,
        endDate: null,
        totalDays: 0,
        uniqueNumbers: new Set(),
        numberFirstSeen: {},
        dailyProgress: [],
        prizeStates: new Map(),
      };

      // ✅ Helper: get remaining numbers (0000-9999 not in the set)
      function getRemainingNumbers(uniqueSet) {
        const remaining = [];
        for (let i = 0; i < 10000; i++) {
          const num = String(i).padStart(4, "0"); // "0000" to "9999"
          if (!uniqueSet.has(num)) {
            remaining.push(num);
          }
        }
        return remaining;
      }

      // ✅ Helper: get remaining numbers per prize
      function getRemainingNumbersByPrize(prizeStates) {
        const result = {};
        for (const [prize, ps] of prizeStates.entries()) {
          const remaining = [];
          for (let i = 0; i < 10000; i++) {
            const num = String(i).padStart(4, "0");
            if (!ps.uniqueNumbers.has(num)) {
              remaining.push(num);
            }
          }
          result[prize] = {
            count: remaining.length,
            numbers: remaining,
          };
        }
        return result;
      }

      // helper: build prize summaries for a cycle
      function buildPrizeSummaries(cycle, lastDateForIncomplete) {
        const prizes = Array.from(cycle.prizeStates.entries()).map(
          ([prize, ps]) => {
            const totalUnique = ps.uniqueNumbers.size;
            const isComplete = totalUnique === 10000;

            const totalDays =
              isComplete && ps.endDate
                ? Math.ceil(
                    (parseDate(ps.endDate) - parseDate(ps.startDate)) /
                      (1000 * 60 * 60 * 24),
                  )
                : ps.startDate && lastDateForIncomplete
                  ? Math.ceil(
                      (parseDate(lastDateForIncomplete) -
                        parseDate(ps.startDate)) /
                        (1000 * 60 * 60 * 24),
                    )
                  : 0;

            // ✅ Get remaining numbers for this prize
            const remainingList = [];
            for (let i = 0; i < 10000; i++) {
              const num = String(i).padStart(4, "0");
              if (!ps.uniqueNumbers.has(num)) {
                remainingList.push(num);
              }
            }

            return {
              prize,
              startDate: ps.startDate || null,
              endDate: ps.endDate || null,
              totalDays,
              totalUniqueNumbers: totalUnique,
              remainingNumbers: Math.max(0, 10000 - totalUnique),
              remainingNumbersList: remainingList, // ✅ NEW
              percentComplete: Number(((totalUnique / 10000) * 100).toFixed(2)),
              isComplete,
            };
          },
        );

        prizes.sort((a, b) => b.totalUniqueNumbers - a.totalUniqueNumbers);

        const prizeLeader = prizes[0]
          ? {
              prize: prizes[0].prize,
              totalUniqueNumbers: prizes[0].totalUniqueNumbers,
              percentComplete: prizes[0].percentComplete,
            }
          : null;

        const completedPrizes = prizes
          .filter((p) => p.isComplete)
          .map((p) => p.prize);

        return { prizes, prizeLeader, completedPrizes };
      }

      for (const record of allData) {
        const date = record.date;
        const parsedDate = parseDate(date);
        if (!parsedDate || parsedDate.getTime() === 0) continue;

        if (!currentCycle.startDate) currentCycle.startDate = date;

        let newUniqueCount = 0;
        let cycleCompleted = false;

        const numbersAddedToday = [];
        const prizeNumbersAddedToday = {};

        for (const series of record.series || []) {
          const prize = series.prize;

          if (!currentCycle.prizeStates.has(prize)) {
            currentCycle.prizeStates.set(prize, {
              uniqueNumbers: new Set(),
              startDate: null,
              endDate: null,
            });
          }

          const prizeState = currentCycle.prizeStates.get(prize);

          if (!prizeNumbersAddedToday[prize]) {
            prizeNumbersAddedToday[prize] = [];
          }

          for (const numObj of series.numbers || []) {
            const num = numObj.number;

            if (!currentCycle.uniqueNumbers.has(num)) {
              currentCycle.uniqueNumbers.add(num);
              currentCycle.numberFirstSeen[num] = date;
              newUniqueCount++;
              numbersAddedToday.push(num);
            }

            if (!prizeState.uniqueNumbers.has(num)) {
              prizeState.uniqueNumbers.add(num);
              prizeNumbersAddedToday[prize].push(num);

              if (!prizeState.startDate) {
                prizeState.startDate = date;
              }

              if (
                prizeState.uniqueNumbers.size === 10000 &&
                !prizeState.endDate
              ) {
                prizeState.endDate = date;
              }
            }

            if (currentCycle.uniqueNumbers.size === 10000) {
              currentCycle.endDate = date;
              currentCycle.totalDays = Math.ceil(
                (parseDate(date) - parseDate(currentCycle.startDate)) /
                  (1000 * 60 * 60 * 24),
              );

              currentCycle.dailyProgress.push({
                date,
                newUnique: newUniqueCount,
                totalUnique: currentCycle.uniqueNumbers.size,
                numbersAdded: numbersAddedToday,
                prizeNumbersAdded: prizeNumbersAddedToday,
              });

              const { prizes, prizeLeader, completedPrizes } =
                buildPrizeSummaries(currentCycle, date);

              cycles.push({
                cycleNumber: currentCycle.cycleNumber,
                startDate: currentCycle.startDate,
                endDate: currentCycle.endDate,
                totalDays: currentCycle.totalDays,
                totalUniqueNumbers: currentCycle.uniqueNumbers.size,
                isComplete: true,
                remainingNumbers: 0,
                remainingNumbersList: [], // ✅ Empty for complete cycles
                dailyProgress: currentCycle.dailyProgress,
                prizes,
                prizeLeader,
                completedPrizes,
              });

              currentCycle = {
                cycleNumber: cycles.length + 1,
                startDate: date,
                endDate: null,
                totalDays: 0,
                uniqueNumbers: new Set(),
                numberFirstSeen: {},
                dailyProgress: [],
                prizeStates: new Map(),
              };

              newUniqueCount = 0;
              cycleCompleted = true;
              break;
            }
          }

          if (cycleCompleted) break;
        }

        if (!cycleCompleted) {
          currentCycle.dailyProgress.push({
            date,
            newUnique: newUniqueCount,
            totalUnique: currentCycle.uniqueNumbers.size,
            numbersAdded: numbersAddedToday,
            prizeNumbersAdded: prizeNumbersAddedToday,
          });
        }
      }

      // push last incomplete cycle
      if (currentCycle.uniqueNumbers.size > 0) {
        const lastDate =
          currentCycle.dailyProgress[currentCycle.dailyProgress.length - 1]
            ?.date || null;

        const { prizes, prizeLeader, completedPrizes } = buildPrizeSummaries(
          currentCycle,
          lastDate,
        );

        // ✅ Get remaining numbers for the incomplete cycle
        const remainingNumbersList = getRemainingNumbers(
          currentCycle.uniqueNumbers,
        );

        cycles.push({
          cycleNumber: currentCycle.cycleNumber,
          startDate: currentCycle.startDate,
          endDate: null,
          totalDays: lastDate
            ? Math.ceil(
                (parseDate(lastDate) - parseDate(currentCycle.startDate)) /
                  (1000 * 60 * 60 * 24),
              )
            : 0,
          totalUniqueNumbers: currentCycle.uniqueNumbers.size,
          isComplete: false,
          remainingNumbers: 10000 - currentCycle.uniqueNumbers.size,
          remainingNumbersList, // ✅ NEW
          dailyProgress: currentCycle.dailyProgress,
          prizes,
          prizeLeader,
          completedPrizes,
        });
      }

      const firstDay = allData[0]?.date || "Unknown";
      const lastDay = allData[allData.length - 1]?.date || "Unknown";

      const completedCycles = cycles.filter((c) => c.isComplete).length;
      const incompleteCycles = cycles.filter((c) => !c.isComplete).length;

      res.json({
        summary: {
          totalCycles: cycles.length,
          completedCycles,
          incompleteCycles,
          firstDay,
          lastDay,
        },
        cycles,
      });
    } catch (err) {
      console.error("❌ Cycle error:", err);
      res.status(500).json({ error: err.message });
    }
  };
}

// Two collections, same logic
app.get("/api/cycles/lotterydata", makeCyclesHandler(LotteryData));
app.get("/api/cycles/lotterydatanew", makeCyclesHandler(LotteryDataNew));

//comparisons
// Add this new endpoint

// Factory function for cycle comparison handler
function makeCycleComparisonHandler(Model) {
  return async (req, res) => {
    try {
      const allData = await Model.find({}).lean();

      if (!allData.length) {
        return res.json({ error: "No data found" });
      }

      function parseDate(str) {
        if (!str || str === "Unknown") return new Date(0);
        const parts = String(str)
          .trim()
          .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
        if (parts) {
          return new Date(
            parseInt(parts[3], 10),
            parseInt(parts[2], 10) - 1,
            parseInt(parts[1], 10),
          );
        }
        return new Date(str);
      }

      allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

      // ========== STEP 1: Build all cycles with detailed number tracking ==========
      const cycles = [];
      let currentCycle = {
        cycleNumber: 1,
        startDate: null,
        endDate: null,
        uniqueNumbers: new Set(),
        numberDetails: {},
        dailyDates: [],
      };

      let dayCounter = 0;

      for (const record of allData) {
        const date = record.date;
        const parsedDate = parseDate(date);
        if (!parsedDate || parsedDate.getTime() === 0) continue;

        if (!currentCycle.startDate) {
          currentCycle.startDate = date;
        }

        dayCounter++;
        currentCycle.dailyDates.push(date);

        let cycleCompleted = false;

        for (const series of record.series || []) {
          const prize = series.prize;

          for (const numObj of series.numbers || []) {
            const num = numObj.number;

            if (!currentCycle.uniqueNumbers.has(num)) {
              currentCycle.uniqueNumbers.add(num);
              currentCycle.numberDetails[num] = {
                date,
                dayNumber: dayCounter,
                prize,
              };
            }

            // Cycle complete
            if (currentCycle.uniqueNumbers.size === 10000) {
              currentCycle.endDate = date;
              currentCycle.totalDays = dayCounter;

              cycles.push({
                cycleNumber: currentCycle.cycleNumber,
                startDate: currentCycle.startDate,
                endDate: currentCycle.endDate,
                totalDays: currentCycle.totalDays,
                numberDetails: { ...currentCycle.numberDetails },
                isComplete: true,
              });

              // Start new cycle
              currentCycle = {
                cycleNumber: cycles.length + 1,
                startDate: date,
                endDate: null,
                uniqueNumbers: new Set(),
                numberDetails: {},
                dailyDates: [date],
              };
              dayCounter = 1;
              cycleCompleted = true;
              break;
            }
          }

          if (cycleCompleted) break;
        }
      }

      // Push last incomplete cycle
      if (currentCycle.uniqueNumbers.size > 0) {
        currentCycle.totalDays = dayCounter;
        cycles.push({
          cycleNumber: currentCycle.cycleNumber,
          startDate: currentCycle.startDate,
          endDate: null,
          totalDays: currentCycle.totalDays,
          numberDetails: { ...currentCycle.numberDetails },
          isComplete: false,
          currentDay: dayCounter,
        });
      }

      // ========== STEP 2: Dynamic cycle selection ==========
      // Find cycles 2, 3, 4 and the current incomplete cycle (or last complete)
      const completeCycles = cycles.filter((c) => c.isComplete);
      const incompleteCycle = cycles.find((c) => !c.isComplete);

      // Need at least 3 complete cycles for comparison
      if (completeCycles.length < 3) {
        return res.json({
          error: `Need at least 3 complete cycles. Found: ${completeCycles.length}`,
          availableCycles: cycles.map((c) => ({
            cycleNumber: c.cycleNumber,
            isComplete: c.isComplete,
            totalDays: c.totalDays,
          })),
        });
      }

      // Get cycles 2, 3, 4 (skip cycle 1)
      const cycle2 = cycles.find((c) => c.cycleNumber === 2);
      const cycle3 = cycles.find((c) => c.cycleNumber === 3);
      const cycle4 = cycles.find((c) => c.cycleNumber === 4);
      const cycle5 = cycles.find((c) => c.cycleNumber === 5) || incompleteCycle;

      if (!cycle2 || !cycle3 || !cycle4) {
        return res.json({ error: "Cycles 2, 3, 4 not found" });
      }

      // ========== STEP 3: Build comparison for each number ==========
      const numberComparison = [];

      for (let i = 0; i < 10000; i++) {
        const num = String(i).padStart(4, "0");

        const c2 = cycle2.numberDetails[num] || null;
        const c3 = cycle3.numberDetails[num] || null;
        const c4 = cycle4.numberDetails[num] || null;
        const c5 = cycle5?.numberDetails[num] || null;

        // Calculate stats from cycles 2-4
        const appearances = [c2, c3, c4].filter((x) => x !== null);
        const dayNumbers = appearances.map((x) => x.dayNumber);

        const avgDay =
          dayNumbers.length > 0
            ? Math.round(
                dayNumbers.reduce((a, b) => a + b, 0) / dayNumbers.length,
              )
            : null;

        const minDay = dayNumbers.length > 0 ? Math.min(...dayNumbers) : null;
        const maxDay = dayNumbers.length > 0 ? Math.max(...dayNumbers) : null;

        // Prizes it appeared in
        const prizesInCycles = appearances.map((x) => x.prize);

        // Prediction for cycle 5
        const appearedInCycle5 = c5 !== null;
        const cycle5CurrentDay = cycle5?.currentDay || cycle5?.totalDays || 0;

        let prediction = null;
        if (!appearedInCycle5 && avgDay !== null) {
          const daysOverdue = cycle5CurrentDay - avgDay;
          let priority = "low";

          if (daysOverdue > 50) priority = "critical";
          else if (daysOverdue > 30) priority = "high";
          else if (daysOverdue > 10) priority = "medium";
          else if (daysOverdue > 0) priority = "low";
          else priority = "upcoming";

          prediction = {
            expectedDay: avgDay,
            currentDay: cycle5CurrentDay,
            daysOverdue: Math.max(0, daysOverdue),
            priority,
            confidence:
              appearances.length === 3
                ? "high"
                : appearances.length === 2
                  ? "medium"
                  : "low",
          };
        }

        numberComparison.push({
          number: num,
          cycle2: c2
            ? { date: c2.date, dayNumber: c2.dayNumber, prize: c2.prize }
            : null,
          cycle3: c3
            ? { date: c3.date, dayNumber: c3.dayNumber, prize: c3.prize }
            : null,
          cycle4: c4
            ? { date: c4.date, dayNumber: c4.dayNumber, prize: c4.prize }
            : null,
          cycle5: c5
            ? { date: c5.date, dayNumber: c5.dayNumber, prize: c5.prize }
            : null,
          stats: {
            appearanceCount: appearances.length,
            avgDay,
            minDay,
            maxDay,
            prizes: [...new Set(prizesInCycles)],
          },
          appearedInCycle5,
          prediction,
        });
      }

      // ========== STEP 4: Generate predictions sorted by priority ==========
      const predictions = numberComparison
        .filter((n) => !n.appearedInCycle5 && n.prediction)
        .sort((a, b) => {
          const priorityOrder = {
            critical: 0,
            high: 1,
            medium: 2,
            low: 3,
            upcoming: 4,
          };
          const pA = priorityOrder[a.prediction.priority];
          const pB = priorityOrder[b.prediction.priority];
          if (pA !== pB) return pA - pB;
          return b.prediction.daysOverdue - a.prediction.daysOverdue;
        });

      // ========== STEP 5: Summary stats ==========
      const summary = {
        totalCyclesFound: cycles.length,
        cycle2: {
          startDate: cycle2.startDate,
          endDate: cycle2.endDate,
          totalDays: cycle2.totalDays,
          isComplete: cycle2.isComplete,
        },
        cycle3: {
          startDate: cycle3.startDate,
          endDate: cycle3.endDate,
          totalDays: cycle3.totalDays,
          isComplete: cycle3.isComplete,
        },
        cycle4: {
          startDate: cycle4.startDate,
          endDate: cycle4.endDate,
          totalDays: cycle4.totalDays,
          isComplete: cycle4.isComplete,
        },
        cycle5: cycle5
          ? {
              cycleNumber: cycle5.cycleNumber,
              startDate: cycle5.startDate,
              endDate: cycle5.endDate,
              totalDays: cycle5.totalDays,
              currentDay: cycle5.currentDay || cycle5.totalDays,
              numbersAppeared: Object.keys(cycle5.numberDetails).length,
              numbersRemaining:
                10000 - Object.keys(cycle5.numberDetails).length,
              isComplete: cycle5.isComplete,
            }
          : null,
        avgCycleDays: Math.round(
          (cycle2.totalDays + cycle3.totalDays + cycle4.totalDays) / 3,
        ),
        predictions: {
          critical: predictions.filter(
            (p) => p.prediction.priority === "critical",
          ).length,
          high: predictions.filter((p) => p.prediction.priority === "high")
            .length,
          medium: predictions.filter((p) => p.prediction.priority === "medium")
            .length,
          low: predictions.filter((p) => p.prediction.priority === "low")
            .length,
          upcoming: predictions.filter(
            (p) => p.prediction.priority === "upcoming",
          ).length,
        },
      };

      // ========== STEP 6: Pattern Analysis ==========
      const patterns = {
        alwaysEarly: numberComparison.filter(
          (n) =>
            n.stats.appearanceCount === 3 &&
            n.stats.maxDay <= Math.round(summary.avgCycleDays * 0.3),
        ),
        alwaysLate: numberComparison.filter(
          (n) =>
            n.stats.appearanceCount === 3 &&
            n.stats.minDay >= Math.round(summary.avgCycleDays * 0.7),
        ),
        highVariance: numberComparison.filter(
          (n) =>
            n.stats.appearanceCount === 3 &&
            n.stats.maxDay - n.stats.minDay >
              Math.round(summary.avgCycleDays * 0.5),
        ),
        consistentTiming: numberComparison.filter(
          (n) =>
            n.stats.appearanceCount === 3 &&
            n.stats.maxDay - n.stats.minDay <= 20,
        ),
      };

      res.json({
        summary,
        patterns: {
          alwaysEarly: patterns.alwaysEarly.slice(0, 100).map((n) => ({
            number: n.number,
            avgDay: n.stats.avgDay,
            cycle5Status: n.appearedInCycle5 ? "appeared" : "pending",
          })),
          alwaysLate: patterns.alwaysLate.slice(0, 100).map((n) => ({
            number: n.number,
            avgDay: n.stats.avgDay,
            cycle5Status: n.appearedInCycle5 ? "appeared" : "pending",
          })),
          consistentTiming: patterns.consistentTiming.length,
          highVariance: patterns.highVariance.length,
        },
        predictions: predictions.slice(0, 500),
        fullComparison: numberComparison,
      });
    } catch (err) {
      console.error("❌ Comparison error:", err);
      res.status(500).json({ error: err.message });
    }
  };
}

// ✅ Two separate endpoints for both collections
app.get(
  "/api/cycle-comparison/lotterydata",
  makeCycleComparisonHandler(LotteryData),
);
app.get(
  "/api/cycle-comparison/lotterydatanew",
  makeCycleComparisonHandler(LotteryDataNew),
);

// Add this new endpoint
function makeDayCycleComparisonHandler(Model) {
  return async (req, res) => {
    try {
      const allData = await Model.find({}).lean();

      if (!allData.length) {
        return res.json({ error: "No data found" });
      }

      function parseDate(str) {
        if (!str || str === "Unknown") return new Date(0);
        const parts = String(str)
          .trim()
          .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
        if (parts) {
          return new Date(
            parseInt(parts[3], 10),
            parseInt(parts[2], 10) - 1,
            parseInt(parts[1], 10),
          );
        }
        return new Date(str);
      }

      allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

      // ========== STEP 1: Build cycles with day-by-day tracking ==========
      const cycles = [];
      let currentCycle = {
        cycleNumber: 1,
        startDate: null,
        endDate: null,
        uniqueNumbers: new Set(),
        numbersByDay: {}, // { dayNumber: [numbers] }
        dayByNumber: {}, // { number: dayNumber }
        dateByDay: {}, // { dayNumber: date }
      };

      let dayCounter = 0;

      for (const record of allData) {
        const date = record.date;
        const parsedDate = parseDate(date);
        if (!parsedDate || parsedDate.getTime() === 0) continue;

        if (!currentCycle.startDate) {
          currentCycle.startDate = date;
        }

        dayCounter++;
        currentCycle.dateByDay[dayCounter] = date;

        if (!currentCycle.numbersByDay[dayCounter]) {
          currentCycle.numbersByDay[dayCounter] = [];
        }

        let cycleCompleted = false;

        for (const series of record.series || []) {
          const prize = series.prize;

          for (const numObj of series.numbers || []) {
            const num = numObj.number;

            if (!currentCycle.uniqueNumbers.has(num)) {
              currentCycle.uniqueNumbers.add(num);
              currentCycle.dayByNumber[num] = dayCounter;
              currentCycle.numbersByDay[dayCounter].push({
                number: num,
                prize,
              });
            }

            if (currentCycle.uniqueNumbers.size === 10000) {
              currentCycle.endDate = date;
              currentCycle.totalDays = dayCounter;

              cycles.push({
                cycleNumber: currentCycle.cycleNumber,
                startDate: currentCycle.startDate,
                endDate: currentCycle.endDate,
                totalDays: currentCycle.totalDays,
                numbersByDay: { ...currentCycle.numbersByDay },
                dayByNumber: { ...currentCycle.dayByNumber },
                dateByDay: { ...currentCycle.dateByDay },
                isComplete: true,
              });

              currentCycle = {
                cycleNumber: cycles.length + 1,
                startDate: date,
                endDate: null,
                uniqueNumbers: new Set(),
                numbersByDay: { 1: [] },
                dayByNumber: {},
                dateByDay: { 1: date },
              };
              dayCounter = 1;
              cycleCompleted = true;
              break;
            }
          }

          if (cycleCompleted) break;
        }
      }

      // Push last incomplete cycle
      if (currentCycle.uniqueNumbers.size > 0) {
        currentCycle.totalDays = dayCounter;
        cycles.push({
          cycleNumber: currentCycle.cycleNumber,
          startDate: currentCycle.startDate,
          endDate: null,
          totalDays: currentCycle.totalDays,
          numbersByDay: { ...currentCycle.numbersByDay },
          dayByNumber: { ...currentCycle.dayByNumber },
          dateByDay: { ...currentCycle.dateByDay },
          isComplete: false,
          currentDay: dayCounter,
        });
      }

      // Get cycles 2, 3, 4
      const cycle2 = cycles.find((c) => c.cycleNumber === 2);
      const cycle3 = cycles.find((c) => c.cycleNumber === 3);
      const cycle4 = cycles.find((c) => c.cycleNumber === 4);
      const cycle5 = cycles.find((c) => c.cycleNumber === 5);

      if (!cycle2 || !cycle3 || !cycle4) {
        return res.json({
          error: "Cycles 2, 3, 4 not found",
          availableCycles: cycles.map((c) => c.cycleNumber),
        });
      }

      // ========== STEP 2: Find numbers appearing on SAME DAY across cycles ==========
      const exactSameDay = []; // Numbers appearing on exact same day in all 3 cycles
      const sameDay2Cycles = []; // Numbers appearing on same day in 2 cycles
      const within1Day = []; // Numbers within ±1 day
      const within2Days = []; // Numbers within ±2 days
      const within3Days = []; // Numbers within ±3 days
      const within5Days = []; // Numbers within ±5 days

      for (let i = 0; i < 10000; i++) {
        const num = String(i).padStart(4, "0");

        const day2 = cycle2.dayByNumber[num] || null;
        const day3 = cycle3.dayByNumber[num] || null;
        const day4 = cycle4.dayByNumber[num] || null;
        const day5 = cycle5?.dayByNumber[num] || null;

        if (day2 === null || day3 === null || day4 === null) continue;

        const days = [day2, day3, day4];
        const minDay = Math.min(...days);
        const maxDay = Math.max(...days);
        const range = maxDay - minDay;
        const avgDay = Math.round((day2 + day3 + day4) / 3);

        const entry = {
          number: num,
          cycle2: { day: day2, date: cycle2.dateByDay[day2] },
          cycle3: { day: day3, date: cycle3.dateByDay[day3] },
          cycle4: { day: day4, date: cycle4.dateByDay[day4] },
          cycle5: day5 ? { day: day5, date: cycle5.dateByDay[day5] } : null,
          avgDay,
          minDay,
          maxDay,
          range,
          appearedInCycle5: day5 !== null,
        };

        // Exact same day in all 3 cycles
        if (day2 === day3 && day3 === day4) {
          exactSameDay.push(entry);
        }

        // Same day in 2 cycles
        if (day2 === day3 || day3 === day4 || day2 === day4) {
          sameDay2Cycles.push(entry);
        }

        // Within range
        if (range <= 1) within1Day.push(entry);
        if (range <= 2) within2Days.push(entry);
        if (range <= 3) within3Days.push(entry);
        if (range <= 5) within5Days.push(entry);
      }

      // Sort by day
      const sortByAvgDay = (a, b) => a.avgDay - b.avgDay;
      exactSameDay.sort(sortByAvgDay);
      sameDay2Cycles.sort(sortByAvgDay);
      within1Day.sort(sortByAvgDay);
      within2Days.sort(sortByAvgDay);
      within3Days.sort(sortByAvgDay);
      within5Days.sort(sortByAvgDay);

      // ========== STEP 3: Day-by-Day comparison ==========
      const maxDays = Math.max(
        cycle2.totalDays,
        cycle3.totalDays,
        cycle4.totalDays,
      );
      const dayByDayComparison = [];

      for (let day = 1; day <= maxDays; day++) {
        const nums2 = new Set(
          (cycle2.numbersByDay[day] || []).map((n) => n.number),
        );
        const nums3 = new Set(
          (cycle3.numbersByDay[day] || []).map((n) => n.number),
        );
        const nums4 = new Set(
          (cycle4.numbersByDay[day] || []).map((n) => n.number),
        );

        // Find common numbers on this day
        const commonAll3 = [...nums2].filter(
          (n) => nums3.has(n) && nums4.has(n),
        );
        const common2_3 = [...nums2].filter(
          (n) => nums3.has(n) && !nums4.has(n),
        );
        const common2_4 = [...nums2].filter(
          (n) => !nums3.has(n) && nums4.has(n),
        );
        const common3_4 = [...nums3].filter(
          (n) => !nums2.has(n) && nums4.has(n),
        );

        dayByDayComparison.push({
          day,
          cycle2: {
            date: cycle2.dateByDay[day] || null,
            count: nums2.size,
            numbers: [...nums2].slice(0, 50), // Limit for response size
          },
          cycle3: {
            date: cycle3.dateByDay[day] || null,
            count: nums3.size,
            numbers: [...nums3].slice(0, 50),
          },
          cycle4: {
            date: cycle4.dateByDay[day] || null,
            count: nums4.size,
            numbers: [...nums4].slice(0, 50),
          },
          commonInAll3: commonAll3,
          common2_3: common2_3.slice(0, 20),
          common2_4: common2_4.slice(0, 20),
          common3_4: common3_4.slice(0, 20),
          totalCommon:
            commonAll3.length +
            common2_3.length +
            common2_4.length +
            common3_4.length,
        });
      }

      // ========== STEP 4: Cycle Similarity Analysis ==========
      function calculateSimilarity(cycleA, cycleB) {
        let exactMatches = 0;
        let within1 = 0;
        let within3 = 0;
        let within5 = 0;
        let totalCompared = 0;

        for (let i = 0; i < 10000; i++) {
          const num = String(i).padStart(4, "0");
          const dayA = cycleA.dayByNumber[num];
          const dayB = cycleB.dayByNumber[num];

          if (dayA && dayB) {
            totalCompared++;
            const diff = Math.abs(dayA - dayB);

            if (diff === 0) exactMatches++;
            if (diff <= 1) within1++;
            if (diff <= 3) within3++;
            if (diff <= 5) within5++;
          }
        }

        return {
          totalCompared,
          exactMatches,
          exactMatchPercent: ((exactMatches / totalCompared) * 100).toFixed(2),
          within1,
          within1Percent: ((within1 / totalCompared) * 100).toFixed(2),
          within3,
          within3Percent: ((within3 / totalCompared) * 100).toFixed(2),
          within5,
          within5Percent: ((within5 / totalCompared) * 100).toFixed(2),
        };
      }

      const similarity = {
        cycle2_vs_3: calculateSimilarity(cycle2, cycle3),
        cycle2_vs_4: calculateSimilarity(cycle2, cycle4),
        cycle3_vs_4: calculateSimilarity(cycle3, cycle4),
      };

      // ========== STEP 5: Predictions for Cycle 5 ==========
      const predictions = [];
      const cycle5CurrentDay = cycle5?.currentDay || cycle5?.totalDays || 0;

      for (let i = 0; i < 10000; i++) {
        const num = String(i).padStart(4, "0");

        const day2 = cycle2.dayByNumber[num];
        const day3 = cycle3.dayByNumber[num];
        const day4 = cycle4.dayByNumber[num];
        const day5 = cycle5?.dayByNumber[num];

        if (!day2 || !day3 || !day4) continue;
        if (day5) continue; // Already appeared in cycle 5

        const days = [day2, day3, day4];
        const avgDay = Math.round((day2 + day3 + day4) / 3);
        const minDay = Math.min(...days);
        const maxDay = Math.max(...days);
        const range = maxDay - minDay;

        // Prediction score based on consistency
        let consistencyScore = 0;
        if (range === 0)
          consistencyScore = 100; // Exact same day
        else if (range <= 1) consistencyScore = 95;
        else if (range <= 2) consistencyScore = 90;
        else if (range <= 3) consistencyScore = 85;
        else if (range <= 5) consistencyScore = 75;
        else if (range <= 10) consistencyScore = 60;
        else consistencyScore = 40;

        // Overdue calculation
        const daysOverdue = cycle5CurrentDay - avgDay;
        let urgency = "low";
        if (daysOverdue > 30) urgency = "critical";
        else if (daysOverdue > 15) urgency = "high";
        else if (daysOverdue > 5) urgency = "medium";
        else if (daysOverdue > 0) urgency = "low";
        else urgency = "upcoming";

        predictions.push({
          number: num,
          cycle2Day: day2,
          cycle3Day: day3,
          cycle4Day: day4,
          avgDay,
          minDay,
          maxDay,
          range,
          consistencyScore,
          currentDay: cycle5CurrentDay,
          daysOverdue: Math.max(0, daysOverdue),
          urgency,
          predictedDayRange: `${minDay} - ${maxDay}`,
        });
      }

      // Sort predictions by urgency then consistency
      const urgencyOrder = {
        critical: 0,
        high: 1,
        medium: 2,
        low: 3,
        upcoming: 4,
      };
      predictions.sort((a, b) => {
        if (urgencyOrder[a.urgency] !== urgencyOrder[b.urgency]) {
          return urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
        }
        return b.consistencyScore - a.consistencyScore;
      });

      // ========== STEP 6: Find "Hot Days" - days with most common numbers ==========
      const hotDays = dayByDayComparison
        .filter((d) => d.commonInAll3.length > 0)
        .sort((a, b) => b.commonInAll3.length - a.commonInAll3.length)
        .slice(0, 50);

      // ========== STEP 7: Summary ==========
      const summary = {
        cycles: {
          cycle2: {
            startDate: cycle2.startDate,
            endDate: cycle2.endDate,
            totalDays: cycle2.totalDays,
          },
          cycle3: {
            startDate: cycle3.startDate,
            endDate: cycle3.endDate,
            totalDays: cycle3.totalDays,
          },
          cycle4: {
            startDate: cycle4.startDate,
            endDate: cycle4.endDate,
            totalDays: cycle4.totalDays,
          },
          cycle5: cycle5
            ? {
                startDate: cycle5.startDate,
                currentDay: cycle5.currentDay || cycle5.totalDays,
                numbersAppeared: Object.keys(cycle5.dayByNumber).length,
                numbersRemaining:
                  10000 - Object.keys(cycle5.dayByNumber).length,
                isComplete: cycle5.isComplete,
              }
            : null,
        },
        avgCycleDays: Math.round(
          (cycle2.totalDays + cycle3.totalDays + cycle4.totalDays) / 3,
        ),
        matches: {
          exactSameDay: exactSameDay.length,
          sameDay2Cycles: sameDay2Cycles.length,
          within1Day: within1Day.length,
          within2Days: within2Days.length,
          within3Days: within3Days.length,
          within5Days: within5Days.length,
        },
        similarity,
        predictionsCount: {
          critical: predictions.filter((p) => p.urgency === "critical").length,
          high: predictions.filter((p) => p.urgency === "high").length,
          medium: predictions.filter((p) => p.urgency === "medium").length,
          low: predictions.filter((p) => p.urgency === "low").length,
          upcoming: predictions.filter((p) => p.urgency === "upcoming").length,
        },
      };

      res.json({
        summary,
        exactSameDay,
        sameDay2Cycles: sameDay2Cycles.slice(0, 200),
        within1Day: within1Day.slice(0, 200),
        within2Days: within2Days.slice(0, 300),
        within3Days: within3Days.slice(0, 400),
        within5Days: within5Days.slice(0, 500),
        dayByDayComparison,
        hotDays,
        predictions: predictions.slice(0, 500),
      });
    } catch (err) {
      console.error("❌ Day comparison error:", err);
      res.status(500).json({ error: err.message });
    }
  };
}

// ✅ Two endpoints for both collections
app.get(
  "/api/day-comparison/lotterydata",
  makeDayCycleComparisonHandler(LotteryData),
);
app.get(
  "/api/day-comparison/lotterydatanew",
  makeDayCycleComparisonHandler(LotteryDataNew),
);

//bal with 5000 compare

// Helper function to build cycle data with prize tracking
async function buildCycleData(Model) {
  const allData = await Model.find({}).lean();

  if (!allData.length) {
    return { error: "No data found" };
  }

  function parseDate(str) {
    if (!str || str === "Unknown") return new Date(0);
    const parts = String(str)
      .trim()
      .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
    if (parts) {
      return new Date(
        parseInt(parts[3], 10),
        parseInt(parts[2], 10) - 1,
        parseInt(parts[1], 10),
      );
    }
    return new Date(str);
  }

  allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

  // Build cycles
  const cycles = [];
  let currentCycle = {
    cycleNumber: 1,
    startDate: null,
    endDate: null,
    uniqueNumbers: new Set(),
    numberDetails: {},
    dateByDay: {},
  };

  let dayCounter = 0;

  for (const record of allData) {
    const date = record.date;
    const parsedDate = parseDate(date);
    if (!parsedDate || parsedDate.getTime() === 0) continue;

    if (!currentCycle.startDate) {
      currentCycle.startDate = date;
    }

    dayCounter++;
    currentCycle.dateByDay[dayCounter] = date;

    let cycleCompleted = false;

    for (const series of record.series || []) {
      const prize = series.prize;

      for (const numObj of series.numbers || []) {
        const num = numObj.number;

        if (!currentCycle.uniqueNumbers.has(num)) {
          currentCycle.uniqueNumbers.add(num);
          currentCycle.numberDetails[num] = {
            day: dayCounter,
            date,
            firstPrize: prize,
            prizeHistory: [{ prize, date, day: dayCounter }],
          };
        } else {
          currentCycle.numberDetails[num].prizeHistory.push({
            prize,
            date,
            day: dayCounter,
          });
        }

        if (currentCycle.uniqueNumbers.size === 10000) {
          currentCycle.endDate = date;
          currentCycle.totalDays = dayCounter;

          cycles.push({
            cycleNumber: currentCycle.cycleNumber,
            startDate: currentCycle.startDate,
            endDate: currentCycle.endDate,
            totalDays: currentCycle.totalDays,
            numberDetails: { ...currentCycle.numberDetails },
            dateByDay: { ...currentCycle.dateByDay },
            isComplete: true,
          });

          currentCycle = {
            cycleNumber: cycles.length + 1,
            startDate: date,
            endDate: null,
            uniqueNumbers: new Set(),
            numberDetails: {},
            dateByDay: { 1: date },
          };
          dayCounter = 1;
          cycleCompleted = true;
          break;
        }
      }

      if (cycleCompleted) break;
    }
  }

  // Push last incomplete cycle
  if (currentCycle.uniqueNumbers.size > 0) {
    currentCycle.totalDays = dayCounter;
    cycles.push({
      cycleNumber: currentCycle.cycleNumber,
      startDate: currentCycle.startDate,
      endDate: null,
      totalDays: currentCycle.totalDays,
      numberDetails: { ...currentCycle.numberDetails },
      dateByDay: { ...currentCycle.dateByDay },
      isComplete: false,
      currentDay: dayCounter,
    });
  }

  return { cycles, parseDate };
}

// Main comparison endpoint - compares BOTH databases
app.get("/api/balance-comparison", async (req, res) => {
  try {
    // Build data for both databases
    const [oldDbResult, newDbResult] = await Promise.all([
      buildCycleData(LotteryData),
      buildCycleData(LotteryDataNew),
    ]);

    if (oldDbResult.error || newDbResult.error) {
      return res.json({
        error: oldDbResult.error || newDbResult.error,
      });
    }

    const oldCycles = oldDbResult.cycles;
    const newCycles = newDbResult.cycles;

    // Get cycles 2, 3, 4, 5 from both DBs
    const getRelevantCycles = (cycles) => ({
      cycle2: cycles.find((c) => c.cycleNumber === 2),
      cycle3: cycles.find((c) => c.cycleNumber === 3),
      cycle4: cycles.find((c) => c.cycleNumber === 4),
      cycle5: cycles.find((c) => c.cycleNumber === 5),
    });

    const oldDb = getRelevantCycles(oldCycles);
    const newDb = getRelevantCycles(newCycles);

    // Function to analyze remaining numbers with ₹5000 prize
    function analyzeRemainingNumbers(cycle2, cycle3, cycle4, cycle5) {
      if (!cycle2 || !cycle3 || !cycle4) {
        return { error: "Cycles 2, 3, 4 not found" };
      }

      const remainingNumbers = [];
      const cycle5CurrentDay = cycle5?.currentDay || cycle5?.totalDays || 0;

      for (let i = 0; i < 10000; i++) {
        const num = String(i).padStart(4, "0");

        // Skip if already appeared in cycle 5
        if (cycle5?.numberDetails[num]) continue;

        const c2 = cycle2.numberDetails[num] || null;
        const c3 = cycle3.numberDetails[num] || null;
        const c4 = cycle4.numberDetails[num] || null;

        // Check ₹5000 prize appearances
        const in5000Cycle2 =
          c2?.prizeHistory?.some((p) => p.prize === 5000) || false;
        const in5000Cycle3 =
          c3?.prizeHistory?.some((p) => p.prize === 5000) || false;
        const in5000Cycle4 =
          c4?.prizeHistory?.some((p) => p.prize === 5000) || false;

        const prize5000Count = [
          in5000Cycle2,
          in5000Cycle3,
          in5000Cycle4,
        ].filter(Boolean).length;

        // Get ₹5000 prize details
        const prize5000Details = {
          cycle2: c2?.prizeHistory?.find((p) => p.prize === 5000) || null,
          cycle3: c3?.prizeHistory?.find((p) => p.prize === 5000) || null,
          cycle4: c4?.prizeHistory?.find((p) => p.prize === 5000) || null,
        };

        // Calculate stats for first appearance (any prize)
        const days = [c2?.day, c3?.day, c4?.day].filter(
          (d) => d !== null && d !== undefined,
        );
        const avgDay =
          days.length > 0
            ? Math.round(days.reduce((a, b) => a + b, 0) / days.length)
            : null;
        const minDay = days.length > 0 ? Math.min(...days) : null;
        const maxDay = days.length > 0 ? Math.max(...days) : null;
        const range =
          minDay !== null && maxDay !== null ? maxDay - minDay : null;

        // Calculate stats for ₹5000 prize appearances
        const prize5000Days = [
          prize5000Details.cycle2?.day,
          prize5000Details.cycle3?.day,
          prize5000Details.cycle4?.day,
        ].filter((d) => d !== null && d !== undefined);

        const prize5000AvgDay =
          prize5000Days.length > 0
            ? Math.round(
                prize5000Days.reduce((a, b) => a + b, 0) / prize5000Days.length,
              )
            : null;

        // Urgency calculation
        const daysOverdue = avgDay !== null ? cycle5CurrentDay - avgDay : null;
        let urgency = "unknown";
        if (daysOverdue !== null) {
          if (daysOverdue > 50) urgency = "critical";
          else if (daysOverdue > 30) urgency = "high";
          else if (daysOverdue > 15) urgency = "medium";
          else if (daysOverdue > 0) urgency = "low";
          else urgency = "upcoming";
        }

        // Consistency score
        let consistencyScore = 0;
        if (range !== null) {
          if (range === 0) consistencyScore = 100;
          else if (range <= 2) consistencyScore = 95;
          else if (range <= 5) consistencyScore = 85;
          else if (range <= 10) consistencyScore = 70;
          else if (range <= 20) consistencyScore = 50;
          else consistencyScore = 30;
        }

        remainingNumbers.push({
          number: num,
          cycle2: c2
            ? {
                day: c2.day,
                date: c2.date,
                firstPrize: c2.firstPrize,
                in5000: in5000Cycle2,
                prize5000Day: prize5000Details.cycle2?.day || null,
                prize5000Date: prize5000Details.cycle2?.date || null,
              }
            : null,
          cycle3: c3
            ? {
                day: c3.day,
                date: c3.date,
                firstPrize: c3.firstPrize,
                in5000: in5000Cycle3,
                prize5000Day: prize5000Details.cycle3?.day || null,
                prize5000Date: prize5000Details.cycle3?.date || null,
              }
            : null,
          cycle4: c4
            ? {
                day: c4.day,
                date: c4.date,
                firstPrize: c4.firstPrize,
                in5000: in5000Cycle4,
                prize5000Day: prize5000Details.cycle4?.day || null,
                prize5000Date: prize5000Details.cycle4?.date || null,
              }
            : null,
          stats: {
            avgDay,
            minDay,
            maxDay,
            range,
            consistencyScore,
            appearedInCycles: days.length,
          },
          prize5000: {
            count: prize5000Count,
            avgDay: prize5000AvgDay,
            days: prize5000Days,
            inCycle2: in5000Cycle2,
            inCycle3: in5000Cycle3,
            inCycle4: in5000Cycle4,
          },
          prediction: {
            expectedDay: avgDay,
            currentDay: cycle5CurrentDay,
            daysOverdue: daysOverdue !== null ? Math.max(0, daysOverdue) : null,
            urgency,
          },
        });
      }

      // Sort by ₹5000 count desc, then by urgency
      const urgencyOrder = {
        critical: 0,
        high: 1,
        medium: 2,
        low: 3,
        upcoming: 4,
        unknown: 5,
      };
      remainingNumbers.sort((a, b) => {
        if (b.prize5000.count !== a.prize5000.count) {
          return b.prize5000.count - a.prize5000.count;
        }
        return (
          urgencyOrder[a.prediction.urgency] -
          urgencyOrder[b.prediction.urgency]
        );
      });

      // Summary
      const summary = {
        totalRemaining: remainingNumbers.length,
        cycle5CurrentDay,
        in5000AllThree: remainingNumbers.filter((n) => n.prize5000.count === 3)
          .length,
        in5000Two: remainingNumbers.filter((n) => n.prize5000.count === 2)
          .length,
        in5000One: remainingNumbers.filter((n) => n.prize5000.count === 1)
          .length,
        in5000None: remainingNumbers.filter((n) => n.prize5000.count === 0)
          .length,
        urgencyBreakdown: {
          critical: remainingNumbers.filter(
            (n) => n.prediction.urgency === "critical",
          ).length,
          high: remainingNumbers.filter((n) => n.prediction.urgency === "high")
            .length,
          medium: remainingNumbers.filter(
            (n) => n.prediction.urgency === "medium",
          ).length,
          low: remainingNumbers.filter((n) => n.prediction.urgency === "low")
            .length,
          upcoming: remainingNumbers.filter(
            (n) => n.prediction.urgency === "upcoming",
          ).length,
        },
      };

      return {
        summary,
        remainingNumbers,
        // Pre-filtered lists
        in5000All: remainingNumbers.filter((n) => n.prize5000.count === 3),
        in5000Two: remainingNumbers.filter((n) => n.prize5000.count === 2),
        in5000One: remainingNumbers.filter((n) => n.prize5000.count === 1),
        critical: remainingNumbers.filter(
          (n) => n.prediction.urgency === "critical",
        ),
        high: remainingNumbers.filter((n) => n.prediction.urgency === "high"),
      };
    }

    // Analyze both databases
    const oldAnalysis = analyzeRemainingNumbers(
      oldDb.cycle2,
      oldDb.cycle3,
      oldDb.cycle4,
      oldDb.cycle5,
    );
    const newAnalysis = analyzeRemainingNumbers(
      newDb.cycle2,
      newDb.cycle3,
      newDb.cycle4,
      newDb.cycle5,
    );

    // Find common numbers remaining in BOTH databases
    const oldRemainingSet = new Set(
      oldAnalysis.remainingNumbers?.map((n) => n.number) || [],
    );
    const newRemainingSet = new Set(
      newAnalysis.remainingNumbers?.map((n) => n.number) || [],
    );

    const commonRemaining = [...oldRemainingSet].filter((n) =>
      newRemainingSet.has(n),
    );
    const onlyInOld = [...oldRemainingSet].filter(
      (n) => !newRemainingSet.has(n),
    );
    const onlyInNew = [...newRemainingSet].filter(
      (n) => !oldRemainingSet.has(n),
    );

    // Build comparison for common remaining numbers
    const commonComparison = commonRemaining.map((num) => {
      const oldData = oldAnalysis.remainingNumbers.find(
        (n) => n.number === num,
      );
      const newData = newAnalysis.remainingNumbers.find(
        (n) => n.number === num,
      );

      return {
        number: num,
        old: oldData,
        new: newData,
        combined: {
          // Combine ₹5000 counts from both DBs
          totalPrize5000Appearances:
            (oldData?.prize5000.count || 0) + (newData?.prize5000.count || 0),
          avgOfAvgDays:
            oldData?.stats.avgDay && newData?.stats.avgDay
              ? Math.round((oldData.stats.avgDay + newData.stats.avgDay) / 2)
              : oldData?.stats.avgDay || newData?.stats.avgDay || null,
        },
      };
    });

    // Sort common comparison by total ₹5000 appearances
    commonComparison.sort((a, b) => {
      if (
        b.combined.totalPrize5000Appearances !==
        a.combined.totalPrize5000Appearances
      ) {
        return (
          b.combined.totalPrize5000Appearances -
          a.combined.totalPrize5000Appearances
        );
      }
      // Then by urgency (using old DB urgency as reference)
      const urgencyOrder = {
        critical: 0,
        high: 1,
        medium: 2,
        low: 3,
        upcoming: 4,
        unknown: 5,
      };
      return (
        urgencyOrder[a.old?.prediction.urgency || "unknown"] -
        urgencyOrder[b.old?.prediction.urgency || "unknown"]
      );
    });

    // Cycle info summary
    const cycleInfo = {
      lotteryData: {
        cycle2: oldDb.cycle2
          ? {
              startDate: oldDb.cycle2.startDate,
              endDate: oldDb.cycle2.endDate,
              totalDays: oldDb.cycle2.totalDays,
            }
          : null,
        cycle3: oldDb.cycle3
          ? {
              startDate: oldDb.cycle3.startDate,
              endDate: oldDb.cycle3.endDate,
              totalDays: oldDb.cycle3.totalDays,
            }
          : null,
        cycle4: oldDb.cycle4
          ? {
              startDate: oldDb.cycle4.startDate,
              endDate: oldDb.cycle4.endDate,
              totalDays: oldDb.cycle4.totalDays,
            }
          : null,
        cycle5: oldDb.cycle5
          ? {
              startDate: oldDb.cycle5.startDate,
              currentDay: oldDb.cycle5.currentDay || oldDb.cycle5.totalDays,
              isComplete: oldDb.cycle5.isComplete,
            }
          : null,
      },
      lotteryDataNew: {
        cycle2: newDb.cycle2
          ? {
              startDate: newDb.cycle2.startDate,
              endDate: newDb.cycle2.endDate,
              totalDays: newDb.cycle2.totalDays,
            }
          : null,
        cycle3: newDb.cycle3
          ? {
              startDate: newDb.cycle3.startDate,
              endDate: newDb.cycle3.endDate,
              totalDays: newDb.cycle3.totalDays,
            }
          : null,
        cycle4: newDb.cycle4
          ? {
              startDate: newDb.cycle4.startDate,
              endDate: newDb.cycle4.endDate,
              totalDays: newDb.cycle4.totalDays,
            }
          : null,
        cycle5: newDb.cycle5
          ? {
              startDate: newDb.cycle5.startDate,
              currentDay: newDb.cycle5.currentDay || newDb.cycle5.totalDays,
              isComplete: newDb.cycle5.isComplete,
            }
          : null,
      },
    };

    res.json({
      cycleInfo,
      comparison: {
        commonRemainingCount: commonRemaining.length,
        onlyInOldCount: onlyInOld.length,
        onlyInNewCount: onlyInNew.length,
      },
      lotteryData: oldAnalysis,
      lotteryDataNew: newAnalysis,
      commonRemaining: commonComparison,
      onlyInOld: onlyInOld.slice(0, 200),
      onlyInNew: onlyInNew.slice(0, 200),
      // Top predictions (common numbers with ₹5000 history)
      topPredictions: commonComparison
        .filter((c) => c.combined.totalPrize5000Appearances > 0)
        .slice(0, 100),
    });
  } catch (err) {
    console.error("❌ Balance comparison error:", err);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/cycles/balance/:dbKey", async (req, res) => {
  try {
    const { dbKey } = req.params;
    const Model = dbKey === "old" ? LotteryData : LotteryDataNew;
    const allData = await Model.find({}).lean();

    if (!allData.length) return res.json({ error: "No data found" });

    function parseDate(str) {
      if (!str || str === "Unknown") return new Date(0);
      const parts = String(str)
        .trim()
        .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
      if (parts) {
        return new Date(
          parseInt(parts[3], 10),
          parseInt(parts[2], 10) - 1,
          parseInt(parts[1], 10),
        );
      }
      return new Date(str);
    }

    function diffDays(a, b) {
      const ms = parseDate(b).getTime() - parseDate(a).getTime();
      return Math.ceil(ms / (1000 * 60 * 60 * 24));
    }

    allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

    // ── Build cycles ──────────────────────────────────────────────────────
    function freshCycle(num, startDate = null) {
      return {
        cycleNumber: num,
        startDate,
        endDate: null,
        totalDays: 0,
        uniqueNumbers: new Set(),
        // prize -> Set of numbers seen under that prize
        prizeNumbers: new Map(),
        numberFirstSeen: {}, // num -> { date, dayOfCycle, prize }
      };
    }

    const builtCycles = [];
    let cur = freshCycle(1);

    for (const record of allData) {
      const date = record.date;
      const pd = parseDate(date);
      if (!pd || pd.getTime() === 0) continue;
      if (!cur.startDate) cur.startDate = date;

      const dayOfCycle = diffDays(cur.startDate, date);
      let cycleCompleted = false;

      for (const series of record.series || []) {
        const prize = series.prize;
        if (!cur.prizeNumbers.has(prize))
          cur.prizeNumbers.set(prize, new Set());
        const prizeSet = cur.prizeNumbers.get(prize);

        for (const numObj of series.numbers || []) {
          const num = numObj.number;

          if (!cur.uniqueNumbers.has(num)) {
            cur.uniqueNumbers.add(num);
            cur.numberFirstSeen[num] = { date, dayOfCycle, prize };
          }
          if (!prizeSet.has(num)) prizeSet.add(num);

          if (cur.uniqueNumbers.size === 10000) {
            cur.endDate = date;
            cur.totalDays = diffDays(cur.startDate, date);
            builtCycles.push({ ...cur });
            cur = freshCycle(builtCycles.length + 1, date);
            cycleCompleted = true;
            break;
          }
        }
        if (cycleCompleted) break;
      }
    }

    if (cur.uniqueNumbers.size > 0) {
      const lastDate = allData[allData.length - 1]?.date || null;
      cur.totalDays = lastDate ? diffDays(cur.startDate, lastDate) : 0;
      builtCycles.push({ ...cur });
    }

    // ── Grab cycle 5 ─────────────────────────────────────────────────────
    const c5 = builtCycles.find((c) => c.cycleNumber === 5) || null;

    if (!c5) {
      return res.json({
        dbKey,
        error: "Cycle 5 not found",
        cycles: builtCycles.map((c) => ({
          cycleNumber: c.cycleNumber,
          startDate: c.startDate,
          endDate: c.endDate,
          totalDays: c.totalDays,
          totalUniqueNumbers: c.uniqueNumbers.size,
          isComplete: c.uniqueNumbers.size === 10000,
        })),
      });
    }

    // ── All 10000 possible numbers ────────────────────────────────────────
    const ALL = [];
    for (let i = 0; i <= 9999; i++) ALL.push(String(i).padStart(4, "0"));

    // ── Seen / Balance sets for cycle 5 ──────────────────────────────────
    const seenInC5 = c5.uniqueNumbers;
    const balanceNums = ALL.filter((n) => !seenInC5.has(n)); // NOT yet in C5

    // ── Available prize categories (sorted high→low) ──────────────────────
    const allPrizes = Array.from(
      new Set(allData.flatMap((r) => (r.series || []).map((s) => s.prize))),
    ).sort((a, b) => b - a);

    const TOP_PRIZE = allPrizes[0]; // e.g. 5000

    // ── Numbers seen under TOP PRIZE in cycle 5 ───────────────────────────
    const topPrizeC5Set = c5.prizeNumbers.get(TOP_PRIZE) || new Set();

    // ── For each balance number — enrich with: ────────────────────────────
    // • which prize categories it appeared in (across ALL cycles in this DB)
    // • was it ever in the top prize category (historical)
    // • how many cycles it appeared in (c2, c3, c4)

    const c2 = builtCycles.find((c) => c.cycleNumber === 2) || null;
    const c3 = builtCycles.find((c) => c.cycleNumber === 3) || null;
    const c4 = builtCycles.find((c) => c.cycleNumber === 4) || null;

    const topC2 = c2?.prizeNumbers.get(TOP_PRIZE) || new Set();
    const topC3 = c3?.prizeNumbers.get(TOP_PRIZE) || new Set();
    const topC4 = c4?.prizeNumbers.get(TOP_PRIZE) || new Set();

    // ── Per-prize balance count ───────────────────────────────────────────
    // For each prize: how many balance numbers appeared under it in c2/c3/c4?
    const prizeBalanceSets = {};
    for (const prize of allPrizes) {
      const inC2 = c2?.prizeNumbers.get(prize) || new Set();
      const inC3 = c3?.prizeNumbers.get(prize) || new Set();
      const inC4 = c4?.prizeNumbers.get(prize) || new Set();

      prizeBalanceSets[prize] = {
        inC2: new Set(balanceNums.filter((n) => inC2.has(n))),
        inC3: new Set(balanceNums.filter((n) => inC3.has(n))),
        inC4: new Set(balanceNums.filter((n) => inC4.has(n))),
        // balance numbers that appeared in top prize in all 3 reference cycles
        inAll3: new Set(
          balanceNums.filter((n) => inC2.has(n) && inC3.has(n) && inC4.has(n)),
        ),
        inAny2: new Set(
          balanceNums.filter((n) => {
            const count = [inC2.has(n), inC3.has(n), inC4.has(n)].filter(
              Boolean,
            ).length;
            return count >= 2;
          }),
        ),
      };
    }

    // ── Build enriched balance list ───────────────────────────────────────
    const balanceList = balanceNums.map((num) => {
      const inTopC2 = topC2.has(num);
      const inTopC3 = topC3.has(num);
      const inTopC4 = topC4.has(num);
      const topPrizeCount = [inTopC2, inTopC3, inTopC4].filter(Boolean).length;

      const e2 = c2?.numberFirstSeen[num] || null;
      const e3 = c3?.numberFirstSeen[num] || null;
      const e4 = c4?.numberFirstSeen[num] || null;
      const appearedIn = [e2, e3, e4].filter(Boolean).length;

      const days = [e2, e3, e4].filter(Boolean).map((e) => e.dayOfCycle);
      const avgDay = days.length
        ? Math.round((days.reduce((a, b) => a + b, 0) / days.length) * 10) / 10
        : null;

      const prediction =
        appearedIn === 3
          ? "HIGH"
          : appearedIn === 2
            ? "MEDIUM"
            : appearedIn === 1
              ? "LOW"
              : "NEW";

      return {
        number: num,
        prediction,
        appearedIn,
        avgDay,
        topPrizeCount, // how many of C2/C3/C4 had it under top prize
        inTopPrizeC2: inTopC2,
        inTopPrizeC3: inTopC3,
        inTopPrizeC4: inTopC4,
        c2: e2 ? { day: e2.dayOfCycle, date: e2.date, prize: e2.prize } : null,
        c3: e3 ? { day: e3.dayOfCycle, date: e3.date, prize: e3.prize } : null,
        c4: e4 ? { day: e4.dayOfCycle, date: e4.date, prize: e4.prize } : null,
      };
    });

    // sort: top prize 3 cycles first → HIGH → avg day
    balanceList.sort((a, b) => {
      if (b.topPrizeCount !== a.topPrizeCount)
        return b.topPrizeCount - a.topPrizeCount;
      const predOrder = { HIGH: 0, MEDIUM: 1, LOW: 2, NEW: 3 };
      if (predOrder[a.prediction] !== predOrder[b.prediction])
        return predOrder[a.prediction] - predOrder[b.prediction];
      return (a.avgDay ?? 9999) - (b.avgDay ?? 9999);
    });

    // ── Per prize summary stats ───────────────────────────────────────────
    const prizeSummary = allPrizes.map((prize) => {
      const bs = prizeBalanceSets[prize];
      const c5p = c5.prizeNumbers.get(prize) || new Set();
      return {
        prize,
        seenInC5: c5p.size,
        balanceCount:
          bs.inC2.size || bs.inC3.size || bs.inC4.size
            ? [...new Set([...bs.inC2, ...bs.inC3, ...bs.inC4])].filter(
                (n) => !seenInC5.has(n),
              ).length
            : 0,
        inAll3Cycles: bs.inAll3.size,
        inAny2Cycles: bs.inAny2.size,
        top: prize === TOP_PRIZE,
      };
    });

    // ── Top prize breakdown ───────────────────────────────────────────────
    const topPrizeBalance = balanceList.filter((n) => n.topPrizeCount > 0);
    const topPrizeAll3 = balanceList.filter((n) => n.topPrizeCount === 3);
    const topPrizeAny2 = balanceList.filter((n) => n.topPrizeCount >= 2);
    const highNotTop = balanceList.filter(
      (n) => n.prediction === "HIGH" && n.topPrizeCount === 0,
    );

    // last date seen in c5
    const c5Dates = Object.values(c5.numberFirstSeen).map((e) => e.date);
    c5Dates.sort((a, b) => parseDate(b) - parseDate(a));
    const lastDateC5 = c5Dates[0] || null;

    res.json({
      dbKey,
      topPrize: TOP_PRIZE,
      allPrizes,
      c5Status: {
        startDate: c5.startDate,
        endDate: c5.endDate || null,
        lastDate: lastDateC5,
        totalDays: c5.totalDays,
        totalUniqueNumbers: seenInC5.size,
        isComplete: seenInC5.size === 10000,
        balanceCount: balanceNums.length,
        topPrizeSeenCount: topPrizeC5Set.size,
      },
      prizeSummary,
      summary: {
        totalBalance: balanceNums.length,
        topPrizeAll3: topPrizeAll3.length,
        topPrizeAny2: topPrizeAny2.length,
        topPrizeAny1: topPrizeBalance.length,
        highPrediction: balanceList.filter((n) => n.prediction === "HIGH")
          .length,
        mediumPrediction: balanceList.filter((n) => n.prediction === "MEDIUM")
          .length,
        lowPrediction: balanceList.filter((n) => n.prediction === "LOW").length,
        newNumbers: balanceList.filter((n) => n.prediction === "NEW").length,
        highNotTop: highNotTop.length,
      },
      balanceList,
      // quick access groups
      topPrizeAll3,
      topPrizeAny2: topPrizeAny2.filter((n) => n.topPrizeCount === 2),
      highNotTop,
    });
  } catch (err) {
    console.error("❌ Balance error:", err);
    res.status(500).json({ error: err.message });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// BACKTRACK HANDLER
// Returns all cycles with numbers ordered LAST-NEW → FIRST-NEW (reversed discovery)
// ─────────────────────────────────────────────────────────────────────────────
function makeBacktrackHandler(Model) {
  return async (req, res) => {
    try {
      const allData = await Model.find({}).lean();

      if (!allData.length) {
        return res.json({
          summary: {
            totalCycles: 0,
            completedCycles: 0,
            incompleteCycles: 0,
            firstDay: "Unknown",
            lastDay: "Unknown",
          },
          cycles: [],
        });
      }

      // ── helpers ──────────────────────────────────────────────────────────
      function parseDate(str) {
        if (!str || str === "Unknown") return new Date(0);
        const p = String(str)
          .trim()
          .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
        if (p)
          return new Date(
            parseInt(p[3], 10),
            parseInt(p[2], 10) - 1,
            parseInt(p[1], 10),
          );
        return new Date(str);
      }

      function norm(n) {
        return String(n).padStart(4, "0");
      }

      function daysBetween(a, b) {
        return Math.ceil((parseDate(b) - parseDate(a)) / (1000 * 60 * 60 * 24));
      }

      // ── sort records chronologically ──────────────────────────────────────
      allData.sort((a, b) => parseDate(a.date) - parseDate(b.date));

      // ── cycle builder ─────────────────────────────────────────────────────
      const cycles = [];

      let cur = freshCycle(1);

      function freshCycle(num) {
        return {
          cycleNumber: num,
          startDate: null,
          uniqueNumbers: new Set(),
          // Each entry: { number, date, prize, position (1-based, chronological) }
          discoveryOrder: [],
        };
      }

      function finalizeCycle(cycle, endDate, isComplete) {
        // ── reversed flat order ───────────────────────────────────────────
        const backtrackOrder = [...cycle.discoveryOrder].reverse();

        // ── build reversed-daily map ──────────────────────────────────────
        // key = date string, value = array of { number, prize }
        const dailyMap = new Map();
        for (const item of cycle.discoveryOrder) {
          if (!dailyMap.has(item.date)) dailyMap.set(item.date, []);
          dailyMap
            .get(item.date)
            .push({ number: item.number, prize: item.prize });
        }

        // sort dates newest → oldest
        const sortedDates = [...dailyMap.keys()].sort(
          (a, b) => parseDate(b) - parseDate(a),
        );

        const reversedDailyProgress = sortedDates.map((date) => {
          const nums = dailyMap.get(date);
          // within each day also reverse (last-added first)
          const reversed = [...nums].reverse();

          // group by prize inside this day
          const byPrize = {};
          for (const x of reversed) {
            if (!byPrize[x.prize]) byPrize[x.prize] = [];
            byPrize[x.prize].push(x.number);
          }

          return {
            date,
            count: nums.length,
            numbersAdded: reversed, // flat reversed list
            byPrize, // { 5000: ["1234","..."], ... }
          };
        });

        // ── prize-level stats ─────────────────────────────────────────────
        const prizeMap = new Map();
        for (const item of cycle.discoveryOrder) {
          if (!prizeMap.has(item.prize))
            prizeMap.set(item.prize, {
              numbers: new Set(),
              firstDate: item.date,
              lastDate: item.date,
            });
          const ps = prizeMap.get(item.prize);
          ps.numbers.add(item.number);
          ps.lastDate = item.date; // discoveryOrder is chronological so last wins
        }

        const prizes = [...prizeMap.entries()]
          .map(([prize, ps]) => ({
            prize,
            totalUniqueNumbers: ps.numbers.size,
            percentComplete: Number(
              ((ps.numbers.size / 10000) * 100).toFixed(2),
            ),
            isComplete: ps.numbers.size === 10000,
            startDate: ps.firstDate,
            endDate: ps.numbers.size === 10000 ? ps.lastDate : null,
            remainingNumbers: Math.max(0, 10000 - ps.numbers.size),
          }))
          .sort((a, b) => b.totalUniqueNumbers - a.totalUniqueNumbers);

        const totalUnique = cycle.uniqueNumbers.size;

        return {
          cycleNumber: cycle.cycleNumber,
          startDate: cycle.startDate,
          endDate: isComplete ? endDate : null,
          isComplete,
          totalDays:
            cycle.startDate && endDate
              ? daysBetween(cycle.startDate, endDate)
              : 0,
          totalUniqueNumbers: totalUnique,
          remainingNumbers: Math.max(0, 10000 - totalUnique),
          backtrackOrder, // ← reversed discovery (last-new first)
          reversedDailyProgress, // ← days newest first, numbers reversed within day
          prizes,
        };
      }

      // ── main loop ─────────────────────────────────────────────────────────
      for (const record of allData) {
        const date = record.date;
        if (!date || parseDate(date).getTime() === 0) continue;
        if (!cur.startDate) cur.startDate = date;

        let cycleJustCompleted = false;

        outer: for (const series of record.series || []) {
          const prize = series.prize;
          for (const numObj of series.numbers || []) {
            const num = norm(numObj.number);
            if (!cur.uniqueNumbers.has(num)) {
              cur.uniqueNumbers.add(num);
              cur.discoveryOrder.push({
                number: num,
                date,
                prize,
                position: cur.discoveryOrder.length + 1,
              });

              if (cur.uniqueNumbers.size === 10000) {
                cycles.push(finalizeCycle(cur, date, true));
                cur = freshCycle(cycles.length + 1);
                cur.startDate = date;
                cycleJustCompleted = true;
                break outer;
              }
            }
          }
        }
        // (if cycleJustCompleted, remaining numbers in this record go to the new cycle
        //  – to be processed in the NEXT record iteration)
      }

      // push last incomplete cycle
      if (cur.uniqueNumbers.size > 0) {
        const lastDate = allData[allData.length - 1]?.date || null;
        cycles.push(finalizeCycle(cur, lastDate, false));
      }

      // ── summary ───────────────────────────────────────────────────────────
      const completedCycles = cycles.filter((c) => c.isComplete).length;

      res.json({
        summary: {
          totalCycles: cycles.length,
          completedCycles,
          incompleteCycles: cycles.length - completedCycles,
          firstDay: allData[0]?.date || "Unknown",
          lastDay: allData[allData.length - 1]?.date || "Unknown",
        },
        cycles,
      });
    } catch (err) {
      console.error("❌ Backtrack error:", err);
      res.status(500).json({ error: err.message });
    }
  };
}

// ── Register routes ──────────────────────────────────────────────────────────
app.get("/api/cycles/backtrack/lotterydata", makeBacktrackHandler(LotteryData));
app.get(
  "/api/cycles/backtrack/lotterydatanew",
  makeBacktrackHandler(LotteryDataNew),
);

//
//some tests

// ─────────────────────────────────────────────────────────────────────────────
// ANALYSIS ENGINE (20 tests) — single-file index.js version
// Routes:
//   GET /api/analysis/lotterydata
//   GET /api/analysis/lotterydatanew
// Optional query:
//   ?date=DD/MM/YYYY
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// ANALYSIS ENGINE (index.js)
// Routes:
//   /api/analysis/lotterydata
//   /api/analysis/lotterydatanew
// Query: ?date=DD/MM/YYYY
// ─────────────────────────────────────────────────────────────────────────────

function makeAnalysisHandler(Model) {
  return async (req, res) => {
    try {
      const allData = await Model.find({}).lean();

      if (!allData.length) {
        return res.json({
          ok: true,
          summary: { firstDate: null, lastDate: null, totalDays: 0 },
          meta: { invalidDateCount: 0, invalidDateExamples: [] },
          targetDate: null,
          totalNumbers: 0,
          availableDates: [],
          anomalies: [],
          anomalyCount: 0,
          tests: {},
        });
      }

      // ── helpers ──────────────────────────────────────────────────────
      function norm4(n) {
        return String(n).padStart(4, "0");
      }

      // ✅ FIXED: must capture DD, MM, YYYY (3 groups)
      // Handles: "11/07/2020", "11-07-2020", "11.07.2020", also "11/7/2020"
      function parseDateKey(str) {
        if (!str || str === "Unknown") return null;
        const s = String(str).trim();

        const m = s.match(
          /^(\d{1,2})\s*[\/\-\.]\s*(\d{1,2})\s*[\/\-\.]\s*(\d{2,4})$/,
        );
        if (!m) return null;

        const dd = parseInt(m[1], 10);
        const mm = parseInt(m[2], 10);
        let yy = parseInt(m[3], 10);

        if (
          !Number.isFinite(dd) ||
          !Number.isFinite(mm) ||
          !Number.isFinite(yy)
        )
          return null;

        // normalize 2-digit years to 2000+
        if (yy < 100) yy += 2000;

        // validate using UTC (prevents timezone rollovers)
        const t = Date.UTC(yy, mm - 1, dd);
        const d = new Date(t);

        // reject invalid dates like 31/02/2026
        if (
          d.getUTCFullYear() !== yy ||
          d.getUTCMonth() !== mm - 1 ||
          d.getUTCDate() !== dd
        ) {
          return null;
        }

        const key =
          String(dd).padStart(2, "0") +
          "/" +
          String(mm).padStart(2, "0") +
          "/" +
          String(yy).padStart(4, "0");

        return { key, time: t, dd, mm, yy };
      }

      function isPrime(n) {
        if (n < 2) return false;
        if (n < 4) return true;
        if (n % 2 === 0 || n % 3 === 0) return false;
        for (let i = 5; i * i <= n; i += 6) {
          if (n % i === 0 || n % (i + 2) === 0) return false;
        }
        return true;
      }

      // ── group numbers by canonical date key ──────────────────────────
      const dayMap = new Map(); // dateKey -> Set("0000")
      const dayPrizeMap = new Map(); // dateKey -> { [prize]: Set("0000") }
      const dayTimeMap = new Map(); // dateKey -> utcMillis

      let invalidDateCount = 0;
      const invalidDateExamples = new Set();

      for (const record of allData) {
        const parsed = parseDateKey(record.date);

        if (!parsed) {
          invalidDateCount++;
          if (invalidDateExamples.size < 10 && record.date) {
            invalidDateExamples.add(String(record.date));
          }
          continue;
        }

        const dateKey = parsed.key;

        if (!dayMap.has(dateKey)) dayMap.set(dateKey, new Set());
        if (!dayPrizeMap.has(dateKey)) dayPrizeMap.set(dateKey, {});
        if (!dayTimeMap.has(dateKey)) dayTimeMap.set(dateKey, parsed.time);

        for (const series of record.series || []) {
          const prize = series.prize;

          const prizeObj = dayPrizeMap.get(dateKey);
          if (!prizeObj[prize]) prizeObj[prize] = new Set();

          for (const numObj of series.numbers || []) {
            const num = norm4(numObj.number);
            dayMap.get(dateKey).add(num);
            prizeObj[prize].add(num);
          }
        }
      }

      const dates = [...dayMap.keys()].sort(
        (a, b) => dayTimeMap.get(a) - dayTimeMap.get(b),
      );

      if (!dates.length) {
        return res.json({
          ok: true,
          summary: { firstDate: null, lastDate: null, totalDays: 0 },
          meta: {
            invalidDateCount,
            invalidDateExamples: [...invalidDateExamples],
          },
          targetDate: null,
          totalNumbers: 0,
          availableDates: [],
          anomalies: [],
          anomalyCount: 0,
          tests: {},
        });
      }

      const firstDate = dates[0];
      const lastDate = dates[dates.length - 1];

      // canonicalize requested date too
      const requestedKey = req.query.date
        ? parseDateKey(req.query.date)?.key
        : null;

      const targetDate =
        requestedKey && dayMap.has(requestedKey) ? requestedKey : lastDate;

      const targetNumsStrSet = dayMap.get(targetDate);
      if (!targetNumsStrSet || targetNumsStrSet.size === 0) {
        return res.json({
          ok: false,
          error: `No data for date: ${req.query.date || targetDate}`,
          availableDates: dates,
          summary: { firstDate, lastDate, totalDays: dates.length },
          meta: {
            invalidDateCount,
            invalidDateExamples: [...invalidDateExamples],
          },
        });
      }

      const nums = [...targetNumsStrSet]
        .map((x) => parseInt(x, 10))
        .filter(Number.isFinite)
        .sort((a, b) => a - b);
      const numsStr = nums.map(norm4);
      const numSet = new Set(nums);
      const count = nums.length;

      // ════════════════════════════════════════════════════════════════
      // TEST 1: BASIC STATS
      // ════════════════════════════════════════════════════════════════
      const sum = nums.reduce((a, b) => a + b, 0);
      const mean = sum / (count || 1);
      const variance =
        nums.reduce((a, b) => a + (b - mean) ** 2, 0) / (count || 1);
      const stdDev = Math.sqrt(variance);
      const median =
        count % 2 === 0
          ? (nums[count / 2 - 1] + nums[count / 2]) / 2
          : nums[Math.floor(count / 2)];

      const basicStats = {
        count,
        min: nums[0] ?? null,
        max: nums[nums.length - 1] ?? null,
        sum,
        mean: +mean.toFixed(2),
        median,
        stdDev: +stdDev.toFixed(2),
        variance: +variance.toFixed(2),
        expectedMean: 4999.5,
        expectedStdDev: 2886.75,
        meanDeviation: +(mean - 4999.5).toFixed(2),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 2: DIGIT POSITION FREQUENCY
      // ════════════════════════════════════════════════════════════════
      const digitFreq = Array.from({ length: 4 }, () => ({
        0: 0,
        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
        7: 0,
        8: 0,
        9: 0,
      }));

      for (const s of numsStr) {
        for (let pos = 0; pos < 4; pos++)
          digitFreq[pos][parseInt(s[pos], 10)]++;
      }

      const expectedPerDigit = count / 10;
      const digitAnalysis = digitFreq.map((freq, pos) => {
        const entries = Object.entries(freq).map(([digit, f]) => ({
          digit: +digit,
          frequency: f,
          expected: +expectedPerDigit.toFixed(2),
          deviation: +(f - expectedPerDigit).toFixed(2),
          deviationPercent: expectedPerDigit
            ? +(((f - expectedPerDigit) / expectedPerDigit) * 100).toFixed(1)
            : 0,
        }));

        const chiSquared = entries.reduce(
          (acc, e) =>
            acc +
            (e.frequency - expectedPerDigit) ** 2 / (expectedPerDigit || 1),
          0,
        );

        const biasedDigits = entries
          .filter((e) => Math.abs(e.deviationPercent) > 15)
          .sort(
            (a, b) =>
              Math.abs(b.deviationPercent) - Math.abs(a.deviationPercent),
          );

        return {
          position: pos + 1,
          positionLabel: ["Thousands", "Hundreds", "Tens", "Units"][pos],
          frequencies: entries,
          chiSquared: +chiSquared.toFixed(2),
          isSignificant: chiSquared > 16.92,
          biasedDigits,
        };
      });

      // ════════════════════════════════════════════════════════════════
      // TEST 3: DIGIT SUM DISTRIBUTION
      // ════════════════════════════════════════════════════════════════
      const digitSums = {};
      for (const s of numsStr) {
        const dsum = s.split("").reduce((a, d) => a + parseInt(d, 10), 0);
        digitSums[dsum] = (digitSums[dsum] || 0) + 1;
      }

      const avgDigitSum =
        numsStr.reduce(
          (a, s) => a + s.split("").reduce((x, d) => x + parseInt(d, 10), 0),
          0,
        ) / (count || 1);

      const digitSumAnalysis = {
        distribution: Object.entries(digitSums)
          .map(([s, f]) => ({ digitSum: +s, frequency: f }))
          .sort((a, b) => a.digitSum - b.digitSum),
        averageDigitSum: +avgDigitSum.toFixed(2),
        expectedAverage: 18,
        peakDigitSum: Object.entries(digitSums).sort((a, b) => b[1] - a[1])[0],
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 4: MODULAR ARITHMETIC
      // ════════════════════════════════════════════════════════════════
      const modTests = [
        2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 17, 19, 23, 50, 100,
      ];
      const dfCritical = {
        1: 3.84,
        2: 5.99,
        3: 7.81,
        4: 9.49,
        5: 11.07,
        6: 12.59,
        7: 14.07,
        8: 15.51,
        9: 16.92,
        10: 18.31,
        12: 21.03,
        16: 26.3,
        18: 28.87,
        22: 33.92,
        49: 66.34,
        99: 124.34,
      };

      const modularPatterns = modTests.map((m) => {
        const buckets = {};
        for (let r = 0; r < m; r++) buckets[r] = 0;
        for (const n of nums) buckets[n % m]++;

        const expected = count / m;
        const entries = Object.entries(buckets).map(([r, f]) => ({
          residue: +r,
          frequency: f,
          expected: +expected.toFixed(2),
          deviation: +(f - expected).toFixed(2),
        }));

        const chiSquared = entries.reduce(
          (acc, e) => acc + (e.frequency - expected) ** 2 / (expected || 1),
          0,
        );

        const critical = dfCritical[m - 1] || (m - 1) * 1.5;
        const isSignificant = chiSquared > critical;

        const sorted = [...entries].sort((a, b) => b.frequency - a.frequency);

        return {
          modulus: m,
          chiSquared: +chiSquared.toFixed(2),
          isSignificant,
          hotResidue: sorted[0],
          coldResidue: sorted[sorted.length - 1],
          distribution: entries,
        };
      });

      // ════════════════════════════════════════════════════════════════
      // TEST 5: EVEN / ODD
      // ════════════════════════════════════════════════════════════════
      const evenCount = nums.filter((n) => n % 2 === 0).length;
      const oddCount = count - evenCount;

      const evenOdd = {
        even: evenCount,
        odd: oddCount,
        expectedEach: +(count / 2).toFixed(1),
        ratio: +(evenCount / (oddCount || 1)).toFixed(3),
        biasDirection:
          evenCount > oddCount
            ? "EVEN"
            : evenCount < oddCount
              ? "ODD"
              : "BALANCED",
        biasPercent: +(
          (Math.abs(evenCount - oddCount) / (count || 1)) *
          100
        ).toFixed(1),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 6: GAP ANALYSIS
      // ════════════════════════════════════════════════════════════════
      const gaps = [];
      for (let i = 1; i < nums.length; i++) gaps.push(nums[i] - nums[i - 1]);

      const gapAnalysis = {
        averageGap: gaps.length
          ? +(gaps.reduce((a, b) => a + b, 0) / gaps.length).toFixed(2)
          : 0,
        expectedGap: count ? +(10000 / count).toFixed(2) : 0,
        maxGap: gaps.length ? Math.max(...gaps) : null,
        minGap: gaps.length ? Math.min(...gaps) : null,
        maxGapBetween: null,
        gapDistribution: [],
        consecutivePairsCount: 0,
        expectedConsecutivePairs: count
          ? +((count * (count - 1)) / 10000).toFixed(1)
          : 0,
        consecutivePairs: [],
      };

      if (gaps.length) {
        const maxGapIdx = gaps.indexOf(gapAnalysis.maxGap);

        const gapBuckets = {};
        for (const g of gaps) {
          const bucket = Math.floor(g / 10) * 10;
          gapBuckets[bucket] = (gapBuckets[bucket] || 0) + 1;
        }

        gapAnalysis.gapDistribution = Object.entries(gapBuckets)
          .map(([b, f]) => ({ range: `${b}-${+b + 9}`, frequency: f }))
          .sort((a, b) => parseInt(a.range, 10) - parseInt(b.range, 10));

        const consecutivePairs = [];
        for (let i = 1; i < nums.length; i++) {
          if (nums[i] - nums[i - 1] === 1)
            consecutivePairs.push([norm4(nums[i - 1]), norm4(nums[i])]);
        }
        gapAnalysis.consecutivePairsCount = consecutivePairs.length;
        gapAnalysis.consecutivePairs = consecutivePairs.slice(0, 50);

        gapAnalysis.maxGapBetween =
          maxGapIdx >= 0
            ? [norm4(nums[maxGapIdx]), norm4(nums[maxGapIdx + 1])]
            : null;
      }

      // ════════════════════════════════════════════════════════════════
      // TEST 7: COMPLEMENT PAIRS (n+m=9999)
      // ════════════════════════════════════════════════════════════════
      const complementPairs = [];
      for (const n of nums) {
        const comp = 9999 - n;
        if (comp > n && numSet.has(comp))
          complementPairs.push([norm4(n), norm4(comp)]);
      }
      const expectedComplement = (count * count) / (2 * 10000);
      const complementAnalysis = {
        pairsFound: complementPairs.length,
        expectedPairs: +expectedComplement.toFixed(1),
        isUnusual:
          Math.abs(complementPairs.length - expectedComplement) >
          3 * Math.sqrt(expectedComplement || 1),
        pairs: complementPairs.slice(0, 50),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 8: REVERSE PAIRS (abcd↔dcba)
      // ════════════════════════════════════════════════════════════════
      const reversePairs = [];
      const reverseChecked = new Set();
      for (const s of numsStr) {
        const rev = s.split("").reverse().join("");
        if (
          rev !== s &&
          !reverseChecked.has(rev) &&
          targetNumsStrSet.has(rev)
        ) {
          reversePairs.push([s, rev]);
          reverseChecked.add(s);
        }
      }
      const reverseAnalysis = {
        pairsFound: reversePairs.length,
        expectedPairs: +((count * count) / (2 * 10000)).toFixed(1),
        pairs: reversePairs.slice(0, 50),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 9: PALINDROMES
      // ════════════════════════════════════════════════════════════════
      const palindromes = numsStr.filter(
        (s) => s === s.split("").reverse().join(""),
      );
      const palindromeAnalysis = {
        count: palindromes.length,
        expected: +((count / 10000) * 100).toFixed(1),
        numbers: palindromes,
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 10: PRIMES
      // ════════════════════════════════════════════════════════════════
      const primeCount = nums.filter(isPrime).length;
      const primeAnalysis = {
        primesInSet: primeCount,
        expectedPrimes: +((count / 10000) * 1229).toFixed(1),
        totalPrimesUnder10000: 1229,
        deviation: +(primeCount - (count / 10000) * 1229).toFixed(1),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 11: DIVISIBILITY
      // ════════════════════════════════════════════════════════════════
      const divTests = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 25, 50, 100];
      const divisibility = divTests.map((d) => {
        const divisible = nums.filter((n) => n % d === 0).length;
        const expected = (count * Math.floor(10000 / d)) / 10000;
        return {
          divisor: d,
          count: divisible,
          expected: +expected.toFixed(1),
          deviation: +(divisible - expected).toFixed(1),
          deviationPercent: expected
            ? +(((divisible - expected) / expected) * 100).toFixed(1)
            : 0,
        };
      });

      // ════════════════════════════════════════════════════════════════
      // TEST 12: LAST 2 DIGITS (suffix)
      // ════════════════════════════════════════════════════════════════
      const last2 = {};
      for (const s of numsStr) {
        const l2 = s.slice(2);
        last2[l2] = (last2[l2] || 0) + 1;
      }
      const expectedLast2 = count / 100;
      const last2Sorted = Object.entries(last2)
        .map(([suffix, freq]) => ({
          suffix,
          frequency: freq,
          expected: +expectedLast2.toFixed(2),
          deviation: +(freq - expectedLast2).toFixed(2),
        }))
        .sort((a, b) => b.frequency - a.frequency);

      const last2Analysis = {
        hotSuffixes: last2Sorted.slice(0, 10),
        coldSuffixes: last2Sorted.slice(-10).reverse(),
        uniqueSuffixes: Object.keys(last2).length,
        expectedUnique: 100,
        chiSquared: +last2Sorted
          .reduce(
            (acc, e) =>
              acc + (e.frequency - expectedLast2) ** 2 / (expectedLast2 || 1),
            0,
          )
          .toFixed(2),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 13: FIRST 2 DIGITS (prefix)
      // ════════════════════════════════════════════════════════════════
      const first2 = {};
      for (const s of numsStr) {
        const f2 = s.slice(0, 2);
        first2[f2] = (first2[f2] || 0) + 1;
      }
      const expectedFirst2 = count / 100;
      const first2Sorted = Object.entries(first2)
        .map(([prefix, freq]) => ({
          prefix,
          frequency: freq,
          expected: +expectedFirst2.toFixed(2),
          deviation: +(freq - expectedFirst2).toFixed(2),
        }))
        .sort((a, b) => b.frequency - a.frequency);

      const first2Analysis = {
        hotPrefixes: first2Sorted.slice(0, 10),
        coldPrefixes: first2Sorted.slice(-10).reverse(),
        uniquePrefixes: Object.keys(first2).length,
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 14: ARITHMETIC PROGRESSION
      // ════════════════════════════════════════════════════════════════
      function findLongestAP(sortedNums) {
        const set = new Set(sortedNums);
        let bestLen = 0;
        let bestStart = 0;
        let bestDiff = 0;

        const diffs = [
          1, 2, 3, 4, 5, 7, 9, 10, 11, 13, 17, 19, 23, 25, 33, 50, 100, 111,
          1111,
        ];

        for (const d of diffs) {
          for (const start of sortedNums) {
            let len = 1;
            let curr = start + d;
            while (set.has(curr) && curr <= 9999) {
              len++;
              curr += d;
            }
            if (len > bestLen) {
              bestLen = len;
              bestStart = start;
              bestDiff = d;
            }
          }
        }

        const sequence = [];
        for (let i = 0; i < bestLen; i++)
          sequence.push(norm4(bestStart + i * bestDiff));

        return {
          length: bestLen,
          start: norm4(bestStart),
          commonDifference: bestDiff,
          sequence: sequence.slice(0, 20),
        };
      }
      const apResult = findLongestAP(nums);

      // ════════════════════════════════════════════════════════════════
      // TEST 15: REPEATING DIGITS
      // ════════════════════════════════════════════════════════════════
      const repeatingDigits = {
        allSame: numsStr.filter(
          (s) => s[0] === s[1] && s[1] === s[2] && s[2] === s[3],
        ),
        doubleDouble: numsStr.filter(
          (s) => s[0] === s[1] && s[2] === s[3] && s[0] !== s[2],
        ),
        ascending: numsStr.filter(
          (s) =>
            +s[1] === +s[0] + 1 && +s[2] === +s[1] + 1 && +s[3] === +s[2] + 1,
        ),
        descending: numsStr.filter(
          (s) =>
            +s[1] === +s[0] - 1 && +s[2] === +s[1] - 1 && +s[3] === +s[2] - 1,
        ),
        mirror: numsStr.filter((s) => s[0] === s[3] && s[1] === s[2]),
      };

      // ════════════════════════════════════════════════════════════════
      // TEST 16: QUADRANTS
      // ════════════════════════════════════════════════════════════════
      const quadrants = [
        { label: "Q1 (0000-2499)", count: 0 },
        { label: "Q2 (2500-4999)", count: 0 },
        { label: "Q3 (5000-7499)", count: 0 },
        { label: "Q4 (7500-9999)", count: 0 },
      ];
      for (const n of nums) {
        if (n < 2500) quadrants[0].count++;
        else if (n < 5000) quadrants[1].count++;
        else if (n < 7500) quadrants[2].count++;
        else quadrants[3].count++;
      }
      const expectedPerQuadrant = count / 4;
      quadrants.forEach((q) => {
        q.expected = +expectedPerQuadrant.toFixed(1);
        q.deviation = +(q.count - expectedPerQuadrant).toFixed(1);
        q.deviationPercent = expectedPerQuadrant
          ? +(
              ((q.count - expectedPerQuadrant) / expectedPerQuadrant) *
              100
            ).toFixed(1)
          : 0;
      });

      // ════════════════════════════════════════════════════════════════
      // TEST 17: CROSS-DAY OVERLAP
      // ════════════════════════════════════════════════════════════════
      const dateIdx = dates.indexOf(targetDate);
      const crossDay = {};
      if (dateIdx > 0) {
        const prevDate = dates[dateIdx - 1];
        const prevSet = dayMap.get(prevDate);
        const overlap = [...targetNumsStrSet].filter((n) => prevSet.has(n));
        crossDay.previous = {
          date: prevDate,
          overlapCount: overlap.length,
          overlapPercent: +((overlap.length / (count || 1)) * 100).toFixed(1),
          prevCount: prevSet.size,
          expectedOverlap: +((count * prevSet.size) / 10000).toFixed(1),
        };
      }
      if (dateIdx < dates.length - 1) {
        const nextDate = dates[dateIdx + 1];
        const nextSet = dayMap.get(nextDate);
        const overlap = [...targetNumsStrSet].filter((n) => nextSet.has(n));
        crossDay.next = {
          date: nextDate,
          overlapCount: overlap.length,
          overlapPercent: +((overlap.length / (count || 1)) * 100).toFixed(1),
          nextCount: nextSet.size,
          expectedOverlap: +((count * nextSet.size) / 10000).toFixed(1),
        };
      }

      // ════════════════════════════════════════════════════════════════
      // TEST 18: PRIZE COMPARISON
      // ════════════════════════════════════════════════════════════════
      const prizeData = dayPrizeMap.get(targetDate) || {};
      const prizeComparison = Object.entries(prizeData)
        .map(([prize, set]) => {
          const pnums = [...set]
            .map((n) => parseInt(n, 10))
            .filter(Number.isFinite)
            .sort((a, b) => a - b);
          if (!pnums.length) return null;

          const pcount = pnums.length;
          const psum = pnums.reduce((a, b) => a + b, 0);
          const pmean = psum / pcount;
          const pEven = pnums.filter((n) => n % 2 === 0).length;

          const pDigitSumAvg =
            pnums.reduce(
              (a, n) =>
                a +
                norm4(n)
                  .split("")
                  .reduce((x, d) => x + parseInt(d, 10), 0),
              0,
            ) / pcount;

          return {
            prize: +prize,
            count: pcount,
            mean: +pmean.toFixed(2),
            evenPercent: +((pEven / pcount) * 100).toFixed(1),
            avgDigitSum: +pDigitSumAvg.toFixed(2),
            min: norm4(pnums[0]),
            max: norm4(pnums[pnums.length - 1]),
          };
        })
        .filter(Boolean)
        .sort((a, b) => b.prize - a.prize);

      // ════════════════════════════════════════════════════════════════
      // TEST 19: SUM PAIRS
      // ════════════════════════════════════════════════════════════════
      const sumTargets = [5000, 9999, 10000];
      const sumPairs = sumTargets.map((target) => {
        const pairs = [];
        for (const n of nums) {
          const partner = target - n;
          if (
            partner > n &&
            partner >= 0 &&
            partner <= 9999 &&
            numSet.has(partner)
          ) {
            pairs.push([norm4(n), norm4(partner)]);
          }
        }
        return {
          targetSum: target,
          pairsFound: pairs.length,
          expectedPairs: +((count * count) / (2 * 10000)).toFixed(1),
          sample: pairs.slice(0, 20),
        };
      });

      // ════════════════════════════════════════════════════════════════
      // TEST 20: MULTIPLICATIVE PAIRS
      // ════════════════════════════════════════════════════════════════
      const multipliers = [2, 3, 5, 7];
      const multiplicativePatterns = multipliers.map((m) => {
        const pairs = [];
        for (const n of nums) {
          if (n === 0) continue;
          const product = n * m;
          if (product <= 9999 && numSet.has(product)) {
            pairs.push({
              base: norm4(n),
              multiplied: norm4(product),
              multiplier: m,
            });
          }
        }
        const expected = (count * count) / (m * 10000);
        const pairsFound = pairs.length;
        return {
          multiplier: m,
          pairsFound,
          expectedPairs: +expected.toFixed(1),
          isUnusual:
            Math.abs(pairsFound - expected) > 2 * Math.sqrt(expected || 1),
          sample: pairs.slice(0, 20),
        };
      });

      // ── anomalies summary ────────────────────────────────────────────
      const anomalies = [];

      for (const da of digitAnalysis) {
        if (da.isSignificant) {
          anomalies.push({
            type: "DIGIT_BIAS",
            severity: "HIGH",
            message: `Digit bias at ${da.positionLabel} (χ²=${da.chiSquared})`,
          });
        }
      }
      for (const mp of modularPatterns) {
        if (mp.isSignificant) {
          anomalies.push({
            type: "MODULAR_BIAS",
            severity: "HIGH",
            message: `Mod ${mp.modulus} significant (χ²=${mp.chiSquared}), hot r=${mp.hotResidue.residue}`,
          });
        }
      }
      if (evenOdd.biasPercent > 8) {
        anomalies.push({
          type: "EVEN_ODD_BIAS",
          severity: "MEDIUM",
          message: `${evenOdd.biasDirection} bias ${evenOdd.biasPercent}%`,
        });
      }
      if (apResult.length >= 5) {
        anomalies.push({
          type: "ARITHMETIC_PROGRESSION",
          severity: "HIGH",
          message: `Arithmetic progression length ${apResult.length} (start ${apResult.start}, diff ${apResult.commonDifference})`,
        });
      }

      return res.json({
        ok: true,
        summary: { firstDate, lastDate, totalDays: dates.length },
        meta: {
          invalidDateCount,
          invalidDateExamples: [...invalidDateExamples],
        },
        targetDate,
        totalNumbers: count,
        availableDates: dates,
        anomalies,
        anomalyCount: anomalies.length,
        tests: {
          basicStats,
          digitAnalysis,
          digitSumAnalysis,
          modularPatterns,
          evenOdd,
          gapAnalysis,
          complementAnalysis,
          reverseAnalysis,
          palindromeAnalysis,
          primeAnalysis,
          divisibility,
          last2Analysis,
          first2Analysis,
          arithmeticProgression: apResult,
          repeatingDigits,
          quadrants,
          crossDay,
          prizeComparison,
          sumPairs,
          multiplicativePatterns,
        },
      });
    } catch (err) {
      console.error("❌ Analysis error:", err);
      return res.status(500).json({ ok: false, error: err.message });
    }
  };
}

// routes
app.get("/api/analysis/lotterydata", makeAnalysisHandler(LotteryData));
app.get("/api/analysis/lotterydatanew", makeAnalysisHandler(LotteryDataNew));

//
//Prize Cycles
//
// ─────────────────────────────────────────────────────────────────────────────
// PRIZE CYCLES (per prize): 5000,2000,1000,500,200,100
// Cycle completes when a prize has seen all 10,000 numbers (0000..9999).
// Provides:
//   GET /api/prizecycles/lotterydata
//   GET /api/prizecycles/lotterydatanew
//   GET /api/prizecycles/lotterydata/cycle-details
//   GET /api/prizecycles/lotterydatanew/cycle-details
// ─────────────────────────────────────────────────────────────────────────────

const PRIZES = [5000, 2000, 1000, 500, 200, 100];
const MS_DAY = 24 * 60 * 60 * 1000;

function norm4(n) {
  return String(n).trim().padStart(4, "0");
}

// ✅ Robust DD/MM/YYYY (also DD-MM-YYYY, DD.MM.YYYY, and spaces)
function parseDateKey(str) {
  if (!str || str === "Unknown") return null;
  const s = String(str).trim();

  // DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
  const m = s.match(
    /^(\d{1,2})\s*[\/\-\.]\s*(\d{1,2})\s*[\/\-\.]\s*(\d{2,4})$/,
  );
  if (!m) return null;

  const dd = parseInt(m[1], 10);
  const mm = parseInt(m[2], 10);
  let yy = parseInt(m[3], 10);
  if (!Number.isFinite(dd) || !Number.isFinite(mm) || !Number.isFinite(yy))
    return null;

  if (yy < 100) yy += 2000;

  const t = Date.UTC(yy, mm - 1, dd);
  const d = new Date(t);

  // reject invalid calendar dates like 31/02
  if (
    d.getUTCFullYear() !== yy ||
    d.getUTCMonth() !== mm - 1 ||
    d.getUTCDate() !== dd
  )
    return null;

  const key =
    String(dd).padStart(2, "0") +
    "/" +
    String(mm).padStart(2, "0") +
    "/" +
    String(yy).padStart(4, "0");

  return { key, time: t };
}

function daysInclusive(startTime, endTime) {
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return 0;
  return Math.floor((endTime - startTime) / MS_DAY) + 1; // inclusive
}

async function loadValidRecordsSorted(Model) {
  // Pull only fields we need
  const allData = await Model.find(
    {},
    { entryNumber: 1, date: 1, series: 1 },
  ).lean();

  let invalidDateCount = 0;
  const invalidDateExamples = new Set();

  const records = [];
  for (const r of allData) {
    const pd = parseDateKey(r.date);
    if (!pd) {
      invalidDateCount++;
      if (invalidDateExamples.size < 10 && r.date)
        invalidDateExamples.add(String(r.date));
      continue;
    }
    records.push({
      entryNumber: r.entryNumber ?? 0,
      dateKey: pd.key,
      dateTime: pd.time,
      series: r.series || [],
    });
  }

  records.sort((a, b) => {
    if (a.dateTime !== b.dateTime) return a.dateTime - b.dateTime;
    return (a.entryNumber || 0) - (b.entryNumber || 0);
  });

  return {
    records,
    meta: {
      invalidDateCount,
      invalidDateExamples: [...invalidDateExamples],
    },
  };
}

// Build cycles summary for all prizes in one pass
function buildPrizeCyclesSummary(records) {
  if (!records.length) {
    return {
      summary: { firstDate: null, lastDate: null, totalDays: 0 },
      prizes: PRIZES.map((p) => ({
        prize: p,
        completedCycles: 0,
        totalCycles: 0,
        currentCycle: null,
        cycles: [],
      })),
    };
  }

  const firstDate = records[0].dateKey;
  const lastDate = records[records.length - 1].dateKey;
  const firstTime = records[0].dateTime;
  const lastTime = records[records.length - 1].dateTime;

  const state = {};
  for (const prize of PRIZES) {
    state[prize] = {
      cycleNumber: 1,
      startDate: null,
      startTime: null,
      lastSeenDate: null,
      lastSeenTime: null,
      unique: new Set(),
      cycles: [],
    };
  }

  function pushCycle(prize, endDateKey, endTime, isComplete) {
    const st = state[prize];
    const totalUnique = st.unique.size;

    st.cycles.push({
      cycleNumber: st.cycleNumber,
      prize,
      startDate: st.startDate,
      endDate: isComplete ? endDateKey : null,
      isComplete,
      totalUniqueNumbers: totalUnique,
      remainingNumbers: Math.max(0, 10000 - totalUnique),
      percentComplete: +((totalUnique / 10000) * 100).toFixed(2),
      totalDays:
        st.startTime && endTime ? daysInclusive(st.startTime, endTime) : 0,
      lastSeenDate: st.lastSeenDate,
    });

    // reset for next cycle
    st.cycleNumber += 1;
    st.startDate = null;
    st.startTime = null;
    st.lastSeenDate = null;
    st.lastSeenTime = null;
    st.unique = new Set();
  }

  for (const r of records) {
    for (const series of r.series) {
      const prize = series.prize;
      if (!PRIZES.includes(prize)) continue;

      const st = state[prize];

      for (const numObj of series.numbers || []) {
        const num = norm4(numObj.number);
        if (!/^\d{4}$/.test(num)) continue;

        if (!st.startDate) {
          st.startDate = r.dateKey;
          st.startTime = r.dateTime;
        }

        st.lastSeenDate = r.dateKey;
        st.lastSeenTime = r.dateTime;

        if (!st.unique.has(num)) {
          st.unique.add(num);

          if (st.unique.size === 10000) {
            pushCycle(prize, r.dateKey, r.dateTime, true);
          }
        }
      }
    }
  }

  // push in-progress cycles
  const prizes = PRIZES.map((prize) => {
    const st = state[prize];

    if (st.unique.size > 0) {
      pushCycle(prize, lastDate, lastTime, false); // uses lastTime for totalDays
      // pushCycle resets state; but we don’t need it again after this
    }

    const cycles = st.cycles;
    const completedCycles = cycles.filter((c) => c.isComplete).length;
    const totalCycles = cycles.length;
    const currentCycle = cycles.length ? cycles[cycles.length - 1] : null;

    return { prize, completedCycles, totalCycles, currentCycle, cycles };
  });

  return {
    summary: {
      firstDate,
      lastDate,
      totalDays: daysInclusive(firstTime, lastTime),
    },
    prizes,
  };
}

// Compute details for ONE (prize, cycle) on demand
function computePrizeCycleDetails(records, prize, targetCycleNumber) {
  let cycleNo = 1;

  let startDate = null;
  let startTime = null;
  let lastSeenDate = null;
  let lastSeenTime = null;

  let unique = new Set();

  // timeline tracking for the target cycle only
  const dayOrder = []; // [{dateKey, dateTime}]
  const dayMap = new Map(); // dateKey -> { newUnique }
  function touchDay(dateKey, dateTime) {
    if (!dayMap.has(dateKey)) {
      dayMap.set(dateKey, { newUnique: 0 });
      dayOrder.push({ dateKey, dateTime });
    }
  }

  // We scan numbers in order; if cycle completes before target, reset and continue.
  for (const r of records) {
    for (const series of r.series) {
      if (series.prize !== prize) continue;

      for (const numObj of series.numbers || []) {
        const num = norm4(numObj.number);
        if (!/^\d{4}$/.test(num)) continue;

        // If we are not at the target cycle yet, just build until completion then reset.
        if (cycleNo < targetCycleNumber) {
          if (!unique.has(num)) {
            unique.add(num);
            if (unique.size === 10000) {
              cycleNo += 1;
              unique = new Set();
            }
          }
          continue;
        }

        // Now cycleNo === targetCycleNumber: capture details
        if (!startDate) {
          startDate = r.dateKey;
          startTime = r.dateTime;
        }

        lastSeenDate = r.dateKey;
        lastSeenTime = r.dateTime;

        if (!unique.has(num)) {
          unique.add(num);

          touchDay(r.dateKey, r.dateTime);
          dayMap.get(r.dateKey).newUnique += 1;

          if (unique.size === 10000) {
            // completed here
            const endDate = r.dateKey;
            const endTime = r.dateTime;

            // build running total timeline
            let running = 0;
            const timeline = dayOrder
              .sort((a, b) => a.dateTime - b.dateTime)
              .map((d) => {
                const nu = dayMap.get(d.dateKey).newUnique;
                running += nu;
                return { date: d.dateKey, newUnique: nu, totalUnique: running };
              });

            return {
              found: true,
              cycleInfo: {
                cycleNumber: targetCycleNumber,
                prize,
                startDate,
                endDate,
                isComplete: true,
                totalUniqueNumbers: 10000,
                remainingNumbers: 0,
                percentComplete: 100,
                totalDays: daysInclusive(startTime, endTime),
                lastSeenDate,
              },
              uniqueSet: unique, // full set (10,000)
              timeline,
            };
          }
        }
      }
    }
  }

  // If we never reached target cycle
  if (cycleNo < targetCycleNumber)
    return { found: false, reason: "cycle_not_found" };

  // In-progress target cycle
  if (!startDate) {
    // target cycle exists but has no numbers (rare)
    return { found: false, reason: "cycle_empty" };
  }

  let running = 0;
  const timeline = dayOrder
    .sort((a, b) => a.dateTime - b.dateTime)
    .map((d) => {
      const nu = dayMap.get(d.dateKey).newUnique;
      running += nu;
      return { date: d.dateKey, newUnique: nu, totalUnique: running };
    });

  const totalUnique = unique.size;
  const endTime = lastSeenTime;

  return {
    found: true,
    cycleInfo: {
      cycleNumber: targetCycleNumber,
      prize,
      startDate,
      endDate: null,
      isComplete: false,
      totalUniqueNumbers: totalUnique,
      remainingNumbers: Math.max(0, 10000 - totalUnique),
      percentComplete: +((totalUnique / 10000) * 100).toFixed(2),
      totalDays: startTime && endTime ? daysInclusive(startTime, endTime) : 0,
      lastSeenDate,
    },
    uniqueSet: unique,
    timeline,
  };
}

function makePrizeCyclesHandler(Model) {
  return async (req, res) => {
    try {
      const { records, meta } = await loadValidRecordsSorted(Model);
      const built = buildPrizeCyclesSummary(records);

      return res.json({
        ok: true,
        summary: built.summary,
        meta,
        prizes: built.prizes,
      });
    } catch (err) {
      console.error("❌ prizecycles error:", err);
      return res.status(500).json({ ok: false, error: err.message });
    }
  };
}

// cycle-details endpoint: mode=stats | remaining | timeline
function makePrizeCycleDetailsHandler(Model) {
  return async (req, res) => {
    try {
      const prize = parseInt(req.query.prize, 10);
      const cycle = parseInt(req.query.cycle, 10);
      const mode = String(req.query.mode || "stats");
      const search = String(req.query.search || "");
      const page = Math.max(0, parseInt(req.query.page || "0", 10));
      const pageSize = Math.min(
        1000,
        Math.max(50, parseInt(req.query.pageSize || "200", 10)),
      );

      if (!PRIZES.includes(prize)) {
        return res.json({ ok: false, error: "Invalid prize" });
      }
      if (!Number.isFinite(cycle) || cycle < 1) {
        return res.json({ ok: false, error: "Invalid cycle number" });
      }

      const { records, meta } = await loadValidRecordsSorted(Model);

      const built = buildPrizeCyclesSummary(records);
      const summary = built.summary;

      const details = computePrizeCycleDetails(records, prize, cycle);
      if (!details.found) {
        return res.json({
          ok: false,
          error:
            details.reason === "cycle_not_found"
              ? "Cycle not found"
              : "Cycle has no data",
          summary,
          meta,
        });
      }

      const cycleInfo = details.cycleInfo;

      if (mode === "stats") {
        return res.json({
          ok: true,
          mode,
          summary,
          meta,
          cycleInfo,
        });
      }

      if (mode === "timeline") {
        const items = details.timeline;
        const total = items.length;
        const slice = items.slice(page * pageSize, (page + 1) * pageSize);

        return res.json({
          ok: true,
          mode,
          summary,
          meta,
          cycleInfo,
          timeline: {
            total,
            page,
            pageSize,
            items: slice,
          },
        });
      }

      if (mode === "remaining") {
        // build remaining list then filter + paginate
        const remaining = [];
        for (let i = 0; i < 10000; i++) {
          const n = String(i).padStart(4, "0");
          if (!details.uniqueSet.has(n)) remaining.push(n);
        }

        const filtered = search
          ? remaining.filter((n) => n.includes(search))
          : remaining;

        const total = filtered.length;
        const items = filtered.slice(page * pageSize, (page + 1) * pageSize);

        return res.json({
          ok: true,
          mode,
          summary,
          meta,
          cycleInfo,
          remaining: {
            total,
            page,
            pageSize,
            search,
            items,
          },
        });
      }

      return res.json({ ok: false, error: "Invalid mode" });
    } catch (err) {
      console.error("❌ cycle-details error:", err);
      return res.status(500).json({ ok: false, error: err.message });
    }
  };
}

// Register routes (match your frontend ENDPOINTS exactly)
app.get("/api/prizecycles/lotterydata", makePrizeCyclesHandler(LotteryData));
app.get(
  "/api/prizecycles/lotterydatanew",
  makePrizeCyclesHandler(LotteryDataNew),
);

app.get(
  "/api/prizecycles/lotterydata/cycle-details",
  makePrizeCycleDetailsHandler(LotteryData),
);
app.get(
  "/api/prizecycles/lotterydatanew/cycle-details",
  makePrizeCycleDetailsHandler(LotteryDataNew),
);

//
// new route
//

const PRIZE_AMOUNTS = ["5000", "2000", "1000", "500", "200", "100"];
const REQUIRED_PRIZES = ["5000", "1000", "500", "100"];
const REQUIRED_PRIZE_AMOUNTS = [5000, 1000, 500, 100];

app.get("/api/full-upload-folder", async (req, res) => {
  try {
    const folderPath = path.join(process.cwd(), "files");
    const files = fs
      .readdirSync(folderPath)
      .filter((f) => f.toLowerCase().endsWith(".pdf"));

    console.log(`🚀 [START] Processing ${files.length} files.`);
    const summary = [];

    for (const fileName of files) {
      console.log(`\n--- 📄 FILE: ${fileName} ---`);
      try {
        const buffer = fs.readFileSync(path.join(folderPath, fileName));
        const pdfData = await PdfParse(buffer);
        const rawText = pdfData.text || "";
        // console.log("RAW Data : " + rawText);

        const startMarker = "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";
        const splitIndex = rawText
          .toLowerCase()
          .indexOf(startMarker.toLowerCase());

        if (splitIndex === -1) {
          console.log(`   ❌ Skipped: Start marker not found.`);
          summary.push({
            fileName,
            status: "Skipped",
            reason: "Marker not found",
          });
          continue;
        }

        const upperSection = rawText.substring(0, splitIndex);
        const rawPrizeSection = rawText.substring(
          splitIndex + startMarker.length,
        );

        const serialNumber = extractSerialNumber(upperSection);
        const date = extractDateFromText(upperSection);

        console.log(`   🆔 ${serialNumber} | 📅 ${date}`);

        if (serialNumber === "Unknown" || date === "Unknown") {
          summary.push({
            fileName,
            status: "Skipped",
            reason: "Metadata error",
          });
          continue;
        }

        // 1. Perform dynamic extraction
        // ... inside the app.get("/api/full-upload") loop ...

        const prizeNumbers = getPrizeNumbersByAmount(rawPrizeSection);

        // --- 🔍 DETAILED INSPECTION LOG ---
        console.log(`   📊 EXTRACTION SUMMARY FOR ${serialNumber}:`);

        // Sort amounts descending so 5000 is first, 100 is last
        const sortedAmounts = Object.keys(prizeNumbers).sort((a, b) => b - a);

        sortedAmounts.forEach((amt) => {
          const numbers = prizeNumbers[amt];

          // Check if the scrubbed numbers contain any suspicious 4-digit years
          const hasYearIssue = numbers.some((n) =>
            ["2020", "2021", "2022", "2023", "2024", "2025", "2026"].includes(
              n,
            ),
          );

          console.log(
            `      💰 ₹${amt.padEnd(5)} [Total: ${String(numbers.length).padStart(3)}]`,
          );

          if (numbers.length > 0) {
            // Log the first 10 and last 10 numbers to keep console clean but informative
            const displayList =
              numbers.length > 20
                ? `${numbers.slice(0, 10).join(", ")} ... ${numbers.slice(-10).join(", ")}`
                : numbers.join(", ");

            console.log(`         🔢 ${displayList}`);

            if (hasYearIssue) {
              console.log(
                `         ⚠️  WARNING: Potential year detected in this prize tier!`,
              );
            }
          } else {
            console.log(`         ❌ No numbers found for this prize.`);
          }
        });

        // --- 🛡️ VALIDATION CHECK ---
        const missing = REQUIRED_PRIZE_AMOUNTS.filter(
          (amt) => !prizeNumbers[amt] || prizeNumbers[amt].length === 0,
        );
        // ... rest of the save logic ...

        if (missing.length > 0) {
          const reason = `Missing required amounts: ${missing.join(", ")}`;
          console.log(`   ⚠️ [VALIDATION] Skipped: ${reason}`);
          summary.push({ fileName, status: "Skipped", reason });
          continue;
        }

        // 4. Duplicate Check
        const exists = await FullLotteryData.findOne({ serialNumber }).lean();
        if (exists) {
          console.log(`   🚫 Duplicate record.`);
          summary.push({ fileName, status: "Duplicate", serialNumber });
          continue;
        }

        // 5. Save to Database
        const series = Object.entries(prizeNumbers).map(([amt, numbers]) => ({
          prize: Number(amt),
          numbers: numbers.map((n) => ({ number: n, count: 1 })),
        }));

        const newDoc = new FullLotteryData({
          serialNumber,
          date,
          drawDate: ddmmyyyyToUTCDate(date),
          fileName,
          series,
        });

        await newDoc.save();
        console.log(`   ✅ Saved Successfully.`);
        summary.push({ fileName, status: "Saved", serialNumber });
      } catch (err) {
        console.error(`   🔥 Error: ${err.message}`);
        summary.push({ fileName, status: "Error", error: err.message });
      }
    }

    res.json({ status: "Complete", summary });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
//get data test

app.get("/api/get-lottery-data", async (req, res) => {
  try {
    // Get the last 10 records uploaded
    const data = await FullLotteryData.find()
      .sort({ createdAt: -1 }) // Newest first
      .limit(10);

    if (!data || data.length === 0) {
      return res
        .status(404)
        .json({ message: "No lottery data found in database." });
    }

    // Format the response for easy reading
    const formattedData = data.map((item) => ({
      recordNumber: item.recordNumber,
      serialNumber: item.serialNumber,
      date: item.date,
      prizes: item.series.map((s) => ({
        prizeAmount: s.prize,
        // Join numbers into a string for quick visual verification
        winningNumbers: s.numbers.map((n) => n.number).join(", "),
        totalNumbers: s.numbers.length,
      })),
    }));

    res.json({
      success: true,
      count: data.length,
      results: formattedData,
    });
  } catch (err) {
    res
      .status(500)
      .json({ error: "Failed to fetch data", details: err.message });
  }
});

// ROUTE TO CHECK SPECIFIC SERIAL
app.get("/api/get-lottery-data/:serial", async (req, res) => {
  try {
    const data = await FullLotteryData.findOne({
      serialNumber: req.params.serial,
    });
    if (!data)
      return res.status(404).json({ error: "Serial number not found" });
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/verify-clash-numbers", async (req, res) => {
  try {
    // These are the "dangerous" numbers that usually get skipped/deleted
    const numbersToCheck = [
      "0050",
      "0100",
      "0200",
      "0250",
      "0300",
      "0500",
      "1000",
      "2000",
      "5000",
    ];

    // Find any record that contains these specific winning numbers
    const findings = await FullLotteryData.find({
      "series.numbers.number": { $in: numbersToCheck },
    }).lean();

    if (findings.length === 0) {
      return res.json({
        message:
          "No clash numbers found yet. Upload more PDFs or check your raw text for these numbers.",
        checkedNumbers: numbersToCheck,
      });
    }

    // Process findings to show exactly where these numbers were found
    const auditReport = findings.map((item) => {
      let detectedInThisFile = [];

      item.series.forEach((prizeTier) => {
        prizeTier.numbers.forEach((numObj) => {
          if (numbersToCheck.includes(numObj.number)) {
            detectedInThisFile.push({
              winningNumber: numObj.number,
              foundInPrizeTier: prizeTier.prize,
              count: numObj.count,
            });
          }
        });
      });

      return {
        serialNumber: item.serialNumber,
        date: item.date,
        fileName: item.fileName,
        detections: detectedInThisFile,
      };
    });

    res.json({
      success: true,
      totalFilesWithClashNumbers: findings.length,
      report: auditReport,
    });
  } catch (err) {
    res
      .status(500)
      .json({ error: "Verification failed", details: err.message });
  }
});

//
//full 3 DB page for cycles.
//
// === IMPROVED CYCLE HANDLER - Works with all 3 DBs ===
function createCyclesHandler(Model) {
  return async (req, res) => {
    try {
      const allData = await Model.find({}).lean();

      console.log(
        `\n📊 [${Model.modelName}] Fetched ${allData.length} records`,
      );

      if (!allData.length) {
        return res.json({
          summary: {
            totalCycles: 0,
            completedCycles: 0,
            incompleteCycles: 0,
            firstDay: "Unknown",
            lastDay: "Unknown",
          },
          cycles: [],
        });
      }

      // Robust date parser
      function parseDate(record) {
        if (!record) return new Date(0);

        // Priority 1: Use drawDate if available
        if (record.drawDate) {
          const d = new Date(record.drawDate);
          if (!isNaN(d.getTime())) return d;
        }

        // Priority 2: Parse date string
        const dateStr = record.date;
        if (!dateStr || dateStr === "Unknown") return new Date(0);

        const match = String(dateStr)
          .trim()
          .match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
        if (match) {
          let year = parseInt(match[3], 10);
          if (String(match[3]).length === 2) year = 2000 + year;
          return new Date(
            year,
            parseInt(match[2], 10) - 1,
            parseInt(match[1], 10),
          );
        }

        const fallback = new Date(dateStr);
        return isNaN(fallback.getTime()) ? new Date(0) : fallback;
      }

      // Sort records by date
      allData.sort((a, b) => parseDate(a) - parseDate(b));

      const cycles = [];
      let currentCycle = {
        cycleNumber: 1,
        startDate: null,
        endDate: null,
        totalDays: 0,
        uniqueNumbers: new Set(),
        numberFirstSeen: {},
        dailyProgress: [],
        prizeStates: new Map(),
      };

      function getRemainingNumbers(set) {
        const arr = [];
        for (let i = 0; i < 10000; i++) {
          const num = String(i).padStart(4, "0");
          if (!set.has(num)) arr.push(num);
        }
        return arr;
      }

      function buildPrizeSummaries(cycle, lastDate) {
        const prizes = Array.from(cycle.prizeStates.entries()).map(
          ([prize, state]) => {
            const total = state.uniqueNumbers.size;
            const isComplete = total === 10000;

            const totalDays =
              isComplete && state.endDate
                ? Math.ceil(
                    (parseDate(state.endDate) - parseDate(state.startDate)) /
                      86400000,
                  )
                : state.startDate && lastDate
                  ? Math.ceil(
                      (parseDate(lastDate) - parseDate(state.startDate)) /
                        86400000,
                    )
                  : 0;

            return {
              prize,
              startDate: state.startDate,
              endDate: state.endDate,
              totalDays,
              totalUniqueNumbers: total,
              remainingNumbers: 10000 - total,
              remainingNumbersList: getRemainingNumbers(state.uniqueNumbers),
              percentComplete: Number(((total / 10000) * 100).toFixed(2)),
              isComplete,
            };
          },
        );

        prizes.sort((a, b) => b.totalUniqueNumbers - a.totalUniqueNumbers);

        return {
          prizes,
          prizeLeader: prizes[0] || null,
          completedPrizes: prizes
            .filter((p) => p.isComplete)
            .map((p) => p.prize),
        };
      }

      for (const record of allData) {
        const date = record.date;
        const parsedDate = parseDate(record);

        if (parsedDate.getTime() === 0) continue;

        if (!currentCycle.startDate) currentCycle.startDate = date;

        let newUniqueCount = 0;
        let cycleCompleted = false;

        const numbersAddedToday = [];
        const prizeNumbersAddedToday = {};

        // Support different schema structures
        const seriesList = record.series || record.Series || [];

        for (const series of seriesList) {
          const prize = series.prize || series.Prize;
          if (!prize) continue;

          if (!currentCycle.prizeStates.has(prize)) {
            currentCycle.prizeStates.set(prize, {
              uniqueNumbers: new Set(),
              startDate: null,
              endDate: null,
            });
          }

          const prizeState = currentCycle.prizeStates.get(prize);
          if (!prizeNumbersAddedToday[prize])
            prizeNumbersAddedToday[prize] = [];

          const numbersList = series.numbers || series.Numbers || [];

          for (const item of numbersList) {
            const num = item.number || item.Number || item;
            if (!num) continue;

            const numStr = String(num).padStart(4, "0");

            if (!currentCycle.uniqueNumbers.has(numStr)) {
              currentCycle.uniqueNumbers.add(numStr);
              currentCycle.numberFirstSeen[numStr] = date;
              newUniqueCount++;
              numbersAddedToday.push(numStr);
            }

            if (!prizeState.uniqueNumbers.has(numStr)) {
              prizeState.uniqueNumbers.add(numStr);
              prizeNumbersAddedToday[prize].push(numStr);

              if (!prizeState.startDate) prizeState.startDate = date;
              if (
                prizeState.uniqueNumbers.size === 10000 &&
                !prizeState.endDate
              ) {
                prizeState.endDate = date;
              }
            }

            // Cycle completed?
            if (currentCycle.uniqueNumbers.size === 10000) {
              currentCycle.endDate = date;
              currentCycle.totalDays = Math.ceil(
                (parseDate(date) - parseDate(currentCycle.startDate)) /
                  86400000,
              );

              currentCycle.dailyProgress.push({
                date,
                newUnique: newUniqueCount,
                totalUnique: currentCycle.uniqueNumbers.size,
                numbersAdded: numbersAddedToday,
                prizeNumbersAdded: prizeNumbersAddedToday,
              });

              const summary = buildPrizeSummaries(currentCycle, date);

              cycles.push({
                cycleNumber: currentCycle.cycleNumber,
                startDate: currentCycle.startDate,
                endDate: currentCycle.endDate,
                totalDays: currentCycle.totalDays,
                totalUniqueNumbers: currentCycle.uniqueNumbers.size,
                isComplete: true,
                remainingNumbers: 0,
                remainingNumbersList: [],
                dailyProgress: currentCycle.dailyProgress,
                prizes: summary.prizes,
                prizeLeader: summary.prizeLeader,
                completedPrizes: summary.completedPrizes,
              });

              // Start new cycle
              currentCycle = {
                cycleNumber: cycles.length + 1,
                startDate: date,
                endDate: null,
                totalDays: 0,
                uniqueNumbers: new Set(),
                numberFirstSeen: {},
                dailyProgress: [],
                prizeStates: new Map(),
              };

              cycleCompleted = true;
              break;
            }
          }
          if (cycleCompleted) break;
        }

        if (!cycleCompleted) {
          currentCycle.dailyProgress.push({
            date,
            newUnique: newUniqueCount,
            totalUnique: currentCycle.uniqueNumbers.size,
            numbersAdded: numbersAddedToday,
            prizeNumbersAdded: prizeNumbersAddedToday,
          });
        }
      }

      // Push last incomplete cycle
      if (currentCycle.uniqueNumbers.size > 0) {
        const lastDate =
          currentCycle.dailyProgress[currentCycle.dailyProgress.length - 1]
            ?.date || null;
        const summary = buildPrizeSummaries(currentCycle, lastDate);
        const remainingList = getRemainingNumbers(currentCycle.uniqueNumbers);

        cycles.push({
          cycleNumber: currentCycle.cycleNumber,
          startDate: currentCycle.startDate,
          endDate: null,
          totalDays: lastDate
            ? Math.ceil(
                (parseDate(lastDate) - parseDate(currentCycle.startDate)) /
                  86400000,
              )
            : 0,
          totalUniqueNumbers: currentCycle.uniqueNumbers.size,
          isComplete: false,
          remainingNumbers: 10000 - currentCycle.uniqueNumbers.size,
          remainingNumbersList: remainingList,
          dailyProgress: currentCycle.dailyProgress,
          prizes: summary.prizes,
          prizeLeader: summary.prizeLeader,
          completedPrizes: summary.completedPrizes,
        });
      }

      const firstDay = allData[0]?.date || "Unknown";
      const lastDay = allData[allData.length - 1]?.date || "Unknown";

      console.log(`✅ [${Model.modelName}] Generated ${cycles.length} cycles`);

      res.json({
        summary: {
          totalCycles: cycles.length,
          completedCycles: cycles.filter((c) => c.isComplete).length,
          incompleteCycles: cycles.filter((c) => !c.isComplete).length,
          firstDay,
          lastDay,
        },
        cycles,
      });
    } catch (err) {
      console.error("❌ Cycle error:", err);
      res.status(500).json({ error: err.message });
    }
  };
}
app.get("/api/cycles-3db/lotterydata", createCyclesHandler(LotteryData));
app.get("/api/cycles-3db/lotterydatanew", createCyclesHandler(LotteryDataNew));
app.get(
  "/api/cycles-3db/fulllotterydata",
  createCyclesHandler(FullLotteryData),
);

// ====================== COMPARE 3 DATABASES BY SERIAL NUMBER ======================
// ================================================
// IMPROVED COMPARISON - 3 DATABASES
// ================================================
// ================================================
// FINAL IMPROVED 3-DB COMPARISON
// ================================================
// ====================== FIND EXACT DIFFERENT NUMBERS ======================
app.get("/api/compare-3dbs/detailed", async (req, res) => {
  try {
    const [db1, db2, db3] = await Promise.all([
      LotteryData.find({}).lean(),
      LotteryDataNew.find({}).lean(),
      FullLotteryData.find({}).lean(),
    ]);

    const map = new Map();

    const add = (records, dbName) => {
      records.forEach((record) => {
        if (!record.serialNumber) return;

        if (!map.has(record.serialNumber)) {
          map.set(record.serialNumber, {
            serialNumber: record.serialNumber,
            date: record.date,
            sources: {},
          });
        }

        // Create prize -> list of numbers map
        const prizeMap = {};
        const seriesList = record.series || record.Series || [];

        seriesList.forEach((series) => {
          const prize = series.prize;
          if (prize) {
            prizeMap[prize] = (series.numbers || series.Numbers || []).map(
              (n) => n.number || n.Number || n,
            );
          }
        });

        map.get(record.serialNumber).sources[dbName] = prizeMap;
      });
    };

    add(db1, "LotteryData");
    add(db2, "LotteryDataNew");
    add(db3, "FullLotteryData");

    const detailedResults = [];

    for (const [serial, info] of map) {
      const sources = Object.keys(info.sources);
      if (sources.length < 2) continue;

      const comparison = {
        serialNumber: serial,
        date: info.date,
        presentIn: sources,
        differences: [],
      };

      // Compare each prize across sources
      const allPrizes = new Set();
      sources.forEach((src) => {
        Object.keys(info.sources[src]).forEach((p) => allPrizes.add(p));
      });

      allPrizes.forEach((prize) => {
        const numberSets = {};

        sources.forEach((src) => {
          numberSets[src] = new Set(info.sources[src][prize] || []);
        });

        // Find numbers that are not common in all sources
        const allNumbers = new Set();
        Object.values(numberSets).forEach((set) =>
          set.forEach((n) => allNumbers.add(n)),
        );

        const diff = {
          prize: `₹${prize}`,
          counts: {},
          extraNumbers: {},
          missingNumbers: {},
        };

        sources.forEach((src) => {
          diff.counts[src] = numberSets[src].size;
        });

        // Find extra / missing numbers
        allNumbers.forEach((num) => {
          const presentIn = sources.filter((src) => numberSets[src].has(num));

          if (presentIn.length !== sources.length) {
            const missingIn = sources.filter(
              (src) => !numberSets[src].has(num),
            );

            if (presentIn.length === 1) {
              // This number exists only in one DB → clear odd number
              const oddDb = presentIn[0];
              if (!diff.extraNumbers[oddDb]) diff.extraNumbers[oddDb] = [];
              diff.extraNumbers[oddDb].push(num);
            } else if (missingIn.length === 1) {
              // This number is missing in only one DB
              const missingDb = missingIn[0];
              if (!diff.missingNumbers[missingDb])
                diff.missingNumbers[missingDb] = [];
              diff.missingNumbers[missingDb].push(num);
            }
          }
        });

        if (
          Object.keys(diff.extraNumbers).length > 0 ||
          Object.keys(diff.missingNumbers).length > 0
        ) {
          comparison.differences.push(diff);
        }
      });

      if (comparison.differences.length > 0) {
        detailedResults.push(comparison);
      }
    }

    detailedResults.sort((a, b) =>
      a.serialNumber.localeCompare(b.serialNumber),
    );

    res.json({
      summary: {
        totalCompared: detailedResults.length,
        totalInconsistent: detailedResults.length,
      },
      inconsistentSerials: detailedResults.slice(0, 100), // First 100 for readability
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

//raw data

//const PRIZE_AMOUNTS = ["5000", "2000", "1000", "500", "200", "100"];
//const REQUIRED_PRIZES = ["5000", "1000", "500"];

app.get("/api/full-upload", async (req, res) => {
  try {
    const folderPath = path.join(process.cwd(), "files");
    const files = fs
      .readdirSync(folderPath)
      .filter((f) => f.toLowerCase().endsWith(".pdf"));

    console.log(`🚀 [START] Processing ${files.length} files.`);
    const summary = [];

    for (const fileName of files) {
      console.log(`\n--- 📄 FILE: ${fileName} ---`);
      try {
        const buffer = fs.readFileSync(path.join(folderPath, fileName));
        const pdfData = await PdfParse(buffer);
        const rawText = pdfData.text || "";
        // console.log("RAW Data : " + rawText);

        const startMarker = "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";
        const splitIndex = rawText
          .toLowerCase()
          .indexOf(startMarker.toLowerCase());

        if (splitIndex === -1) {
          console.log(`   ❌ Skipped: Start marker not found.`);
          summary.push({
            fileName,
            status: "Skipped",
            reason: "Marker not found",
          });
          continue;
        }

        const upperSection = rawText.substring(0, splitIndex);
        const rawPrizeSection = rawText.substring(
          splitIndex + startMarker.length,
        );

        const serialNumber = extractSerialNumber(upperSection);
        const date = extractDateFromText(upperSection);

        console.log(`   🆔 ${serialNumber} | 📅 ${date}`);

        if (serialNumber === "Unknown" || date === "Unknown") {
          summary.push({
            fileName,
            status: "Skipped",
            reason: "Metadata error",
          });
          continue;
        }

        // 1. Perform dynamic extraction
        // ... inside the app.get("/api/full-upload") loop ...

        const prizeNumbers = getPrizeNumbersByAmount(rawPrizeSection);

        // --- 🔍 DETAILED INSPECTION LOG ---
        console.log(`   📊 EXTRACTION SUMMARY FOR ${serialNumber}:`);

        // Sort amounts descending so 5000 is first, 100 is last
        const sortedAmounts = Object.keys(prizeNumbers).sort((a, b) => b - a);

        sortedAmounts.forEach((amt) => {
          const numbers = prizeNumbers[amt];

          // Check if the scrubbed numbers contain any suspicious 4-digit years
          const hasYearIssue = numbers.some((n) =>
            ["2020", "2021", "2022", "2023", "2024", "2025", "2026"].includes(
              n,
            ),
          );

          console.log(
            `      💰 ₹${amt.padEnd(5)} [Total: ${String(numbers.length).padStart(3)}]`,
          );

          if (numbers.length > 0) {
            // Log the first 10 and last 10 numbers to keep console clean but informative
            const displayList =
              numbers.length > 20
                ? `${numbers.slice(0, 10).join(", ")} ... ${numbers.slice(-10).join(", ")}`
                : numbers.join(", ");

            console.log(`         🔢 ${displayList}`);

            if (hasYearIssue) {
              console.log(
                `         ⚠️  WARNING: Potential year detected in this prize tier!`,
              );
            }
          } else {
            console.log(`         ❌ No numbers found for this prize.`);
          }
        });

        // --- 🛡️ VALIDATION CHECK ---
        const missing = REQUIRED_PRIZE_AMOUNTS.filter(
          (amt) => !prizeNumbers[amt] || prizeNumbers[amt].length === 0,
        );
        // ... rest of the save logic ...

        if (missing.length > 0) {
          const reason = `Missing required amounts: ${missing.join(", ")}`;
          console.log(`   ⚠️ [VALIDATION] Skipped: ${reason}`);
          summary.push({ fileName, status: "Skipped", reason });
          continue;
        }

        // 4. Duplicate Check
        const exists = await FullLotteryData.findOne({ serialNumber }).lean();
        if (exists) {
          console.log(`   🚫 Duplicate record.`);
          summary.push({ fileName, status: "Duplicate", serialNumber });
          continue;
        }

        // 5. Save to Database
        const series = Object.entries(prizeNumbers).map(([amt, numbers]) => ({
          prize: Number(amt),
          numbers: numbers.map((n) => ({ number: n, count: 1 })),
        }));

        const newDoc = new FullLotteryData({
          serialNumber,
          date,
          drawDate: ddmmyyyyToUTCDate(date),
          fileName,
          series,
        });

        await newDoc.save();
        console.log(`   ✅ Saved Successfully.`);
        summary.push({ fileName, status: "Saved", serialNumber });
      } catch (err) {
        console.error(`   🔥 Error: ${err.message}`);
        summary.push({ fileName, status: "Error", error: err.message });
      }
    }

    res.json({ status: "Complete", summary });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

//compare 3DB's
function parseDDMMYYYY(dateStr = "") {
  const match = String(dateStr).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);

  return new Date(Date.UTC(year, month - 1, day));
}

function isWithinRange(dateStr, fromDate, toDate) {
  const d = parseDDMMYYYY(dateStr);
  if (!d) return false;

  if (fromDate) {
    const from = new Date(`${fromDate}T00:00:00.000Z`);
    if (d < from) return false;
  }

  if (toDate) {
    const to = new Date(`${toDate}T23:59:59.999Z`);
    if (d > to) return false;
  }

  return true;
}

function normalizeSeries(series = []) {
  const result = {};

  for (const item of series || []) {
    const prize = String(item.prize);

    result[prize] = (item.numbers || [])
      .map((n) => ({
        number: String(n.number || "").padStart(4, "0"),
        count: Number(n.count || 1),
      }))
      .sort((a, b) => a.number.localeCompare(b.number));
  }

  return result;
}

function seriesToTokenMap(series = []) {
  const normalized = normalizeSeries(series);
  const result = {};

  for (const [prize, numbers] of Object.entries(normalized)) {
    result[prize] = numbers.map((n) => `${n.number}:${n.count}`);
  }

  return result;
}

function compareTwoSeries(seriesA = [], seriesB = []) {
  const a = seriesToTokenMap(seriesA);
  const b = seriesToTokenMap(seriesB);

  const allPrizes = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort(
    (x, y) => Number(y) - Number(x),
  );

  const diffs = [];
  let equal = true;

  for (const prize of allPrizes) {
    const arrA = a[prize] || [];
    const arrB = b[prize] || [];

    const onlyInA = arrA
      .filter((x) => !arrB.includes(x))
      .map((x) => {
        const [number, count] = x.split(":");
        return { number, count: Number(count) };
      });

    const onlyInB = arrB
      .filter((x) => !arrA.includes(x))
      .map((x) => {
        const [number, count] = x.split(":");
        return { number, count: Number(count) };
      });

    if (onlyInA.length || onlyInB.length) {
      equal = false;
      diffs.push({
        prize: Number(prize),
        onlyInA,
        onlyInB,
      });
    }
  }

  return { equal, diffs };
}

function totalWinningNumbers(series = []) {
  return (series || []).reduce((sum, item) => {
    return sum + (item.numbers || []).length;
  }, 0);
}

app.get("/api/compare-3-dbs", async (req, res) => {
  try {
    const { fromDate, toDate, serialNumber = "", status = "" } = req.query;

    const [db1DocsRaw, db2DocsRaw, db3DocsRaw, db4DocsRaw] = await Promise.all([
      LotteryData.find({}).lean(),
      LotteryDataNew.find({}).lean(),
      FullLotteryData.find({}).lean(),
      AbsoluteData.find({}).lean(),
    ]);

    const serialSearch = serialNumber.trim().toLowerCase();
    const allPrizeSet = new Set();

    const filterDocs = (docs) =>
      docs.filter((doc) => {
        const serialOk = serialSearch
          ? String(doc.serialNumber || "")
              .toLowerCase()
              .includes(serialSearch)
          : true;

        const dateOk =
          !fromDate && !toDate
            ? true
            : isWithinRange(String(doc.date || ""), fromDate, toDate);

        return serialOk && dateOk;
      });

    const db1Docs = filterDocs(db1DocsRaw);
    const db2Docs = filterDocs(db2DocsRaw);
    const db3Docs = filterDocs(db3DocsRaw);
    const db4Docs = filterDocs(db4DocsRaw);

    const merged = new Map();

    function addDocs(sourceKey, docs) {
      for (const doc of docs) {
        const key = `${doc.date || ""}__${doc.serialNumber || ""}`;

        if (!merged.has(key)) {
          merged.set(key, {
            key,
            date: doc.date || "",
            serialNumber: doc.serialNumber || "",
            db1: null,
            db2: null,
            db3: null,
            db4: null,
          });
        }

        merged.get(key)[sourceKey] = doc;

        for (const item of doc.series || []) {
          allPrizeSet.add(String(item.prize));
        }
      }
    }

    addDocs("db1", db1Docs);
    addDocs("db2", db2Docs);
    addDocs("db3", db3Docs);
    addDocs("db4", db4Docs);

    const rows = [];

    for (const row of merged.values()) {
      const hasDb1 = !!row.db1;
      const hasDb2 = !!row.db2;
      const hasDb3 = !!row.db3;
      const hasDb4 = !!row.db4;

      const missingIn = [];
      if (!hasDb1) missingIn.push("LotteryData");
      if (!hasDb2) missingIn.push("LotteryDataNew");
      if (!hasDb3) missingIn.push("FullLotteryData");
      if (!hasDb4) missingIn.push("AbsoluteData");

      let compare12 = null;
      let compare13 = null;
      let compare14 = null;
      let compare23 = null;
      let compare24 = null;
      let compare34 = null;

      if (hasDb1 && hasDb2) {
        compare12 = compareTwoSeries(row.db1.series, row.db2.series);
      }

      if (hasDb1 && hasDb3) {
        compare13 = compareTwoSeries(row.db1.series, row.db3.series);
      }

      if (hasDb1 && hasDb4) {
        compare14 = compareTwoSeries(row.db1.series, row.db4.series);
      }

      if (hasDb2 && hasDb3) {
        compare23 = compareTwoSeries(row.db2.series, row.db3.series);
      }

      if (hasDb2 && hasDb4) {
        compare24 = compareTwoSeries(row.db2.series, row.db4.series);
      }

      if (hasDb3 && hasDb4) {
        compare34 = compareTwoSeries(row.db3.series, row.db4.series);
      }

      let finalStatus = "MATCH";
      const mismatchReason = [];

      if (missingIn.length > 0) {
        finalStatus = "MISSING";
      } else {
        const allEqual =
          compare12?.equal !== false &&
          compare13?.equal !== false &&
          compare14?.equal !== false &&
          compare23?.equal !== false &&
          compare24?.equal !== false &&
          compare34?.equal !== false;

        if (!allEqual) {
          finalStatus = "MISMATCH";

          if (compare12 && !compare12.equal) {
            mismatchReason.push("LotteryData vs LotteryDataNew");
          }

          if (compare13 && !compare13.equal) {
            mismatchReason.push("LotteryData vs FullLotteryData");
          }

          if (compare14 && !compare14.equal) {
            mismatchReason.push("LotteryData vs AbsoluteData");
          }

          if (compare23 && !compare23.equal) {
            mismatchReason.push("LotteryDataNew vs FullLotteryData");
          }

          if (compare24 && !compare24.equal) {
            mismatchReason.push("LotteryDataNew vs AbsoluteData");
          }

          if (compare34 && !compare34.equal) {
            mismatchReason.push("FullLotteryData vs AbsoluteData");
          }
        }
      }

      rows.push({
        key: row.key,
        date: row.date,
        serialNumber: row.serialNumber,
        status: finalStatus,
        missingIn,
        mismatchReason,

        db1: row.db1
          ? {
              entryNumber: row.db1.entryNumber,
              totalNumbers: totalWinningNumbers(row.db1.series),
              series: normalizeSeries(row.db1.series),
              createdAt: row.db1.createdAt || null,
            }
          : null,

        db2: row.db2
          ? {
              entryNumber: row.db2.entryNumber,
              totalNumbers: totalWinningNumbers(row.db2.series),
              series: normalizeSeries(row.db2.series),
              createdAt: row.db2.createdAt || null,
            }
          : null,

        db3: row.db3
          ? {
              recordNumber: row.db3.recordNumber,
              fileName: row.db3.fileName || "",
              drawDate: row.db3.drawDate || null,
              totalNumbers: totalWinningNumbers(row.db3.series),
              series: normalizeSeries(row.db3.series),
              createdAt: row.db3.createdAt || null,
            }
          : null,

        db4: row.db4
          ? {
              recordNumber: row.db4.recordNumber,
              fileName: row.db4.fileName || "",
              drawDate: row.db4.drawDate || null,
              totalNumbers: totalWinningNumbers(row.db4.series),
              series: normalizeSeries(row.db4.series),
              createdAt: row.db4.createdAt || null,
            }
          : null,

        diffs: {
          db1VsDb2: compare12?.diffs || [],
          db1VsDb3: compare13?.diffs || [],
          db1VsDb4: compare14?.diffs || [],
          db2VsDb3: compare23?.diffs || [],
          db2VsDb4: compare24?.diffs || [],
          db3VsDb4: compare34?.diffs || [],
        },
      });
    }

    let filteredRows = rows;

    if (status) {
      filteredRows = rows.filter(
        (r) => r.status === String(status).toUpperCase(),
      );
    }

    filteredRows.sort((a, b) => {
      const da = parseDDMMYYYY(a.date);
      const db = parseDDMMYYYY(b.date);

      if (da && db && db.getTime() !== da.getTime()) {
        return db - da;
      }

      return String(a.serialNumber || "").localeCompare(
        String(b.serialNumber || ""),
      );
    });

    const allPrizes = Array.from(allPrizeSet).sort(
      (a, b) => Number(b) - Number(a),
    );

    const summary = {
      total: filteredRows.length,
      matched: filteredRows.filter((r) => r.status === "MATCH").length,
      missing: filteredRows.filter((r) => r.status === "MISSING").length,
      mismatch: filteredRows.filter((r) => r.status === "MISMATCH").length,
    };

    res.json({
      summary,
      allPrizes,
      rows: filteredRows,
    });
  } catch (err) {
    console.error("❌ Compare 4 DBs error:", err.message);
    res.status(500).json({
      error: "Compare failed",
      details: err.message,
    });
  }
});
//
//Full Cycles
//
function parseDDMMYYYYToDate(dateStr = "") {
  const match = String(dateStr).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);

  return new Date(Date.UTC(year, month - 1, day));
}

function generateAll4DigitNumbers() {
  return Array.from({ length: 10000 }, (_, i) => String(i).padStart(4, "0"));
}

function getUniqueNumbersFromDoc(doc) {
  const set = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      const number = String(item.number || "").trim();
      if (/^\d{4}$/.test(number)) {
        set.add(number);
      }
    }
  }

  return Array.from(set).sort();
}

function sortDocsChronologically(docs = []) {
  return [...docs].sort((a, b) => {
    const dateA = a.drawDate
      ? new Date(a.drawDate)
      : parseDDMMYYYYToDate(a.date || "");
    const dateB = b.drawDate
      ? new Date(b.drawDate)
      : parseDDMMYYYYToDate(b.date || "");

    if (dateA && dateB && dateA.getTime() !== dateB.getTime()) {
      return dateA - dateB;
    }

    if ((a.recordNumber || 0) !== (b.recordNumber || 0)) {
      return (a.recordNumber || 0) - (b.recordNumber || 0);
    }

    return String(a.serialNumber || "").localeCompare(
      String(b.serialNumber || ""),
    );
  });
}

function buildCycleAnalysis(docs = []) {
  const TOTAL_NUMBERS = 10000;
  const ALL_NUMBERS = generateAll4DigitNumbers();
  const sortedDocs = sortDocsChronologically(docs);

  const cycles = [];

  let cycleNumber = 1;
  let seenInCycle = new Set();
  let firstSeenMap = new Map();
  let cycleStartDoc = null;
  let drawTimeline = [];

  for (const doc of sortedDocs) {
    const drawNumbers = getUniqueNumbersFromDoc(doc);
    if (!drawNumbers.length) continue;

    if (!cycleStartDoc) {
      cycleStartDoc = doc;
    }

    const newNumbers = [];

    for (const num of drawNumbers) {
      if (!seenInCycle.has(num)) {
        seenInCycle.add(num);
        newNumbers.push(num);

        if (!firstSeenMap.has(num)) {
          firstSeenMap.set(num, {
            number: num,
            firstSeenDate: doc.date || "",
            firstSeenSerialNumber: doc.serialNumber || "",
            recordNumber: doc.recordNumber || null,
            fileName: doc.fileName || "",
          });
        }
      }
    }

    drawTimeline.push({
      recordNumber: doc.recordNumber || null,
      serialNumber: doc.serialNumber || "",
      date: doc.date || "",
      fileName: doc.fileName || "",
      uniqueNumbersInDraw: drawNumbers.length,
      newNumbersCount: newNumbers.length,
      totalSeenAfterDraw: seenInCycle.size,
      progressPercent: Number(
        ((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2),
      ),
      newNumbers,
    });

    if (seenInCycle.size === TOTAL_NUMBERS) {
      const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
        a.number.localeCompare(b.number),
      );

      cycles.push({
        cycleNumber,
        status: "COMPLETED",
        startDate: cycleStartDoc?.date || "",
        startSerialNumber: cycleStartDoc?.serialNumber || "",
        startRecordNumber: cycleStartDoc?.recordNumber || null,
        endDate: doc.date || "",
        endSerialNumber: doc.serialNumber || "",
        endRecordNumber: doc.recordNumber || null,
        drawsCount: drawTimeline.length,
        uniqueNumbersSeen: seenInCycle.size,
        remainingCount: 0,
        progressPercent: 100,
        remainingNumbers: [],
        firstSeenNumbers,
        drawTimeline,
      });

      cycleNumber += 1;
      seenInCycle = new Set();
      firstSeenMap = new Map();
      cycleStartDoc = null;
      drawTimeline = [];
    }
  }

  if (cycleStartDoc || seenInCycle.size > 0 || cycles.length === 0) {
    const remainingNumbers = ALL_NUMBERS.filter((num) => !seenInCycle.has(num));
    const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
      a.number.localeCompare(b.number),
    );

    const lastDoc = sortedDocs[sortedDocs.length - 1] || null;

    cycles.push({
      cycleNumber,
      status: "IN_PROGRESS",
      startDate: cycleStartDoc?.date || "",
      startSerialNumber: cycleStartDoc?.serialNumber || "",
      startRecordNumber: cycleStartDoc?.recordNumber || null,
      endDate: lastDoc?.date || "",
      endSerialNumber: lastDoc?.serialNumber || "",
      endRecordNumber: lastDoc?.recordNumber || null,
      drawsCount: drawTimeline.length,
      uniqueNumbersSeen: seenInCycle.size,
      remainingCount: remainingNumbers.length,
      progressPercent: Number(
        ((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2),
      ),
      remainingNumbers,
      firstSeenNumbers,
      drawTimeline,
    });
  }

  return {
    totalDraws: sortedDocs.length,
    totalPossibleNumbers: TOTAL_NUMBERS,
    cycles,
  };
}

//summary
app.get("/api/full-lottery-cycles", async (req, res) => {
  try {
    const fromCycle = Math.max(Number(req.query.fromCycle || 1), 1);

    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildCycleAnalysis(docs);

    const cycles = analysis.cycles
      .filter((cycle) => cycle.cycleNumber >= fromCycle)
      .map((cycle) => ({
        cycleNumber: cycle.cycleNumber,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
      }));

    const completedCycles = analysis.cycles.filter(
      (c) => c.status === "COMPLETED",
    ).length;

    const currentCycle =
      analysis.cycles.length > 0
        ? analysis.cycles[analysis.cycles.length - 1]
        : null;

    res.json({
      summary: {
        totalDraws: analysis.totalDraws,
        totalPossibleNumbers: analysis.totalPossibleNumbers,
        totalCycles: analysis.cycles.length,
        completedCycles,
        currentCycleNumber: currentCycle?.cycleNumber || null,
        currentCycleStatus: currentCycle?.status || null,
        currentUniqueNumbersSeen: currentCycle?.uniqueNumbersSeen || 0,
        currentRemainingCount: currentCycle?.remainingCount || 0,
        currentProgressPercent: currentCycle?.progressPercent || 0,
      },
      cycles,
    });
  } catch (err) {
    console.error("❌ full-lottery-cycles error:", err.message);
    res.status(500).json({
      error: "Failed to build cycle summary",
      details: err.message,
    });
  }
});
//detailed
app.get("/api/full-lottery-cycles/:cycleNumber", async (req, res) => {
  try {
    const cycleNumber = Number(req.params.cycleNumber);

    if (!cycleNumber || cycleNumber < 1) {
      return res.status(400).json({ error: "Invalid cycle number" });
    }

    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildCycleAnalysis(docs);
    const cycle = analysis.cycles.find((c) => c.cycleNumber === cycleNumber);

    if (!cycle) {
      return res.status(404).json({ error: "Cycle not found" });
    }

    res.json({
      cycle: {
        cycleNumber: cycle.cycleNumber,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
        remainingNumbers: cycle.remainingNumbers,
        firstSeenNumbers: cycle.firstSeenNumbers,
        drawTimeline: cycle.drawTimeline,
      },
    });
  } catch (err) {
    console.error("❌ full-lottery-cycles/:cycleNumber error:", err.message);
    res.status(500).json({
      error: "Failed to load cycle details",
      details: err.message,
    });
  }
});

//prize cycles

function getAllPrizeCategories(docs = []) {
  const set = new Set();

  for (const doc of docs) {
    for (const series of doc.series || []) {
      if (series?.prize != null && !Number.isNaN(Number(series.prize))) {
        set.add(Number(series.prize));
      }
    }
  }

  return Array.from(set).sort((a, b) => b - a);
}

function getUniqueNumbersForPrize(doc, prize) {
  const set = new Set();

  const foundSeries = (doc.series || []).find(
    (series) => Number(series.prize) === Number(prize),
  );

  if (!foundSeries) return [];

  for (const item of foundSeries.numbers || []) {
    const number = String(item.number || "").trim();
    if (/^\d{4}$/.test(number)) {
      set.add(number);
    }
  }

  return Array.from(set).sort();
}

function buildPrizeCycleAnalysis(docs = [], prize) {
  const TOTAL_NUMBERS = 10000;
  const ALL_NUMBERS = generateAll4DigitNumbers();
  const sortedDocs = sortDocsChronologically(docs);

  const prizeDocs = sortedDocs
    .map((doc) => ({
      doc,
      numbers: getUniqueNumbersForPrize(doc, prize),
    }))
    .filter((item) => item.numbers.length > 0);

  const cycles = [];

  if (!prizeDocs.length) {
    return {
      prize: Number(prize),
      totalDrawsWithPrize: 0,
      totalPossibleNumbers: TOTAL_NUMBERS,
      firstDate: null,
      latestDate: null,
      cycles: [],
    };
  }

  let cycleNumber = 1;
  let seenInCycle = new Set();
  let firstSeenMap = new Map();
  let cycleStartDoc = null;
  let drawTimeline = [];

  for (const item of prizeDocs) {
    const doc = item.doc;
    const drawNumbers = item.numbers;

    if (!cycleStartDoc) {
      cycleStartDoc = doc;
    }

    const newNumbers = [];

    for (const num of drawNumbers) {
      if (!seenInCycle.has(num)) {
        seenInCycle.add(num);
        newNumbers.push(num);

        if (!firstSeenMap.has(num)) {
          firstSeenMap.set(num, {
            number: num,
            firstSeenDate: doc.date || "",
            firstSeenSerialNumber: doc.serialNumber || "",
            recordNumber: doc.recordNumber || null,
            fileName: doc.fileName || "",
          });
        }
      }
    }

    drawTimeline.push({
      recordNumber: doc.recordNumber || null,
      serialNumber: doc.serialNumber || "",
      date: doc.date || "",
      fileName: doc.fileName || "",
      uniqueNumbersInDraw: drawNumbers.length,
      newNumbersCount: newNumbers.length,
      totalSeenAfterDraw: seenInCycle.size,
      progressPercent: Number(
        ((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2),
      ),
      newNumbers,
    });

    if (seenInCycle.size === TOTAL_NUMBERS) {
      const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
        a.number.localeCompare(b.number),
      );

      cycles.push({
        cycleNumber,
        prize: Number(prize),
        status: "COMPLETED",
        startDate: cycleStartDoc?.date || "",
        startSerialNumber: cycleStartDoc?.serialNumber || "",
        startRecordNumber: cycleStartDoc?.recordNumber || null,
        endDate: doc.date || "",
        endSerialNumber: doc.serialNumber || "",
        endRecordNumber: doc.recordNumber || null,
        drawsCount: drawTimeline.length,
        uniqueNumbersSeen: seenInCycle.size,
        remainingCount: 0,
        progressPercent: 100,
        remainingNumbers: [],
        firstSeenNumbers,
        drawTimeline,
      });

      cycleNumber += 1;
      seenInCycle = new Set();
      firstSeenMap = new Map();
      cycleStartDoc = null;
      drawTimeline = [];
    }
  }

  if (cycleStartDoc || seenInCycle.size > 0 || cycles.length === 0) {
    const remainingNumbers = ALL_NUMBERS.filter((num) => !seenInCycle.has(num));

    const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
      a.number.localeCompare(b.number),
    );

    const lastDoc = prizeDocs[prizeDocs.length - 1]?.doc || null;

    cycles.push({
      cycleNumber,
      prize: Number(prize),
      status: "IN_PROGRESS",
      startDate: cycleStartDoc?.date || "",
      startSerialNumber: cycleStartDoc?.serialNumber || "",
      startRecordNumber: cycleStartDoc?.recordNumber || null,
      endDate: lastDoc?.date || "",
      endSerialNumber: lastDoc?.serialNumber || "",
      endRecordNumber: lastDoc?.recordNumber || null,
      drawsCount: drawTimeline.length,
      uniqueNumbersSeen: seenInCycle.size,
      remainingCount: remainingNumbers.length,
      progressPercent: Number(
        ((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2),
      ),
      remainingNumbers,
      firstSeenNumbers,
      drawTimeline,
    });
  }

  return {
    prize: Number(prize),
    totalDrawsWithPrize: prizeDocs.length,
    totalPossibleNumbers: TOTAL_NUMBERS,
    firstDate: prizeDocs[0]?.doc?.date || null,
    latestDate: prizeDocs[prizeDocs.length - 1]?.doc?.date || null,
    cycles,
  };
}
app.get("/api/all-prize-cycles", async (req, res) => {
  try {
    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const sortedDocs = sortDocsChronologically(docs);
    const prizeCategories = getAllPrizeCategories(sortedDocs);

    const prizeSummaries = prizeCategories.map((prize) => {
      const analysis = buildPrizeCycleAnalysis(sortedDocs, prize);
      const currentCycle =
        analysis.cycles.length > 0
          ? analysis.cycles[analysis.cycles.length - 1]
          : null;

      return {
        prize,
        totalDrawsWithPrize: analysis.totalDrawsWithPrize,
        totalCycles: analysis.cycles.length,
        completedCycles: analysis.cycles.filter((c) => c.status === "COMPLETED")
          .length,
        firstDate: analysis.firstDate,
        latestDate: analysis.latestDate,
        currentCycleNumber: currentCycle?.cycleNumber || null,
        currentStatus: currentCycle?.status || null,
        currentUniqueNumbersSeen: currentCycle?.uniqueNumbersSeen || 0,
        currentRemainingCount: currentCycle?.remainingCount || 0,
        currentProgressPercent: currentCycle?.progressPercent || 0,
      };
    });

    res.json({
      datasetSummary: {
        totalDraws: sortedDocs.length,
        firstDate: sortedDocs[0]?.date || null,
        latestDate: sortedDocs[sortedDocs.length - 1]?.date || null,
        prizeCategories,
      },
      prizeSummaries,
    });
  } catch (err) {
    console.error("❌ all-prize-cycles error:", err.message);
    res.status(500).json({
      error: "Failed to load prize cycle summary",
      details: err.message,
    });
  }
});

app.get("/api/all-prize-cycles/:prize", async (req, res) => {
  try {
    const prize = Number(req.params.prize);

    if (!prize || Number.isNaN(prize)) {
      return res.status(400).json({ error: "Invalid prize" });
    }

    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildPrizeCycleAnalysis(docs, prize);

    const currentCycle =
      analysis.cycles.length > 0
        ? analysis.cycles[analysis.cycles.length - 1]
        : null;

    res.json({
      prize: analysis.prize,
      totalDrawsWithPrize: analysis.totalDrawsWithPrize,
      totalPossibleNumbers: analysis.totalPossibleNumbers,
      firstDate: analysis.firstDate,
      latestDate: analysis.latestDate,
      totalCycles: analysis.cycles.length,
      completedCycles: analysis.cycles.filter((c) => c.status === "COMPLETED")
        .length,
      currentCycleNumber: currentCycle?.cycleNumber || null,
      currentStatus: currentCycle?.status || null,
      cycles: analysis.cycles.map((cycle) => ({
        cycleNumber: cycle.cycleNumber,
        prize: cycle.prize,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
      })),
    });
  } catch (err) {
    console.error("❌ all-prize-cycles/:prize error:", err.message);
    res.status(500).json({
      error: "Failed to load prize cycles",
      details: err.message,
    });
  }
});

app.get("/api/all-prize-cycles/:prize/:cycleNumber", async (req, res) => {
  try {
    const prize = Number(req.params.prize);
    const cycleNumber = Number(req.params.cycleNumber);

    if (!prize || Number.isNaN(prize)) {
      return res.status(400).json({ error: "Invalid prize" });
    }

    if (!cycleNumber || cycleNumber < 1) {
      return res.status(400).json({ error: "Invalid cycle number" });
    }

    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildPrizeCycleAnalysis(docs, prize);
    const cycle = analysis.cycles.find((c) => c.cycleNumber === cycleNumber);

    if (!cycle) {
      return res.status(404).json({ error: "Cycle not found" });
    }

    res.json({
      cycle,
    });
  } catch (err) {
    console.error(
      "❌ all-prize-cycles/:prize/:cycleNumber error:",
      err.message,
    );
    res.status(500).json({
      error: "Failed to load prize cycle detail",
      details: err.message,
    });
  }
});

//tactic
function getNumberToPrizeMap(doc) {
  const map = new Map();

  for (const series of doc.series || []) {
    const prize = Number(series.prize);

    for (const item of series.numbers || []) {
      const num = String(item.number || "").trim();
      if (!/^\d{4}$/.test(num)) continue;

      if (!map.has(num)) {
        map.set(num, []);
      }

      map.get(num).push(prize);
    }
  }

  for (const [num, prizes] of map.entries()) {
    map.set(
      num,
      [...new Set(prizes)].sort((a, b) => b - a),
    );
  }

  return map;
}

function getUniqueNumbersFromDoc(doc) {
  const set = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      const num = String(item.number || "").trim();
      if (/^\d{4}$/.test(num)) {
        set.add(num);
      }
    }
  }

  return [...set].sort();
}

// function buildFullCycleStateTimeline(docs = []) {
//   const ALL = generateAll4DigitNumbers();
//   const sortedDocs = sortDocsChronologically(docs);

//   const seen = new Set();
//   const timeline = [];

//   for (const doc of sortedDocs) {
//     const remainingBefore = ALL.filter((n) => !seen.has(n));
//     const drawNumbers = getUniqueNumbersFromDoc(doc);
//     const prizeMap = getNumberToPrizeMap(doc);

//     const hitsFromRemaining = drawNumbers
//       .filter((num) => !seen.has(num))
//       .map((num) => ({
//         number: num,
//         prizes: prizeMap.get(num) || [],
//       }))
//       .sort((a, b) => a.number.localeCompare(b.number));

//     for (const num of drawNumbers) {
//       seen.add(num);
//     }

//     const remainingAfter = ALL.filter((n) => !seen.has(n));

//     timeline.push({
//       recordNumber: doc.recordNumber || null,
//       serialNumber: doc.serialNumber || "",
//       date: doc.date || "",
//       drawDate: doc.drawDate || null,
//       fileName: doc.fileName || "",
//       remainingBeforeCount: remainingBefore.length,
//       remainingBefore,
//       drawUniqueNumbersCount: drawNumbers.length,
//       drawUniqueNumbers: drawNumbers,
//       hitsFromRemainingCount: hitsFromRemaining.length,
//       hitsFromRemaining,
//       remainingAfterCount: remainingAfter.length,
//       remainingAfter,
//     });
//   }

//   return timeline;
// }

function buildUniqueCycleTimeline(docs = []) {
  const ALL = generateAll4DigitNumbers();
  const sortedDocs = sortDocsChronologically(docs);

  const seen = new Set();
  const timeline = [];

  for (const doc of sortedDocs) {
    const remainingBefore = ALL.filter((n) => !seen.has(n));
    const drawNumbers = getUniqueNumbersFromDoc(doc);
    const prizeMap = getNumberToPrizeMap(doc);

    const hitsFromRemaining = drawNumbers
      .filter((num) => !seen.has(num))
      .map((num) => ({
        number: num,
        prizes: prizeMap.get(num) || [],
      }))
      .sort((a, b) => a.number.localeCompare(b.number));

    for (const num of drawNumbers) {
      seen.add(num);
    }

    const remainingAfter = ALL.filter((n) => !seen.has(n));

    timeline.push({
      recordNumber: doc.recordNumber || null,
      serialNumber: doc.serialNumber || "",
      date: doc.date || "",
      drawDate: doc.drawDate || null,
      fileName: doc.fileName || "",
      remainingBeforeCount: remainingBefore.length,
      remainingBefore,
      drawUniqueNumbersCount: drawNumbers.length,
      drawUniqueNumbers: drawNumbers,
      hitsFromRemainingCount: hitsFromRemaining.length,
      hitsFromRemaining,
      remainingAfterCount: remainingAfter.length,
      remainingAfter,
    });
  }

  return timeline;
}

function average(arr = []) {
  if (!arr.length) return 0;
  return Number((arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(2));
}

function weightedAverage(arr = []) {
  if (!arr.length) return 0;

  let weightedSum = 0;
  let totalWeight = 0;

  arr.forEach((val, idx) => {
    const weight = idx + 1;
    weightedSum += val * weight;
    totalWeight += weight;
  });

  return Number((weightedSum / totalWeight).toFixed(2));
}

function buildGlobalUniqueCycles(docs = []) {
  const TOTAL_NUMBERS = 10000;
  const ALL_NUMBERS = generateAll4DigitNumbers();
  const sortedDocs = sortDocsChronologically(docs);

  const cycles = [];

  let cycleNumber = 1;
  let seenInCycle = new Set();
  let firstSeenMap = new Map();
  let cycleStartDoc = null;
  let drawTimeline = [];

  for (const doc of sortedDocs) {
    const drawNumbers = getUniqueNumbersFromDoc(doc);
    if (!drawNumbers.length) continue;

    if (!cycleStartDoc) {
      cycleStartDoc = doc;
    }

    const remainingBefore = ALL_NUMBERS.filter((n) => !seenInCycle.has(n));
    const prizeMap = getNumberToPrizeMap(doc);

    const newNumbers = [];

    for (const num of drawNumbers) {
      if (!seenInCycle.has(num)) {
        seenInCycle.add(num);
        newNumbers.push({
          number: num,
          prizes: prizeMap.get(num) || [],
        });

        if (!firstSeenMap.has(num)) {
          firstSeenMap.set(num, {
            number: num,
            firstSeenDate: doc.date || "",
            firstSeenSerialNumber: doc.serialNumber || "",
            recordNumber: doc.recordNumber || null,
            fileName: doc.fileName || "",
            prizes: prizeMap.get(num) || [],
          });
        }
      }
    }

    const remainingAfter = ALL_NUMBERS.filter((n) => !seenInCycle.has(n));

    drawTimeline.push({
      recordNumber: doc.recordNumber || null,
      serialNumber: doc.serialNumber || "",
      date: doc.date || "",
      fileName: doc.fileName || "",
      drawUniqueNumbersCount: drawNumbers.length,
      drawUniqueNumbers: drawNumbers,
      remainingBeforeCount: remainingBefore.length,
      remainingBefore,
      newNumbersCount: newNumbers.length,
      newNumbers,
      totalSeenAfterDraw: seenInCycle.size,
      remainingAfterCount: remainingAfter.length,
      remainingAfter,
      progressPercent: Number(
        ((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2),
      ),
    });

    if (seenInCycle.size === TOTAL_NUMBERS) {
      const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
        a.number.localeCompare(b.number),
      );

      cycles.push({
        cycleNumber,
        status: "COMPLETED",
        startDate: cycleStartDoc?.date || "",
        startSerialNumber: cycleStartDoc?.serialNumber || "",
        startRecordNumber: cycleStartDoc?.recordNumber || null,
        endDate: doc.date || "",
        endSerialNumber: doc.serialNumber || "",
        endRecordNumber: doc.recordNumber || null,
        drawsCount: drawTimeline.length,
        uniqueNumbersSeen: seenInCycle.size,
        remainingCount: 0,
        progressPercent: 100,
        remainingNumbers: [],
        firstSeenNumbers,
        drawTimeline,
      });

      cycleNumber += 1;
      seenInCycle = new Set();
      firstSeenMap = new Map();
      cycleStartDoc = null;
      drawTimeline = [];
    }
  }

  if (cycleStartDoc || seenInCycle.size > 0 || cycles.length === 0) {
    const remainingNumbers = ALL_NUMBERS.filter((n) => !seenInCycle.has(n));
    const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
      a.number.localeCompare(b.number),
    );

    const lastDoc = sortedDocs[sortedDocs.length - 1] || null;

    cycles.push({
      cycleNumber,
      status: "IN_PROGRESS",
      startDate: cycleStartDoc?.date || "",
      startSerialNumber: cycleStartDoc?.serialNumber || "",
      startRecordNumber: cycleStartDoc?.recordNumber || null,
      endDate: lastDoc?.date || "",
      endSerialNumber: lastDoc?.serialNumber || "",
      endRecordNumber: lastDoc?.recordNumber || null,
      drawsCount: drawTimeline.length,
      uniqueNumbersSeen: seenInCycle.size,
      remainingCount: remainingNumbers.length,
      progressPercent: Number(
        ((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2),
      ),
      remainingNumbers,
      firstSeenNumbers,
      drawTimeline,
    });
  }

  return {
    totalDraws: sortedDocs.length,
    totalPossibleNumbers: TOTAL_NUMBERS,
    cycles,
  };
}

function buildLikelyNextUnseenForCycle(cycle, recentWindow = 14, topN = 100) {
  if (!cycle || !cycle.drawTimeline?.length) {
    return {
      recentWindow,
      recentHitNumbers: [],
      candidates: [],
    };
  }

  const recent = cycle.drawTimeline.slice(-recentWindow);

  const recentHitNumbers = [
    ...new Set(
      recent.flatMap((day) => (day.newNumbers || []).map((x) => x.number)),
    ),
  ].sort();

  const remainingNow = cycle.remainingNumbers || [];
  const scoreMap = new Map();

  for (const day of cycle.drawTimeline) {
    const drawSet = new Set(day.drawUniqueNumbers || []);
    const intersectsRecent = recentHitNumbers.some((n) => drawSet.has(n));

    if (!intersectsRecent) continue;

    for (const num of remainingNow) {
      if (drawSet.has(num)) {
        scoreMap.set(num, (scoreMap.get(num) || 0) + 1);
      }
    }
  }

  const candidates = remainingNow
    .map((num) => ({
      number: num,
      score: scoreMap.get(num) || 0,
    }))
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.number.localeCompare(b.number);
    })
    .slice(0, topN);

  return {
    recentWindow,
    recentHitNumbers,
    candidates,
  };
}

app.get("/api/global-unique-cycles", async (req, res) => {
  try {
    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildGlobalUniqueCycles(docs);

    const currentCycle =
      analysis.cycles.length > 0
        ? analysis.cycles[analysis.cycles.length - 1]
        : null;

    res.json({
      datasetSummary: {
        totalDraws: analysis.totalDraws,
        totalPossibleNumbers: analysis.totalPossibleNumbers,
        totalCycles: analysis.cycles.length,
        completedCycles: analysis.cycles.filter((c) => c.status === "COMPLETED")
          .length,
        currentCycleNumber: currentCycle?.cycleNumber || null,
        currentCycleStatus: currentCycle?.status || null,
        currentUniqueNumbersSeen: currentCycle?.uniqueNumbersSeen || 0,
        currentRemainingCount: currentCycle?.remainingCount || 0,
        currentProgressPercent: currentCycle?.progressPercent || 0,
        firstDate: analysis.cycles[0]?.startDate || null,
        latestDate: currentCycle?.endDate || null,
      },
      cycles: analysis.cycles.map((cycle) => ({
        cycleNumber: cycle.cycleNumber,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
      })),
    });
  } catch (err) {
    console.error("❌ global-unique-cycles error:", err.message);
    res.status(500).json({
      error: "Failed to load global unique cycles",
      details: err.message,
    });
  }
});
app.get("/api/global-unique-cycles/:cycleNumber", async (req, res) => {
  try {
    const cycleNumber = Number(req.params.cycleNumber);

    if (!cycleNumber || cycleNumber < 1) {
      return res.status(400).json({ error: "Invalid cycle number" });
    }

    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildGlobalUniqueCycles(docs);
    const cycle = analysis.cycles.find((c) => c.cycleNumber === cycleNumber);

    if (!cycle) {
      return res.status(404).json({ error: "Cycle not found" });
    }

    const counts = cycle.drawTimeline.map((d) => d.newNumbersCount);
    const last7 = counts.slice(-7);
    const last14 = counts.slice(-14);
    const last30 = counts.slice(-30);

    const nextLikely = buildLikelyNextUnseenForCycle(cycle, 14, 100);

    res.json({
      cycle: {
        cycleNumber: cycle.cycleNumber,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
        remainingNumbers: cycle.remainingNumbers,
        drawTimeline: cycle.drawTimeline,
      },
      recentStats: {
        avgLast7: average(last7),
        avgLast14: average(last14),
        avgLast30: average(last30),
        weightedAvgLast14: weightedAverage(last14),
      },
      nextLikely,
    });
  } catch (err) {
    console.error("❌ global-unique-cycles/:cycleNumber error:", err.message);
    res.status(500).json({
      error: "Failed to load cycle detail",
      details: err.message,
    });
  }
});

//prize-unique cycle
function computePrizeStats(prizeSeen = {}) {
  const TOTAL = 10000;
  const stats = {};

  for (const [prize, set] of Object.entries(prizeSeen)) {
    const p = Number(prize);
    const seen = set.size;
    stats[p] = {
      seen,
      remaining: TOTAL - seen,
      progress: Number(((seen / TOTAL) * 100).toFixed(2)),
    };
  }

  return stats;
}

function buildMergedCycles(docs = []) {
  const TOTAL = 10000;
  const ALL = generateAll4DigitNumbers();
  const sortedDocs = sortDocsChronologically(docs);

  const cycles = [];
  let cycleNumber = 1;
  let globalSeen = new Set();
  let prizeSeen = {}; // <-- tracks prize progress WITHIN current global cycle
  let cycleStartDoc = null;
  let drawTimeline = [];

  const resetState = () => {
    globalSeen = new Set();
    prizeSeen = {};
    cycleStartDoc = null;
    drawTimeline = [];
  };

  for (const doc of sortedDocs) {
    const drawNumbers = getUniqueNumbersFromDoc(doc);
    if (!drawNumbers.length) continue;

    if (!cycleStartDoc) {
      cycleStartDoc = doc;
    }

    const prizeMap = getNumberToPrizeMap(doc);

    const newGlobalNumbers = [];
    const prizeUpdates = {};

    const prizesInDraw = new Set();
    for (const series of doc.series || []) {
      if (series.prize != null) {
        prizesInDraw.add(Number(series.prize));
      }
    }

    // Initialize prizeSeen for prizes in this draw
    for (const p of prizesInDraw) {
      if (!prizeSeen[p]) prizeSeen[p] = new Set();
      prizeUpdates[p] = {
        newNumbers: [],
        seenAfter: 0,
        remainingAfter: TOTAL,
        progress: 0,
      };
    }

    // Process each number in the draw
    for (const num of drawNumbers) {
      const prizes = prizeMap.get(num) || [];
      const isNewGlobal = !globalSeen.has(num);

      if (isNewGlobal) {
        globalSeen.add(num);
        newGlobalNumbers.push({
          number: num,
          prizes,
        });
      }

      // Update prizeSeen for each prize this number belongs to
      for (const p of prizes) {
        if (!prizeSeen[p]) prizeSeen[p] = new Set();

        if (!prizeSeen[p].has(num)) {
          prizeSeen[p].add(num);
          if (!prizeUpdates[p]) {
            prizeUpdates[p] = {
              newNumbers: [],
              seenAfter: 0,
              remainingAfter: TOTAL,
              progress: 0,
            };
          }
          prizeUpdates[p].newNumbers.push(num);
        }
      }
    }

    // Calculate stats after processing all numbers in this draw
    const globalRemainingAfter = TOTAL - globalSeen.size;
    const globalProgress = Number(((globalSeen.size / TOTAL) * 100).toFixed(2));

    for (const p of Object.keys(prizeUpdates)) {
      const pp = Number(p);
      const seenCount = prizeSeen[pp].size;
      prizeUpdates[pp].seenAfter = seenCount;
      prizeUpdates[pp].remainingAfter = TOTAL - seenCount;
      prizeUpdates[pp].progress = Number(
        ((seenCount / TOTAL) * 100).toFixed(2),
      );
    }

    // Record this draw in timeline
    drawTimeline.push({
      recordNumber: doc.recordNumber || null,
      serialNumber: doc.serialNumber || "",
      date: doc.date || "",
      fileName: doc.fileName || "",
      drawUniqueNumbersCount: drawNumbers.length,
      newGlobalNumbersCount: newGlobalNumbers.length,
      newGlobalNumbers,
      globalRemainingAfter,
      globalProgress,
      prizeUpdates,
    });

    // If global cycle completed (all 10000 numbers seen)
    if (globalSeen.size === TOTAL) {
      cycles.push({
        cycleNumber,
        status: "COMPLETED",
        startDate: cycleStartDoc?.date || "",
        startSerialNumber: cycleStartDoc?.serialNumber || "",
        startRecordNumber: cycleStartDoc?.recordNumber || null,
        endDate: doc.date || "",
        endSerialNumber: doc.serialNumber || "",
        endRecordNumber: doc.recordNumber || null,
        drawsCount: drawTimeline.length,
        uniqueNumbersSeen: globalSeen.size,
        remainingCount: 0,
        progressPercent: 100,
        remainingNumbers: [],
        drawTimeline,
        prizeStats: computePrizeStats(prizeSeen), // <-- prize progress FOR THIS CYCLE
      });

      cycleNumber += 1;
      resetState(); // <-- resets prizeSeen too
    }
  }

  // If last cycle is still in progress
  if (cycleStartDoc || globalSeen.size > 0 || cycles.length === 0) {
    const remainingNumbers = ALL.filter((n) => !globalSeen.has(n));
    const lastDoc = sortedDocs[sortedDocs.length - 1] || null;

    cycles.push({
      cycleNumber,
      status: "IN_PROGRESS",
      startDate: cycleStartDoc?.date || "",
      startSerialNumber: cycleStartDoc?.serialNumber || "",
      startRecordNumber: cycleStartDoc?.recordNumber || null,
      endDate: lastDoc?.date || "",
      endSerialNumber: lastDoc?.serialNumber || "",
      endRecordNumber: lastDoc?.recordNumber || null,
      drawsCount: drawTimeline.length,
      uniqueNumbersSeen: globalSeen.size,
      remainingCount: remainingNumbers.length,
      progressPercent: Number(((globalSeen.size / TOTAL) * 100).toFixed(2)),
      remainingNumbers,
      drawTimeline,
      prizeStats: computePrizeStats(prizeSeen),
    });
  }

  return {
    totalDraws: sortedDocs.length,
    cycles,
  };
}

// Helper to get all prize categories from docs
function getAllPrizeCategories(docs = []) {
  const prizes = new Set();
  for (const doc of docs) {
    for (const series of doc.series || []) {
      if (series.prize != null) {
        prizes.add(Number(series.prize));
      }
    }
  }
  return [...prizes].sort((a, b) => a - b);
}

// Helper to build prize cycle analysis (for current cycle selector)
function buildPrizeCycleAnalysis(docs = [], targetPrize) {
  const TOTAL = 10000;
  const ALL = generateAll4DigitNumbers();
  const sortedDocs = sortDocsChronologically(docs);

  const cycles = [];
  let cycleNumber = 1;
  let seenInCycle = new Set();
  let cycleStartDoc = null;
  let drawTimeline = [];

  for (const doc of sortedDocs) {
    const prizeBlock = doc.series?.find((s) => s.prize === targetPrize);
    const numbersInBlock = prizeBlock
      ? prizeBlock.numbers.map((n) => String(n.number).padStart(4, "0"))
      : [];

    if (!cycleStartDoc && numbersInBlock.length > 0) {
      cycleStartDoc = doc;
    }

    if (numbersInBlock.length === 0) continue;

    const remainingBefore = ALL.filter((n) => !seenInCycle.has(n));
    const newNumbers = numbersInBlock.filter((num) => !seenInCycle.has(num));

    for (const num of newNumbers) {
      seenInCycle.add(num);
    }

    const remainingAfter = ALL.filter((n) => !seenInCycle.has(n));

    drawTimeline.push({
      recordNumber: doc.recordNumber || null,
      serialNumber: doc.serialNumber || "",
      date: doc.date || "",
      fileName: doc.fileName || "",
      newNumbersCount: newNumbers.length,
      newNumbers,
      remainingBeforeCount: remainingBefore.length,
      remainingAfterCount: remainingAfter.length,
      progressPercent: Number(((seenInCycle.size / TOTAL) * 100).toFixed(2)),
    });

    if (seenInCycle.size === TOTAL) {
      cycles.push({
        cycleNumber,
        status: "COMPLETED",
        startDate: cycleStartDoc?.date || "",
        startSerialNumber: cycleStartDoc?.serialNumber || "",
        endDate: doc.date || "",
        endSerialNumber: doc.serialNumber || "",
        drawsCount: drawTimeline.length,
        uniqueNumbersSeen: seenInCycle.size,
        remainingCount: 0,
        progressPercent: 100,
        drawTimeline: [...drawTimeline],
      });

      cycleNumber += 1;
      seenInCycle = new Set();
      cycleStartDoc = null;
      drawTimeline = [];
    }
  }

  if (drawTimeline.length > 0) {
    const seenList = [...seenInCycle].sort();
    const remainingList = ALL.filter((n) => !seenInCycle.has(n));

    cycles.push({
      cycleNumber,
      status: "IN_PROGRESS",
      startDate: cycleStartDoc?.date || "",
      startSerialNumber: cycleStartDoc?.serialNumber || "",
      endDate: sortedDocs[sortedDocs.length - 1]?.date || "",
      endSerialNumber: sortedDocs[sortedDocs.length - 1]?.serialNumber || "",
      drawsCount: drawTimeline.length,
      uniqueNumbersSeen: seenInCycle.size,
      remainingCount: 10000 - seenInCycle.size,
      progressPercent: Number(((seenInCycle.size / 10000) * 100).toFixed(2)),
      remainingNumbers: remainingList,
      seenNumbers: seenList,
      drawTimeline: [...drawTimeline],
    });
  }

  return {
    totalCycles: cycles.length,
    cycles: cycles,
  };
}

// Routes

app.get("/api/merged-cycles", async (req, res) => {
  try {
    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildMergedCycles(docs);
    const sortedDocs = sortDocsChronologically(docs);

    const currentCycle =
      analysis.cycles.length > 0
        ? analysis.cycles[analysis.cycles.length - 1]
        : null;

    // Calculate current active cycle for EACH prize block independently
    const prizeCategories = getAllPrizeCategories(sortedDocs);
    const currentPrizeCycles = {};

    for (const prize of prizeCategories) {
      const prizeAnalysis = buildPrizeCycleAnalysis(sortedDocs, prize);
      const currentPrizeCycle =
        prizeAnalysis.cycles.length > 0
          ? prizeAnalysis.cycles[prizeAnalysis.cycles.length - 1]
          : null;

      if (currentPrizeCycle) {
        currentPrizeCycles[prize] = {
          prizeCycleNumber: currentPrizeCycle.cycleNumber,
          prizeCycleStatus: currentPrizeCycle.status,
          seen: currentPrizeCycle.uniqueNumbersSeen,
          remaining: currentPrizeCycle.remainingCount,
          progress: currentPrizeCycle.progressPercent,
          remainingNumbers: currentPrizeCycle.remainingNumbers,
        };
      }
    }

    res.json({
      datasetSummary: {
        totalDraws: analysis.totalDraws,
        totalCycles: analysis.cycles.length,
        completedCycles: analysis.cycles.filter((c) => c.status === "COMPLETED")
          .length,
        currentCycleNumber: currentCycle?.cycleNumber || null,
        currentCycleStatus: currentCycle?.status || null,
        currentUniqueNumbersSeen: currentCycle?.uniqueNumbersSeen || 0,
        currentRemainingCount: currentCycle?.remainingCount || 0,
        currentProgressPercent: currentCycle?.progressPercent || 0,
        firstDate: analysis.cycles[0]?.startDate || null,
        latestDate: currentCycle?.endDate || null,
      },
      cycles: analysis.cycles.map((cycle) => ({
        cycleNumber: cycle.cycleNumber,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
      })),
      currentPrizeCycles,
    });
  } catch (err) {
    console.error("❌ merged-cycles error:", err.message);
    res.status(500).json({
      error: "Failed to load merged cycles",
      details: err.message,
    });
  }
});

app.get("/api/merged-cycles/:cycleNumber", async (req, res) => {
  try {
    const cycleNumber = Number(req.params.cycleNumber);

    if (!cycleNumber || cycleNumber < 1) {
      return res.status(400).json({ error: "Invalid cycle number" });
    }

    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    const analysis = buildMergedCycles(docs);
    const cycle = analysis.cycles.find((c) => c.cycleNumber === cycleNumber);

    if (!cycle) {
      return res.status(404).json({ error: "Cycle not found" });
    }

    res.json({
      cycle: {
        cycleNumber: cycle.cycleNumber,
        status: cycle.status,
        startDate: cycle.startDate,
        startSerialNumber: cycle.startSerialNumber,
        startRecordNumber: cycle.startRecordNumber,
        endDate: cycle.endDate,
        endSerialNumber: cycle.endSerialNumber,
        endRecordNumber: cycle.endRecordNumber,
        drawsCount: cycle.drawsCount,
        uniqueNumbersSeen: cycle.uniqueNumbersSeen,
        remainingCount: cycle.remainingCount,
        progressPercent: cycle.progressPercent,
        remainingNumbers: cycle.remainingNumbers,
        prizeStats: cycle.prizeStats || {},
        drawTimeline: cycle.drawTimeline,
      },
    });
  } catch (err) {
    console.error("❌ merged-cycles/:cycleNumber error:", err.message);
    res.status(500).json({
      error: "Failed to load merged cycle detail",
      details: err.message,
    });
  }
});

//crosscheck
app.get("/api/current-cycle-comparison", async (req, res) => {
  try {
    const docs = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    // Build global cycles to get current cycle (Cycle 5)
    const globalAnalysis = buildGlobalUniqueCycles(docs);
    const currentGlobalCycle =
      globalAnalysis.cycles.length > 0
        ? globalAnalysis.cycles[globalAnalysis.cycles.length - 1]
        : null;

    if (!currentGlobalCycle) {
      return res.status(404).json({ error: "No global cycle found" });
    }

    // Build current prize cycles for each prize
    const PRIZE_AMOUNTS = [5000, 2000, 1000, 500, 200, 100, 50];
    const currentPrizeCycles = {};

    for (const prize of PRIZE_AMOUNTS) {
      const prizeAnalysis = buildPrizeCycleAnalysis(docs, prize);
      const currentPrizeCycle =
        prizeAnalysis.cycles.length > 0
          ? prizeAnalysis.cycles[prizeAnalysis.cycles.length - 1]
          : null;

      if (currentPrizeCycle) {
        currentPrizeCycles[prize] = {
          cycleNumber: currentPrizeCycle.cycleNumber,
          status: currentPrizeCycle.status,
          seen: currentPrizeCycle.uniqueNumbersSeen,
          remaining: currentPrizeCycle.remainingCount,
          progress: currentPrizeCycle.progressPercent,
          remainingNumbers: currentPrizeCycle.remainingNumbers || [],
          seenNumbers: currentPrizeCycle.seenNumbers || [],
        };
      }
    }

    res.json({
      lastUpdated: new Date().toISOString(),
      globalCycle: {
        cycleNumber: currentGlobalCycle.cycleNumber,
        status: currentGlobalCycle.status,
        startDate: currentGlobalCycle.startDate,
        endDate: currentGlobalCycle.endDate || "Ongoing",
        uniqueNumbersSeen: currentGlobalCycle.uniqueNumbersSeen,
        remainingCount: currentGlobalCycle.remainingCount,
        progressPercent: currentGlobalCycle.progressPercent,
        remainingNumbers: currentGlobalCycle.remainingNumbers || [],
      },
      prizeCycles: currentPrizeCycles,
    });
  } catch (err) {
    console.error("❌ current-cycle-comparison error:", err.message);
    res.status(500).json({
      error: "Failed to load current cycle comparison",
      details: err.message,
    });
  }
});

//Absolute data
const ABSOLUTE_PRIZE_AMOUNTS = [5000, 1000];
app.get("/api/absolute-folder", async (req, res) => {
  try {
    const folderPath = path.join(process.cwd(), "Afiles");
    const files = fs
      .readdirSync(folderPath)
      .filter((f) => f.toLowerCase().endsWith(".pdf"));

    console.log(`🚀 [START] Processing ${files.length} files.`);
    const summary = [];

    for (const fileName of files) {
      console.log(`\n--- 📄 FILE: ${fileName} ---`);
      try {
        const buffer = fs.readFileSync(path.join(folderPath, fileName));
        const pdfData = await PdfParse(buffer);
        const rawText = pdfData.text || "";

        const startMarker = "FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS";
        const splitIndex = rawText
          .toLowerCase()
          .indexOf(startMarker.toLowerCase());

        if (splitIndex === -1) {
          console.log(`   ❌ Skipped: Start marker not found.`);
          summary.push({
            fileName,
            status: "Skipped",
            reason: "Marker not found",
          });
          continue;
        }

        const upperSection = rawText.substring(0, splitIndex);
        const rawPrizeSection = rawText.substring(
          splitIndex + startMarker.length,
        );

        const serialNumber = extractSerialNumber(upperSection);
        const date = extractDateFromText(upperSection);

        console.log(`   🆔 ${serialNumber} | 📅 ${date}`);

        if (serialNumber === "Unknown" || date === "Unknown") {
          summary.push({
            fileName,
            status: "Skipped",
            reason: "Metadata error",
          });
          continue;
        }

        const prizeNumbers = getPrizeNumbersByAmount(rawPrizeSection);

        // --- 🔍 DETAILED INSPECTION LOG ---
        console.log(`   📊 EXTRACTION SUMMARY FOR ${serialNumber}:`);

        const sortedAmounts = Object.keys(prizeNumbers).sort((a, b) => b - a);

        sortedAmounts.forEach((amt) => {
          const numbers = prizeNumbers[amt];

          const hasYearIssue = numbers.some((n) =>
            ["2020", "2021", "2022", "2023", "2024", "2025", "2026"].includes(
              n,
            ),
          );

          console.log(
            `      💰 ₹${amt.padEnd(5)} [Total: ${String(numbers.length).padStart(3)}]`,
          );

          if (numbers.length > 0) {
            const displayList =
              numbers.length > 20
                ? `${numbers.slice(0, 10).join(", ")} ... ${numbers.slice(-10).join(", ")}`
                : numbers.join(", ");

            console.log(`         🔢 ${displayList}`);

            if (hasYearIssue) {
              console.log(
                `         ⚠️  WARNING: Potential year detected in this prize tier!`,
              );
            }
          } else {
            console.log(`         ❌ No numbers found for this prize.`);
          }
        });

        const missing = ABSOLUTE_PRIZE_AMOUNTS.filter(
          (amt) => !prizeNumbers[amt] || prizeNumbers[amt].length === 0,
        );

        if (missing.length > 0) {
          const reason = `Missing required amounts: ${missing.join(", ")}`;
          console.log(`   ⚠️ [VALIDATION] Skipped: ${reason}`);
          summary.push({ fileName, status: "Skipped", reason });
          continue;
        }

        // 4. Duplicate Check using AbsoluteData
        const exists = await AbsoluteData.findOne({ serialNumber }).lean();
        if (exists) {
          console.log(`   🚫 Duplicate record.`);
          summary.push({ fileName, status: "Duplicate", serialNumber });
          continue;
        }

        // 5. Save to AbsoluteData
        const series = Object.entries(prizeNumbers).map(([amt, numbers]) => ({
          prize: Number(amt),
          numbers: numbers.map((n) => ({ number: n, count: 1 })),
        }));

        const newDoc = new AbsoluteData({
          serialNumber,
          date,
          drawDate: ddmmyyyyToUTCDate(date),
          fileName,
          series,
        });

        await newDoc.save();
        console.log(`   ✅ Saved Successfully to AbsoluteData.`);
        summary.push({ fileName, status: "Saved", serialNumber });
      } catch (err) {
        console.error(`   🔥 Error: ${err.message}`);
        summary.push({ fileName, status: "Error", error: err.message });
      }
    }

    res.json({ status: "Complete", summary });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

//advanced
const models = {
  db1: require("./models/LotteryData"),
  db2: require("./models/LotteryDataNew"),
  db3: require("./models/FullLotteryData"),
  db4: require("./models/AbsoluteData"),
};

app.get("/api/cycles-advanced/:dbKey", async (req, res) => {
  try {
    const { dbKey } = req.params;

    const Model = models[dbKey];
    if (!Model) return res.status(400).json({ error: "Invalid dbKey" });

    // If you only want first 5 cycles (as you predicted), pass maxCycles=5
    const maxCycles = Math.max(Number(req.query.maxCycles || 5), 1);

    const includeDailyNumbers =
      String(req.query.includeDailyNumbers || "true") === "true";

    // Fetch all docs (can be heavy). Consider adding date range + indexes later.
    const docs = await Model.find({}).lean();

    const analysis = buildCycleAnalysisByDay(docs);

    // Keep only first N cycles (if you specifically want cycles 1..5)
    const cycles = analysis.cycles.slice(0, maxCycles);

    // If they want only daily counts (to reduce payload)
    let dailyTimeline = analysis.dailyTimeline;
    if (!includeDailyNumbers) {
      dailyTimeline = dailyTimeline.map((d) => ({
        cycleNumber: d.cycleNumber,
        date: d.date,
        uniqueNumbersInDay: d.uniqueNumbersInDay,
        newNumbersCount: d.newNumbersCount,
        totalSeenAfterDay: d.totalSeenAfterDay,
        progressPercent: d.progressPercent,
        // omit newNumbers array
      }));
      // Also omit remaining arrays per cycle if you want (optional)
      // cycles.forEach(c => { delete c.remainingNumbers; delete c.firstSeenNumbers; });
    }

    res.json({
      dbKey,
      summary: {
        totalDraws: analysis.totalDraws,
        totalPossibleNumbers: analysis.totalPossibleNumbers,
        totalCycles: analysis.totalCycles,
        returnedCycles: cycles.length,
      },
      cycles,
      dailyTimeline,
    });
  } catch (err) {
    console.error("❌ cycles-advanced error:", err);
    res
      .status(500)
      .json({ error: "Failed to build advanced cycles", details: err.message });
  }
});

// Quick check route - add to index.js
app.get("/api/check-absolute-data-full", async (req, res) => {
  try {
    const docs = await AbsoluteData.find({})
      .select("date drawDate serialNumber recordNumber fileName")
      .lean();

    if (docs.length === 0) {
      return res.json({ message: "No documents found in AbsoluteData" });
    }

    const { parseDDMMYYYYToDate } = require("./utils/cycleAnalysis");

    const docsWithParsedDate = docs.map((doc) => ({
      ...doc,
      parsedDate: doc.drawDate
        ? new Date(doc.drawDate)
        : parseDDMMYYYYToDate(doc.date || ""),
    }));

    // Sort chronologically
    const sorted = docsWithParsedDate.sort((a, b) => {
      if (!a.parsedDate || !b.parsedDate) return 0;
      return a.parsedDate - b.parsedDate;
    });

    const first = sorted[0];
    const last = sorted[sorted.length - 1];

    const firstDate = first.parsedDate
      ? first.parsedDate.toISOString().split("T")[0]
      : first.date;
    const lastDate = last.parsedDate
      ? last.parsedDate.toISOString().split("T")[0]
      : last.date;

    // Check for 11 July 2020
    const july11_2020 = new Date(Date.UTC(2020, 6, 11));
    const startsAt11July =
      first.parsedDate && first.parsedDate.getTime() === july11_2020.getTime();

    // Check ALL dates for chronological order
    let isChronological = true;
    const outOfOrderDates = [];

    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1].parsedDate;
      const curr = sorted[i].parsedDate;

      if (!prev || !curr) continue;

      if (prev.getTime() > curr.getTime()) {
        isChronological = false;
        outOfOrderDates.push({
          index: i,
          prevDate: prev.toISOString().split("T")[0],
          prevSerial: sorted[i - 1].serialNumber,
          currDate: curr.toISOString().split("T")[0],
          currSerial: sorted[i].serialNumber,
        });
      }
    }

    // Check for duplicate dates with filenames
    const dateMap = new Map();
    for (const doc of sorted) {
      const dateKey = doc.date;
      if (!dateMap.has(dateKey)) {
        dateMap.set(dateKey, []);
      }
      dateMap.get(dateKey).push({
        serialNumber: doc.serialNumber,
        recordNumber: doc.recordNumber,
        fileName: doc.fileName || "N/A",
      });
    }

    const duplicateDates = Array.from(dateMap.entries())
      .filter(([_, records]) => records.length > 1)
      .map(([date, records]) => ({
        date,
        recordCount: records.length,
        records, // all records for this date with filenames
      }));

    res.json({
      totalDocs: docs.length,
      firstDate: {
        date: firstDate,
        serialNumber: first.serialNumber,
        recordNumber: first.recordNumber,
      },
      lastDate: {
        date: lastDate,
        serialNumber: last.serialNumber,
        recordNumber: last.recordNumber,
      },
      startsAt11July2020: startsAt11July,
      isChronological,
      outOfOrderCount: outOfOrderDates.length,
      outOfOrderDates: outOfOrderDates.slice(0, 10),
      duplicateDatesCount: duplicateDates.length,
      duplicateDates, // now includes all records with filenames
      status:
        isChronological && duplicateDates.length === 0
          ? "✅ GOOD"
          : "⚠️ ISSUES FOUND",
    });
  } catch (err) {
    console.error("❌ check-absolute-data-full error:", err);
    res.status(500).json({ error: err.message });
  }
});

//hit compare

/**
 * Get detailed breakdown: which remaining numbers are in each prize's hit history
 */
app.get("/api/remaining-in-hit-history", async (req, res) => {
  try {
    const { dbKey = "db3", sourceDbKey = "db3" } = req.query;

    if (!["db3", "db4"].includes(dbKey)) {
      return res.status(400).json({ error: "dbKey must be db3 or db4" });
    }

    if (!["db3", "db4"].includes(sourceDbKey)) {
      return res.status(400).json({ error: "sourceDbKey must be db3 or db4" });
    }

    const models = {
      db3: FullLotteryData,
      db4: AbsoluteData,
    };

    const Model = models[dbKey];
    const SourceModel = models[sourceDbKey];

    console.log(`\n📊 REMAINING IN HIT HISTORY ANALYSIS`);
    console.log(`🎯 Target DB: ${dbKey}`);
    console.log(`📚 Source DB: ${sourceDbKey}`);

    // 1. Get remaining numbers from target DB
    const { buildCycleAnalysisByDay } = require("./utils/cycleAnalysis");

    const targetDocs = await Model.find({}).lean();
    const targetAnalysis = buildCycleAnalysisByDay(targetDocs);

    const latestCycle = targetAnalysis.cycles[targetAnalysis.cycles.length - 1];

    if (!latestCycle) {
      return res.status(404).json({ error: "No cycles found in target DB" });
    }

    const remainingNumbers = latestCycle.remainingNumbers || [];
    const dailyTimeline = latestCycle.dailyTimeline || [];

    console.log(`📋 Remaining Numbers: ${remainingNumbers.length}`);

    // 2. Extract hit history from source DB (by prize)
    const sourceDocs = await SourceModel.find({}).lean();
    const hitHistoryByPrize = extractHitHistoryFromDBByPrize(sourceDocs);

    console.log(
      `💰 Prize Tiers Found: ${Object.keys(hitHistoryByPrize).length}`,
    );

    // 3. For each prize, show which remaining numbers are in it
    const remainingByPrize = {};
    const remainingNotInAnyPrize = new Set(remainingNumbers);

    for (const [prize, prizeHistory] of Object.entries(hitHistoryByPrize)) {
      const prizeHistoryMap = new Map(prizeHistory.map((r) => [r.number, r]));

      const inThisPrize = [];

      for (const remainingNum of remainingNumbers) {
        if (prizeHistoryMap.has(remainingNum)) {
          const record = prizeHistoryMap.get(remainingNum);
          inThisPrize.push({
            number: remainingNum,
            totalHits: record.totalHits,
            avgGapDays: record.avgGapDays,
            lastDate:
              record.dates && record.dates.length > 0
                ? new Date(record.dates[record.dates.length - 1])
                    .toISOString()
                    .split("T")[0]
                : "Never",
            firstDate:
              record.dates && record.dates.length > 0
                ? new Date(record.dates[0]).toISOString().split("T")[0]
                : "Never",
            dateCount: record.dates.length,
          });

          remainingNotInAnyPrize.delete(remainingNum);
        }
      }

      // Sort by total hits
      inThisPrize.sort((a, b) => a.totalHits - b.totalHits);

      remainingByPrize[prize] = {
        count: inThisPrize.count,
        numbers: inThisPrize,
      };
    }

    console.log(`✅ Analysis Complete!`);

    // 4. Get today's breakdown
    let todayByPrize = null;

    if (dailyTimeline.length > 0) {
      const todayData = dailyTimeline[dailyTimeline.length - 1];
      const todayUniqueNumbers = todayData.newNumbers || [];

      todayByPrize = {};

      for (const [prize, prizeHistory] of Object.entries(hitHistoryByPrize)) {
        const prizeHistoryMap = new Map(prizeHistory.map((r) => [r.number, r]));

        const todayInThisPrize = [];

        for (const todayNum of todayUniqueNumbers) {
          if (prizeHistoryMap.has(todayNum)) {
            const record = prizeHistoryMap.get(todayNum);
            todayInThisPrize.push({
              number: todayNum,
              totalHits: record.totalHits,
              avgGapDays: record.avgGapDays,
              lastDate:
                record.dates && record.dates.length > 0
                  ? new Date(record.dates[record.dates.length - 1])
                      .toISOString()
                      .split("T")[0]
                  : "Never",
            });
          }
        }

        todayInThisPrize.sort((a, b) => a.totalHits - b.totalHits);

        todayByPrize[prize] = {
          count: todayInThisPrize.length,
          numbers: todayInThisPrize,
        };
      }
    }

    res.json({
      metadata: {
        targetDbKey: dbKey,
        targetDbName: dbKey === "db3" ? "FullLotteryData" : "AbsoluteData",
        sourceDbKey: sourceDbKey,
        sourceDbName:
          sourceDbKey === "db3" ? "FullLotteryData" : "AbsoluteData",
        cycleNumber: latestCycle.cycleNumber,
        remainingCount: remainingNumbers.length,
        prizeCount: Object.keys(hitHistoryByPrize).length,
      },
      remainingByPrize,
      notInAnyPrize: Array.from(remainingNotInAnyPrize),
      todayByPrize,
    });
  } catch (err) {
    console.error("❌ Error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * Helper: Extract hit history from DB grouped by prize
 */
function extractHitHistoryFromDBByPrize(docs) {
  const prizeMap = new Map();

  for (const doc of docs) {
    const date = doc.date || "Unknown";
    const dateObj = parseDDMMYYYYToDate(date);

    for (const series of doc.series || []) {
      const prize = series.prize || "All";

      if (!prizeMap.has(prize)) {
        prizeMap.set(prize, new Map());
      }

      const prizeNumbers = prizeMap.get(prize);

      for (const item of series.numbers || []) {
        const number = String(item.number || "").trim();
        if (!/^\d{4}$/.test(number)) continue;

        if (!prizeNumbers.has(number)) {
          prizeNumbers.set(number, {
            number,
            dates: [],
            totalHits: 0,
          });
        }

        const record = prizeNumbers.get(number);
        record.totalHits += 1;
        if (dateObj) {
          record.dates.push(dateObj);
        }
      }
    }
  }

  const result = {};

  for (const [prize, numberMap] of prizeMap.entries()) {
    result[prize] = Array.from(numberMap.values()).map((record) => {
      const avgGapDays = calculateAverageGap(record.dates);

      return {
        number: record.number,
        totalHits: record.totalHits,
        avgGapDays: avgGapDays,
        dates: record.dates,
      };
    });
  }

  return result;
}

/**
 * Calculate average gap between dates
 */
function calculateAverageGap(dates = []) {
  if (dates.length <= 1) return 0;

  const sortedDates = [...dates].sort((a, b) => a - b);
  let totalGap = 0;

  for (let i = 1; i < sortedDates.length; i++) {
    const gap = (sortedDates[i] - sortedDates[i - 1]) / (1000 * 60 * 60 * 24);
    totalGap += gap;
  }

  return Number((totalGap / (sortedDates.length - 1)).toFixed(2));
}

/**
 * Parse DD/MM/YYYY to Date
 */
function parseDDMMYYYYToDate(dateStr = "") {
  const match = String(dateStr).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  return new Date(Date.UTC(year, month - 1, day));
}

//
//grid update
//
// Get numbers for a specific prize from a specific DB
app.get("/api/prize-numbers/:dbKey/:prize", async (req, res) => {
  try {
    const { dbKey, prize } = req.params;
    const prizeAmount = Number(prize);

    const models = {
      db1: LotteryData,
      db2: LotteryDataNew,
      db3: FullLotteryData,
      db4: AbsoluteData,
    };

    const Model = models[dbKey];
    if (!Model) return res.status(400).json({ error: "Invalid dbKey" });

    const docs = await Model.find({}).lean();

    const numbersMap = new Map();

    for (const doc of docs) {
      for (const series of doc.series || []) {
        if (Number(series.prize) === prizeAmount) {
          for (const item of series.numbers || []) {
            const num = String(item.number || "").trim();
            if (/^\d{4}$/.test(num)) {
              const current = numbersMap.get(num) || { number: num, count: 0 };
              current.count += item.count || 1;
              numbersMap.set(num, current);
            }
          }
        }
      }
    }

    const numbers = Array.from(numbersMap.values()).sort((a, b) =>
      a.number.localeCompare(b.number),
    );

    res.json({
      prize: prizeAmount,
      totalUnique: numbers.length,
      numbers,
    });
  } catch (err) {
    console.error("❌ prize-numbers error:", err);
    res.status(500).json({ error: err.message });
  }
});

//new page
// ===== Cycle 5000 routes (Unique + Balance) =====
//const FullLotteryData = require("./models/FullLotteryData"); // adjust path if needed
//const AbsoluteData = require("./models/AbsoluteData"); // adjust path if needed

const PRIZE = 5000;
const TOTAL_NUMBERS = 10000;

// const parseDDMMYYYYToDate = (ddmmyyyy) => {
//   // ddmmyyyy like "01/02/2024"
//   // return a valid Date for sorting
//   const [dd, mm, yyyy] = (ddmmyyyy || "").split("/");
//   const day = Number(dd);
//   const monthIndex = Number(mm) - 1;
//   const year = Number(yyyy);
//   if (!day || !monthIndex && monthIndex !== 0 || !year) return new Date(0);
//   return new Date(Date.UTC(year, monthIndex, day));
// };

const isValid4Digits = (s) => /^\d{4}$/.test(String(s || "").trim());

// cache to avoid recomputing sets repeatedly
const cycleCache = new Map();
const CACHE_TTL_MS = 60 * 1000; // 1 minute

async function buildPrizeDateSets(Model) {
  // returns:
  // { dateKeysSorted: [...], dateToSet: Map(dateKey -> Set(numbers)) }
  const docs = await Model.find({}, { date: 1, series: 1 }).lean();

  const dateToSet = new Map();

  for (const doc of docs) {
    const dateKey = doc?.date;
    if (!dateKey) continue;

    let set = dateToSet.get(dateKey);
    if (!set) {
      set = new Set();
      dateToSet.set(dateKey, set);
    }

    for (const series of doc.series || []) {
      if (Number(series.prize) !== PRIZE) continue;

      for (const item of series.numbers || []) {
        const num = String(item?.number || "").trim();
        if (isValid4Digits(num)) set.add(num);
      }
    }
  }

  const dateKeysSorted = Array.from(dateToSet.keys()).sort(
    (a, b) => parseDDMMYYYYToDate(a) - parseDDMMYYYYToDate(b),
  );

  return { dateKeysSorted, dateToSet };
}

async function getCachedPrizeDateSets(dbKey) {
  const cacheKey = `${dbKey}_${PRIZE}`;
  const cached = cycleCache.get(cacheKey);
  const now = Date.now();

  if (cached && now - cached.createdAt < CACHE_TTL_MS) return cached.data;

  const models = {
    db3: FullLotteryData,
    db4: AbsoluteData,
  };

  const Model = models[dbKey];
  if (!Model) throw new Error("Invalid dbKey");

  const data = await buildPrizeDateSets(Model);
  cycleCache.set(cacheKey, { createdAt: now, data });
  return data;
}

// 1) Returns the cycle timeline (all dates) with uniqueCount + balanceCount
app.get("/api/cycle-5000/:dbKey", async (req, res) => {
  try {
    const { dbKey } = req.params;

    const { dateKeysSorted, dateToSet } = await getCachedPrizeDateSets(dbKey);

    const cumulative = new Set();
    const steps = [];

    for (const dateKey of dateKeysSorted) {
      const todaysSet = dateToSet.get(dateKey) || new Set();
      let addedCount = 0;

      for (const num of todaysSet) {
        if (!cumulative.has(num)) {
          cumulative.add(num);
          addedCount++;
        }
      }

      const uniqueCount = cumulative.size;
      const balanceCount = TOTAL_NUMBERS - uniqueCount;

      steps.push({
        dateKey,
        dateLabel: dateKey, // keep same format "DD/MM/YYYY"
        uniqueCount,
        balanceCount,
        addedCount,
      });
    }

    res.json({
      prize: PRIZE,
      totalNumbers: TOTAL_NUMBERS,
      steps,
    });
  } catch (err) {
    console.error("❌ /api/cycle-5000 error:", err);
    res.status(500).json({ error: err.message || "Failed to build cycle" });
  }
});

// 2) Returns cumulative unique numbers upto a specific date (query param dateKey)
app.get("/api/cycle-5000/cumulative/:dbKey", async (req, res) => {
  try {
    const { dbKey } = req.params;
    const { dateKey } = req.query;

    if (!dateKey) return res.status(400).json({ error: "Missing dateKey" });

    const { dateKeysSorted, dateToSet } = await getCachedPrizeDateSets(dbKey);

    const foundIndex = dateKeysSorted.indexOf(dateKey);
    if (foundIndex === -1) {
      return res.status(404).json({ error: "dateKey not found" });
    }

    const cumulative = new Set();

    for (let i = 0; i <= foundIndex; i++) {
      const dk = dateKeysSorted[i];
      const todaysSet = dateToSet.get(dk) || new Set();
      for (const num of todaysSet) cumulative.add(num);
    }

    const numbers = Array.from(cumulative).sort((a, b) => a.localeCompare(b));

    res.json({
      prize: PRIZE,
      dateKey,
      numbers,
      uniqueCount: numbers.length,
      balanceCount: TOTAL_NUMBERS - numbers.length,
    });
  } catch (err) {
    console.error("❌ /api/cycle-5000/cumulative error:", err);
    res
      .status(500)
      .json({ error: err.message || "Failed to fetch cumulative numbers" });
  }
});

// ========================================
// ==========================================
// CYCLES COMPARISON ROUTE (No Duplication)
// ==========================================
// Reuses buildGlobalUniqueCycles and buildPrizeCycleAnalysis
// GET /api/cycles/:dbKey?prize=5000
// ==========================================

app.get("/api/cycles/:dbKey", async (req, res) => {
  try {
    const { dbKey } = req.params;
    const prizeParam = req.query.prize;
    const prize = prizeParam ? Number(prizeParam) : null;

    const Model = models[dbKey];
    if (!Model) {
      return res.status(400).json({ error: "Invalid dbKey" });
    }

    // Fetch docs
    const docs = await Model.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    if (!docs.length) {
      return res.json({
        totalCompletedCycles: 0,
        currentCycle: {
          cycle: 1,
          startDate: "",
          lastDate: "",
          uniqueCount: 0,
          remainingCount: 10000,
          remainingNumbers: Array.from({ length: 10000 }, (_, i) =>
            String(i).padStart(4, "0"),
          ),
        },
        cycles: [],
      });
    }

    let analysis;

    // ✅ REUSE EXISTING BUILDERS (No duplication)
    if (prize) {
      // Assumes buildPrizeCycleAnalysis is defined in your file (Part 3)
      analysis = buildPrizeCycleAnalysis(docs, prize);
    } else {
      // Assumes buildGlobalUniqueCycles is defined in your file (Part 3)
      analysis = buildGlobalUniqueCycles(docs);
    }

    // Map to frontend format
    const allCycles = analysis.cycles || [];
    const completedCycles = allCycles.filter((c) => c.status === "COMPLETED");
    const currentCycleRaw =
      allCycles.length > 0 ? allCycles[allCycles.length - 1] : null;

    const currentCycle = currentCycleRaw
      ? {
          cycle: currentCycleRaw.cycleNumber,
          startDate: currentCycleRaw.startDate || "",
          lastDate: currentCycleRaw.endDate || "", // Frontend expects lastDate
          uniqueCount: currentCycleRaw.uniqueNumbersSeen || 0,
          remainingCount: currentCycleRaw.remainingCount || 0,
          remainingNumbers: currentCycleRaw.remainingNumbers || [],
        }
      : {
          cycle: 1,
          startDate: "",
          lastDate: "",
          uniqueCount: 0,
          remainingCount: 10000,
          remainingNumbers: Array.from({ length: 10000 }, (_, i) =>
            String(i).padStart(4, "0"),
          ),
        };

    res.json({
      totalCompletedCycles: completedCycles.length,
      currentCycle,
      cycles: completedCycles.map((c) => ({
        cycle: c.cycleNumber,
        startDate: c.startDate || "",
        endDate: c.endDate || "",
        uniqueCount: c.uniqueNumbersSeen || 0,
      })),
    });
  } catch (err) {
    console.error("❌ /api/cycles error:", err);
    res.status(500).json({ error: err.message });
  }
});

//reverse compare
// app.use("/api/reverse-cycles", reverseCyclesRouter);

// Verify they are functions/objects before using them
console.log("Forward router type:", typeof forwardCyclesRouter);
console.log("Reverse router type:", typeof reverseCyclesRouter);

app.use("/api/forward-cycles", forwardCyclesRouter);
app.use("/api/reverse-cycles", reverseCyclesRouter);
