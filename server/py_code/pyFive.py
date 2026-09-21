import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm

# =========================
# CONFIGURATION
# =========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
LOW_PRIZES = [100, 200, 500, 1000, 2000]
HIGH_PRIZE = 5000
DETAIL_CSV = "low_to_5000_repeat_analysis.csv"
SUMMARY_CSV = "low_to_5000_summary.csv"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =========================
# HELPERS
# =========================
def parse_date(d):
    """Parse dates safely in Indian format (DD/MM/YYYY) and sort correctly."""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except Exception:
            continue
    return None


def get_prize_data(prize):
    """Fetch all numbers and dates for a specific prize."""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date"
        }}
    ]
    return list(lottery_data.aggregate(pipeline))


# =========================
# MAIN LOGIC
# =========================
print("🔄 Fetching data from MongoDB...")

# Load 5000 prize numbers
high_data = get_prize_data(HIGH_PRIZE)
high_df = pd.DataFrame(high_data)
high_df["date"] = high_df["date"].apply(parse_date)
high_df = high_df[high_df["date"].notnull()]

# ✅ Sort chronologically (Indian order → oldest to newest)
high_df.sort_values("date", inplace=True)

# Keep first appearance
high_first_seen = high_df.groupby("number")["date"].min().to_dict()

print(f"✅ Loaded {len(high_df)} records for ₹{HIGH_PRIZE} prize")

# Storage
detailed_rows = []
summary_rows = []

# Process lower prizes
for prize in LOW_PRIZES:
    print(f"\n🔍 Checking ₹{prize} prize numbers...")
    data = get_prize_data(prize)
    df = pd.DataFrame(data)
    df["date"] = df["date"].apply(parse_date)
    df = df[df["date"].notnull()]
    df.sort_values("date", inplace=True)

    low_first_seen = df.groupby("number")["date"].min().to_dict()

    matched_count = 0
    total_low = len(low_first_seen)
    gap_list = []
    earliest_5000 = None
    latest_5000 = None

    for num, low_date in tqdm(low_first_seen.items(), total=len(low_first_seen)):
        if num in high_first_seen:
            high_date = high_first_seen[num]
            if high_date > low_date:
                gap = (high_date - low_date).days
                matched_count += 1
                gap_list.append(gap)

                if not earliest_5000 or high_date < earliest_5000:
                    earliest_5000 = high_date
                if not latest_5000 or high_date > latest_5000:
                    latest_5000 = high_date

                detailed_rows.append({
                    "low_prize": prize,
                    "number": str(num).zfill(4),
                    "first_seen_low": low_date.strftime("%d/%m/%Y"),
                    "on_5000_date": high_date.strftime("%d/%m/%Y"),
                    "gap_days": gap
                })

    percent_matched = (matched_count / total_low * 100) if total_low else 0
    avg_gap = sum(gap_list)/len(gap_list) if gap_list else None

    summary_rows.append({
        "low_prize": prize,
        "total_numbers": total_low,
        "matched_in_5000": matched_count,
        "percent_matched": round(percent_matched, 2),
        "avg_gap_days": round(avg_gap, 2) if avg_gap else None,
        "earliest_5000_date": earliest_5000.strftime("%d/%m/%Y") if earliest_5000 else None,
        "latest_5000_date": latest_5000.strftime("%d/%m/%Y") if latest_5000 else None
    })

# =========================
# SAVE OUTPUT (sorted by date)
# =========================
detailed_df = pd.DataFrame(detailed_rows)
summary_df = pd.DataFrame(summary_rows)

if not detailed_df.empty:
    detailed_df["first_seen_low_dt"] = pd.to_datetime(detailed_df["first_seen_low"], format="%d/%m/%Y")
    detailed_df.sort_values(["low_prize", "first_seen_low_dt"], inplace=True)
    detailed_df.drop(columns=["first_seen_low_dt"], inplace=True)
    detailed_df.to_csv(DETAIL_CSV, index=False, encoding="utf-8")

if not summary_df.empty:
    summary_df.sort_values("low_prize", inplace=True)
    summary_df.to_csv(SUMMARY_CSV, index=False, encoding="utf-8")

# =========================
# REPORT
# =========================
print("\n✅ Analysis complete.")
print(f"📄 Detailed matches → {DETAIL_CSV}")
print(f"📊 Summary report → {SUMMARY_CSV}")

if not summary_df.empty:
    print("\nSummary preview:")
    print(summary_df.to_string(index=False))
