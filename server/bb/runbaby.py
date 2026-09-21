from pymongo import MongoClient
from collections import defaultdict
from datetime import datetime
import pandas as pd
import json
from pathlib import Path

# ====================== CONFIG ======================
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "numbergrid"      # ← CHANGE THIS
COLLECTION_NAME = "lotterydatas"          # ← CHANGE IF DIFFERENT
# ===================================================

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# Load all documents and sort by date
print("Loading data from MongoDB...")
docs = list(collection.find({}))

# Parse dates and build daily number sets
daily_numbers = {}
all_dates = []

for doc in docs:
    date_str = doc.get("date")
    if not date_str:
        continue
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        continue

    date_key = date_str
    numbers_today = set()

    for series in doc.get("series", []):
        for item in series.get("numbers", []):
            num = str(item.get("number", "")).zfill(4)
            if num.isdigit() and len(num) == 4:
                numbers_today.add(num)

    if numbers_today:
        daily_numbers[date_key] = numbers_today
        all_dates.append((date_key, dt))

# Sort dates chronologically
all_dates.sort(key=lambda x: x[1])
sorted_dates = [d[0] for d in all_dates]

print(f"Total days found: {len(sorted_dates)}")
print(f"First day: {sorted_dates[0]} with {len(daily_numbers[sorted_dates[0]])} numbers")

# ====================== BUILD THE MAP ======================
appearances_map = defaultdict(list)      # number → list of dates (in order)
first_seen = {}
last_seen = {}
daily_progress = []

seen_so_far = set()                      # all numbers seen until now

for date_str in sorted_dates:
    current_numbers = daily_numbers[date_str]
    
    new_today = current_numbers - seen_so_far
    repeat_today = current_numbers & seen_so_far
    
    # Record appearances
    for num in current_numbers:
        appearances_map[num].append(date_str)
        last_seen[num] = date_str
        if num not in first_seen:
            first_seen[num] = date_str
    
    seen_so_far.update(current_numbers)
    
    daily_progress.append({
        "date": date_str,
        "total_numbers": len(current_numbers),
        "new_numbers": len(new_today),
        "repeating_numbers": len(repeat_today),
        "cumulative_unique": len(seen_so_far)
    })

print(f"Total unique numbers appeared: {len(seen_so_far)} out of 10000")

# ====================== CREATE SUMMARY ======================
summary_rows = []

for num in sorted(appearances_map.keys()):
    dates = appearances_map[num]
    gaps = []
    for i in range(1, len(dates)):
        d1 = datetime.strptime(dates[i-1], "%d/%m/%Y")
        d2 = datetime.strptime(dates[i], "%d/%m/%Y")
        gaps.append((d2 - d1).days)
    
    summary_rows.append({
        "number": num,
        "first_appearance": dates[0],
        "last_appearance": dates[-1],
        "total_appearances": len(dates),
        "first_day_new": 1 if len(dates) > 0 else 0,
        "avg_gap_days": round(sum(gaps)/len(gaps), 1) if gaps else None,
        "max_gap_days": max(gaps) if gaps else None,
        "all_appearance_dates": ", ".join(dates)
    })

# Fill missing numbers (never appeared)
for i in range(10000):
    num = str(i).zfill(4)
    if num not in appearances_map:
        summary_rows.append({
            "number": num,
            "first_appearance": None,
            "last_appearance": None,
            "total_appearances": 0,
            "first_day_new": 0,
            "avg_gap_days": None,
            "max_gap_days": None,
            "all_appearance_dates": ""
        })

summary_df = pd.DataFrame(summary_rows)
daily_df = pd.DataFrame(daily_progress)

# ====================== SAVE OUTPUTS ======================
output_dir = Path("lottery_analysis")
output_dir.mkdir(exist_ok=True)

summary_df.to_csv(output_dir / "number_appearance_map.csv", index=False)
daily_df.to_csv(output_dir / "daily_progress.csv", index=False)

# Save the main map as JSON (very useful)
with open(output_dir / "number_appearances_map.json", "w") as f:
    json.dump({k: v for k, v in sorted(appearances_map.items())}, f, indent=2)

print("\n✅ Analysis completed! Files saved in 'lottery_analysis/' folder:")
print("   • number_appearances_map.json     ← Main map you asked for")
print("   • number_appearance_map.csv       ← Full details per number")
print("   • daily_progress.csv              ← New vs repeat per day")

# Show sample of first day
first_date = sorted_dates[0]
print(f"\nFirst day ({first_date}): {len(daily_numbers[first_date])} numbers were added.")