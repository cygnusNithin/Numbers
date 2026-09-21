import pandas as pd
import numpy as np
import datetime as dt
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, average_precision_score
import csv
import warnings
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

warnings.filterwarnings("ignore")
np.random.seed(42)
tf.random.set_seed(42)

# ======================
# CONFIG
# ======================
DATA_CSV = "lotteryData.csv"     # your flat export
PRIZE_TARGET = 5000              # predict ₹5000 bracket
TOP_K = 18                       # "real machine" picks 18
NEGATIVE_SAMPLES = 18            # 1:18 positive/negative per winning row
TARGET_DATE = dt.date(2025, 8, 1)
ROLLING_WINDOW_DAYS = 365        # train on last 365 days up to TARGET_DATE-1

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
# ROLLING TRAIN WINDOW
# ======================
end_date = TARGET_DATE - dt.timedelta(days=1)
start_date = end_date - dt.timedelta(days=ROLLING_WINDOW_DAYS - 1)
train_mask = (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date) & (df["prize"] == PRIZE_TARGET)
df_train = df.loc[train_mask].copy()

print(f"📅 Training window: {start_date} → {end_date}")
print("📊 Training samples:", len(df_train))

if df_train.empty:
    raise SystemExit("No training rows in the selected window.")

# ======================
# FEATURES
# ======================
def add_features(frame):
    frame["last2"] = frame["number"].str[-2:]
    frame["last3"] = frame["number"].str[-3:]

    freq_num = frame["number"].value_counts()
    frame["freq_num_win"] = frame["number"].map(freq_num).fillna(0).astype(int)

    freq_l2 = frame["last2"].value_counts()
    freq_l3 = frame["last3"].value_counts()

    frame["freq_last2_win"] = frame["last2"].map(freq_l2).fillna(0).astype(int)
    frame["freq_last3_win"] = frame["last3"].map(freq_l3).fillna(0).astype(int)

    frame["d1"] = frame["number"].str[0].astype(int)
    frame["d2"] = frame["number"].str[1].astype(int)
    frame["d3"] = frame["number"].str[2].astype(int)
    frame["d4"] = frame["number"].str[3].astype(int)

    return frame

df_train = add_features(df_train)

# ======================
# BUILD DATASET (positive+negative)
# ======================
all_numbers_int = np.arange(10000)
rows = []

for _, r in tqdm(df_train.iterrows(), total=len(df_train), desc="Building dataset"):
    # positive
    rows.append([
        r["day"], r["month"], r["weekday"], int(r["number"]),
        r["freq_num_win"], r["freq_last2_win"], r["freq_last3_win"],
        r["d1"], r["d2"], r["d3"], r["d4"], 1
    ])
    # negatives
    negs = np.random.choice(all_numbers_int, size=NEGATIVE_SAMPLES, replace=False)
    for n in negs:
        n_str = f"{n:04d}"
        rows.append([
            r["day"], r["month"], r["weekday"], n,
            0,0,0, int(n_str[0]), int(n_str[1]), int(n_str[2]), int(n_str[3]), 0
        ])

cols = ["day","month","weekday","number_int","freq_num_win","freq_last2_win","freq_last3_win","d1","d2","d3","d4","target"]
clf_df = pd.DataFrame(rows, columns=cols)

print("📊 Final dataset size:", clf_df.shape)

# ======================
# TRAIN / VAL SPLIT
# ======================
X = clf_df.drop("target", axis=1).values
y = clf_df["target"].values

X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.1, stratify=y, random_state=42)

# ======================
# KERAS MODEL
# ======================
model = keras.Sequential([
    layers.Input(shape=(X_train.shape[1],)),
    layers.Dense(128, activation="relu"),
    layers.Dropout(0.3),
    layers.Dense(64, activation="relu"),
    layers.Dropout(0.2),
    layers.Dense(1, activation="sigmoid")   # binary classification
])

model.compile(
    optimizer=keras.optimizers.Adam(learning_rate=0.001),
    loss="binary_crossentropy",
    metrics=["accuracy", keras.metrics.AUC(name="auc")]
)

print("⏳ Training Keras model...")
history = model.fit(
    X_train, y_train,
    validation_data=(X_val, y_val),
    epochs=10,
    batch_size=512,
    verbose=1
)

# ======================
# PREDICT FUTURE
# ======================
target_dt = pd.Timestamp(TARGET_DATE)
wk = target_dt.weekday()

pred = pd.DataFrame({
    "day": target_dt.day,
    "month": target_dt.month,
    "weekday": wk,
    "number_int": np.arange(10000)
})
pred["number"] = pred["number_int"].apply(lambda x: f"{x:04d}")
pred["last2"] = pred["number"].str[-2:]
pred["last3"] = pred["number"].str[-3:]

# Frequency lookups from training data
freq_num_lut = df_train.groupby("number")["freq_num_win"].max().to_dict()
freq_l2_lut  = df_train.groupby("last2")["freq_last2_win"].max().to_dict()
freq_l3_lut  = df_train.groupby("last3")["freq_last3_win"].max().to_dict()

pred["freq_num_win"] = pred["number"].map(freq_num_lut).fillna(0).astype(int)
pred["freq_last2_win"] = pred["last2"].map(freq_l2_lut).fillna(0).astype(int)
pred["freq_last3_win"] = pred["last3"].map(freq_l3_lut).fillna(0).astype(int)

# Digit features
pred["d1"] = pred["number"].str[0].astype(int)
pred["d2"] = pred["number"].str[1].astype(int)
pred["d3"] = pred["number"].str[2].astype(int)
pred["d4"] = pred["number"].str[3].astype(int)

# Use the same 11 features as training
X_future = pred[["day","month","weekday","number_int",
                 "freq_num_win","freq_last2_win","freq_last3_win",
                 "d1","d2","d3","d4"]].values

pred["prob"] = model.predict(X_future, verbose=0).flatten()

top_preds = pred.sort_values("prob", ascending=False).head(TOP_K)[["number","prob"]]

print(f"\n📅 Predicting for {TARGET_DATE.strftime('%d-%m-%Y')} (weekday={wk})")
print("\n🎯 Top predicted numbers:\n", top_preds)

