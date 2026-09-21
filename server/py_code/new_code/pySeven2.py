import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import numpy as np
from tqdm import tqdm

# ==========================
# CONFIGURATION
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
OUTPUT_FILE = "predicted_5000_candidates.csv"
TARGET_DATE = datetime(2025, 11, 9)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# ==========================
# HELPERS
# ==========================
def parse_date(d):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_data():
    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "prize": "$series.prize",
            "date": "$date"
        }}
    ]
    data = list(lottery_data.aggregate(pipeline))
    df = pd.DataFrame(data)
    df["parsed_date"] = df["date"].apply(parse_date)
    df = df[df["parsed_date"].notnull()]
    return df

# ==========================
# MAIN
# ==========================
print("🔄 Fetching data...")
df = get_data()
df.sort_values("parsed_date", inplace=True)

prizes = [100, 200, 500, 1000, 2000, 5000]
weight_map = {100: 1.0, 200: 1.2, 500: 1.5, 1000: 2.0, 2000: 2.5, 5000: 3.0}

records = []
for num, grp in tqdm(df.groupby("number"), total=df["number"].nunique()):
    grp = grp.sort_values("parsed_date")
    total_counts = grp["prize"].value_counts().to_dict()
    last_date = grp["parsed_date"].max()
    recency_days = (TARGET_DATE - last_date).days
    recency_weight = np.exp(-recency_days / 180)  # decay ~6 months
    
    score = 0
    for p, c in total_counts.items():
        score += c * weight_map.get(p, 1.0)
    score *= recency_weight

    records.append({
        "number": str(num).zfill(4),
        "last_seen": last_date.strftime("%d/%m/%Y"),
        "days_since_seen": recency_days,
        "score": round(score, 4),
        "counts": total_counts
    })

pred_df = pd.DataFrame(records)
pred_df.sort_values("score", ascending=False, inplace=True)
pred_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

print(f"✅ Predicted next ₹5000 candidates saved -> {OUTPUT_FILE}")
print("\nTop 15 likely ₹5000 candidates:")
print(pred_df.head(15))
