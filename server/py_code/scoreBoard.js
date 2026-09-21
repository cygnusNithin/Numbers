import fs from "fs";
import path from "path";

// Configuration
const CSV_FILE = "all_prizes_number_patterns30.csv";
const OUTPUT_FILE = "pattern_analysis_results.json";
const TOP_N = 50;

// Parse CSV
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

// Analyze a single number
function analyzeNumber(row) {
  // Parse dates and prizes
  const entries = row.dates
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

  // Prize tier counts
  const tierCounts = { 5000: 0, 2000: 0, 1000: 0, 500: 0, 200: 0, 100: 0 };
  entries.forEach((e) => {
    e.prizes.forEach((p) => {
      if (tierCounts[p] !== undefined) tierCounts[p]++;
    });
  });

  // Recent momentum (last 6 months)
  const sixMonthsAgo = new Date();
  sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
  const recentEntries = entries.filter((e) => e.date >= sixMonthsAgo);
  const recentHighTier = recentEntries.filter((e) =>
    e.prizes.some((p) => p >= 1000),
  ).length;

  // Last appearance
  const lastEntry = entries.length > 0 ? entries[entries.length - 1] : null;
  const daysSinceLastHit = lastEntry
    ? Math.floor((new Date() - lastEntry.date) / (1000 * 60 * 60 * 24))
    : 999;

  // Calculate pattern score
  let score = 0;
  const factors = [];

  // High tier frequency (30 points)
  const highTierHits = tierCounts[5000] + tierCounts[2000] + tierCounts[1000];
  if (highTierHits >= 15) {
    score += 30;
    factors.push("Elite high-tier performer (15+)");
  } else if (highTierHits >= 10) {
    score += 25;
    factors.push("Strong high-tier history (10-14)");
  } else if (highTierHits >= 5) {
    score += 15;
    factors.push("Moderate high-tier presence (5-9)");
  }

  // Recent momentum (25 points)
  if (recentHighTier >= 3) {
    score += 25;
    factors.push("Hot streak (3+ high-tier in 6mo)");
  } else if (recentHighTier >= 2) {
    score += 20;
    factors.push("Active high-tier momentum (2)");
  } else if (recentEntries.length >= 5) {
    score += 10;
    factors.push("Frequent recent appearances");
  }

  // Gap overdue (20 points)
  const overdueRatio =
    row.avg_gap_days > 0 ? daysSinceLastHit / row.avg_gap_days : 0;
  if (overdueRatio >= 2) {
    score += 20;
    factors.push(`Severely overdue (${overdueRatio.toFixed(1)}x avg gap)`);
  } else if (overdueRatio >= 1.5) {
    score += 15;
    factors.push(`Overdue (${overdueRatio.toFixed(1)}x avg gap)`);
  } else if (overdueRatio >= 1.2) {
    score += 10;
    factors.push(`Slightly overdue (${overdueRatio.toFixed(1)}x)`);
  }

  // Tier progression (15 points)
  if (tierCounts[100] >= 20 && tierCounts[5000] >= 3) {
    score += 15;
    factors.push("Proven 100→5000 progression");
  } else if (tierCounts[500] >= 10 && tierCounts[1000] >= 2) {
    score += 10;
    factors.push("500→1000 progression pattern");
  }

  // Consistency (10 points)
  if (row.total_hits >= 80 && row.avg_gap_days < 25) {
    score += 10;
    factors.push("Ultra-consistent (<25d gap, 80+ hits)");
  } else if (row.total_hits >= 50 && row.avg_gap_days < 35) {
    score += 7;
    factors.push("Very consistent performer");
  }

  return {
    number: row.number,
    score,
    total_hits: row.total_hits,
    avg_gap_days: row.avg_gap_days,
    days_since_last: daysSinceLastHit,
    overdue_ratio: overdueRatio,
    tier_5000: tierCounts[5000],
    tier_2000: tierCounts[2000],
    tier_1000: tierCounts[1000],
    tier_500: tierCounts[500],
    tier_200: tierCounts[200],
    tier_100: tierCounts[100],
    high_tier_total: highTierHits,
    recent_high_tier: recentHighTier,
    recent_total: recentEntries.length,
    factors,
    last_date: lastEntry ? lastEntry.dateStr : "N/A",
  };
}

// Main execution
console.log("🔄 Loading CSV file...");
const data = parseCSV(CSV_FILE);
console.log(`✅ Loaded ${data.length} numbers\n`);

console.log("🔄 Analyzing patterns...");
const analyzed = data.map(analyzeNumber);

// Sort by score
analyzed.sort((a, b) => b.score - a.score);

// Statistics
const stats = {
  total_numbers: analyzed.length,
  avg_score: (
    analyzed.reduce((sum, d) => sum + d.score, 0) / analyzed.length
  ).toFixed(2),
  high_score_count: analyzed.filter((d) => d.score >= 70).length,
  hot_numbers: analyzed.filter((d) => d.recent_high_tier >= 2).length,
  overdue_numbers: analyzed.filter((d) => d.overdue_ratio >= 1.5).length,
  elite_performers: analyzed.filter((d) => d.high_tier_total >= 10).length,
};

console.log("📊 OVERALL STATISTICS");
console.log("═══════════════════════════════════════════════════════════");
console.log(`Total Numbers Analyzed: ${stats.total_numbers}`);
console.log(`Average Pattern Score: ${stats.avg_score}`);
console.log(`High Scores (70+): ${stats.high_score_count}`);
console.log(`Hot Numbers (2+ recent high-tier): ${stats.hot_numbers}`);
console.log(`Overdue Numbers (1.5x+ gap): ${stats.overdue_numbers}`);
console.log(`Elite Performers (10+ high-tier): ${stats.elite_performers}`);
console.log("═══════════════════════════════════════════════════════════\n");

// Top performers
console.log(`🏆 TOP ${TOP_N} NUMBERS BY PATTERN SCORE`);
console.log("═══════════════════════════════════════════════════════════");
console.log(
  "Rank | Number | Score | Hits | ₹5K | ₹2K | ₹1K | HT | Recent | Status",
);
console.log(
  "─────┼────────┼───────┼──────┼─────┼─────┼─────┼────┼────────┼─────────",
);

analyzed.slice(0, TOP_N).forEach((item, index) => {
  const status =
    item.overdue_ratio >= 1.5
      ? "OVERDUE"
      : item.recent_high_tier >= 2
        ? "HOT 🔥"
        : "Normal";

  console.log(
    `${String(index + 1).padStart(4)} | ` +
      `${item.number.padEnd(6)} | ` +
      `${String(item.score).padStart(5)} | ` +
      `${String(item.total_hits).padStart(4)} | ` +
      `${String(item.tier_5000).padStart(3)} | ` +
      `${String(item.tier_2000).padStart(3)} | ` +
      `${String(item.tier_1000).padStart(3)} | ` +
      `${String(item.high_tier_total).padStart(2)} | ` +
      `${String(item.recent_high_tier).padStart(6)} | ` +
      `${status}`,
  );
});
console.log("═══════════════════════════════════════════════════════════\n");

// Category breakdowns
console.log("🔥 HOT NUMBERS (Recent Momentum)");
console.log("─────────────────────────────────────────");
const hotNumbers = analyzed.filter((d) => d.recent_high_tier >= 2).slice(0, 20);
hotNumbers.forEach((item, idx) => {
  console.log(
    `${idx + 1}. ${item.number} - Score: ${item.score}, Recent High-Tier: ${item.recent_high_tier}, Last: ${item.last_date}`,
  );
});
console.log("");

console.log("⏰ OVERDUE NUMBERS (Past Average Gap)");
console.log("─────────────────────────────────────────");
const overdueNumbers = analyzed
  .filter((d) => d.overdue_ratio >= 1.5)
  .slice(0, 20);
overdueNumbers.forEach((item, idx) => {
  console.log(
    `${idx + 1}. ${item.number} - Score: ${item.score}, Overdue: ${item.overdue_ratio.toFixed(2)}x, Days Since: ${item.days_since_last}d`,
  );
});
console.log("");

console.log("👑 ELITE PERFORMERS (10+ High-Tier Wins)");
console.log("─────────────────────────────────────────");
const eliteNumbers = analyzed
  .filter((d) => d.high_tier_total >= 10)
  .slice(0, 20);
eliteNumbers.forEach((item, idx) => {
  console.log(
    `${idx + 1}. ${item.number} - Score: ${item.score}, High-Tier: ${item.high_tier_total}, ₹5000: ${item.tier_5000}`,
  );
});
console.log("");

// Save detailed results
const output = {
  generated_at: new Date().toISOString(),
  statistics: stats,
  top_50: analyzed.slice(0, 50),
  hot_numbers: hotNumbers,
  overdue_numbers: overdueNumbers,
  elite_performers: eliteNumbers,
};

fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
console.log(`✅ Detailed results saved to: ${OUTPUT_FILE}`);
console.log("\n🎯 Analysis complete!");
