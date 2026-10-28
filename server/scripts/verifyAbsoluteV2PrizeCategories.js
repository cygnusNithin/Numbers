
const mongoose = require("mongoose");
const AbsoluteDataV2 = require("../models/AbsoluteDataV2");

const MONGO_URI =
  process.env.MONGO_URI || "mongodb://localhost:27017/numbergrid";

const EXPECTED = [
  { serialNumber: "KR-456", groups: 5, totalNumbers: 234 },
  { serialNumber: "KR-457", groups: 5, totalNumbers: 234 },
  { serialNumber: "KR-458", groups: 5, totalNumbers: 234 },
  { serialNumber: "KR-459", groups: 5, totalNumbers: 234 },
  { serialNumber: "W-576", groups: 5, totalNumbers: 238 },
  { serialNumber: "AK-457", groups: 5, totalNumbers: 235 },
  { serialNumber: "NR-185", groups: 4, totalNumbers: 244 },
  { serialNumber: "SS-222", groups: 6, totalNumbers: 259 },
  { serialNumber: "KN-329", groups: 4, totalNumbers: 246 },
  { serialNumber: "W-578", groups: 5, totalNumbers: 238 },
];

async function main() {
  await mongoose.connect(MONGO_URI);

  let failures = 0;

  try {
    for (const expected of EXPECTED) {
      const record = await AbsoluteDataV2.findOne({
        serialNumber: expected.serialNumber,
      }).lean();

      if (!record) {
        console.log(`FAIL ${expected.serialNumber}: record missing`);
        failures++;
        continue;
      }

      const series = record.series || [];
      const totalNumbers = series.reduce(
        (sum, group) => sum + (group.numbers || []).length,
        0,
      );

      const missingCategory = series.filter(
        (group) =>
          typeof group.prizeCategory !== "string" ||
          !group.prizeCategory.trim(),
      );

      const invalidNumbers = series.flatMap((group) =>
        (group.numbers || [])
          .filter((item) => !/^\d{4}$/.test(item.number))
          .map((item) => item.number),
      );

      const passed =
        series.length === expected.groups &&
        totalNumbers === expected.totalNumbers &&
        missingCategory.length === 0 &&
        invalidNumbers.length === 0;

      console.log(
        `${passed ? "PASS" : "FAIL"} ${expected.serialNumber}`,
        JSON.stringify({
          groups: series.length,
          totalNumbers,
          categories: series.map((group) => ({
            prizeCategory: group.prizeCategory,
            prize: group.prize,
            count: (group.numbers || []).length,
          })),
          missingCategoryCount: missingCategory.length,
          invalidNumberCount: invalidNumbers.length,
        }),
      );

      if (!passed) failures++;
    }
  } finally {
    await mongoose.disconnect();
  }

  console.log(
    `\nVerification result: ${EXPECTED.length - failures}/${EXPECTED.length} records passed`,
  );

  if (failures > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error("Verification failed:", error);
  process.exitCode = 1;
});
