import pandas as pd

# === Load Provided Top-Hit Data CSV (you will export your data to this file first) ===
INPUT_CSV = "5000_number_patterns20.csv"           # your full data
OUTPUT_CSV = "predictive_hot_numbers.csv"  # filtered top picks

# === Best Intervals to Extract ===
best_ranges = [
    (7400, 7449),
    (7900, 7949),
    (7950, 7999),
    (8050, 8099)
]

# === Load the Data ===
df = pd.read_csv(INPUT_CSV)

# === Convert number column to integer ===
df["number"] = df["number"].astype(int)

# === Filter Function ===
def is_in_best_range(num):
    return any(low <= num <= high for low, high in best_ranges)

# === Apply Filter ===
filtered_df = df[df["number"].apply(is_in_best_range)]

# === Save the predictive result ===
filtered_df.to_csv(OUTPUT_CSV, index=False)

print("\n🎉 Predictive CSV file created!")
print(f"📌 Saved as: {OUTPUT_CSV}")
