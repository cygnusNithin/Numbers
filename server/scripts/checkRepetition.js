/**
 * Get all records that share the same `date` but have DIFFERENT serialNumbers.
 *
 * Run:
 *   MONGODB_URI="mongodb://localhost:27017/yourdb" node same_date_different_serial.js
 *   ... node same_date_different_serial.js --date=02/05/2025     (only one date)
 *
 * Output:
 *   same_date_different_serial.json  full records grouped by date
 *   same_date_different_serial.csv   flat rows: date, serial, prize, number, count
 */
const mongoose = require("mongoose");
const fs = require("fs");

const AbsoluteData = require("../models/AbsoluteData"); // <-- change path if needed

const dateArg = (process.argv.find((a) => a.startsWith("--date=")) || "").split(
  "=",
)[1];
const toISO = (s) => s.split("/").reverse().join("-");

(async () => {
  await mongoose.connect(
    process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid",
  );

  // 1. which dates have 2+ different serialNumbers?
  const pipeline = [];
  if (dateArg) pipeline.push({ $match: { date: dateArg } });
  pipeline.push(
    { $group: { _id: "$date", serials: { $addToSet: "$serialNumber" } } },
    { $addFields: { serialCount: { $size: "$serials" } } },
    { $match: { serialCount: { $gt: 1 } } },
  );
  const dates = await AbsoluteData.aggregate(pipeline);
  const dateList = dates
    .map((d) => d._id)
    .sort((a, b) => toISO(a).localeCompare(toISO(b)));
  console.log(`Dates with different serialNumbers: ${dateList.length}`);
  if (!dateList.length) return mongoose.disconnect();

  // 2. fetch the full records for those dates
  const docs = await AbsoluteData.find({ date: { $in: dateList } })
    .sort({ recordNumber: 1 })
    .lean();

  const grouped = {};
  for (const d of docs) (grouped[d.date] = grouped[d.date] || []).push(d);

  // 3. console summary: tier sizes, shared numbers, "pair like 17/07/2022" check
  const fileNo = (f) =>
    parseInt((String(f).match(/(\d+)(?!.*\d)/) || [])[1], 10);
  const tierSizes = (r) =>
    r.series
      .map((s) => `${s.prize}x${new Set(s.numbers.map((n) => n.number)).size}`)
      .join(" ");
  const csv = ["date,recordNumber,serialNumber,fileName,prize,number,count"];
  const summary = [];

  for (const date of dateList) {
    const recs = grouped[date];
    const sets = recs.map(
      (r) => new Set(r.series.flatMap((s) => s.numbers.map((n) => n.number))),
    );
    const union = new Set(sets.flatMap((s) => [...s]));
    console.log(
      `\n${date}  (${recs.length} records, ${union.size} unique numbers in total)`,
    );
    recs.forEach((r, i) => {
      console.log(
        `   #${r.recordNumber}  serial=${r.serialNumber}  file=${r.fileName || "-"}  unique=${sets[i].size}`,
      );
      console.log(`        tiers: ${tierSizes(r)}`);
      for (const s of r.series)
        for (const n of s.numbers)
          csv.push(
            [
              date,
              r.recordNumber,
              r.serialNumber,
              r.fileName || "",
              s.prize,
              n.number,
              n.count,
            ].join(","),
          );
    });
    let consecutive = true;
    for (let i = 1; i < recs.length; i++) {
      const recGap = recs[i].recordNumber - recs[i - 1].recordNumber;
      const fileGap = fileNo(recs[i].fileName) - fileNo(recs[i - 1].fileName);
      if (recGap !== 1 || fileGap !== 1) consecutive = false;
    }
    for (let i = 0; i < sets.length; i++)
      for (let j = i + 1; j < sets.length; j++) {
        const shared = [...sets[i]].filter((x) => sets[j].has(x));
        console.log(
          `   shared numbers ${recs[i].serialNumber} vs ${recs[j].serialNumber}: ${shared.length}  ${shared.slice(0, 12).join(" ")}`,
        );
      }
    console.log(
      `   consecutive recordNumber + fileName: ${consecutive ? "YES (same pattern as 17/07/2022)" : "no"}`,
    );
    summary.push({
      date,
      records: recs.length,
      serials: recs.map((r) => r.serialNumber).join(" | "),
      consecutive,
    });
  }

  console.log("\n=== SUMMARY ===");
  console.table(summary);

  fs.writeFileSync(
    "same_date_different_serial.json",
    JSON.stringify(grouped, null, 2),
  );
  fs.writeFileSync("same_date_different_serial.csv", csv.join("\n"));
  console.log(
    "\nSaved: same_date_different_serial.json, same_date_different_serial.csv",
  );
  await mongoose.disconnect();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
