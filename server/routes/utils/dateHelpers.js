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
 * IMPORTANT:
 *
 * If a PDF contains:
 *
 * DRAW scheduled on 11/07/2020 at 3:00 PM
 * and held on:- 26/07/2020, 3:00 PM
 *
 * this function MUST return:
 *
 * 11/07/2020
 *
 * The scheduled date has priority over the held date.
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
    "(\\d{1,2}[\\/\\.\\-]\\d{1,2}[\\/\\.\\-]\\d{2,4}|\\d{1,2}\\s+[A-Za-z]+\\s+\\d{4}|[A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})";

  /*
   * ============================================================
   * 1. SCHEDULED DATE — HIGHEST PRIORITY
   * ============================================================
   *
   * Examples:
   *
   * DRAW scheduled on 11/07/2020 at 3:00 PM
   * DRAW scheduled on:- 11/07/2020
   * Draw scheduled on: 11/07/2020
   * scheduled on 11/07/2020
   * scheduled for 11/07/2020
   *
   * This MUST be checked before "held on".
   */

  const scheduledPatterns = [
    new RegExp(
      `(?:draw\\s+)?scheduled\\s+(?:on|for)\\s*[:\\-]*\\s*${datePattern}`,
      "i",
    ),

    new RegExp(
      `scheduled\\s+draw\\s+(?:on|for)\\s*[:\\-]*\\s*${datePattern}`,
      "i",
    ),
  ];

  for (const pattern of scheduledPatterns) {
    const match = cleanText.match(pattern);

    if (match) {
      const normalized = normalizeDateToDDMMYYYY(match[1]);

      if (normalized !== "Unknown") {
        return normalized;
      }
    }
  }

  /*
   * ============================================================
   * 2. EXPLICIT DRAW DATE
   * ============================================================
   *
   * Examples:
   *
   * Draw Date: 11/07/2020
   * Drawn on: 11/07/2020
   * Date of Draw: 11/07/2020
   */

  const drawDatePatterns = [
    new RegExp(
      `(?:drawn\\s+on|draw\\s+date|date\\s+of\\s+draw)\\s*[:\\-]*\\s*${datePattern}`,
      "i",
    ),
  ];

  for (const pattern of drawDatePatterns) {
    const match = cleanText.match(pattern);

    if (match) {
      const normalized = normalizeDateToDDMMYYYY(match[1]);

      if (normalized !== "Unknown") {
        return normalized;
      }
    }
  }

  /*
   * ============================================================
   * 3. HELD DATE — FALLBACK ONLY
   * ============================================================
   *
   * Examples:
   *
   * held on:- 26/07/2020
   * held on: 26/07/2020
   * draw held on 26/07/2020
   *
   * We reach this section ONLY when no scheduled/draw date
   * was found.
   */

  const heldPatterns = [
    new RegExp(`(?:draw\\s+)?held\\s+on\\s*[:\\-]*\\s*${datePattern}`, "i"),

    new RegExp(`held\\s+(?:on|at)\\s*[:\\-]*\\s*${datePattern}`, "i"),
  ];

  for (const pattern of heldPatterns) {
    const match = cleanText.match(pattern);

    if (match) {
      const normalized = normalizeDateToDDMMYYYY(match[1]);

      if (normalized !== "Unknown") {
        return normalized;
      }
    }
  }

  /*
   * ============================================================
   * 4. REMOVE COMMON PDF FOOTER DATES
   * ============================================================
   *
   * These dates are not lottery draw dates.
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
   * ============================================================
   * 5. FINAL FALLBACK
   * ============================================================
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
 * into a MongoDB UTC Date.
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
