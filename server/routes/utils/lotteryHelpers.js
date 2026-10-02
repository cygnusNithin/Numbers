/**
 * Basic text cleaning for raw PDF output
 */
function cleanExtractedText(text = "") {
  return String(text)
    .replace(/\u0000/g, " ")
    .replace(/\r|\n|\t/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Extracts the Lottery Serial/Number from the header section
 */
function extractSerialNumber(text = "") {
  const clean = cleanExtractedText(text);
  const match = clean.match(/LOTTERY\s+NO\.?\s*([A-Z0-9-]+)(?:st|nd|rd|th)?/i);
  return match ? match[1].trim().replace(/(st|nd|rd|th)$/i, "") : "Unknown";
}

/**
 * Aggressively removes headers, footers, and legal disclaimers
 */
function cleanPrizeSection(text = "") {
  let cleaned = text.replace(/\u0000/g, " ");

  // 1. REMOVE FOOTER LINES ENTIRELY
  const footerPattern = /\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}.*?Page\s*\d+/gi;
  cleaned = cleaned.replace(footerPattern, " ");

  // 2. TRUNCATE AT LEGAL DISCLAIMER
  const endMarkers = [
    "winners are advised to verify",
    "The prize winners are advised",
    "ze winners are advised",
    "Next Draw will be held on",
    "Next",
  ];

  for (const marker of endMarkers) {
    const stopIndex = cleaned.toLowerCase().indexOf(marker.toLowerCase());
    if (stopIndex !== -1) {
      cleaned = cleaned.substring(0, stopIndex);
      break;
    }
  }

  // 3. REMOVE REMAINING DEPARTMENT HEADERS
  cleaned = cleaned.replace(/Modernization & IT Software Division/gi, " ");
  cleaned = cleaned.replace(/Department of State Lotteries/gi, " ");
  cleaned = cleaned.replace(/IT Support\s*:\s*NIC Kerala/gi, " ");

  return cleaned.replace(/\s+/g, " ").trim();
}

/**
 * Dynamically identifies every prize category from the PDF
 * and extracts its 4-digit winning numbers.
 *
 * Only prize amounts from ₹1 to ₹5000 are accepted.
 *
 * Example:
 *   3rd Prize - Rs 5000/-
 *   4th Prize - Rs 3000/-
 *   5th Prize - Rs 400/-
 *
 * becomes:
 * {
 *   5000: ["1234", "5678"],
 *   3000: ["1111", "2222"],
 *   400: ["3333", "4444"]
 * }
 */
function getPrizeNumbersByAmount(sectionText = "") {
  const normalized = cleanPrizeSection(sectionText);
  const results = {};

  const prizeHeaderRegex =
    /(\d+(?:st|nd|rd|th))\s*Prize\s*-\s*Rs\s*[:.]?\s*([\d,]+)/gi;

  const matches = [];

  let match;

  while ((match = prizeHeaderRegex.exec(normalized)) !== null) {
    const amount = parseInt(match[2].replace(/,/g, ""), 10);

    if (!Number.isFinite(amount)) {
      continue;
    }

    // Only accept prize amounts from ₹1 through ₹5000.
    if (amount < 1 || amount > 5000) {
      console.log(
        `      ⛔ Skipped Prize-Rs :${amount}/- (outside 1-5000 range)`,
      );
      continue;
    }

    matches.push({
      index: match.index,
      amount,
      fullMatch: match[0],
    });
  }

  for (let i = 0; i < matches.length; i++) {
    const currentMatch = matches[i];
    const nextMatch = matches[i + 1];

    const start = currentMatch.index + currentMatch.fullMatch.length;
    const end = nextMatch ? nextMatch.index : normalized.length;

    let chunk = normalized.substring(start, end);

    // Remove dates.
    chunk = chunk.replace(/\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}/g, " ");

    // Remove times.
    chunk = chunk.replace(/\d{2}:\d{2}:\d{2}/g, " ");

    // Remove page numbers.
    chunk = chunk.replace(/Page\s*\d+/gi, " ");

    // Remove footer/header text.
    chunk = chunk.replace(/Modernization.*?Division/gi, " ");
    chunk = chunk.replace(/Department.*?Lotteries/gi, " ");
    chunk = chunk.replace(/IT\s*Support.*?Kerala/gi, " ");

    // Extract only 4-digit numbers.
    const numbers = (chunk.match(/\d{4}/g) || []).map((number) =>
      number.padStart(4, "0"),
    );

    if (numbers.length === 0) {
      continue;
    }

    const amount = currentMatch.amount;

    if (!results[amount]) {
      results[amount] = [];
    }

    results[amount] = [...new Set([...results[amount], ...numbers])];
  }

  return results;
}

module.exports = {
  cleanExtractedText,
  extractSerialNumber,
  cleanPrizeSection,
  getPrizeNumbersByAmount,
};
