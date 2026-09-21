import pandas as pd
import numpy as np
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import matplotlib.pyplot as plt
import csv
import datetime   # ✅ for correct weekday calculation

# 1. Load dataset
df = pd.read_csv("lotteryData.csv")
df["number"] = df["number"].astype(str).str.zfill(4)

# Convert date → features
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
df["day"] = df["date"].dt.day
df["month"] = df["date"].dt.month
df["weekday"] = df["date"].dt.weekday

print("✅ Data loaded:", df.head())

# 2. Build dataset with NEGATIVE sampling (stream to CSV)
NEGATIVE_SAMPLES = 18
all_numbers = np.arange(10000)

csv_file = "training_data.csv"
with open(csv_file, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["prize", "day", "month", "weekday", "number", "target"])
    writer.writeheader()

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Building dataset"):
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

# 3. Reload dataset from CSV (safe, memory efficient)
clf_df = pd.read_csv(csv_file)
print("📊 Final dataset size:", clf_df.shape)

# Encode number
clf_df["number_int"] = clf_df["number"].astype(int)

# Features & target
X = clf_df[["prize", "day", "month", "weekday", "number_int"]]
y = clf_df["target"]

# 4. Train/test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.1, random_state=42, stratify=y
)

# 5. Train classifier
model = RandomForestClassifier(
    n_estimators=200, random_state=42, class_weight="balanced", n_jobs=-1
)
print("⏳ Training classifier...")
model.fit(X_train, y_train)
print("✅ Model trained as classifier")
print(f"📊 Accuracy on test: {model.score(X_test, y_test):.4f}")

# 6. Predict probabilities for ALL numbers (example: 01/08/2025, Friday)
future_date = datetime.datetime(2025, 8, 1)  # ✅ Date to predict
weekday = future_date.weekday()  # 0=Mon, 6=Sun

future_sample = pd.DataFrame({
    "prize": [5000]*10000,
    "day": [future_date.day]*10000,
    "month": [future_date.month]*10000,
    "weekday": [weekday]*10000,
    "number_int": list(range(10000))
})
future_sample["number"] = [str(i).zfill(4) for i in range(10000)]  # display only

# 🚨 Only keep features used in training
X_future = future_sample[["prize", "day", "month", "weekday", "number_int"]]

batch_size = 1000
probs = []

for i in tqdm(range(0, len(X_future), batch_size), desc="Predicting"):
    batch = X_future.iloc[i:i+batch_size]
    batch_probs = model.predict_proba(batch)[:, 1]
    probs.extend(batch_probs)

future_sample["prob"] = np.array(probs)

# 7. Top 20 predicted numbers
top_preds = future_sample.sort_values("prob", ascending=False).head(20)
print(f"\n🎯 Top predicted numbers for {future_date.strftime('%d/%m/%Y')}:\n", top_preds[["number", "prob"]])

# 8. Visualization – distribution of hot numbers
plt.figure(figsize=(10,5))
top_preds.plot(x="number", y="prob", kind="bar", legend=False, ax=plt.gca())
plt.title(f"Top 20 Predicted Numbers (Probability) - {future_date.strftime('%d/%m/%Y')}")
plt.ylabel("Probability")
plt.show()
