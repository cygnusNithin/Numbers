/**
 * Common numbers between records that share the same date (different serialNumbers).
 * For every shared number it shows which prize tier it won in each record.
 *
 * Run:
 *   MONGODB_URI="mongodb://localhost:27017/YOUR_DB_NAME" node common_numbers_same_date.js
 * Optional: --collection=absolute_data   --date=17/07/2022
 *
 * Output: console report + common_numbers_same_date.csv
 */
const fs = require("fs");

const arg = (k, d) =>
  (process.argv.find((a) => a.startsWith(`--${k}=`)) || "").split("=")[1] || d;
const toISO = (s) => s.split("/").reverse().join("-");

// number -> sorted list of prizes it won in this record
function tiersByNumber(rec) {
  const m = new Map();
  for (const s of rec.series || [])
    for (const n of s.numbers || []) {
      if (!m.has(n.number)) m.set(n.number, new Set());
      m.get(n.number).add(s.prize);
    }
  return m;
}

// compare two records -> list of { number, prizesA, prizesB } + chance expectation
function sharedBetween(a, b) {
  const A = tiersByNumber(a),
    B = tiersByNumber(b);
  const shared = [];
  for (const [num, pa] of A)
    if (B.has(num))
      shared.push({
        number: num,
        prizesA: [...pa].sort((x, y) => y - x),
        prizesB: [...B.get(num)].sort((x, y) => y - x),
      });
  shared.sort((x, y) => x.number.localeCompare(y.number));
  const expected = (A.size * B.size) / 10000; // overlap two independent random draws would have
  return { shared, sizeA: A.size, sizeB: B.size, expected };
}

async function main() {
  const mongoose = require("mongoose");
  await mongoose.connect(
    process.env.MONGODB_URI || "mongodb://localhost:27017/numbergrid",
  );
  const db = mongoose.connection.db;
  console.log(`Connected to database: "${db.databaseName}"`);
  const col = db.collection(arg("collection", "absolute_data"));
  const onlyDate = arg("date", "");

  const pipe = [
    { $addFields: { d: { $trim: { input: { $toString: "$date" } } } } },
  ];
  if (onlyDate) pipe.push({ $match: { d: onlyDate } });
  pipe.push(
    { $group: { _id: "$d", serials: { $addToSet: "$serialNumber" } } },
    { $addFields: { n: { $size: "$serials" } } },
    { $match: { n: { $gt: 1 } } },
  );
  const dates = (await col.aggregate(pipe).toArray())
    .map((x) => x._id)
    .sort((a, b) => toISO(a).localeCompare(toISO(b)));
  console.log(`Dates with different serialNumbers: ${dates.length}`);

  const csv = ["date,number,serialA,prizeA,serialB,prizeB"];
  for (const date of dates) {
    const recs = await col
      .aggregate([
        { $addFields: { d: { $trim: { input: { $toString: "$date" } } } } },
        { $match: { d: date } },
        { $sort: { recordNumber: 1 } },
      ])
      .toArray();

    for (let i = 0; i < recs.length; i++)
      for (let j = i + 1; j < recs.length; j++) {
        const { shared, sizeA, sizeB, expected } = sharedBetween(
          recs[i],
          recs[j],
        );
        console.log(
          `\n${date}   ${recs[i].serialNumber} (${sizeA} numbers)  vs  ${recs[j].serialNumber} (${sizeB} numbers)`,
        );
        console.log(
          `   common numbers: ${shared.length}   (pure chance would give about ${expected.toFixed(1)})`,
        );
        console.log(
          `   ${"number".padEnd(8)}${recs[i].serialNumber.padEnd(14)}${recs[j].serialNumber}`,
        );
        for (const s of shared) {
          console.log(
            `   ${s.number.padEnd(8)}${("prize " + s.prizesA.join("/")).padEnd(14)}prize ${s.prizesB.join("/")}`,
          );
          csv.push(
            [
              date,
              s.number,
              recs[i].serialNumber,
              s.prizesA.join("/"),
              recs[j].serialNumber,
              s.prizesB.join("/"),
            ].join(","),
          );
        }
      }
  }
  fs.writeFileSync("common_numbers_same_date.csv", csv.join("\n"));
  console.log("\nSaved: common_numbers_same_date.csv");
  await mongoose.disconnect();
}

module.exports = { sharedBetween };
if (require.main === module)
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
