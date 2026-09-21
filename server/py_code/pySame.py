from pymongo import MongoClient
from itertools import combinations
from tqdm import tqdm   # ✅ progress bar
import csv

# =======================
# CONFIG
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"   # adjust to your collection name
MIN_SIZE = 2
MAX_SIZE = 20

# Connect MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

def get_combinations(array, size):
    """Generate all combinations of given size."""
    return list(combinations(array, size))

def find_number_sets(prize_amount):
    # Step 1: Collect all numbers by date+code
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize_amount}},
        {"$unwind": "$series.numbers"},
        {"$group": {
            "_id": {"date": "$date", "code": "$serialNumber"},
            "numbers": {"$addToSet": "$series.numbers.number"}
        }}
    ]

    draws = list(lottery_data.aggregate(pipeline))

    # Step 2: Map combinations → appearances
    combo_map = {}

    print(f"🔄 Processing {len(draws)} draws...")
    for draw in tqdm(draws, desc="Generating combos"):   # ✅ progress bar
        nums = sorted(draw["numbers"])
        for size in range(MIN_SIZE, min(MAX_SIZE, len(nums)) + 1):
            subsets = get_combinations(nums, size)
            for subset in subsets:
                key = "|".join(subset)
                if key not in combo_map:
                    combo_map[key] = []
                combo_map[key].append(f"{draw['_id']['date']} ({draw['_id']['code']})")

    # Step 3: Only keep combos that repeat
    results = []
    for combo, appearances in combo_map.items():
        if len(appearances) > 1:
            results.append({
                "prize": prize_amount,
                "count": len(appearances),
                "numbers": combo,
                "draws": "|".join(appearances)
            })

    return results


if __name__ == "__main__":
    try:
        combos = find_number_sets(5000)

        # Save CSV
        with open("number_20_combos.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Prize", "Count", "Numbers", "Dates+Codes"])
            for c in combos:
                writer.writerow([c["prize"], c["count"], c["numbers"], c["draws"]])

        print("✅ Saved to number_20_combos.csv")

    except Exception as e:
        print("❌ Error:", e)

    finally:
        client.close()
