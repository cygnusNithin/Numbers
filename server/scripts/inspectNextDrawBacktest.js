const fs = require("fs");
const path = require("path");

const filePath = path.join(
  __dirname,
  "..",
  "analysis-results",
  "next-draw-strategy-backtest-v2",
  "next_draw_v2_per_target.csv",
);

function parseCSVLine(line) {
  const values = [];
  let value = "";
  let quoted = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        value += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      values.push(value);
      value = "";
    } else {
      value += char;
    }
  }

  values.push(value);
  return values;
}

if (!fs.existsSync(filePath)) {
  console.error("CSV file not found:");
  console.error(filePath);
  process.exit(1);
}

const content = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
const lines = content.split(/\r?\n/).filter((line) => line.trim() !== "");

if (lines.length < 2) {
  console.error("CSV is empty or contains no data rows.");
  process.exit(1);
}

const headers = parseCSVLine(lines[0]);
const firstRow = parseCSVLine(lines[1]);

console.log("\n=== CSV FILE ===");
console.log(filePath);

console.log("\n=== ROW COUNTS ===");
console.log("Data rows:", lines.length - 1);
console.log("Columns:", headers.length);

console.log("\n=== COLUMN NAMES ===");
headers.forEach((header, index) => {
  console.log(`${index + 1}. ${header}`);
});

console.log("\n=== FIRST DATA ROW ===");
console.table(
  headers.map((header, index) => ({
    column: header,
    exampleValue: firstRow[index] ?? "",
  })),
);

console.log("\n=== DATE / STRATEGY / HIT-RELATED COLUMNS ===");
console.log(
  headers.filter((header) =>
    /date|target|strategy|top.?10|top.?25|top.?50|top.?100|hit|index/i.test(
      header,
    ),
  ),
);

console.log("\nInspection complete. No files or database records changed.");
