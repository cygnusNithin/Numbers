/**
 * The scoring formula:
 *
 *   Score(N) = (1 / avgFirstDay)^W1         ← earlier first appearance = higher score
 *            × (1 / (stdDev + 1))^W2        ← lower std dev = more consistent = higher score
 *            × avgAppearances^W3             ← more appearances = hotter = higher score
 *            × cycleAppearanceRate^W4        ← appeared in all 4 cycles = bonus
 *
 * Weights are tuned by backtesting on cycle 4.
 */

const WEIGHTS = {
  earlyAppearance: 2.0,   // W1 — most important: does it appear early?
  consistency: 1.5,       // W2 — does it appear at same time each cycle?
  hotness: 1.0,           // W3 — how many times does it appear per cycle?
  coverage: 0.5,          // W4 — did it appear in every cycle?
};

function buildScoringModel(completedCycles, stats) {
  const completedCount = completedCycles.length;

  return stats.map((s) => {
    // Normalize avgFirstDay: numbers with day 1-5 get highest score
    // Use inverse: 1 / avgFirstDay (but cap at 1 for day=0 edge case)
    const firstDayScore = s.avgFirstDay
      ? Math.pow(1 / s.avgFirstDay, WEIGHTS.earlyAppearance)
      : 0;

    // Consistency: inverse of (stdDev + 1) to avoid division by zero
    const consistencyScore = s.stdDevFirstDay !== null
      ? Math.pow(1 / (s.stdDevFirstDay + 1), WEIGHTS.consistency)
      : 0;

    // Hotness: normalize avgAppearances (max ~19.5 from data)
    const maxAppearances = 20;
    const hotnessScore = s.avgAppearances
      ? Math.pow(s.avgAppearances / maxAppearances, WEIGHTS.hotness)
      : 0;

    // Coverage: did it appear in all completed cycles?
    const coverageScore = Math.pow(
      s.appearedInCycles / completedCount,
      WEIGHTS.coverage
    );

    const score = firstDayScore * consistencyScore * hotnessScore * coverageScore;

    return {
      number: s.number,
      score,
      avgFirstDay: s.avgFirstDay,
      stdDevFirstDay: s.stdDevFirstDay,
      avgAppearances: s.avgAppearances,
      appearedInCycles: s.appearedInCycles,
      predictedPrize: s.prizePrediction,
      prizeIsFixed: s.prizeIsAlwaysSame,
      preferredDOW: s.preferredDOW,
      cyclesUsed: completedCount,

      // Score breakdown for debugging
      breakdown: {
        firstDayScore: parseFloat(firstDayScore.toFixed(6)),
        consistencyScore: parseFloat(consistencyScore.toFixed(6)),
        hotnessScore: parseFloat(hotnessScore.toFixed(6)),
        coverageScore: parseFloat(coverageScore.toFixed(6)),
      },
    };
  }).sort((a, b) => b.score - a.score);
}

function predictNextDraw(scoringModel, remainingInCycle, drawSize = 364) {
  // If cycle nearly complete: predict remaining + start of next
  if (remainingInCycle.length <= drawSize) {
    const remainingSet = new Set(remainingInCycle);
    const fromNewCycle = scoringModel
      .filter((s) => !remainingSet.has(s.number))
      .slice(0, drawSize - remainingInCycle.length);

    return {
      fromCurrentCycle: remainingInCycle,
      fromNewCycle: fromNewCycle.map((s) => ({
        number: s.number,
        score: s.score,
        predictedPrize: s.predictedPrize,
        prizeIsFixed: s.prizeIsFixed,
      })),
      totalPredicted: remainingInCycle.length + fromNewCycle.length,
      note: `Cycle completes! ${remainingInCycle.length} from cycle 5 + ${fromNewCycle.length} starting cycle 6`,
    };
  }

  // Normal mid-cycle prediction
  const candidates = scoringModel.filter((s) =>
    remainingInCycle.includes(s.number)
  );
  return {
    fromCurrentCycle: candidates.slice(0, drawSize).map((s) => s.number),
    fromNewCycle: [],
    totalPredicted: drawSize,
    note: "Mid-cycle draw prediction",
  };
}

module.exports = { buildScoringModel, predictNextDraw };