import mongoose from "mongoose";
const schema = new mongoose.Schema({
  prize: String,
  numbers: [String],
});
export default mongoose.model("Result", schema);
