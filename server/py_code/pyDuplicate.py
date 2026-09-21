import pandas as pd
from pymongo import MongoClient
from collections import defaultdict, Counter
from tqdm import tqdm
import numpy as np
from math import log2

# ======================
# CONFIG
# ======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
coll = client[DB_NAME][COLLECTION]

# ======================
# Helper: Shannon entropy
# ======================
def shannon_entropy(numbers):
    counts = Counter(numbers)
    total = sum(counts.values())
    probs = [c/total for c in counts.values()]
    return -sum(p * log2(p) for p in probs)

# ======================
# Load all documents
# ======================
docs = list(coll.find({}, {"series": 1, "date": 1, "serialNumber": 1}))

# ----------------------
# 1. Duplicate full-draw sets
# ----------------------
print("🔍 Checking for duplicate full-draw sets...")
key_map = defaultdict(list)

for doc in tqdm(docs, desc="Processing draws for duplicates"):
    nums = []
    for s in doc.get("series", []):
        for n in s.get("numbers", []):
            nums.append(n.get("number"))
    key = "|".join(sorted(set(nums)))
    key_map[key].append((doc.get("date"), doc.get("serialNumber")))

dups = {k: v for k, v in key_map.items() if len(v) > 1}
dup_rows = []
for k, v in dups.items():
    dup_rows.append({
        "category": "duplicate_draw",
        "info": k,
        "count": len(v),
        "details": str(v)
    })

# ----------------------
# 2. Serial number reuse
# ----------------------
print("🔍 Checking for serial number reuse...")
serials = Counter()
serial_details = defaultdict(list)

for d in tqdm(docs, desc="Checking serial numbers"):
    s = d.get("serialNumber") or "<NULL>"
    serials[s] += 1
    serial_details[s].append(d.get("date"))

serial_rows = []
for s, c in serials.items():
    if c > 1:
        serial_rows.append({
            "category": "serial_reuse",
            "info": s,
            "count": c,
            "details": "|".join(serial_details[s])
        })

# ----------------------
# 3. Date anomalies
# ----------------------
print("🔍 Checking for date anomalies...")

df_dates = pd.DataFrame(docs)
df_dates["parsed"] = pd.to_datetime(df_dates["date"], dayfirst=True, errors="coerce")

malformed_rows = [
    {"category": "malformed_date", "info": row["date"], "count": 1, "details": str(row["_id"])}
    for _, row in df_dates[df_dates["parsed"].isna()].iterrows()
]

future_rows = [
    {"category": "future_date", "info": row["date"], "count": 1, "details": str(row["_id"])}
    for _, row in df_dates[df_dates["parsed"] > pd.Timestamp.today()].iterrows()
]

# ----------------------
# 4. Digit randomness / entropy
# ----------------------
print("🔍 Checking digit randomness/entropy...")

all_numbers = []
for doc in tqdm(docs, desc="Collecting numbers for entropy"):
    for s in doc.get("series", []):
        for n in s.get("numbers", []):
            all_numbers.append(n.get("number"))

digit_rows = []
if all_numbers:
    flat_digits = "".join(all_numbers)
    entropy = shannon_entropy(flat_digits)
    digit_counts = Counter(flat_digits)

    digit_rows.append({
        "category": "digit_entropy",
        "info": "entropy",
        "count": round(entropy, 4),
        "details": str(dict(digit_counts))
    })

# ----------------------
# Combine all anomalies
# ----------------------
all_rows = dup_rows + serial_rows + malformed_rows + future_rows + digit_rows
df_all = pd.DataFrame(all_rows)

df_all.to_csv("forensic_summary.csv", index=False, encoding="utf-8")
print(f"\n✅ Unified forensic summary saved → forensic_summary.csv ({len(df_all)} rows)")
