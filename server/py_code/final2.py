from pymongo import MongoClient
from collections import Counter, defaultdict
from datetime import datetime
import calendar
import csv

# ================= CONFIG =================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

YEAR = 2025
TARGET_PRIZE = 5000
TOP_N = 100

OUTPUT_CSV = "calendar_2025_top100.csv"

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db[COLLECTION]

docs = list(col.find())

# ================= PASS 1: GLOBAL TOP 100 =================
global_counter = Counter()

for doc in docs:
    for series in doc.get("series", []):
        if series.get("prize") == TARGET_PRIZE:
            for n in series.get("numbers", []):
                global_counter[n["number"]] += n.get("count", 1)

top_100 = set(num for num, _ in global_counter.most_common(TOP_N))

print("✅ Global Top-100 ready")

# ================= PASS 2: DATE → DAY MAP =================
year_map = defaultdict(lambda: defaultdict(list))
# year_map[month][day] = [numbers]

for doc in docs:
    date_str = doc.get("date")

    parsed = None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            break
        except:
            pass

    if not parsed or parsed.year != YEAR:
        continue

    month = parsed.month
    day = parsed.day

    for series in doc.get("series", []):
        if series.get("prize") == TARGET_PRIZE:
            for n in series.get("numbers", []):
                num = n["number"]
                if num in top_100:
                    year_map[month][day].append(num)

# ================= CALENDAR WRITE =================
cal = calendar.Calendar(calendar.MONDAY)

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.writer(f)

    for month in range(1, 13):
        writer.writerow([calendar.month_name[month].upper(), YEAR])
        writer.writerow(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])

        weeks = cal.monthdayscalendar(YEAR, month)

        for week in weeks:
            row = []
            for day in week:
                if day == 0:
                    row.append("")
                else:
                    nums = sorted(set(year_map[month].get(day, [])))
                    if nums:
                        row.append(f"{day} ({', '.join(nums)})")
                    else:
                        row.append(str(day))
            writer.writerow(row)

        writer.writerow([])  # blank line between months

print("📅 Full 2025 calendar saved:", OUTPUT_CSV)
