import pymongo
import pandas as pd
import numpy as np
import json
import os

# ===================== SETTINGS =====================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000
RANGE_SIZE = 50

CSV_OUTPUT = "range_interval_patterns.csv"
JSON_OUTPUT = "range_interval_patterns.json"

# ===================== CONNECT DB =====================
client = pymongo.MongoClient(MONGO_URI)
col = client[DB_NAME][COLLECTION]

# ===================== BUILD RANGES =====================
ranges = [f"{i:04d}-{i+RANGE_SIZE-1:04d}" for i in range(0, 10000, RANGE_SIZE)]

def get_range_index(num):
    return num // RANGE_SIZE

# ===================== FETCH DB DATA =====================
dates = []
daily_counts = []

for doc in col.find({}, {"date": 1, "series": 1, "_id": 0}):
    date = doc.get("date", "")
    nums = []

    for s in doc.get("series", []):
        if s.get("prize") == PRIZE_FILTER:
            for n in s.get("numbers", []):
                try:
                    nums.append(int(n["number"]))
                except:
                    pass

    count_map = {r: 0 for r in ranges}
    for num in nums:
        idx = get_range_index(num)
        if idx < len(ranges):
            count_map[ranges[idx]] += 1

    dates.append(date)
    daily_counts.append(count_map)

df = pd.DataFrame(daily_counts)
df.insert(0, "Date", dates)  # first column = date

# ===================== ANALYZE INTERVALS =====================
interval_report = {}

for r in ranges:
    hits = df.index[df[r] > 0].tolist()  # row indexes where the range appears
    if len(hits) <= 1:
        continue  # no pattern possible
    
    intervals = np.diff(hits).tolist()  # difference between indexes (not real dates)

    # interval stats
    interval_report[r] = {
        "occurrences": len(hits),
        "indexes": hits,
        "intervals": intervals,
        "most_common_interval": int(pd.Series(intervals).mode()[0]),
        "avg_interval": float(np.mean(intervals)),
        "stability_score": round(100 - np.std(intervals) * 25, 2)  # 0-100
    }

# ===================== EXPORT CSV =====================
pd.DataFrame([
    {
        "Range": r,
        "Occurrences": info["occurrences"],
        "Most Common Interval": info["most_common_interval"],
        "Average Interval": info["avg_interval"],
        "Stability Score (0-100)": info["stability_score"],
    }
    for r, info in interval_report.items()
]).to_csv(CSV_OUTPUT, index=False)

# ===================== EXPORT JSON =====================
with open(JSON_OUTPUT, "w") as f:
    json.dump(interval_report, f, indent=4)

# ===================== DONE! =====================
print("\n🎉 Patterns Extracted Successfully!")
print(f"📁 CSV Saved → {os.path.abspath(CSV_OUTPUT)}")
print(f"📁 JSON Saved → {os.path.abspath(JSON_OUTPUT)}")
