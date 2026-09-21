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

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

def parse_date(d):
    """Try parsing with multiple formats and normalize to DD/MM/YYYY"""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_all_5000_numbers():
    """Fetch all numbers & dates where prize=5000"""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": 5000}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date"
        }}
    ]
    return list(lottery_data.aggregate(pipeline))

print("🔄 Fetching all 5000 prize numbers from DB...")
data = get_all_5000_numbers()
df = pd.DataFrame(data)

print(f"📊 Total records fetched: {len(df)}")

patterns = []
unique_numbers = df["number"].unique()

print(f"🔄 Analyzing {len(unique_numbers)} unique numbers...")
for num in tqdm(unique_numbers, total=len(unique_numbers), desc="Processing numbers"):
    num_df = df[df["number"] == num]

    # Parse dates
    dt_list = [parse_date(d) for d in num_df["date"] if parse_date(d)]
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
        "number": str(num).zfill(4),
        "total_hits": len(dt_list),
        "dates": "|".join(d.strftime("%d/%m/%Y") for d in dt_list),
        "avg_gap_days": sum(gaps)/len(gaps) if gaps else None,
        "weekday_counts": weekday_counts,
        "month_counts": month_counts
    })

# Save results
out_df = pd.DataFrame(patterns)
out_df.to_csv("5000_number_patterns1.csv", index=False, encoding="utf-8")

print("✅ Saved detailed number patterns to 5000_number_patterns1.csv")
