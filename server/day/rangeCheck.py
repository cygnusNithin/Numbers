import pandas as pd

# Load the CSV
df = pd.read_csv("filtered_prizes.csv")

# Identify columns
date_col = df.columns[0]      # first column is the date
range_cols = df.columns[1:]   # all range columns

# Sum each range column across all rows
range_totals = df[range_cols].sum(numeric_only=True)

# Total numbers counted across all ranges
grand_total = range_totals.sum()
if grand_total == 0:
    raise ValueError("Grand total is zero; cannot compute probabilities.")

# Calculate probability for each range
probabilities = (range_totals / grand_total) * 100

# Build Dates column: pipe-separated dates where the range has a non-zero count
# Uses the original date strings as-is (preserves format/order from the CSV)
dates_map = {
    col: "|".join(df.loc[df[col].fillna(0) > 0, date_col].astype(str).tolist())
    for col in range_cols
}

# Prepare output table
result = pd.DataFrame({
    "Range": range_cols,
    "Total_Appearances": range_totals.values.astype(int),
    "Probability_%": probabilities.values,
    "Dates": [dates_map[c] for c in range_cols]
})

# Sort by most frequent first
result = result.sort_values(by="Total_Appearances", ascending=False)

# Save result
result.to_csv("range_probabilities.csv", index=False, encoding="utf-8")

print("Done! Generated: range_probabilities.csv")