const mongoose = require("mongoose");
const AutoIncrement = require("mongoose-sequence")(mongoose);

const WinningNumberSchema = new mongoose.Schema(
  {
    number: {
      type: String,
      required: true,
      trim: true,
      match: /^\d{4}$/, // keep leading zeros: 0100, 0200, etc.
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
      // enum: [5000, 2000, 1000, 500, 200, 100],
    },
    numbers: {
      type: [WinningNumberSchema],
      default: [],
    },
  },
  { _id: false },
);

const LotteryDataSchema = new mongoose.Schema(
  {
    // Changed from entryNumber -> recordNumber
    recordNumber: {
      type: Number,
      unique: true,
      index: true,
    },

    serialNumber: {
      type: String,
      required: true,
      trim: true,
      unique: true,
      index: true,
    },

    // Exact document/display format
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

    // Safe backend date for sorting/filtering
    drawDate: {
      type: Date,
      default: null,
      index: true,
    },

    fileName: {
      type: String,
      trim: true,
      default: "",
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
    collection: "lottery_results_v2",
  },
);

// changed sequence id too, so old sequence is not reused
LotteryDataSchema.plugin(AutoIncrement, {
  id: "lottery_record_number_seq_v2",
  inc_field: "recordNumber",
  start_seq: 1,
});

module.exports = mongoose.model("FullLotteryData", LotteryDataSchema);
