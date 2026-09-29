// utils/cycleCompare.js
// Shared helpers + cycle builders for Type1 (Daily) and Type2 (Prize) cycles

const TOTAL_UNIVERSE = 10000;

function parseDateDDMMYYYY(str) {
  if (!str || str === "Unknown") return null;
  const m = String(str).trim().match(/^(\d{1,2})\s*[\/\-\.]\s*(\d{1,2})\s*[\/\-\.]\s*(\d{2,4})$/);
  if (!m) return null;

  const dd = parseInt(m[1], 10);
  const mm = parseInt(m[2], 10);
  let yy = parseInt(m[3], 10);
  if (yy < 100) yy += 2000;

  const t = Date.UTC(yy, mm - 1, dd);
  const d = new Date(t);

  if (d.getUTCFullYear() !== yy || d.getUTCMonth() !== mm - 1 || d.getUTCDate() !== dd) {
    return null;
  }

  const key = String(dd).padStart(2, "0") + "/" + String(mm).padStart(2, "0") + "/" + String(yy);
  return { key, time: t };
}

function isValid4Digit(s) {
  return /^\d{4}$/.test(String(s || "").trim());
}

function pad4(n) {
  return String(n).padStart(4, "0");
}

function allNumbersSet() {
  const s = new Set();
  for (let i = 0; i < TOTAL_UNIVERSE; i++) s.add(pad4(i));
  return s;
}

function getRemainingArray(seenSet) {
  const all = allNumbersSet();
  const remaining = [];
  for (const n of all) {
    if (!seenSet.has(n)) remaining.push(n);
  }
  return remaining;
}

/**
 * Builds cycles for a dateMap (dateKey -> Set<number>)
 * Returns { completedCycles: [...], currentCycle: {...}, dailyProgress: [...] }
 */
function buildCyclesFromDateMap(dateMap, dateTimeMap) {
  const sortedDates = Array.from(dateMap.keys()).sort(
    (a, b) => (dateTimeMap.get(a) || 0) - (dateTimeMap.get(b) || 0)
  );

  const cycles = [];
  let cycleIdx = 1;
  let cycleStartDate = null;
  let cycleSet = new Set();
  let cycleDayCount = 0;

  const dailyProgress = [];

  for (const dateStr of sortedDates) {
    if (cycleStartDate === null) {
      cycleStartDate = dateStr;
      cycleDayCount = 0;
    }

    cycleDayCount++;
    const dayNums = dateMap.get(dateStr) || new Set();

    let addedToday = 0;
    for (const n of dayNums) {
      if (!cycleSet.has(n)) {
        cycleSet.add(n);
        addedToday++;
      }
    }

    dailyProgress.push({
      date: dateStr,
      cycle: cycleIdx,
      uniqueCount: cycleSet.size,
      remaining: TOTAL_UNIVERSE - cycleSet.size,
      dayInCycle: cycleDayCount,
      addedToday,
    });

    if (cycleSet.size >= TOTAL_UNIVERSE) {
      cycles.push({
        cycle: cycleIdx,
        startDate: cycleStartDate,
        endDate: dateStr,
        totalDays: cycleDayCount,
        completed: true,
      });
      cycleIdx++;
      cycleStartDate = null;
      cycleSet = new Set();
      cycleDayCount = 0;
    }
  }

  // Current incomplete cycle
  const remaining = getRemainingArray(cycleSet);

  const currentCycle = {
    cycle: cycleIdx,
    startDate: cycleStartDate,
    lastDate: sortedDates.length > 0 ? sortedDates[sortedDates.length - 1] : null,
    totalDaysSoFar: cycleDayCount,
    presentCount: cycleSet.size,
    remainingCount: remaining.length,
    remainingNumbers: remaining,
    completed: false,
  };

  return { completedCycles: cycles, currentCycle, dailyProgress };
}

/**
 * Load docs and build date maps for Type1 (daily all-prizes) and Type2 (per-prize)
 */
async function loadAndBuildCycleMaps(Model) {
  const docs = await Model.find({}, { date: 1, series: 1 }).lean();

  // Type 1: Daily (all prizes combined)
  const dailyDateMap = new Map();
  const dailyDateTimeMap = new Map();

  // Type 2: Prize -> dateMap
  const prizeMap = new Map(); // prize -> Map(dateStr -> Set<number>)
  const prizeDateTimeMap = new Map(); // prize -> Map(dateStr -> time)

  for (const doc of docs) {
    const parsed = parseDateDDMMYYYY(doc.date);
    if (!parsed) continue;

    const dateStr = parsed.key;
    const dateTime = parsed.time;

    // Daily
    if (!dailyDateMap.has(dateStr)) dailyDateMap.set(dateStr, new Set());
    if (!dailyDateTimeMap.has(dateStr)) dailyDateTimeMap.set(dateStr, dateTime);

    for (const series of doc.series || []) {
      const prize = Number(series.prize);
      if (isNaN(prize)) continue;

      const dailySet = dailyDateMap.get(dateStr);

      // Prize map init
      if (!prizeMap.has(prize)) {
        prizeMap.set(prize, new Map());
        prizeDateTimeMap.set(prize, new Map());
      }
      const pDateMap = prizeMap.get(prize);
      const pTimeMap = prizeDateTimeMap.get(prize);

      if (!pDateMap.has(dateStr)) pDateMap.set(dateStr, new Set());
      if (!pTimeMap.has(dateStr)) pTimeMap.set(dateStr, dateTime);

      const pDaySet = pDateMap.get(dateStr);

      for (const item of series.numbers || []) {
        const num = String(item.number || "").trim();
        if (isValid4Digit(num)) {
          const n4 = num.padStart(4, "0");
          dailySet.add(n4);
          pDaySet.add(n4);
        }
      }
    }
  }

  return { dailyDateMap, dailyDateTimeMap, prizeMap, prizeDateTimeMap };
}

module.exports = {
  TOTAL_UNIVERSE,
  parseDateDDMMYYYY,
  isValid4Digit,
  pad4,
  allNumbersSet,
  getRemainingArray,
  buildCyclesFromDateMap,
  loadAndBuildCycleMaps,
};