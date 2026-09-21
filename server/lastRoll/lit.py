import numpy as np
import pandas as pd
from pymongo import MongoClient
from tqdm.auto import tqdm
import os

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME   = "numbergrid"
COLL      = "lotterydatas"

PRIZES_NON5000 = [100, 200, 500, 1000, 2000]
ALL_PRIZES     = set(PRIZES_NON5000 + [5000])

# Default windows if you don't have hazard_windows_*.csv
DEFAULT_WINDOWS_PRE2025 = {
    100: [(28,45)], 500: [(28,45)], 1000: [(25,40)], 2000: [(25,45)], 200: [(25,35)]
}
DEFAULT_WINDOWS_2025 = {
    100: [(20,35)], 500: [(20,35)], 200: [(14,28)], 1000: [(20,35)], 2000: [(20,40)]
}

ACTIVE_WINDOW_DAYS        = 180   # only consider numbers active in last X days
EXCLUDE_5000_WITHIN_DAYS  = 30    # exclude if 5000 in last X days
SCHEDULE_HORIZON_DAYS     = 30    # build schedule for next X days
TOP_TODAY                 = 100   # how many to list for today

# If you saved hazard windows from previous step, set paths here (optional)
HAZARD_WINDOWS_PRE2025_CSV = "hazard_windows_pre2025.csv"
HAZARD_WINDOWS_2025_CSV    = "hazard_windows_y2025.csv"

# =======================
# HELPERS
# =======================
def parse_date_any(s):
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    return pd.to_datetime(s, errors="coerce")

def load_windows_from_csv(path):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    # Expect columns: cohort, prize, bucket, hit_rate, exposed_days
    # Parse bucket like "28-35" or "40+"
    wins = {}
    for p in PRIZES_NON5000:
        sub = df[df["prize"] == p]
        out = []
        for _, r in sub.iterrows():
            lbl = str(r["bucket"])
            if lbl.endswith("+"):
                lo = int(lbl[:-1]); hi = 10**9
            else:
                a, b = lbl.split("-"); lo, hi = int(a), int(b)
            out.append((lo, hi))
        wins[p] = out
    return wins

def pick_windows(today_year):
    # Prefer hazard windows CSVs; fall back to defaults
    if today_year == 2025:
        wins = load_windows_from_csv(HAZARD_WINDOWS_2025_CSV) or DEFAULT_WINDOWS_2025
        cohort = "y2025"
    else:
        wins = load_windows_from_csv(HAZARD_WINDOWS_PRE2025_CSV) or DEFAULT_WINDOWS_PRE2025
        cohort = "pre2025"
    # Ensure all prizes present
    for p in PRIZES_NON5000:
        if p not in wins:
            wins[p] = []
    return cohort, wins

def in_any_window(gap, windows):
    for lo, hi in windows:
        if lo <= gap <= hi:
            return True
    return False

def nearest_days_to_enter(gap, windows):
    # 0 if already in; else min distance to any window range (lower edge if below; upper edge if above)
    best = 10**9
    for lo, hi in windows:
        if lo <= gap <= hi:
            return 0
        if gap < lo:
            best = min(best, lo - gap)
        else:
            best = min(best, 0)  # already above; we don't schedule exiting windows
    return best if best != 10**9 else None

# =======================
# LOAD FROM MONGO
# =======================
print("🔄 Fetching data from MongoDB...")
client = MongoClient(MONGO_URI)
col = client[DB_NAME][COLL]
pipe = [
    {"$unwind":"$series"},
    {"$unwind":"$series.numbers"},
    {"$project":{
        "date":"$date", "prize":"$series.prize",
        "number":"$series.numbers.number",
        "count":{"$ifNull":["$series.numbers.count",1]}
    }}
]
rows = list(tqdm(col.aggregate(pipe, allowDiskUse=True), desc="Loading events"))
df = pd.DataFrame(rows)
print(f"📦 Loaded rows: {len(df)}")

# =======================
# CLEAN / AGGREGATE PRESENCE
# =======================
print("🧹 Cleaning and normalizing...")
df["dt"] = df["date"].apply(parse_date_any)
df = df.dropna(subset=["dt"]).copy()
df["day"] = df["dt"].dt.normalize()
df["year"] = df["day"].dt.year
df["number"] = df["number"].astype(str).str.strip().str.zfill(4)
df["prize"] = pd.to_numeric(df["prize"], errors="coerce").astype("Int64")
df = df[df["prize"].isin(ALL_PRIZES)].copy()
# Presence per day
df = df.groupby(["number","prize","day"], as_index=False).size()

# =======================
# BUILD LAST-SEEN MAPS
# =======================
print("🔧 Building last-seen maps...")
days = sorted(df["day"].unique())
any_by_day = {d: set(g["number"]) for d,g in df[["number","day"]].drop_duplicates().groupby("day")}
by_prize = {p: {d: set(g["number"]) for d,g in df[df["prize"]==p][["number","day"]].drop_duplicates().groupby("day")}
            for p in PRIZES_NON5000}
tgt_by_day = {d: set(g["number"]) for d,g in df[df["prize"]==5000][["number","day"]].drop_duplicates().groupby("day")}

last_any    = {}
last_5000   = {}
last_by_pr  = {p:{} for p in PRIZES_NON5000}

for d in tqdm(days, desc="Scanning days"):
    # update last_any
    for n in any_by_day.get(d, set()):
        last_any[n] = d
    # update per prize
    for p in PRIZES_NON5000:
        for n in by_prize[p].get(d, set()):
            last_by_pr[p][n] = d
    # update last 5000
    for n in tgt_by_day.get(d, set()):
        last_5000[n] = d

today = max(days)
today_year = int(pd.Timestamp(today).year)
cohort, windows = pick_windows(today_year)
print(f"Using cohort '{cohort}' windows: {windows}")

# =======================
# TODAY CANDIDATES
# =======================
print("🧮 Selecting today candidates...")
# Active set
active = set(n for n, ld in last_any.items() if (today - ld) / np.timedelta64(1,"D") <= ACTIVE_WINDOW_DAYS)

rows_today = []
rows_sched = []

for n in active:
    # exclude recent 5000
    if n in last_5000:
        gap5000 = int((today - last_5000[n]) / np.timedelta64(1,"D"))
        if gap5000 <= EXCLUDE_5000_WITHIN_DAYS:
            continue

    # last_prize_any
    best_p, best_day = None, None
    for p in PRIZES_NON5000:
        ld = last_by_pr[p].get(n)
        if ld is None: 
            continue
        if (best_day is None) or (ld > best_day):
            best_day = ld; best_p = p
    if best_p is None:
        continue

    gap = int((today - best_day) / np.timedelta64(1,"D"))
    wins = windows.get(best_p, [])
    if not wins:
        continue

    # is in window?
    if in_any_window(gap, wins):
        rows_today.append({"number": n, "last_prize_any": best_p, "gap_days": gap})
    else:
        # schedule entry within horizon
        dte = nearest_days_to_enter(gap, wins)
        if dte is not None and 0 < dte <= SCHEDULE_HORIZON_DAYS:
            target_date = today + np.timedelta64(dte, "D")
            rows_sched.append({"date": str(pd.Timestamp(target_date).date()),
                               "number": n, "last_prize_any": best_p,
                               "gap_today": gap, "days_to_enter": int(dte)})

today_df = pd.DataFrame(rows_today).sort_values(["last_prize_any","gap_days"])
sched_df = pd.DataFrame(rows_sched).sort_values(["date","last_prize_any"])

# Optional: cap to top-N for human use
today_df = today_df.head(TOP_TODAY)

today_df.to_csv(f"today_candidates_{cohort}.csv", index=False, encoding="utf-8")
sched_df.to_csv(f"schedule_next_{SCHEDULE_HORIZON_DAYS}d_{cohort}.csv", index=False, encoding="utf-8")
print(f"✅ Saved today_candidates_{cohort}.csv ({len(today_df)} rows)")
print(f"✅ Saved schedule_next_{SCHEDULE_HORIZON_DAYS}d_{cohort}.csv ({len(sched_df)} rows)")

print("\nTop today candidates:")
print(today_df.to_string(index=False))