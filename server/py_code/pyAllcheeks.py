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
    """Fetch all numbers, counts, and dates across ALL prizes (no server-side date parsing)."""
    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "prize": "$series.prize",
            "count": {"$ifNull": ["$series.numbers.count", 1]},
            "date": "$date"  # string in schema; mixed formats possible
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
    print("⚠️ No data returned. Exiting.")
    raise SystemExit

# Normalize fields
df["number"] = df["number"].astype(str).str.zfill(4)
df["count"] = pd.to_numeric(df.get("count", 1), errors="coerce").fillna(1).astype(int)

# Parse date (supports dd.mm.yyyy, dd/mm/yyyy, yyyy-mm-dd, etc.)
df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

bad_dates = int(df["date_parsed"].isna().sum())
if bad_dates:
    print(f"⚠️ {bad_dates} records have unparseable dates (kept for totals, ignored for time-based stats).")

# Weighted totals per number (respect 'count')
counts_by_number = df.groupby("number")["count"].sum()
MAX_COUNT = int(counts_by_number.max()) if not counts_by_number.empty else 0
print(f"🎯 MAX_COUNT (weighted by 'count') = {MAX_COUNT}")

# Use only valid dates for temporal stats
df_valid = df.dropna(subset=["date_parsed"]).copy()
df_valid["date_parsed"] = pd.to_datetime(df_valid["date_parsed"])  # ensure dtype
df_valid = df_valid.sort_values(["number", "date_parsed"])

# Prepare ordered labels
weekdays_order = list(calendar.day_name)  # Monday..Sunday
months_order = list(calendar.month_name)[1:]  # Jan..Dec

tqdm.pandas()

def summarize_group(g: pd.DataFrame) -> pd.Series:
    # Unique dates (normalized to day) for gaps and date list
    unique_days = g["date_parsed"].dt.normalize().drop_duplicates().sort_values()
    gaps = unique_days.diff().dt.days.dropna()
    avg_gap = float(gaps.mean()) if not gaps.empty else np.nan

    # Weighted weekday/month counts (sum of 'count' per weekday/month)
    weekday_counts = (
        g.assign(weekday=g["date_parsed"].dt.day_name())
         .groupby("weekday")["count"].sum()
         .reindex(weekdays_order, fill_value=0)
         .to_dict()
    )
    month_counts = (
        g.assign(month=g["date_parsed"].dt.month_name())
         .groupby("month")["count"].sum()
         .reindex(months_order, fill_value=0)
         .to_dict()
    )

    return pd.Series({
        "dates": "|".join(unique_days.dt.strftime("%d/%m/%Y")) if not unique_days.empty else "",
        "avg_gap_days": avg_gap,
        "weekday_counts": json.dumps(weekday_counts, sort_keys=True, ensure_ascii=False),
        "month_counts": json.dumps(month_counts, sort_keys=True, ensure_ascii=False),
    })

# Build time-based summary for numbers that have at least one valid date
# (Select only needed columns to avoid FutureWarning)
time_summary = (
    df_valid.groupby("number")[["date_parsed", "count"]]
            .progress_apply(summarize_group)
            .reset_index()
)

# Merge with weighted totals to get the final table (ensure all numbers included)
out_df = (
    counts_by_number.rename("total_hits").reset_index()
    .merge(time_summary, on="number", how="left")
)

# Remaining to max, fill defaults
out_df["remaining_to_max"] = (MAX_COUNT - out_df["total_hits"]).clip(lower=0).astype(int)
out_df["avg_gap_days"] = out_df["avg_gap_days"].astype(float)
out_df["dates"] = out_df["dates"].fillna("")
out_df["weekday_counts"] = out_df["weekday_counts"].fillna("{}")
out_df["month_counts"] = out_df["month_counts"].fillna("{}")

# Sort: primary total_hits desc (if SORT_DESC), secondary avg_gap_days asc, tertiary number asc
out_df = out_df.sort_values(
    by=["total_hits", "avg_gap_days", "number"],
    ascending=[not SORT_DESC, True, True],
    na_position="last"  # put NaN avg_gap_days at the end
)

# Save
out_df.to_csv("all_prizes_number_patterns28.csv", index=False, encoding="utf-8")
print("✅ Saved detailed number patterns to all_prizes_number_patterns28.csv")