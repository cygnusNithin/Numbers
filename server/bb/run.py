

## Full Python Script


from pymongo import MongoClient
from datetime import datetime
import pandas as pd

# === CONFIG ===
DB_NAME = "numbergrid"
COLLECTION_NAME = "lotterydatas"
DATE_FORMAT = "%d/%m/%Y"

# === CONNECT ===
client = MongoClient("mongodb://localhost:27017/")
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# === BUILD: date -> set of numbers ===
docs = list(collection.find().sort("date", 1))

date_to_numbers = {}
all_dates = []

for doc in docs:
    date_str = doc.get("date", "")
    try:
        dt = datetime.strptime(date_str, DATE_FORMAT)
    except:
        continue

    if date_str not in date_to_numbers:
        date_to_numbers[date_str] = set()
        all_dates.append(date_str)

    for series in doc.get("series", []):
        for item in series.get("numbers", []):
            num = str(item.get("number", "")).zfill(4)
            date_to_numbers[date_str].add(num)

print(f"Total dates: {len(all_dates)}")
print(f"First date: {all_dates[0]}")
print(f"Last date: {all_dates[-1]}")

# === BUILD: number -> list of days appeared ===
number_to_days = {}

for num in [str(i).zfill(4) for i in range(10000)]:
    number_to_days[num] = []

for idx, date_str in enumerate(all_dates, start=1):
    for num in date_to_numbers[date_str]:
        number_to_days[num].append({
            "day_index": idx,
            "date": date_str
        })

# === CALCULATE STATS ===
timeline_rows = []
appearance_rows = []

latest_day = len(all_dates)

for num in [str(i).zfill(4) for i in range(10000)]:
    entries = number_to_days[num]

    if not entries:
        timeline_rows.append({
            "number": num,
            "first_day": None,
            "last_day": None,
            "total": 0,
            "days_list": "",
            "gaps_list": "",
            "short_gap": None,
            "long_gap": None,
            "status": "Never"
        })
        continue

    days = [e["day_index"] for e in entries]
    dates = [e["date"] for e in entries]

    first = days[0]
    last = days[-1]
    total = len(days)

    # gaps
    gaps = []
    for i in range(1, len(days)):
        gaps.append(days[i] - days[i - 1])

    short_gap = min(gaps) if gaps else 0
    long_gap = max(gaps) if gaps else 0

    # status
    days_since_last = latest_day - last
    if total == 1:
        status = "Once"
    elif days_since_last <= 7:
        status = "Hot"
    elif days_since_last <= 30:
        status = "Warm"
    elif days_since_last <= 90:
        status = "Cold"
    else:
        status = "Inactive"

    timeline_rows.append({
        "number": num,
        "first_day": first,
        "last_day": last,
        "total": total,
        "days_list": ",".join(map(str, days)),
        "dates_list": ",".join(dates),
        "gaps_list": ",".join(map(str, gaps)) if gaps else "",
        "short_gap": short_gap,
        "long_gap": long_gap,
        "status": status
    })

    # appearance rows
    for i, entry in enumerate(entries):
        gap = gaps[i - 1] if i > 0 else 0
        appearance_rows.append({
            "number": num,
            "day_index": entry["day_index"],
            "date": entry["date"],
            "is_first": i == 0,
            "is_last": i == len(entries) - 1,
            "gap_since_last": gap
        })

# === SAVE ===
timeline_df = pd.DataFrame(timeline_rows)
appearance_df = pd.DataFrame(appearance_rows)

timeline_df.to_csv("number_timeline.csv", index=False)
appearance_df.to_csv("number_appearances.csv", index=False)

print(f"Saved: number_timeline.csv ({len(timeline_df)} rows)")
print(f"Saved: number_appearances.csv ({len(appearance_df)} rows)")

# === SAMPLE OUTPUT ===
print("\n=== SAMPLE (first 10 numbers) ===")
print(timeline_df.head(10).to_string(index=False))


import matplotlib.pyplot as plt
import numpy as np

top_numbers = timeline_df[timeline_df["total"] > 0].nlargest(100, "total")["number"].tolist()

matrix = np.zeros((len(top_numbers), len(all_dates)), dtype=int)

for ni, num in enumerate(top_numbers):
    days = timeline_df[timeline_df["number"] == num]["days_list"].values[0]
    if days:
        for d in map(int, days.split(",")):
            matrix[ni, d - 1] = 1

plt.figure(figsize=(20, 10))
plt.imshow(matrix, cmap="Blues", aspect="auto")
plt.xlabel("Day Index")
plt.ylabel("Number (top 100)")
plt.title("Number Presence Map")
plt.colorbar(label="Appeared")
plt.tight_layout()
plt.savefig("presence_map.png", dpi=150)
plt.show()