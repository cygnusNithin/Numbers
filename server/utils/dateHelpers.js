function pad2(value) {
  return String(value).padStart(2, "0");
}

function normalizeYear(yearStr) {
  const year = Number(yearStr);
  if (String(yearStr).length === 2) {
    return 2000 + year;
  }
  return year;
}

function isValidDateParts(day, month, year) {
  const test = new Date(year, month - 1, day);
  return (
    test.getFullYear() === year &&
    test.getMonth() === month - 1 &&
    test.getDate() === day
  );
}

function monthNameToNumber(monthName) {
  const months = {
    jan: 1,
    january: 1,
    feb: 2,
    february: 2,
    mar: 3,
    march: 3,
    apr: 4,
    april: 4,
    may: 5,
    jun: 6,
    june: 6,
    jul: 7,
    july: 7,
    aug: 8,
    august: 8,
    sep: 9,
    sept: 9,
    september: 9,
    oct: 10,
    october: 10,
    nov: 11,
    november: 11,
    dec: 12,
    december: 12,
  };
  return months[String(monthName).toLowerCase()] || null;
}

function normalizeDateToDDMMYYYY(rawDate) {
  if (!rawDate || typeof rawDate !== "string") return "Unknown";
  const value = rawDate.trim();
  let day,
    month,
    year,
    match = null;

  // FIXED REGEX: Matches 27/03/2026 or 27-03-2026 or 27.03.2026
  match = value.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})$/);
  if (match) {
    day = Number(match[1]);
    month = Number(match[2]);
    year = normalizeYear(match[3]);
  }

  // Matches 27 March 2026
  if (!match) {
    match = value.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/i);
    if (match) {
      day = Number(match[1]);
      month = monthNameToNumber(match[2]);
      year = Number(match[3]);
    }
  }

  if (!day || !month || !year || !isValidDateParts(day, month, year))
    return "Unknown";
  return `${pad2(day)}/${pad2(month)}/${year}`;
}

function extractDateFromText(text) {
  if (!text) return "Unknown";
  const cleanText = text.replace(/\s+/g, " ").trim();
  // Look for dates in the text
  const dateMatch = cleanText.match(
    /\b(\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},\s+\d{4})\b/i,
  );
  if (!dateMatch) return "Unknown";
  return normalizeDateToDDMMYYYY(dateMatch[0]);
}

function ddmmyyyyToUTCDate(dateStr) {
  if (!dateStr || dateStr === "Unknown") return null;
  const match = dateStr.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number(match[1]),
    month = Number(match[2]),
    year = Number(match[3]);
  return new Date(Date.UTC(year, month - 1, day));
}

module.exports = {
  extractDateFromText,
  normalizeDateToDDMMYYYY,
  ddmmyyyyToUTCDate,
};
