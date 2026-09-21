import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
LOW_PRIZES = [100, 500, 1000]   # ✅ include 1000 now
TARGET_PRIZE = 5000
OUTPUT_FILE = "new_5000_numbers_appearances.csv"

# =======================
# DB SETUP
# =======================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# HELPERS
# =======================
def parse_date(d):
    """Convert any date format into datetime (Indian DD/MM/YYYY structure)."""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None


def get_prize_data(prize):
    """Fetch all numbers & dates for a specific prize."""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date",
            "prize": "$series.prize"
        }}
    ]
    data = list(lottery_data.aggregate(pipeline))
    df = pd.DataFrame(data)
    df["parsed_date"] = df["date"].apply(parse_date)
    df = df[df["parsed_date"].notnull()]
    df.sort_values("parsed_date", inplace=True)
    return df


# =======================
# FETCH DATA
# =======================
print("🔄 Fetching ₹100, ₹500, ₹1000, and ₹5000 prize data...")
dfs = {p: get_prize_data(p) for p in LOW_PRIZES + [TARGET_PRIZE]}

# =======================
# GET NEW NUMBERS FROM 5000 (DAY 1)
# =======================
df_5000 = dfs[TARGET_PRIZE]
df_5000 = df_5000.sort_values("parsed_date")
seen = set()
new_5000 = []

for _, row in df_5000.iterrows():
    num = str(row["number"]).zfill(4)
    if num not in seen:
        seen.add(num)
        new_5000.append({
            "number": num,
            "first_seen_in_5000": row["parsed_date"]
        })

print(f"✅ Found {len(new_5000)} new ₹5000 numbers from day 1.")

# =======================
# TRACK ALL APPEARANCES
# =======================
records = []
print("🔍 Tracking each new 5000 number across ₹100, ₹500, ₹1000, and ₹5000...")

all_data = pd.concat([dfs[p] for p in LOW_PRIZES + [TARGET_PRIZE]])

for item in tqdm(new_5000, total=len(new_5000)):
    num = item["number"]
    first_5000_date = item["first_seen_in_5000"]

    # All occurrences across 100–5000
    entries = all_data[all_data["number"] == num]
    if entries.empty:
        continue

    entries = entries.sort_values("parsed_date")

    # Timeline across all prizes
    timeline = [
        f"{d.strftime('%d/%m/%Y')} (₹{p})"
        for d, p in zip(entries["parsed_date"], entries["prize"])
    ]

    records.append({
        "number": num,
        "first_seen_in_5000": first_5000_date.strftime("%d/%m/%Y"),
        "first_seen_date_sort": first_5000_date,  # for proper sorting
        "appearances_timeline": " → ".join(timeline),
        "total_appearances": len(timeline),
        "in_100": (entries["prize"] == 100).sum(),
        "in_500": (entries["prize"] == 500).sum(),
        "in_1000": (entries["prize"] == 1000).sum(),
        "in_5000": (entries["prize"] == 5000).sum(),
    })

# =======================
# SORT & SAVE (INDIAN DATE STRUCTURE)
# =======================
out_df = pd.DataFrame(records)

# 🗓️ Sort chronologically from day 1 → last (using datetime)
out_df.sort_values(["first_seen_date_sort", "number"], inplace=True)

# Drop sorting helper
out_df.drop(columns=["first_seen_date_sort"], inplace=True)

# Save file
out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

# =======================
# SUMMARY
# =======================
print(f"\n✅ Saved detailed number appearance history → {OUTPUT_FILE}")
print(f"📊 Tracked {len(out_df)} numbers from {out_df['first_seen_in_5000'].min()} to {out_df['first_seen_in_5000'].max()}")
print(out_df.head(10))
