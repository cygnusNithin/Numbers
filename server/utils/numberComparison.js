/**
 * Get numbers with least hits (across ALL data, not just one cycle)
 * Grouped by prize tier
 */
function getLeastHitNumbers(hitHistoryByPrize = {}, limit = 100) {
  const result = {};

  for (const [prize, prizeHistory] of Object.entries(hitHistoryByPrize)) {
    // Sort by total hits ascending
    const sorted = [...prizeHistory]
      .sort((a, b) => a.totalHits - b.totalHits)
      .slice(0, limit);

    result[prize] = sorted.map((record) => ({
      number: record.number,
      totalHits: record.totalHits,
      avgGapDays: record.avgGapDays,
      lastDate: record.dates && record.dates.length > 0 
        ? new Date(record.dates[record.dates.length - 1]).toISOString().split('T')[0]
        : "Never",
    }));
  }

  return result;
}

/**
 * Compare remaining numbers with least-hit numbers
 * Returns which remaining numbers are in the least-hit pool
 */
function compareLeastHitWithRemaining(remainingNumbers = [], leastHitByPrize = {}) {
  const result = {};

  for (const [prize, leastHitNumbers] of Object.entries(leastHitByPrize)) {
    const leastHitSet = new Set(leastHitNumbers.map((n) => n.number));

    const matchedLeastHit = [];
    const notInLeastHit = [];

    for (const remaining of remainingNumbers) {
      const record = leastHitNumbers.find((n) => n.number === remaining);
      if (record) {
        matchedLeastHit.push(record);
      } else {
        notInLeastHit.push(remaining);
      }
    }

    // Sort by hit count
    matchedLeastHit.sort((a, b) => a.totalHits - b.totalHits);

    result[prize] = {
      inLeastHit: matchedLeastHit, // Remaining numbers that are in least-hit pool
      notInLeastHit: notInLeastHit, // Remaining numbers NOT in least-hit pool
      leastHitCount: leastHitNumbers.length,
      remainingInLeastHit: matchedLeastHit.length,
      percentageInLeastHit: (
        (matchedLeastHit.length / remainingNumbers.length) * 100
      ).toFixed(2),
    };
  }

  return result;
}

/**
 * Compare daily unique numbers with least-hit numbers
 */
function compareDailyWithLeastHit(dailyNumbers = [], leastHitByPrize = {}) {
  const result = {};

  for (const [prize, leastHitNumbers] of Object.entries(leastHitByPrize)) {
    const leastHitSet = new Set(leastHitNumbers.map((n) => n.number));

    const matchedLeastHit = [];

    for (const daily of dailyNumbers) {
      const record = leastHitNumbers.find((n) => n.number === daily);
      if (record) {
        matchedLeastHit.push(record);
      }
    }

    matchedLeastHit.sort((a, b) => a.totalHits - b.totalHits);

    result[prize] = {
      leastHitInDaily: matchedLeastHit,
      countLeastHitInDaily: matchedLeastHit.length,
    };
  }

  return result;
}

module.exports = {
  getLeastHitNumbers,
  compareLeastHitWithRemaining,
  compareDailyWithLeastHit,
};