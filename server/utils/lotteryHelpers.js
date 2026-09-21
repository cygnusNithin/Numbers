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
 * Dynamically identifies prizes and extracts numbers between headers.
 * EXCLUDES Prize-Rs :100000/- and other blacklisted amounts
 */
function getPrizeNumbersByAmount(sectionText = "") {
  // Blacklist of prize amounts to exclude
  const BLACKLISTED_AMOUNTS = [100000];

  // 1. Initial cleanup
  const normalized = cleanPrizeSection(sectionText);
  const results = {};

  const prizeHeaderRegex =
    /(\d+(?:st|nd|rd|th))\s*Prize\s*-\s*Rs\s*[:.]?\s*([\d,]+)/gi;

  let match;
  const matches = [];
  while ((match = prizeHeaderRegex.exec(normalized)) !== null) {
    const amount = parseInt(match[2].replace(/,/g, ""), 10);

    // 🛡️ SKIP BLACKLISTED AMOUNTS
    if (BLACKLISTED_AMOUNTS.includes(amount)) {
      console.log(`      ⛔ Skipped Prize-Rs :${amount}/- (blacklisted)`);
      continue;
    }

    matches.push({
      index: match.index,
      amount: amount,
      fullMatch: match[0],
    });
  }

  for (let i = 0; i < matches.length; i++) {
    const currentMatch = matches[i];
    const nextMatch = matches[i + 1];

    const start = currentMatch.index + currentMatch.fullMatch.length;
    const end = nextMatch ? nextMatch.index : normalized.length;
    let chunk = normalized.substring(start, end);

    // --- 🛡️ SMART METADATA SCRUBBING PHASE ---

    // Remove Dates (e.g., 05/08/2020)
    chunk = chunk.replace(/\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}/g, " ");

    // Remove Times (e.g., 16:44:03)
    chunk = chunk.replace(/\d{2}:\d{2}:\d{2}/g, " ");

    // Remove Page Numbers, Headers, and Department info
    chunk = chunk.replace(/Page\s*\d+/gi, " ");
    chunk = chunk.replace(/Modernization.*?Division/gi, " ");
    chunk = chunk.replace(/Department.*?Lotteries/gi, " ");
    chunk = chunk.replace(/IT\s*Support.*?Kerala/gi, " ");

    // --- 🎯 NUMBER EXTRACTION PHASE ---

    // Extract only the remaining 4-digit numbers
    const numbers = (chunk.match(/\d{4}/g) || []).map((n) =>
      n.padStart(4, "0"),
    );

    if (numbers.length > 0) {
      const amt = currentMatch.amount;
      if (!results[amt]) results[amt] = [];

      // Combine and remove duplicates
      results[amt] = [...new Set([...results[amt], ...numbers])];
    }
  }

  return results;
}

module.exports = {
  cleanExtractedText,
  extractSerialNumber,
  cleanPrizeSection,
  getPrizeNumbersByAmount,
};