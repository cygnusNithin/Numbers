import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from tqdm import tqdm
import joblib

# =====================
# CONFIG
# =====================
CSV_FILE = "5000_number_patterns3.csv"
LOOKAHEAD_DAYS = 7  # Predict if number will appear in next 7 days
MODEL_FILE = "lottery_date_number_model.pkl"
PREDICTION_DATE = "14/09/2025"   # 🎯 Change this date for prediction
TOP_N = 20                       # 🎯 How many numbers to output
OUTPUT_FILE = "lottery_predictions1.csv"

# =====================
# LOAD DATA
# =====================
print("🔄 Loading dataset...")
df = pd.read_csv(CSV_FILE)

# Expand dates into per-draw rows
print("🔄 Expanding dates into rows...")
rows = []
for _, row in tqdm(df.iterrows(), total=len(df), desc="Expanding dates"):
    number = row["number"]
    dates = str(row["dates"]).split("|")
    for d in dates:
        try:
            dt = datetime.strptime(d.strip(), "%d/%m/%Y")
            rows.append({"number": number, "date": dt})
        except:
            continue

expanded = pd.DataFrame(rows)
expanded = expanded.sort_values("date")

print(f"📊 Expanded dataset: {len(expanded)} rows")

# =====================
# FEATURE ENGINEERING
# =====================
print("🔄 Building features...")
features = []
numbers = expanded["number"].unique()

for num in tqdm(numbers, total=len(numbers), desc="Processing numbers"):
    num_df = expanded[expanded["number"] == num].sort_values("date")

    last_seen = None
    for _, row in num_df.iterrows():
        dt = row["date"]
        if last_seen:
            gap = (dt - last_seen).days
        else:
            gap = 9999

        features.append({
            "number": num,
            "date": dt,
            "weekday": dt.weekday(),  # 0=Mon
            "month": dt.month,
            "gap_since_last": gap,
            "target": 1
        })
        last_seen = dt

dataset = pd.DataFrame(features)

# Label target_future
print("🔄 Labeling future targets...")
dataset["target_future"] = 0
for idx in tqdm(range(len(dataset)), desc="Labeling"):
    num = dataset.iloc[idx]["number"]
    date = dataset.iloc[idx]["date"]
    next_hits = expanded[
        (expanded["number"] == num) &
        (expanded["date"] > date) &
        (expanded["date"] <= date + timedelta(days=LOOKAHEAD_DAYS))
    ]
    if len(next_hits) > 0:
        dataset.at[idx, "target_future"] = 1

# =====================
# TRAIN MODEL
# =====================
print("⚡ Training model...")

X = dataset[["weekday", "month", "gap_since_last"]]
y = dataset["target_future"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
acc = accuracy_score(y_test, y_pred)

print(f"✅ Accuracy: {acc:.3f}")
print(classification_report(y_test, y_pred))

# Save model
joblib.dump(model, MODEL_FILE)
print(f"💾 Model saved as {MODEL_FILE}")

# =====================
# PREDICTION
# =====================
print(f"🔮 Predicting numbers for {PREDICTION_DATE}...")
pred_date = datetime.strptime(PREDICTION_DATE, "%d/%m/%Y")

pred_rows = []
for num in tqdm(numbers, total=len(numbers), desc="Predicting"):
    # Find last seen date for this number
    num_df = expanded[expanded["number"] == num].sort_values("date")
    if len(num_df) == 0:
        continue
    last_seen = num_df["date"].max()
    gap = (pred_date - last_seen).days if pd.notnull(last_seen) else 9999

    X_pred = pd.DataFrame([{
        "weekday": pred_date.weekday(),
        "month": pred_date.month,
        "gap_since_last": gap
    }])
    prob = model.predict_proba(X_pred)[0][1]  # probability of appearing
    pred_rows.append({"number": num, "probability": prob, "last_seen": last_seen.strftime("%d/%m/%Y")})

pred_df = pd.DataFrame(pred_rows).sort_values("probability", ascending=False).head(TOP_N)

# Save predictions
pred_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
print(f"✅ Predictions saved to {OUTPUT_FILE}")
print("\n🎯 Top predicted numbers:")
print(pred_df)
