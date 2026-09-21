const { extractNumbers, getDayLabel } = require("./utils");

/**
 * Correct cycle detection:
 * A cycle ends ONLY when all 10,000 numbers (0000-9999) have appeared
 * at least once. Numbers CAN repeat within a cycle (hot numbers),
 * but the cycle only closes when full coverage is achieved.
 */
function detectCycles(draws) {
  const cycles = [];
  let seenInCycle = new Set();
  let currentCycle = newCycle(1);
  currentCycle.startDate = draws[0]?.drawDate;
  currentCycle.startDrawIndex = 0;

  for (let drawIndex = 0; drawIndex < draws.length; drawIndex++) {
    const draw = draws[drawIndex];
    const drawDate = draw.drawDate || draw.date;
    const dayLabel = getDayLabel(new Date(drawDate));
    const numbersInDraw = extractNumbers(draw);

    const dayEntry = {
      dayIndexInCycle: currentCycle.drawEntries.length + 1,
      serialNumber: draw.serialNumber,
      recordNumber: draw.recordNumber,
      drawDate,
      dayOfWeek: dayLabel,
      numbers: [],
      numberCount: numbersInDraw.length,
      newNumbersAdded: 0, // numbers not yet seen in this cycle
    };

    for (const { number, prize } of numbersInDraw) {
      const isNew = !seenInCycle.has(number);
      if (isNew) {
        seenInCycle.add(number);
        dayEntry.newNumbersAdded++;
      }
      dayEntry.numbers.push({ number, prize, isNew });
    }

    currentCycle.drawEntries.push(dayEntry);
    currentCycle.totalNumbersDrawn = seenInCycle.size;

    // ── Cycle complete: all 10,000 unique numbers have been seen ──
    if (seenInCycle.size === 10000) {
      currentCycle.endDate = drawDate;
      currentCycle.endDrawIndex = drawIndex;
      currentCycle.totalDrawDays = currentCycle.drawEntries.length;
      currentCycle.isComplete = true;
      currentCycle.remainingNumbers = 0;
      cycles.push(currentCycle);

      // Start new cycle from next draw
      seenInCycle = new Set();
      const nextDraw = draws[drawIndex + 1];
      currentCycle = newCycle(cycles.length + 1);
      currentCycle.startDate = nextDraw?.drawDate || drawDate;
      currentCycle.startDrawIndex = drawIndex + 1;
    }
  }

  // Push the final incomplete cycle (cycle 5)
  if (currentCycle.drawEntries.length > 0) {
    currentCycle.endDate = draws[draws.length - 1]?.drawDate;
    currentCycle.endDrawIndex = draws.length - 1;
    currentCycle.totalDrawDays = currentCycle.drawEntries.length;
    currentCycle.totalNumbersDrawn = seenInCycle.size;
    currentCycle.isComplete = false;
    currentCycle.remainingNumbers = 10000 - seenInCycle.size;
    cycles.push(currentCycle);
  }

  return cycles;
}

function newCycle(number) {
  return {
    cycleNumber: number,
    startDate: null,
    endDate: null,
    startDrawIndex: 0,
    endDrawIndex: null,
    totalDrawDays: 0,
    totalNumbersDrawn: 0,
    isComplete: true,
    remainingNumbers: 0,
    drawEntries: [],
  };
}

function printCycleSummary(cycles) {
  console.log("\n========== CYCLE SUMMARY ==========");
  console.log(
    "Cycle | Start Date | End Date   | Draw Days | Numbers Drawn | Remaining | Complete"
  );
  console.log("-".repeat(92));
  for (const c of cycles) {
    const start = c.startDate
      ? new Date(c.startDate).toISOString().split("T")[0]
      : "N/A";
    const end = c.endDate
      ? new Date(c.endDate).toISOString().split("T")[0]
      : "ongoing";
    console.log(
      `  ${String(c.cycleNumber).padEnd(4)} | ${start} | ${String(end).padEnd(10)} | ` +
        `${String(c.totalDrawDays).padEnd(9)} | ${String(c.totalNumbersDrawn).padEnd(13)} | ` +
        `${String(c.remainingNumbers).padEnd(9)} | ${c.isComplete ? "YES" : "IN PROGRESS"}`
    );
  }
  console.log("====================================\n");
}

function printDrawSizeStats(cycles) {
  console.log("\n========== DRAW SIZE + NEW NUMBERS PER DAY (per cycle) ==========");
  for (const c of cycles) {
    const sizes = c.drawEntries.map((d) => d.numberCount);
    const newPerDay = c.drawEntries.map((d) => d.newNumbersAdded);
    const minSize = Math.min(...sizes);
    const maxSize = Math.max(...sizes);
    const avgSize = (sizes.reduce((a, b) => a + b, 0) / sizes.length).toFixed(1);
    const totalNew = newPerDay.reduce((a, b) => a + b, 0);
    const avgNew = (totalNew / newPerDay.length).toFixed(1);
    console.log(
      `Cycle ${String(c.cycleNumber).padEnd(2)}: ` +
        `drawSize min=${String(minSize).padEnd(4)} max=${String(maxSize).padEnd(4)} avg=${String(avgSize).padEnd(6)} | ` +
        `newNums/day avg=${String(avgNew).padEnd(6)} | ` +
        `days=${c.totalDrawDays} | ` +
        `${c.isComplete ? "complete" : "IN PROGRESS"}`
    );
  }
  console.log("=================================================================\n");
}

module.exports = { detectCycles, printCycleSummary, printDrawSizeStats };