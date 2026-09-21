import pandas as pd
import numpy as np
from tqdm import tqdm
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.metrics import r2_score

# ======================
# CONFIG
# ======================
ALL_FILE = "all_prizes_number_patterns2.csv"
P5000_FILE = "5000_number_patterns5.csv"
OUTPUT_FILE = "comparison_analysis1.csv"

print("📂 Loading CSV files...")
df_all = pd.read_csv(ALL_FILE)
df_5000 = pd.read_csv(P5000_FILE)

# Normalize number to 4-digit string
df_all["number"] = df_all["number"].astype(str).str.zfill(4)
df_5000["number"] = df_5000["number"].astype(str).str.zfill(4)

# Merge datasets
df = pd.merge(
    df_all[["number", "total_hits", "dates"]],
    df_5000[["number", "total_hits", "dates"]],
    on="number",
    suffixes=("_all", "_5000"),
    how="outer"
).fillna(0)

df["total_hits_all"] = df["total_hits_all"].astype(int)
df["total_hits_5000"] = df["total_hits_5000"].astype(int)

# Ratio of 5000 hits to all hits
df["ratio"] = df.apply(
    lambda r: r["total_hits_5000"]/r["total_hits_all"]
    if r["total_hits_all"] > 0 else 0,
    axis=1
)

# --- Feature Engineering ---
def avg_gap(dates_str):
    if not dates_str or dates_str == 0:
        return None
    dates = [pd.to_datetime(d, dayfirst=True, errors="coerce") for d in str(dates_str).split("|")]
    dates = [d for d in dates if pd.notna(d)]
    if len(dates) < 2:
        return None
    dates = sorted(dates)
    gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
    return np.mean(gaps)

print("🔄 Calculating average gaps...")
df["avg_gap_all"] = [avg_gap(d) for d in tqdm(df["dates_all"], desc="All prizes gaps")]
df["avg_gap_5000"] = [avg_gap(d) for d in tqdm(df["dates_5000"], desc="5000 gaps")]

# Fill NaN gaps with 0
df = df.fillna({"avg_gap_all": 0, "avg_gap_5000": 0})

# --- ML Regression Model ---
print("⚡ Training regression model...")
X = df[["total_hits_all", "avg_gap_all"]].values
y = df["total_hits_5000"].values

model = RandomForestRegressor(n_estimators=200, random_state=42)
model.fit(X, y)
y_pred = model.predict(X)

df["predicted_5000_hits"] = y_pred
df["prediction_error"] = df["total_hits_5000"] - df["predicted_5000_hits"]

print(f"✅ Regression R² score: {r2_score(y, y_pred):.3f}")

# --- Anomaly Detection ---
print("🔍 Running anomaly detection (Isolation Forest)...")
iso = IsolationForest(contamination=0.05, random_state=42)
df["anomaly_score"] = iso.fit_predict(df[["ratio", "prediction_error"]])

df["is_anomaly"] = df["anomaly_score"].apply(lambda x: "⚠️ YES" if x == -1 else "NO")

# --- Save Results ---
df_out = df[[
    "number", "total_hits_all", "total_hits_5000", "ratio",
    "avg_gap_all", "avg_gap_5000",
    "predicted_5000_hits", "prediction_error",
    "is_anomaly"
]]

# 🔽 Dual sort: first by 5000 prize hits, then by all-prize hits
df_out = df_out.sort_values(
    by=["total_hits_5000", "total_hits_all"],
    ascending=[False, False]
)

df_out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
print(f"✅ Saved analysis to {OUTPUT_FILE} ({len(df_out)} rows, sorted by 5000 and all-prize hits)")
