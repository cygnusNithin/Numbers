
const mongoose = require("mongoose");
const AbsoluteDataV2 = require("../models/AbsoluteDataV2");

const MONGO_URI = "mongodb://localhost:27017/numbergrid";

const serials = [
  "KR-456",
  "KR-457",
  "KR-458",
  "KR-459",
  "W-576",
  "AK-457",
  "NR-185",
  "SS-222",
  "KN-329",
  "W-578",
];

async function main() {
  await mongoose.connect(MONGO_URI);

  try {
    const totalDocuments = await AbsoluteDataV2.countDocuments();

    const records = await AbsoluteDataV2.find({
      serialNumber: { $in: serials },
    })
      .select("serialNumber date series drawCategory")
      .lean();

    const foundSerials = new Set(records.map((r) => r.serialNumber));

    console.log("\n=== V2 DATABASE VERIFICATION ===");
    console.log("Total V2 documents:", totalDocuments);
    console.log("Expected test records:", serials.length);
    console.log("Found test records:", records.length);
    console.log("Missing serials:", serials.filter((s) => !foundSerials.has(s)));

    for (const record of records.sort(
      (a, b) => serials.indexOf(a.serialNumber) - serials.indexOf(b.serialNumber)
    )) {
      const groups = record.series || [];
      const totalNumbers = groups.reduce(
        (sum, group) => sum + (group.numbers?.length || 0),
        0
      );

      const invalidGroups = groups.filter(
        (group) =>
          !Number.isFinite(Number(group.prize)) ||
          Number(group.prize) <= 0
      );

      const invalidNumbers = [];

      for (const group of groups) {
        for (const item of group.numbers || []) {
          if (!/^\d{4}$/.test(String(item.number))) {
            invalidNumbers.push(item.number);
          }
        }
      }

      console.log(`\n${record.serialNumber} | ${record.date}`);
      console.log("  Category:", record.drawCategory ?? "(unset)");
      console.log("  Prize groups:", groups.length);
      console.log("  Total numbers:", totalNumbers);
      console.log(
        "  Prize counts:",
        groups
          .map((g) => `${g.prize ?? "MISSING"}:${g.numbers?.length || 0}`)
          .join(", ")
      );
      console.log("  Invalid prize groups:", invalidGroups.length);
      console.log("  Invalid number strings:", invalidNumbers.length);

      if (invalidGroups.length) {
        console.log("  Invalid group details:", invalidGroups);
      }

      if (invalidNumbers.length) {
        console.log("  Invalid values:", invalidNumbers);
      }
    }
  } finally {
    await mongoose.disconnect();
  }
}

main().catch((error) => {
  console.error("Verification failed:", error);
  process.exitCode = 1;
});
