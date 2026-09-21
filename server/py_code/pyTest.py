from pymongo import MongoClient
import pandas as pd
from tqdm import tqdm

# ==========================
# CONFIG
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE = 5000

# Connect MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

print("🔄 Loading all 5000 prize numbers...")

pipeline = [
    {"$unwind": "$series"},
    {"$match": {"series.prize": PRIZE}},
    {"$unwind": "$series.numbers"},
    {"$group": {
        "_id": "$series.numbers.number",
        "count": {"$sum": 1}
    }},
    {"$sort": {"count": -1}}
]

results = list(lottery_data.aggregate(pipeline))

# Convert to DataFrame
df = pd.DataFrame(results)
df.rename(columns={"_id": "number"}, inplace=True)

# Find max count
max_count = df["count"].max()

# Calculate remaining attempts
df["remaining_attempts"] = max_count - df["count"]

# Sort by count
df = df.sort_values(by="count", ascending=False).reset_index(drop=True)

print("\n🔥 All Numbers (5000 prize) with Remaining Attempts:\n")
print(df.head(50))  # preview top 50 for quick check

# Save to CSV
df.to_csv("all_remaining_attempts1.csv", index=False)
print("\n✅ Full list saved to all_remaining_attempts1.csv")
