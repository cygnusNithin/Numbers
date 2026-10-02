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
  entryNumber: { type: Number, unique: true }, // auto-increment field
  serialNumber: String, // e.g., "AB-1234"
  date: String, // format: DD/MM/YYYY
  series: [SeriesSchema], // multiple prize categories with numbers
  createdAt: { type: Date, default: Date.now },
});

// Auto-increment plugin
DataSchema.plugin(AutoIncrement, { inc_field: "entryNumber" });

module.exports = mongoose.model("LotteryData", DataSchema);
