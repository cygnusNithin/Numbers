import pandas as pd
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB = "numbergrid"
COL = "lotterydatas"

client = MongoClient(MONGO_URI)
col = client[DB][COL]

pipeline = [
    {"$unwind": "$series"},
    {"$match": {"series.prize": 5000}},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "date": "$date",
        "number": "$series.numbers.number",
        "count": {"$ifNull": ["$series.numbers.count", 1]},
    }},
]
rows = list(col.aggregate(pipeline, allowDiskUse=True))
df = pd.DataFrame(rows)

# Parse dates
df["dt"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
df = df.dropna(subset=["dt"]).copy()

# Define trailing 5-year window ending at latest date in DB
end = df["dt"].max()
start = end - pd.DateOffset(years=5)

df_5y = df[(df["dt"] >= start) & (df["dt"] <= end)].copy()

# Total hits per number in 5 years (respect 'count')
hits_5y = df_5y.groupby("number")["count"].sum()

# Example: confirm for 4393
print("4393 hits in last 5 years:", int(hits_5y.get("4393", 0)))

# Distribution of totals
vc = hits_5y.value_counts().sort_index()
print("\nCounts per number over 5 years (value_counts):")
print(vc.head(25))  # look at 0..24
share_12 = vc.get(12, 0) / vc.sum() if vc.sum() else 0
print(f"\nShare of numbers with exactly 12 hits: {share_12:.2%}")