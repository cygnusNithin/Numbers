import pandas as pd
import numpy as np
from pymongo import MongoClient
from tqdm.auto import tqdm

MONGO_URI = "mongodb://localhost:27017/"
DB, COL = "numbergrid", "lotterydatas"
PRIZES_NON5000 = [100,200,500,1000,2000]
ALL = set(PRIZES_NON5000+[5000])

client = MongoClient(MONGO_URI)
col = client[DB][COL]

pipe = [
    {"$unwind":"$series"},
    {"$unwind":"$series.numbers"},
    {"$project":{"date":"$date","prize":"$series.prize","number":"$series.numbers.number"}},
]
rows = list(col.aggregate(pipe, allowDiskUse=True))
df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
df = df.dropna(subset=["date"])
df["day"] = df["date"].dt.normalize()
df["number"] = df["number"].astype(str).str.zfill(4)
df["prize"] = pd.to_numeric(df["prize"], errors="coerce").astype("Int64")
df = df[df["prize"].isin(ALL)]
df = df.groupby(["number","day","prize"], as_index=False).size()  # presence
df = df.sort_values(["number","day","prize"]).reset_index(drop=True)
df["year"] = df["day"].dt.year

def prev_table(group):
    g = group.sort_values(["day","prize"]).copy()
    g["prev_prize"] = g["prize"].shift(1)
    g["prev_day"] = g["day"].shift(1)
    return g.dropna(subset=["prev_prize"])

years = sorted(df["year"].unique())
for y in years:
    dyy = df[df["year"]==y]
    if dyy.empty: continue
    prev_all = dyy.groupby("number").apply(prev_table).reset_index(drop=True)
    # Immediate previous before 5000
    prev_5000 = prev_all[prev_all["prize"]==5000]["prev_prize"].astype(int)
    a = prev_5000.value_counts().reindex(PRIZES_NON5000, fill_value=0)
    # Immediate previous before any prize (baseline exposure)
    b = prev_all["prev_prize"].astype(int).value_counts().reindex(PRIZES_NON5000, fill_value=0)
    a_pct = a / max(a.sum(),1)
    b_pct = b / max(b.sum(),1)
    or_ = (a_pct / b_pct).replace([np.inf, -np.inf], np.nan)
    print(f"\n{y} immediate previous prize OR vs baseline:")
    print(pd.DataFrame({"a_5000":a, "a_pct":(a_pct*100).round(2), "b_all":b, "b_pct":(b_pct*100).round(2), "OR":or_.round(2)}))