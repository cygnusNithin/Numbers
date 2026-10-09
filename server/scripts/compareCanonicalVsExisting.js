const fs = require("fs");
const path = require("path");

const SERVER_ROOT = path.resolve(__dirname, "..");

const CANONICAL_CSV = path.join(
  SERVER_ROOT,
  "analysis-results",
  "absolute_data_canonical.csv",
);

const EXISTING_CSV = path.join(
  SERVER_ROOT,
  "absolute_data_number_patterns.csv",
);

const REPORT_PATH = path.join(
  SERVER_ROOT,
  "analysis-results",
  "canonical_vs_existing_comparison.json",
);

const MONTH_NAME_TO_NUMBER = {
  January: "1",
  February: "2",
  March: "3",
  April: "4",
  May: "5",
  June: "6",
  July: "7",
  August: "8",
  September: "9",
  October: "10",
  November: "11",
  December: "12",
};

const CORE_FIELDS = [
  "number",
  "total_hits",
  "last_seen_date",
  "days_since_last_hit",
  "avg_gap_days",
  "min_gap_days",
  "max_gap_days",
  "dates",
  "prize_breakdown",
  "weekday_counts",
  "month_counts",
  "d1",
  "d2",
  "d3",
  "d4",
  "digit_sum",
  "even_digit_count",
];

const NUMERIC_FIELDS = new Set([
  "total_hits",
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
]);

const JSON_FIELDS = new Set([
  "prize_breakdown",
  "weekday_counts",
  "month_counts",
]);

const DATE_LIST_FIELDS = new Set(["dates"]);

const NUMERIC_TOLERANCE = 1e-9;

// ------------------------------------------------------------
// CSV parser
// ------------------------------------------------------------

function parseCsv(text) {
  const rows = [];

  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (char === '"' && next === '"') {
        field += '"';
        i++;
        continue;
      }

      if (char === '"') {
        inQuotes = false;
        continue;
      }

      field += char;
      continue;
    }

    if (char === '"') {
      inQuotes = true;
      continue;
    }

    if (char === ",") {
      row.push(field);
      field = "";
      continue;
    }

    if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      continue;
    }

    if (char === "\r") {
      continue;
    }

    field += char;
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  if (rows.length === 0) {
    return [];
  }

  const headers = rows[0];

  return rows
    .slice(1)
    .filter((row) => row.some((value) => value !== ""))
    .map((row) => {
      const object = {};

      for (let i = 0; i < headers.length; i++) {
        object[headers[i]] = row[i] ?? "";
      }

      return object;
    });
}

// ------------------------------------------------------------
// Generic helpers
// ------------------------------------------------------------

function safeJsonParse(value, fallback = {}) {
  if (value === null || value === undefined) {
    return fallback;
  }

  if (typeof value === "object") {
    return value;
  }

  const text = String(value).trim();

  if (!text) {
    return fallback;
  }

  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function normalizeNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const number = Number(value);

  return Number.isFinite(number) ? number : null;
}

function numbersEqual(a, b) {
  const x = normalizeNumber(a);
  const y = normalizeNumber(b);

  if (x === null || y === null) {
    return x === y;
  }

  return Math.abs(x - y) <= NUMERIC_TOLERANCE;
}

// ------------------------------------------------------------
// Dates
// ------------------------------------------------------------

function normalizeDateString(value) {
  return String(value || "").trim();
}

function normalizeDates(value) {
  if (Array.isArray(value)) {
    return [...new Set(value.map(normalizeDateString).filter(Boolean))];
  }

  const text = String(value || "");

  if (!text.trim()) {
    return [];
  }

  return [...new Set(text.split("|").map(normalizeDateString).filter(Boolean))];
}

// ------------------------------------------------------------
// Month counts
//
// Canonical:
//   {"1":6,"2":1,"3":6}
//
// Existing:
//   {"April":5,"August":10,...}
//
// Normalize both to:
//   {"1":6,"2":1,...}
// ------------------------------------------------------------

function normalizeMonthCounts(value) {
  const parsed = safeJsonParse(value, {});

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {};
  }

  const result = {};

  for (const [rawKey, rawValue] of Object.entries(parsed)) {
    let monthNumber = null;

    if (/^(1[0-2]|[1-9])$/.test(String(rawKey).trim())) {
      monthNumber = String(Number(rawKey));
    } else if (MONTH_NAME_TO_NUMBER[rawKey]) {
      monthNumber = MONTH_NAME_TO_NUMBER[rawKey];
    } else {
      const normalizedName = String(rawKey).trim().replace(/\s+/g, " ");

      if (MONTH_NAME_TO_NUMBER[normalizedName]) {
        monthNumber = MONTH_NAME_TO_NUMBER[normalizedName];
      }
    }

    if (!monthNumber) {
      continue;
    }

    const count = Number(rawValue);

    if (!Number.isFinite(count)) {
      continue;
    }

    result[monthNumber] = count;
  }

  return Object.fromEntries(
    Object.entries(result).sort(([a], [b]) => Number(a) - Number(b)),
  );
}

// ------------------------------------------------------------
// Prize / weekday objects
// ------------------------------------------------------------

function normalizeObject(value) {
  const parsed = safeJsonParse(value, {});

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {};
  }

  const result = {};

  for (const [key, rawValue] of Object.entries(parsed)) {
    const numericValue = Number(rawValue);

    result[String(key)] = Number.isFinite(numericValue)
      ? numericValue
      : rawValue;
  }

  return Object.fromEntries(
    Object.entries(result).sort(([a], [b]) => a.localeCompare(b)),
  );
}

// ------------------------------------------------------------
// Semantic normalization
// ------------------------------------------------------------

function normalizeField(field, value) {
  if (field === "dates") {
    return normalizeDates(value);
  }

  if (field === "month_counts") {
    return normalizeMonthCounts(value);
  }

  if (field === "prize_breakdown" || field === "weekday_counts") {
    return normalizeObject(value);
  }

  if (NUMERIC_FIELDS.has(field)) {
    return normalizeNumber(value);
  }

  return String(value ?? "").trim();
}

function semanticEqual(field, canonicalValue, existingValue) {
  const a = normalizeField(field, canonicalValue);
  const b = normalizeField(field, existingValue);

  if (field === "avg_gap_days") {
    return numbersEqual(a, b);
  }

  if (NUMERIC_FIELDS.has(field)) {
    return numbersEqual(a, b);
  }

  return JSON.stringify(a) === JSON.stringify(b);
}

// ------------------------------------------------------------
// Main
// ------------------------------------------------------------

console.log("");
console.log("==============================================");
console.log("CANONICAL vs EXISTING DATASET");
console.log("SEMANTIC COMPARISON");
console.log("==============================================");
console.log("");

if (!fs.existsSync(CANONICAL_CSV)) {
  throw new Error(`Canonical CSV not found: ${CANONICAL_CSV}`);
}

if (!fs.existsSync(EXISTING_CSV)) {
  throw new Error(`Existing CSV not found: ${EXISTING_CSV}`);
}

const canonicalRows = parseCsv(fs.readFileSync(CANONICAL_CSV, "utf8"));

const existingRows = parseCsv(fs.readFileSync(EXISTING_CSV, "utf8"));

console.log(`Canonical CSV rows: ${canonicalRows.length}`);
console.log(`Existing CSV rows : ${existingRows.length}`);
console.log("");

const canonicalByNumber = new Map();
const existingByNumber = new Map();

for (const row of canonicalRows) {
  canonicalByNumber.set(String(row.number).padStart(4, "0"), row);
}

for (const row of existingRows) {
  existingByNumber.set(String(row.number).padStart(4, "0"), row);
}

const allNumbers = [
  ...new Set([...canonicalByNumber.keys(), ...existingByNumber.keys()]),
].sort();

const fieldStats = {};

for (const field of CORE_FIELDS) {
  fieldStats[field] = {
    matched: 0,
    different: 0,
  };
}

const coreDifferences = [];
const dateDifferences = [];
const monthDifferences = [];

for (const number of allNumbers) {
  const canonical = canonicalByNumber.get(number);
  const existing = existingByNumber.get(number);

  if (!canonical || !existing) {
    coreDifferences.push({
      number,
      reason: !canonical ? "missing_from_canonical" : "missing_from_existing",
    });

    continue;
  }

  for (const field of CORE_FIELDS) {
    const same = semanticEqual(field, canonical[field], existing[field]);

    if (same) {
      fieldStats[field].matched++;
    } else {
      fieldStats[field].different++;

      if (field === "dates") {
        dateDifferences.push({
          number,
          canonical: normalizeDates(canonical[field]),
          existing: normalizeDates(existing[field]),
        });
      }

      if (field === "month_counts") {
        monthDifferences.push({
          number,
          derived: normalizeMonthCounts(existing.month_counts),
          canonical: normalizeMonthCounts(canonical.month_counts),
          existingRaw: existing.month_counts,
        });
      }
    }
  }
}

// ------------------------------------------------------------
// Core match
// ------------------------------------------------------------

const coreMatchedNumbers = allNumbers.filter((number) => {
  const canonical = canonicalByNumber.get(number);
  const existing = existingByNumber.get(number);

  if (!canonical || !existing) {
    return false;
  }

  return CORE_FIELDS.every((field) =>
    semanticEqual(field, canonical[field], existing[field]),
  );
});

const coreDifferentCount = allNumbers.length - coreMatchedNumbers.length;

console.log("CORE DATA");
console.log("----------------------------------------------");
console.log(`Numbers compared : ${allNumbers.length}`);
console.log(`Core matched     : ${coreMatchedNumbers.length}`);
console.log(`Core different   : ${coreDifferentCount}`);
console.log("");

console.log("FIELD COMPARISON");
console.log("----------------------------------------------");

for (const field of CORE_FIELDS) {
  const stats = fieldStats[field];

  console.log(
    `${field.padEnd(20)} matched=${String(stats.matched).padStart(5)} different=${String(stats.different).padStart(5)}`,
  );
}

console.log("");

const canonicalOnlyFields = Object.keys(canonicalRows[0] || {}).filter(
  (field) =>
    !Object.prototype.hasOwnProperty.call(existingRows[0] || {}, field),
);

const existingOnlyFields = Object.keys(existingRows[0] || {}).filter(
  (field) =>
    !Object.prototype.hasOwnProperty.call(canonicalRows[0] || {}, field),
);

console.log("SCHEMA DIFFERENCES");
console.log("----------------------------------------------");
console.log(
  `Canonical-only: ${
    canonicalOnlyFields.length ? canonicalOnlyFields.join(", ") : "None"
  }`,
);
console.log(
  `Existing-only : ${
    existingOnlyFields.length ? existingOnlyFields.join(", ") : "None"
  }`,
);

console.log("");

console.log("DATE DIAGNOSTIC");
console.log("----------------------------------------------");

const canonicalDateCount = canonicalRows.reduce(
  (sum, row) => sum + normalizeDates(row.dates).length,
  0,
);

const existingDateCount = existingRows.reduce(
  (sum, row) => sum + normalizeDates(row.dates).length,
  0,
);

console.log(`Date mismatches : ${dateDifferences.length}`);
console.log(`Canonical dates : ${canonicalDateCount}`);
console.log(`Existing dates  : ${existingDateCount}`);

console.log("");

console.log("MONTH DIAGNOSTIC");
console.log("----------------------------------------------");

let canonicalMonthMatchesDates = 0;
let existingMonthMatchesDates = 0;

for (const number of allNumbers) {
  const canonical = canonicalByNumber.get(number);
  const existing = existingByNumber.get(number);

  if (!canonical || !existing) {
    continue;
  }

  const dates = normalizeDates(canonical.dates);

  const derived = {};

  for (const dateString of dates) {
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(dateString);

    if (!match) {
      continue;
    }

    const month = String(Number(match[2]));

    derived[month] = (derived[month] || 0) + 1;
  }

  const canonicalMonths = normalizeMonthCounts(canonical.month_counts);

  const existingMonths = normalizeMonthCounts(existing.month_counts);

  if (JSON.stringify(derived) === JSON.stringify(canonicalMonths)) {
    canonicalMonthMatchesDates++;
  }

  if (JSON.stringify(derived) === JSON.stringify(existingMonths)) {
    existingMonthMatchesDates++;
  }
}

console.log(`Month mismatches: ${monthDifferences.length}`);
console.log(`Canonical matches dates: ${canonicalMonthMatchesDates}`);
console.log(`Existing matches dates : ${existingMonthMatchesDates}`);

if (monthDifferences.length > 0) {
  console.log("");
  console.log("FIRST 10 MONTH DIFFERENCES");
  console.log("----------------------------------------------");

  for (const diff of monthDifferences.slice(0, 10)) {
    console.log("");
    console.log(`Number: ${diff.number}`);
    console.log(`Canonical: ${JSON.stringify(diff.canonical)}`);
    console.log(`Existing : ${JSON.stringify(diff.derived)}`);
    console.log(`Existing raw: ${diff.existingRaw}`);
  }
}

console.log("");
console.log("==============================================");

if (coreDifferentCount === 0) {
  console.log("✅ CANONICAL CORE DATA MATCHES EXISTING DATA");
} else {
  console.log("❌ REAL CORE DATA DIFFERENCES FOUND");
}

console.log("");
console.log(`Core differences: ${coreDifferentCount}`);
console.log(`Date mismatches : ${dateDifferences.length}`);
console.log(`Month mismatches: ${monthDifferences.length}`);
console.log("==============================================");
console.log("");

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
    numbersCompared: allNumbers.length,
    matched: coreMatchedNumbers.length,
    different: coreDifferentCount,
  },

  fieldStats,

  schema: {
    canonicalOnly: canonicalOnlyFields,
    existingOnly: existingOnlyFields,
  },

  dateDiagnostic: {
    mismatches: dateDifferences.length,
    canonicalDates: canonicalDateCount,
    existingDates: existingDateCount,
  },

  monthDiagnostic: {
    mismatches: monthDifferences.length,
    canonicalMatchesDates: canonicalMonthMatchesDates,
    existingMatchesDates: existingMonthMatchesDates,
  },

  differences: {
    core: coreDifferences,
    dates: dateDifferences.slice(0, 100),
    months: monthDifferences.slice(0, 100),
  },
};

fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");

console.log(`Report: ${REPORT_PATH}`);
