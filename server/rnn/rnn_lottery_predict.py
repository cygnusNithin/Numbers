import os
import csv
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"

# ====== choose ======
DB_KEY = "db3"          # "db3" or "db4"
PRIZE = 5000           # e.g. 5000
OUTPUT_DIR = "output_cycles"

TOTAL_UNIVERSE = 10000  # 0000..9999

# ====== collections ======
COLLECTIONS = {
    "db3": "lottery_results_v2",
    "db4": "absolute_data",
}

def is_valid_4digits(num):
    s = str(num).strip()
    return len(s) == 4 and s.isdigit()

def parse_ddmmyyyy(s):
    # your schema: DD/MM/YYYY
    return datetime.strptime(s, "%d/%m/%Y")

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def fetch_daily_sets(collection, prize):
    """
    Returns list of (date_string, set_of_4digit_strings) sorted by real date.
    """
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {"date": 1, "number": "$series.numbers.number"}},
        {"$group": {"_id": "$date", "numbers": {"$addToSet": "$number"}}},
    ]
    days = []
    for doc in collection.aggregate(pipeline, allowDiskUse=True):
        date_str = doc.get("_id")
        if not date_str:
            continue

        nums = set()
        for n in doc.get("numbers", []):
            if is_valid_4digits(n):
                nums.add(str(n).zfill(4))
        if nums:
            days.append((date_str, nums))

    days.sort(key=lambda x: parse_ddmmyyyy(x[0]))
    return days

def cycle_progress(days):
    """
    Cycle rule:
    - cycle_set starts empty
    - add each day's nums
    - if cycle_set reaches 10000, cycle completes and resets at next day
    """
    all_numbers = {str(i).zfill(4) for i in range(TOTAL_UNIVERSE)}

    cycle_idx = 1
    cycle_start_date = None
    cycle_set = set()

    cycles = []  # list of dicts
    # For current incomplete cycle:
    last_seen_set = set()
    last_seen_date = None

    for date_str, day_nums in days:
        if cycle_start_date is None:
            cycle_start_date = date_str

        # add for this day
        cycle_set |= day_nums
        last_seen_set = set(cycle_set)
        last_seen_date = date_str

        # complete cycle if full
        if len(cycle_set) >= TOTAL_UNIVERSE:
            cycles.append({
                "cycle": cycle_idx,
                "start_date": cycle_start_date,
                "end_date": date_str,
                "unique_count": len(cycle_set),
                "completed": True
            })
            cycle_idx += 1
            cycle_start_date = None
            cycle_set = set()

    # current cycle is the last cycle_idx-1 in progress if there are remaining dates processed
    # If cycles finished exactly at the end, cycle_start_date will be None and cycle_set empty.
    current_cycle_num = cycle_idx if cycle_start_date is not None else (cycle_idx - 1)
    if current_cycle_num < 1:
        current_cycle_num = 1

    # remaining numbers in current (in-progress) cycle:
    remaining = all_numbers - last_seen_set
    present_count = len(last_seen_set)
    remaining_count = len(remaining)

    return cycles, {
        "current_cycle": current_cycle_num,
        "current_cycle_start_date": cycle_start_date,
        "last_seen_date_in_current_cycle": last_seen_date,
        "present_count": present_count,
        "remaining_count": remaining_count,
        "remaining_numbers": sorted(list(remaining))
    }

def write_csv_list(path, header, values):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([header])
        for v in values:
            w.writerow([v])

def write_cycles_summary(path, cycles, incomplete_info):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cycle", "start_date", "end_date", "unique_count", "completed"])
        for c in cycles:
            w.writerow([c["cycle"], c["start_date"], c["end_date"], c["unique_count"], c["completed"]])
        # Also write current incomplete as a special row
        w.writerow([])
        w.writerow(["CURRENT_CYCLE_INCOMPLETE", "", "", "", ""])
        w.writerow(["current_cycle", incomplete_info["current_cycle"], "", "", ""])
        w.writerow(["current_cycle_start_date", incomplete_info["current_cycle_start_date"], "", "", ""])
        w.writerow(["last_seen_date_in_current_cycle", incomplete_info["last_seen_date_in_current_cycle"], "", "", ""])
        w.writerow(["present_count", incomplete_info["present_count"], "", "", ""])
        w.writerow(["remaining_count", incomplete_info["remaining_count"], "", "", ""])

def main():
    ensure_dir(OUTPUT_DIR)
    out_dir = os.path.join(OUTPUT_DIR, f"{DB_KEY}_prize_{PRIZE}")
    ensure_dir(out_dir)

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTIONS[DB_KEY]]

    print(f"Fetching daily unique number sets for DB={DB_KEY}, prize={PRIZE} ...")
    days = fetch_daily_sets(collection, PRIZE)
    print(f"Total days found (with numbers): {len(days)}")

    print("Computing cycles (0000..9999 coverage) ...")
    cycles, incomplete = cycle_progress(days)

    # Save outputs
    cycles_summary_csv = os.path.join(out_dir, "cycles_summary.csv")
    write_cycles_summary(cycles_summary_csv, cycles, incomplete)

    remaining_csv = os.path.join(out_dir, "current_cycle_remaining_numbers.csv")
    write_csv_list(remaining_csv, "number", incomplete["remaining_numbers"])

    print("\n===== RESULT =====")
    print(f"Completed cycles: {len(cycles)}")
    if cycles:
        last_completed = cycles[-1]
        print(f"Last completed cycle: {last_completed['cycle']} from {last_completed['start_date']} to {last_completed['end_date']}")
    print(f"Current cycle number (incomplete): {incomplete['current_cycle']}")
    print(f"Numbers present in current cycle: {incomplete['present_count']}")
    print(f"Numbers remaining to complete current cycle: {incomplete['remaining_count']}")
    print(f"Remaining list saved to: {remaining_csv}")
    print(f"Cycles summary saved to: {cycles_summary_csv}")

if __name__ == "__main__":
    main()