const mongoose = require("mongoose");
const AutoIncrement = require("mongoose-sequence")(mongoose);

const SeriesSchema = new mongoose.Schema({
  prize: {
    type: Number,
    required: true,
    min: 1,
    max: 5000,
  },
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
