const fs = require("fs");
const path = require("path");
const pdfParse = require("pdf-parse");

const ROOT = path.resolve(__dirname, "..");
const PDF_DIR = path.join(ROOT, "files");
const OUTPUT_DIR = path.join(ROOT, "data", "pdf-audit");

function findPdfs(dir) {
  if (!fs.existsSync(dir)) {
    throw new Error(`PDF folder not found: ${dir}`);
  }

  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) return findPdfs(fullPath);

    return entry.isFile() && /\.pdf$/i.test(entry.name) ? [fullPath] : [];
  });
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const pdfFiles = findPdfs(PDF_DIR);
  const results = [];
  const errors = [];

  console.log(`Found ${pdfFiles.length} PDF files.\n`);

  for (const file of pdfFiles) {
    try {
      const buffer = fs.readFileSync(file);
      const parsed = await pdfParse(buffer);
      const text = parsed.text || "";
      const lines = text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

      // Preserve category headings and nearby lines for manual verification.
      const relevantLines = lines.filter((line) =>
        /\b(?:1st|2nd|3rd|[4-9]th)\s*PRIZE\b|CONSOLATION|PRIZE\s*(?:NO\.?|NUMBER)/i.test(
          line,
        ),
      );

      results.push({
        file: path.relative(PDF_DIR, file),
        pages: parsed.numpages,
        extractedTextLength: text.length,
        relevantLines,
        text,
      });

      console.log(
        `[${results.length}/${pdfFiles.length}] ${path.relative(PDF_DIR, file)} — ${parsed.numpages} pages`,
      );
    } catch (error) {
      errors.push({
        file: path.relative(PDF_DIR, file),
        error: error.message,
      });

      console.error(`FAILED: ${file}\n  ${error.message}`);
    }
  }

  // Save all extracted text so we can inspect categories and number formats.
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "all_pdf_text.json"),
    JSON.stringify(
      results.map(({ text, ...metadata }) => ({ ...metadata, text })),
      null,
      2,
    ),
    "utf8",
  );

  fs.writeFileSync(
    path.join(OUTPUT_DIR, "category_lines.json"),
    JSON.stringify(
      results.map(({ file, pages, extractedTextLength, relevantLines }) => ({
        file,
        pages,
        extractedTextLength,
        relevantLines,
      })),
      null,
      2,
    ),
    "utf8",
  );

  fs.writeFileSync(
    path.join(OUTPUT_DIR, "pdf_errors.json"),
    JSON.stringify(errors, null, 2),
    "utf8",
  );

  console.log("\nAudit extraction finished.");
  console.log(`Successfully parsed: ${results.length}`);
  console.log(`Failed: ${errors.length}`);
  console.log(`Results: ${OUTPUT_DIR}`);
  console.log(
    "Review category_lines.json and pdf_errors.json before deciding categories.",
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
