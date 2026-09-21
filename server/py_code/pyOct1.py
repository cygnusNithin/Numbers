# Who hits 12 next? Empirical-Bayes Poisson + momentum + week-of-year seasonality.
# Uses MongoDB: numbergrid.lotterydatas (schema you shared).
# pip install pandas numpy pymongo tqdm

import math
import numpy as np
import pandas as pd
from pymongo import MongoClient
from datetime import timedelta
from tqdm.auto import tqdm

# ==========================
# CONFIG
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
TARGET_PRIZE = 5000

THRESHOLD = 12           # target total appearances
MIN_CURRENT = 1          # only list numbers that already have >= MIN_CURRENT hits
TOP_K = 20               # how many to display

# Momentum and smoothing
EWMA_SPAN_WEEKS = 12     # recent momentum horizon
MOMENTUM_CLAMP = (0.5, 2.0)  # cap how extreme momentum can be
LAMBDA_MIN = 1e-6        # floor to avoid zero rates

# Seasonality (global, week-of-year)
SEASON_WOY_WEIGHT = 0.25 # 0..1: strength of week-of-year factor
KAPPA_WOY = 2000.0       # shrinkage toward global if current weekday-of-year data is sparse

# ==========================
# DATA LOAD (server-side aggregation)
# ==========================
client = MongoClient(MONGO_URI)
coll = client[DB_NAME][COLLECTION]

pipeline = [
    {"$unwind": "$series"},
    {"$addFields": {"prizeStr": {"$toString": "$series.prize"}}},
    {"$addFields": {"prizeClean": {"$replaceAll": {"input": "$prizeStr", "find": ",", "replacement": ""}}}},
    {"$addFields": {"prizeInt": {"$toInt": "$prizeClean"}}},
    {"$match": {"prizeInt": TARGET_PRIZE}},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "_id": 0,
        "dateStr": "$date",                        # "DD.MM.YYYY"
        "number": "$series.numbers.number",        # keep string
        "count": {"$ifNull": ["$series.numbers.count", 1]}
    }},
    {"$addFields": {
        "date": {"$dateFromString": {"dateString": "$dateStr", "format": "%d.%m.%Y", "onError": None, "onNull": None}}
    }},
    {"$match": {"date": {"$ne": None}}},
    {"$group": {"_id": {"date": "$date", "number": "$number"}, "count": {"$sum": "$count"}}},
    {"$project": {"_id": 0, "date": "$_id.date", "number": "$_id.number", "count": 1}},
    {"$sort": {"date": 1}}
]

print("Querying MongoDB...")
docs = list(coll.aggregate(pipeline, allowDiskUse=True))
flat = pd.DataFrame(docs)
if flat.empty:
    raise SystemExit("No prize=5000 rows found in DB.")

flat["date"] = pd.to_datetime(flat["date"], utc=True).dt.tz_localize(None)
flat["number"] = flat["number"].astype(str)
flat["count"] = flat["count"].astype(int)

# ==========================
# WEEKLY AGGREGATION
# ==========================
flat["week_start"] = flat["date"].dt.to_period("W-MON").dt.start_time
weekly = (flat.groupby(["number", "week_start"], as_index=False)["count"]
             .sum()
             .sort_values(["number", "week_start"]))

numbers = weekly["number"].unique().tolist()
min_week = weekly["week_start"].min()
max_week = weekly["week_start"].max()
weeks = pd.date_range(min_week, max_week, freq="W-MON")
T = len(weeks)
last_week = weeks[-1]

print(f"Prize={TARGET_PRIZE}: {len(numbers)} numbers, weeks: {weeks[0].date()} → {weeks[-1].date()} (T={T})")

# ==========================
# GLOBAL WEEK-OF-YEAR SEASONALITY
# ==========================
# Sum counts across numbers per week, get average by week-of-year, normalize ~1.0
week_totals = weekly.groupby("week_start")["count"].sum().reindex(weeks, fill_value=0)
woy = weeks.isocalendar().week.astype(int).to_numpy()
df_woy = pd.DataFrame({"w": weeks, "count": week_totals.values, "woy": woy})
s_woy_raw = df_woy.groupby("woy")["count"].mean()
s_woy = (s_woy_raw / (s_woy_raw.mean() if s_woy_raw.mean() > 0 else 1)).to_dict()

# Shrink next week-of-year toward 1.0 if data is sparse
next_week = last_week + timedelta(days=7)
next_woy = int(pd.Timestamp(next_week).isocalendar().week)
n_obs = len(df_woy[df_woy["woy"] == next_woy])
w_shrink = n_obs / (n_obs + KAPPA_WOY)
season_next = (1 - SEASON_WOY_WEIGHT) + SEASON_WOY_WEIGHT * (w_shrink * s_woy.get(next_woy, 1.0) + (1 - w_shrink) * 1.0)

# ==========================
# PER-NUMBER RATES (Empirical-Bayes + Momentum)
# ==========================
def last_nonzero_idx(a):
    nz = np.where(a > 0)[0]
    return int(nz[-1]) if len(nz) else None

per_num = []
long_means = []

print("Building per-number weekly series and features...")
for n in tqdm(numbers):
    s = (weekly[weekly["number"] == n]
            .set_index("week_start")["count"]
            .reindex(weeks, fill_value=0)
            .astype(float))
    total = float(s.sum())
    lmean = float(s.mean())  # mean per week
    long_means.append(lmean)
    ewma = float(s.ewm(span=EWMA_SPAN_WEEKS, adjust=False).mean().iloc[-1])

    idx_last = last_nonzero_idx(s.values)
    w_since_last = (len(s) - 1 - idx_last) if idx_last is not None else 9999

    per_num.append({
        "number": n,
        "total": total,
        "long_mean": lmean,
        "ewma": ewma,
        "weeks_since_last": int(w_since_last),
    })

per_num = pd.DataFrame(per_num)

overall_mean = float(np.mean(long_means))
overall_var = float(np.var(long_means, ddof=1)) if len(long_means) > 1 else 1e-12
overall_var = max(overall_var, 1e-12)

# Gamma-Poisson EB prior over weekly rate mu
alpha0 = (overall_mean**2) / overall_var
beta0  = overall_mean / overall_var

# Posterior mean lambda_base per week
per_num["lambda_base"] = (alpha0 + per_num["total"]) / (beta0 + T)

# Momentum factor (recent vs long-run), clamped
per_num["momentum"] = (per_num["ewma"] + 1e-8) / (per_num["long_mean"] + 1e-8)
per_num["momentum"] = per_num["momentum"].clip(MOMENTUM_CLAMP[0], MOMENTUM_CLAMP[1])

# Current effective weekly rate
per_num["lambda_now"] = per_num["lambda_base"] * per_num["momentum"] * season_next
per_num["lambda_now"] = per_num["lambda_now"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
per_num["lambda_now"] = per_num["lambda_now"].clip(lower=LAMBDA_MIN)

# ==========================
# HITTING TIME TO 12 (Gamma approx)
# ==========================
# Remaining R = THRESHOLD - total; T ~ Gamma(shape=R, rate=lambda_now)
def gamma_mean_weeks(R, lam): return float(R / lam) if (R > 0 and lam > 0) else np.inf
def gamma_median_weeks(R, lam):
    if R <= 0 or lam <= 0: return np.inf
    return float((R * (1 - 1/(9*R))**3) / lam)
Z80 = 0.841621
def gamma_q80_weeks(R, lam):
    if R <= 0 or lam <= 0: return np.inf
    return float((R + Z80*np.sqrt(R)) / lam)

print("Forecasting time to reach 12...")
rows = []
for r in tqdm(per_num.itertuples(index=False), total=len(per_num)):
    now = int(getattr(r, "total"))
    remaining = max(THRESHOLD - now, 0)
    if remaining <= 0:  # already at 12
        continue
    lam = float(getattr(r, "lambda_now"))  # per week
    mean_w = gamma_mean_weeks(remaining, lam)
    med_w  = gamma_median_weeks(remaining, lam)
    q80_w  = gamma_q80_weeks(remaining, lam)
    rows.append({
        "number": getattr(r, "number"),
        "now": now,
        "remaining": remaining,
        "lambda_now_per_week": lam,
        "weeks_mean": mean_w,
        "weeks_median": med_w,
        "weeks_p80": q80_w,
        "weeks_since_last": int(getattr(r, "weeks_since_last")),
        "momentum": float(getattr(r, "momentum")),
    })

forecast = pd.DataFrame(rows)
if forecast.empty:
    print("All numbers already at threshold.")
    raise SystemExit(0)

# Convert to dates (from last_week start)
def weeks_to_date(w):
    if not np.isfinite(w): return pd.NaT
    return (last_week + timedelta(days=int(round(w*7)))).date()

forecast["eta_mean_date"]   = forecast["weeks_mean"].apply(weeks_to_date)
forecast["eta_median_date"] = forecast["weeks_median"].apply(weeks_to_date)
forecast["eta_p80_date"]    = forecast["weeks_p80"].apply(weeks_to_date)

# Focus on numbers already close
close = forecast[forecast["now"] >= MIN_CURRENT].copy()
close = close.sort_values(["remaining", "weeks_median", "weeks_mean"], ascending=[True, True, True])

print(f"\nSeason next (week-of-year {next_woy}): multiplier ~ {season_next:.3f}")
print(f"Momentum clamp: {MOMENTUM_CLAMP}, EWMA span (weeks): {EWMA_SPAN_WEEKS}")

# ==========================
# OUTPUT TOP-K
# ==========================
top = close.head(TOP_K)
if top.empty:
    print("No numbers meet MIN_CURRENT filter. Lower MIN_CURRENT.")
else:
    print(f"\nTop {len(top)} numbers expected to reach {THRESHOLD} next:")
    print("(now = current hits, λ = weekly rate, med = median weeks, p80 = conservative weeks)")
    for i, r in enumerate(top.itertuples(index=False), 1):
        print(f"{i:2d}. {r.number:<6} now={r.now:2d}  λ={r.lambda_now_per_week:.4f}/wk  "
              f"med~{r.weeks_median:6.1f}w ({r.eta_median_date})  "
              f"mean~{r.weeks_mean:6.1f}w ({r.eta_mean_date})  "
              f"p80~{r.weeks_p80:6.1f}w ({r.eta_p80_date})  "
              f"mom={r.momentum:.2f}  wSL={r.weeks_since_last}")

# Optional: save full table
close.to_csv(f"prize_{TARGET_PRIZE}_reach{THRESHOLD}_forecast.csv", index=False)
print(f"\n💾 Saved: prize_{TARGET_PRIZE}_reach{THRESHOLD}_forecast.csv")