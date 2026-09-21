// utils/cycleAnalysis.js

function generateAll4DigitNumbers() {
  return Array.from({ length: 10000 }, (_, i) => String(i).padStart(4, "0"));
}

function parseDDMMYYYYToDate(dateStr = "") {
  const match = String(dateStr).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  return new Date(Date.UTC(year, month - 1, day));
}

function extractUniqueNumbersFromDoc(doc) {
  const set = new Set();

  for (const series of doc.series || []) {
    for (const item of series.numbers || []) {
      const number = String(item.number || "").trim();
      if (/^\d{4}$/.test(number)) set.add(number);
    }
  }
  return set;
}

function sortDocsChronologically(docs = []) {
  return [...docs].sort((a, b) => {
    const dateA = a.drawDate
      ? new Date(a.drawDate)
      : parseDDMMYYYYToDate(a.date || "");
    const dateB = b.drawDate
      ? new Date(b.drawDate)
      : parseDDMMYYYYToDate(b.date || "");

    if (dateA && dateB && dateA.getTime() !== dateB.getTime()) return dateA - dateB;

    const numA = a.recordNumber ?? a.entryNumber ?? 0;
    const numB = b.recordNumber ?? b.entryNumber ?? 0;
    if (numA !== numB) return numA - numB;

    return String(a.serialNumber || "").localeCompare(String(b.serialNumber || ""));
  });
}

function buildCycleAnalysisByDay(docs = [], options = {}) {
  const TOTAL_NUMBERS = 10000;
  const ALL_NUMBERS = generateAll4DigitNumbers();

  const sortedDocs = sortDocsChronologically(docs);

  const docsByDay = new Map();
  for (const doc of sortedDocs) {
    const dayKey = doc.date || "";
    if (!dayKey) continue;
    if (!docsByDay.has(dayKey)) docsByDay.set(dayKey, []);
    docsByDay.get(dayKey).push(doc);
  }

  const dayKeys = Array.from(docsByDay.keys()).sort((a, b) => {
    const da = parseDDMMYYYYToDate(a);
    const db = parseDDMMYYYYToDate(b);
    if (!da || !db) return a.localeCompare(b);
    return da - db;
  });

  const cycles = [];

  let cycleNumber = 1;
  let seenInCycle = new Set();
  let firstSeenMap = new Map();

  let cycleStartDayKey = null;
  let cycleStartMeta = null;

  let dailyTimeline = [];

  for (const dayKey of dayKeys) {
    const dayDocs = docsByDay.get(dayKey);

    const daySet = new Set();
    for (const doc of dayDocs) {
      for (const n of extractUniqueNumbersFromDoc(doc)) daySet.add(n);
    }

    const dayUniqueNumbers = Array.from(daySet).sort();

    if (dayUniqueNumbers.length === 0) continue;

    const firstDocOfDay = dayDocs[0];
    if (!cycleStartDayKey) {
      cycleStartDayKey = dayKey;
      cycleStartMeta = {
        serialNumber: firstDocOfDay.serialNumber || "",
        number: firstDocOfDay.recordNumber ?? firstDocOfDay.entryNumber ?? null,
      };
    }

    const newNumbers = [];
    for (const num of dayUniqueNumbers) {
      if (!seenInCycle.has(num)) {
        seenInCycle.add(num);
        newNumbers.push(num);

        if (!firstSeenMap.has(num)) {
          firstSeenMap.set(num, {
            number: num,
            firstSeenDate: dayKey,
            firstSeenSerialNumber: firstDocOfDay.serialNumber || "",
            recordNumber: firstDocOfDay.recordNumber ?? firstDocOfDay.entryNumber ?? null,
            fileName: firstDocOfDay.fileName || "",
          });
        }
      }
    }

    const uniqueNumbersInDayCount = dayUniqueNumbers.length;
    const newNumbersCount = newNumbers.length;

    const progressPercent = Number(((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2));

    dailyTimeline.push({
      cycleNumber,
      date: dayKey,
      uniqueNumbersInDay: uniqueNumbersInDayCount,
      newNumbersCount,
      totalSeenAfterDay: seenInCycle.size,
      progressPercent,
      newNumbers,
    });

    if (seenInCycle.size === TOTAL_NUMBERS) {
      const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
        a.number.localeCompare(b.number),
      );

      const endMeta = dayDocs[dayDocs.length - 1];

      cycles.push({
        cycleNumber,
        status: "COMPLETED",
        startDate: cycleStartDayKey,
        startSerialNumber: cycleStartMeta?.serialNumber || "",
        startRecordNumber: cycleStartMeta?.number ?? null,

        endDate: dayKey,
        endSerialNumber: endMeta.serialNumber || "",
        endRecordNumber: endMeta.recordNumber ?? endMeta.entryNumber ?? null,

        uniqueNumbersSeen: seenInCycle.size,
        remainingCount: 0,
        progressPercent: 100,

        remainingNumbers: [],
        firstSeenNumbers,

        dailyTimeline: dailyTimeline.filter((d) => d.cycleNumber === cycleNumber),
      });

      cycleNumber += 1;
      seenInCycle = new Set();
      firstSeenMap = new Map();
      cycleStartDayKey = null;
      cycleStartMeta = null;
    }
  }

  if (seenInCycle.size > 0 && cycles.length >= 0) {
    const remainingNumbers = ALL_NUMBERS.filter((num) => !seenInCycle.has(num));

    const firstSeenNumbers = Array.from(firstSeenMap.values()).sort((a, b) =>
      a.number.localeCompare(b.number),
    );

    const lastDayKey = dayKeys[dayKeys.length - 1] || "";

    cycles.push({
      cycleNumber,
      status: "IN_PROGRESS",
      startDate: cycleStartDayKey || "",
      startSerialNumber: cycleStartMeta?.serialNumber || "",
      startRecordNumber: cycleStartMeta?.number ?? null,

      endDate: lastDayKey,
      endSerialNumber: "",
      endRecordNumber: null,

      uniqueNumbersSeen: seenInCycle.size,
      remainingCount: remainingNumbers.length,
      progressPercent: Number(((seenInCycle.size / TOTAL_NUMBERS) * 100).toFixed(2)),

      remainingNumbers,
      firstSeenNumbers,
      dailyTimeline: dailyTimeline.filter((d) => d.cycleNumber === cycleNumber),
    });
  }

  return {
    totalDraws: docs.length,
    totalPossibleNumbers: TOTAL_NUMBERS,
    totalCycles: cycles.length,
    cycles,
    dailyTimeline,
  };
}

// Export all functions
module.exports = {
  generateAll4DigitNumbers,
  parseDDMMYYYYToDate,
  extractUniqueNumbersFromDoc,
  sortDocsChronologically,
  buildCycleAnalysisByDay,
};