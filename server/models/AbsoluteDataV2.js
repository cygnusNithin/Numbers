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

const AbsoluteDataV2Schema = new mongoose.Schema(
  {
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

    date: {
      type: String,
      required: true,
      validate: {
        validator: function (value) {
          if (
            typeof value !== "string" ||
            !/^(0[1-9]|[12][0-9]|3[01])\/(0[1-9]|1[0-2])\/\d{4}$/.test(value)
          ) {
            return false;
          }

          const [day, month, year] = value.split("/").map(Number);
          const parsed = new Date(Date.UTC(year, month - 1, day));

          return (
            parsed.getUTCFullYear() === year &&
            parsed.getUTCMonth() === month - 1 &&
            parsed.getUTCDate() === day
          );
        },
        message: "Date must be a valid date in DD/MM/YYYY format",
      },
    },

    drawDate: {
      type: Date,
      default: null,
      index: true,
    },

    drawCategory: {
      type: String,
      enum: ["BM", "BR", "OTHER", "UNKNOWN"],
      default: "UNKNOWN",
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
    collection: "absolute_data_v2",
  },
);

AbsoluteDataV2Schema.plugin(AutoIncrement, {
  id: "absolute_data_v2_record_number_seq",
  inc_field: "recordNumber",
  start_seq: 1,
});

module.exports = mongoose.model("AbsoluteDataV2", AbsoluteDataV2Schema);
