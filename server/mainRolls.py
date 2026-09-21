import pandas as pd
from pymongo import MongoClient

# ===============================
# CONFIGURATION
# ===============================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotteryresults"
ROLLER_FILE = "mainRoll.csv"
OUTPUT_FILE = "roller_gaps_detailed.csv"

# ===============================
# LOAD ROLLER SEQUENCES
# ===============================
def load_rollers(csv_path):
    df = pd.read_csv(csv_path, dtype=str)
    rollers = {}
    for _, row in df.iterrows():
        rid = int(row["number_id"])
        seq = [int(x) for x in row["sequence"].split("|") if x.strip().isdigit()]
        rollers[rid] = seq
    return rollers

# ===============================
# FIND ROLLER GAP
# ===============================
def roller_gap(seq, start_digit, end_digit):
    """Calculate how many steps forward from start_digit to reach end_digit in the roller sequence."""
    if start_digit not in seq or end_digit not in seq:
        return None
    i1, i2 = seq.index(start_digit), seq.index(end_digit)
    return (i2 - i1) % len(seq)

# ===============================
# MAIN FUNCTION
# ===============================
def main():
    rollers = load_rollers(ROLLER_FILE)
    print(f"✅ Loaded {len(rollers)} roller sequences")

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]

    draws = list(collection.find({}, {"drawDate": 1, "serialNumber": 1, "prizes": 1}))
    print(f"📅 Total draws fetched: {len(draws)}")

    all_rows = []

    for draw in draws:
        date = draw.get("drawDate", "Unknown")
        serial = draw.get("serialNumber", "Unknown")
        prizes = draw.get("prizes", {})

        # Extract 6-digit parts of each prize number
        prize_order = ["1st Prize", "2nd Prize", "3rd Prize", "4th Prize", "5th Prize", "6th Prize"]
        valid = [(p, v[-6:]) for p, v in ((p, prizes.get(p)) for p in prize_order) if v and len(v) >= 8]

        if len(valid) < 2:
            continue  # skip incomplete records

        # Sequential comparisons: 1→2, 2→3, etc.
        for i in range(len(valid) - 1):
            from_prize, num_a = valid[i]
            to_prize, num_b = valid[i + 1]

            for roller_id in range(1, 7):  # 6 rollers = 6 digits
                seq = rollers.get(roller_id)
                if not seq:
                    continue

                d1 = int(num_a[roller_id - 1])
                d2 = int(num_b[roller_id - 1])
                gap = roller_gap(seq, d1, d2)

                all_rows.append({
                    "date": date,
                    "serialNumber": serial,
                    "from_number": num_a,
                    "to_number": num_b,
                    "roller_id": roller_id,
                    "digit_from": d1,
                    "digit_to": d2,
                    "gap_steps": gap
                })

    # Save to CSV
    df = pd.DataFrame(all_rows)
    df.sort_values(["date", "serialNumber", "from_number", "roller_id"], inplace=True)
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"✅ Saved detailed roller differences → {OUTPUT_FILE}")
    print(df.head(12))


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    main()
