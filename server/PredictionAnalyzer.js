import fs from "fs";
import path from "path";

// ==============================================
// CONFIGURATION
// ==============================================
const CSV_FILE = "all_prizes_number_patterns30.csv";
const OUTPUT_FILE = "prediction_results.json";
const REFERENCE_DATE = new Date(2026, 1, 24); // Feb 24, 2026

// Weights for different prediction methods
const WEIGHTS = {
  gap_based: 0.25,
  frequency: 0.2,
  hot_streak: 0.2,
  tier_progression: 0.2,
  seasonality: 0.15,
};

// ==============================================
// HELPER FUNCTIONS
// ==============================================

function parseCSV(filePath) {
  const content = fs.readFileSync(filePath, "utf-8");
  const lines = content.trim().split("\n");
  const headers = lines[0].split(",");

  return lines.slice(1).map((line) => {
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
}

function parseDates(dateString) {
  return dateString
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
}

function getTierCounts(entries) {
  const tierCounts = { 5000: 0, 2000: 0, 1000: 0, 500: 0, 200: 0, 100: 0 };
  entries.forEach((e) => {
    e.prizes.forEach((p) => {
      if (tierCounts[p] !== undefined) tierCounts[p]++;
    });
  });
  return tierCounts;
}

function getRecentActivity(entries, monthsBack = 6) {
  const cutoffDate = new Date(REFERENCE_DATE);
  cutoffDate.setMonth(cutoffDate.getMonth() - monthsBack);
  return entries.filter((e) => e.date >= cutoffDate);
}

// ==============================================
// PREDICTION METHOD 1: GAP-BASED ANALYSIS
// ==============================================
function gapBasedPrediction(row, entries) {
  if (entries.length === 0 || row.avg_gap_days === 0) return 0;

  const lastEntry = entries[entries.length - 1];
  const daysSince = Math.floor(
    (REFERENCE_DATE - lastEntry.date) / (1000 * 60 * 60 * 24),
  );
  const overdueRatio = daysSince / row.avg_gap_days;

  // Score increases dramatically when overdue
  if (overdueRatio >= 2.0) return 100;
  if (overdueRatio >= 1.5) return 85;
  if (overdueRatio >= 1.2) return 70;
  if (overdueRatio >= 1.0) return 60;
  if (overdueRatio >= 0.8) return 40;
  return 20;
}

// ==============================================
// PREDICTION METHOD 2: FREQUENCY-BASED SCORING
// ==============================================
function frequencyBasedScore(row, tierCounts, maxHits) {
  if (maxHits === 0) return 0;

  // Weight high-tier wins more heavily
  const weightedScore =
    tierCounts[5000] * 10 +
    tierCounts[2000] * 7 +
    tierCounts[1000] * 5 +
    tierCounts[500] * 3 +
    tierCounts[200] * 2 +
    tierCounts[100] * 1;

  const frequencyRatio = row.total_hits / maxHits;

  return Math.min(100, weightedScore / 10 + frequencyRatio * 50);
}

// ==============================================
// PREDICTION METHOD 3: HOT STREAK DETECTION
// ==============================================
function hotStreakScore(recentEntries, tierCounts) {
  if (recentEntries.length === 0) return 0;

  const recentHighTier = recentEntries.filter((e) =>
    e.prizes.some((p) => p >= 1000),
  ).length;

  const recentTotal = recentEntries.length;
  const momentum = recentHighTier / Math.max(recentTotal, 1);

  // Bonus for very recent appearances
  const lastEntry = recentEntries[recentEntries.length - 1];
  const daysSinceLast = Math.floor(
    (REFERENCE_DATE - lastEntry.date) / (1000 * 60 * 60 * 24),
  );
  const recencyBonus = daysSinceLast < 30 ? 20 : daysSinceLast < 60 ? 10 : 0;

  return Math.min(100, momentum * 80 + recencyBonus);
}

// ==============================================
// PREDICTION METHOD 4: TIER PROGRESSION
// ==============================================
function tierProgressionScore(tierCounts) {
  // Check for 100 → 500 → 1000 → 5000 progression
  const has100 = tierCounts[100] >= 10;
  const has500 = tierCounts[500] >= 5;
  const has1000 = tierCounts[1000] >= 3;
  const has5000 = tierCounts[5000] >= 1;

  let score = 0;

  // Strong progression pattern
  if (has100 && has500 && has1000 && has5000) {
    score = 90;
  }
  // Building momentum
  else if (has100 && has500 && has1000) {
    score = 75;
  }
  // Early stage
  else if (has100 && has500) {
    score = 55;
  }
  // Starting out
  else if (has100) {
    score = 35;
  }

  // Bonus for recent tier upgrades
  const highTierTotal = tierCounts[5000] + tierCounts[2000] + tierCounts[1000];
  if (highTierTotal >= 15) score += 10;

  return Math.min(100, score);
}

// ==============================================
// PREDICTION METHOD 5: SEASONALITY ANALYSIS
// ==============================================
function seasonalityScore(row) {
  try {
    const weekdayCounts = JSON.parse(row.weekday_counts);
    const monthCounts = JSON.parse(row.month_counts);

    // Get current weekday and month
    const currentWeekday = REFERENCE_DATE.toLocaleDateString("en-US", {
      weekday: "long",
    });
    const currentMonth = REFERENCE_DATE.toLocaleDateString("en-US", {
      month: "long",
    });

    // Calculate weekday score
    const maxWeekdayCount = Math.max(...Object.values(weekdayCounts));
    const currentWeekdayCount = weekdayCounts[currentWeekday] || 0;
    const weekdayScore =
      (currentWeekdayCount / Math.max(maxWeekdayCount, 1)) * 50;

    // Calculate month score
    const maxMonthCount = Math.max(...Object.values(monthCounts));
    const currentMonthCount = monthCounts[currentMonth] || 0;
    const monthScore = (currentMonthCount / Math.max(maxMonthCount, 1)) * 50;

    return weekdayScore + monthScore;
  } catch (e) {
    return 0;
  }
}

// ==============================================
// MAIN PREDICTION ENGINE
// ==============================================
function analyzePredictions(data) {
  console.log("🔄 Analyzing predictions for all numbers...\n");

  const maxHits = Math.max(...data.map((d) => d.total_hits));

  const predictions = data.map((row) => {
    const entries = parseDates(row.dates);
    const tierCounts = getTierCounts(entries);
    const recentEntries = getRecentActivity(entries);

    // Calculate scores for each method
    const scores = {
      gap_based: gapBasedPrediction(row, entries),
      frequency: frequencyBasedScore(row, tierCounts, maxHits),
      hot_streak: hotStreakScore(recentEntries, tierCounts),
      tier_progression: tierProgressionScore(tierCounts),
      seasonality: seasonalityScore(row),
    };

    // Calculate weighted final score
    const finalScore = Math.round(
      scores.gap_based * WEIGHTS.gap_based +
        scores.frequency * WEIGHTS.frequency +
        scores.hot_streak * WEIGHTS.hot_streak +
        scores.tier_progression * WEIGHTS.tier_progression +
        scores.seasonality * WEIGHTS.seasonality,
    );

    // Calculate additional metrics
    const lastEntry = entries.length > 0 ? entries[entries.length - 1] : null;
    const daysSince = lastEntry
      ? Math.floor((REFERENCE_DATE - lastEntry.date) / (1000 * 60 * 60 * 24))
      : 999;
    const overdueRatio =
      row.avg_gap_days > 0 ? daysSince / row.avg_gap_days : 0;

    return {
      number: row.number,
      finalScore,
      scores,
      tierCounts,
      total_hits: row.total_hits,
      avg_gap_days: row.avg_gap_days,
      days_since_last: daysSince,
      overdue_ratio: overdueRatio,
      recent_activity: recentEntries.length,
      last_date: lastEntry ? lastEntry.dateStr : "N/A",
      recommendation: getRecommendation(
        finalScore,
        overdueRatio,
        recentEntries.length,
      ),
    };
  });

  // Sort by final score
  predictions.sort((a, b) => b.finalScore - a.finalScore);

  return predictions;
}

// ==============================================
// RECOMMENDATION GENERATOR
// ==============================================
function getRecommendation(score, overdueRatio, recentActivity) {
  if (score >= 80 && overdueRatio >= 1.5) {
    return "STRONG BUY - Highly overdue with excellent patterns";
  }
  if (score >= 70 && recentActivity >= 5) {
    return "BUY - Hot streak with recent momentum";
  }
  if (score >= 60) {
    return "CONSIDER - Good fundamentals, watch closely";
  }
  if (score >= 40) {
    return "HOLD - Monitor for pattern changes";
  }
  return "PASS - Better opportunities available";
}

// ==============================================
// CATEGORY FILTERS
// ==============================================
function categorizePredictions(predictions) {
  return {
    top_50: predictions.slice(0, 50),
    strong_buy: predictions.filter((p) =>
      p.recommendation.startsWith("STRONG BUY"),
    ),
    buy: predictions.filter((p) => p.recommendation.startsWith("BUY")),
    overdue: predictions.filter((p) => p.overdue_ratio >= 1.5).slice(0, 30),
    hot_streak: predictions
      .filter((p) => p.recent_activity >= 5 && p.scores.hot_streak >= 70)
      .slice(0, 30),
    high_tier_potential: predictions
      .filter(
        (p) =>
          p.tierCounts[5000] >= 5 ||
          (p.tierCounts[1000] >= 5 && p.scores.tier_progression >= 70),
      )
      .slice(0, 30),
  };
}

// ==============================================
// STATISTICS GENERATOR
// ==============================================
function generateStats(predictions) {
  return {
    total_analyzed: predictions.length,
    avg_score: (
      predictions.reduce((sum, p) => sum + p.finalScore, 0) / predictions.length
    ).toFixed(2),
    strong_buy_count: predictions.filter((p) =>
      p.recommendation.startsWith("STRONG BUY"),
    ).length,
    buy_count: predictions.filter((p) => p.recommendation.startsWith("BUY"))
      .length,
    overdue_count: predictions.filter((p) => p.overdue_ratio >= 1.5).length,
    hot_count: predictions.filter((p) => p.recent_activity >= 5).length,
    score_distribution: {
      "80-100": predictions.filter((p) => p.finalScore >= 80).length,
      "60-79": predictions.filter(
        (p) => p.finalScore >= 60 && p.finalScore < 80,
      ).length,
      "40-59": predictions.filter(
        (p) => p.finalScore >= 40 && p.finalScore < 60,
      ).length,
      "0-39": predictions.filter((p) => p.finalScore < 40).length,
    },
  };
}

// ==============================================
// MAIN EXECUTION
// ==============================================
console.log("╔════════════════════════════════════════════╗");
console.log("║   LOTTERY PREDICTION ANALYSIS SYSTEM       ║");
console.log("╚════════════════════════════════════════════╝\n");

console.log("📂 Loading CSV data...");
const data = parseCSV(CSV_FILE);
console.log(`✅ Loaded ${data.length} numbers\n`);

console.log("🧮 Running 5 prediction methods:");
console.log(`   1. Gap-Based Analysis (${WEIGHTS.gap_based * 100}%)`);
console.log(`   2. Frequency Scoring (${WEIGHTS.frequency * 100}%)`);
console.log(`   3. Hot Streak Detection (${WEIGHTS.hot_streak * 100}%)`);
console.log(`   4. Tier Progression (${WEIGHTS.tier_progression * 100}%)`);
console.log(`   5. Seasonality Analysis (${WEIGHTS.seasonality * 100}%)\n`);

const predictions = analyzePredictions(data);
const categories = categorizePredictions(predictions);
const stats = generateStats(predictions);

// ==============================================
// CONSOLE OUTPUT
// ==============================================
console.log("📊 PREDICTION STATISTICS");
console.log("═══════════════════════════════════════════════");
console.log(`Total Numbers Analyzed: ${stats.total_analyzed}`);
console.log(`Average Prediction Score: ${stats.avg_score}`);
console.log(`Strong Buy Signals: ${stats.strong_buy_count}`);
console.log(`Buy Signals: ${stats.buy_count}`);
console.log(`Overdue Numbers: ${stats.overdue_count}`);
console.log(`Hot Numbers: ${stats.hot_count}`);
console.log("\nScore Distribution:");
console.log(`  80-100: ${stats.score_distribution["80-100"]}`);
console.log(`  60-79:  ${stats.score_distribution["60-79"]}`);
console.log(`  40-59:  ${stats.score_distribution["40-59"]}`);
console.log(`  0-39:   ${stats.score_distribution["0-39"]}`);
console.log("═══════════════════════════════════════════════\n");

console.log("🎯 TOP 20 PREDICTIONS");
console.log(
  "════════════════════════════════════════════════════════════════════════",
);
console.log("Rank | Number | Score | Gap | Overdue | Recent | Recommendation");
console.log(
  "─────┼────────┼───────┼─────┼─────────┼────────┼──────────────────────",
);

predictions.slice(0, 20).forEach((p, i) => {
  console.log(
    `${String(i + 1).padStart(4)} | ` +
      `${p.number.padEnd(6)} | ` +
      `${String(p.finalScore).padStart(5)} | ` +
      `${String(p.days_since_last).padStart(3)}d | ` +
      `${p.overdue_ratio.toFixed(2).padStart(7)} | ` +
      `${String(p.recent_activity).padStart(6)} | ` +
      `${p.recommendation}`,
  );
});
console.log(
  "════════════════════════════════════════════════════════════════════════\n",
);

console.log("🔥 TOP 10 STRONG BUY SIGNALS");
console.log("──────────────────────────────────────────────");
categories.strong_buy.slice(0, 10).forEach((p, i) => {
  console.log(
    `${i + 1}. ${p.number} - Score: ${p.finalScore}, Overdue: ${p.overdue_ratio.toFixed(2)}x`,
  );
});
console.log("");

// ==============================================
// SAVE TO JSON
// ==============================================
const output = {
  generated_at: new Date().toISOString(),
  reference_date: REFERENCE_DATE.toISOString(),
  weights: WEIGHTS,
  statistics: stats,
  categories,
  all_predictions: predictions,
};

fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
console.log(`✅ Results saved to: ${OUTPUT_FILE}`);
console.log("\n🎯 Analysis complete!");
console.log(
  `\n💡 Tip: Focus on numbers with Score ≥ 70 and Overdue Ratio ≥ 1.5x`,
);
