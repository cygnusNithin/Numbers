// server/scripts/analyzeGapHazards.js
//
// Analyze historical draw-gap behavior for all numbers 0000-9999.
// Source: AbsoluteData collection.
// Output: analysis-results/gap-hazard/
//
// Important:
// - Each unique serialNumber represents one draw event.
// - Same-date draws remain separate events.
// - A number is considered present in a draw if its 4-digit number
//   appears at least once in that draw.
// - No database writes are performed.

const mongoose = require("mongoose");
const fs = require("fs");
const path = require("path");

const AbsoluteData = require("../models/AbsoluteData");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

const OUTPUT_DIR = path.join(__dirname, "..", "analysis-results", "gap-hazard");

const BUCKETS = [
  { label: "1", min: 1, max: 1 },
  { label: "2", min: 2, max: 2 },
  { label: "3", min: 3, max: 3 },
  { label: "4-5", min: 4, max: 5 },
  { label: "6-10", min: 6, max: 10 },
  { label: "11-20", min: 11, max: 20 },
  { label: "21-30", min: 21, max: 30 },
  { label: "31-50", min: 31, max: 50 },
  { label: "51-100", min: 51, max: 100 },
  { label: "101-200", min: 101, max: 200 },
  { label: "201+", min: 201, max: Infinity },
];

function padNumber(value) {
  return String(value).padStart(4, "0");
}

function toDate(value) {
  if (!value) return null;

  // Handle Date objects returned by MongoDB.
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  // Handle ISO dates and other standard date strings first.
  if (typeof value === "string") {
    const text = value.trim();

    // Explicitly parse DD/MM/YYYY or DD-MM-YYYY.
    const match = text.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);

    if (match) {
      const day = Number(match[1]);
      const month = Number(match[2]);
      const year = Number(match[3]);

      const date = new Date(Date.UTC(year, month - 1, day));

      // Reject invalid dates such as 31/02/2020.
      if (
        date.getUTCFullYear() !== year ||
        date.getUTCMonth() !== month - 1 ||
        date.getUTCDate() !== day
      ) {
        return null;
      }

      return date;
    }
  }

  // Fallback for Date-compatible values such as ISO timestamps.
  const date = new Date(value);

  return Number.isNaN(date.getTime()) ? null : date;
}

function dateLabel(value) {
  if (!value) return "";

  const d = new Date(value);

  return [
    String(d.getDate()).padStart(2, "0"),
    String(d.getMonth() + 1).padStart(2, "0"),
    d.getFullYear(),
  ].join("/");
}

function csvEscape(value) {
  const text = String(value ?? "");

  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}

function writeCsv(filePath, rows, columns) {
  const lines = [
    columns.join(","),
    ...rows.map((row) =>
      columns.map((column) => csvEscape(row[column])).join(","),
    ),
  ];

  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

function getNumberSet(doc) {
  const numbers = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      const value = String(item.number ?? "").trim();

      if (/^\d{4}$/.test(value)) {
        numbers.add(value);
      }
    }
  }

  return numbers;
}

function median(values) {
  if (!values.length) return null;

  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);

  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function mean(values) {
  if (!values.length) return null;

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function getBucket(gap) {
  return BUCKETS.find((bucket) => gap >= bucket.min && gap <= bucket.max);
}

async function main() {
  await mongoose.connect(MONGO_URI);

  console.log("Connected to MongoDB.");

  const docs = await AbsoluteData.find({})
    .select("serialNumber recordNumber date drawDate series")
    .lean();

  // Deduplicate by draw event identifier, not calendar date.
  const uniqueDocs = new Map();

  for (const doc of docs) {
    const serial = String(doc.serialNumber || "").trim();

    if (!serial) {
      console.warn("Skipping document without serialNumber:", doc._id);
      continue;
    }

    if (!uniqueDocs.has(serial)) {
      uniqueDocs.set(serial, doc);
    }
  }

  const draws = [...uniqueDocs.values()]
    .map((doc) => {
      const date = toDate(doc.drawDate) || toDate(doc.date);

      return {
        serialNumber: String(doc.serialNumber).trim(),
        recordNumber: Number(doc.recordNumber) || 0,
        date,
        numbers: getNumberSet(doc),
      };
    })
    .filter((draw) => draw.date && draw.numbers.size > 0)
    .sort((a, b) => {
      const dateDiff = a.date.getTime() - b.date.getTime();

      if (dateDiff !== 0) return dateDiff;

      const recordDiff = a.recordNumber - b.recordNumber;

      if (recordDiff !== 0) return recordDiff;

      return a.serialNumber.localeCompare(b.serialNumber);
    });

  if (draws.length < 2) {
    throw new Error("At least two valid draw events are required.");
  }

  console.log(`Unique draw events loaded: ${draws.length}`);

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  // appearanceIndices[number] = chronological draw indices where it appeared.
  const appearanceIndices = new Map();

  for (let n = 0; n < 10000; n++) {
    appearanceIndices.set(padNumber(n), []);
  }

  draws.forEach((draw, drawIndex) => {
    for (const number of draw.numbers) {
      appearanceIndices.get(number)?.push(drawIndex);
    }
  });

  // Number-level gap summaries.
  const numberRows = [];

  for (let n = 0; n < 10000; n++) {
    const number = padNumber(n);
    const indices = appearanceIndices.get(number);
    const gaps = [];

    for (let i = 1; i < indices.length; i++) {
      gaps.push(indices[i] - indices[i - 1]);
    }

    const lastIndex = indices.length ? indices[indices.length - 1] : null;

    const currentGap =
      lastIndex === null ? draws.length : draws.length - 1 - lastIndex;

    numberRows.push({
      number,
      historical_hits: indices.length,
      completed_gap_count: gaps.length,
      mean_gap_draws: mean(gaps),
      median_gap_draws: median(gaps),
      min_gap_draws: gaps.length ? Math.min(...gaps) : null,
      max_gap_draws: gaps.length ? Math.max(...gaps) : null,
      current_gap_draws: currentGap,
      last_seen_date:
        lastIndex === null ? "" : dateLabel(draws[lastIndex].date),
      current_gap_to_median_ratio:
        gaps.length && median(gaps) > 0 ? currentGap / median(gaps) : null,
    });
  }

  // Empirical next-draw hit rates by the gap immediately before a draw.
  //
  // For each historical draw t, use only appearances before t to calculate
  // the gap. Then check whether the number appears in draw t.
  //
  // This is a retrospective association, not proof that a number is due.
  const bucketStats = new Map();

  for (const bucket of BUCKETS) {
    bucketStats.set(bucket.label, {
      bucket: bucket.label,
      opportunities: 0,
      hits: 0,
      numberOpportunities: new Set(),
      numberHits: new Set(),
    });
  }

  const exactGapStats = new Map();

  for (let n = 0; n < 10000; n++) {
    const number = padNumber(n);
    let lastSeenIndex = null;

    for (let drawIndex = 0; drawIndex < draws.length; drawIndex++) {
      // Gap before this draw: number of intervening draw events since
      // its previous appearance. Never use the target draw to compute it.
      const gap =
        lastSeenIndex === null ? drawIndex + 1 : drawIndex - lastSeenIndex;

      const appeared = draws[drawIndex].numbers.has(number);
      const bucket = getBucket(gap);

      if (bucket) {
        const stats = bucketStats.get(bucket.label);

        stats.opportunities++;
        stats.numberOpportunities.add(number);

        if (appeared) {
          stats.hits++;
          stats.numberHits.add(number);
        }
      }

      if (!exactGapStats.has(gap)) {
        exactGapStats.set(gap, {
          gap_draws: gap,
          opportunities: 0,
          hits: 0,
        });
      }

      const exact = exactGapStats.get(gap);
      exact.opportunities++;

      if (appeared) exact.hits++;

      if (appeared) {
        lastSeenIndex = drawIndex;
      }
    }
  }

  const totalNumberOpportunities = [...bucketStats.values()].reduce(
    (sum, item) => sum + item.opportunities,
    0,
  );

  const bucketRows = [...bucketStats.values()].map((stats) => ({
    bucket: stats.bucket,
    opportunities: stats.opportunities,
    hits: stats.hits,
    next_draw_hit_rate: stats.opportunities
      ? stats.hits / stats.opportunities
      : null,
    number_count_observed: stats.numberOpportunities.size,
    distinct_numbers_with_hits: stats.numberHits.size,
  }));

  const exactRows = [...exactGapStats.values()]
    .sort((a, b) => a.gap_draws - b.gap_draws)
    .map((stats) => ({
      ...stats,
      next_draw_hit_rate: stats.opportunities
        ? stats.hits / stats.opportunities
        : null,
    }));

  // Current snapshot: what gap each number has at the end of the dataset.
  // This is descriptive; it is not a future prediction.
  const currentBucketStats = new Map();

  for (const bucket of BUCKETS) {
    currentBucketStats.set(bucket.label, {
      bucket: bucket.label,
      numbers: 0,
      total_historical_hits: 0,
      median_historical_gap_sum: 0,
      median_gap_count: 0,
    });
  }

  for (const row of numberRows) {
    const bucket = getBucket(row.current_gap_draws);
    if (!bucket) continue;

    const stats = currentBucketStats.get(bucket.label);
    stats.numbers++;
    stats.total_historical_hits += row.historical_hits;

    if (row.median_gap_draws !== null) {
      stats.median_historical_gap_sum += row.median_gap_draws;
      stats.median_gap_count++;
    }
  }

  const currentRows = [...currentBucketStats.values()].map((stats) => ({
    bucket: stats.bucket,
    numbers: stats.numbers,
    average_historical_hits: stats.numbers
      ? stats.total_historical_hits / stats.numbers
      : null,
    average_median_gap_draws: stats.median_gap_count
      ? stats.median_historical_gap_sum / stats.median_gap_count
      : null,
  }));

  writeCsv(path.join(OUTPUT_DIR, "number_gap_profiles.csv"), numberRows, [
    "number",
    "historical_hits",
    "completed_gap_count",
    "mean_gap_draws",
    "median_gap_draws",
    "min_gap_draws",
    "max_gap_draws",
    "current_gap_draws",
    "last_seen_date",
    "current_gap_to_median_ratio",
  ]);

  writeCsv(path.join(OUTPUT_DIR, "gap_bucket_hazard.csv"), bucketRows, [
    "bucket",
    "opportunities",
    "hits",
    "next_draw_hit_rate",
    "number_count_observed",
    "distinct_numbers_with_hits",
  ]);

  writeCsv(path.join(OUTPUT_DIR, "exact_gap_hazard.csv"), exactRows, [
    "gap_draws",
    "opportunities",
    "hits",
    "next_draw_hit_rate",
  ]);

  writeCsv(path.join(OUTPUT_DIR, "current_gap_distribution.csv"), currentRows, [
    "bucket",
    "numbers",
    "average_historical_hits",
    "average_median_gap_draws",
  ]);

  const summary = {
    generatedAt: new Date().toISOString(),
    sourceCollection: "absolute_data",
    mongoDocuments: docs.length,
    uniqueSerialNumbers: uniqueDocs.size,
    validChronologicalDrawEvents: draws.length,
    firstDrawDate: dateLabel(draws[0].date),
    lastDrawDate: dateLabel(draws[draws.length - 1].date),
    numberUniverse: 10000,
    definitions: {
      gap_draws:
        "For a target draw, number of draw events since the number's previous appearance; for a number never seen before, target draw index + 1.",
      nextDrawHitRate:
        "Hits divided by observed number-draw opportunities in the specified gap bucket.",
      caution:
        "Historical association only. Gap buckets mix numbers with different base frequencies and are not calibrated future probabilities.",
    },
    bucketResults: bucketRows,
  };

  fs.writeFileSync(
    path.join(OUTPUT_DIR, "gap_hazard_summary.json"),
    JSON.stringify(summary, null, 2),
    "utf8",
  );

  console.log("\n============================================================");
  console.log("GAP HAZARD ANALYSIS");
  console.log("============================================================");
  console.log(`Valid draw events: ${draws.length}`);
  console.log(`Numbers analyzed: ${numberRows.length}`);
  console.log(`Output directory: ${OUTPUT_DIR}`);

  console.log("\nGAP BUCKET RESULTS");
  console.table(
    bucketRows.map((row) => ({
      gap: row.bucket,
      opportunities: row.opportunities,
      hits: row.hits,
      hitRate:
        row.next_draw_hit_rate === null
          ? "N/A"
          : (row.next_draw_hit_rate * 100).toFixed(4) + "%",
      numbersSeen: row.number_count_observed,
    })),
  );

  console.log("\nFILES CREATED");
  console.log("  number_gap_profiles.csv");
  console.log("  gap_bucket_hazard.csv");
  console.log("  exact_gap_hazard.csv");
  console.log("  current_gap_distribution.csv");
  console.log("  gap_hazard_summary.json");

  console.log("\nAnalysis complete.");
}

main()
  .catch((error) => {
    console.error("Gap hazard analysis failed:", error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await mongoose.disconnect().catch(() => {});
  });
