import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime, timedelta
from sklearn.metrics import classification_report, accuracy_score, average_precision_score
from sklearn.ensemble import RandomForestClassifier
import joblib
from tqdm import tqdm

# ==========================
# CONFIG
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
LOOKAHEAD_DAYS = 7  # label window
GAP_DAYS = LOOKAHEAD_DAYS  # purging gap between train and test

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
    for series in row.get("series", []):
        prize = series.get("prize")
        for num in series.get("numbers", []):
            rows.append({"date": row["date"], "number": num.get("number"), "prize": prize})

flat = pd.DataFrame(rows).dropna(subset=["date", "number"]).sort_values("date")

# Ensure numbers are strings (preserve leading zeros if they matter)
flat["number"] = flat["number"].astype(str)

# ==========================
# FEATURE ENGINEERING (no leakage)
# ==========================
features = []
all_dates = sorted(flat["date"].unique())

print(f"🔄 Building dataset across {len(all_dates)} draw dates...")
for d in tqdm(all_dates, desc="Processing dates"):
    past_data = flat[flat["date"] < d]
    future_window = (flat["date"] >= d) & (flat["date"] < d + timedelta(days=LOOKAHEAD_DAYS))
    future_set = set(flat.loc[future_window, "number"])

    # Only consider numbers that have appeared at least once before d
    numbers_in_past = past_data["number"].unique()

    # Pre-slice windows for efficiency
    w7 = d - timedelta(days=7)
    w30 = d - timedelta(days=30)
    w90 = d - timedelta(days=90)

    for num in numbers_in_past:
        num_df = past_data[past_data["number"] == num]

        # frequency features
        freq_total = len(num_df)
        freq_7 = (num_df["date"] > w7).sum()
        freq_30 = (num_df["date"] > w30).sum()
        freq_90 = (num_df["date"] > w90).sum()

        # recency
        last_seen = num_df["date"].max()
        days_since_last = int((d - last_seen).days) if pd.notnull(last_seen) else 9999

        # digit features (robust)
        s = str(num)
        digits = [int(ch) for ch in s if ch.isdigit()]  # ignore any non-digits safely
        sum_digits = sum(digits) if digits else 0
        even_count = sum((d % 2 == 0) for d in digits) if digits else 0

        # target: does number appear in future window?
        appeared_future = int(num in future_set)

        features.append({
            "as_of_date": d,
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
if dataset.empty:
    raise ValueError("Dataset ended up empty. Check source data and flattening logic.")

# ==========================
# TIME-BASED SPLIT WITH GAP
# ==========================
feature_cols = ["freq_total", "freq_7", "freq_30", "freq_90", "days_since_last", "sum_digits", "even_count"]

unique_dates = sorted(dataset["as_of_date"].unique())
test_start_idx = int(len(unique_dates) * 0.8)
test_start_date = unique_dates[test_start_idx]
train_end_date = test_start_date - timedelta(days=GAP_DAYS)

train_mask = dataset["as_of_date"] < train_end_date
test_mask = dataset["as_of_date"] >= test_start_date

train = dataset.loc[train_mask].copy()
test = dataset.loc[test_mask].copy()

if train.empty or test.empty:
    raise ValueError("Train or Test split is empty. Adjust split ratio or GAP_DAYS.")

X_train, y_train = train[feature_cols], train["target"]
X_test, y_test = test[feature_cols], test["target"]

print(f"Train dates: {train['as_of_date'].min().date()} -> {train['as_of_date'].max().date()}")
print(f"Test dates:  {test['as_of_date'].min().date()} -> {test['as_of_date'].max().date()}")
print(f"Class balance (train): positive rate = {y_train.mean():.4f}")

# ==========================
# TRAIN MODEL
# ==========================
print("⚡ Training model...")
model = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    n_jobs=-1,
    class_weight="balanced_subsample",
    max_depth=None,
    min_samples_leaf=2
)
model.fit(X_train, y_train)

# ==========================
# EVALUATION
# ==========================
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

print("✅ Accuracy:", accuracy_score(y_test, y_pred))
print("Average Precision (PR-AUC):", average_precision_score(y_test, y_prob))
print(classification_report(y_test, y_pred, digits=4))

# Naive baseline for context
base_acc = max(y_test.mean(), 1 - y_test.mean())
print(f"Baseline accuracy (predict-all-one-or-all-zero): {base_acc:.4f}")

# Optional: Top-K evaluation per date (ranking use-case)
def topk_hit_rate(df, probs, k=10):
    df = df.copy()
    df["prob"] = probs
    hits = []
    recalls = []
    for dte, g in df.groupby("as_of_date"):
        pos = set(g.loc[g["target"] == 1, "number"])
        if len(pos) == 0:
            continue
        topk = set(g.nlargest(k, "prob")["number"])
        hit = int(len(pos & topk) > 0)
        recall = len(pos & topk) / len(pos)
        hits.append(hit)
        recalls.append(recall)
    return (np.mean(hits) if hits else np.nan, np.mean(recalls) if recalls else np.nan)

hit_rate, recall_at_k = topk_hit_rate(test[["as_of_date", "number", "target"]], y_prob, k=10)
print(f"Top-10 per-date: hit-rate={hit_rate:.3f}, recall@10={recall_at_k:.3f}")

# Save model + metadata
artifact = {
    "model": model,
    "feature_cols": feature_cols,
    "lookahead_days": LOOKAHEAD_DAYS,
    "gap_days": GAP_DAYS,
    "train_end_date": train["as_of_date"].max(),
    "test_start_date": test["as_of_date"].min(),
}
joblib.dump(artifact, "lottery_predictor1.joblib")
print("💾 Model saved as lottery_predictor1.joblib")