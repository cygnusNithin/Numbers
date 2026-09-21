require("dotenv").config();
const express      = require("express");
const mongoose     = require("mongoose");
const cors         = require("cors");

const LotteryData      = require("../models/FullLotteryData");
const { detectCycles } = require("./cycleDetector");
const {
  buildNumberProfiles,
  computeNumberStats,
  getRemainingCycle5Numbers,
} = require("./numberProfiler");

const app  = express();
const PORT = process.env.ANALYSIS_PORT || 4000;

app.use(cors());
app.use(express.json());

// ─────────────────────────────────────────────────────
// In-memory state — rebuilt on startup + on /refresh
// ─────────────────────────────────────────────────────
let STATE = null;

async function buildState() {
  console.log("🔄 Building analysis state...");

  const draws      = await LotteryData.find({}).sort({ drawDate: 1 }).lean();
  const allCycles  = detectCycles(draws);
  const validCycles  = allCycles.filter((c) => c.cycleNumber !== 1);
  const trainCycles  = validCycles.filter((c) => c.isComplete);
  const currentCycle = validCycles.find((c) => !c.isComplete);

  const profiles   = buildNumberProfiles(validCycles);
  const stats      = computeNumberStats(profiles, validCycles.length);
  const statsMap   = new Map(stats.map((s) => [s.number, s]));
  const remaining  = getRemainingCycle5Numbers(profiles, currentCycle.cycleNumber);

  // Frequency table (training cycles 2,3,4)
  const avgCycleDays = trainCycles.reduce((a, c) => a + c.totalDrawDays, 0)
    / trainCycles.length;
  const freqTable = buildFrequencyTable(statsMap, avgCycleDays);

  // Recency table (cycle 5)
  const recencyTable = buildRecencyTable(currentCycle, freqTable);

  // Daily scores
  const dailyScores = buildDailyScores(freqTable, recencyTable, remaining);

  // Prize model
  const prizeModel = buildPrizeModel(statsMap);

  // Cycle 5 stats
  const recentEntries  = currentCycle.drawEntries.slice(-7);
  const recentNewPerDay = recentEntries
    .map((d) => d.newNumbersAdded)
    .reduce((a, b) => a + b, 0) / recentEntries.length;

  const avgDrawSize = currentCycle.drawEntries
    .map((d) => d.numberCount)
    .reduce((a, b) => a + b, 0) / currentCycle.drawEntries.length;

  const estimatedDaysLeft = recentNewPerDay > 0
    ? Math.ceil(remaining.length / recentNewPerDay)
    : null;

  // Cycle 6 top-500 prediction
  const normProfiles = buildNormalizedProfiles(validCycles);
  const normMap      = buildNormStatsMap(normProfiles, trainCycles);
  const maxApp       = Math.max(...[...normMap.values()].map((v) => v.avgAppearances));
  const cycle6Model  = buildNormScoringModel(normMap, trainCycles.length, maxApp);

  STATE = {
    builtAt:         new Date().toISOString(),
    cycleCount:      allCycles.length,
    currentCycle: {
      number:        currentCycle.cycleNumber,
      drawDays:      currentCycle.totalDrawDays,
      numbersDrawn:  currentCycle.totalNumbersDrawn,
      remaining:     remaining.length,
      lastDrawDate:  new Date(currentCycle.endDate).toISOString().split("T")[0],
      avgDrawSize:   Math.round(avgDrawSize),
      recentNewPerDay: parseFloat(recentNewPerDay.toFixed(1)),
      estimatedDaysLeft,
      isEndImminent: remaining.length <= Math.ceil(recentNewPerDay * 3),
    },
    remaining,
    dailyScores,
    prizeModel,
    cycle6Model:     cycle6Model.slice(0, 500),
    statsMap,
  };

  console.log(`✅ State built — cycle ${currentCycle.cycleNumber}, ` +
    `${remaining.length} remaining, ~${estimatedDaysLeft} days left`);
  return STATE;
}

// ─────────────────────────────────────────────────────
// GET /status
// High-level system status
// ─────────────────────────────────────────────────────
app.get("/status", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  res.json({
    status:    "ok",
    builtAt:   STATE.builtAt,
    cycle:     STATE.currentCycle,
    summary: {
      remaining:        STATE.currentCycle.remaining,
      estimatedDaysLeft: STATE.currentCycle.estimatedDaysLeft,
      isEndImminent:    STATE.currentCycle.isEndImminent,
      cycle6Ready:      STATE.cycle6Model.length > 0,
    },
  });
});

// ─────────────────────────────────────────────────────
// GET /remaining
// All numbers guaranteed to appear before cycle ends
// Query: ?sortBy=overdue|prize|number  (default: overdue)
// ─────────────────────────────────────────────────────
app.get("/remaining", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const sortBy   = req.query.sortBy || "overdue";
  const scoreMap = new Map(STATE.dailyScores.map((s) => [s.number, s]));

  const enriched = STATE.remaining.map((num) => {
    const score = scoreMap.get(num);
    const stat  = STATE.statsMap.get(num);
    return {
      number:         num,
      overdueScore:   score?.overdueScore ?? 0,
      daysSinceSeen:  score?.daysSinceSeen ?? 0,
      avgGapDays:     score?.avgGapDays ?? 0,
      predictedPrize: score?.predictedPrize ?? null,
      prizeIsFixed:   score?.prizeIsFixed ?? false,
      preferredDOW:   score?.preferredDOW ?? null,
      prizeConfidence: STATE.prizeModel.get(num)?.confidence ?? null,
      urgency:
        (score?.overdueScore ?? 0) >= 4 ? "CRITICAL" :
        (score?.overdueScore ?? 0) >= 2 ? "HIGH"     :
        (score?.overdueScore ?? 0) >= 1 ? "MED"      : "LOW",
    };
  });

  const sorted =
    sortBy === "prize"  ? enriched.sort((a, b) => (b.predictedPrize ?? 0) - (a.predictedPrize ?? 0)) :
    sortBy === "number" ? enriched.sort((a, b) => a.number.localeCompare(b.number)) :
                          enriched.sort((a, b) => b.overdueScore - a.overdueScore);

  res.json({
    count:   sorted.length,
    sortBy,
    cycle:   STATE.currentCycle.number,
    numbers: sorted,
  });
});

// ─────────────────────────────────────────────────────
// GET /predict/tomorrow
// Full tomorrow prediction: certain + high probability
// Query: ?topN=100 (default 100)
// ─────────────────────────────────────────────────────
app.get("/predict/tomorrow", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const topN         = Math.min(parseInt(req.query.topN) || 100, 500);
  const remainingSet = new Set(STATE.remaining);

  // Layer 1: certain
  const certain = STATE.dailyScores
    .filter((s) => s.isCertain)
    .map((s) => ({
      ...s,
      layer:           "CERTAIN",
      prizeConfidence: STATE.prizeModel.get(s.number)?.confidence ?? null,
    }));

  // Layer 2: high probability non-certain
  const highProb = STATE.dailyScores
    .filter((s) => !s.isCertain)
    .slice(0, Math.max(topN - certain.length, 0))
    .map((s) => ({
      ...s,
      layer:           "HIGH_PROB",
      prizeConfidence: STATE.prizeModel.get(s.number)?.confidence ?? null,
    }));

  res.json({
    generatedAt:    new Date().toISOString(),
    cycleStatus:    STATE.currentCycle,
    totalPredicted: certain.length + highProb.length,
    certain: {
      count:   certain.length,
      numbers: certain,
    },
    highProbability: {
      count:   highProb.length,
      numbers: highProb,
    },
  });
});

// ─────────────────────────────────────────────────────
// GET /predict/cycle6
// Top-N predictions for cycle 6 start
// Query: ?topN=500
// ─────────────────────────────────────────────────────
app.get("/predict/cycle6", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const topN     = Math.min(parseInt(req.query.topN) || 500, 500);
  const numbers  = STATE.cycle6Model.slice(0, topN).map((p) => ({
    ...p,
    prizeConfidence: STATE.prizeModel.get(p.number)?.confidence ?? null,
  }));

  res.json({
    generatedAt: new Date().toISOString(),
    note:        "Ranked by normalized first-appearance position across cycles 2–4",
    count:       numbers.length,
    numbers,
  });
});

// ─────────────────────────────────────────────────────
// GET /prize/:number
// Prize prediction for a specific number
// ─────────────────────────────────────────────────────
app.get("/prize/:number", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const num   = req.params.number.padStart(4, "0");
  const prize = STATE.prizeModel.get(num);
  const stat  = STATE.statsMap.get(num);

  if (!prize) return res.status(404).json({ error: `Number ${num} not found` });

  res.json({
    number:         num,
    predictedPrize: prize.predictedPrize,
    isFixed:        prize.isFixed,
    confidence:     prize.confidence,
    prizeHistory:   prize.prizeHistory,
    avgAppearances: stat?.avgAppearances ?? null,
    preferredDOW:   stat?.preferredDOW ?? null,
    drawnInCycle5:  !STATE.remaining.includes(num),
    isRemaining:    STATE.remaining.includes(num),
  });
});

// ─────────────────────────────────────────────────────
// GET /prize/summary
// Full prize distribution across all numbers
// Query: ?confidence=75  (filter by min confidence)
// ─────────────────────────────────────────────────────
app.get("/prize/summary", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const minConf = parseFloat(req.query.confidence) || 0;

  const byPrize = {};
  for (const [num, p] of STATE.prizeModel) {
    if (p.confidence < minConf) continue;
    if (!byPrize[p.predictedPrize]) byPrize[p.predictedPrize] = [];
    byPrize[p.predictedPrize].push({
      number:     num,
      isFixed:    p.isFixed,
      confidence: p.confidence,
    });
  }

  const summary = Object.entries(byPrize)
    .sort((a, b) => Number(b[0]) - Number(a[0]))
    .map(([prize, numbers]) => ({
      prize:       Number(prize),
      count:       numbers.length,
      fixedCount:  numbers.filter((n) => n.isFixed).length,
      numbers:     numbers.sort((a, b) => b.confidence - a.confidence),
    }));

  res.json({
    minConfidenceFilter: minConf,
    totalNumbers:        [...STATE.prizeModel.values()].filter(
      (p) => p.confidence >= minConf
    ).length,
    byPrize: summary,
  });
});

// ─────────────────────────────────────────────────────
// GET /number/:number
// Full profile for a specific number
// ─────────────────────────────────────────────────────
app.get("/number/:number", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const num       = req.params.number.padStart(4, "0");
  const stat      = STATE.statsMap.get(num);
  const score     = STATE.dailyScores.find((s) => s.number === num);
  const prize     = STATE.prizeModel.get(num);
  const isRemaining = STATE.remaining.includes(num);

  if (!stat) return res.status(404).json({ error: `Number ${num} not found` });

  res.json({
    number:           num,
    isRemainingInCycle5: isRemaining,
    isGuaranteed:     isRemaining,
    cycle5Status:     isRemaining ? "NOT YET DRAWN" : "DRAWN",
    frequency: {
      avgAppearances:  stat.avgAppearances,
      baseRatePerDay:  score?.baseRate ?? null,
      avgGapDays:      score?.avgGapDays ?? null,
    },
    recency: {
      overdueScore:   score?.overdueScore ?? null,
      daysSinceSeen:  score?.daysSinceSeen ?? null,
      recencyMult:    score?.recencyMult ?? null,
    },
    prize: {
      predictedPrize:  prize?.predictedPrize ?? null,
      isFixed:         prize?.isFixed ?? false,
      confidence:      prize?.confidence ?? null,
      prizeHistory:    prize?.prizeHistory ?? {},
    },
    timing: {
      preferredDOW:    stat.preferredDOW,
      appearedInCycles: stat.appearedInCycles,
    },
    dailyScore:        score?.finalScore ?? null,
  });
});

// ─────────────────────────────────────────────────────
// GET /cycle/status
// Detailed cycle 5 status + cycle 6 transition readiness
// ─────────────────────────────────────────────────────
app.get("/cycle/status", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const c = STATE.currentCycle;

  res.json({
    cycle5: {
      ...c,
      remainingNumbers: STATE.remaining,
      urgencyBreakdown: {
        critical: STATE.dailyScores.filter(
          (s) => s.isCertain && s.overdueScore >= 4
        ).length,
        high: STATE.dailyScores.filter(
          (s) => s.isCertain && s.overdueScore >= 2 && s.overdueScore < 4
        ).length,
        med: STATE.dailyScores.filter(
          (s) => s.isCertain && s.overdueScore >= 1 && s.overdueScore < 2
        ).length,
        low: STATE.dailyScores.filter(
          (s) => s.isCertain && s.overdueScore < 1
        ).length,
      },
    },
    cycle6: {
      transitionImminent: c.isEndImminent,
      estimatedStart:     c.estimatedDaysLeft
        ? `~${c.estimatedDaysLeft} draw days from now`
        : "unknown",
      top10Predictions:   STATE.cycle6Model.slice(0, 10),
    },
  });
});

// ─────────────────────────────────────────────────────
// POST /refresh
// Rebuild state from latest DB data (call after adding new draw)
// ─────────────────────────────────────────────────────
app.post("/refresh", async (req, res) => {
  try {
    await buildState();
    res.json({
      status:  "refreshed",
      builtAt: STATE.builtAt,
      cycle:   STATE.currentCycle,
    });
  } catch (err) {
    console.error("Refresh failed:", err);
    res.status(500).json({ error: err.message });
  }
});

// ─────────────────────────────────────────────────────
// GET /numbers/search
// Search numbers by criteria
// Query: ?prize=500&fixed=true&minConf=90&limit=50
// ─────────────────────────────────────────────────────
app.get("/numbers/search", (req, res) => {
  if (!STATE) return res.status(503).json({ error: "State not ready" });

  const filterPrize   = req.query.prize ? Number(req.query.prize) : null;
  const filterFixed   = req.query.fixed === "true";
  const minConf       = parseFloat(req.query.minConf) || 0;
  const limit         = Math.min(parseInt(req.query.limit) || 50, 500);
  const onlyRemaining = req.query.remaining === "true";
  const remainingSet  = new Set(STATE.remaining);

  const results = [];
  for (const [num, prize] of STATE.prizeModel) {
    if (filterPrize && prize.predictedPrize !== filterPrize) continue;
    if (filterFixed && !prize.isFixed) continue;
    if (prize.confidence < minConf) continue;
    if (onlyRemaining && !remainingSet.has(num)) continue;

    const score = STATE.dailyScores.find((s) => s.number === num);
    results.push({
      number:         num,
      predictedPrize: prize.predictedPrize,
      isFixed:        prize.isFixed,
      confidence:     prize.confidence,
      overdueScore:   score?.overdueScore ?? null,
      isRemaining:    remainingSet.has(num),
    });
  }

  results.sort((a, b) => b.confidence - a.confidence);

  res.json({
    query:   req.query,
    count:   results.length,
    showing: Math.min(results.length, limit),
    results: results.slice(0, limit),
  });
});

// ─────────────────────────────────────────────────────
// HELPER FUNCTIONS
// (same logic as phase3.js, self-contained here)
// ─────────────────────────────────────────────────────
function buildFrequencyTable(statsMap, avgCycleDays) {
  const table = new Map();
  for (const [number, stat] of statsMap) {
    if ((stat.appearedInCycles ?? 0) < 2) continue;
    const avgApp   = stat.avgAppearances ?? 1;
    const baseRate = avgApp / avgCycleDays;
    table.set(number, {
      number,
      avgAppearances:  avgApp,
      baseRatePerDay:  parseFloat(baseRate.toFixed(6)),
      avgGapDays:      parseFloat((avgCycleDays / avgApp).toFixed(2)),
      predictedPrize:  stat.prizePrediction,
      prizeIsFixed:    stat.prizeIsAlwaysSame,
      preferredDOW:    stat.preferredDOW,
    });
  }
  return table;
}

function buildRecencyTable(currentCycle, freqTable) {
  const lastSeenDay = new Map();
  for (const dayEntry of currentCycle.drawEntries) {
    for (const { number } of dayEntry.numbers) {
      lastSeenDay.set(number, dayEntry.dayIndexInCycle);
    }
  }
  const currentDay = currentCycle.totalDrawDays;
  const recency    = new Map();
  for (const [number, freq] of freqTable) {
    const lastDay       = lastSeenDay.get(number) ?? 0;
    const daysSinceSeen = currentDay - lastDay;
    const overdueScore  = freq.avgGapDays > 0 ? daysSinceSeen / freq.avgGapDays : 1;
    recency.set(number, {
      number,
      lastSeenDay:       lastDay || null,
      daysSinceSeen,
      avgGapDays:        freq.avgGapDays,
      overdueScore:      parseFloat(overdueScore.toFixed(3)),
      recencyMultiplier: parseFloat(Math.min(overdueScore, 3.0).toFixed(3)),
    });
  }
  return recency;
}

function buildDailyScores(freqTable, recencyTable, remaining) {
  const remainingSet = new Set(remaining);
  return [...freqTable.values()]
    .map((freq) => {
      const recency   = recencyTable.get(freq.number);
      const isCertain = remainingSet.has(freq.number);
      const baseRate  = freq.baseRatePerDay;
      const recMult   = recency?.recencyMultiplier ?? 1.0;
      const certainty = isCertain ? 10.0 : 1.0;
      return {
        number:         freq.number,
        finalScore:     parseFloat((baseRate * recMult * certainty).toFixed(8)),
        baseRate,
        recencyMult:    recMult,
        overdueScore:   recency?.overdueScore ?? 1.0,
        daysSinceSeen:  recency?.daysSinceSeen ?? 0,
        avgGapDays:     freq.avgGapDays,
        isCertain,
        predictedPrize: freq.predictedPrize,
        prizeIsFixed:   freq.prizeIsFixed,
        preferredDOW:   freq.preferredDOW,
        avgAppearances: freq.avgAppearances,
      };
    })
    .sort((a, b) => b.finalScore - a.finalScore);
}

function buildPrizeModel(statsMap) {
  const map = new Map();
  for (const [number, stat] of statsMap) {
    if (!stat.prizePrediction) continue;
    const history    = stat.prizeHistory ?? {};
    const totalDraws = Object.values(history).reduce((a, b) => a + b, 0);
    const topCount   = history[stat.prizePrediction] ?? 0;
    map.set(number, {
      predictedPrize: stat.prizePrediction,
      isFixed:        stat.prizeIsAlwaysSame,
      confidence:     totalDraws > 0
        ? parseFloat(((topCount / totalDraws) * 100).toFixed(1))
        : 0,
      prizeHistory: history,
    });
  }
  return map;
}

// Normalized profile helpers (for cycle 6 model)
function buildNormalizedProfiles(cycles) {
  const profiles = new Map();
  for (const cycle of cycles) {
    const cycleDays = cycle.totalDrawDays;
    const firstSeen = new Map();
    const countSeen = new Map();
    const metaFirst = new Map();
    for (const dayEntry of cycle.drawEntries) {
      for (const { number, prize, isNew } of dayEntry.numbers) {
        if (!firstSeen.has(number)) {
          firstSeen.set(number, dayEntry.dayIndexInCycle);
          metaFirst.set(number, { prize, dow: dayEntry.dayOfWeek });
        }
        countSeen.set(number, (countSeen.get(number) || 0) + 1);
      }
    }
    for (const [number, firstDay] of firstSeen) {
      if (!profiles.has(number)) profiles.set(number, []);
      const meta = metaFirst.get(number);
      profiles.get(number).push({
        cycleNumber:  cycle.cycleNumber,
        normFirstDay: cycleDays > 0 ? firstDay / cycleDays : 0,
        appearances:  countSeen.get(number) || 1,
        prize:        meta.prize,
        dow:          meta.dow,
        isComplete:   cycle.isComplete,
      });
    }
  }
  return profiles;
}

function buildNormStatsMap(profiles, trainCycles) {
  const trainNums = new Set(trainCycles.map((c) => c.cycleNumber));
  const map = new Map();
  for (const [number, history] of profiles) {
    const used = history.filter((h) => h.isComplete && trainNums.has(h.cycleNumber));
    if (used.length === 0) continue;
    const norms  = used.map((h) => h.normFirstDay);
    const avgN   = norms.reduce((a, b) => a + b, 0) / norms.length;
    const varN   = norms.reduce((s, d) => s + (d - avgN) ** 2, 0) / norms.length;
    const stdN   = Math.sqrt(varN);
    const avgApp = used.map((h) => h.appearances).reduce((a, b) => a + b, 0) / used.length;
    const prizeFreq = {};
    used.forEach((h) => { prizeFreq[h.prize] = (prizeFreq[h.prize] || 0) + 1; });
    const topPrize = Object.entries(prizeFreq).sort((a, b) => b[1] - a[1])[0]?.[0];
    const dowFreq  = {};
    used.forEach((h) => { if (h.dow) dowFreq[h.dow] = (dowFreq[h.dow] || 0) + 1; });
    const topDOW = Object.entries(dowFreq).sort((a, b) => b[1] - a[1])[0]?.[0];
    map.set(number, {
      number,
      avgNormFirstDay:  parseFloat(avgN.toFixed(5)),
      stdNormFirstDay:  parseFloat(stdN.toFixed(5)),
      avgAppearances:   parseFloat(avgApp.toFixed(2)),
      appearedInCycles: used.length,
      predictedPrize:   topPrize ? Number(topPrize) : null,
      preferredDOW:     topDOW,
      prizeHistory:     prizeFreq,
    });
  }
  return map;
}

function buildNormScoringModel(normMap, totalCycles, maxApp) {
  const W1 = 2.5, W2 = 1.5, W3 = 0.8, W4 = 0.3;
  return [...normMap.values()]
    .map((s) => ({
      number:          s.number,
      score:           parseFloat((
        Math.pow(1 - s.avgNormFirstDay, W1) *
        Math.pow(1 / (s.stdNormFirstDay + 0.01), W2) *
        (maxApp > 0 ? Math.pow(s.avgAppearances / maxApp, W3) : 0) *
        Math.pow(s.appearedInCycles / totalCycles, W4)
      ).toFixed(8)),
      avgNormFirstDay: s.avgNormFirstDay,
      stdNormFirstDay: s.stdNormFirstDay,
      avgAppearances:  s.avgAppearances,
      predictedPrize:  s.predictedPrize,
      preferredDOW:    s.preferredDOW,
    }))
    .sort((a, b) => b.score - a.score);
}

// ─────────────────────────────────────────────────────
// STARTUP
// ─────────────────────────────────────────────────────
async function start() {
  const dbUri = process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid";
  await mongoose.connect(dbUri);
  console.log("✅ Connected to MongoDB");

  await buildState();

  app.listen(PORT, () => {
    console.log(`\n🚀 Analysis API running on port ${PORT}`);
    console.log(`\n   Endpoints:`);
    console.log(`   GET  /status                  — system status`);
    console.log(`   GET  /remaining               — guaranteed 53 numbers`);
    console.log(`   GET  /predict/tomorrow        — tomorrow's prediction`);
    console.log(`   GET  /predict/cycle6          — cycle 6 predictions`);
    console.log(`   GET  /prize/:number           — prize prediction for one number`);
    console.log(`   GET  /prize/summary           — all prize predictions`);
    console.log(`   GET  /number/:number          — full profile for one number`);
    console.log(`   GET  /cycle/status            — cycle transition status`);
    console.log(`   GET  /numbers/search          — filter by prize/confidence`);
    console.log(`   POST /refresh                 — rebuild after new draw added`);
  });
}

start().catch((err) => {
  console.error("❌ Startup failed:", err);
  process.exit(1);
});