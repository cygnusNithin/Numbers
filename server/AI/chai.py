import pandas as pd
import numpy as np
from pymongo import MongoClient

# -----------------------------
# MongoDB connection
# -----------------------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
SORT_DESC = True  # unused by aggregate, kept for compatibility

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]

# -----------------------------
# Load data from MongoDB (schema-aware)
# -----------------------------
# Documents have: date (string), series: [{prize, numbers: [{number, count}]}]
pipeline = [
    {"$unwind": "$series"},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "date": "$date",
        "prize": "$series.prize",
        "number": "$series.numbers.number",
        "count": {"$ifNull": ["$series.numbers.count", 1]}
    }}
]

rows = list(collection.aggregate(pipeline, allowDiskUse=True))
df = pd.DataFrame(rows)
if df.empty:
    raise SystemExit("No data returned from MongoDB; check collection or pipeline.")

# -----------------------------
# Normalize fields
# -----------------------------
def parse_date_any(s):
    # Accept DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    return pd.to_datetime(s, errors="coerce")

# Parse date and drop invalids
df["date"] = df["date"].apply(parse_date_any)
df = df.dropna(subset=["date"]).copy()

# Normalize number as 4-digit string
df["number"] = df["number"].astype(str).str.strip().str.zfill(4)

# Prize and count to numeric
df["prize"] = pd.to_numeric(df["prize"], errors="coerce").astype("Int64")
df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)

# Only expected prize set (if you want to enforce)
valid_prizes = {100, 200, 500, 1000, 2000, 5000}
df = df[df["prize"].isin(valid_prizes)].copy()

# Time features
df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.month
# ISO week (ensure int)
df["week"] = df["date"].dt.isocalendar().week.astype(int)
df["day_of_week"] = df["date"].dt.dayofweek  # 0=Mon
df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

# Number id (0..9999)
df["number_id"] = df["number"].astype(int)

# -----------------------------
# Example analysis
# -----------------------------
# Daily counts per (date, number) across all prizes (sum counts)
daily_counts = (
    df.groupby(["date", "number"], as_index=False)["count"]
      .sum()
      .rename(columns={"count": "hits"})
)

# Also daily counts by prize (if you need per-prize series)
daily_counts_by_prize = (
    df.groupby(["date", "prize", "number"], as_index=False)["count"]
      .sum()
      .rename(columns={"count": "hits"})
)

# Pivot to time series per number (overall, not per-prize)
ts = daily_counts.pivot(index="date", columns="number", values="hits").fillna(0).sort_index()

# Rolling features (simple moving averages on the time series)
# NOTE: This can be large if you have many days × 10,000 numbers
roll_7 = ts.rolling(7, min_periods=1).mean().add_suffix("_ma7")
roll_30 = ts.rolling(30, min_periods=1).mean().add_suffix("_ma30")
roll_90 = ts.rolling(90, min_periods=1).mean().add_suffix("_ma90")

# Combine
ts_features = pd.concat([ts, roll_7, roll_30, roll_90], axis=1)

# -----------------------------
# Export summaries
# -----------------------------
# Total hits per number (sum of counts across all prizes/days)
total_hits = (
    df.groupby("number")["count"].sum()
      .reset_index(name="total_hits")
      .sort_values("total_hits", ascending=False)
)

# Yearly hits per number
year_hits = (
    df.groupby(["number", "year"])["count"].sum()
      .reset_index(name="hits_year")
      .sort_values(["year", "hits_year"], ascending=[True, False])
)

# "Category" hits per number -> in this schema, category is 'prize'
cat_hits = (
    df.groupby(["number", "prize"])["count"].sum()
      .reset_index(name="hits_category")
      .sort_values(["prize", "hits_category"], ascending=[True, False])
)

# Save to CSV
total_hits.to_csv("total_hits.csv", index=False)
year_hits.to_csv("yearly_hits.csv", index=False)
# Keep the original filename 'category_hits.csv' but it's per 'prize'
cat_hits.to_csv("category_hits.csv", index=False)

# Time series features (this can be big)
# If it's too large, see memory tips below.
ts_features.to_csv("time_series_features.csv")

print("✅ Saved: total_hits.csv, yearly_hits.csv, category_hits.csv, time_series_features.csv")

# -----------------------------
# Optional: also save per-prize daily series
# -----------------------------
# Example: per-prize pivot for prize=5000
# d5k = daily_counts_by_prize[daily_counts_by_prize["prize"] == 5000]
# ts_5k = d5k.pivot(index="date", columns="number", values="hits").fillna(0).sort_index()
# ts_5k.to_csv("time_series_5000.csv")

# -----------------------------
# Memory/performance tips (if needed)
# -----------------------------
# - The wide ts_features table is date × (10,000 + 10,000*3) columns; it can be very large.
#   If it’s too big:
#     1) Only compute rolling means for the top N numbers (by total_hits).
#     2) Or only save the base ts (without roll_7/30/90).
#     3) Or compute per-prize time series (fewer active numbers per prize).
# - If you hit dtype warnings on read, you can set low_memory=False when reading back CSVs.