import pandas as pd
from math import exp, factorial
from pymongo import MongoClient

# ----- CONFIG -----
MONGO_URI = "mongodb://localhost:27017/"
DB = "numbergrid"
COL = "lotterydatas"
PRIZE = 5000
K = 10000  # 0000..9999

# ----- LOAD FROM MONGO -----
client = MongoClient(MONGO_URI)
col = client[DB][COL]

pipeline = [
    {"$unwind": "$series"},
    {"$match": {"series.prize": PRIZE}},
    {"$unwind": "$series.numbers"},
    {"$project": {
        "date": "$date",
        "number": "$series.numbers.number",
        "count": {"$ifNull": ["$series.numbers.count", 1]},
    }},
]
rows = list(col.aggregate(pipeline, allowDiskUse=True))
df = pd.DataFrame(rows)

# ----- CLEAN & WINDOW (last 5 years) -----
df["dt"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
df = df.dropna(subset=["dt"]).copy()

# keep only 4-digit numbers 0000..9999
df["number"] = df["number"].astype(str).str.zfill(4)
df = df[df["number"].str.match(r"^\d{4}$")]

end = df["dt"].max()
start = end - pd.DateOffset(years=5)
df_5y = df[(df["dt"] >= start) & (df["dt"] <= end)].copy()

# total hits per number (respect 'count')
hits_5y = df_5y.groupby("number")["count"].sum()

# ----- POISSON OVERLAY -----
lam = hits_5y.sum() / K  # mean per number over 5y (including zeros)
obs = hits_5y.value_counts().sort_index()
zeros = K - len(hits_5y)  # numbers never seen in 5y
obs = pd.concat([pd.Series({0: zeros}), obs]).sort_index()

def pois_pmf(k, l):
    return exp(-l) * (l**k) / factorial(k)

ks = range(0, max(12, int(obs.index.max())) + 1)
exp_counts = pd.Series({k: K * pois_pmf(k, lam) for k in ks})

compare = pd.DataFrame({"Observed": obs, "Expected": exp_counts}).fillna(0).round(1)

# ----- SUMMARY -----
nums_seen = len(hits_5y)
total_hits = int(hits_5y.sum())
print(f"Universe (4-digit): {K}")
print(f"Numbers seen at least once: {nums_seen}  (never seen: {K - nums_seen})")
print(f"Total hits over 5y: {total_hits}")
print("λ (mean per number over 5y):", round(lam, 3))
print("\nObserved vs Poisson expected (counts) for k=0..12:")
print(compare.loc[:12])