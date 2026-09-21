from pymongo import MongoClient
import pandas as pd

# ===============================
# CONFIGURATION
# ===============================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotteryresults"
OUTPUT_FILE = "extra_prize_days.csv"

# ===============================
# MAIN LOGIC
# ===============================
def main():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]

    draws = list(collection.find({}, {"drawDate": 1, "serialNumber": 1, "prizes": 1}))
    print(f"📅 Total records fetched: {len(draws)}")

    extra_prize_rows = []

    for draw in draws:
        date = draw.get("drawDate", "Unknown")
        serial = draw.get("serialNumber", "Unknown")
        prizes = draw.get("prizes", {})

        # Count how many prizes exist in this draw
        prize_count = len([p for p in prizes.keys() if prizes[p]])

        if prize_count > 3:
            extra_prize_rows.append({
                "date": date,
                "serialNumber": serial,
                "prize_count": prize_count,
                "available_prizes": "|".join(sorted(prizes.keys()))
            })

    if not extra_prize_rows:
        print("✅ No draws found with more than 3 prizes.")
    else:
        df = pd.DataFrame(extra_prize_rows)
        df.sort_values(["date", "serialNumber"], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"✅ Found {len(df)} draws with >3 prizes. Saved to → {OUTPUT_FILE}")
        print(df.head(10))


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    main()
