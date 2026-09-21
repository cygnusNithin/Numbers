import pandas as pd
import numpy as np
from pymongo import MongoClient
from tqdm import tqdm
from scipy.stats import chisquare

# ==========================
# CONFIG
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000   # only analyze 5000 prize

# Connect MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

print("🔄 Loading data from MongoDB...")

# ==========================
# LOAD DATA
# ==========================
df = pd.DataFrame(list(lottery_data.find()))
df["date"] = pd.to_datetime(df["date"], errors="coerce")

# Flatten only 5000 prize numbers
rows = []
print("🔄 Flattening numbers...")
for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing draws"):
    for series in row["series"]:
        if series["prize"] == PRIZE_FILTER:
            for num in series["numbers"]:
                rows.append({"date": row["date"], "number": num["number"], "prize": series["prize"]})

flat = pd.DataFrame(rows)

# ==========================
# DIGIT FREQUENCY ANALYSIS
# ==========================
print("🔄 Analyzing digit positions...")

digit_counts = {pos: {d: 0 for d in range(10)} for pos in range(4)}

for num in tqdm(flat["number"], desc="Splitting digits"):
    if pd.isna(num) or not str(num).isdigit():
        continue
    num = str(num).zfill(4)
    for pos, digit in enumerate(num):
        digit_counts[pos][int(digit)] += 1

print("\n🔢 Digit Frequency by Position (only 5000 prize):")
for pos in range(4):
    print(f"Position {pos}: {digit_counts[pos]}")

# ==========================
# CHI-SQUARE TEST
# ==========================
print("\n📊 Chi-Square Test for Uniformity (5000 prize only):")
for pos in range(4):
    observed = list(digit_counts[pos].values())
    expected = [np.mean(observed)] * 10
    chi2, p = chisquare(observed, expected)
    print(f"Position {pos} → Chi2={chi2:.2f}, p={p:.4f}")

# ==========================
# TOP REPEATED NUMBERS
# ==========================
print("\n🔥 Top 20 Repeated Numbers (5000 prize only):")
top_repeats = flat["number"].value_counts().head(20)
print(top_repeats)
