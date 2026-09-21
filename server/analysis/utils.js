function parseDate(ddmmyyyy) {
  const [dd, mm, yyyy] = ddmmyyyy.split("/");
  return new Date(`${yyyy}-${mm}-${dd}T00:00:00.000Z`);
}

function pad4(n) {
  return String(n).padStart(4, "0");
}

function getAllNumbers() {
  return Array.from({ length: 10000 }, (_, i) => pad4(i));
}

/**
 * Extract all numbers from a single draw document.
 * Returns: [{ number, prize, count }]
 */
function extractNumbers(drawDoc) {
  const result = [];
  for (const series of drawDoc.series) {
    for (const { number, count } of series.numbers) {
      result.push({ number, prize: series.prize, count: count || 1 });
    }
  }
  return result;
}

function getDayLabel(date) {
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][date.getUTCDay()];
}

module.exports = { parseDate, pad4, getAllNumbers, extractNumbers, getDayLabel };