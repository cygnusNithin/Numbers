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
DATA_CSV = "lotteryData.csv"
PRIZE_TARGET = 5000
TOP_K = 18
NEGATIVE_SAMPLES = 18
ROLLING_WINDOW_DAYS = 365
CALIBRATE = True

# Backtest window
BACKTEST = True
BACKTEST_START = dt.date(2023, 1, 1)
BACKTEST_END = dt.date(2024, 12, 31)

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
df["weekday"] = df["date"].dt.weekday

print("✅ Data loaded:", df.head())

# ======================
# Helper: Add frequency & digit features
# ======================
def add_freq_features(frame: pd.DataFrame) -> pd.DataFrame:
    freq_num = frame.groupby("number").size()
    frame["freq_num_win"] = frame["number"].map(freq_num).fillna(0).astype(int)

    frame["last2"] = frame["number"].str[-2:]
    frame["last3"] = frame["number"].str[-3:]

    freq_l2 = frame["last2"].value_counts()
    freq_l3 = frame["last3"].value_counts()

    frame["freq_last2_win"] = frame["last2"].map(freq_l2).fillna(0).astype(int)
    frame["freq_last3_win"] = frame["last3"].map(freq_l3).fillna(0).astype(int)

    frame["d1"] = frame["number"].str[0].astype(int)
    frame["d2"] = frame["number"].str[1].astype(int)
    frame["d3"] = frame["number"].str[2].astype(int)
    frame["d4"] = frame["number"].str[3].astype(int)

    return frame

# ======================
# Evaluate predictions
# ======================
def evaluate_topk(pred_df, truth_list, k=TOP_K):
    truth = set([str(x).zfill(4) for x in truth_list])
    topk_list = pred_df.sort_values("prob", ascending=False).head(k)["number"].tolist()
    hits = [n for n in topk_list if n in truth]
    return len(hits), hits

# ======================
# BACKTEST LOOP
# ======================
if BACKTEST:
    results = []
    # Find all unique draw dates within backtest window
    backtest_dates = sorted(df[(df["date"].dt.date >= BACKTEST_START) & 
                               (df["date"].dt.date <= BACKTEST_END)]["date"].dt.date.unique())

    for target_date in tqdm(backtest_dates, desc="Backtesting"):
        # Training window
        end_date = target_date - dt.timedelta(days=1)
        start_date = end_date - dt.timedelta(days=ROLLING_WINDOW_DAYS - 1)
        df_train = df[(df["date"].dt.date >= start_date) & 
                      (df["date"].dt.date <= end_date) & 
                      (df["prize"] == PRIZE_TARGET)].copy()
        df_truth = df[(df["date"].dt.date == target_date) & (df["prize"] == PRIZE_TARGET)]

        if df_train.empty or df_truth.empty:
            continue

        df_train = add_freq_features(df_train)

        # Build training set (positive + negatives)
        train_csv = "training_temp.csv"
        all_numbers_int = np.arange(10000)
        with open(train_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "prize","day","month","weekday",
                "number","number_int",
                "freq_num_win","freq_last2_win","freq_last3_win",
                "d1","d2","d3","d4","target"])
            writer.writeheader()

            for _, r in df_train.iterrows():
                writer.writerow({
                    "prize": r["prize"],"day": r["day"],"month": r["month"],"weekday": r["weekday"],
                    "number": r["number"],"number_int": int(r["number"]),
                    "freq_num_win": r["freq_num_win"],"freq_last2_win": r["freq_last2_win"],
                    "freq_last3_win": r["freq_last3_win"],
                    "d1": r["d1"],"d2": r["d2"],"d3": r["d3"],"d4": r["d4"],"target": 1
                })
                negs = np.random.choice(all_numbers_int, size=NEGATIVE_SAMPLES, replace=False)
                for n in negs:
                    n_str = f"{n:04d}"
                    if n_str == r["number"]:
                        continue
                    last2 = n_str[-2:]
                    last3 = n_str[-3:]
                    writer.writerow({
                        "prize": r["prize"],"day": r["day"],"month": r["month"],"weekday": r["weekday"],
                        "number": n_str,"number_int": n,
                        "freq_num_win": int(df_train["freq_num_win"][df_train["number"]==n_str].head(1).fillna(0).sum()),
                        "freq_last2_win": int(df_train["freq_last2_win"][df_train["last2"]==last2].head(1).fillna(0).sum()),
                        "freq_last3_win": int(df_train["freq_last3_win"][df_train["last3"]==last3].head(1).fillna(0).sum()),
                        "d1": int(n_str[0]),"d2": int(n_str[1]),"d3": int(n_str[2]),"d4": int(n_str[3]),"target": 0
                    })

        clf_df = pd.read_csv(train_csv)
        FEATS = ["prize","day","month","weekday","number_int",
                 "freq_num_win","freq_last2_win","freq_last3_win","d1","d2","d3","d4"]
        X = clf_df[FEATS]
        y = clf_df["target"]

        rf = RandomForestClassifier(n_estimators=200, random_state=42,
                                    class_weight="balanced_subsample", n_jobs=-1, max_features="sqrt")
        if CALIBRATE:
            model = CalibratedClassifierCV(estimator=rf, method="isotonic", cv=3)
        else:
            model = rf

        model.fit(X, y)

        # Predict for all 0000–9999
        freq_num_lut = df_train.groupby("number")["freq_num_win"].max().to_dict()
        freq_l2_lut  = df_train.groupby("last2")["freq_last2_win"].max().to_dict()
        freq_l3_lut  = df_train.groupby("last3")["freq_last3_win"].max().to_dict()

        pred = pd.DataFrame({
            "prize": PRIZE_TARGET,"day": target_date.day,"month": target_date.month,"weekday": target_date.weekday(),
            "number_int": np.arange(10000)})
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

        pred["prob"] = model.predict_proba(pred[FEATS])[:,1]

        # Evaluate hits
        truth_nums = df_truth["number"].tolist()
        hits, hit_list = evaluate_topk(pred, truth_nums, k=TOP_K)
        results.append({
            "date": target_date,
            "hits": hits,
            "truth_count": len(truth_nums),
            "hit_numbers": hit_list
        })

    # Final summary
    res_df = pd.DataFrame(results)
    print("\n📊 BACKTEST SUMMARY")
    print(res_df.groupby("date")["hits"].mean())
    print(f"\n🔥 Avg hits per draw: {res_df['hits'].mean():.2f}")
    res_df.to_csv("backtest_results.csv", index=False)
