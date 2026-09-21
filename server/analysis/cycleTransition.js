/**
 * Builds a profile of WHAT numbers tend to appear on day 1 of a new cycle.
 * Cross-references with cycle-start patterns from cycles 1-4.
 */

function buildTransitionProfile(completedCycles, statsMap) {
  // For each completed cycle, record the numbers that appeared on day 1
  const day1Profiles = completedCycles.map((cycle) => {
    const day1Entry = cycle.drawEntries[0];
    if (!day1Entry) return null;

    const newOnDay1 = day1Entry.numbers
      .filter((n) => n.isNew)
      .map((n) => n.number);

    return {
      cycleNumber: cycle.cycleNumber,
      day1Date: day1Entry.drawDate,
      day1DOW: day1Entry.dayOfWeek,
      newNumbersOnDay1: newOnDay1,
      totalDrawnOnDay1: day1Entry.numberCount,
      newCountOnDay1: newOnDay1.length,
    };
  });

  console.log("\n  Day 1 profile per cycle:");
  for (const p of day1Profiles) {
    if (!p) continue;
    console.log(
      `    Cycle ${p.cycleNumber}: ${p.newCountOnDay1} new numbers on day 1 ` +
        `(${p.day1DOW}, total drawn: ${p.totalDrawnOnDay1})`
    );
  }

  // For each number, count how many times it appeared on day 1 of ANY cycle
  const day1Frequency = new Map();
  for (const profile of day1Profiles) {
    if (!profile) continue;
    for (const num of profile.newNumbersOnDay1) {
      day1Frequency.set(num, (day1Frequency.get(num) || 0) + 1);
    }
  }

  // How many numbers appeared on day 1 of EVERY cycle?
  const alwaysDay1 = [...day1Frequency.entries()].filter(
    ([, count]) => count === completedCycles.length
  );
  const usuallyDay1 = [...day1Frequency.entries()].filter(
    ([, count]) => count >= completedCycles.length - 1
  );

  console.log(`\n  Numbers appearing on day 1 of ALL ${completedCycles.length} completed cycles: ${alwaysDay1.length}`);
  console.log(`  Numbers appearing on day 1 of ≥${completedCycles.length - 1} completed cycles: ${usuallyDay1.length}`);

  return { day1Profiles, day1Frequency, alwaysDay1, usuallyDay1 };
}

/**
 * Predict which numbers will appear on Day 1 of Cycle 6.
 * Priority order:
 *   1. Numbers that appeared on day 1 of ALL previous cycles (highest confidence)
 *   2. Numbers that appeared on day 1 of 3/4 cycles
 *   3. Numbers with lowest avgFirstDay + lowest stdDev (from scoring model)
 *   4. Fill remainder with high-score numbers
 */
function predictCycle6Day1(transitionProfile, statsMap, targetCount = 400) {
  const { day1Frequency, alwaysDay1, usuallyDay1 } = transitionProfile;

  // Tier 1: appeared on day 1 of every cycle
  const tier1 = alwaysDay1.map(([number, count]) => ({
    number,
    tier: 1,
    day1Appearances: count,
    score: scoreNumber(number, statsMap, count, 4),
    avgFirstDay: statsMap.get(number)?.avgFirstDay,
    predictedPrize: statsMap.get(number)?.prizePrediction,
    prizeIsFixed: statsMap.get(number)?.prizeIsAlwaysSame,
  }));

  // Tier 2: appeared on day 1 of 3/4 cycles (not already in tier 1)
  const tier1Set = new Set(tier1.map((t) => t.number));
  const tier2 = usuallyDay1
    .filter(([number]) => !tier1Set.has(number))
    .map(([number, count]) => ({
      number,
      tier: 2,
      day1Appearances: count,
      score: scoreNumber(number, statsMap, count, 4),
      avgFirstDay: statsMap.get(number)?.avgFirstDay,
      predictedPrize: statsMap.get(number)?.prizePrediction,
      prizeIsFixed: statsMap.get(number)?.prizeIsAlwaysSame,
    }));

  // Tier 3: numbers with avgFirstDay ≤ 3 that haven't already been included
  const tier12Set = new Set([...tier1, ...tier2].map((t) => t.number));
  const tier3 = [...statsMap.values()]
    .filter(
      (s) =>
        !tier12Set.has(s.number) &&
        s.avgFirstDay !== null &&
        s.avgFirstDay <= 3 &&
        !(day1Frequency.get(s.number) > 0)
    )
    .sort((a, b) => a.avgFirstDay - b.avgFirstDay)
    .slice(0, targetCount)
    .map((s) => ({
      number: s.number,
      tier: 3,
      day1Appearances: day1Frequency.get(s.number) || 0,
      score: scoreNumber(s.number, statsMap, 0, 4),
      avgFirstDay: s.avgFirstDay,
      predictedPrize: s.prizePrediction,
      prizeIsFixed: s.prizeIsAlwaysSame,
    }));

  // Combine and fill to targetCount
  const combined = [...tier1, ...tier2, ...tier3];
  const combinedSet = new Set(combined.map((t) => t.number));

  // Fill with high-scoring numbers if not enough
  if (combined.length < targetCount) {
    const filler = [...statsMap.values()]
      .filter((s) => !combinedSet.has(s.number) && s.avgFirstDay !== null)
      .sort((a, b) => a.avgFirstDay - b.avgFirstDay)
      .slice(0, targetCount - combined.length)
      .map((s) => ({
        number: s.number,
        tier: 4,
        day1Appearances: day1Frequency.get(s.number) || 0,
        score: scoreNumber(s.number, statsMap, 0, 4),
        avgFirstDay: s.avgFirstDay,
        predictedPrize: s.prizePrediction,
        prizeIsFixed: s.prizeIsAlwaysSame,
      }));
    combined.push(...filler);
  }

  // Sort by tier then score
  combined.sort((a, b) => a.tier - b.tier || b.score - a.score);

  return combined.slice(0, targetCount);
}

function scoreNumber(number, statsMap, day1Count, totalCycles) {
  const s = statsMap.get(number);
  if (!s) return 0;
  const firstDayScore = s.avgFirstDay ? 1 / s.avgFirstDay : 0;
  const consistencyScore = s.stdDevFirstDay !== null ? 1 / (s.stdDevFirstDay + 1) : 0;
  const hotnessScore = s.avgAppearances ? s.avgAppearances / 20 : 0;
  const day1Bonus = day1Count / totalCycles;
  return (firstDayScore * 2 + consistencyScore * 1.5 + hotnessScore + day1Bonus * 2) / 6.5;
}

module.exports = { buildTransitionProfile, predictCycle6Day1 };