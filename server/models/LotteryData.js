const mongoose = require("mongoose");
const AutoIncrement = require("mongoose-sequence")(mongoose);

const WinningNumberSchema = new mongoose.Schema(
  {
    number: {
      type: String,
      required: true,
      trim: true,
      match: /^\d{4}$/,
    },

    count: {
      type: Number,
      default: 1,
      min: 1,
    },
  },
  { _id: false },
);

const SeriesSchema = new mongoose.Schema(
  {
    prize: {
      type: Number,
      required: true,
      min: 1,
      max: 5000,
    },

    numbers: {
      type: [WinningNumberSchema],
      default: [],
    },
  },
  { _id: false },
);

const DataSchema = new mongoose.Schema(
  {
    entryNumber: {
      type: Number,
      unique: true,
      index: true,
    },

    serialNumber: {
      type: String,
      required: true,
      trim: true,
      index: true,
    },

    date: {
      type: String,
      required: true,
      validate: {
        validator: function (v) {
          return /^(0[1-9]|[12][0-9]|3[01])\/(0[1-9]|1[0-2])\/\d{4}$/.test(v);
        },
        message: "Date must be in DD/MM/YYYY format",
      },
    },

    series: {
      type: [SeriesSchema],
      default: [],
    },

    createdAt: {
      type: Date,
      default: Date.now,
    },
  },
  {
    versionKey: false,
    collection: "lotterydatas",
  },
);

DataSchema.plugin(AutoIncrement, {
  inc_field: "entryNumber",
  id: "lottery_data_counter_1",
});

module.exports = mongoose.model("LotteryData", DataSchema);
