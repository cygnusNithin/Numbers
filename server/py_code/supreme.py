import os
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"

OUTPUT_ROOT = "output_csvs"  # ✅ folder for all results

SOURCES = {
    "db3": "lottery_results_v2",  # FullLotteryData
    "db4": "absolute_data",      # AbsoluteData
}

SORT_DESC = True  # ✅ Change to False for ascending order

# =======================
# HELPERS
# =======================
def parse_date(d):
    """Try parsing with multiple formats and normalize to DD/MM/YYYY"""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except (ValueError, TypeError):
            continue
    return None

def get_all_prizes(collection):
    """Get all distinct prize values from series.prize"""
    pipeline = [
        {"$unwind": "$series"},
        {"$group": {"_id": "$series.prize"}}
    ]
    prizes = [doc["_id"] for doc in collection.aggregate(pipeline)]
    prizes = [p for p in prizes if p is not None]
    return sorted(prizes, key=lambda x: float(x))

def get_all_prize_numbers(collection, prize):
    """Fetch all numbers & dates for a specific prize"""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date"
        }}
    ]
    return list(collection.aggregate(pipeline))

# =======================
# MAIN
# =======================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

os.makedirs(OUTPUT_ROOT, exist_ok=True)

for db_key, collection_name in SOURCES.items():
    print(f"\n========== {db_key} → {collection_name} ==========")
    collection = db[collection_name]

    prizes = get_all_prizes(collection)
    if not prizes:
        print(f"⚠️ No prizes found in {db_key} ({collection_name}). Skipping.")
        continue

    print(f"✅ Found {len(prizes)} prizes in {db_key}: {prizes}")

    out_dir = os.path.join(OUTPUT_ROOT, db_key)
    os.makedirs(out_dir, exist_ok=True)

    for prize in prizes:
        # Make prize consistent as int for filenames/columns
        prize_int = int(float(prize))

        try:
            print(f"\n🔄 Fetching all prize numbers for prize={prize_int} from {db_key}...")
            data = get_all_prize_numbers(collection, prize)

            df = pd.DataFrame(data)
            print(f"📊 Total records fetched: {len(df)}")

            if df.empty or "number" not in df.columns or "date" not in df.columns:
                print(f"⚠️ No usable data for prize={prize_int} in {db_key}. Skipping.")
                continue

            # 🎯 Find dynamic MAX_COUNT from database (same logic as your code)
            counts = df["number"].value_counts()
            MAX_COUNT = counts.max() if len(counts) else 0
            print(f"🎯 MAX_COUNT (highest repeat for prize {prize_int}) = {MAX_COUNT}")

            patterns = []
            unique_numbers = df["number"].unique()
            print(f"🔄 Analyzing {len(unique_numbers)} unique numbers for prize={prize_int}...")

            for num in tqdm(unique_numbers, total=len(unique_numbers), desc=f"Processing {db_key} prize={prize_int}"):
                num_df = df[df["number"] == num]

                # Parse dates once
                parsed = []
                for d in num_df["date"]:
                    dt = parse_date(d)
                    if dt:
                        parsed.append(dt)

                if not parsed:
                    continue

                parsed.sort()
                gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]

                weekdays = [d.strftime("%A") for d in parsed]
                weekday_counts = pd.Series(weekdays).value_counts().to_dict()

                months = [d.strftime("%B") for d in parsed]
                month_counts = pd.Series(months).value_counts().to_dict()

                total_hits = len(parsed)

                patterns.append({
                    "number": str(num).zfill(4),
                    "prize": prize_int,
                    "total_hits": total_hits,
                    "remaining_to_max": max(0, MAX_COUNT - total_hits),
                    "dates": "|".join(d.strftime("%d/%m/%Y") for d in parsed),
                    "avg_gap_days": sum(gaps) / len(gaps) if gaps else None,
                    "weekday_counts": weekday_counts,
                    "month_counts": month_counts
                })

            out_df = pd.DataFrame(patterns)
            if out_df.empty:
                print(f"⚠️ No valid patterns produced for prize={prize_int} in {db_key}. Skipping CSV.")
                continue

            # 🧮 Sort: first by total_hits (desc/asc), then by number (asc)
            out_df = out_df.sort_values(
                by=["total_hits", "number"],
                ascending=[not SORT_DESC, True]
            ).reset_index(drop=True)

            # 🆕 Add serial number column ONCE (fix)
            out_df.insert(0, "serial_number", range(1, len(out_df) + 1))

            # 💾 Save to CSV
            out_file = os.path.join(out_dir, f"{db_key}_prize_{prize_int}_number_patterns.csv")
            out_df.to_csv(out_file, index=False, encoding="utf-8")
            print(f"✅ Saved: {out_file}")

        except Exception as e:
            print(f"❌ Error processing prize={prize_int} in db4={db_key}: {e}")

print("\n🎉 DONE! All CSV files exported.")