const fs = require("fs");
const path = require("path");
const PdfParse = require("pdf-parse");

const folders = ["files"];

function extractPrizeAmounts(text) {
  const amounts = new Set();

  /*
   * Finds amounts such as:
   *
   * 5000/-
   * 5,000/-
   * Rs. 5000/-
   * Rs 3000/-
   * ₹1000/-
   *
   * We only care about numeric prize values <= 5000.
   */
  const regex =
    /(?:₹|Rs\.?|Prize\s*[:\-]?)?\s*(\d{1,2}(?:,\d{3})*|\d{2,5})\s*\/-/gi;

  let match;

  while ((match = regex.exec(text))) {
    const amount = Number(match[1].replace(/,/g, ""));

    if (Number.isFinite(amount) && amount > 0 && amount <= 5000) {
      amounts.add(amount);
    }
  }

  return [...amounts].sort((a, b) => b - a);
}

function getType(fileName, text) {
  const combined = `${fileName} ${text}`;

  if (/\bBR\b/i.test(combined)) return "BR";
  if (/\bBM\b/i.test(combined)) return "BM";

  return "OTHER";
}

(async () => {
  const summary = {
    BM: new Set(),
    BR: new Set(),
    OTHER: new Set(),
  };

  for (const folder of folders) {
    const folderPath = path.join(process.cwd(), folder);

    if (!fs.existsSync(folderPath)) {
      console.log(`\n⚠️ Folder not found: ${folderPath}`);
      continue;
    }

    const files = fs
      .readdirSync(folderPath)
      .filter((f) => f.toLowerCase().endsWith(".pdf"));

    console.log(`\n========================================`);
    console.log(`FOLDER: ${folder}`);
    console.log(`PDF COUNT: ${files.length}`);
    console.log(`========================================`);

    for (const fileName of files) {
      try {
        const buffer = fs.readFileSync(path.join(folderPath, fileName));
        const pdf = await PdfParse(buffer);
        const text = pdf.text || "";

        const type = getType(fileName, text);
        const prizes = extractPrizeAmounts(text);

        prizes.forEach((p) => summary[type].add(p));

        console.log(
          `${type.padEnd(6)} | ${fileName} | ${prizes.join(", ") || "NO PRIZES FOUND"}`,
        );
      } catch (err) {
        console.log(`ERROR | ${fileName} | ${err.message}`);
      }
    }
  }

  console.log("\n\n========================================");
  console.log("FINAL PRIZE CATEGORY SUMMARY");
  console.log("========================================");

  for (const type of ["BM", "BR", "OTHER"]) {
    console.log(
      `${type}: ${[...summary[type]].sort((a, b) => b - a).join(", ") || "none"}`,
    );
  }
})();
