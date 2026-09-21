# Let's create a different method, since we have the sequence and  Partial overlaps (≥2 rollers same):
#   number_id 1 and 2 share 2 rollers
#   number_id 1 and 4 share 2 rollers
#   number_id 1 and 5 share 2 rollers
#   number_id 1 and 6 share 2 rollers
#   number_id 1 and 8 share 2 rollers
#   number_id 1 and 9 share 2 rollers
#   number_id 1 and 10 share 2 rollers
#   number_id 1 and 11 share 2 rollers
#   number_id 1 and 17 share 2 rollers
#   number_id 2 and 3 share 3 rollers
#   number_id 2 and 4 share 3 rollers
#   number_id 2 and 5 share 3 rollers
#   number_id 2 and 6 share 3 rollers
#   number_id 2 and 16 share 2 rollers
#   number_id 2 and 18 share 2 rollers
#   number_id 3 and 4 share 3 rollers
#   number_id 3 and 5 share 2 rollers
#   number_id 3 and 6 share 3 rollers
#   number_id 3 and 14 share 2 rollers
#   number_id 3 and 16 share 3 rollers
#   number_id 3 and 18 share 3 rollers
#   number_id 4 and 5 share 2 rollers
#   number_id 4 and 6 share 4 rollers
#   number_id 4 and 11 share 2 rollers
#   number_id 4 and 16 share 2 rollers
#   number_id 4 and 18 share 2 rollers
#   number_id 5 and 6 share 2 rollers
#   number_id 5 and 10 share 2 rollers
#   number_id 5 and 16 share 2 rollers
#   number_id 5 and 17 share 2 rollers
#   number_id 5 and 18 share 3 rollers
#   number_id 6 and 11 share 2 rollers
#   number_id 6 and 16 share 2 rollers
#   number_id 6 and 18 share 2 rollers
#   number_id 7 and 17 share 2 rollers
#   number_id 8 and 9 share 3 rollers
#   number_id 8 and 10 share 2 rollers
#   number_id 8 and 11 share 3 rollers
#   number_id 8 and 12 share 2 rollers
#   number_id 8 and 13 share 2 rollers
#   number_id 8 and 15 share 2 rollers
#   number_id 9 and 10 share 2 rollers
#   number_id 9 and 11 share 3 rollers
#   number_id 9 and 12 share 3 rollers
#   number_id 9 and 13 share 2 rollers
#   number_id 10 and 12 share 3 rollers
#   number_id 10 and 13 share 2 rollers
#   number_id 10 and 14 share 2 rollers
#   number_id 10 and 15 share 2 rollers
#   number_id 10 and 17 share 3 rollers
#   number_id 11 and 12 share 2 rollers
#   number_id 11 and 13 share 2 rollers
#   number_id 11 and 14 share 2 rollers
#   number_id 12 and 13 share 3 rollers
#   number_id 12 and 14 share 2 rollers
#   number_id 12 and 15 share 2 rollers
#   number_id 12 and 17 share 2 rollers
#   number_id 13 and 14 share 3 rollers
#   number_id 13 and 15 share 2 rollers
#   number_id 13 and 16 share 2 rollers
#   number_id 13 and 17 share 2 rollers
#   number_id 14 and 17 share 2 rollers
#   number_id 15 and 17 share 2 rollers
#   number_id 16 and 18 share 3 rollers
#   number_id 17 and 18 share 2 rollers. lets check for 10 days in 5000 prize section. which has 18-20 numbers in each results. from DB: MONGO_URI = "mongodb://localhost:27017/"
# DB_NAME = "numbergrid"
# COLLECTION = "numberdatas" and schema: const mongoose = require("mongoose");
# const AutoIncrement = require("mongoose-sequence")(mongoose);

# const SeriesSchema = new mongoose.Schema({
#   prize: Number, // e.g., 5000, 2000, 500, 200, 100
#   numbers: [
#     {
#       number: String, // keep as string to preserve leading zeros
#       count: { type: Number, default: 1 }, // how many times this number appeared
#     },
#   ],
# });

# const DataSchema = new mongoose.Schema({
#   entryNumber: { type: Number, unique: true }, // auto-increment field
#   serialNumber: String, // e.g., "AB-1234"
#   date: String, // format: DD.MM.YYYY
#   series: [SeriesSchema], // multiple prize categories with numbers
#   createdAt: { type: Date, default: Date.now },
# });

# // Auto-increment plugin
# DataSchema.plugin(AutoIncrement, { inc_field: "entryNumber" });

# module.exports = mongoose.model("NumberData", DataSchema); create a for loop nad take all 18-20 5000 data from DB and run that rollers overlapping. since 4 and 6 has same roller sequence but different pattern. but assign first number to forth number rollers and check cyclic permutation for 6th number.
