const fs = require("fs");
const path = require("path");

/* ============================================================
   PATHS
============================================================ */

const SERVER_DIR = path.join(__dirname, "..");

const CANONICAL_CSV = path.join(
  SERVER_DIR,
  "analysis-results",
  "absolute_data_canonical.csv",
);

const EXISTING_CSV = path.join(SERVER_DIR, "absolute_data_number_patterns.csv");

const OUTPUT_DIR = path.join(SERVER_DIR, "analysis-results");

const OUTPUT_JSON = path.join(
  OUTPUT_DIR,
  "canonical_vs_existing_comparison.json",
);

/* ============================================================
   CSV PARSER
============================================================ */

function parseCsvLine(line) {
  const values = [];

  let current = "";
  let insideQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      if (insideQuotes && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        insideQuotes = !insideQuotes;
      }

      continue;
    }

    if (char === "," && !insideQuotes) {
      values.push(current);
      current = "";
      continue;
    }

    current += char;
  }

  values.push(current);

  return values;
}

function parseCsv(text) {
  const lines = text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "");

  if (lines.length === 0) {
    return [];
  }

  const headers = parseCsvLine(lines[0]);

  const rows = [];

  for (let i = 1; i < lines.length; i++) {
    const values = parseCsvLine(lines[i]);

    const row = {};

    for (let j = 0; j < headers.length; j++) {
      row[headers[j]] = values[j] !== undefined ? values[j] : "";
    }

    rows.push(row);
  }

  return rows;
}

/* ============================================================
   JSON HELPERS
============================================================ */

function parseJson(value, fallback = {}) {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }

  if (typeof value === "object") {
    return value;
  }

  try {
    return JSON.parse(value);
  } catch (error) {
    return fallback;
  }
}

/* ============================================================
   NORMALIZATION
============================================================ */

/*
 * Month counts have two valid representations:
 *
 * Canonical:
 *
 * {
 *   "1": 5,
 *   "2": 3,
 *   "3": 7
 * }
 *
 * Existing:
 *
 * {
 *   "1": 5,
 *   "2": 3,
 *   "3": 7,
 *   "4": 0
 * }
 *
 * These are semantically identical.
 *
 * Remove zero-valued months before comparison.
 */

function normalizeMonthCounts(value) {
  const parsed = parseJson(value, {});

  const normalized = {};

  for (let month = 1; month <= 12; month++) {
    const key = String(month);

    const count = Number(parsed[key] || 0);

    if (count > 0) {
      normalized[key] = count;
    }
  }

  return normalized;
}

function normalizeJsonObject(value) {
  return parseJson(value, {});
}

function normalizeNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const number = Number(value);

  return Number.isFinite(number) ? number : null;
}

/* ============================================================
   DEEP EQUALITY
============================================================ */

function stableObject(value) {
  if (value === null || typeof value !== "object") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map(stableObject);
  }

  const result = {};

  for (const key of Object.keys(value).sort()) {
    result[key] = stableObject(value[key]);
  }

  return result;
}

function objectsEqual(a, b) {
  return JSON.stringify(stableObject(a)) === JSON.stringify(stableObject(b));
}

/* ============================================================
   FIELD COMPARISON
============================================================ */

const CORE_FIELDS = [
  "number",
  "total_hits",
  "last_seen_date",
  "days_since_last_hit",
  "avg_gap_days",
  "min_gap_days",
  "max_gap_days",
  "d1",
  "d2",
  "d3",
  "d4",
  "digit_sum",
  "even_digit_count",
  "dates",
  "prize_breakdown",
  "weekday_counts",
  "month_counts",
];

function compareField(canonical, existing, field) {
  switch (field) {
    case "number":
    case "last_seen_date":
      return String(canonical[field] ?? "") === String(existing[field] ?? "");

    case "total_hits":
    case "days_since_last_hit":
    case "avg_gap_days":
    case "min_gap_days":
    case "max_gap_days":
    case "d1":
    case "d2":
    case "d3":
    case "d4":
    case "digit_sum":
    case "even_digit_count":
      return (
        normalizeNumber(canonical[field]) === normalizeNumber(existing[field])
      );

    case "dates": {
      const a = parseJson(canonical[field], []);

      const b = parseJson(existing[field], []);

      return objectsEqual(a, b);
    }

    case "prize_breakdown":
    case "weekday_counts": {
      const a = normalizeJsonObject(canonical[field]);

      const b = normalizeJsonObject(existing[field]);

      return objectsEqual(a, b);
    }

    case "month_counts": {
      const a = normalizeMonthCounts(canonical[field]);

      const b = normalizeMonthCounts(existing[field]);

      return objectsEqual(a, b);
    }

    default:
      return String(canonical[field] ?? "") === String(existing[field] ?? "");
  }
}

/* ============================================================
   DATE-DERIVED MONTH DIAGNOSTIC
============================================================ */

function deriveMonthCountsFromDates(value) {
  const dates = parseJson(value, []);

  const result = {};

  for (const dateString of dates) {
    const match = String(dateString).match(/^\d{2}\/(\d{2})\/\d{4}$/);

    if (!match) {
      continue;
    }

    const month = String(Number(match[1]));

    result[month] = (result[month] || 0) + 1;
  }

  return result;
}

/* ============================================================
   MAIN
============================================================ */

function main() {
  console.log("");
  console.log("==============================================");
  console.log("CANONICAL vs EXISTING DATASET");
  console.log("SEMANTIC COMPARISON");
  console.log("==============================================");
  console.log("");

  if (!fs.existsSync(CANONICAL_CSV)) {
    throw new Error(`Canonical CSV not found:\n${CANONICAL_CSV}`);
  }

  if (!fs.existsSync(EXISTING_CSV)) {
    throw new Error(`Existing CSV not found:\n${EXISTING_CSV}`);
  }

  const canonicalRows = parseCsv(fs.readFileSync(CANONICAL_CSV, "utf8"));

  const existingRows = parseCsv(fs.readFileSync(EXISTING_CSV, "utf8"));

  console.log(`Canonical CSV rows: ${canonicalRows.length}`);

  console.log(`Existing CSV rows : ${existingRows.length}`);

  console.log("");

  /*
   * Index existing rows by number.
   */

  const existingByNumber = new Map();

  for (const row of existingRows) {
    existingByNumber.set(String(row.number).padStart(4, "0"), row);
  }

  const canonicalByNumber = new Map();

  for (const row of canonicalRows) {
    canonicalByNumber.set(String(row.number).padStart(4, "0"), row);
  }

  /* ==========================================================
     CORE DATA
  ========================================================== */

  let numbersCompared = 0;
  let coreMatched = 0;
  let coreDifferent = 0;

  const coreDifferences = [];

  for (const canonical of canonicalRows) {
    const number = String(canonical.number).padStart(4, "0");

    const existing = existingByNumber.get(number);

    if (!existing) {
      coreDifferent++;

      coreDifferences.push({
        number,
        reason: "missing_from_existing",
      });

      continue;
    }

    numbersCompared++;

    let matched = true;

    for (const field of CORE_FIELDS) {
      if (!compareField(canonical, existing, field)) {
        matched = false;
        break;
      }
    }

    if (matched) {
      coreMatched++;
    } else {
      coreDifferent++;

      coreDifferences.push({
        number,
        reason: "core_field_difference",
      });
    }
  }

  console.log("CORE DATA");

  console.log("----------------------------------------------");

  console.log(`Numbers compared : ${numbersCompared}`);

  console.log(`Core matched     : ${coreMatched}`);

  console.log(`Core different   : ${coreDifferent}`);

  console.log("");

  /* ==========================================================
     FIELD COMPARISON
  ========================================================== */

  console.log("FIELD COMPARISON");

  console.log("----------------------------------------------");

  const fieldResults = {};

  for (const field of CORE_FIELDS) {
    let matched = 0;
    let different = 0;

    for (const canonical of canonicalRows) {
      const number = String(canonical.number).padStart(4, "0");

      const existing = existingByNumber.get(number);

      if (!existing) {
        different++;
        continue;
      }

      if (compareField(canonical, existing, field)) {
        matched++;
      } else {
        different++;
      }
    }

    fieldResults[field] = {
      matched,
      different,
    };

    console.log(
      `${field.padEnd(20)} matched=${String(matched).padStart(
        5,
      )} different=${String(different).padStart(5)}`,
    );
  }

  console.log("");

  /* ==========================================================
     SCHEMA DIFFERENCES
  ========================================================== */

  const canonicalFields = canonicalRows.length
    ? Object.keys(canonicalRows[0])
    : [];

  const existingFields = existingRows.length
    ? Object.keys(existingRows[0])
    : [];

  const canonicalOnly = canonicalFields.filter(
    (field) => !existingFields.includes(field),
  );

  const existingOnly = existingFields.filter(
    (field) => !canonicalFields.includes(field),
  );

  console.log("SCHEMA DIFFERENCES");

  console.log("----------------------------------------------");

  console.log(
    `Canonical-only: ${
      canonicalOnly.length ? canonicalOnly.join(", ") : "none"
    }`,
  );

  console.log(
    `Existing-only : ${existingOnly.length ? existingOnly.join(", ") : "none"}`,
  );

  console.log("");

  /* ==========================================================
     MONTH DIAGNOSTIC
  ========================================================== */

  let monthMismatches = 0;
  let canonicalMatchesDates = 0;
  let existingMatchesDates = 0;
  let bothMatchDates = 0;
  let neitherMatchesDates = 0;

  const monthDifferences = [];

  for (const canonical of canonicalRows) {
    const number = String(canonical.number).padStart(4, "0");

    const existing = existingByNumber.get(number);

    if (!existing) {
      continue;
    }

    const derived = deriveMonthCountsFromDates(canonical.dates);

    const canonicalMonth = normalizeMonthCounts(canonical.month_counts);

    const existingMonth = normalizeMonthCounts(existing.month_counts);

    const canonicalMatches = objectsEqual(canonicalMonth, derived);

    const existingMatches = objectsEqual(existingMonth, derived);

    if (canonicalMatches) {
      canonicalMatchesDates++;
    }

    if (existingMatches) {
      existingMatchesDates++;
    }

    if (canonicalMatches && existingMatches) {
      bothMatchDates++;
    }

    if (!canonicalMatches && !existingMatches) {
      neitherMatchesDates++;
    }

    if (!objectsEqual(canonicalMonth, existingMonth)) {
      monthMismatches++;

      monthDifferences.push({
        number,
        dates: JSON.parse(canonical.dates || "[]"),
        derived,
        canonical: canonicalMonth,
        existing: existingMonth,
        canonicalMatchesDates,
        existingMatchesDates,
      });
    }
  }

  console.log("MONTH DIAGNOSTIC");

  console.log("----------------------------------------------");

  console.log(`Month mismatches: ${monthMismatches}`);

  console.log(`Canonical matches dates: ${canonicalMatchesDates}`);

  console.log(`Existing matches dates : ${existingMatchesDates}`);

  console.log(`Both match dates       : ${bothMatchDates}`);

  console.log(`Neither matches dates  : ${neitherMatchesDates}`);

  console.log("");

  if (monthDifferences.length > 0) {
    console.log("FIRST 10 MONTH DIFFERENCES");

    console.log("----------------------------------------------");

    for (const difference of monthDifferences.slice(0, 10)) {
      console.log("");

      console.log(`Number: ${difference.number}`);

      console.log(`Dates: ${difference.dates.length}`);

      console.log(`Derived : ${JSON.stringify(difference.derived)}`);

      console.log(`Canonical: ${JSON.stringify(difference.canonical)}`);

      console.log(`Existing : ${JSON.stringify(difference.existing)}`);

      console.log(
        `Canonical matches dates: ${objectsEqual(
          difference.canonical,
          difference.derived,
        )}`,
      );

      console.log(
        `Existing matches dates : ${objectsEqual(
          difference.existing,
          difference.derived,
        )}`,
      );
    }
  }

  console.log("");

  /* ==========================================================
     MISSING NUMBERS
  ========================================================== */

  const missingFromExisting = [];

  for (const canonical of canonicalRows) {
    const number = String(canonical.number).padStart(4, "0");

    if (!existingByNumber.has(number)) {
      missingFromExisting.push(number);
    }
  }

  const missingFromCanonical = [];

  for (const existing of existingRows) {
    const number = String(existing.number).padStart(4, "0");

    if (!canonicalByNumber.has(number)) {
      missingFromCanonical.push(number);
    }
  }

  /* ==========================================================
     FINAL VERDICT
  ========================================================== */

  /*
   * The raw month representation is intentionally ignored
   * here because {"4":0} and an absent "4" are equivalent.
   *
   * CORE DATA is already using semantic month comparison.
   */

  const passed =
    coreDifferent === 0 &&
    missingFromExisting.length === 0 &&
    missingFromCanonical.length === 0;

  console.log("==============================================");

  if (passed) {
    console.log("✅ SEMANTIC COMPARISON PASSED");

    console.log("Canonical and existing datasets contain");

    console.log("the same historical data.");
  } else {
    console.log("❌ REAL CORE DATA DIFFERENCES FOUND");

    if (missingFromExisting.length > 0) {
      console.log(`Missing from existing: ${missingFromExisting.length}`);
    }

    if (missingFromCanonical.length > 0) {
      console.log(`Missing from canonical: ${missingFromCanonical.length}`);
    }

    if (coreDifferent > 0) {
      console.log(`Core differences: ${coreDifferent}`);
    }
  }

  console.log("==============================================");

  /* ==========================================================
     REPORT
  ========================================================== */

  fs.mkdirSync(OUTPUT_DIR, {
    recursive: true,
  });

  const report = {
    generatedAt: new Date().toISOString(),

    files: {
      canonical: CANONICAL_CSV,
      existing: EXISTING_CSV,
    },

    rowCounts: {
      canonical: canonicalRows.length,
      existing: existingRows.length,
    },

    core: {
      numbersCompared,
      matched: coreMatched,
      different: coreDifferent,
    },

    fields: fieldResults,

    schema: {
      canonicalOnly,
      existingOnly,
    },

    monthDiagnostic: {
      mismatches: monthMismatches,
      canonicalMatchesDates,
      existingMatchesDates,
      bothMatchDates,
      neitherMatchesDates,
    },

    missing: {
      fromExisting: missingFromExisting,
      fromCanonical: missingFromCanonical,
    },

    coreDifferences,

    firstMonthDifferences: monthDifferences.slice(0, 100),

    passed,
  };

  fs.writeFileSync(OUTPUT_JSON, JSON.stringify(report, null, 2), "utf8");

  console.log("");

  console.log(`Report: ${OUTPUT_JSON}`);

  console.log("");
}

/* ============================================================
   RUN
============================================================ */

try {
  main();
} catch (error) {
  console.error("");
  console.error("❌ COMPARISON FAILED");
  console.error("");
  console.error(error);
  console.error("");

  process.exit(1);
}
