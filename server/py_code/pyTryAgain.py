import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib
from tqdm import tqdm

# ==========================
# CONFIG
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
LOOKAHEAD_DAYS = 7  # label window

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# ==========================
# LOAD DATA
# ==========================
df = pd.DataFrame(list(lottery_data.find()))
df["date"] = pd.to_datetime(df["date"], errors="coerce")

# Flatten prize data
rows = []
for _, row in df.iterrows():
    for series in row["series"]:
        prize = series["prize"]
        for num in series["numbers"]:
            rows.append({"date": row["date"], "number": num["number"], "prize": prize})
flat = pd.DataFrame(rows).sort_values("date")

# ==========================
# FEATURE ENGINEERING (no leakage)
# ==========================
features = []
all_dates = sorted(flat["date"].unique())
numbers = flat["number"].unique()

print(f"🔄 Building dataset across {len(all_dates)} draw dates...")

for d in tqdm(all_dates, desc="Processing dates"):
    past_data = flat[flat["date"] < d]
    future_data = flat[(flat["date"] >= d) & (flat["date"] < d + timedelta(days=LOOKAHEAD_DAYS))]

    for num in numbers:
        num_df = past_data[past_data["number"] == num]

        # skip numbers with no history (optional)
        if num_df.empty:
            continue

        # frequency features
        freq_total = len(num_df)
        freq_7 = len(num_df[num_df["date"] > d - timedelta(days=7)])
        freq_30 = len(num_df[num_df["date"] > d - timedelta(days=30)])
        freq_90 = len(num_df[num_df["date"] > d - timedelta(days=90)])

        # recency
        last_seen = num_df["date"].max()
        days_since_last = (d - last_seen).days if pd.notnull(last_seen) else 9999

        # digit features
        digits = list(map(int, list(num)))
        sum_digits = sum(digits)
        even_count = sum(d % 2 == 0 for d in digits)

        # target: does number appear in future window?
        appeared_future = int(num in future_data["number"].values)

        features.append({
            "number": num,
            "freq_total": freq_total,
            "freq_7": freq_7,
            "freq_30": freq_30,
            "freq_90": freq_90,
            "days_since_last": days_since_last,
            "sum_digits": sum_digits,
            "even_count": even_count,
            "target": appeared_future
        })

dataset = pd.DataFrame(features)

# ==========================
# TRAIN MODEL
# ==========================
X = dataset.drop(columns=["number", "target"])
y = dataset["target"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=True, random_state=42)

print("⚡ Training model...")
model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X_train, y_train)

# ==========================
# EVALUATION
# ==========================
y_pred = model.predict(X_test)
print("✅ Accuracy:", accuracy_score(y_test, y_pred))
print(classification_report(y_test, y_pred))

# Save model
joblib.dump(model, "lottery_predictor1.pkl")
print("💾 Model saved as lottery_predictor1.pkl")
