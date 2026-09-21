const mongoose = require("mongoose");
const AutoIncrement = require("mongoose-sequence")(mongoose);

const SeriesSchema = new mongoose.Schema({
  prize: Number,
  numbers: [
    {
      number: String,
      count: { type: Number, default: 1 },
    },
  ],
});

const DataSchema = new mongoose.Schema({
  entryNumber: { type: Number, unique: true },
  serialNumber: String,
  date: String,
  series: [SeriesSchema],
  createdAt: { type: Date, default: Date.now },
});

DataSchema.plugin(AutoIncrement, {
  inc_field: "entryNumber",
  id: "lottery_data_new_counter",
});

module.exports = mongoose.model(
  "LotteryDataNew",
  DataSchema,
  "lotterydata_new",
);
