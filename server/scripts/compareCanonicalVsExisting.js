const fs = require("fs");
const path = require("path");
const { parse } = require("csv-parse/sync");

const ROOT = path.join(__dirname, "..");

const CANONICAL_FILE = path.join(
  ROOT,
  "analysis-results",
  "absolute_data_canonical.csv",
);

const EXISTING_FILE = path.join(ROOT, "absolute_data_number_patterns.csv");

const REPORT_FILE = path.join(
  ROOT,
  "analysis-results",
  "canonical_vs_existing_comparison.json",
);

const MONTH_NAMES = {
  january: "1",
  february: "2",
  march: "3",
  april: "4",
  may: "5",
  june: "6",
  july: "7",
  august: "8",
  september: "9",
  october: "10",
  november: "11",
  december: "12",
};

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

const CANONICAL_ONLY_FIELDS = [
  "first_seen_date",
  "draw_count",
  "median_gap_days",
  "gap_stddev_days",
];

const EXISTING_ONLY_FIELDS = ["remaining_to_max"];

const FLOAT_TOLERANCE = 0.0001;

function readCsv(file) {
  return parse(fs.readFileSync(file, "utf8"), {
    columns: true,
    skip_empty_lines: true,
    bom: true,
    relax_column_count: true,
    trim: true,
  });
}

function numberValue(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }

  const n = Number(value);

  return Number.isFinite(n) ? n : null;
}

function numbersEqual(a, b) {
  const na = numberValue(a);
  const nb = numberValue(b);

  if (na === null && nb === null) {
    return true;
  }

  if (na === null || nb === null) {
    return false;
  }

  return Math.abs(na - nb) <= FLOAT_TOLERANCE;
}

function parseDates(value) {
  if (!value) {
    return [];
  }

  const raw = String(value).trim();

  // Old dataset:
  // 07/10/2020|04/04/2021|...
  if (raw.includes("|")) {
    return raw
      .split("|")
      .map((v) => v.trim())
      .filter(Boolean);
  }

  // Canonical dataset:
  // ["07/10/2020","04/04/2021",...]
  try {
    const parsed = JSON.parse(raw);

    if (Array.isArray(parsed)) {
      return parsed.map((v) => String(v).trim()).filter(Boolean);
    }
  } catch {
    // Ignore.
  }

  return raw ? [raw] : [];
}

function parseObject(value) {
  if (!value) {
    return {};
  }

  if (typeof value === "object") {
    return value;
  }

  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function sortObject(object) {
  return Object.keys(object)
    .sort((a, b) =>
      a.localeCompare(b, undefined, {
        numeric: true,
      }),
    )
    .reduce((result, key) => {
      result[key] = object[key];
      return result;
    }, {});
}

function normalizeGenericObject(value) {
  const parsed = parseObject(value);

  if (parsed === null) {
    return null;
  }

  const result = {};

  for (const [key, rawValue] of Object.entries(parsed)) {
    const n = numberValue(rawValue);

    result[String(key)] = n === null ? rawValue : n;
  }

  return sortObject(result);
}

function normalizePrizeBreakdown(value) {
  const parsed = parseObject(value);

  if (parsed === null) {
    return null;
  }

  const result = {};

  for (const [key, rawValue] of Object.entries(parsed)) {
    const normalizedKey = String(key).replace(/,/g, "").trim();

    const n = numberValue(rawValue);

    result[normalizedKey] = n === null ? rawValue : n;
  }

  return sortObject(result);
}

function normalizeMonthCounts(value) {
  const parsed = parseObject(value);

  if (parsed === null) {
    return null;
  }

  const result = {};

  for (const [key, rawValue] of Object.entries(parsed)) {
    const lower = String(key).trim().toLowerCase();

    let normalizedKey;

    if (MONTH_NAMES[lower]) {
      normalizedKey = MONTH_NAMES[lower];
    } else {
      const n = Number(lower);

      if (Number.isFinite(n) && n >= 1 && n <= 12) {
        normalizedKey = String(n);
      } else {
        normalizedKey = lower;
      }
    }

    const numericValue = numberValue(rawValue);

    result[normalizedKey] = numericValue === null ? rawValue : numericValue;
  }

  return sortObject(result);
}

function objectsEqual(a, b) {
  if (a === null || b === null) {
    return a === b;
  }

  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);

  if (aKeys.length !== bKeys.length) {
    return false;
  }

  for (const key of aKeys) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) {
      return false;
    }

    const av = a[key];
    const bv = b[key];

    if (typeof av === "number" || typeof bv === "number") {
      if (!numbersEqual(av, bv)) {
        return false;
      }
    } else if (String(av) !== String(bv)) {
      return false;
    }
  }

  return true;
}

function arraysEqual(a, b) {
  if (a.length !== b.length) {
    return false;
  }

  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) {
      return false;
    }
  }

  return true;
}

function compareField(field, canonical, existing) {
  switch (field) {
    case "dates":
      return arraysEqual(parseDates(canonical), parseDates(existing));

    case "prize_breakdown":
      return objectsEqual(
        normalizePrizeBreakdown(canonical),
        normalizePrizeBreakdown(existing),
      );

    case "weekday_counts":
      return objectsEqual(
        normalizeGenericObject(canonical),
        normalizeGenericObject(existing),
      );

    case "month_counts":
      return objectsEqual(
        normalizeMonthCounts(canonical),
        normalizeMonthCounts(existing),
      );

    case "number":
    case "last_seen_date":
      return String(canonical ?? "").trim() === String(existing ?? "").trim();

    default:
      return numbersEqual(canonical, existing);
  }
}

function createMap(rows) {
  const map = new Map();

  for (const row of rows) {
    const number = String(row.number).trim().padStart(4, "0");

    map.set(number, row);
  }

  return map;
}

function monthCountsFromDates(dates) {
  const result = {};

  for (const date of dates) {
    const parts = String(date).split("/");

    if (parts.length !== 3) {
      continue;
    }

    const month = String(Number(parts[1]));

    result[month] = (result[month] || 0) + 1;
  }

  return sortObject(result);
}

function getMonthDiagnostic(row) {
  const dates = parseDates(row.dates);

  const derived = monthCountsFromDates(dates);

  const canonical = normalizeMonthCounts(row.__canonicalMonthCounts);

  const existing = normalizeMonthCounts(row.__existingMonthCounts);

  return {
    dates: dates.length,
    derivedFromDates: derived,
    canonicalMonthCounts: canonical,
    existingMonthCounts: existing,
    canonicalMatchesDates: objectsEqual(derived, canonical),
    existingMatchesDates: objectsEqual(derived, existing),
  };
}

const canonicalRows = readCsv(CANONICAL_FILE);
const existingRows = readCsv(EXISTING_FILE);

const canonicalMap = createMap(canonicalRows);
const existingMap = createMap(existingRows);

const allNumbers = new Set([...canonicalMap.keys(), ...existingMap.keys()]);

const fieldStats = {};

for (const field of CORE_FIELDS) {
  fieldStats[field] = {
    matched: 0,
    different: 0,
  };
}

const differences = [];
const monthDiagnostics = [];

let matchedCore = 0;
let differentCore = 0;

for (const number of [...allNumbers].sort()) {
  const canonical = canonicalMap.get(number);
  const existing = existingMap.get(number);

  if (!canonical || !existing) {
    continue;
  }

  let hasCoreDifference = false;

  for (const field of CORE_FIELDS) {
    const same = compareField(field, canonical[field], existing[field]);

    if (same) {
      fieldStats[field].matched++;
    } else {
      fieldStats[field].different++;
      hasCoreDifference = true;

      differences.push({
        number,
        field,
        canonical: canonical[field],
        existing: existing[field],
      });
    }
  }

  if (hasCoreDifference) {
    differentCore++;
  } else {
    matchedCore++;
  }

  const canonicalMonth = normalizeMonthCounts(canonical.month_counts);

  const existingMonth = normalizeMonthCounts(existing.month_counts);

  if (!objectsEqual(canonicalMonth, existingMonth)) {
    const dates = parseDates(canonical.dates);

    const derived = monthCountsFromDates(dates);

    monthDiagnostics.push({
      number,

      dates,

      derivedFromDates: derived,

      canonicalMonthCounts: canonicalMonth,

      existingMonthCounts: existingMonth,

      canonicalMatchesDates: objectsEqual(derived, canonicalMonth),

      existingMatchesDates: objectsEqual(derived, existingMonth),
    });
  }
}

const report = {
  generatedAt: new Date().toISOString(),

  summary: {
    canonicalRows: canonicalRows.length,
    existingRows: existingRows.length,

    canonicalNumbers: canonicalMap.size,
    existingNumbers: existingMap.size,

    numbersCompared: allNumbers.size,

    matchedCore,
    differentCore,

    monthMismatchCount: monthDiagnostics.length,
  },

  coreFieldStats: fieldStats,

  schemaDifferences: {
    canonicalOnly: CANONICAL_ONLY_FIELDS,
    existingOnly: EXISTING_ONLY_FIELDS,
  },

  differences,

  monthDiagnostics,
};

fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2), "utf8");

console.log("");
console.log("==============================================");
console.log("CANONICAL vs EXISTING DATASET");
console.log("SEMANTIC COMPARISON");
console.log("==============================================");
console.log("");

console.log(`Canonical CSV rows: ${canonicalRows.length}`);

console.log(`Existing CSV rows : ${existingRows.length}`);

console.log("");

console.log("CORE DATA");
console.log("----------------------------------------------");

console.log(`Numbers compared : ${allNumbers.size}`);

console.log(`Core matched     : ${matchedCore}`);

console.log(`Core different   : ${differentCore}`);

console.log("");

console.log("FIELD COMPARISON");
console.log("----------------------------------------------");

for (const field of CORE_FIELDS) {
  const stats = fieldStats[field];

  console.log(
    `${field.padEnd(20)} matched=${String(stats.matched).padStart(
      5,
    )} different=${String(stats.different).padStart(5)}`,
  );
}

console.log("");

console.log("SCHEMA DIFFERENCES");
console.log("----------------------------------------------");

console.log(`Canonical-only: ${CANONICAL_ONLY_FIELDS.join(", ")}`);

console.log(`Existing-only : ${EXISTING_ONLY_FIELDS.join(", ")}`);

console.log("");

console.log("MONTH DIAGNOSTIC");
console.log("----------------------------------------------");

console.log(`Month mismatches: ${monthDiagnostics.length}`);

let canonicalCorrect = 0;
let existingCorrect = 0;
let bothWrong = 0;
let bothMatch = 0;

for (const item of monthDiagnostics) {
  if (item.canonicalMatchesDates && item.existingMatchesDates) {
    bothMatch++;
  } else if (item.canonicalMatchesDates) {
    canonicalCorrect++;
  } else if (item.existingMatchesDates) {
    existingCorrect++;
  } else {
    bothWrong++;
  }
}

console.log(`Canonical matches dates: ${canonicalCorrect}`);

console.log(`Existing matches dates : ${existingCorrect}`);

console.log(`Both match dates       : ${bothMatch}`);

console.log(`Neither matches dates  : ${bothWrong}`);

console.log("");

if (monthDiagnostics.length > 0) {
  console.log("FIRST 10 MONTH DIFFERENCES");
  console.log("----------------------------------------------");

  for (const item of monthDiagnostics.slice(0, 10)) {
    console.log("");
    console.log(`Number: ${item.number}`);

    console.log(`Dates: ${item.dates.length}`);

    console.log(`Derived : ${JSON.stringify(item.derivedFromDates)}`);

    console.log(`Canonical: ${JSON.stringify(item.canonicalMonthCounts)}`);

    console.log(`Existing : ${JSON.stringify(item.existingMonthCounts)}`);

    console.log(`Canonical matches dates: ${item.canonicalMatchesDates}`);

    console.log(`Existing matches dates : ${item.existingMatchesDates}`);
  }
}

console.log("");
console.log("==============================================");

console.log(`Report: ${REPORT_FILE}`);

console.log("==============================================");
console.log("");

if (matchedCore === allNumbers.size && monthDiagnostics.length === 0) {
  console.log("✅ CORE DATASETS MATCH COMPLETELY");
} else if (matchedCore === allNumbers.size) {
  console.log("✅ CORE DATA MATCHES");

  console.log("⚠️ Only month_counts requires investigation.");
} else {
  console.log("⚠️ REAL CORE DATA DIFFERENCES FOUND");
}
