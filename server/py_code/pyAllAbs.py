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
COLLECTION = "absolute_data"  # Updated to match Mongoose schema collection
OUTPUT_FILE = "absolute_data_number_patterns.csv"
SORT_DESC = True  # Total hits descending

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# HELPERS
# =======================
def get_all_numbers():
    """Fetch numbers, prize information, counts, and dates from absolute_data."""
    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "prize": "$series.prize",
            "count": {"$ifNull": ["$series.numbers.count", 1]},
            "drawDate": "$drawDate",
            "date": "$date"
        }}
    ]
    return lottery_data.aggregate(pipeline, allowDiskUse=True)

# =======================
# MAIN PROCESS
# =======================
print(f"🔄 Fetching records from '{COLLECTION}' collection...")
rows = list(get_all_numbers())
df = pd.DataFrame(rows)

print(f"📊 Total records fetched: {len(df)}")
if df.empty:
    print("⚠️ No data returned. Exiting.")
    raise SystemExit

# 1. Normalize core fields
df["number"] = df["number"].astype(str).str.zfill(4)
df["count"] = pd.to_numeric(df.get("count", 1), errors="coerce").fillna(1).astype(int)
df["prize"] = pd.to_numeric(df.get("prize"), errors="coerce").fillna(0).astype(int)

# 2. Parse dates: Prefer native `drawDate`, fall back to string `date` (DD/MM/YYYY)
df["date_parsed"] = pd.to_datetime(df["drawDate"], errors="coerce")
missing_dates = df["date_parsed"].isna()
if missing_dates.any():
    df.loc[missing_dates, "date_parsed"] = pd.to_datetime(
        df.loc[missing_dates, "date"], errors="coerce", format="%d/%m/%Y"
    )

bad_dates = int(df["date_parsed"].isna().sum())
if bad_dates:
    print(f"⚠️ {bad_dates} records have unparseable dates (kept for aggregate totals).")

# 3. Overall dataset metrics
latest_overall_date = df["date_parsed"].max()
counts_by_number = df.groupby("number")["count"].sum()
MAX_COUNT = int(counts_by_number.max()) if not counts_by_number.empty else 0
print(f"🎯 MAX_COUNT (weighted by 'count') = {MAX_COUNT}")
print(f"📅 Most recent draw date in DB: {latest_overall_date.strftime('%Y-%m-%d') if pd.notna(latest_overall_date) else 'N/A'}")

# Prepare ordered labels for calendar features
weekdays_order = list(calendar.day_name)
months_order = list(calendar.month_name)[1:]

# Filter valid dates for temporal features
df_valid = df.dropna(subset=["date_parsed"]).copy()
df_valid["date_parsed"] = pd.to_datetime(df_valid["date_parsed"])
df_valid = df_valid.sort_values(["number", "date_parsed"])

tqdm.pandas()

def summarize_group(g: pd.DataFrame) -> pd.Series:
    unique_days = g["date_parsed"].dt.normalize().drop_duplicates().sort_values()
    
    # Gap calculations
    gaps = unique_days.diff().dt.days.dropna()
    avg_gap = float(gaps.mean()) if not gaps.empty else np.nan
    min_gap = float(gaps.min()) if not gaps.empty else np.nan
    max_gap = float(gaps.max()) if not gaps.empty else np.nan

    # Recency (Days since last seen relative to overall dataset max date)
    last_seen_date = unique_days.max()
    days_since_last = (latest_overall_date - last_seen_date).days if pd.notna(latest_overall_date) and pd.notna(last_seen_date) else np.nan

    # Calendar distributions
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

    # Prize distribution breakdown
    prize_counts = g.groupby("prize")["count"].sum().to_dict()

    return pd.Series({
        "last_seen_date": last_seen_date.strftime("%d/%m/%Y") if pd.notna(last_seen_date) else "",
        "days_since_last_hit": days_since_last,
        "avg_gap_days": avg_gap,
        "min_gap_days": min_gap,
        "max_gap_days": max_gap,
        "dates": "|".join(unique_days.dt.strftime("%d/%m/%Y")),
        "prize_breakdown": json.dumps(prize_counts, sort_keys=True),
        "weekday_counts": json.dumps(weekday_counts, sort_keys=True, ensure_ascii=False),
        "month_counts": json.dumps(month_counts, sort_keys=True, ensure_ascii=False),
    })

# Run aggregation on temporal group
time_summary = (
    df_valid.groupby("number")[["date_parsed", "count", "prize"]]
            .progress_apply(summarize_group)
            .reset_index()
)

# Merge back with total counts
out_df = (
    counts_by_number.rename("total_hits").reset_index()
    .merge(time_summary, on="number", how="left")
)

# 4. Feature Engineering on Digits
out_df["d1"] = out_df["number"].str[0].astype(int)
out_df["d2"] = out_df["number"].str[1].astype(int)
out_df["d3"] = out_df["number"].str[2].astype(int)
out_df["d4"] = out_df["number"].str[3].astype(int)
out_df["digit_sum"] = out_df["d1"] + out_df["d2"] + out_df["d3"] + out_df["d4"]
out_df["even_digit_count"] = out_df[["d1", "d2", "d3", "d4"]].apply(lambda row: sum(1 for d in row if d % 2 == 0), axis=1)

# 5. Cleanup defaults and missing values
out_df["remaining_to_max"] = (MAX_COUNT - out_df["total_hits"]).clip(lower=0).astype(int)
out_df["dates"] = out_df["dates"].fillna("")
out_df["prize_breakdown"] = out_df["prize_breakdown"].fillna("{}")
out_df["weekday_counts"] = out_df["weekday_counts"].fillna("{}")
out_df["month_counts"] = out_df["month_counts"].fillna("{}")

# 6. Sorting
out_df = out_df.sort_values(
    by=["total_hits", "days_since_last_hit", "number"],
    ascending=[not SORT_DESC, True, True],
    na_position="last"
)

# 7. Export to CSV
out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
print(f"✅ Successfully processed and saved patterns to '{OUTPUT_FILE}'")