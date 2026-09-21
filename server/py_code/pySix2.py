import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm

# ============================
# CONFIGURATION
# ============================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZES = [100, 500, 1000, 5000]
OUTPUT_FILE = "prize_number_history_sorted.csv"

# ============================
# DATABASE CONNECTION
# ============================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# ============================
# HELPERS
# ============================
def parse_date_indian(d):
    """Convert to datetime from Indian DD/MM/YYYY or related formats."""
    if pd.isna(d):
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d.strip(), fmt)
        except ValueError:
            continue
    return None


def get_prize_data(prize):
    """Fetch all numbers & dates for a given prize."""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date",
            "prize": "$series.prize"
        }}
    ]
    data = list(lottery_data.aggregate(pipeline))
    df = pd.DataFrame(data)
    df["parsed_date"] = df["date"].apply(parse_date_indian)
    df = df[df["parsed_date"].notnull()]
    df.sort_values("parsed_date", inplace=True)
    return df


def compute_avg_gap(dates):
    """Compute average gap (days) between consecutive dates."""
    if len(dates) < 2:
        return None
    gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
    return sum(gaps) / len(gaps)


# ============================
# FETCH & MERGE DATA
# ============================
print("🔄 Fetching prize data for ₹100, ₹500, ₹1000, and ₹5000...")
dfs = {p: get_prize_data(p) for p in PRIZES}
print("✅ Data loaded for all prize categories.")

# Combine all data
all_data = pd.concat(dfs.values(), ignore_index=True)

# ============================
# BUILD NUMBER HISTORY
# ============================
numbers = all_data["number"].unique()
records = []

print(f"🔍 Processing {len(numbers)} numbers...")
for num in tqdm(numbers, total=len(numbers)):
    num_str = str(num).zfill(4)
    num_entries = all_data[all_data["number"] == num]

    # Initialize stats
    first_seen = {}
    total_appearances = {}
    avg_gaps = {}
    weekday_counts = {}
    month_counts = {}
    timeline = []

    for prize in PRIZES:
        dfp = num_entries[num_entries["prize"] == prize].sort_values("parsed_date")
        if not dfp.empty:
            dates = list(dfp["parsed_date"])
            first_seen[prize] = dates[0]
            total_appearances[prize] = len(dates)
            avg_gaps[prize] = compute_avg_gap(dates)

            # Timeline fragments
            timeline += [f"{d.strftime('%d/%m/%Y')} (₹{prize})" for d in dates]

            # Weekday/month counts
            weekday_counts[prize] = pd.Series([d.strftime("%A") for d in dates]).value_counts().to_dict()
            month_counts[prize] = pd.Series([d.strftime("%B") for d in dates]).value_counts().to_dict()
        else:
            first_seen[prize] = None
            total_appearances[prize] = 0
            avg_gaps[prize] = None
            weekday_counts[prize] = {}
            month_counts[prize] = {}

    # Build final record
    records.append({
        "number": num_str,
        "first_seen_in_100": first_seen[100].strftime("%d/%m/%Y") if first_seen[100] else "",
        "first_seen_in_500": first_seen[500].strftime("%d/%m/%Y") if first_seen[500] else "",
        "first_seen_in_1000": first_seen[1000].strftime("%d/%m/%Y") if first_seen[1000] else "",
        "first_seen_in_5000": first_seen[5000].strftime("%d/%m/%Y") if first_seen[5000] else "",
        "total_appearances": len(num_entries),
        "remaining_to_max": 0,  # Placeholder (can compute if needed)
        "appearances_timeline": " → ".join(sorted(timeline, key=lambda x: parse_date_indian(x.split()[0]))),
        "total_appearances_in_100": total_appearances[100],
        "total_appearances_in_500": total_appearances[500],
        "total_appearances_in_1000": total_appearances[1000],
        "total_appearances_in_5000": total_appearances[5000],
        "avg_gap_days_in_100": avg_gaps[100],
        "avg_gap_days_in_500": avg_gaps[500],
        "avg_gap_days_in_1000": avg_gaps[1000],
        "avg_gap_days_in_5000": avg_gaps[5000],
        "weekday_counts": weekday_counts,
        "month_counts": month_counts,
    })

# ============================
# SORT & SAVE
# ============================
out_df = pd.DataFrame(records)

# Parse for sorting
out_df["parsed_first_seen_5000"] = out_df["first_seen_in_5000"].apply(parse_date_indian)
out_df = out_df.sort_values("parsed_first_seen_5000", ascending=True)
out_df.drop(columns=["parsed_first_seen_5000"], inplace=True)

# Save to CSV
out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

print(f"\n✅ Saved comprehensive prize history → {OUTPUT_FILE}")
print(f"📊 Total numbers processed: {len(out_df)}")
print(out_df.head(10))
