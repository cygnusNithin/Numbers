from pymongo import MongoClient
import pandas as pd
from datetime import datetime

# --- Connect to MongoDB ---
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# --- Load all dates and parse as datetime (DD/MM/YYYY) ---
date_docs = list(lottery_data.find({}, {"date": 1, "_id": 0}))
dates = [d.get("date") for d in date_docs if d.get("date")]

def parse_db_date(s):
    try:
        return datetime.strptime(s, "%d/%m/%Y")   # <-- corrected format
    except Exception:
        return None

parsed = [(parse_db_date(s), s) for s in dates if parse_db_date(s)]
parsed.sort(key=lambda x: x[0])

if not parsed:
    raise ValueError("No valid DD/MM/YYYY dates found in DB")

first_date_str = parsed[0][1]
print("First day in DB:", first_date_str)

# --- Get all results for that date ---
docs = lottery_data.find({"date": first_date_str}, {"series": 1, "date": 1})

rows = []
for doc in docs:
    for s in doc.get("series", []):
        prize = s.get("prize")
        for num in s.get("numbers", []):
            if isinstance(num, dict) and "number" in num:
                rows.append({
                    "date": doc["date"],
                    "category": prize,
                    "number": num["number"]
                })

df = pd.DataFrame(rows)
# Save all first day numbers with categories
df.to_csv("first_day_results.csv", index=False)

print("Saved first day numbers to first_day_results.csv")


# --- Summarize baseline ---
total_unique = df["number"].nunique()
n_categories = df["category"].nunique()
per_cat = df.groupby("category")["number"].nunique().sort_values(ascending=False)

print("Total results on first day:", total_unique)
print("Number of categories:", n_categories)
print("Results per category:\n", per_cat)
