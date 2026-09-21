import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from zoneinfo import ZoneInfo
from tqdm import tqdm

# =======================
# CONFIGURATION
# =======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
PRIZE_FILTER = 5000   # 🎯 Track 5000 prize numbers
OUTPUT_FILE = "new_5000_prize_numbers_grouped_ist.csv"

# Date range (India timezone). Change these if you want different window.
TZ = ZoneInfo("Asia/Kolkata")
START_DATE = datetime(2020, 1, 1, tzinfo=TZ)
END_DATE = datetime(2025, 12, 31, 23, 59, 59, tzinfo=TZ)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# =======================
# HELPERS
# =======================
def parse_date_to_ist(d):
    """
    Try to parse a date string into an aware datetime in Asia/Kolkata.
    Accepts multiple common formats. Returns None if parsing fails.
    """
    if not isinstance(d, str) or not d.strip():
        return None

    s = d.strip()

    # Common formats to try (with day-first priority)
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%d %B %Y",        # e.g. 09 September 2025
        "%d %b %Y",        # e.g. 09 Sep 2025
        "%B %d, %Y",       # e.g. September 9, 2025
        "%b %d, %Y",       # e.g. Sep 9, 2025
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=TZ)
        except Exception:
            continue

    # try to grab any dd/mm/yyyy-like substring using simple fallback
    import re
    m = re.search(r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", s)
    if m:
        substr = m.group(1)
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
            try:
                dt = datetime.strptime(substr, fmt)
                # Expand two-digit years if needed: strptime already handles %y, but we prefer 2000+ for small values
                return dt.replace(tzinfo=TZ)
            except Exception:
                continue

    return None


def get_prize_numbers(prize):
    """Fetch all numbers and dates for a specific prize from Mongo aggregation."""
    pipeline = [
        {"$unwind": "$series"},
        {"$match": {"series.prize": prize}},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "date": "$date"
        }}
    ]
    return list(lottery_data.aggregate(pipeline))


# =======================
# MAIN
# =======================
def main():
    print(f"🔄 Fetching all ₹{PRIZE_FILTER} prize numbers from DB...")
    data = get_prize_numbers(PRIZE_FILTER)
    df = pd.DataFrame(data)

    if df.empty:
        print("⚠️ No records found in the database for that prize.")
        return

    # Normalize number field as 4-digit (or preserve length if 6-digit stored; we'll zfill to 4 to match earlier logic)
    df["number"] = df["number"].astype(str).str.zfill(4)

    # Parse dates to IST
    df["parsed_date"] = df["date"].apply(parse_date_to_ist)
    # drop rows where date parsing failed
    df = df[df["parsed_date"].notnull()].copy()

    if df.empty:
        print("⚠️ No rows with parsable dates found after parsing.")
        return

    # filter by START_DATE and END_DATE if desired
    df = df[(df["parsed_date"] >= START_DATE) & (df["parsed_date"] <= END_DATE)]

    if df.empty:
        print("⚠️ No rows remain after applying date range filter.")
        return

    # sort by parsed_date ascending (India time)
    df.sort_values("parsed_date", inplace=True)

    print(f"📊 Total records fetched (after parse & range): {len(df)} across {df['parsed_date'].nunique()} draw days")

    # Identify first appearance date for each unique number
    seen = set()
    first_seen_by_number = {}   # number -> first_seen_datetime

    # iterate in chronological order (ascending)
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Scanning rows"):
        num = str(row["number"]).zfill(4)
        dt = row["parsed_date"]
        if num not in seen:
            seen.add(num)
            first_seen_by_number[num] = dt

    # Group numbers by their first_seen_date (string dd/mm/YYYY)
    grouped = {}
    for num, dt in first_seen_by_number.items():
        date_key = dt.strftime("%d/%m/%Y")
        # optional: only include numbers where first seen within START->END (we already filtered df)
        grouped.setdefault(date_key, []).append(num)

    # Build final output rows sorted by date (India ascending)
    rows = []
    # convert keys to datetime for accurate sort in IST
    date_items = []
    for date_str, nums in grouped.items():
        parsed = datetime.strptime(date_str, "%d/%m/%Y").replace(tzinfo=TZ)
        date_items.append((parsed, date_str, nums))
    date_items.sort(key=lambda x: x[0])  # ascending

    for parsed_dt, date_str, nums in date_items:
        nums_sorted = sorted(nums)
        rows.append({
            "date": date_str,
            "new_numbers_count": len(nums_sorted),
            "new_numbers": "|".join(nums_sorted)
        })

    out_df = pd.DataFrame(rows, columns=["date", "new_numbers_count", "new_numbers"])
    out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print(f"\n✅ Found {len(first_seen_by_number)} unique ₹{PRIZE_FILTER} numbers first seen between {START_DATE.date()} and {END_DATE.date()}.")
    print(f"📁 Saved grouped output to: {OUTPUT_FILE}")
    print("\n📊 Preview (top 12 rows):")
    print(out_df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
