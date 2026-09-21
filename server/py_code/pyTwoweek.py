import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta
from tqdm import tqdm

# ======================
# CONFIG
# ======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000
MAX_TARGET = 12             # 🎯 Max times any number has appeared
GROUP_BY = "W"              # "D" = daily, "W" = weekly, "M" = monthly
SORT_DESC = True             # Sort descending by hits

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# ======================
# HELPERS
# ======================
def parse_date(d):
    """Try parsing multiple date formats."""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_all_prize_numbers(prize):
    """Fetch all numbers & dates for a specific prize"""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {"number": "$series.numbers.number", "date": "$date"}}
    ]
    return list(lottery_data.aggregate(pipeline))

# ======================
# MAIN
# ======================
print(f"🔄 Fetching all {PRIZE_FILTER} prize numbers from DB...")
data = get_all_prize_numbers(PRIZE_FILTER)
df = pd.DataFrame(data)
print(f"📊 Total records fetched: {len(df)}")

# Parse valid dates
df["parsed_date"] = df["date"].apply(parse_date)
df = df[df["parsed_date"].notnull()]
df = df.sort_values("parsed_date", ascending=True)

start_date = df["parsed_date"].min()
end_date = df["parsed_date"].max()

print(f"📅 Range: {start_date.strftime('%d-%m-%Y')} → {end_date.strftime('%d-%m-%Y')}")

# ======================
# TIMELINE ANALYSIS
# ======================
timeline = []
progress_dates = pd.date_range(start=start_date, end=end_date, freq=GROUP_BY)

print(f"📈 Analyzing repeat progression ({GROUP_BY}-wise)...")
for date in tqdm(progress_dates, total=len(progress_dates)):
    # Filter data up to this date
    current = df[df["parsed_date"] <= date]
    if current.empty:
        continue

    # Count number appearances
    counts = current["number"].value_counts()
    top_numbers = counts.head(10).index.tolist()

    # Find how close each number is to max
    progress = (counts / MAX_TARGET).clip(upper=1.0)

    # Collect summary stats
    avg_progress = progress.mean()
    top_progress = progress.loc[top_numbers].mean()

    timeline.append({
        "date": date.strftime("%Y-%m-%d"),
        "unique_numbers_seen": len(counts),
        "avg_progress": round(avg_progress * 100, 2),
        "top_avg_progress": round(top_progress * 100, 2),
        "top_numbers": ",".join(str(n).zfill(4) for n in top_numbers)
    })

timeline_df = pd.DataFrame(timeline)

# ======================
# SAVE OUTPUT
# ======================
out_file = "5000_number_progress_timeline.csv"
timeline_df.to_csv(out_file, index=False, encoding="utf-8")

print(f"✅ Saved timeline → {out_file}")
print("📊 Example preview:")
print(timeline_df.tail(10))
