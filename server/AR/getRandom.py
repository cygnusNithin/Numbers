from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]

total_days = 0
total_numbers = 0

for doc in collection.find({}):
    total_days += 1
    daily_count = 0

    series_list = doc.get("series", [])
    
    for series in series_list:
        numbers = series.get("numbers", [])
        
        for num_obj in numbers:
            daily_count += num_obj.get("count", 1)

    total_numbers += daily_count

average = total_numbers / total_days if total_days > 0 else 0

print("Total Days:", total_days)
print("Total Numbers:", total_numbers)
print("Average Numbers Per Day:", round(average, 4))
