import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib
from tqdm import tqdm   # ✅ progress bar

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

# flatten prize data
rows = []
for _, row in df.iterrows():
    for series in row["series"]:
        prize = series["prize"]
        for num in series["numbers"]:
            rows.append({"date": row["date"], "number": num["number"], "prize": prize})
flat = pd.DataFrame(rows)

# ==========================
# FEATURE ENGINEERING
# ==========================
features = []
numbers = flat["number"].unique()
now = flat["date"].max()

print(f"🔄 Generating features for {len(numbers)} numbers...")

for num in tqdm(numbers, desc="Building features"):
    num_df = flat[flat["number"] == num].sort_values("date")
    last_seen = num_df["date"].max()
    freq_total = len(num_df)

    # frequency in windows
    freq_7 = len(num_df[num_df["date"] > now - timedelta(days=7)])
    freq_30 = len(num_df[num_df["date"] > now - timedelta(days=30)])
    freq_90 = len(num_df[num_df["date"] > now - timedelta(days=90)])

    # recency
    days_since_last = (now - last_seen).days if pd.notnull(last_seen) else 9999

    # digit features
    digits = list(map(int, list(num)))
    sum_digits = sum(digits)
    even_count = sum(d % 2 == 0 for d in digits)

    # target: will it appear in next LOOKAHEAD_DAYS?
    appeared_future = int(len(num_df[num_df["date"] > now]) > 0)

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
print("⚡ Training model...")
X = dataset.drop(columns=["number", "target"])
y = dataset["target"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

# ==========================
# EVALUATION
# ==========================
y_pred = model.predict(X_test)
print("✅ Accuracy:", accuracy_score(y_test, y_pred))
print(classification_report(y_test, y_pred))

# save model
joblib.dump(model, "lottery_predictor.pkl")
print("💾 Model saved as lottery_predictor.pkl")
