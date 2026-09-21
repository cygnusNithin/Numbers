import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm

# =========================
# CONFIG
# =========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000
MAX_TARGET = 12
OUT_FILE = "5000_number_training_data_saturation.csv"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =========================
# HELPERS
# =========================
def parse_date(d):
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_all_prize_numbers(prize):
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {"number": "$series.numbers.number", "date": "$date"}}
    ]
    return list(lottery_data.aggregate(pipeline))

# =========================
# LOAD DATA
# =========================
print(f"🔄 Fetching all ₹{PRIZE_FILTER} prize numbers...")
data = get_all_prize_numbers(PRIZE_FILTER)
df = pd.DataFrame(data)
df["parsed_date"] = df["date"].apply(parse_date)
df = df[df["parsed_date"].notnull()]
df = df.sort_values("parsed_date").reset_index(drop=True)

all_numbers = set(range(10000))  # 0000–9999
seen_numbers = set()
timeline_summary = []

# =========================
# BUILD FEATURES + SATURATION
# =========================
records = []

print("🧮 Building features with saturation tracking...")

for idx, row in tqdm(df.iterrows(), total=len(df), ncols=90):
    num = int(row["number"])
    date = row["parsed_date"]
    
    # Check if number is new
    is_new = 1 if num not in seen_numbers else 0
    
    # Update seen numbers
    seen_numbers.add(num)
    
    # Saturation & daily stats
    unique_so_far = len(seen_numbers)
    saturation = unique_so_far / 10000
    
    # Count new vs repeat ratio (approximate)
    new_count = sum([1 for n in df[df["parsed_date"] <= date]["number"].unique() if n not in seen_numbers])
    repeat_count = unique_so_far - new_count
    new_ratio = new_count / (new_count + repeat_count + 1e-6)
    repeat_ratio = repeat_count / (new_count + repeat_count + 1e-6)
    
    # Previous hits for this number
    num_prev_dates = df[(df["number"] == num) & (df["parsed_date"] < date)]
    if not num_prev_dates.empty:
        last_date = num_prev_dates["parsed_date"].max()
        days_since_last = (date - last_date).days
        total_hits = len(num_prev_dates) + 1
    else:
        last_date = None
        days_since_last = 0
        total_hits = 1
    
    records.append({
        "number": num,
        "date": date.strftime("%Y-%m-%d"),
        "is_new_number": is_new,
        "unique_numbers_so_far": unique_so_far,
        "saturation_level": round(saturation, 4),
        "new_ratio": round(new_ratio, 4),
        "repeat_ratio": round(repeat_ratio, 4),
        "days_since_last": days_since_last,
        "total_hits": total_hits
    })

# =========================
# SAVE ML-READY DATASET
# =========================
feature_df = pd.DataFrame(records)
feature_df.to_csv(OUT_FILE, index=False, encoding="utf-8")
print(f"✅ Saved ML-ready dataset with saturation features → {OUT_FILE}")
print(feature_df.head(10))
