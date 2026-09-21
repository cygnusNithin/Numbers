from pymongo import MongoClient
import pandas as pd
import numpy as np
from collections import Counter
from scipy.stats import chisquare
from tqdm import tqdm   # ✅ progress bar

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# LOAD DATA
# =======================
print("🔄 Loading data from MongoDB...")
df = pd.DataFrame(list(lottery_data.find()))

rows = []
print("🔄 Flattening numbers...")
for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing draws"):
    for series in row["series"]:
        for num in series["numbers"]:
            rows.append(num["number"])

numbers = pd.Series(rows)

# =======================
# DIGIT FREQUENCY
# =======================
digits = {pos: [] for pos in range(4)}  # 4 positions

print("🔄 Analyzing digit positions...")
for num in tqdm(numbers, desc="Splitting digits"):
    if len(num) == 4:
        for i, d in enumerate(num):
            digits[i].append(int(d))

digit_counts = {pos: Counter(d) for pos, d in digits.items()}

print("\n🔢 Digit Frequency by Position:")
for pos, counter in digit_counts.items():
    total = sum(counter.values())
    print(f"Position {pos}: {dict(counter)}")

# =======================
# CHI-SQUARE TEST
# =======================
print("\n📊 Chi-Square Test for Uniformity:")
for pos, counter in digit_counts.items():
    observed = np.array([counter[d] for d in range(10)])
    expected = np.array([sum(observed)/10]*10)
    chi2, p = chisquare(observed, expected)
    print(f"Position {pos} → Chi2={chi2:.2f}, p={p:.4f}")

# =======================
# TOP REPEATED NUMBERS
# =======================
print("\n🔥 Top 20 Repeated Numbers:")
print(numbers.value_counts().head(20))
