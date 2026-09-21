from pymongo import MongoClient
from datetime import datetime
import csv
from tqdm import tqdm  # for progress bar

# MongoDB config
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION_NAME = "lotterydatas"

# Date range filter (match your date format: DD/MM/YYYY)
START_DATE_STR = "11/07/2020"
END_DATE_STR = "08/12/2025"
DATE_FORMAT = "%d/%m/%Y"

START_DATE = datetime.strptime(START_DATE_STR, DATE_FORMAT)
END_DATE = datetime.strptime(END_DATE_STR, DATE_FORMAT)

# Connect MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# Prepare ranges like 0000-0009 ... 9990-9999
range_size = 10
max_number = 9999
ranges = [(start, start + range_size - 1) for start in range(0, max_number + 1, range_size)]

# Prepare CSV header
header = ["date"] + [f"{str(start).zfill(4)}-{str(end).zfill(4)}" for start, end in ranges]

# Load valid documents
docs = []
print("Loading documents from MongoDB and filtering by date...")

for doc in collection.find():
    try:
        doc_date = datetime.strptime(doc["date"], DATE_FORMAT)
        if START_DATE <= doc_date <= END_DATE:
            # Save **DD/MM/YYYY** format
            docs.append((doc_date.strftime("%d/%m/%Y"), doc))
    except Exception as e:
        print(f"Skipping document with invalid date '{doc.get('date')}': {e}")

print(f"Documents in date range: {len(docs)}")
if not docs:
    print("No documents found in the specified date range.")
    exit()

# Aggregate data
aggregated = {}

print("Aggregating counts from documents...")
for date_str, doc in tqdm(docs, desc="Processing docs"):
    if date_str not in aggregated:
        aggregated[date_str] = {f"{str(s).zfill(4)}-{str(e).zfill(4)}": 0 for s, e in ranges}

    for series in doc.get("series", []):
        for number_obj in series.get("numbers", []):
            num_str = number_obj.get("number")
            count = number_obj.get("count", 1)

            if num_str and num_str.isdigit():
                num = int(num_str)
                for start, end in ranges:
                    if start <= num <= end:
                        aggregated[date_str][f"{str(start).zfill(4)}-{str(end).zfill(4)}"] += count
                        break

# Write CSV
csv_filename = "filtered_prizes.csv"
print(f"Writing CSV to {csv_filename}...")

with open(csv_filename, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(header)

    for date_str in tqdm(sorted(aggregated.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y")), 
                        desc="Writing CSV rows"):
        row = [date_str] + [aggregated[date_str][key] for key in header[1:]]
        writer.writerow(row)

print(f"CSV saved as {csv_filename}")

# -------- Pretty Print to Terminal -------- #

def print_table(aggregated_data, header):
    max_columns = 10
    limited_header = header[:max_columns + 1]

    col_widths = [max(len(col), 5) for col in limited_header]

    header_row = "| " + " | ".join(col.ljust(col_widths[i]) for i, col in enumerate(limited_header)) + " |"
    print(header_row)

    separator_row = "|-" + "-|-".join("-" * col_widths[i] for i in range(len(col_widths))) + "-|"
    print(separator_row)

    for date_str in sorted(aggregated_data.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y")):
        row_data = [date_str] + [str(aggregated_data[date_str][k]) for k in limited_header[1:]]
        row = "| " + " | ".join(row_data[i].ljust(col_widths[i]) for i in range(len(row_data))) + " |"
        print(row)


print("\nAggregated counts table (first 10 ranges):")
print_table(aggregated, header)


# -------- Save Pretty Table to Text File -------- #

def write_pretty_table_to_file(aggregated_data, header, filename, max_columns=None):

    with open(filename, "w", encoding="utf-8") as f:

        if max_columns is not None:
            hdr = header[:max_columns + 1]
        else:
            hdr = header[:]

        col_widths = [len(h) for h in hdr]

        for date_str in aggregated_data:
            if len(date_str) > col_widths[0]:
                col_widths[0] = len(date_str)
            for i, key in enumerate(hdr[1:], start=1):
                v = str(aggregated_data[date_str][key])
                if len(v) > col_widths[i]:
                    col_widths[i] = len(v)

        # Header row
        f.write("| " + " | ".join(hdr[i].ljust(col_widths[i]) for i in range(len(hdr))) + " |\n")

        # Separator
        f.write("|-" + "-|-".join("-" * col_widths[i] for i in range(len(hdr))) + "-|\n")

        # Rows
        for date_str in sorted(aggregated_data.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y")):
            values = [date_str] + [str(aggregated_data[date_str][k]) for k in hdr[1:]]
            f.write("| " + " | ".join(values[i].ljust(col_widths[i]) for i in range(len(values))) + " |\n")

    print(f"Pretty table saved to {filename}")


write_pretty_table_to_file(aggregated, header, "filtered_prizes_table.txt")
write_pretty_table_to_file(aggregated, header, "filtered_prizes_table_limited.txt", max_columns=10)
