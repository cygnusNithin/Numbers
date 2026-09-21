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
MONTH = 10
TARGET_PRIZE = 5000
TOP_N = 100

OUTPUT_CSV = "october_2025_calendar.csv"

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
print("🔎 Example check → 2214:", "YES" if "2214" in top_100 else "NO")

# ================= PASS 2: DECEMBER DATA =================
day_map = defaultdict(list)

for doc in docs:
    date_str = doc.get("date")

    # Handle both DD.MM.YYYY and DD/MM/YYYY
    parsed = None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            break
        except:
            pass

    if not parsed:
        continue

    if parsed.year != YEAR or parsed.month != MONTH:
        continue

    day = parsed.day

    for series in doc.get("series", []):
        if series.get("prize") == TARGET_PRIZE:
            for n in series.get("numbers", []):
                num = n["number"]
                if num in top_100:
                    day_map[day].append(num)

# ================= CALENDAR BUILD =================
cal = calendar.Calendar(calendar.MONDAY)
weeks = cal.monthdayscalendar(YEAR, MONTH)

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])

    for week in weeks:
        row = []
        for day in week:
            if day == 0:
                row.append("")
            else:
                nums = sorted(set(day_map.get(day, [])))
                if nums:
                    row.append(f"{day} ({', '.join(nums)})")
                else:
                    row.append(str(day))
        writer.writerow(row)

print("📅 Calendar generated:", OUTPUT_CSV)
