import os
import numpy as np
import pandas as pd
from pymongo import MongoClient
from tqdm.auto import tqdm

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME   = "numbergrid"
COLL      = "lotterydatas"

PRIZES_NON5000 = [100, 200, 500, 1000, 2000]
ALL_PRIZES     = set(PRIZES_NON5000 + [5000])

# Tuned defaults if hazard windows CSVs are not present
DEFAULT_WINDOWS_PRE2025 = {
    100: [(28, 45)],
    500: [(28, 45)],
    200: [(25, 35)],
    1000: [(25, 40)],
    2000: [(25, 45)],
}
DEFAULT_WINDOWS_2025 = {
    100: [(24, 32)],
    500: [(24, 32)],
    200: [(16, 24)],
    1000: [(22, 32)],
    2000: [(22, 36)],
}

ACTIVE_WINDOW_DAYS        = 180   # only numbers active in last X days
EXCLUDE_5000_WITHIN_DAYS  = 30    # exclude if 5000 in last X days
SCHEDULE_HORIZON_DAYS     = 30    # schedule next X days
TOP_TODAY                 = 200   # how many to list for today
PROXIMITY_TAU             = 5     # soft preference for center of window

# Quotas to diversify today’s picks (sum should be <= TOP_TODAY; remaining filled globally)
QUOTAS_2025 = {100: 80, 500: 60, 200: 40, 1000: 10, 2000: 10}
QUOTAS_PRE  = {100: 80, 500: 60, 200: 20, 1000: 20, 2000: 20}

# If you generated hazard windows from your data, set paths here
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
    # Expect: columns {cohort, prize, bucket ("lo-hi" or "40+"), hit_rate, exposed_days}
    if not os.path.exists(path):
        return None
    dfw = pd.read_csv(path)
    wins = {}
    for p in PRIZES_NON5000:
        sub = dfw[dfw["prize"] == p].copy()
        out = []
        for _, r in sub.iterrows():
            lbl = str(r["bucket"])
            if lbl.endswith("+"):
                lo = int(lbl[:-1]); hi = 10**9
            else:
                a, b = lbl.split("-"); lo, hi = int(a), int(b)
            rate = float(r.get("hit_rate", 0.0))
            if not np.isfinite(rate) or rate <= 0:
                rate = 1e-6  # avoid zeros so proximity can still rank
            out.append({"lo": lo, "hi": hi, "rate": rate, "bucket": lbl})
        wins[p] = out
    return wins

def pick_windows(today_year):
    if today_year == 2025:
        wins = load_windows_from_csv(HAZARD_WINDOWS_2025_CSV) or \
               {p: [{"lo": lo, "hi": hi, "rate": 1.0, "bucket": f"{lo}-{hi}"} for (lo,hi) in DEFAULT_WINDOWS_2025[p]]
                for p in PRIZES_NON5000}
        quotas = QUOTAS_2025
        cohort = "y2025"
    else:
        wins = load_windows_from_csv(HAZARD_WINDOWS_PRE2025_CSV) or \
               {p: [{"lo": lo, "hi": hi, "rate": 1.0, "bucket": f"{lo}-{hi}"} for (lo,hi) in DEFAULT_WINDOWS_PRE2025[p]]
                for p in PRIZES_NON5000}
        quotas = QUOTAS_PRE
        cohort = "pre2025"
    for p in PRIZES_NON5000:
        if p not in wins:
            wins[p] = []
    return cohort, wins, quotas

def in_any_window(gap, windows):
    for w in windows:
        if int(w["lo"]) <= gap <= int(w["hi"]):
            return True
    return False

def days_to_window_center(gap, windows):
    # Return minimal positive days to reach the center of any window (0 if already at center), else None
    best = None
    for w in windows:
        lo, hi = int(w["lo"]), int(w["hi"])
        if hi == 10**9:
            mid = lo  # treat open-ended as at least lo
        else:
            mid = (lo + hi) / 2.0
        delta = int(np.ceil(mid - gap))
        if delta >= 0:
            if best is None or delta < best:
                best = delta
    return best

def safe_len(x): return 0 if x is None else len(x)

# =======================
# LOAD FROM MONGO
# =======================
print("🔄 Fetching data from MongoDB...")
client = MongoClient(MONGO_URI)
col = client[DB_NAME][COLL]
pipe = [
    {"$unwind": "$series"},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "date": "$date",
        "prize": "$series.prize",
        "number": "$series.numbers.number",
        "count": {"$ifNull": ["$series.numbers.count", 1]},
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
# Presence per (number, prize, day)
df = df.groupby(["number","prize","day"], as_index=False).size()
df = df.sort_values(["number","day","prize"]).reset_index(drop=True)

today = df["day"].max()
today_year = int(pd.Timestamp(today).year)
cohort, hz_windows, quotas = pick_windows(today_year)
print(f"Using cohort '{cohort}' windows.")

# =======================
# BUILD LAST-SEEN MAPS
# =======================
print("🔧 Building last-seen maps...")
days = sorted(df["day"].unique())
any_by_day = {d: set(g["number"]) for d,g in df[["number","day"]].drop_duplicates().groupby("day")}
by_prize = {
    p: {d: set(g["number"]) for d,g in df[df["prize"]==p][["number","day"]].drop_duplicates().groupby("day")}
    for p in PRIZES_NON5000
}
tgt_by_day = {d: set(g["number"]) for d,g in df[df["prize"]==5000][["number","day"]].drop_duplicates().groupby("day")}

last_any = {}
last_5000 = {}
last_by_pr = {p:{} for p in PRIZES_NON5000}

for d in tqdm(days, desc="Scanning days"):
    # update last_any
    for n in any_by_day.get(d, set()):
        last_any[n] = d
    # update last seen per non-5000 prize
    for p in PRIZES_NON5000:
        for n in by_prize[p].get(d, set()):
            last_by_pr[p][n] = d
    # update last 5000
    for n in tgt_by_day.get(d, set()):
        last_5000[n] = d

# =======================
# TODAY CANDIDATES (weighted by hit_rate and proximity; with quotas)
# =======================
print("🧮 Selecting today candidates...")
# Active set
active = set(n for n, ld in last_any.items() if (today - ld) / np.timedelta64(1,"D") <= ACTIVE_WINDOW_DAYS)

rows = []
for n in active:
    # exclude recent 5000
    if n in last_5000:
        gap5000 = int((today - last_5000[n]) / np.timedelta64(1,"D"))
        if gap5000 <= EXCLUDE_5000_WITHIN_DAYS:
            continue

    # last_prize_any (most recent among 100/200/500/1000/2000)
    best_p, best_day = None, None
    for p in PRIZES_NON5000:
        ld = last_by_pr[p].get(n)
        if ld is None: 
            continue
        if (best_day is None) or (ld > best_day):
            best_day, best_p = ld, p
    if best_p is None:
        continue

    gap = int((today - best_day) / np.timedelta64(1,"D"))
    wins = hz_windows.get(best_p, [])
    if not wins:
        continue

    # score by window rate and proximity to center
    score = 0.0; chosen = None
    for w in wins:
        lo, hi, rate = int(w["lo"]), int(w["hi"]), float(w["rate"])
        if lo <= gap <= hi:
            mid = lo if hi == 10**9 else (lo + hi) / 2.0
            prox = np.exp(-abs(gap - mid) / max(1, PROXIMITY_TAU))
            score += rate * prox
            chosen = w.get("bucket", f"{lo}-{hi if hi!=10**9 else '+'}")
    if score > 0:
        rows.append({"number": n, "last_prize_any": best_p, "gap_days": gap,
                     "chosen_window": chosen, "score": score})

cand = pd.DataFrame(rows).sort_values(["score","gap_days"], ascending=[False, True])

# Enforce quotas then fill remaining
def apply_quotas(df_cand, quotas, top_n):
    if df_cand.empty:
        return df_cand
    picks, used = [], set()
    for p, q in quotas.items():
        sub = df_cand[(df_cand["last_prize_any"] == p) & (~df_cand["number"].isin(used))]
        if not sub.empty:
            take = sub.head(q)
            picks.append(take)
            used |= set(take["number"].values)
    total_picked = sum(len(x) for x in picks) if picks else 0
    if total_picked < top_n:
        fill = df_cand[~df_cand["number"].isin(used)].head(top_n - total_picked)
        if not fill.empty: picks.append(fill)
    out = pd.concat(picks, ignore_index=True) if picks else df_cand.head(top_n)
    return out.head(top_n).sort_values(["score","gap_days"], ascending=[False, True])

today_picks = apply_quotas(cand, quotas, TOP_TODAY)

out_today = today_picks[["number","last_prize_any","gap_days","chosen_window","score"]].copy()
out_today.to_csv(f"today_candidates_{cohort}_weighted.csv", index=False, encoding="utf-8")
print(f"✅ Saved today_candidates_{cohort}_weighted.csv ({len(out_today)} rows)")
print("Counts by last_prize_any:")
print(out_today["last_prize_any"].value_counts().sort_index())

# =======================
# SCHEDULE NEXT N DAYS (aim for window center)
# =======================
print("🗓️  Building schedule...")
schedule_rows = []
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
            best_day, best_p = ld, p
    if best_p is None:
        continue

    gap = int((today - best_day) / np.timedelta64(1,"D"))
    wins = hz_windows.get(best_p, [])
    if not wins:
        continue

    # days to center of nearest window
    dte = days_to_window_center(gap, wins)
    if dte is not None and 0 < dte <= SCHEDULE_HORIZON_DAYS:
        target_date = today + np.timedelta64(int(dte), "D")
        schedule_rows.append({
            "date": str(pd.Timestamp(target_date).date()),
            "number": n,
            "last_prize_any": best_p,
            "gap_today": gap,
            "days_to_enter": int(dte)
        })

schedule_df = pd.DataFrame(schedule_rows).sort_values(["date","last_prize_any","days_to_enter","number"])
schedule_df.to_csv(f"schedule_next_{SCHEDULE_HORIZON_DAYS}d_{cohort}_weighted.csv", index=False, encoding="utf-8")
print(f"✅ Saved schedule_next_{SCHEDULE_HORIZON_DAYS}d_{cohort}_weighted.csv ({len(schedule_df)} rows)")

# =======================
# PREVIEW
# =======================
print("\nTop today candidates (preview):")
print(out_today.head(50).to_string(index=False))
print("\nNext few scheduled entries:")
print(schedule_df.head(50).to_string(index=False))