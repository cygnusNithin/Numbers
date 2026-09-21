from pymongo import MongoClient
from datetime import datetime
import csv
from tqdm import tqdm  # for progress bar
import re

# ---------------- Config ----------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION_NAME = "lotterydatas"

# Date range filter (accept mixed formats in DB; output as DD/MM/YYYY)
START_DATE_STR = "11/07/2020"
END_DATE_STR   = "08/12/2025"
DATE_FORMAT_OUT = "%d/%m/%Y"

PRIZE_FILTER = 5000                     # only this prize tier
INCLUDE_COUNTS_IN_NUMBERS = True        # numbers column uses "NNNN:count" if True, else just "NNNN"

# Ranges (0000-0009 ... 9990-9999)
RANGE_SIZE = 10
MAX_NUMBER = 9999
range_starts = list(range(0, MAX_NUMBER + 1, RANGE_SIZE))
range_labels = [f"{s:04d}-{s+RANGE_SIZE-1:04d}" for s in range_starts]

# CSV filenames
COUNTS_CSV  = "filtered_prizes_5000_counts.csv"
NUMBERS_CSV = "filtered_prizes_5000_numbers.csv"
# ---------------------------------------


def parse_date_any(s):
    """Parse date from common formats, return datetime or None."""
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def number_to_range_label(n):
    """Map 0..9999 to its 10-wide range label."""
    start = (n // 10) * 10
    return f"{start:04d}-{start+9:04d}"


def numbers_dict_to_str(d, include_counts=True):
    """Convert {num: count} to a pipe-separated string, sorted by number."""
    if not d:
        return ""
    items = sorted(d.items(), key=lambda x: int(x[0]))
    if include_counts:
        return "|".join(f"{num}:{cnt}" for num, cnt in items)
    else:
        return "|".join(num for num, _ in items)


# Connect MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# Parse date range bounds
START_DATE = parse_date_any(START_DATE_STR)
END_DATE   = parse_date_any(END_DATE_STR)
if START_DATE is None or END_DATE is None:
    raise ValueError("Invalid START_DATE_STR or END_DATE_STR")

# Load docs in date range
docs = []
print("Loading documents from MongoDB and filtering by date...")
for doc in collection.find({}, {"date": 1, "series": 1}):
    dt = parse_date_any(doc.get("date"))
    if dt and START_DATE <= dt <= END_DATE:
        docs.append((dt, doc))

print(f"Documents in date range: {len(docs)}")
if not docs:
    print("No documents found in the specified date range.")
    raise SystemExit

# Aggregate data (counts and numbers per range per day, prize=5000 only)
aggregated = {}
print("Aggregating counts and numbers (prize=5000 only)...")

for dt, doc in tqdm(docs, desc="Processing docs"):
    date_str = dt.strftime(DATE_FORMAT_OUT)
    if date_str not in aggregated:
        aggregated[date_str] = {}  # lazy per-range creation

    for series in doc.get("series", []):
        if series.get("prize") != PRIZE_FILTER:
            continue

        for number_obj in series.get("numbers", []):
            num_str = number_obj.get("number")
            if num_str is None:
                continue

            # keep as 4-digit string if possible
            num_str = str(num_str).strip()
            if not re.fullmatch(r"\d{1,4}", num_str):
                continue  # skip non 4-digit numeric strings

            num_str = num_str.zfill(4)
            n = int(num_str)
            if n < 0 or n > 9999:
                continue

            count = number_obj.get("count", 1)
            try:
                count = int(count)
            except Exception:
                count = 1

            label = number_to_range_label(n)
            cell = aggregated[date_str].setdefault(label, {"count": 0, "numbers": {}})
            cell["count"] += count
            cell["numbers"][num_str] = cell["numbers"].get(num_str, 0) + count

# Write counts CSV (date × ranges with totals)
print(f"Writing counts CSV to {COUNTS_CSV}...")
with open(COUNTS_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    header = ["date"] + range_labels
    writer.writerow(header)

    for date_str in tqdm(sorted(aggregated.keys(), key=lambda d: datetime.strptime(d, DATE_FORMAT_OUT)),
                         desc="Writing counts rows"):
        row = [date_str]
        cells = aggregated[date_str]
        for label in range_labels:
            row.append(cells.get(label, {}).get("count", 0))
        writer.writerow(row)

# Write numbers CSV (date × ranges with "NNNN:count|..." strings)
print(f"Writing numbers CSV to {NUMBERS_CSV}...")
with open(NUMBERS_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    header = ["date"] + range_labels
    writer.writerow(header)

    for date_str in tqdm(sorted(aggregated.keys(), key=lambda d: datetime.strptime(d, DATE_FORMAT_OUT)),
                         desc="Writing numbers rows"):
        row = [date_str]
        cells = aggregated[date_str]
        for label in range_labels:
            nums_str = numbers_dict_to_str(
                cells.get(label, {}).get("numbers", {}),
                include_counts=INCLUDE_COUNTS_IN_NUMBERS
            )
            row.append(nums_str)
        writer.writerow(row)

print(f"CSV saved: {COUNTS_CSV}, {NUMBERS_CSV}")

# -------- Pretty print (first 10 ranges counts) -------- #
def print_table_counts(aggregated_data, header, max_columns=10):
    limited_header = header[:max_columns + 1]
    col_widths = [max(len(col), 5) for col in limited_header]

    header_row = "| " + " | ".join(col.ljust(col_widths[i]) for i, col in enumerate(limited_header)) + " |"
    print(header_row)
    separator_row = "|-" + "-|-".join("-" * col_widths[i] for i in range(len(col_widths))) + "-|"
    print(separator_row)

    for date_str in sorted(aggregated_data.keys(), key=lambda d: datetime.strptime(d, DATE_FORMAT_OUT)):
        row_data = [date_str] + [str(aggregated_data[date_str].get(k, {}).get("count", 0)) for k in limited_header[1:]]
        row = "| " + " | ".join(row_data[i].ljust(col_widths[i]) for i in range(len(row_data))) + " |"
        print(row)

print("\nAggregated 5000 counts table (first 10 ranges):")
print_table_counts(aggregated, ["date"] + range_labels)

# -------- Save pretty counts table to text files -------- #
def write_pretty_table_to_file(aggregated_data, header, filename, max_columns=None):
    if max_columns is not None:
        hdr = header[:max_columns + 1]
    else:
        hdr = header[:]

    # compute column widths
    col_widths = [len(h) for h in hdr]
    for date_str in aggregated_data:
        if len(date_str) > col_widths[0]:
            col_widths[0] = len(date_str)
        for i, key in enumerate(hdr[1:], start=1):
            v = str(aggregated_data[date_str].get(key, {}).get("count", 0))
            if len(v) > col_widths[i]:
                col_widths[i] = len(v)

    with open(filename, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(hdr[i].ljust(col_widths[i]) for i in range(len(hdr))) + " |\n")
        f.write("|-" + "-|-".join("-" * col_widths[i] for i in range(len(hdr))) + "-|\n")
        for date_str in sorted(aggregated_data.keys(), key=lambda d: datetime.strptime(d, DATE_FORMAT_OUT)):
            values = [date_str] + [str(aggregated_data[date_str].get(k, {}).get("count", 0)) for k in hdr[1:]]
            f.write("| " + " | ".join(values[i].ljust(col_widths[i]) for i in range(len(values))) + " |\n")

    print(f"Pretty table saved to {filename}")

write_pretty_table_to_file(aggregated, ["date"] + range_labels, "filtered_prizes_5000_counts_table.txt")
write_pretty_table_to_file(aggregated, ["date"] + range_labels, "filtered_prizes_5000_counts_table_limited.txt", max_columns=10)