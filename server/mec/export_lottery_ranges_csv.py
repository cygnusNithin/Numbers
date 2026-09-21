import pymongo
import pandas as pd
import os

# === Config ===
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000
RANGE_SIZE = 50
OUTPUT_FILE = "5000_prize_distribution.csv"  # pipe separated but saved as .csv

# === Connect to MongoDB ===
client = pymongo.MongoClient(MONGO_URI)
col = client[DB_NAME][COLLECTION]

# === Build Ranges ===
ranges = [f"{i:04d}-{i+RANGE_SIZE-1:04d}" for i in range(0, 10000, RANGE_SIZE)]

# === Extract & Format Data ===
rows = []

for doc in col.find({}, {"date": 1, "series": 1, "_id": 0}):
    date_raw = doc.get("date", "")
    date = date_raw.strip()

    numbers = []
    for s in doc.get("series", []):
        if s.get("prize") == PRIZE_FILTER:
            for n in s.get("numbers", []):
                try:
                    numbers.append(int(n["number"]))
                except:
                    pass

    count_map = {r: 0 for r in ranges}
    for num in numbers:
        idx = num // RANGE_SIZE
        if idx < len(ranges):
            count_map[ranges[idx]] += 1

    rows.append({"Date": date, **count_map})

# === Create DataFrame ===
df = pd.DataFrame(rows)

# === Filter only columns with at least one hit (except Date) ===
non_zero_cols = [col for col in df.columns if col == "Date" or df[col].sum() > 0]
df_filtered = df[non_zero_cols]

# === Build the pipe-separated, aligned string ===
col_width = 11

def align_val(val):
    return str(val).center(col_width)

header = " | ".join(align_val(col) for col in df_filtered.columns)

lines = [header, "-" * len(header)]

for _, row in df_filtered.iterrows():
    line = " | ".join(align_val(val) for val in row)
    lines.append(line)

# === Write to file ===
with open(OUTPUT_FILE, "w") as f:
    f.write("\n".join(lines))

print(f"\n✅ Pipe-separated formatted file saved as: {os.path.abspath(OUTPUT_FILE)}")
print("⚠️  This is NOT a standard CSV file; it uses pipes and spacing for human viewing.")
print("⚠️  It may not open properly in Excel as columns separated correctly.")
