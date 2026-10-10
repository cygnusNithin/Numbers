
const mongoose = require("mongoose");
const AbsoluteData = require("../models/AbsoluteData");

const URI =
  process.env.MONGODB_URI ||
  process.env.MONGO_URI ||
  "mongodb://localhost:27017/numbergrid";

async function main() {
  await mongoose.connect(URI);

  const draws = await AbsoluteData.find({})
    .select("recordNumber serialNumber date drawDate createdAt fileName")
    .lean();

  const byDate = new Map();

  for (const draw of draws) {
    if (!byDate.has(draw.date)) byDate.set(draw.date, []);
    byDate.get(draw.date).push(draw);
  }

  const duplicates = [...byDate.entries()]
    .filter(([, rows]) => rows.length > 1)
    .sort(([a], [b]) => {
      const [ad, am, ay] = a.split("/").map(Number);
      const [bd, bm, by] = b.split("/").map(Number);
      return Date.UTC(ay, am - 1, ad) - Date.UTC(by, bm - 1, bd);
    });

  console.log("Dates with multiple events:", duplicates.length);

  for (const [date, rows] of duplicates) {
    console.log(`\nDate: ${date}`);

    rows.sort((a, b) =>
      (a.recordNumber ?? 0) - (b.recordNumber ?? 0)
    );

    for (const row of rows) {
      console.log({
        recordNumber: row.recordNumber,
        serialNumber: row.serialNumber,
        drawDate: row.drawDate,
        createdAt: row.createdAt,
        fileName: row.fileName,
      });
    }
  }
}

main()
  .catch(console.error)
  .finally(async () => {
    await mongoose.disconnect().catch(() => {});
  });