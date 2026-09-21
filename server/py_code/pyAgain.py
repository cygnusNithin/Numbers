import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import timedelta
import joblib
from tqdm import tqdm   # ✅ progress bar

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
MODEL_PATH = "lottery_predictor1.pkl"
TOP_N = 10

# Load model
model = joblib.load(MODEL_PATH)

# Connect MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# Load latest dataset
# =======================
df = pd.DataFrame(list(lottery_data.find()))
df["date"] = pd.to_datetime(df["date"], errors="coerce")

# Flatten prize data
rows = []
for _, row in df.iterrows():
    for series in row["series"]:
        prize = series["prize"]
        for num in series["numbers"]:
            rows.append({"date": row["date"], "number": num["number"], "prize": prize})
flat = pd.DataFrame(rows)

# Latest draw date
now = flat["date"].max()

# =======================
# Feature Engineering (with progress bar)
# =======================
features = []
numbers = flat["number"].unique()

print(f"🔄 Generating features for {len(numbers)} numbers...")
for num in tqdm(numbers, desc="Building features"):
    num_df = flat[flat["number"] == num].sort_values("date")
    last_seen = num_df["date"].max()
    freq_total = len(num_df)

    freq_7 = len(num_df[num_df["date"] > now - timedelta(days=7)])
    freq_30 = len(num_df[num_df["date"] > now - timedelta(days=30)])
    freq_90 = len(num_df[num_df["date"] > now - timedelta(days=90)])

    days_since_last = (now - last_seen).days if pd.notnull(last_seen) else 9999

    digits = list(map(int, list(num)))
    sum_digits = sum(digits)
    even_count = sum(d % 2 == 0 for d in digits)

    features.append({
        "number": num,
        "freq_total": freq_total,
        "freq_7": freq_7,
        "freq_30": freq_30,
        "freq_90": freq_90,
        "days_since_last": days_since_last,
        "sum_digits": sum_digits,
        "even_count": even_count,
    })

dataset = pd.DataFrame(features)

# =======================
# Predict probabilities (with progress bar)
# =======================
X = dataset.drop(columns=["number"])

print("⚡ Predicting probabilities...")
probs = []
batch_size = 1000  # predict in batches to avoid memory spikes
for i in tqdm(range(0, len(X), batch_size), desc="Predicting"):
    batch = X.iloc[i:i+batch_size]
    batch_probs = model.predict_proba(batch)[:, 1]
    probs.extend(batch_probs)

dataset["prob"] = probs

# Top N numbers
topN = dataset.sort_values("prob", ascending=False).head(TOP_N)
print("\n🎯 Top predicted numbers:")
print(topN[["number", "prob"]])
