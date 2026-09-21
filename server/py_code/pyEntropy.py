import pandas as pd
from pymongo import MongoClient
from collections import Counter, defaultdict
import math
from tqdm import tqdm

# ======================
# CONFIG
# ======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
coll = client[DB_NAME][COLLECTION]

# ----------------------
# Helper: Shannon entropy
# ----------------------
def shannon_entropy(freq_dict):
    total = sum(freq_dict.values())
    if total == 0:
        return 0
    entropy = 0
    for count in freq_dict.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy

# ----------------------
# Collect numbers with prizes
# ----------------------
print("🔄 Fetching all numbers with prize info...")
docs = list(coll.find({}, {"series": 1}))

all_numbers = []
for doc in tqdm(docs, desc="Extracting numbers"):
    for s in doc.get("series", []):
        prize = s.get("prize")
        for n in s.get("numbers", []):
            num = n.get("number")
            if num and num.isdigit():
                all_numbers.append((num.zfill(4), prize))

print(f"📊 Total numbers collected: {len(all_numbers)}")

# ----------------------
# 1. Overall digit frequency (already done)
# ----------------------
digit_counter = Counter("".join(num for num, _ in all_numbers))
overall_entropy = shannon_entropy(digit_counter)

# ----------------------
# 2. Per-position entropy
# ----------------------
pos_freqs = [Counter() for _ in range(4)]  # thousands,hundreds,tens,ones
for num, _ in all_numbers:
    for i, d in enumerate(num):
        pos_freqs[i][d] += 1

pos_results = []
for i, freq in enumerate(pos_freqs):
    pos_results.append({
        "position": i,
        "entropy": shannon_entropy(freq),
        "counts": dict(freq)
    })

# ----------------------
# 3. Per-prize entropy
# ----------------------
prize_freqs = defaultdict(Counter)
for num, prize in all_numbers:
    prize_freqs[prize].update(num)

prize_results = []
for prize, freq in prize_freqs.items():
    prize_results.append({
        "prize": prize,
        "entropy": shannon_entropy(freq),
        "counts": dict(freq)
    })

# ----------------------
# Save results
# ----------------------
rows = []

# overall
rows.append({
    "category": "overall",
    "info": "entropy",
    "value": overall_entropy,
    "details": dict(digit_counter)
})

# per position
for r in pos_results:
    rows.append({
        "category": f"position_{r['position']}",
        "info": "entropy",
        "value": r["entropy"],
        "details": r["counts"]
    })

# per prize
for r in prize_results:
    rows.append({
        "category": f"prize_{r['prize']}",
        "info": "entropy",
        "value": r["entropy"],
        "details": r["counts"]
    })

df_out = pd.DataFrame(rows)
df_out.to_csv("forensic_entropy_detailed.csv", index=False)

print("✅ Saved → forensic_entropy_detailed.csv with per-position and per-prize entropy.")
