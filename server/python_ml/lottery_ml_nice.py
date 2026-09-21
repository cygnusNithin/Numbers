import pandas as pd
import numpy as np
import datetime as dt
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, roc_auc_score
import csv
import warnings

warnings.filterwarnings("ignore")
np.random.seed(42)

# ======================
# CONFIG
# ======================
DATA_CSV = "lotteryData.csv"     # your flat export
PRIZE_TARGET = 5000              # predict ₹5000 bracket
TOP_K = 18                       # "real machine" picks 18
NEGATIVE_SAMPLES = 18            # 1:18 positive/negative per winning row
TARGET_DATE = dt.date(2025, 8, 1)
ROLLING_WINDOW_DAYS = 365        # train on last 365 days up to TARGET_DATE-1
CALIBRATE = True                 # calibrate RF probabilities

# Optional: paste the true winners for 01-Aug-2025 (strings, zero-padded to 4 digits)
# Leave empty list [] if you don't want to evaluate yet.
GROUND_TRUTH_5000 = [
    # e.g. "3615","1130","5845", ...  (fill when you have them)
    "0269","0494","0803","1503","1954",
"2992","3288","3562","3904","4075",
"4511","4523","4785","4889","5355",
"6265","6278","6504","8301","9064"
]

# ======================
# LOAD & PREP
# ======================
df = pd.read_csv(DATA_CSV)
df["number"] = df["number"].astype(str).str.zfill(4)
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
df = df.dropna(subset=["date"])

# Core date features
df["day"] = df["date"].dt.day
df["month"] = df["date"].dt.month
df["weekday"] = df["date"].dt.weekday  # 0=Mon ... 6=Sun

print("✅ Data loaded:", df.head())

# ======================
# ROLLING TRAIN WINDOW
# ======================
end_date = TARGET_DATE - dt.timedelta(days=1)
start_date = end_date - dt.timedelta(days=ROLLING_WINDOW_DAYS - 1)
train_mask = (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date) & (df["prize"] == PRIZE_TARGET)
df_train = df.loc[train_mask].copy()

print(f"📅 Training window: {start_date} → {end_date}")
print("📊 Training samples:", len(df_train))

if df_train.empty:
    raise SystemExit("No training rows in the selected window. Expand ROLLING_WINDOW_DAYS or check your data.")

# ======================
# (Light) Extra features helpful for ranking
# ======================
# Global (in-window) frequencies by number, last2, last3 — used as model features
def add_freq_features(frame: pd.DataFrame) -> pd.DataFrame:
    # Count in-window occurrences
    freq_num = frame.groupby("number").size()
    frame["freq_num_win"] = frame["number"].map(freq_num).fillna(0).astype(int)

    frame["last2"] = frame["number"].str[-2:]
    frame["last3"] = frame["number"].str[-3:]

    freq_l2 = frame["last2"].value_counts()
    freq_l3 = frame["last3"].value_counts()

    frame["freq_last2_win"] = frame["last2"].map(freq_l2).fillna(0).astype(int)
    frame["freq_last3_win"] = frame["last3"].map(freq_l3).fillna(0).astype(int)

    # digit-position features
    frame["d1"] = frame["number"].str[0].astype(int)
    frame["d2"] = frame["number"].str[1].astype(int)
    frame["d3"] = frame["number"].str[2].astype(int)
    frame["d4"] = frame["number"].str[3].astype(int)

    return frame

df_train = add_freq_features(df_train)

# ======================
# BUILD TRAINING SET with NEGATIVE SAMPLING (stream to CSV to save RAM)
# ======================
train_csv = "training_data.csv"
all_numbers_int = np.arange(10000)

with open(train_csv, "w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "prize", "day", "month", "weekday",
            "number", "number_int",
            "freq_num_win", "freq_last2_win", "freq_last3_win",
            "d1","d2","d3","d4",
            "target"
        ],
    )
    writer.writeheader()

    for _, r in tqdm(df_train.iterrows(), total=len(df_train), desc="Building dataset"):
        # positive row
        writer.writerow({
            "prize": r["prize"],
            "day": r["day"],
            "month": r["month"],
            "weekday": r["weekday"],
            "number": r["number"],
            "number_int": int(r["number"]),
            "freq_num_win": r["freq_num_win"],
            "freq_last2_win": r["freq_last2_win"],
            "freq_last3_win": r["freq_last3_win"],
            "d1": r["d1"], "d2": r["d2"], "d3": r["d3"], "d4": r["d4"],
            "target": 1
        })

        # negatives
        negs = np.random.choice(all_numbers_int, size=NEGATIVE_SAMPLES, replace=False)
        for n in negs:
            n_str = f"{n:04d}"
            if n_str == r["number"]:
                continue
            # reuse the same freq/digit features for the negative number
            # (look them up from the in-window aggregates; unseen -> 0)
            last2 = n_str[-2:]
            last3 = n_str[-3:]
            writer.writerow({
                "prize": r["prize"],
                "day": r["day"],
                "month": r["month"],
                "weekday": r["weekday"],
                "number": n_str,
                "number_int": n,
                "freq_num_win": int(df_train["freq_num_win"][df_train["number"]==n_str].head(1).fillna(0).sum()),
                "freq_last2_win": int(df_train["freq_last2_win"][df_train["last2"]==last2].head(1).fillna(0).sum()),
                "freq_last3_win": int(df_train["freq_last3_win"][df_train["last3"]==last3].head(1).fillna(0).sum()),
                "d1": int(n_str[0]), "d2": int(n_str[1]), "d3": int(n_str[2]), "d4": int(n_str[3]),
                "target": 0
            })

print(f"✅ Training dataset written to {train_csv}")

clf_df = pd.read_csv(train_csv)
print("📊 Final dataset size:", clf_df.shape)

# FEATURES / TARGET
FEATS = [
    "prize","day","month","weekday","number_int",
    "freq_num_win","freq_last2_win","freq_last3_win",
    "d1","d2","d3","d4"
]
X = clf_df[FEATS]
y = clf_df["target"]

# SPLIT + MODEL
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.1, random_state=42, stratify=y
)

rf = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    class_weight="balanced_subsample",
    n_jobs=-1,
    max_features="sqrt"
)

if CALIBRATE:
    model = CalibratedClassifierCV(estimator=rf, method="isotonic", cv=3)
else:
    model = rf

print("⏳ Training classifier...")
model.fit(X_train, y_train)
acc = model.score(X_val, y_val)

# extra metrics on validation
val_probs = model.predict_proba(X_val)[:,1]
try:
    auc = roc_auc_score(y_val, val_probs)
    ap = average_precision_score(y_val, val_probs)
except Exception:
    auc, ap = np.nan, np.nan

print("✅ Model trained as classifier")
print(f"📊 Accuracy on holdout: {acc:.4f} | ROC-AUC: {auc:.4f} | AP: {ap:.4f}")

# ======================
# PREDICT FOR THE TARGET DATE (01-Aug-2025, correct weekday auto-computed)
# ======================
target_dt = pd.Timestamp(TARGET_DATE)
wk = target_dt.weekday()  # 0=Mon..6=Sun

# Build prediction frame for ALL 0000..9999 numbers with same features
# We need the in-window frequency features for those numbers too.
# Construct a small lookup from df_train:
freq_num_lut = df_train.groupby("number")["freq_num_win"].max().to_dict()
freq_l2_lut  = df_train.groupby("last2")["freq_last2_win"].max().to_dict()
freq_l3_lut  = df_train.groupby("last3")["freq_last3_win"].max().to_dict()

pred = pd.DataFrame({
    "prize": PRIZE_TARGET,
    "day": target_dt.day,
    "month": target_dt.month,
    "weekday": wk,
    "number_int": np.arange(10000)
})
pred["number"] = pred["number_int"].apply(lambda x: f"{x:04d}")
pred["last2"] = pred["number"].str[-2:]
pred["last3"] = pred["number"].str[-3:]
pred["freq_num_win"] = pred["number"].map(freq_num_lut).fillna(0).astype(int)
pred["freq_last2_win"] = pred["last2"].map(freq_l2_lut).fillna(0).astype(int)
pred["freq_last3_win"] = pred["last3"].map(freq_l3_lut).fillna(0).astype(int)
pred["d1"] = pred["number"].str[0].astype(int)
pred["d2"] = pred["number"].str[1].astype(int)
pred["d3"] = pred["number"].str[2].astype(int)
pred["d4"] = pred["number"].str[3].astype(int)

X_future = pred[FEATS]

# batch predict for memory safety
batch = 2000
probs = []
for i in tqdm(range(0, len(X_future), batch), desc="Predicting"):
    probs.extend(model.predict_proba(X_future.iloc[i:i+batch])[:,1])
pred["prob"] = np.array(probs)

top_preds = pred.sort_values("prob", ascending=False).head(TOP_K)[["number","prob"]]

print(f"\n📅 Predicting for {TARGET_DATE.strftime('%d-%m-%Y')} (weekday={wk})")
print("\n🎯 Top predicted numbers:\n", top_preds)

top_preds.to_csv("pred_aug1_2025_top18.csv", index=False)

# ======================
# OPTIONAL: EVALUATION if you pasted the truth
# ======================
def evaluate_topk(pred_df, truth_list, k=TOP_K):
    truth = set([str(x).zfill(4) for x in truth_list])
    topk_list = pred_df.sort_values("prob", ascending=False).head(k)["number"].tolist()
    hits = [n for n in topk_list if n in truth]
    precision_at_k = len(hits) / k
    recall = len(hits) / max(1, len(truth))
    return {
        "topk_list": topk_list,
        "hits": hits,
        "precision@k": precision_at_k,
        "recall": recall,
        "hits_count": len(hits),
        "truth_count": len(truth)
    }

if len(GROUND_TRUTH_5000) > 0:
    ev = evaluate_topk(pred, GROUND_TRUTH_5000, k=TOP_K)
    print("\n✅ EVALUATION vs ground truth (01-Aug-2025, ₹5000)")
    print(f"- Hits: {ev['hits_count']} / {ev['truth_count']}")
    print(f"- Precision@{TOP_K}: {ev['precision@k']:.3f}")
    print(f"- Recall: {ev['recall']:.3f}")
    print(f"- Hit numbers: {ev['hits']}")
    pd.DataFrame({
        "rank": list(range(1, TOP_K+1)),
        "number": ev["topk_list"]
    }).to_csv("pred_aug1_2025_ranked_top18.csv", index=False)
else:
    print("\nℹ️ Paste the real 01-Aug-2025 ₹5000 winners into GROUND_TRUTH_5000 to auto-evaluate.")
