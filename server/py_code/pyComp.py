import pandas as pd
from pymongo import MongoClient

# =========================
# CONFIG
# =========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

OLD_FILE = "all_remaining_attempts.csv"   # snapshot before 26/08/2025
NEW_FILE = "all_remaining_attempts1.csv"  # snapshot after including new data
OUT_FILE = "comparison_with_new_dates.csv"

CUTOFF_DATE = pd.to_datetime("26/08/2025", format="%d/%m/%Y")

# =========================
# LOAD SNAPSHOTS
# =========================
old_df = pd.read_csv(OLD_FILE)
new_df = pd.read_csv(NEW_FILE)

# MongoDB connect
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =========================
# GET 5000 PRIZE DATA FROM DB
# =========================
pipeline = [
    {"$unwind": "$series"},
    {"$match": {"series.prize": 5000}},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "date": 1,
        "number": "$series.numbers.number"
    }}
]

records = list(lottery_data.aggregate(pipeline))

# Organize into dict → number : {dates}
num_to_dates = {}
for rec in records:
    num = rec["number"]
    d = pd.to_datetime(rec["date"], format="%d.%m.%Y", errors="coerce")
    if pd.isnull(d):
        continue
    if num not in num_to_dates:
        num_to_dates[num] = []
    num_to_dates[num].append(d)

# =========================
# COMPARE OLD vs NEW
# =========================
merged = pd.merge(old_df, new_df, on="number", suffixes=("_old", "_new"))

rows = []
for _, row in merged.iterrows():
    count_old = row["count_old"]
    count_new = row["count_new"]

    if count_new > count_old:  # number appeared more times
        diff = count_new - count_old

        # all dates for this number
        all_dates = sorted(num_to_dates.get(row["number"], []))

        # select only dates >= cutoff
        new_dates = [d.strftime("%d/%m/%Y") for d in all_dates if d >= CUTOFF_DATE]

        # keep only last `diff` dates in case of multiple increments
        new_dates = new_dates[-diff:] if diff > 0 else []

        rows.append({
            "number": row["number"],
            "count_old": count_old,
            "count_new": count_new,
            "count_diff": f"{diff:+d}",
            "remaining_attempts_old": row["remaining_attempts_old"],
            "remaining_attempts_new": row["remaining_attempts_new"],
            "new_dates_added": "{" + ",".join(new_dates) + "}"
        })

# =========================
# SAVE OUTPUT
# =========================
out_df = pd.DataFrame(rows)
out_df.to_csv(OUT_FILE, index=False, encoding="utf-8")

print(f"✅ Comparison with new dates saved: {OUT_FILE}")
