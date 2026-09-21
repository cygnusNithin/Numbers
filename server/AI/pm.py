import csv
from itertools import permutations

INPUT_CSV = "all_prizes_number_patterns18.csv"
OUTPUT_CSV = "permutation_analysis.csv"

# --------------------------------------------------
# Load CSV into memory (preserve order)
# --------------------------------------------------
rows = []
number_map = {}

with open(INPUT_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        num = row["number"].zfill(4)
        row["number"] = num
        rows.append(row)
        number_map[num] = row

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def digit_key(num_str):
    """Canonical digit-set key (sorted digits)"""
    return "".join(sorted(num_str))

def get_permutations(num_str):
    return sorted(set("".join(p) for p in permutations(num_str, 4)))

# --------------------------------------------------
# Process numbers (skip duplicate digit-sets)
# --------------------------------------------------
visited_digit_sets = set()
results = []

for row in rows:
    base = row["number"]
    key = digit_key(base)

    # 🔒 Skip if this digit-set already processed
    if key in visited_digit_sets:
        continue

    visited_digit_sets.add(key)

    perms = get_permutations(base)

    for p in perms:
        if p in number_map:
            results.append({
                "base_number": base,
                "permutation": p,
                "exists": "YES",
                "total_hits": number_map[p]["total_hits"],
                "dates": number_map[p]["dates"]
            })
        else:
            results.append({
                "base_number": base,
                "permutation": p,
                "exists": "NO",
                "total_hits": 0,
                "dates": ""
            })

# --------------------------------------------------
# Write output
# --------------------------------------------------
fieldnames = [
    "base_number",
    "permutation",
    "exists",
    "total_hits",
    "dates"
]

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

print("✅ Permutation analysis completed (duplicates skipped)")
print("📁 Output file:", OUTPUT_CSV)
