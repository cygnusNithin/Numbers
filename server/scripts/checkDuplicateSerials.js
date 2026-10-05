const mongoose = require("mongoose");

mongoose
  .connect("mongodb://localhost:27017/numbergrid")
  .then(async () => {
    const db = mongoose.connection.db;

    for (const collectionName of [
      "lotterydatas",
      "lotterydata_new",
      "lottery_results_v2",
      "absolute_data",
    ]) {
      const results = await db
        .collection(collectionName)
        .aggregate([
          {
            $group: {
              _id: "$serialNumber",
              count: { $sum: 1 },
              dates: { $addToSet: "$date" },
              ids: { $push: "$_id" },
            },
          },
          {
            $match: {
              count: { $gt: 1 },
            },
          },
          {
            $sort: {
              count: -1,
            },
          },
        ])
        .toArray();

      const extraRecords = results.reduce(
        (sum, item) => sum + item.count - 1,
        0
      );

      console.log("\n========================================");
      console.log(collectionName);
      console.log("========================================");
      console.log("Duplicate serial groups:", results.length);
      console.log("Extra records represented by duplicates:", extraRecords);

      if (results.length > 0) {
        console.log(
          JSON.stringify(results.slice(0, 20), null, 2)
        );
      }
    }

    await mongoose.disconnect();
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
