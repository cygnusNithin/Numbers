from pymongo import MongoClient
import pandas as pd

# MongoDB connection
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# Fetch documents
docs = list(lottery_data.find())

# Flatten nested structure
rows = []
for doc in docs:
    for s in doc.get("series", []):
        prize = s.get("prize")
        for num in s.get("numbers", []):
            rows.append({
                "entryNumber": doc.get("entryNumber"),
                "serialNumber": doc.get("serialNumber"),
                "date": doc.get("date"),
                "prize": prize,
                "number": num.get("number"),
                "count": num.get("count", 1)
            })

df = pd.DataFrame(rows)
print(df.head())
