import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm   # ✅ Progress bar

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000       # 🎯 Analyze 5000 prize
SORT_DESC = True           # ✅ Change to False for ascending order
TO_DATE = "01/01/2023"     # 📅 Custom cutoff date (DD/MM/YYYY)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# HELPERS
# =======================
def parse_date(d):
    """Try parsing with multiple formats and normalize to datetime"""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_all_prize_numbers(prize):
    """Fetch all numbers & dates for a specific prize"""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date"
        }}
    ]
    return list(lottery_data.aggregate(pipeline))

# =======================
# MAIN
# =======================
print(f"🔄 Fetching all {PRIZE_FILTER} prize numbers from DB...")
data = get_all_prize_numbers(PRIZE_FILTER)
df = pd.DataFrame(data)
print(f"📊 Total records fetched: {len(df)}")

# 🎯 Parse and filter by TO_DATE
to_date_obj = parse_date(TO_DATE)
df["parsed_date"] = df["date"].apply(parse_date)
df = df[df["parsed_date"].notnull()]              # Remove invalid dates
df = df[df["parsed_date"] <= to_date_obj]         # Filter to cutoff date

print(f"📅 Records up to {TO_DATE}: {len(df)} remaining")

# 🎯 Find dynamic MAX_COUNT from filtered data
counts = df["number"].value_counts()
MAX_COUNT = counts.max() if not counts.empty else 0
print(f"🎯 MAX_COUNT (highest repeat for prize {PRIZE_FILTER}) = {MAX_COUNT}")

patterns = []
unique_numbers = df["number"].unique()

print(f"🔄 Analyzing {len(unique_numbers)} unique numbers...")
for num in tqdm(unique_numbers, total=len(unique_numbers), desc="Processing numbers"):
    num_df = df[df["number"] == num]

    # Parse dates again (already filtered)
    dt_list = sorted(num_df["parsed_date"].tolist())
    if not dt_list:
        continue

    gaps = [(dt_list[i+1] - dt_list[i]).days for i in range(len(dt_list)-1)]

    # Weekday counts
    weekdays = [d.strftime("%A") for d in dt_list]
    weekday_counts = pd.Series(weekdays).value_counts().to_dict()

    # Month counts
    months = [d.strftime("%B") for d in dt_list]
    month_counts = pd.Series(months).value_counts().to_dict()

    total_hits = len(dt_list)

    # Store results
    patterns.append({
        "number": str(num).zfill(4),
        "total_hits": total_hits,
        "remaining_to_max": max(0, MAX_COUNT - total_hits),
        "dates": "|".join(d.strftime("%d/%m/%Y") for d in dt_list),
        "avg_gap_days": sum(gaps)/len(gaps) if gaps else None,
        "weekday_counts": weekday_counts,
        "month_counts": month_counts
    })

# =======================
# SORT & SAVE
# =======================
out_df = pd.DataFrame(patterns)

# 🧮 Sort by total_hits (desc/asc) then number (asc)
out_df = out_df.sort_values(
    by=["total_hits", "number"],
    ascending=[not SORT_DESC, True]
)

out_file = f"5000_number_patterns_upto_{TO_DATE.replace('/', '-')}.csv"
out_df.to_csv(out_file, index=False, encoding="utf-8")

print(f"✅ Saved detailed number patterns up to {TO_DATE} → {out_file}")
