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
    },
    numbers: {
      type: [WinningNumberSchema],
      default: [],
    },
  },
  { _id: false },
);

const AbsoluteDataSchema = new mongoose.Schema(
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
        validator: function (v) {
          return /^(0[1-9]|[12][0-9]|3[01])\/(0[1-9]|1[0-2])\/\d{4}$/.test(v);
        },
        message: "Date must be in DD/MM/YYYY format",
      },
    },

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
    collection: "absolute_data",
  },
);

AbsoluteDataSchema.plugin(AutoIncrement, {
  id: "absolute_data_record_number_seq",
  inc_field: "recordNumber",
  start_seq: 1,
});

module.exports = mongoose.model("AbsoluteData", AbsoluteDataSchema);