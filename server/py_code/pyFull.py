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

# Collections for different schemas
COLLECTIONS = {
    "db3": "lottery_results_v2",      # FullLotteryData
    "db4": "absolute_data",            # AbsoluteData
}

SORT_DESC = True  # total_hits descending if True

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# =======================
# HELPERS
# =======================
def get_all_numbers(collection_name):
    """
    Fetch all numbers, prize categories, counts, and dates
    across ALL prize series from specified collection.
    """
    collection = db[collection_name]
    
    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "prize": "$series.prize",   # prize category
            "count": {"$ifNull": ["$series.numbers.count", 1]},
            "date": "$date"
        }}
    ]
    return collection.aggregate(pipeline, allowDiskUse=True)

# =======================
# CORE LOGIC
# =======================
def summarize_group(g: pd.DataFrame) -> pd.Series:
    """Summarize statistics for a single number"""
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
         .reindex(list(calendar.day_name), fill_value=0)
         .to_dict()
    )

    # ---- MONTH COUNTS ----
    month_counts = (
        g.assign(month=g["date_parsed"].dt.month_name())
         .groupby("month")["count"].sum()
         .reindex(list(calendar.month_name)[1:], fill_value=0)
         .to_dict()
    )

    return pd.Series({
        "dates": "|".join(date_strings),
        "avg_gap_days": avg_gap,
        "weekday_counts": json.dumps(weekday_counts, sort_keys=True),
        "month_counts": json.dumps(month_counts, sort_keys=True),
    })

# =======================
# PROCESS EACH COLLECTION
# =======================
tqdm.pandas()

for db_key, collection_name in COLLECTIONS.items():
    print(f"\n{'='*60}")
    print(f"🔄 Processing: {db_key} ({collection_name})")
    print(f"{'='*60}")
    
    try:
        # Fetch data
        print(f"🔄 Fetching ALL prize numbers from {collection_name}...")
        rows = list(get_all_numbers(collection_name))
        
        if not rows:
            print(f"⚠️  No data found in {collection_name}. Skipping...")
            continue
        
        df = pd.DataFrame(rows)
        print(f"📊 Total records fetched: {len(df)}")

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
            print(f"⚠️  {bad_dates} rows have invalid dates (ignored for time stats)")

        # -----------------------
        # TOTAL HITS (WEIGHTED)
        # -----------------------
        counts_by_number = df.groupby("number")["count"].sum()
        MAX_COUNT = int(counts_by_number.max())
        print(f"🎯 MAX_COUNT = {MAX_COUNT}")
        print(f"📈 Unique numbers: {len(counts_by_number)}")

        # -----------------------
        # VALID DATES ONLY
        # -----------------------
        df_valid = df.dropna(subset=["date_parsed"]).copy()
        df_valid = df_valid.sort_values(["number", "date_parsed"])

        # =======================
        # BUILD SUMMARY
        # =======================
        print(f"⏳ Building statistics for {len(counts_by_number)} numbers...")
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
        filename = f"number_patterns_{db_key}.csv"
        out_df.to_csv(filename, index=False, encoding="utf-8")
        
        print(f"✅ Saved: {filename}")
        print(f"   📋 Rows: {len(out_df)}")
        print(f"   📊 Columns: {list(out_df.columns)}")
        
    except Exception as e:
        print(f"❌ Error processing {db_key}: {str(e)}")
        continue

print(f"\n{'='*60}")
print(f"✅ All processing complete!")
print(f"{'='*60}")