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
CSV_FILE = "5000_analysis_since_2025-08-26.csv"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# Load the analysis file
df = pd.read_csv(CSV_FILE)

def parse_date(d):
    """Try parsing with multiple formats and normalize to DD/MM/YYYY"""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_number_dates(num):
    """Fetch all dates when a number appeared in 5000 prize"""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": 5000}},
        {"$unwind": "$series.numbers"},
        {"$match": {"series.numbers.number": str(num).zfill(4)}},
        {"$group": {"_id": "$date"}}
    ]
    results = list(lottery_data.aggregate(pipeline))
    return sorted([r["_id"] for r in results if r["_id"]])

patterns = []

print(f"🔄 Analyzing {len(df)} numbers...")
for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing numbers"):
    num = str(row["number"]).zfill(4)
    dates = get_number_dates(num)

    # Convert to datetime safely
    dt_list = [parse_date(d) for d in dates if parse_date(d)]
    if not dt_list:
        continue

    dt_list = sorted(dt_list)
    gaps = [(dt_list[i+1] - dt_list[i]).days for i in range(len(dt_list)-1)]

    # Weekday counts
    weekdays = [d.strftime("%A") for d in dt_list]
    weekday_counts = pd.Series(weekdays).value_counts().to_dict()

    # Month counts
    months = [d.strftime("%B") for d in dt_list]
    month_counts = pd.Series(months).value_counts().to_dict()

    # Store results
    patterns.append({
        "number": num,
        "total_hits": len(dt_list),
        "dates": "|".join(d.strftime("%d/%m/%Y") for d in dt_list),  # normalized
        "avg_gap_days": sum(gaps)/len(gaps) if gaps else None,
        "weekday_counts": weekday_counts,
        "month_counts": month_counts
    })

# Save results
out_df = pd.DataFrame(patterns)
out_df.to_csv("5000_number_patterns.csv", index=False, encoding="utf-8")

print("✅ Saved detailed number patterns to 5000_number_patterns.csv")
