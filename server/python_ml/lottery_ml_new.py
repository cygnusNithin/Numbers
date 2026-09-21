import pandas as pd
import numpy as np
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import matplotlib.pyplot as plt
import csv
import datetime

# 1. Load dataset
df = pd.read_csv("lotteryData.csv")
df["number"] = df["number"].astype(str).str.zfill(4)

# Convert date → features
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
df["day"] = df["date"].dt.day
df["month"] = df["date"].dt.month
df["weekday"] = df["date"].dt.weekday  # 0=Monday, 6=Sunday

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

# 3. Reload dataset from CSV
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

# 6. Predict probabilities for future date
future_date = datetime.datetime(2025, 8, 1)  # Example: Aug 1, 2025
print(f"\n📅 Predicting for {future_date.strftime('%d-%m-%Y')} (weekday={future_date.weekday()})")

future_sample = pd.DataFrame({
    "prize": [5000]*10000,
    "day": [future_date.day]*10000,
    "month": [future_date.month]*10000,
    "weekday": [future_date.weekday()]*10000,
    "number_int": list(range(10000))
})
future_sample["number"] = [str(i).zfill(4) for i in range(10000)]

# 🚨 Keep only training features
X_future = future_sample[["prize", "day", "month", "weekday", "number_int"]]

batch_size = 1000
probs = []
for i in tqdm(range(0, len(X_future), batch_size), desc="Predicting"):
    batch = X_future.iloc[i:i+batch_size]
    batch_probs = model.predict_proba(batch)[:, 1]
    probs.extend(batch_probs)

future_sample["prob"] = np.array(probs)

# 7. Top 18 predicted numbers
top_preds = future_sample.sort_values("prob", ascending=False).head(18)
print("\n🎯 Top predicted numbers:\n", top_preds[["number", "prob"]])

# 8. Visualization – ML predictions
plt.figure(figsize=(10,5))
top_preds.plot(x="number", y="prob", kind="bar", legend=False, ax=plt.gca())
plt.title("Top 18 Predicted Numbers (Probability)")
plt.ylabel("Probability")
plt.show()

# ----------------------------
# EXTRA ANALYSIS SECTION
# ----------------------------
print("\n📊 EXTRA ANALYSIS (Patterns & Statistics)")

# 1. Frequency by Month
freq_month = df.groupby(["month", "number"]).size().reset_index(name="count")
top_month = freq_month.sort_values("count", ascending=False).groupby("month").head(5)
print("\n🔥 Top numbers per month:")
print(top_month)

# 2. Frequency by Weekday
freq_weekday = df.groupby(["weekday", "number"]).size().reset_index(name="count")
top_weekday = freq_weekday.sort_values("count", ascending=False).groupby("weekday").head(5)
print("\n🔥 Top numbers per weekday (0=Monday ... 6=Sunday):")
print(top_weekday)

# 3. Ending Patterns (last 2 and last 3 digits)
df["last2"] = df["number"].str[-2:]
df["last3"] = df["number"].str[-3:]
last2_freq = df["last2"].value_counts().head(10)
last3_freq = df["last3"].value_counts().head(10)
print("\n🔢 Most common last 2 digits:\n", last2_freq)
print("\n🔢 Most common last 3 digits:\n", last3_freq)

# 4. Adjacent Numbers (neighbors of winners)
df["num_int"] = df["number"].astype(int)
adjacent_hits = []
for n in df["num_int"]:
    if (n+1) in df["num_int"].values or (n-1) in df["num_int"].values:
        adjacent_hits.append(n)
print(f"\n🔗 Found {len(adjacent_hits)} winners that had an adjacent neighbor also winning.")

# 5. Digit Position Heatmap
digits = pd.DataFrame({
    "d1": df["number"].str[0].astype(int),
    "d2": df["number"].str[1].astype(int),
    "d3": df["number"].str[2].astype(int),
    "d4": df["number"].str[3].astype(int)
})
heatmap = digits.apply(pd.Series.value_counts).fillna(0).astype(int)
print("\n🔥 Digit frequency per position (rows=digit, cols=position):\n")
print(heatmap)

# Optional: Plot digit heatmap
plt.figure(figsize=(6,4))
plt.imshow(heatmap.values, cmap="hot", interpolation="nearest")
plt.colorbar(label="Frequency")
plt.xticks(range(4), ["1st", "2nd", "3rd", "4th"])
plt.yticks(range(10), range(10))
plt.title("Digit Frequency Heatmap (per position)")
plt.show()
