import json
import calendar
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
SORT_DESC = True  # total_hits descending if True

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# HELPERS
# =======================
def get_all_numbers():
    """
    Fetch all numbers, prize categories, counts, and dates
    across ALL prize series.
    """
    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "prize": "$series.prize",   # ← prize category
            "count": {"$ifNull": ["$series.numbers.count", 1]},
            "date": "$date"
        }}
    ]
    return lottery_data.aggregate(pipeline, allowDiskUse=True)

# =======================
# MAIN
# =======================
print("🔄 Fetching ALL prize numbers from DB...")
rows = list(get_all_numbers())
df = pd.DataFrame(rows)

print(f"📊 Total records fetched: {len(df)}")
if df.empty:
    raise SystemExit("⚠️ No data returned from DB")

# -----------------------
# NORMALIZATION
# -----------------------
df["number"] = df["number"].astype(str).str.zfill(4)
df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)
df["prize"] = pd.to_numeric(df["prize"], errors="coerce")

# Parse date (DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD supported)
df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

bad_dates = int(df["date_parsed"].isna().sum())
if bad_dates:
    print(f"⚠️ {bad_dates} rows have invalid dates (ignored for time stats)")

# -----------------------
# TOTAL HITS (WEIGHTED)
# -----------------------
counts_by_number = df.groupby("number")["count"].sum()
MAX_COUNT = int(counts_by_number.max())
print(f"🎯 MAX_COUNT = {MAX_COUNT}")

# -----------------------
# VALID DATES ONLY
# -----------------------
df_valid = df.dropna(subset=["date_parsed"]).copy()
df_valid = df_valid.sort_values(["number", "date_parsed"])

# -----------------------
# LABEL ORDERS
# -----------------------
weekdays_order = list(calendar.day_name)
months_order = list(calendar.month_name)[1:]

tqdm.pandas()

# =======================
# CORE LOGIC
# =======================
def summarize_group(g: pd.DataFrame) -> pd.Series:
    g = g.copy()
    g["day"] = g["date_parsed"].dt.normalize()

    # ---- DATE + PRIZE CATEGORY ----
    date_category = (
        g.groupby("day")["prize"]
        .apply(lambda x: ",".join(
            sorted(set(str(int(v)) for v in x if pd.notna(v)))
        ))
        .reset_index()
        .sort_values("day")
    )

    # Build: dd/mm/yyyy(prize)
    date_strings = date_category.apply(
        lambda r: f"{r['day'].strftime('%d/%m/%Y')}({r['prize']})",
        axis=1
    )

    # ---- GAP CALCULATION ----
    gaps = date_category["day"].diff().dt.days.dropna()
    avg_gap = float(gaps.mean()) if not gaps.empty else np.nan

    # ---- WEEKDAY COUNTS ----
    weekday_counts = (
        g.assign(weekday=g["date_parsed"].dt.day_name())
         .groupby("weekday")["count"].sum()
         .reindex(weekdays_order, fill_value=0)
         .to_dict()
    )

    # ---- MONTH COUNTS ----
    month_counts = (
        g.assign(month=g["date_parsed"].dt.month_name())
         .groupby("month")["count"].sum()
         .reindex(months_order, fill_value=0)
         .to_dict()
    )

    return pd.Series({
        "dates": "|".join(date_strings),
        "avg_gap_days": avg_gap,
        "weekday_counts": json.dumps(weekday_counts, sort_keys=True),
        "month_counts": json.dumps(month_counts, sort_keys=True),
    })

# =======================
# BUILD SUMMARY
# =======================
time_summary = (
    df_valid.groupby("number")[["date_parsed", "count", "prize"]]
    .progress_apply(summarize_group)
    .reset_index()
)

# =======================
# MERGE + FINAL OUTPUT
# =======================
out_df = (
    counts_by_number.rename("total_hits").reset_index()
    .merge(time_summary, on="number", how="left")
)

out_df["remaining_to_max"] = (MAX_COUNT - out_df["total_hits"]).clip(lower=0).astype(int)
out_df["dates"] = out_df["dates"].fillna("")
out_df["weekday_counts"] = out_df["weekday_counts"].fillna("{}")
out_df["month_counts"] = out_df["month_counts"].fillna("{}")

out_df = out_df.sort_values(
    by=["total_hits", "avg_gap_days", "number"],
    ascending=[not SORT_DESC, True, True],
    na_position="last"
)

# =======================
# SAVE
# =======================
out_df.to_csv(
    "all_prizes_number_patterns33.csv",
    index=False,
    encoding="utf-8"
)

print("✅ Saved: all_prizes_number_patterns33.csv")
