import re
import numpy as np
import pandas as pd
from pymongo import MongoClient
from tqdm.auto import tqdm  # progress bars

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

LOWER_PRIZES = {100, 200, 500, 1000, 2000}
ALL_PRIZES   = {100, 200, 500, 1000, 2000, 5000}
TARGET_PRIZE = 5000

PRESENCE_MODE = True            # any count>0 on a date counts as 1 appearance
YEARS = list(range(2020, 2026)) # 2020..2025 inclusive
HISTORY_MODE = "cumulative"     # "cumulative" or "in_year"

# =======================
# LOAD FROM MONGO (with progress)
# =======================
client = MongoClient(MONGO_URI)
col = client[DB_NAME][COLLECTION]

pipeline = [
    {"$unwind": "$series"},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "date": "$date",
        "prize": "$series.prize",
        "number": "$series.numbers.number",
        "count": {"$ifNull": ["$series.numbers.count", 1]},
    }}
]

print("🔄 Fetching data from MongoDB...")
rows = []
cursor = col.aggregate(pipeline, allowDiskUse=True)
for doc in tqdm(cursor, desc="Loading events"):
    rows.append(doc)
df = pd.DataFrame(rows)
print(f"📦 Loaded rows: {len(df)}")

# =======================
# CLEAN / NORMALIZE
# =======================
def parse_date_any(s):
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    return pd.to_datetime(s, errors="coerce")

print("🧹 Cleaning and normalizing...")
df["dt"] = df["date"].apply(parse_date_any)
df = df.dropna(subset=["dt"]).copy()

# keep only 4-digit numbers and relevant prizes
df["number"] = df["number"].astype(str).str.strip()
df = df[df["number"].str.match(r"^\d{1,4}$")].copy()
df["number"] = df["number"].str.zfill(4)

df["prize"] = pd.to_numeric(df["prize"], errors="coerce").astype("Int64")
df = df[df["prize"].isin(list(ALL_PRIZES))].copy()

df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)
df["day"] = df["dt"].dt.normalize()

# presence vs counts at (number, prize, day)
if PRESENCE_MODE:
    df = (df.groupby(["number", "prize", "day"], as_index=False)["count"]
            .size().rename(columns={"size": "appear"}))
    df["appear"] = 1
else:
    df = (df.groupby(["number", "prize", "day"], as_index=False)["count"]
            .sum().rename(columns={"count": "appear"}))

# derive year AFTER aggregation (fix for KeyError: 'year')
df["year"] = df["day"].dt.year

# Ensure sorted for per-number sequences
df = df.sort_values(["number", "day", "prize"]).reset_index(drop=True)
print(f"🔢 Unique numbers: {df['number'].nunique()}")

# =======================
# 5000 PRECEDENCE ANALYSIS (global function)
# =======================
def analyze_5000(group: pd.DataFrame) -> pd.DataFrame:
    # group has columns ['prize','day','appear'] for a single number
    g = group.sort_values(["day", "prize"]).copy()

    # Immediate previous event
    g["prev_day"] = g["day"].shift(1)
    g["prev_prize"] = g["prize"].shift(1).astype("Float64")

    # Ever had a lower prize before?
    lower_mask = g["prize"].isin(list(LOWER_PRIZES))
    g["lower_cum"] = lower_mask.cumsum()
    g["has_lower_before"] = g["lower_cum"].shift(1, fill_value=0) > 0

    # Last lower prize day and its prize (forward-fill over time)
    g["last_lower_day"] = g["day"].where(lower_mask)
    g["last_lower_prize"] = g["prize"].where(lower_mask)
    g["last_lower_day"] = g["last_lower_day"].ffill()
    g["last_lower_prize"] = g["last_lower_prize"].ffill()

    # Gaps in days
    g["gap_days_from_last_lower"] = (g["day"] - g["last_lower_day"]).dt.days
    g["gap_days_from_prev"] = (g["day"] - g["prev_day"]).dt.days

    # Keep only TARGET_PRIZE rows
    f5 = g[g["prize"] == TARGET_PRIZE].copy()
    if f5.empty:
        return f5

    # Immediate previous is lower prize?
    f5["immediate_prev_is_lower"] = f5["prev_prize"].isin(list(LOWER_PRIZES))

    # Window flags (strictly-before implied by last_lower_day <= current day)
    for win in [7, 30, 90, 180]:
        f5[f"has_lower_within_{win}d"] = f5["has_lower_before"] & (f5["gap_days_from_last_lower"] <= win)

    # Same-day lower (gap=0)
    f5["same_day_lower"] = f5["gap_days_from_last_lower"].fillna(1e9).astype(int).eq(0)

    return f5[[
        "day",
        "prev_day", "prev_prize",
        "has_lower_before", "immediate_prev_is_lower",
        "last_lower_day", "last_lower_prize",
        "gap_days_from_last_lower", "gap_days_from_prev",
        "same_day_lower",
        "has_lower_within_7d", "has_lower_within_30d",
        "has_lower_within_90d", "has_lower_within_180d"
    ]]

print("📈 Computing global 5000 precedence (for cumulative mode)...")
tqdm.pandas(desc="Per-number global")
f5_global_list = []
for num, g in tqdm(df.groupby("number")[["prize","day","appear"]], total=df["number"].nunique(), desc="Numbers"):
    part = analyze_5000(g)
    if not part.empty:
        part = part.copy()
        part.insert(0, "number", num)
        f5_global_list.append(part)
f5_global = pd.concat(f5_global_list, ignore_index=True) if f5_global_list else pd.DataFrame()
if not f5_global.empty:
    f5_global.rename(columns={"day":"date"}).to_csv("5000_precedence_analysis_GLOBAL.csv", index=False, encoding="utf-8")
    print("✅ Saved 5000_precedence_analysis_GLOBAL.csv")

# =======================
# HELPERS
# =======================
def prize_transition_counts(df_sub: pd.DataFrame) -> pd.DataFrame:
    prizes_sorted = sorted(ALL_PRIZES)
    Pcounts = pd.DataFrame(0, index=prizes_sorted, columns=prizes_sorted, dtype=int)
    for _, g in df_sub.groupby("number", sort=False):
        gg = g.sort_values(["day", "prize"])
        prev = None
        for p in gg["prize"]:
            if prev is not None:
                if prev in Pcounts.index and p in Pcounts.columns:
                    Pcounts.loc[prev, p] += 1
            prev = p
    return Pcounts

def daily_lift_30d(df_year: pd.DataFrame, year: int):
    lower_df = df_year[df_year["prize"].isin(LOWER_PRIZES)][["number","day"]].drop_duplicates()
    tgt_df   = df_year[df_year["prize"] == TARGET_PRIZE][["number","day"]].drop_duplicates()
    lower_by_day = {d: set(g["number"]) for d, g in lower_df.groupby("day")}
    tgt_by_day   = {d: set(g["number"]) for d, g in tgt_df.groupby("day")}
    all_days = np.array(sorted(df_year["day"].unique()))
    last_lower = {}  # resets each year
    exposure_total = exposure_hits = baseline_total = baseline_hits = 0
    rows = []
    for d in tqdm(all_days, desc=f"Lift days {year}"):
        expo_nums = set(n for n, ld in last_lower.items() if (d - ld) / np.timedelta64(1, "D") <= 30)
        outs = tgt_by_day.get(d, set())
        exp_cnt = len(expo_nums)
        exp_hits = len(expo_nums & outs)
        exposure_total += exp_cnt
        exposure_hits  += exp_hits
        baseline_total += 10000  # 0000..9999 universe
        baseline_hits  += len(outs)
        rows.append({"date": d.date(), "exposed_count": exp_cnt, "exposed_hits_5000": exp_hits, "total_5000_today": len(outs)})
        for n in lower_by_day.get(d, set()):
            last_lower[n] = d
    lift = ((exposure_hits / max(exposure_total, 1)) / (baseline_hits / max(baseline_total, 1))) if baseline_hits > 0 else np.nan
    return lift, pd.DataFrame(rows)

def summarize_f5(f5_sub: pd.DataFrame):
    if f5_sub.empty:
        return {
            "total_f5": 0, "ever_lower_pct": 0, "immediate_lower_pct": 0,
            "gap_median": np.nan, "gap_mean": np.nan, "gap_p95": np.nan,
            "same_day_pct": 0, "within_7d_pct": 0, "within_30d_pct": 0,
            "within_90d_pct": 0, "within_180d_pct": 0
        }
    n = len(f5_sub)
    pct = lambda s: round(100 * s.sum() / n, 2)
    gaps = f5_sub["gap_days_from_last_lower"].dropna()
    return {
        "total_f5": n,
        "ever_lower_pct": pct(f5_sub["has_lower_before"]),
        "immediate_lower_pct": pct(f5_sub["immediate_prev_is_lower"]),
        "gap_median": int(np.median(gaps)) if not gaps.empty else np.nan,
        "gap_mean": float(gaps.mean()) if not gaps.empty else np.nan,
        "gap_p95": int(np.percentile(gaps, 95)) if not gaps.empty else np.nan,
        "same_day_pct": pct(f5_sub["same_day_lower"]) if "same_day_lower" in f5_sub else 0,
        "within_7d_pct": pct(f5_sub["has_lower_within_7d"]) if "has_lower_within_7d" in f5_sub else 0,
        "within_30d_pct": pct(f5_sub["has_lower_within_30d"]) if "has_lower_within_30d" in f5_sub else 0,
        "within_90d_pct": pct(f5_sub["has_lower_within_90d"]) if "has_lower_within_90d" in f5_sub else 0,
        "within_180d_pct": pct(f5_sub["has_lower_within_180d"]) if "has_lower_within_180d" in f5_sub else 0,
    }

# Safe formatting helpers (fix f-string ValueError)
def fmt_float(x, nd=1):
    try:
        if x is None or pd.isna(x) or not np.isfinite(x):
            return "na"
        return f"{float(x):.{nd}f}"
    except Exception:
        return "na"

def fmt_int(x):
    try:
        if x is None or pd.isna(x):
            return "na"
        return str(int(x))
    except Exception:
        return "na"

# =======================
# YEAR-BY-YEAR LOOP
# =======================
summary_rows = []
for year in YEARS:
    print(f"\n===== Year {year} =====")
    df_year = df[df["year"] == year].copy()
    if df_year.empty:
        print("No data for this year.")
        summary_rows.append({"year": year, "note": "no data", "history_mode": HISTORY_MODE})
        continue

    # 5000 precedence subset
    if HISTORY_MODE == "cumulative":
        f5_y = f5_global[f5_global["day"].dt.year == year].copy()
    else:  # in_year mode: recompute within the year only
        print(f"📈 Recomputing per-number 5000 precedence (in_year mode) for {year}...")
        f5_list = []
        for num, g in tqdm(df_year.groupby("number")[["prize","day","appear"]], total=df_year["number"].nunique(), desc=f"Numbers {year}"):
            part = analyze_5000(g)
            if not part.empty:
                part = part.copy()
                part.insert(0, "number", num)
                f5_list.append(part)
        f5_y = pd.concat(f5_list, ignore_index=True) if f5_list else pd.DataFrame()

    # Save per-year 5000 analysis
    if not f5_y.empty:
        f5_y.rename(columns={"day":"date"}).to_csv(f"5000_precedence_analysis_{year}.csv", index=False, encoding="utf-8")
        print(f"✅ Saved 5000_precedence_analysis_{year}.csv")

    # Summary (patched formatting)
    s = summarize_f5(f5_y)
    print(f"(1) 5000 appearances: {s['total_f5']}")
    print(f"  - Ever lower before: {s['ever_lower_pct']}%")
    print(f"  - Immediate prev lower: {s['immediate_lower_pct']}%")
    print(f"  - Gap median/mean/p95: {fmt_int(s.get('gap_median'))}/{fmt_float(s.get('gap_mean'), nd=1)}/{fmt_int(s.get('gap_p95'))}")
    print(f"  - Same-day: {s['same_day_pct']}%")
    print(f"  - Within 7/30/90/180 days: {s['within_7d_pct']}% / {s['within_30d_pct']}% / {s['within_90d_pct']}% / {s['within_180d_pct']}%")

    # Gap by last-lower prize
    if not f5_y.empty and "last_lower_prize" in f5_y.columns:
        br = f5_y.dropna(subset=["last_lower_prize"]).copy()
        if not br.empty:
            br["last_lower_prize"] = br["last_lower_prize"].astype(int)
            gap_by_prize = (br.groupby("last_lower_prize")["gap_days_from_last_lower"]
                              .agg(count="size", median="median", mean="mean",
                                   p25=lambda s: np.percentile(s.dropna(),25),
                                   p75=lambda s: np.percentile(s.dropna(),75),
                                   p90=lambda s: np.percentile(s.dropna(),90),
                                   p95=lambda s: np.percentile(s.dropna(),95)))
            gap_by_prize.to_csv(f"gap_by_last_lower_prize_{year}.csv", encoding="utf-8")
            print(f"✅ Saved gap_by_last_lower_prize_{year}.csv")

    # Prize transitions per year
    T_year = prize_transition_counts(df_year)
    T_year.to_csv(f"prize_transition_counts_{year}.csv", encoding="utf-8")
    print(f"✅ Saved prize_transition_counts_{year}.csv")

    # Daily lift (30d exposure) per year
    lift, lift_df = daily_lift_30d(df_year, year)
    lift_df.to_csv(f"daily_lift_30d_timeseries_{year}.csv", index=False, encoding="utf-8")
    print(f"✅ Saved daily_lift_30d_timeseries_{year}.csv")
    print(f"(3) Daily 30d-exposure lift to 5000 in {year}: {fmt_float(lift, nd=2)}×")

    # Add to yearly summary
    summary_rows.append({
        "year": year,
        **s,
        "lift_30d_exposure_x": round(float(lift), 3) if lift == lift else np.nan,
        "history_mode": HISTORY_MODE
    })

# =======================
# SAVE YEARLY SUMMARY
# =======================
summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv("yearly_summary.csv", index=False, encoding="utf-8")
print("✅ Saved yearly_summary.csv")