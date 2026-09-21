import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import xgboost as xgb
from tqdm import tqdm
from datetime import timedelta

# ======================
# CONFIG
# ======================
MAX_TARGET = 12
SIMULATE_DAYS = 7  # simulate next 60 days
ML_DATA_FILE = "5000_number_training_data_saturation.csv"

# ======================
# LOAD DATA
# ======================
df = pd.read_csv(ML_DATA_FILE)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["number", "date"])

features = [
    "is_new_number",
    "unique_numbers_so_far",
    "saturation_level",
    "new_ratio",
    "repeat_ratio",
    "days_since_last",
    "total_hits"
]

# ======================
# PREPARE TARGET FOR TRAINING
# ======================
df["next_date"] = df.groupby("number")["date"].shift(-1)
df["will_appear_next_day"] = (df["next_date"] - df["date"]).dt.days == 1
df["will_appear_next_day"] = df["will_appear_next_day"].fillna(0).astype(int)

X = df[features]
y = df["will_appear_next_day"]

# Chronological split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

# ======================
# TRAIN MODEL
# ======================
model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.1,
    use_label_encoder=False,
    eval_metric='logloss',
    random_state=42
)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"✅ ML next-day prediction accuracy: {acc:.2f}")

# ======================
# SIMULATION FOR FUTURE DATES
# ======================
latest_df = df.sort_values("date").groupby("number").tail(1).copy()
latest_df = latest_df.reset_index(drop=True)

simulation_results = []
current_date = latest_df["date"].max() + timedelta(days=1)

print(f"🔮 Simulating next {SIMULATE_DAYS} days for future predictions...")

for _ in tqdm(range(SIMULATE_DAYS), ncols=90):
    # Predict next-day appearance
    latest_df["pred_next_hit"] = model.predict(latest_df[features])
    
    # Record predictions
    predicted_numbers = latest_df[latest_df["pred_next_hit"] == 1]["number"].tolist()
    simulation_results.append({
        "date": current_date.strftime("%Y-%m-%d"),
        "predicted_numbers": predicted_numbers
    })
    
    # Update features for next day simulation
    for idx, row in latest_df.iterrows():
        num = row["number"]
        if num in predicted_numbers:
            row["total_hits"] += 1
            row["days_since_last"] = 0
        else:
            row["days_since_last"] += 1
        # Update saturation level & ratios
        row["unique_numbers_so_far"] = len(latest_df[latest_df["total_hits"] > 0])
        row["saturation_level"] = row["unique_numbers_so_far"] / 10000
        row["new_ratio"] = max(0, (10000 - row["unique_numbers_so_far"]) / 10000)
        row["repeat_ratio"] = 1 - row["new_ratio"]
        latest_df.loc[idx, features] = row[features]
    
    # Stop numbers exceeding MAX_TARGET
    latest_df.loc[latest_df["total_hits"] >= MAX_TARGET, "pred_next_hit"] = 0
    
    # Increment date
    current_date += timedelta(days=1)

# ======================
# SAVE SIMULATION RESULTS
# ======================
sim_df = pd.DataFrame(simulation_results)
sim_df.to_csv("future_number_predictions.csv", index=False)
print("✅ Saved future predictions → future_number_predictions.csv")
print(sim_df.head(15))
