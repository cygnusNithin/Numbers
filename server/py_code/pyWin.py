#!/usr/bin/env python3
"""
Generate 5000-prize analysis:
- total_count (all history)
- remaining_to_12 = max(0, MAX_COUNT - total_count)
- increase_after_cutoff = how many times it appeared on/after CUTOFF_DATE
- dates_after_cutoff = pipe-separated list of those dates (DD/MM/YYYY)

Saves CSV: 5000_analysis_since_2025-08-26.csv
"""
from pymongo import MongoClient
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import csv

# -------------------------
# CONFIG
# -------------------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

PRIZE_FILTER = 5000
CUTOFF_STR = "26/08/2025"     # inclusive cutoff date (day/month/year)
CUTOFF_DATE = datetime.strptime(CUTOFF_STR, "%d/%m/%Y")
MAX_COUNT = 12                # cap you specified
OUT_CSV = "5000_analysis_since_2025-08-26.csv"

# -------------------------
# Helpers
# -------------------------
def parse_date_string(s):
    """
    Parse date strings produced by your DB schema (DD.MM.YYYY commonly),
    also supports DD/MM/YYYY, YYYY-MM-DD etc. Returns datetime or None.
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    # try common formats (most likely is %d.%m.%Y)
    fmts = ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    # fallback to pandas
    try:
        d = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.notnull(d):
            return d.to_pydatetime()
    except Exception:
        pass
    return None

# -------------------------
# Connect & aggregate
# -------------------------
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
coll = db[COLLECTION]

print("🔄 Running aggregation on MongoDB (this may take a minute)...")

# aggregate: get per-number total count and list of all dates (push)
pipeline = [
    {"$unwind": "$series"},
    {"$match": {"series.prize": PRIZE_FILTER}},
    {"$unwind": "$series.numbers"},
    {"$group": {
        "_id": "$series.numbers.number",
        "total_count": {"$sum": 1},
        "dates": {"$push": "$date"}   # may be strings like "26.08.2025"
    }},
    {"$sort": {"total_count": -1}}
]

cursor = coll.aggregate(pipeline, allowDiskUse=True)
rows = list(cursor)
print(f"🔎 Aggregation returned {len(rows)} unique numbers for prize {PRIZE_FILTER}.")

# -------------------------
# Process each number
# -------------------------
out_rows = []
print("🔄 Parsing dates and computing stats (progress shown)...")
for r in tqdm(rows, desc="Processing numbers"):
    number = str(r["_id"])
    total_count = int(r.get("total_count", 0))

    # parse all date strings into datetimes
    raw_dates = r.get("dates", []) or []
    parsed = []
    for s in raw_dates:
        d = parse_date_string(s)
        if d is not None:
            parsed.append(d)

    # find dates >= cutoff (inclusive)
    dates_after = [d for d in parsed if d >= CUTOFF_DATE]
    # convert to unique sorted string list (DD/MM/YYYY)
    dates_after_unique = sorted({dt.strftime("%d/%m/%Y") for dt in dates_after},
                                key=lambda x: datetime.strptime(x, "%d/%m/%Y"))

    increase_after_cutoff = len(dates_after)  # counts occurrences on/after cutoff
    # remaining to reach MAX_COUNT
    remaining_to_12 = MAX_COUNT - total_count
    if remaining_to_12 < 0:
        remaining_to_12 = 0
        exceeded_by = total_count - MAX_COUNT
    else:
        exceeded_by = 0

    out_rows.append({
        "number": number,
        "total_count": total_count,
        "remaining_to_12": remaining_to_12,
        "increase_after_2025-08-26": increase_after_cutoff,
        "dates_after_2025-08-26": "|".join(dates_after_unique),
        "exceeded_by": exceeded_by   # 0 normally; >0 if count > MAX_COUNT
    })

# -------------------------
# Save CSV
# -------------------------
df_out = pd.DataFrame(out_rows)
df_out = df_out.sort_values(["total_count", "number"], ascending=[False, True])

df_out.to_csv(OUT_CSV, index=False, encoding="utf-8")
print(f"✅ Saved analysis to {OUT_CSV}")
print(f"Rows: {len(df_out)}. Sample top 10:")
print(df_out.head(10).to_string(index=False))

client.close()
