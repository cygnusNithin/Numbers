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

# Prize sets
LOWER_PRIZES = {100, 200, 500, 1000, 2000}
ALL_PRIZES   = {100, 200, 500, 1000, 2000, 5000}
TARGET_PRIZE = 5000

# Presence-level analysis (any count>0 on a date counts as 1 appearance)
PRESENCE_MODE = True

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

# keep only 4-digit numeric numbers and the prizes of interest
df["number"] = df["number"].astype(str).str.strip()
df = df[df["number"].str.match(r"^\d{1,4}$")].copy()
df["number"] = df["number"].str.zfill(4)

df["prize"] = pd.to_numeric(df["prize"], errors="coerce").astype("Int64")
df = df[df["prize"].isin(list(ALL_PRIZES))].copy()

df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)
df["day"] = df["dt"].dt.normalize()

# presence vs counts at (number, prize, day)
if PRESENCE_MODE:
    # any count>0 per (number,prize,day)
    df = (df.groupby(["number", "prize", "day"], as_index=False)["count"]
            .size().rename(columns={"size": "appear"}))
    df["appear"] = 1
else:
    # sum counts per (number,prize,day)
    df = (df.groupby(["number", "prize", "day"], as_index=False)["count"]
            .sum().rename(columns={"count": "appear"}))

# Ensure sorted for per-number sequences
df = df.sort_values(["number", "day", "prize"], ascending=[True, True, True]).reset_index(drop=True)
print(f"🔢 Unique numbers: {df['number'].nunique()}")

# =======================
# (1) 5000 PRECEDENCE ANALYSIS (with progress)
# =======================
def analyze_5000(group: pd.DataFrame) -> pd.DataFrame:
    # group: columns ['prize','day','appear'] for a single number
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

    # Add window flags (strictly before implied by last_lower_day <= current day)
    for win in [7, 30, 90, 180]:
        f5[f"has_lower_within_{win}d"] = f5["has_lower_before"] & (f5["gap_days_from_last_lower"] <= win)

    return f5[[
        "day",
        "prev_day", "prev_prize",
        "has_lower_before", "immediate_prev_is_lower",
        "last_lower_day", "last_lower_prize",
        "gap_days_from_last_lower", "gap_days_from_prev"
    ] + [c for c in f5.columns if c.startswith("has_lower_within_")]]

print("📈 Analyzing 5000 precedence per number...")
tqdm.pandas(desc="Per-number 5000 analysis")
# Avoid FutureWarning by selecting only needed cols before apply
f5_list = []
for num, g in tqdm(df.groupby("number")[["prize", "day", "appear"]], total=df["number"].nunique(), desc="Numbers"):
    part = analyze_5000(g)
    if not part.empty:
        part = part.copy()
        part.insert(0, "number", num)
        f5_list.append(part)
f5_all = pd.concat(f5_list, ignore_index=True) if f5_list else pd.DataFrame(columns=[
    "number","day","prev_day","prev_prize","has_lower_before","immediate_prev_is_lower",
    "last_lower_day","last_lower_prize","gap_days_from_last_lower","gap_days_from_prev",
    "has_lower_within_7d","has_lower_within_30d","has_lower_within_90d","has_lower_within_180d"
])

# Save CSV for (1)
f5_out = f5_all.rename(columns={"day": "date"})
f5_out.to_csv("5000_precedence_analysis.csv", index=False, encoding="utf-8")
print("✅ Saved 5000_precedence_analysis.csv")

# Headline stats
total_f5 = len(f5_all)
ever_preceded = int(f5_all["has_lower_before"].sum()) if total_f5 else 0
immediate_preceded = int(f5_all["immediate_prev_is_lower"].sum()) if total_f5 else 0

def pct(x, n): return 0.0 if n == 0 else round(100.0 * x / n, 2)

print(f"\n(1) 5000 appearances: {total_f5}")
print(f"  - Ever had a lower prize before: {ever_preceded} ({pct(ever_preceded, total_f5)}%)")
print(f"  - Immediate previous event is lower: {immediate_preceded} ({pct(immediate_preceded, total_f5)}%)")

if total_f5 > 0:
    gaps = f5_all["gap_days_from_last_lower"].dropna()
    if not gaps.empty:
        print(f"  - Gap from last lower (days): median={int(np.median(gaps))}, mean={gaps.mean():.1f}, p95={int(np.percentile(gaps,95))}")

    br = f5_all.dropna(subset=["last_lower_prize"])
    if not br.empty:
        breakdown = br["last_lower_prize"].astype(int).value_counts().sort_index()
        print("  - Last lower prize before 5000 (counts):")
        print(breakdown.to_string())

    # Windowed counts
    for win in [7, 30, 90, 180]:
        col = f"has_lower_within_{win}d"
        if col in f5_all.columns:
            cnt = int(f5_all[col].sum())
            print(f"  - Lower→5000 within {win}d: {cnt} ({pct(cnt, total_f5)}%)")

# =======================
# (2) FIRST→LAST PATH PER NUMBER (with progress)
# =======================
def compress_path(seq):
    out = []
    for p in seq:
        if not out or out[-1] != p:
            out.append(p)
    return out

print("🛤️  Building first→last paths per number...")
paths = []
n_nums = df["number"].nunique()
for num, g in tqdm(df.groupby("number", sort=False), total=n_nums, desc="Building paths"):
    gg = g.sort_values(["day", "prize"])
    first_row = gg.iloc[0]
    last_row = gg.iloc[-1]
    seq = gg["prize"].tolist()
    cseq = compress_path(seq)
    paths.append({
        "number": num,
        "first_date": first_row["day"].date(),
        "first_prize": int(first_row["prize"]),
        "last_date": last_row["day"].date(),
        "last_prize": int(last_row["prize"]),
        "unique_prizes_seen": "|".join(map(str, sorted(set(seq)))),
        "steps": len(seq),
        "compressed_steps": len(cseq),
        "prize_path": "->".join(map(str, cseq))
    })

paths_df = pd.DataFrame(paths).sort_values(["first_date", "number"])
paths_df.to_csv("number_paths.csv", index=False, encoding="utf-8")
print("✅ Saved number_paths.csv")

# =======================
# OPTIONAL: prize transition counts (with progress)
# =======================
print("🔁 Computing prize transition counts...")
prizes_sorted = sorted(ALL_PRIZES)
P = pd.DataFrame(0, index=prizes_sorted, columns=prizes_sorted, dtype=int)

for num, g in tqdm(df.groupby("number", sort=False), total=n_nums, desc="Transitions"):
    gg = g.sort_values(["day", "prize"])
    prev = None
    for p in gg["prize"]:
        if prev is not None:
            if prev in P.index and p in P.columns:
                P.loc[prev, p] += 1
        prev = p

P.to_csv("prize_transition_counts.csv", encoding="utf-8")
print("✅ Saved prize_transition_counts.csv")