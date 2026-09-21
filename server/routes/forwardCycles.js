const express = require("express");
const router = express.Router();
const FullLotteryData = require("../models/FullLotteryData");

// ============================================================
// CONSTANTS
// ============================================================
const TOTAL_NUMBERS = 10000;
const WEEKDAY_NAMES = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

// ============================================================
// HELPER: Parse DD/MM/YYYY → Date object
// ============================================================
const parseDate = (dateStr) => {
  if (!dateStr) return null;
  const [dd, mm, yyyy] = dateStr.split("/");
  if (!dd || !mm || !yyyy) return null;
  return new Date(`${yyyy}-${mm}-${dd}`);
};

// ============================================================
// HELPER: Format Date → YYYY-MM-DD
// ============================================================
const formatDate = (date) => {
  if (!date) return null;
  if (date instanceof Date) return date.toISOString().split("T")[0];
  return null;
};

// ============================================================
// HELPER: Get weekday name and index
// ============================================================
const getWeekdayInfo = (dateStr) => {
  const date = parseDate(dateStr);
  if (!date) return { name: "Unknown", index: -1 };
  const dayIndex = date.getDay();
  return {
    name: WEEKDAY_NAMES[dayIndex],
    index: dayIndex,
    date: formatDate(date),
  };
};

// ============================================================
// HELPER: Extract serial prefix (letters from start until first digit)
// ============================================================
const extractSerialPrefix = (serial) => {
  if (!serial) return "Unknown";

  // Extract letters from start until first digit
  const match = serial.match(/^([A-Za-z]+)/);
  if (match && match[1]) {
    return match[1].toUpperCase();
  }

  // If no letters found, use first 2 characters
  return serial.substring(0, 2).toUpperCase();
};

// ============================================================
// HELPER: Extract all 4-digit numbers from a draw
// ============================================================
const extractDrawNumbers = (draw, seenNumbers) => {
  const drawNumbers = [];
  const newNumbersList = [];

  if (!draw.series || !Array.isArray(draw.series)) {
    return { drawNumbers, newNumbersList, newCount: 0 };
  }

  for (const serie of draw.series) {
    if (!serie.numbers || !Array.isArray(serie.numbers)) continue;

    for (const numObj of serie.numbers) {
      const num = String(numObj.number || "")
        .trim()
        .padStart(4, "0");
      if (!/^\d{4}$/.test(num)) continue;

      drawNumbers.push(num);

      if (!seenNumbers.has(num)) {
        seenNumbers.add(num);
        newNumbersList.push(num);
      }
    }
  }

  return {
    drawNumbers: drawNumbers.sort((a, b) => a.localeCompare(b)),
    newNumbersList: newNumbersList.sort((a, b) => a.localeCompare(b)),
    newCount: newNumbersList.length,
  };
};

// ============================================================
// HELPER: Build draw record
// ============================================================
const buildDrawRecord = (
  draw,
  drawNumbers,
  newNumbersList,
  seenCount,
  drawIndex,
) => ({
  drawIndex,
  date: draw.date,
  drawDate: formatDate(draw.drawDate),
  weekdayInfo: getWeekdayInfo(draw.date),
  serialNumber: draw.serialNumber,
  serialPrefix: extractSerialPrefix(draw.serialNumber),
  fileName: draw.fileName || "",
  recordNumber: draw.recordNumber,
  newNums: newNumbersList.length,
  newNumbersList,
  allNumbers: drawNumbers,
  seenCount,
  remainingCount: TOTAL_NUMBERS - seenCount,
  totalSeen: TOTAL_NUMBERS,
  progress: parseFloat(((seenCount / TOTAL_NUMBERS) * 100).toFixed(2)),
});

// ============================================================
// HELPER: Build distribution stats
// ============================================================
const buildDistribution = (cycleDraws) => {
  const dist = {
    zero: 0,
    one: 0,
    two: 0,
    threeToFive: 0,
    sixToTen: 0,
    elevenToTwenty: 0,
    twentyOneToFifty: 0,
    fiftyOneToHundred: 0,
    gtHundred: 0,
    gtTwoHundred: 0,
  };

  for (const d of cycleDraws) {
    const n = d.newNums;
    if (n === 0) dist.zero++;
    else if (n === 1) dist.one++;
    else if (n === 2) dist.two++;
    else if (n <= 5) dist.threeToFive++;
    else if (n <= 10) dist.sixToTen++;
    else if (n <= 20) dist.elevenToTwenty++;
    else if (n <= 50) dist.twentyOneToFifty++;
    else if (n <= 100) dist.fiftyOneToHundred++;
    else dist.gtHundred++;

    if (n > 200) dist.gtTwoHundred++;
  }

  const head50 = cycleDraws.slice(0, 50);
  const tail50 = cycleDraws.slice(-50);

  dist.headAvg = head50.length
    ? parseFloat(
        (head50.reduce((s, d) => s + d.newNums, 0) / head50.length).toFixed(2),
      )
    : 0;

  dist.tailAvg = tail50.length
    ? parseFloat(
        (tail50.reduce((s, d) => s + d.newNums, 0) / tail50.length).toFixed(2),
      )
    : 0;

  return dist;
};

// ============================================================
// HELPER: Get remaining numbers
// ============================================================
const getRemainingNumbers = (seenNumbers) => {
  const remaining = [];
  for (let i = 0; i < TOTAL_NUMBERS; i++) {
    const num = String(i).padStart(4, "0");
    if (!seenNumbers.has(num)) {
      remaining.push(num);
    }
  }
  return remaining.sort((a, b) => a.localeCompare(b));
};

// ============================================================
// HELPER: Build completed cycle
// ============================================================
const buildCompletedCycle = (cycleIndex, cycleDraws) => {
  const firstDraw = cycleDraws[0];
  const lastDraw = cycleDraws[cycleDraws.length - 1];

  const distribution = buildDistribution(cycleDraws);
  const avgNewPerDay = parseFloat(
    (TOTAL_NUMBERS / cycleDraws.length).toFixed(2),
  );

  const lastNewNumber =
    lastDraw.newNumbersList && lastDraw.newNumbersList.length > 0
      ? lastDraw.newNumbersList[lastDraw.newNumbersList.length - 1]
      : null;

  let maxConsecutiveZero = 0;
  let currentConsecutiveZero = 0;
  for (const d of cycleDraws) {
    if (d.newNums === 0) {
      currentConsecutiveZero++;
      maxConsecutiveZero = Math.max(maxConsecutiveZero, currentConsecutiveZero);
    } else {
      currentConsecutiveZero = 0;
    }
  }

  const maxNewInDraw = Math.max(...cycleDraws.map((d) => d.newNums));
  const maxNewDrawIndex = cycleDraws.findIndex(
    (d) => d.newNums === maxNewInDraw,
  );

  return {
    cycle: cycleIndex,
    status: "complete",
    draws: cycleDraws.length,
    start: firstDraw.drawDate,
    end: lastDraw.drawDate,
    startDisplayDate: firstDraw.date,
    endDisplayDate: lastDraw.date,
    startSerial: firstDraw.serialNumber,
    endSerial: lastDraw.serialNumber,
    startRecord: firstDraw.recordNumber,
    endRecord: lastDraw.recordNumber,
    avgNewPerDay,
    lastNumber: lastNewNumber,
    lastNumberDate: lastDraw.drawDate,
    lastNumberDisplayDate: lastDraw.date,
    distribution,
    totalSeen: TOTAL_NUMBERS,
    maxConsecutiveZero,
    maxNewInDraw,
    maxNewDrawDate: cycleDraws[maxNewDrawIndex]?.drawDate,
    first5: cycleDraws.slice(0, 5),
    last5: cycleDraws.slice(-5),
    last30: cycleDraws.slice(-30),
    allDraws: cycleDraws,
  };
};

// ============================================================
// HELPER: Build partial cycle
// ============================================================
const buildPartialCycle = (
  cycleIndex,
  cycleDraws,
  seenCount,
  remainingNumbers,
) => {
  const firstDraw = cycleDraws[0];
  const lastDraw = cycleDraws[cycleDraws.length - 1];
  const seenPct = parseFloat(((seenCount / TOTAL_NUMBERS) * 100).toFixed(2));

  return {
    cycle: cycleIndex,
    status: "partial",
    draws: cycleDraws.length,
    start: firstDraw.drawDate,
    end: lastDraw.drawDate,
    startDisplayDate: firstDraw.date,
    endDisplayDate: lastDraw.date,
    startSerial: firstDraw.serialNumber,
    endSerial: lastDraw.serialNumber,
    startRecord: firstDraw.recordNumber,
    endRecord: lastDraw.recordNumber,
    avgNewPerDay: parseFloat((seenCount / cycleDraws.length).toFixed(2)),
    seenSoFar: `${seenCount}/${TOTAL_NUMBERS}`,
    seenCount,
    seenPct,
    remainingCount: TOTAL_NUMBERS - seenCount,
    remainingNumbers,
    distribution: null,
    first5: cycleDraws.slice(0, 5),
    last5: cycleDraws.slice(-5),
    last30: cycleDraws.slice(-30),
    allDraws: cycleDraws,
  };
};

// ============================================================
// MAIN PROCESSING ENGINE - FORWARD (oldest → newest)
// ============================================================
const processForwardCycles = (allDraws) => {
  const seenNumbers = new Set();
  const cycles = [];
  let currentCycle = [];
  let cycleIndex = 1;
  let drawIndex = 0;

  for (const draw of allDraws) {
    const { drawNumbers, newNumbersList } = extractDrawNumbers(
      draw,
      seenNumbers,
    );

    const record = buildDrawRecord(
      draw,
      drawNumbers,
      newNumbersList,
      seenNumbers.size,
      drawIndex++,
    );

    currentCycle.push(record);

    if (seenNumbers.size >= TOTAL_NUMBERS) {
      cycles.push(buildCompletedCycle(cycleIndex, currentCycle));

      seenNumbers.clear();
      currentCycle = [];
      cycleIndex++;
    }
  }

  if (currentCycle.length > 0) {
    const remainingNumbers = getRemainingNumbers(seenNumbers);
    cycles.push(
      buildPartialCycle(
        cycleIndex,
        currentCycle,
        seenNumbers.size,
        remainingNumbers,
      ),
    );
  }

  return cycles;
};

// ============================================================
// GET /api/forward-cycles
// All forward cycles summary
// ============================================================
router.get("/", async (req, res) => {
  try {
    const allDraws = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    if (!allDraws.length) {
      return res.json({
        success: false,
        message: "No draws found",
      });
    }

    const cycles = processForwardCycles(allDraws);

    const validDates = allDraws.map((d) => d.drawDate).filter(Boolean);
    const oldestDate = validDates[0];
    const newestDate = validDates[validDates.length - 1];

    return res.json({
      success: true,
      summary: {
        totalDraws: allDraws.length,
        totalCycles: cycles.length,
        completeCycles: cycles.filter((c) => c.status === "complete").length,
        partialCycles: cycles.filter((c) => c.status === "partial").length,
        dateRange: {
          oldest: formatDate(oldestDate),
          newest: formatDate(newestDate),
        },
      },
      cycles: cycles.map((c) => ({
        cycle: c.cycle,
        status: c.status,
        draws: c.draws,
        start: c.start,
        end: c.end,
        startDisplayDate: c.startDisplayDate,
        endDisplayDate: c.endDisplayDate,
        avgNewPerDay: c.avgNewPerDay,
        distribution: c.distribution,
        seenCount: c.seenCount,
        seenPct: c.seenPct,
        lastNumber: c.lastNumber,
        maxNewInDraw: c.maxNewInDraw,
      })),
    });
  } catch (err) {
    console.error("❌ Forward cycle error:", err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

// ============================================================
// GET /api/forward-cycles/:cycleNumber
// Complete detailed data for a specific forward cycle
// ============================================================
router.get("/:cycleNumber", async (req, res) => {
  try {
    const targetCycle = parseInt(req.params.cycleNumber, 10);

    if (isNaN(targetCycle) || targetCycle < 1) {
      return res.status(400).json({
        success: false,
        message: "Invalid cycle number",
      });
    }

    const allDraws = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    if (!allDraws.length) {
      return res
        .status(404)
        .json({ success: false, message: "No draws found" });
    }

    const seenNumbers = new Set();
    let currentCycle = [];
    let cycleIndex = 1;
    let drawIndex = 0;

    for (const draw of allDraws) {
      const { drawNumbers, newNumbersList } = extractDrawNumbers(
        draw,
        seenNumbers,
      );

      const record = buildDrawRecord(
        draw,
        drawNumbers,
        newNumbersList,
        seenNumbers.size,
        drawIndex++,
      );

      currentCycle.push(record);

      if (seenNumbers.size >= TOTAL_NUMBERS) {
        if (cycleIndex === targetCycle) {
          const cycleData = buildCompletedCycle(cycleIndex, currentCycle);
          return res.json({
            success: true,
            cycle: cycleData,
          });
        }

        seenNumbers.clear();
        currentCycle = [];
        cycleIndex++;
      }
    }

    if (cycleIndex === targetCycle && currentCycle.length > 0) {
      const remainingNumbers = getRemainingNumbers(seenNumbers);
      const cycleData = buildPartialCycle(
        cycleIndex,
        currentCycle,
        seenNumbers.size,
        remainingNumbers,
      );
      return res.json({
        success: true,
        cycle: cycleData,
      });
    }

    return res.status(404).json({
      success: false,
      message: `Cycle ${targetCycle} not found`,
    });
  } catch (err) {
    console.error("❌ Forward cycle detail error:", err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

// ============================================================
// GET /api/forward-cycles/:cycleNumber/by-weekday
// Numbers grouped by weekday + identify missing days
// ============================================================
router.get("/:cycleNumber/by-weekday", async (req, res) => {
  try {
    const targetCycle = parseInt(req.params.cycleNumber, 10);

    if (isNaN(targetCycle) || targetCycle < 1) {
      return res
        .status(400)
        .json({ success: false, message: "Invalid cycle number" });
    }

    const allDraws = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    if (!allDraws.length) {
      return res
        .status(404)
        .json({ success: false, message: "No draws found" });
    }

    const seenNumbers = new Set();
    let currentCycle = [];
    let cycleIndex = 1;
    let drawIndex = 0;

    for (const draw of allDraws) {
      const { drawNumbers, newNumbersList } = extractDrawNumbers(
        draw,
        seenNumbers,
      );

      const record = buildDrawRecord(
        draw,
        drawNumbers,
        newNumbersList,
        seenNumbers.size,
        drawIndex++,
      );

      currentCycle.push(record);

      if (seenNumbers.size >= TOTAL_NUMBERS) {
        if (cycleIndex === targetCycle) {
          // Group by weekday
          const weekdayGroups = {};
          WEEKDAY_NAMES.forEach((day) => {
            weekdayGroups[day] = {
              name: day,
              totalNumbers: 0,
              totalDraws: 0,
              draws: [],
              allNumbers: new Set(),
              dates: new Set(), // Track all dates for this weekday
            };
          });

          // Process all draws in cycle
          for (const d of currentCycle) {
            const day = d.weekdayInfo.name;
            weekdayGroups[day].totalNumbers += d.newNums;
            weekdayGroups[day].totalDraws++;
            weekdayGroups[day].draws.push({
              date: d.date,
              drawDate: d.drawDate,
              serialNumber: d.serialNumber,
              newNums: d.newNums,
              numbers: d.newNumbersList,
            });

            weekdayGroups[day].dates.add(d.drawDate);

            for (const num of d.newNumbersList) {
              weekdayGroups[day].allNumbers.add(num);
            }
          }

          // Convert to array and sort by day index
          const weekdayStats = WEEKDAY_NAMES.map((day) => ({
            day,
            totalDraws: weekdayGroups[day].totalDraws,
            totalNumbersAdded: weekdayGroups[day].totalNumbers,
            averagePerDraw:
              weekdayGroups[day].totalDraws > 0
                ? parseFloat(
                    (
                      weekdayGroups[day].totalNumbers /
                      weekdayGroups[day].totalDraws
                    ).toFixed(2),
                  )
                : 0,
            uniqueNumbers: Array.from(weekdayGroups[day].allNumbers).sort(
              (a, b) => a.localeCompare(b),
            ),
            dates: Array.from(weekdayGroups[day].dates).sort(),
            draws: weekdayGroups[day].draws,
          }));

          // Find missing dates by comparing with full date range
          const allDatesInCycle = currentCycle.map((d) => d.drawDate).sort();
          const startDate = allDatesInCycle[0];
          const endDate = allDatesInCycle[allDatesInCycle.length - 1];

          if (startDate && endDate) {
            const start = new Date(startDate);
            const end = new Date(endDate);
            const missingDays = {};

            // Generate all dates in range and check which weekdays are missing
            const currentDate = new Date(start);
            while (currentDate <= end) {
              const dateString = formatDate(currentDate);
              const dayInfo = getWeekdayInfo(dateString);

              // Check if this date exists in our cycle
              const dateExists = allDatesInCycle.includes(dateString);

              if (!dateExists) {
                if (!missingDays[dayInfo.name]) {
                  missingDays[dayInfo.name] = [];
                }
                missingDays[dayInfo.name].push(dateString);
              }

              currentDate.setDate(currentDate.getDate() + 1);
            }

            // Add missing days info to response
            Object.keys(missingDays).forEach((day) => {
              const stat = weekdayStats.find((s) => s.day === day);
              if (stat) {
                stat.missingDates = missingDays[day].sort();
              }
            });
          }

          return res.json({
            success: true,
            cycle: cycleIndex,
            weekdayStats,
            cycleDateRange: {
              start: startDate,
              end: endDate,
              totalDays: allDatesInCycle.length,
            },
          });
        }

        seenNumbers.clear();
        currentCycle = [];
        cycleIndex++;
      }
    }

    return res
      .status(404)
      .json({ success: false, message: `Cycle ${targetCycle} not found` });
  } catch (err) {
    console.error("❌ Weekday analysis error:", err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

// ============================================================
// GET /api/forward-cycles/:cycleNumber/by-serial
// Numbers grouped by serial number prefixes with combined lists
// ============================================================
router.get("/:cycleNumber/by-serial", async (req, res) => {
  try {
    const targetCycle = parseInt(req.params.cycleNumber, 10);

    if (isNaN(targetCycle) || targetCycle < 1) {
      return res
        .status(400)
        .json({ success: false, message: "Invalid cycle number" });
    }

    const allDraws = await FullLotteryData.find({})
      .sort({ drawDate: 1, recordNumber: 1 })
      .lean();

    if (!allDraws.length) {
      return res
        .status(404)
        .json({ success: false, message: "No draws found" });
    }

    const seenNumbers = new Set();
    let currentCycle = [];
    let cycleIndex = 1;
    let drawIndex = 0;

    for (const draw of allDraws) {
      const { drawNumbers, newNumbersList } = extractDrawNumbers(
        draw,
        seenNumbers,
      );

      const record = buildDrawRecord(
        draw,
        drawNumbers,
        newNumbersList,
        seenNumbers.size,
        drawIndex++,
      );

      currentCycle.push(record);

      if (seenNumbers.size >= TOTAL_NUMBERS) {
        if (cycleIndex === targetCycle) {
          // Group by serial prefix
          const serialGroups = {};

          for (const d of currentCycle) {
            const prefix = d.serialPrefix;
            if (!serialGroups[prefix]) {
              serialGroups[prefix] = {
                prefix,
                totalNumbers: 0,
                count: 0,
                records: [],
                numbers: new Set(),
                serialNumbers: new Set(),
              };
            }

            serialGroups[prefix].totalNumbers += d.newNums;
            serialGroups[prefix].count++;
            serialGroups[prefix].records.push({
              date: d.date,
              drawDate: d.drawDate,
              serialNumber: d.serialNumber,
              newNums: d.newNums,
              numbers: d.newNumbersList,
            });

            for (const num of d.newNumbersList) {
              serialGroups[prefix].numbers.add(num);
            }

            serialGroups[prefix].serialNumbers.add(d.serialNumber);
          }

          // Convert to array and sort by total numbers descending
          const serialStats = Object.values(serialGroups)
            .sort((a, b) => b.totalNumbers - a.totalNumbers)
            .map((group) => ({
              prefix: group.prefix,
              count: group.count,
              totalNumbersAdded: group.totalNumbers,
              averagePerDraw: parseFloat(
                (group.totalNumbers / group.count).toFixed(2),
              ),
              uniqueNumbers: Array.from(group.numbers).sort((a, b) =>
                a.localeCompare(b),
              ),
              serialNumbers: Array.from(group.serialNumbers).sort(),
              records: group.records,
            }));

          return res.json({
            success: true,
            cycle: cycleIndex,
            serialStats,
          });
        }

        seenNumbers.clear();
        currentCycle = [];
        cycleIndex++;
      }
    }

    return res
      .status(404)
      .json({ success: false, message: `Cycle ${targetCycle} not found` });
  } catch (err) {
    console.error("❌ Serial analysis error:", err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;
