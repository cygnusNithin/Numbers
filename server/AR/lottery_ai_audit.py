from pymongo import MongoClient
import pandas as pd
from collections import Counter
import numpy as np
from sklearn.ensemble import IsolationForest
import matplotlib.pyplot as plt

# =======================
# DATABASE CONNECTION
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION]

# =======================
# FEATURE EXTRACTION
# =======================
def extract_features(prize_filter=None):
    query = {}
    if prize_filter:
        query["series.prize"] = prize_filter

    cursor = collection.find(query, {"date": 1, "series": 1, "_id": 0})

    draw_features = []

    for doc in cursor:
        date = doc["date"]
        numbers = []

        for s in doc["series"]:
            if prize_filter is None or s["prize"] == prize_filter:
                for n in s["numbers"]:
                    numbers.append(n["number"])

        if not numbers:
            continue

        digit_sums = []
        even_digits = 0
        odd_digits = 0
        high_digits = 0
        low_digits = 0
        repeat_count = 0
        last_digits = []

        for num in numbers:
            digits = [int(d) for d in num]
            digit_sums.append(sum(digits))

            even_digits += sum(1 for d in digits if d % 2 == 0)
            odd_digits += sum(1 for d in digits if d % 2 == 1)
            high_digits += sum(1 for d in digits if d >= 5)
            low_digits += sum(1 for d in digits if d < 5)

            if len(set(digits)) < len(digits):
                repeat_count += 1

            last_digits.append(int(num[-1]))

        total_digits = even_digits + odd_digits
        last_digit_counts = Counter(last_digits)

        feature_row = {
            "date": date,
            "mean_digit_sum": np.mean(digit_sums),
            "even_ratio": even_digits / total_digits,
            "high_digit_ratio": high_digits / total_digits,
            "repeat_digit_ratio": repeat_count / len(numbers),
        }

        for d in range(10):
            feature_row[f"last_digit_{d}"] = last_digit_counts.get(d, 0)

        draw_features.append(feature_row)

    return pd.DataFrame(draw_features)

# =======================
# ANOMALY DETECTION
# =======================
def run_anomaly_detection(df, label):
    df_model = df.drop(columns=["date"])

    model = IsolationForest(contamination=0.02, random_state=42)
    model.fit(df_model)

    df["anomaly_score"] = model.decision_function(df_model)
    df["anomaly_flag"] = model.predict(df_model)  # -1 = anomaly

    anomalies = df[df["anomaly_flag"] == -1]

    print(f"\n🚨 Anomalies detected in {label}:")
    print(anomalies[["date", "anomaly_score"]].sort_values("anomaly_score"))

    return df

# =======================
# RUN ALL DATA CHECK
# =======================
df_all = extract_features()
df_all = run_anomaly_detection(df_all, "ALL PRIZES COMBINED")

# =======================
# DRIFT VISUALIZATION
# =======================

# Convert date column to real datetime
df_all["date"] = pd.to_datetime(df_all["date"], dayfirst=True)

plt.figure(figsize=(12,5))
plt.plot(df_all["date"], df_all["anomaly_score"])

# Highlight suspected drift period
plt.axvspan(pd.to_datetime("2025-05-01"), pd.to_datetime("2025-06-15"), alpha=0.2)

plt.title("Anomaly Score Over Time (All Prizes)")
plt.xlabel("Date")
plt.ylabel("Anomaly Score")
plt.grid(True)
plt.show()

# =======================
# PERIOD COMPARISON TEST
# =======================

before = df_all[df_all["date"] < "2025-05-01"]
during = df_all[(df_all["date"] >= "2025-05-01") & (df_all["date"] <= "2025-06-15")]

features_to_check = [
    "mean_digit_sum",
    "even_ratio",
    "high_digit_ratio",
    "repeat_digit_ratio"
]

print("\n📊 FEATURE COMPARISON (Before vs Drift Period)\n")

for f in features_to_check:
    before_mean = before[f].mean()
    during_mean = during[f].mean()
    diff = during_mean - before_mean

    print(f"{f}:")
    print(f"   Before Avg : {before_mean:.4f}")
    print(f"   During Avg : {during_mean:.4f}")
    print(f"   Change     : {diff:+.4f}\n")



# =======================
# RUN CATEGORY CHECKS
# =======================
prizes = [5000, 2000, 1000, 500, 200, 100]

for prize in prizes:
    df_cat = extract_features(prize_filter=prize)
    if len(df_cat) > 10:  # ensure enough data
        run_anomaly_detection(df_cat, f"₹{prize} CATEGORY")
