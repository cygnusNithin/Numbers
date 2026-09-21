import pandas as pd
from pymongo import MongoClient
from datetime import datetime

# ===============================
# CONFIGURATION
# ===============================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotteryresults"
ROLLER_FILE = "sixRoll.csv"
OUTPUT_FILE = "sixroller_gaps_detailed.csv"

# ===============================
# LOAD ROLLER SEQUENCES
# ===============================
def load_rollers(csv_path):
    df = pd.read_csv(csv_path, dtype=str)
    rollers = {}
    for _, row in df.iterrows():
        rid = int(row["number_id"])
        seq = [int(x) for x in row["sequence"].split("|") if str(x).strip().isdigit()]
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
# SAFE DATE PARSER
# ===============================
def parse_date_safe(date_str):
    """Try to parse date from common formats (returns pd.Timestamp or NaT)."""
    if not date_str or pd.isna(date_str):
        return pd.NaT
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return pd.to_datetime(datetime.strptime(date_str, fmt))
        except Exception:
            continue
    # fallback: try pandas
    try:
        return pd.to_datetime(date_str, dayfirst=True, errors="coerce")
    except Exception:
        return pd.NaT

# ===============================
# MAIN FUNCTION
# ===============================
def main():
    rollers = load_rollers(ROLLER_FILE)
    print(f"✅ Loaded {len(rollers)} roller sequences")

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]

    # fetch draws (you can add a filter or projection if desired)
    draws = list(collection.find({}, {"drawDate": 1, "serialNumber": 1, "prizes": 1}))
    print(f"📅 Total draws fetched: {len(draws)}")

    all_rows = []
    prize_order = ["1st Prize", "2nd Prize", "3rd Prize", "4th Prize", "5th Prize", "6th Prize"]

    for draw in draws:
        date = draw.get("drawDate", "Unknown")
        serial = draw.get("serialNumber", "Unknown")
        prizes = draw.get("prizes", {}) or {}

        # Build ordered list of available 6-digit prizes in prize_order order
        ordered = []
        for p in prize_order:
            v = prizes.get(p)
            if not v:
                continue
            # attempt to extract last 6 digits of the prize entry (handles prefixes like "KE236932")
            digits = "".join(ch for ch in str(v) if ch.isdigit())
            if len(digits) >= 6:
                ordered.append((p, digits[-6:]))  # keep prize label and 6-digit string

        if len(ordered) < 2:
            # not enough prizes to compare
            continue

        # Create sequential comparisons: (1st->2nd), (2nd->3rd), ...
        for i in range(len(ordered) - 1):
            from_prize_label, num_a = ordered[i]
            to_prize_label, num_b = ordered[i + 1]
            pair_index = i  # 0 for first pair, 1 for second pair, etc.

            # Ensure each number is 6 chars (pad leading zeros if any)
            num_a = str(num_a).zfill(6)
            num_b = str(num_b).zfill(6)

            # For each of the 6 rollers (digits)
            for roller_id in range(1, 7):
                seq = rollers.get(roller_id)
                if not seq:
                    gap = None
                else:
                    # extract digits for this roller position (1..6)
                    try:
                        d1 = int(num_a[roller_id - 1])
                        d2 = int(num_b[roller_id - 1])
                    except (IndexError, ValueError):
                        # invalid formatting, skip
                        continue
                    gap = roller_gap(seq, d1, d2)

                # Append a detailed row with pair_index for correct sort order later
                all_rows.append({
                    "date": date,
                    "parsed_date": parse_date_safe(date),
                    "serialNumber": serial,
                    "pair_index": pair_index,
                    "from_prize": from_prize_label,
                    "to_prize": to_prize_label,
                    "from_number": num_a,
                    "to_number": num_b,
                    "roller_id": roller_id,
                    "digit_from": int(num_a[roller_id - 1]) if len(num_a) >= roller_id else None,
                    "digit_to": int(num_b[roller_id - 1]) if len(num_b) >= roller_id else None,
                    "gap_steps": gap
                })

    # Convert to DataFrame
    df = pd.DataFrame(all_rows)

    if df.empty:
        print("⚠️ No valid rows to save.")
        return

    # Sort by parsed_date asc, serialNumber, pair_index, roller_id
    df.sort_values(["parsed_date", "serialNumber", "pair_index", "roller_id"], inplace=True)

    # Drop helper parsed_date column (keeps original date string)
    df.drop(columns=["parsed_date"], inplace=True)

    # Save to CSV
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"✅ Saved detailed roller differences → {OUTPUT_FILE}")

    # show small sample
    print(df.head(24).to_string(index=False))


if __name__ == "__main__":
    main()
