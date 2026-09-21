const { getAllNumbers } = require("./utils");

/**
 * Since numbers CAN repeat within a cycle, each profile entry tracks:
 * - firstAppearanceDay: which day in the cycle the number appeared FIRST
 * - totalAppearances: how many times it appeared in that cycle
 * - prize: the prize on its FIRST appearance (for prediction)
 */
function buildNumberProfiles(cycles) {
  const profiles = new Map();
  for (const num of getAllNumbers()) {
    profiles.set(num, []);
  }

  for (const cycle of cycles) {
    // For this cycle, track first appearance and count per number
    const cycleStats = new Map(); // number → { firstDay, count, firstPrize, firstDOW }

    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (!cycleStats.has(number)) {
          cycleStats.set(number, {
            firstDay: dayEntry.dayIndexInCycle,
            count: 0,
            firstPrize: prize,
            firstDOW: dayEntry.dayOfWeek,
            drawDate: dayEntry.drawDate,
          });
        }
        cycleStats.get(number).count++;
      }
    }

    // Push this cycle's stats into each number's profile
    for (const [number, stats] of cycleStats) {
      if (profiles.has(number)) {
        profiles.get(number).push({
          cycleNumber: cycle.cycleNumber,
          firstAppearanceDay: stats.firstDay,
          totalAppearances: stats.count,
          firstPrize: stats.firstPrize,
          firstDOW: stats.firstDOW,
          drawDate: stats.drawDate,
        });
      }
    }
  }

  return profiles;
}

/**
 * Compute per-number statistics from profiles.
 * Key metric: firstAppearanceDay across completed cycles.
 * This tells us WHEN in the cycle a number tends to first appear.
 */
function computeNumberStats(profiles, totalCycleCount) {
  const stats = [];
  const completedCount = totalCycleCount - 1; // exclude current incomplete cycle

  for (const [number, history] of profiles) {
    // Only use completed cycles for statistics
    const completedHistory = history.filter(
      (h) => h.cycleNumber < totalCycleCount
    );

    const firstDays = completedHistory.map((h) => h.firstAppearanceDay);
    const avgFirstDay =
      firstDays.length
        ? parseFloat(
            (firstDays.reduce((a, b) => a + b, 0) / firstDays.length).toFixed(2)
          )
        : null;

    const stdDevFirstDay =
      firstDays.length > 1
        ? parseFloat(
            Math.sqrt(
              firstDays.reduce((s, d) => s + Math.pow(d - avgFirstDay, 2), 0) /
                firstDays.length
            ).toFixed(2)
          )
        : null;

    // Average appearances per cycle (hot = appears many times)
    const avgAppearances =
      completedHistory.length
        ? parseFloat(
            (
              completedHistory.reduce((s, h) => s + h.totalAppearances, 0) /
              completedHistory.length
            ).toFixed(2)
          )
        : null;

    // Prize mode (most common first-appearance prize)
    const prizeFreq = {};
    for (const h of completedHistory) {
      prizeFreq[h.firstPrize] = (prizeFreq[h.firstPrize] || 0) + 1;
    }
    const prizePrediction =
      Object.keys(prizeFreq).length
        ? Number(
            Object.entries(prizeFreq).sort((a, b) => b[1] - a[1])[0][0]
          )
        : null;
    const prizeIsAlwaysSame =
      Object.keys(prizeFreq).length === 1 && completedHistory.length === completedCount;

    // Day-of-week preference for first appearance
    const dowFreq = {};
    for (const h of completedHistory) {
      if (h.firstDOW) dowFreq[h.firstDOW] = (dowFreq[h.firstDOW] || 0) + 1;
    }
    const preferredDOW =
      Object.keys(dowFreq).length
        ? Object.entries(dowFreq).sort((a, b) => b[1] - a[1])[0][0]
        : null;

    // Cycle 5 status
    const cycle5Entry = history.find((h) => h.cycleNumber === totalCycleCount);
    const drawnInCycle5 = !!cycle5Entry;
    const cycle5FirstDay = cycle5Entry?.firstAppearanceDay ?? null;

    stats.push({
      number,
      appearedInCycles: completedHistory.length,
      avgFirstDay,
      stdDevFirstDay,
      avgAppearances,
      prizePrediction,
      prizeIsAlwaysSame,
      prizeHistory: prizeFreq,
      preferredDOW,
      dowHistory: dowFreq,
      drawnInCycle5,
      cycle5FirstDay,
      fullHistory: history,
    });
  }

  return stats;
}

/**
 * Numbers NOT yet drawn in cycle 5 (candidates for upcoming draws).
 * These have appeared in past cycles but haven't shown up in cycle 5 yet.
 */
function getRemainingCycle5Numbers(profiles, lastCycleNumber) {
  const remaining = [];
  for (const [number, history] of profiles) {
    const drawnInCycle5 = history.some((h) => h.cycleNumber === lastCycleNumber);
    if (!drawnInCycle5) {
      remaining.push(number);
    }
  }
  return remaining.sort();
}

/**
 * Print consistency report — numbers with low std dev appear at
 * predictable points in the cycle → most useful for timing prediction.
 */
function printConsistencyReport(stats, topN = 20) {
  const withData = stats.filter(
    (s) => s.stdDevFirstDay !== null && s.avgFirstDay !== null
  );
  const sorted = [...withData].sort((a, b) => a.stdDevFirstDay - b.stdDevFirstDay);

  console.log(
    `\n===== TOP ${topN} MOST CONSISTENT (low std dev in first-appearance day) =====`
  );
  for (const s of sorted.slice(0, topN)) {
    console.log(
      `  ${s.number} | avgDay: ${s.avgFirstDay} | stdDev: ${s.stdDevFirstDay} | ` +
        `avgAppearances/cycle: ${s.avgAppearances} | predictedPrize: ${s.prizePrediction} | ` +
        `prefDOW: ${s.preferredDOW} | prizeFixed: ${s.prizeIsAlwaysSame}`
    );
  }

  console.log(
    `\n===== TOP ${topN} LEAST CONSISTENT (high std dev) =====`
  );
  for (const s of sorted.slice(-topN).reverse()) {
    console.log(
      `  ${s.number} | avgDay: ${s.avgFirstDay} | stdDev: ${s.stdDevFirstDay} | ` +
        `avgAppearances/cycle: ${s.avgAppearances} | predictedPrize: ${s.prizePrediction}`
    );
  }
}

/**
 * Print overall number frequency distribution across cycles.
 */
function printFrequencyDistribution(stats, completedCycleCount) {
  console.log("\n===== NUMBER COVERAGE ACROSS COMPLETED CYCLES =====");
  const buckets = {};
  for (const s of stats) {
    const key = s.appearedInCycles;
    buckets[key] = (buckets[key] || 0) + 1;
  }
  const sorted = Object.entries(buckets).sort((a, b) => Number(b[0]) - Number(a[0]));
  for (const [count, numCount] of sorted) {
    const pct = ((numCount / 10000) * 100).toFixed(1);
    const bar = "█".repeat(Math.round(pct / 2));
    console.log(
      `  Appeared in ${String(count).padEnd(3)} cycles: ${String(numCount).padEnd(5)} numbers (${pct}%) ${bar}`
    );
  }
  console.log("===================================================\n");
}

module.exports = {
  buildNumberProfiles,
  computeNumberStats,
  getRemainingCycle5Numbers,
  printConsistencyReport,
  printFrequencyDistribution,
};