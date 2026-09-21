import re
import numpy as np
import pandas as pd
from pymongo import MongoClient
from tqdm.auto import tqdm

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

PRIZES_NON5000 = [100, 200, 500, 1000, 2000]
ALL_PRIZES     = set(PRIZES_NON5000 + [5000])
TARGET_PRIZE   = 5000

PRESENCE_MODE  = True     # any count>0 on a date counts as 1 appearance
YEARS_START    = 2021     # focus from 2021 onward

# =======================
# LOAD FROM MONGO
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

df["year"] = df["day"].dt.year
df = df.sort_values(["number", "day", "prize"]).reset_index(drop=True)
print(f"🔢 Unique numbers: {df['number'].nunique()}")

# Safe formatting helpers
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
# ANALYZE: per-number, per-5000 with specific last-prize tracking
# =======================
def analyze_by_prize(group: pd.DataFrame) -> pd.DataFrame:
    # group has ['prize','day','appear'] for one number
    g = group.sort_values(["day", "prize"]).copy()

    # Immediate previous event (any prize)
    g["prev_day"] = g["day"].shift(1)
    g["prev_prize"] = g["prize"].shift(1).astype("Float64")

    # Rolling last-day for each non-5000 prize
    for p in PRIZES_NON5000:
        mask = g["prize"].eq(p)
        g[f"last_{p}_day"] = g["day"].where(mask).ffill()

    f5 = g[g["prize"] == TARGET_PRIZE].copy()
    if f5.empty:
        return f5

    # Gaps per prize
    for p in PRIZES_NON5000:
        f5[f"gap_{p}"] = (f5["day"] - f5[f"last_{p}_day"]).dt.days

    # Windows per prize
    for p in PRIZES_NON5000:
        for w in [7, 30, 90, 180]:
            f5[f"has_{p}_within_{w}d"] = f5[f"gap_{p}"] <= w

    # Determine last_prize_any = argmax of last_{p}_day
    # Convert datetimes to int64, handle NaT as very small
    last_day_int = []
    for p in PRIZES_NON5000:
        arr = f5[f"last_{p}_day"].values.astype("datetime64[ns]").astype("int64")
        # NaT -> very negative; keep as is
        last_day_int.append(arr)
    M = np.column_stack(last_day_int) if last_day_int else np.empty((len(f5), 0), dtype="int64")

    if M.shape[1] > 0:
        idx_max = M.argmax(axis=1)  # returns 0..len(PRIZES_NON5000)-1
        # Rows where all are NaT will still pick 0; correct to NaN by checking if max is NaT
        max_vals = M[np.arange(M.shape[0]), idx_max]
        has_any = max_vals > np.iinfo(np.int64).min // 2  # any valid date
        last_prize_any = np.where(has_any, np.array(PRIZES_NON5000)[idx_max], np.nan)
        f5["last_prize_any"] = last_prize_any

        # gap from that last_prize_any (row-wise pick)
        gap_stack = np.column_stack([f5[f"gap_{p}"].values for p in PRIZES_NON5000])
        gap_any = gap_stack[np.arange(gap_stack.shape[0]), idx_max]
        gap_any = np.where(has_any, gap_any, np.nan)
        f5["gap_from_last_prize_any"] = gap_any
    else:
        f5["last_prize_any"] = np.nan
        f5["gap_from_last_prize_any"] = np.nan

    return f5[["day", "prev_day", "prev_prize", "last_prize_any", "gap_from_last_prize_any"]
              + [f"last_{p}_day" for p in PRIZES_NON5000]
              + [f"gap_{p}" for p in PRIZES_NON5000]
              + [f"has_{p}_within_{w}d" for p in PRIZES_NON5000 for w in [7, 30, 90, 180]]]

print("📈 Computing 5000 precedence by specific prize (global, to slice per year)...")
f5_list = []
for num, g in tqdm(df.groupby("number")[["prize","day","appear"]], total=df["number"].nunique(), desc="Numbers"):
    part = analyze_by_prize(g)
    if not part.empty:
        part = part.copy()
        part.insert(0, "number", num)
        f5_list.append(part)

f5_global = pd.concat(f5_list, ignore_index=True) if f5_list else pd.DataFrame()
if f5_global.empty:
    raise SystemExit("No 5000 events found.")

f5_global["year"] = f5_global["day"].dt.year
print("✅ Built global 5000-by-prize precedence table.")

# =======================
# YEAR-BY-YEAR (2021+)
# =======================
years = sorted(y for y in f5_global["year"].unique() if y >= YEARS_START)
print("Years to process:", years)

for year in years:
    print(f"\n===== Year {year} =====")
    f5_y = f5_global[f5_global["year"] == year].copy()
    if f5_y.empty:
        print("No 5000 events.")
        continue

    # Save per-event table
    out_cols = ["number", "day", "prev_day", "prev_prize", "last_prize_any", "gap_from_last_prize_any"] \
               + [f"last_{p}_day" for p in PRIZES_NON5000] \
               + [f"gap_{p}" for p in PRIZES_NON5000] \
               + [f"has_{p}_within_{w}d" for p in PRIZES_NON5000 for w in [7, 30, 90, 180]]
    f5_y[out_cols].rename(columns={"day":"date"}).to_csv(f"5000_precedence_by_prize_{year}.csv", index=False, encoding="utf-8")
    print(f"✅ Saved 5000_precedence_by_prize_{year}.csv")

    n = len(f5_y)
    print(f"(1) 5000 appearances: {n}")

    # (a) Immediate previous prize distribution (focus on 100/200/500/1000/2000; ignore NaN/5000)
    prev = f5_y["prev_prize"].dropna().astype(int)
    prev = prev[prev.isin(PRIZES_NON5000)]
    prev_dist = prev.value_counts().reindex(PRIZES_NON5000, fill_value=0)
    print("  - Immediate previous prize distribution (% of all 5000 events):")
    for p in PRIZES_NON5000:
        pct = 100.0 * prev_dist.get(p, 0) / n
        print(f"    {p}: {pct:.2f}%")

    # (b) Last_prize_any distribution (which prize was most recent before 5000)
    last_any = f5_y["last_prize_any"].dropna().astype(int)
    last_any_dist = last_any.value_counts().reindex(PRIZES_NON5000, fill_value=0)
    print("  - Last prior prize before 5000 (most recent among 100/200/500/1000/2000):")
    for p in PRIZES_NON5000:
        pct = 100.0 * last_any_dist.get(p, 0) / n
        print(f"    {p}: {pct:.2f}%")

    # (c) Gap stats based on last_prize_any
    # Use gap_from_last_prize_any grouped by last_prize_any
    gap_rows = []
    for p in PRIZES_NON5000:
        sub = f5_y.loc[f5_y["last_prize_any"].eq(p), "gap_from_last_prize_any"].dropna()
        if sub.empty:
            gap_rows.append({"last_prize": p, "count": 0, "median": np.nan, "mean": np.nan,
                             "p25": np.nan, "p75": np.nan, "p90": np.nan, "p95": np.nan})
        else:
            gap_rows.append({
                "last_prize": p,
                "count": int(sub.size),
                "median": float(np.median(sub)),
                "mean": float(sub.mean()),
                "p25": float(np.percentile(sub, 25)),
                "p75": float(np.percentile(sub, 75)),
                "p90": float(np.percentile(sub, 90)),
                "p95": float(np.percentile(sub, 95)),
            })
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(f"gap_by_last_prize_{year}.csv", index=False, encoding="utf-8")
    print(f"✅ Saved gap_by_last_prize_{year}.csv")

    # (d) Window flags by prize (counts within 7/30/90/180 days)
    win_rows = []
    for p in PRIZES_NON5000:
        row = {"prize": p}
        for w in [7, 30, 90, 180]:
            cnt = int(f5_y[f"has_{p}_within_{w}d"].sum())
            row[f"within_{w}d_count"] = cnt
            row[f"within_{w}d_pct"] = 100.0 * cnt / n
        win_rows.append(row)
    win_df = pd.DataFrame(win_rows)
    win_df.to_csv(f"windows_by_prize_{year}.csv", index=False, encoding="utf-8")
    print(f"✅ Saved windows_by_prize_{year}.csv")

    # Pretty print a compact summary
    med = fmt_float(gap_df.set_index("last_prize")["median"].reindex(PRIZES_NON5000))
    print("  - Gap median by last_prize_any (days):")
    for p in PRIZES_NON5000:
        val = gap_df.loc[gap_df["last_prize"] == p, "median"]
        print(f"    {p}: {fmt_float(val.values[0] if len(val) else np.nan)}")