
const fs = require("fs");
const path = require("path");
const pdfParseModule = require("pdf-parse");

const FILES_DIR = path.join(__dirname, "..", "files");
const REPORT_DIR = path.join(
  __dirname,
  "..",
  "reports",
  "absolute-v2-source-text"
);

const TARGET_SERIALS = ["KN-543", "KR-676", "NR-402"];

function getPdfFiles(dir) {
  if (!fs.existsSync(dir)) {
    throw new Error(`PDF folder does not exist: ${dir}`);
  }

  const results = [];

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      results.push(...getPdfFiles(fullPath));
    } else if (entry.isFile() && /\.pdf$/i.test(entry.name)) {
      results.push(fullPath);
    }
  }

  return results;
}

// Supports both older and newer pdf-parse APIs.
async function extractPdfText(buffer) {
  const pdfParse =
    typeof pdfParseModule === "function"
      ? pdfParseModule
      : pdfParseModule.default;

  if (typeof pdfParse === "function") {
    const result = await pdfParse(buffer);
    return result.text || "";
  }

  if (typeof pdfParseModule.PDFParse === "function") {
    const parser = new pdfParseModule.PDFParse({ data: buffer });

    try {
      const result = await parser.getText();
      return result.text || "";
    } finally {
      if (typeof parser.destroy === "function") {
        await parser.destroy();
      }
    }
  }

  throw new Error(
    "Unsupported pdf-parse API. Run: npm ls pdf-parse"
  );
}

function safeFileName(value) {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function findContexts(text, pattern, radius = 350) {
  const contexts = [];
  const regex = new RegExp(pattern.source, pattern.flags.includes("g")
    ? pattern.flags
    : pattern.flags + "g");

  let match;

  while ((match = regex.exec(text)) !== null) {
    const start = Math.max(0, match.index - radius);
    const end = Math.min(
      text.length,
      match.index + match[0].length + radius
    );

    contexts.push(
      `--- Match: ${match[0]} at character ${match.index} ---\n` +
      text.slice(start, end)
    );

    // Prevent an infinite loop for zero-length matches.
    if (match[0].length === 0) regex.lastIndex++;
  }

  return contexts;
}

async function main() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });

  const pdfFiles = getPdfFiles(FILES_DIR);

  console.log(`PDF folder: ${FILES_DIR}`);
  console.log(`PDF files found: ${pdfFiles.length}`);
  console.log(`Searching for: ${TARGET_SERIALS.join(", ")}`);
  console.log("");

  const summary = [];
  let matchedFiles = 0;
  let failedFiles = 0;

  for (let i = 0; i < pdfFiles.length; i++) {
    const filePath = pdfFiles[i];
    const fileName = path.basename(filePath);

    try {
      const buffer = fs.readFileSync(filePath);
      const text = await extractPdfText(buffer);

      const upperText = text.toUpperCase();
      const upperName = fileName.toUpperCase();

      const matchedSerials = TARGET_SERIALS.filter(
        (serial) =>
          upperName.includes(serial) ||
          upperText.includes(serial)
      );

      if (matchedSerials.length > 0) {
        matchedFiles++;

        const relativePath = path.relative(FILES_DIR, filePath);
        const reportName = safeFileName(
          `${matchedSerials.join("_")}_${path.parse(fileName).name}`
        );

        // Preserve the complete extracted text for inspection.
        const fullTextPath = path.join(
          REPORT_DIR,
          `${reportName}.txt`
        );

        fs.writeFileSync(
          fullTextPath,
          [
            `Source PDF: ${filePath}`,
            `Matched serials: ${matchedSerials.join(", ")}`,
            "=".repeat(80),
            text,
          ].join("\n"),
          "utf8"
        );

        // Capture context around the serial, dates, and prize headings.
        const patterns = [
          {
            label: "SERIAL",
            regex: /\b(?:KN-543|KR-676|NR-402)\b/gi,
          },
          {
            label: "DATES",
            regex:
              /\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b/g,
          },
          {
            label: "PRIZE HEADINGS",
            regex:
              /\b(?:1st|2nd|3rd|4th|5th|sixth|seventh|eighth|ninth|tenth|consolation)\s*prize\b|\bprize\s*[-:]\s*Rs\.?/gi,
          },
          {
            label: "YEAR 2024",
            regex: /\b2024\b/g,
          },
          {
            label: "NUMBER SECTION MARKER",
            regex:
              /FOR THE TICKETS ENDING WITH THE FOLLOWING NUMBERS/gi,
          },
        ];

        const excerptParts = [
          `SOURCE: ${filePath}`,
          `RELATIVE PATH: ${relativePath}`,
          `MATCHED SERIALS: ${matchedSerials.join(", ")}`,
          `FULL TEXT: ${fullTextPath}`,
          "",
        ];

        for (const item of patterns) {
          const contexts = findContexts(text, item.regex);

          excerptParts.push(
            `\n========== ${item.label} (${contexts.length}) ==========`
          );

          excerptParts.push(
            contexts.length
              ? contexts.join("\n\n")
              : "No matches found."
          );
        }

        const excerptPath = path.join(
          REPORT_DIR,
          `${reportName}_context.txt`
        );

        fs.writeFileSync(
          excerptPath,
          excerptParts.join("\n"),
          "utf8"
        );

        summary.push({
          serials: matchedSerials.join(", "),
          file: relativePath,
          extractedCharacters: text.length,
          fullText: fullTextPath,
          context: excerptPath,
        });

        console.log(`MATCH: ${relativePath}`);
        console.log(`  Serial(s): ${matchedSerials.join(", ")}`);
        console.log(`  Extracted characters: ${text.length}`);
        console.log(`  Full text: ${fullTextPath}`);
        console.log(`  Context: ${excerptPath}`);
      }
    } catch (error) {
      failedFiles++;

      console.error(`ERROR: ${filePath}`);
      console.error(`  ${error.message}`);
    }

    if ((i + 1) % 100 === 0 || i + 1 === pdfFiles.length) {
      console.log(`Progress: ${i + 1}/${pdfFiles.length}`);
    }
  }

  const summaryPath = path.join(REPORT_DIR, "summary.json");

  fs.writeFileSync(
    summaryPath,
    JSON.stringify(
      {
        filesFolder: FILES_DIR,
        totalPdfFiles: pdfFiles.length,
        matchedFiles,
        failedFiles,
        targets: TARGET_SERIALS,
        matches: summary,
      },
      null,
      2
    ),
    "utf8"
  );

  console.log("\n========== COMPLETE ==========");
  console.log(`PDF files scanned: ${pdfFiles.length}`);
  console.log(`Matching PDFs: ${matchedFiles}`);
  console.log(`PDF errors: ${failedFiles}`);
  console.log(`Report folder: ${REPORT_DIR}`);
  console.log(`Summary: ${summaryPath}`);
}

main().catch((error) => {
  console.error("Inspection failed:", error);
  process.exitCode = 1;
});
