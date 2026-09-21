import pandas as pd
import numpy as np
import datetime
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
import matplotlib.pyplot as plt
import csv

# 1. Load dataset
df = pd.read_csv("lotteryData.csv")
df["number"] = df["number"].astype(str).str.zfill(4)

# Convert date → features
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
df["day"] = df["date"].dt.day
df["month"] = df["date"].dt.month
df["weekday"] = df["date"].dt.weekday

print("✅ Data loaded:", df.head())

# 2. Restrict to rolling window (last 12 months)
end_date = df["date"].max()
start_date = end_date - pd.DateOffset(months=12)
df_window = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

print(f"📅 Training window: {start_date.date()} → {end_date.date()}")
print("📊 Training samples:", len(df_window))

# 3. Build dataset with NEGATIVE sampling
NEGATIVE_SAMPLES = 18
all_numbers = np.arange(10000)

csv_file = "training_data.csv"
with open(csv_file, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["prize", "day", "month", "weekday", "number", "target"])
    writer.writeheader()

    for _, row in tqdm(df_window.iterrows(), total=len(df_window), desc="Building dataset"):
        # Positive sample
        writer.writerow({
            "prize": row["prize"],
            "day": row["day"],
            "month": row["month"],
            "weekday": row["weekday"],
            "number": row["number"],
            "target": 1
        })

        # Negative samples
        negatives = np.random.choice(all_numbers, size=NEGATIVE_SAMPLES, replace=False)
        for num in negatives:
            if str(num).zfill(4) != row["number"]:
                writer.writerow({
                    "prize": row["prize"],
                    "day": row["day"],
                    "month": row["month"],
                    "weekday": row["weekday"],
                    "number": str(num).zfill(4),
                    "target": 0
                })

print("✅ Training dataset written to", csv_file)

# 4. Reload dataset
clf_df = pd.read_csv(csv_file)
print("📊 Final dataset size:", clf_df.shape)

# Encode number
clf_df["number_int"] = clf_df["number"].astype(int)

# Features & target
X = clf_df[["prize", "day", "month", "weekday", "number_int"]]
y = clf_df["target"]

# Train/test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.1, random_state=42, stratify=y
)

# 5. Train Random Forest + Calibration
rf = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    class_weight="balanced_subsample",
    n_jobs=-1
)

model = CalibratedClassifierCV(
    estimator=rf,      # ✅ sklearn ≥1.4 uses "estimator"
    method="isotonic",
    cv=3
)

print("⏳ Training classifier...")
model.fit(X_train, y_train)
print("✅ Model trained (with calibration)")
print(f"📊 Accuracy on test: {model.score(X_test, y_test):.4f}")

# 6. Predict for a future date (Aug 1, 2025)
future_date = datetime.datetime(2025, 8, 1)
print(f"\n📅 Predicting for {future_date.strftime('%d-%m-%Y')} (weekday={future_date.weekday()})")

future_sample = pd.DataFrame({
    "prize": [5000]*10000,
    "day": [future_date.day]*10000,
    "month": [future_date.month]*10000,
    "weekday": [future_date.weekday()]*10000,
    "number_int": list(range(10000))
})
future_sample["number"] = [str(i).zfill(4) for i in range(10000)]

X_future = future_sample[["prize", "day", "month", "weekday", "number_int"]]

batch_size = 1000
probs = []
for i in tqdm(range(0, len(X_future), batch_size), desc="Predicting"):
    batch = X_future.iloc[i:i+batch_size]
    batch_probs = model.predict_proba(batch)[:, 1]
    probs.extend(batch_probs)

future_sample["prob"] = np.array(probs)

# 7. Pick Top 18 numbers
top_preds = future_sample.sort_values("prob", ascending=False).head(18)
print(f"\n🎯 Top 18 predicted numbers for {future_date.strftime('%d-%m-%Y')}:\n", top_preds[["number", "prob"]])

# 8. Visualization
plt.figure(figsize=(10,5))
top_preds.plot(x="number", y="prob", kind="bar", legend=False, ax=plt.gca())
plt.title(f"Top 18 Predicted Numbers for {future_date.strftime('%d-%m-%Y')}")
plt.ylabel("Calibrated Probability")
plt.show()

# 9. EXTRA ANALYSIS ------------------------------------------------
print("\n📊 EXTRA ANALYSIS (Patterns & Statistics)\n")

# Most common numbers per month
top_month = df.groupby(["month", "number"]).size().reset_index(name="count").sort_values("count", ascending=False).head(40)
print("🔥 Top numbers per month:\n", top_month)

# Most common numbers per weekday
top_weekday = df.groupby(["weekday", "number"]).size().reset_index(name="count").sort_values("count", ascending=False).head(40)
print("\n🔥 Top numbers per weekday (0=Monday ... 6=Sunday):\n", top_weekday)

# Most common last 2 digits
df["last2"] = df["number"].str[-2:]
print("\n🔢 Most common last 2 digits:\n", df["last2"].value_counts().head(10))

# Most common last 3 digits
df["last3"] = df["number"].str[-3:]
print("\n🔢 Most common last 3 digits:\n", df["last3"].value_counts().head(10))

# Adjacent number check
nums = df["number"].astype(int)
adjacent_hits = ((nums + 1).isin(nums)) | ((nums - 1).isin(nums))
print(f"\n🔗 Found {adjacent_hits.sum()} winners that had an adjacent neighbor also winning.\n")

# Digit frequency per position
digit_freq = pd.DataFrame(0, index=range(10), columns=["d1","d2","d3","d4"])
for num in df["number"]:
    for i, d in enumerate(num):
        digit_freq.iloc[int(d), i] += 1

print("🔥 Digit frequency per position (rows=digit, cols=position):\n")
print(digit_freq)
