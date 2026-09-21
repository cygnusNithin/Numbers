import pandas as pd
import json

# ======================
# CONFIG
# ======================
DATA_CSV = "lotteryData1.csv"
PRIZE_5000 = 5000
PRIZE_100 = 100
MIN_5000 = 1         # must appear at least once in 5000
MAX_5000 = 3         # but fewer than 4 times (i.e., <=3)
MIN_100  = 16        # more than 15 times in 100

# ======================
# LOAD DATA
# ======================
df = pd.read_csv(DATA_CSV)
df["number"] = df["number"].astype(str).str.zfill(4)
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
df = df.dropna(subset=["date"])

print("✅ Data loaded:", df.head())

# ======================
# SUBSETS & COUNTS
# ======================
sub_5000 = df[df["prize"] == PRIZE_5000]
sub_100  = df[df["prize"] == PRIZE_100]

counts_5000 = sub_5000["number"].value_counts()
counts_100  = sub_100["number"].value_counts()

# ======================
# FILTER BY CONDITIONS
# ======================
results = {}
unique_numbers = set()

for number, c5000 in counts_5000.items():
    if MIN_5000 <= c5000 <= MAX_5000 and counts_100.get(number, 0) >= MIN_100:
        results[number] = {
            "count_in_5000": int(c5000),
            "dates_in_5000": sorted(
                sub_5000.loc[sub_5000["number"] == number, "date"]
                        .dt.strftime("%Y-%m-%d")
                        .unique()
                        .tolist()
            ),
            "count_in_100": int(counts_100[number]),
            "dates_in_100": sorted(
                sub_100.loc[sub_100["number"] == number, "date"]
                       .dt.strftime("%Y-%m-%d")
                       .unique()
                       .tolist()
            ),
        }
        unique_numbers.add(number)

# ======================
# SAVE JSON
# ======================
out_path = "lottery_5000_lt4_and_100_gt15.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(
        {
            "results": results,
            "unique_numbers": sorted(list(unique_numbers))  # added set as list
        },
        f,
        indent=2,
        sort_keys=True,
        ensure_ascii=False
    )

print(f"✅ Saved {len(results)} numbers to {out_path}")
print("🎯 Unique numbers set:", unique_numbers)
