import pandas as pd
from tqdm import tqdm

# =======================
# CONFIG
# =======================
ALL_FILE = "all_prizes_number_patterns2.csv"
P5000_FILE = "5000_number_patterns5.csv"
OUTPUT_FILE = "comparison_all_vs_5000.csv"

# Load datasets
print("📂 Loading CSV files...")
df_all = pd.read_csv(ALL_FILE)
df_5000 = pd.read_csv(P5000_FILE)

# Ensure number is 4-digit string for comparison
df_all["number"] = df_all["number"].astype(str).str.zfill(4)
df_5000["number"] = df_5000["number"].astype(str).str.zfill(4)

# Filter numbers from all-prizes between 34 and 47 hits
df_all_filtered = df_all[(df_all["total_hits"] >= 34) & (df_all["total_hits"] <= 47)]

# Merge with 5000 prize data
print("🔄 Comparing numbers...")
comparison = []
for _, row in tqdm(df_all_filtered.iterrows(), total=len(df_all_filtered), desc="Processing"):
    num = row["number"]
    total_hits = row["total_hits"]

    match_5000 = df_5000[df_5000["number"] == num]
    if not match_5000.empty:
        hits_5000 = int(match_5000.iloc[0]["total_hits"])
    else:
        hits_5000 = 0

    comparison.append({
        "number": num,
        "total_hits_all": total_hits,
        "total_hits_5000": hits_5000
    })

# Save output
out_df = pd.DataFrame(comparison).sort_values(by="total_hits_all")
out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

print(f"✅ Saved comparison results to {OUTPUT_FILE} ({len(out_df)} rows)")
