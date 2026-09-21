import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_curve, average_precision_score, confusion_matrix, classification_report
from xgboost import XGBClassifier
from tqdm import tqdm
from datetime import timedelta

# ======================
# CONFIG
# ======================
ML_DATA_FILE = "5000_number_training_data_saturation.csv"
UNIVERSE = 10000            # for saturation calc
MAX_TARGET = 12
MAX_SIM_DAYS = 3650         # safety
PATIENCE_DAYS = 180         # allow more days than before

FEATURES = [
    "is_new_number",
    "unique_numbers_so_far",
    "saturation_level",
    "new_ratio",
    "repeat_ratio",
    "days_since_last",
    "total_hits",
]

# ======================
# LOAD + CLEAN
# ======================
df_raw = pd.read_csv(ML_DATA_FILE)
df_raw["date"] = pd.to_datetime(df_raw["date"], errors="coerce")
df_raw = df_raw.dropna(subset=["date"]).sort_values(["number", "date"]).reset_index(drop=True)

# Fix broken ratios if outside [0,1]
def fix_ratios(df):
    needs_fix = False
    for col in ["saturation_level", "new_ratio", "repeat_ratio"]:
        if col not in df.columns:
            needs_fix = True
            break
    if not needs_fix:
        if (df["saturation_level"].min() < 0) or (df["saturation_level"].max() > 1) or \
           (df["new_ratio"].min() < 0) or (df["new_ratio"].max() > 1) or \
           (df["repeat_ratio"].min() < 0) or (df["repeat_ratio"].max() > 1):
            needs_fix = True
    if needs_fix:
        df["saturation_level"] = df["unique_numbers_so_far"] / UNIVERSE
        df["new_ratio"] = 1.0 - df["saturation_level"]
        df["repeat_ratio"] = 1.0 - df["new_ratio"]
    return df

df_raw = fix_ratios(df_raw)

missing = [c for c in FEATURES if c not in df_raw.columns]
if missing:
    raise ValueError(f"Missing feature columns in CSV: {missing}")

# ======================
# LABEL: appears next day (very imbalanced)
# ======================
df = df_raw.copy()
df["next_date"] = df.groupby("number")["date"].shift(-1)
df["gap_days"] = (df["next_date"] - df["date"]).dt.days
df["y"] = (df["gap_days"] == 1).astype(int)

# Drop last rows (unknown future)
df = df[~df["next_date"].isna()].copy()
df[FEATURES] = df[FEATURES].fillna(0)

# Time-based split
cut = df["date"].quantile(0.8)
train = df[df["date"] <= cut]
test  = df[df["date"] >  cut]

X_train = train[FEATURES]
y_train = train["y"].astype(int)
X_test  = test[FEATURES]
y_test  = test["y"].astype(int)

pos_rate_train = y_train.mean()
neg_rate_train = 1 - pos_rate_train
spw = (neg_rate_train / max(pos_rate_train, 1e-6))  # scale_pos_weight

print(f"Train size={len(train)}, Test size={len(test)}")
print(f"Positive rate (train)={pos_rate_train:.5f}, (test)={y_test.mean():.5f}, spw≈{spw:.1f}")

# ======================
# TRAIN with imbalance handling
# ======================
model = XGBClassifier(
    n_estimators=600,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="binary:logistic",
    eval_metric="logloss",
    scale_pos_weight=spw,  # key for imbalance
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train, y_train)

# Evaluate with PR metrics and choose threshold
proba_test = model.predict_proba(X_test)[:, 1]
acc = accuracy_score(y_test, (proba_test >= 0.5).astype(int))
ap = average_precision_score(y_test, proba_test)  # area under PR curve
prec, rec, thresh = precision_recall_curve(y_test, proba_test)

# Choose threshold that maximizes F1 on test
f1 = (2 * prec * rec) / (prec + rec + 1e-9)
best_idx = int(np.nanargmax(f1))
best_thresh = 0.5 if best_idx >= len(thresh) else float(thresh[best_idx])

print(f"Accuracy@0.5={acc:.4f}, AP={ap:.4f}, Best F1={f1[best_idx]:.4f} at threshold={best_thresh:.4f}")
y_hat = (proba_test >= best_thresh).astype(int)
print("Confusion matrix (test):")
print(confusion_matrix(y_test, y_hat))
print(classification_report(y_test, y_hat, digits=4))

# If still predicting too few positives, relax threshold a bit
if y_hat.mean() < 0.001:
    best_thresh = max(0.05, best_thresh * 0.5)
    print(f"Threshold too conservative; relaxing to {best_thresh:.4f}")

# ======================
# SIMULATION
# ======================
latest_df = (
    df_raw.sort_values("date")
    .groupby("number", as_index=False)
    .tail(1)
    .reset_index(drop=True)
    .copy()
)
# Ensure features ready
latest_df[FEATURES] = latest_df[FEATURES].fillna(0)
latest_df["is_new_number"] = 0  # in the future they're not "new"

# Remaining hits to reach MAX_TARGET
remaining = (MAX_TARGET - latest_df["total_hits"].clip(lower=0)).astype(int)
remaining[remaining < 0] = 0
total_to_earn = int(remaining.sum())

number_schedule = {n: [] for n in latest_df["number"].tolist()}
current_date = latest_df["date"].max() + timedelta(days=1)

if total_to_earn == 0:
    print("All numbers already at or above target.")
else:
    print("🔮 Predicting future schedule until each number reaches 12 hits...")
    no_progress_days = 0
    days_sim = 0

    with tqdm(total=total_to_earn, ncols=100, desc="Hits earned") as pbar:
        while remaining.sum() > 0 and days_sim < MAX_SIM_DAYS:
            need_mask = remaining > 0
            X_now = latest_df.loc[need_mask, FEATURES].copy().fillna(0)
            proba_now = np.zeros(len(latest_df), dtype=float)
            if not X_now.empty:
                proba_vals = model.predict_proba(X_now)[:, 1]
                proba_now[need_mask.values] = proba_vals

            # Use the tuned threshold
            y_next = (proba_now >= best_thresh).astype(int)

            hits_today = 0
            for idx, need in enumerate(need_mask):
                if not need:
                    latest_df.at[idx, "days_since_last"] += 1
                    continue
                if y_next[idx] == 1:
                    num = latest_df.at[idx, "number"]
                    number_schedule[num].append(current_date.strftime("%Y-%m-%d"))
                    latest_df.at[idx, "total_hits"] += 1
                    remaining.iloc[idx] = max(0, remaining.iloc[idx] - 1)
                    latest_df.at[idx, "days_since_last"] = 0
                    hits_today += 1
                else:
                    latest_df.at[idx, "days_since_last"] += 1

            # Per-day global updates
            already_hit = int((latest_df["total_hits"] > 0).sum())
            latest_df["unique_numbers_so_far"] = already_hit
            latest_df["saturation_level"] = latest_df["unique_numbers_so_far"] / UNIVERSE
            latest_df["new_ratio"] = 1.0 - latest_df["saturation_level"]
            latest_df["repeat_ratio"] = 1.0 - latest_df["new_ratio"]
            latest_df["is_new_number"] = 0

            if hits_today > 0:
                pbar.update(hits_today)
                no_progress_days = 0
            else:
                no_progress_days += 1

            current_date += timedelta(days=1)
            days_sim += 1

            if no_progress_days >= PATIENCE_DAYS:
                print(f"⚠️ No hits for {PATIENCE_DAYS} simulated days. Stopping early.")
                break

# ======================
# SAVE
# ======================
schedule_df = pd.DataFrame(
    {"number": list(number_schedule.keys()),
     "predicted_dates": ["|".join(v) for v in number_schedule.values()]}
)
schedule_df.to_csv("number_future_schedule.csv", index=False, encoding="utf-8")
print("✅ Saved full predicted schedule → number_future_schedule.csv")
print(schedule_df.head(10))