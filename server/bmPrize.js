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
