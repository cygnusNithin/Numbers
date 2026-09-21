from pymongo import MongoClient
import pandas as pd
from collections import Counter

client = MongoClient("mongodb://localhost:27017/")
db = client["numbergrid"]
collection = db["lotterydatas"]

records = []

for doc in collection.find({}, {"date":1, "series":1, "_id":0}):
    date = pd.to_datetime(doc["date"], dayfirst=True)

    for s in doc["series"]:
        prize = s["prize"]

        for num_obj in s["numbers"]:
            num = str(num_obj["number"]).zfill(4)  # 4-digit numbers confirmed

            counts = Counter(num).values()
            freq = sorted(counts, reverse=True)

            if freq == [1,1,1,1]:
                pattern = "ALL_UNIQUE"
            elif freq == [2,1,1]:
                pattern = "ONE_PAIR"
            elif freq == [2,2]:
                pattern = "TWO_PAIR"
            elif freq == [3,1]:
                pattern = "THREE_KIND"
            elif freq == [4]:
                pattern = "FOUR_KIND"
            else:
                pattern = "OTHER"

            records.append((date, prize, pattern))

df = pd.DataFrame(records, columns=["date","prize","pattern"])
print("Total numbers analyzed:", len(df))

cutoff = pd.Timestamp("2025-05-01")

before = df[df["date"] < cutoff]
after  = df[df["date"] >= cutoff]

before_dist = before["pattern"].value_counts(normalize=True)
after_dist  = after["pattern"].value_counts(normalize=True)

comparison = pd.DataFrame({
    "Before May 2025": before_dist,
    "After May 2025": after_dist
}).fillna(0)

comparison["Shift"] = comparison["After May 2025"] - comparison["Before May 2025"]

print(comparison.sort_values("Shift", ascending=False))

df_sorted = df.sort_values("date")

df_sorted["next_pattern"] = df_sorted["pattern"].shift(-1)

transitions = pd.crosstab(df_sorted["pattern"], df_sorted["next_pattern"], normalize="index")

print(transitions)

df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.month

year_pattern = pd.crosstab(df["year"], df["pattern"], normalize="index")
month_pattern = pd.crosstab(df["month"], df["pattern"], normalize="index")

print("Yearly pattern distribution:")
print(year_pattern)

print("\nMonthly pattern distribution:")
print(month_pattern)

