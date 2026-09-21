import pandas as pd
from pymongo import MongoClient

# =======================
# CONFIGURATION
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
OUTPUT_FILE = "grouped_high_count_numbers.csv"
COUNT_THRESHOLD = 60  # ✅ Only include numbers with total count >= 60

# =======================
# CONNECT TO DATABASE
# =======================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]

# =======================
# FETCH AND FLATTEN DATA
# =======================
print("🔄 Fetching all numbers and counts from MongoDB...")

pipeline = [
    {"$unwind": "$series"},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "number": "$series.numbers.number",
        "count": "$series.numbers.count"
    }}
]

data = list(collection.aggregate(pipeline))
df = pd.DataFrame(data)

if df.empty:
    print("⚠️ No data found in MongoDB.")
    exit()

# Convert and normalize
df["number"] = df["number"].astype(str).str.zfill(4)
df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)

# =======================
# AGGREGATE TOTAL COUNTS
# =======================
agg_df = df.groupby("number", as_index=False)["count"].sum()

# Filter numbers with count ≥ threshold
filtered = agg_df[agg_df["count"] >= COUNT_THRESHOLD].copy()
print(f"✅ Found {len(filtered)} numbers with count ≥ {COUNT_THRESHOLD}")

# =======================
# GROUP INTO 100-RANGES
# =======================
def number_to_range(num):
    n = int(num)
    start = (n // 100) * 100
    end = start + 99
    return f"{str(start).zfill(4)}-{str(end).zfill(4)}"

filtered["range_group"] = filtered["number"].apply(number_to_range)

# Group summary: how many numbers per range
group_summary = (
    filtered.groupby("range_group")
    .agg(
        total_numbers=("number", "count"),
        avg_count=("count", "mean"),
        max_count=("count", "max"),
        numbers=("number", lambda x: "|".join(x))
    )
    .reset_index()
    .sort_values("range_group")
)

# Round avg_count for cleaner display
group_summary["avg_count"] = group_summary["avg_count"].round(2)

# =======================
# SAVE OUTPUT
# =======================
group_summary.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

# =======================
# SUMMARY
# =======================
print(f"\n📊 Grouped High-Count Summary (≥ {COUNT_THRESHOLD})")
print(group_summary.head(10))
print(f"\n✅ Saved to: {OUTPUT_FILE}")
