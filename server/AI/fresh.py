from pymongo import MongoClient
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter
from scipy.stats import chi2

# =======================
# DB CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]

# =======================
# STEP 1: FETCH ₹5000 DATA
# =======================
cursor = collection.find(
    {"series.prize": 5000},
    {"date": 1, "series": 1, "_id": 0}
)

records = []

for doc in cursor:
    for s in doc["series"]:
        if s["prize"] == 5000:
            for n in s["numbers"]:
                num = n["number"]
                if num and num[-1].isdigit():
                    records.append(num[-1])  # last digit only

# =======================
# STEP 2: FREQUENCY COUNT
# =======================
counts = Counter(records)
total = sum(counts.values())
expected = total / 10

freq_df = pd.DataFrame({
    "digit": list(range(10)),
    "count": [counts.get(str(d), 0) for d in range(10)]
})

print(freq_df)
print(f"\nTotal ₹5000 samples: {total}")

# =======================
# STEP 3: CHI-SQUARE TEST
# =======================
chi_square = sum(
    ((obs - expected) ** 2) / expected
    for obs in freq_df["count"]
)

df = 9  # degrees of freedom (10 digits - 1)
critical = chi2.ppf(0.95, df)

print(f"\nChi-square value: {chi_square:.2f}")
print(f"Critical value (95%): {critical:.2f}")

if chi_square < critical:
    print("✅ Result: Distribution is statistically FAIR")
else:
    print("⚠️ Result: Distribution shows statistical ANOMALY")

# =======================
# STEP 4: GRAPH
# =======================
plt.figure()
plt.bar(freq_df["digit"], freq_df["count"])
plt.xlabel("Last Digit")
plt.ylabel("Frequency")
plt.title("Kerala Lottery ₹5000 Prize – Last Digit Distribution")
plt.show()
