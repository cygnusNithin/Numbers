const mongoose = require("mongoose");

mongoose.connect("mongodb://localhost:27017/numbergrid");

const DataSchema = new mongoose.Schema({
  userId: String,
  date: String, // DD.MM.YYYY
  numbers: [
    {
      number: String,
      count: Number,
    },
  ],
});

const UserData = mongoose.model("UserData", DataSchema);

async function findCrossYearRepeatsWithCounts() {
  const allDocs = await UserData.find();

  const tracker = {}; // number -> day-month -> year -> count

  for (const doc of allDocs) {
    const [day, month, year] = doc.date.split(".");

    for (const numObj of doc.numbers || []) {
      const number = numObj.number;

      if (!tracker[number]) tracker[number] = {};
      const dayMonth = `${day}-${month}`;

      if (!tracker[number][dayMonth]) tracker[number][dayMonth] = {};
      if (!tracker[number][dayMonth][year])
        tracker[number][dayMonth][year] = 0;

      tracker[number][dayMonth][year] += 1;
    }
  }

  // Convert tracker into result format
  const result = [];

  for (const number in tracker) {
    for (const dayMonth in tracker[number]) {
      const yearsInfo = tracker[number][dayMonth];
      const yearsList = Object.entries(yearsInfo)
        .map(([year, count]) => ({ year, count }))
        .filter((y) => y.count >= 1);

      if (yearsList.length > 1) {
        const [day, month] = dayMonth.split("-");
        result.push({
          number,
          day,
          month,
          years: yearsList,
        });
      }
    }
  }

  console.log(JSON.stringify(result, null, 2));
  mongoose.disconnect();
}

findCrossYearRepeatsWithCounts();
