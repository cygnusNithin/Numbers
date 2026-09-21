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

print("Loading data from MongoDB...")
docs = list(collection.find({}))

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

all_dates.sort(key=lambda x: x[1])
sorted_dates = [d[0] for d in all_dates]

first_date = sorted_dates[0]
last_date = sorted_dates[-1]

print(f"First day: {first_date} with {len(daily_numbers[first_date])} numbers")
print(f"Last day:  {last_date}")
print(f"Total days: {len(sorted_dates)}")
print(f"Date range: {first_date} → {last_date}")

# ====================== BUILD MAP WITH CYCLE RESET ======================
appearances_map = defaultdict(list)      # Global history - never resets
first_seen = {}
last_seen = {}
daily_progress = []

global_seen = set()
cycle_seen = set()
cycle = 1

for date_str in sorted_dates:
    current_numbers = daily_numbers[date_str]
    
    # New vs repeating in CURRENT cycle only
    new_in_cycle = current_numbers - cycle_seen
    repeating_in_cycle = current_numbers & cycle_seen
    
    # Update global appearance history (never resets)
    for num in current_numbers:
        appearances_map[num].append(date_str)
        last_seen[num] = date_str
        if num not in first_seen:
            first_seen[num] = date_str
            global_seen.add(num)
    
    # Update current cycle
    cycle_seen.update(current_numbers)
    
    daily_progress.append({
        "date": date_str,
        "cycle": cycle,
        "total_numbers_today": len(current_numbers),
        "new_in_current_cycle": len(new_in_cycle),
        "repeating_in_current_cycle": len(repeating_in_cycle),
        "cumulative_in_cycle": len(cycle_seen),
        "global_unique_ever": len(global_seen)
    })
    
    # === RESET LOGIC AFTER 10000 NUMBERS ===
    if len(cycle_seen) >= 10000:
        print(f"✅ Cycle {cycle} completed on {date_str} (all 10000 numbers appeared)")
        cycle += 1
        cycle_seen = set()   # Reset for next cycle → next line starts at 0

print(f"\nTotal cycles completed: {cycle-1}")
print(f"Total unique numbers ever: {len(global_seen)} / 10000")

# ====================== SUMMARY TABLE ======================
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
        "avg_gap_days": round(sum(gaps)/len(gaps), 1) if gaps else None,
        "max_gap_days": max(gaps) if gaps else None,
        "all_appearance_dates": ", ".join(dates)
    })

# Add never-appeared numbers
for i in range(10000):
    num = str(i).zfill(4)
    if num not in appearances_map:
        summary_rows.append({
            "number": num,
            "first_appearance": None,
            "last_appearance": None,
            "total_appearances": 0,
            "avg_gap_days": None,
            "max_gap_days": None,
            "all_appearance_dates": ""
        })

summary_df = pd.DataFrame(summary_rows)
daily_df = pd.DataFrame(daily_progress)

# ====================== SAVE FILES ======================
output_dir = Path("lottery_analysis")
output_dir.mkdir(exist_ok=True)

summary_df.to_csv(output_dir / "number_appearance_map.csv", index=False)
daily_df.to_csv(output_dir / "daily_progress.csv", index=False)

with open(output_dir / "number_appearances_map.json", "w") as f:
    json.dump({k: v for k, v in sorted(appearances_map.items())}, f, indent=2)

print("\n✅ Files saved in 'lottery_analysis/' folder:")
print("   • number_appearances_map.json")
print("   • number_appearance_map.csv")
print("   • daily_progress.csv   ← Now has cycle reset logic")