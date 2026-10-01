function pad2(value) {
  return String(value).padStart(2, "0");
}

function normalizeYear(yearStr) {
  const year = Number(yearStr);
  return String(yearStr).length === 2 ? 2000 + year : year;
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

/**
 * Convert any supported date string into:
 *
 * DD/MM/YYYY
 *
 * Example:
 * 11/07/2020
 */
function normalizeDateToDDMMYYYY(rawDate) {
  if (!rawDate || typeof rawDate !== "string") {
    return "Unknown";
  }

  const value = rawDate.trim();

  let day;
  let month;
  let year;
  let match;

  // 11/07/2020
  // 11-07-2020
  // 11.07.2020
  match = value.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})$/);

  if (match) {
    day = Number(match[1]);
    month = Number(match[2]);
    year = normalizeYear(match[3]);
  }

  // 11 July 2020
  if (!match) {
    match = value.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$/i);

    if (match) {
      day = Number(match[1]);
      month = monthNameToNumber(match[2]);
      year = Number(match[3]);
    }
  }

  // July 11, 2020
  if (!match) {
    match = value.match(/^([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})$/i);

    if (match) {
      month = monthNameToNumber(match[1]);
      day = Number(match[2]);
      year = Number(match[3]);
    }
  }

  if (!day || !month || !year || !isValidDateParts(day, month, year)) {
    return "Unknown";
  }

  return `${pad2(day)}/${pad2(month)}/${year}`;
}

/**
 * THE ONLY PDF DATE EXTRACTION FUNCTION
 *
 * Always returns:
 *
 * DD/MM/YYYY
 *
 * Example:
 * 11/07/2020
 */
function extractDateFromText(text) {
  if (!text || typeof text !== "string") {
    return "Unknown";
  }

  const cleanText = text
    .replace(/\u0000/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  const datePattern =
    "(\u005cd{1,2}[\\/.\\-]\u005cd{1,2}[\\/.\\-]\u005cd{2,4}|\u005cd{1,2}\u005cs+[A-Za-z]+\u005cs+\u005cd{4}|[A-Za-z]+\u005cs+\u005cd{1,2},\u005cs+\u005cd{4})";

  /*
   * First priority:
   * Find the date attached to an actual draw-date label.
   *
   * Examples:
   * Held on:- 11/07/2020
   * Held on: 11/07/2020
   * Draw held on 11/07/2020
   * Drawn on: 11/07/2020
   * Draw Date: 11/07/2020
   */
  const labelledPatterns = [
    new RegExp(`(?:draw\\s+)?held\\s+on\\s*[:\\-]*\\s*${datePattern}`, "i"),

    new RegExp(
      `(?:drawn\\s+on|draw\\s+date|date\\s+of\\s+draw)\\s*[:\\-]*\\s*${datePattern}`,
      "i",
    ),
  ];

  for (const pattern of labelledPatterns) {
    const match = cleanText.match(pattern);

    if (match) {
      const normalized = normalizeDateToDDMMYYYY(match[1]);

      if (normalized !== "Unknown") {
        return normalized;
      }
    }
  }

  /*
   * Remove common PDF footer dates.
   *
   * These dates are NOT the lottery draw date.
   */
  const withoutFooterDates = cleanText
    .replace(
      /Page\s*\d+[^0-9]{0,120}?\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}(?:\s+\d{1,2}:\d{2}:\d{2})?/gi,
      " ",
    )
    .replace(
      /(?:Modernization\s*&\s*IT\s*Software\s*Division|IT\s*Support\s*:\s*NIC\s*Kerala)[^0-9]{0,120}?\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}/gi,
      " ",
    );

  /*
   * Last fallback:
   * Find a remaining date-looking value.
   */
  const fallbackPattern = new RegExp(`\\b${datePattern}\\b`, "i");

  const fallbackMatch = withoutFooterDates.match(fallbackPattern);

  if (!fallbackMatch) {
    return "Unknown";
  }

  return normalizeDateToDDMMYYYY(fallbackMatch[1]);
}

/**
 * Convert:
 *
 * DD/MM/YYYY
 *
 * into a MongoDB Date for chronological sorting.
 *
 * Example:
 * 11/07/2020
 * ->
 * 2020-07-11T00:00:00.000Z
 */
function ddmmyyyyToUTCDate(dateStr) {
  if (!dateStr || dateStr === "Unknown") {
    return null;
  }

  const match = dateStr.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);

  if (!match) {
    return null;
  }

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);

  return new Date(Date.UTC(year, month - 1, day));
}

module.exports = {
  extractDateFromText,
  normalizeDateToDDMMYYYY,
  ddmmyyyyToUTCDate,
};
