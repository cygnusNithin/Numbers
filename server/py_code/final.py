import calendar
from datetime import datetime
from pymongo import MongoClient
import csv

# =========================
# DB CONFIG
# =========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

YEAR = 2025
MONTH = 12
PRIZE_TO_USE = 5000   # change if needed

OUTPUT_CSV = "december_2025_calendar.csv"

# =========================
# CONNECT
# =========================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db[COLLECTION]

day_map = {}
matched_docs = 0

# =========================
# READ DATA
# =========================
for doc in col.find({}):
    date_str = doc.get("date")
    if not date_str:
        continue

    try:
        # ✅ FIXED FORMAT
        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
    except Exception:
        continue

    if date_obj.year != YEAR or date_obj.month != MONTH:
        continue

    for s in doc.get("series", []):
        if s.get("prize") != PRIZE_TO_USE:
            continue

        matched_docs += 1
        day = date_obj.day

        for n in s.get("numbers", []):
            num = str(n.get("number")).zfill(4)
            day_map.setdefault(day, []).append(num)

print("✅ Matched documents:", matched_docs)

# =========================
# BUILD CALENDAR
# =========================
cal = calendar.Calendar(calendar.MONDAY)
weeks = cal.monthdayscalendar(YEAR, MONTH)

rows = []
for week in weeks:
    row = []
    for d in week:
        if d == 0:
            row.append("")
        else:
            if d in day_map:
                row.append(f"{d} ({','.join(day_map[d])})")
            else:
                row.append(str(d))
    rows.append(row)

# =========================
# SAVE CSV
# =========================
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
    writer.writerows(rows)

print("📅 Calendar saved:", OUTPUT_CSV)
