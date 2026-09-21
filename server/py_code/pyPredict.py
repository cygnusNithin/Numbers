import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from tqdm import tqdm
import argparse
import joblib

# ========================
# CONFIG
# ========================
DATA_FILE = "all_prizes_number_patterns.csv"
MODEL_FILE = "lottery_date_number_model1.pkl"
PREDICTIONS_FILE = "lottery_predictions2.csv"

# ========================
# FEATURE ENGINEERING
# ========================
def build_features(df):
    rows = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Building features"):
        num = row["number"]
        dates = str(row["dates"]).split("|")

        dt_list = []
        for d in dates:
            try:
                dt_list.append(datetime.strptime(d, "%d/%m/%Y"))
            except:
                continue
        dt_list = sorted(dt_list)

        for i in range(1, len(dt_list)):
            prev_date = dt_list[i - 1]
            curr_date = dt_list[i]

            gap = (curr_date - prev_date).days
            weekday = prev_date.weekday()  # 0=Mon, 6=Sun
            month = prev_date.month

            rows.append({
                "number": num,
                "gap_days": gap,
                "weekday": weekday,
                "month": month,
                "label": 1  # hit
            })

            # Add a "non-hit" sample (negative class)
            nohit_date = prev_date + timedelta(days=gap // 2)
            rows.append({
                "number": num,
                "gap_days": gap // 2,
                "weekday": nohit_date.weekday(),
                "month": nohit_date.month,
                "label": 0
            })

    return pd.DataFrame(rows)

# ========================
# TRAIN MODEL
# ========================
def train_model():
    df = pd.read_csv(DATA_FILE)
    features = build_features(df)

    X = features[["gap_days", "weekday", "month"]]
    y = features["label"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print("\n📊 Model Performance:\n")
    print(classification_report(y_test, y_pred))

    joblib.dump(model, MODEL_FILE)
    print(f"✅ Model saved to {MODEL_FILE}")

# ========================
# PREDICT FOR FUTURE DATE
# ========================
def predict_for_date(date_str):
    model = joblib.load(MODEL_FILE)
    df = pd.read_csv(DATA_FILE)

    target_date = datetime.strptime(date_str, "%d/%m/%Y")

    rows = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Preparing predictions"):
        num = row["number"]
        dates = str(row["dates"]).split("|")

        dt_list = []
        for d in dates:
            try:
                dt_list.append(datetime.strptime(d, "%d/%m/%Y"))
            except:
                continue
        dt_list = sorted(dt_list)

        if not dt_list:
            continue

        last_date = dt_list[-1]
        gap = (target_date - last_date).days
        weekday = target_date.weekday()
        month = target_date.month

        X = pd.DataFrame([{"gap_days": gap, "weekday": weekday, "month": month}])
        prob = model.predict_proba(X)[0][1]

        rows.append({
            "number": num,
            "last_seen": last_date.strftime("%d/%m/%Y"),
            "gap_to_target": gap,
            "predicted_probability": prob
        })

    out_df = pd.DataFrame(rows).sort_values("predicted_probability", ascending=False)
    out_df.to_csv(PREDICTIONS_FILE, index=False, encoding="utf-8")
    print(f"✅ Predictions saved to {PREDICTIONS_FILE}")
    return out_df.head(20)

# ========================
# MAIN
# ========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true", help="Train the model")
    parser.add_argument("--date", type=str, help="Predict for date (DD/MM/YYYY)")
    args = parser.parse_args()

    if args.train:
        train_model()
    elif args.date:
        top_preds = predict_for_date(args.date)
        print("\n🎯 Top predictions:")
        print(top_preds)
    else:
        print("⚠️ Use --train to train or --date DD/MM/YYYY to predict")
