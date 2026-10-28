const { cleanPrizeSection } = require("./lotteryHelpers");

function extractFourDigitPrizeSeries(sectionText = "") {
  const normalized = cleanPrizeSection(String(sectionText));

  // Supports headings such as:
  // 1st Prize - Rs : 8000000/-
  // 3rd Prize-Rs :5000/-
  // 4th Prize - Rs. 2000/-
  // Consolation Prize - Rs 5000/-
  const headerRegex =
    /(\d{1,2}(?:st|nd|rd|th)|consolation)\s*Prize\s*[-–—]?\s*Rs\s*[:.]?\s*([\d,]+)/gi;

  const headers = [];
  let match;

  while ((match = headerRegex.exec(normalized)) !== null) {
    const prizeAmount = Number(match[2].replace(/,/g, ""));
    if (!Number.isSafeInteger(prizeAmount) || prizeAmount < 1) {
      continue;
    }

    headers.push({
      prizeCategory: match[1].toLowerCase(),
      prizeAmount,
      start: match.index,
      contentStart: headerRegex.lastIndex,
    });
  }

  const results = [];

  for (let i = 0; i < headers.length; i++) {
    const current = headers[i];
    const next = headers[i + 1];

    // Stop immediately before the next prize heading.
    const chunk = normalized.slice(
      current.contentStart,
      next ? next.start : normalized.length,
    );

    const cleanedChunk = chunk
      .replace(/\bPage\s*\d+\b/gi, " ")
      .replace(/\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}/g, " ")
      .replace(/\b\d{2}:\d{2}:\d{2}\b/g, " ");

    // Exact four-digit tokens only. This prevents extracting
    // four-digit pieces from five- or six-digit ticket numbers.
    const matches = cleanedChunk.match(/(?<!\d)\d{4}(?!\d)/g) || [];

    // Deduplicate within a prize tier without losing leading zeros.
    const numbers = [...new Set(matches)];

    if (numbers.length === 0) continue;

    results.push({
      prizeCategory: current.prizeCategory,
      prizeAmount: current.prizeAmount,
      numbers: numbers.map((number) => ({
        number,
        count: 1,
      })),
    });
  }

  return results;
}

module.exports = { extractFourDigitPrizeSeries };
