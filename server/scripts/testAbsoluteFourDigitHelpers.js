const assert = require("node:assert/strict");

const {
  extractFourDigitPrizeSeries,
} = require("../routes/utils/absoluteFourDigitHelpers");

const sample = `
1st Prize - Rs : 8000000/- KE 236932
3rd Prize-Rs :5000/-0766 1354 1468 1813
4th Prize - Rs. 2000/- 0046 1234 579257 12345
Consolation Prize - Rs 5000/- 6789 0007
`;

const result = extractFourDigitPrizeSeries(sample);

console.log(JSON.stringify(result, null, 2));

const thirdPrize = result.find((item) => item.prizeCategory === "3rd");

const fourthPrize = result.find((item) => item.prizeCategory === "4th");

const consolation = result.find((item) => item.prizeCategory === "consolation");

assert.deepEqual(thirdPrize?.numbers, ["0766", "1354", "1468", "1813"]);

assert.deepEqual(fourthPrize?.numbers, ["0046", "1234"]);

assert.deepEqual(consolation?.numbers, ["6789", "0007"]);

assert.equal(
  result.some((item) => item.numbers.includes("5792")),
  false,
);

assert.equal(
  result.some((item) => item.numbers.includes("1234")),
  true,
);

console.log("PASS: four-digit extraction tests passed.");
