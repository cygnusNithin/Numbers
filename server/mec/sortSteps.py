import csv
import re

INPUT_CSV = "sequence_movement_full_map.csv"
OUTPUT_CSV = "sorted_output.csv"

def extract_rollerset_num(text):
    return int(re.findall(r'\d+', text)[0])

def extract_pair(pair_text):
    # "(3,2)" → 3 , 2
    nums = re.findall(r'\d+', pair_text)
    return int(nums[0]), int(nums[1])

rows = []

# Read CSV
with open(INPUT_CSV, "r", newline="") as f:
    reader = csv.DictReader(f)

    for row in reader:
        # RollerSet number
        row["RollerSet_num"] = extract_rollerset_num(row["RollerSet"])

        # Step number
        row["Step_num"] = int(row["Step"])

        # Pair numbers
        p1, p2 = extract_pair(row["Pair"])
        row["Pair1"] = p1
        row["Pair2"] = p2

        rows.append(row)

# ==== ✅ CUSTOM SORT ORDER ====
rows_sorted = sorted(
    rows,
    key=lambda r: (
        r["Step_num"],   # Step first
        r["Pair1"],      # then pair’s first number
        r["Pair2"],      # then pair’s second number (1–4)
        r["RollerSet_num"]  # lastly rollerset (if needed)
    )
)

# ==== SAVE OUTPUT ====
fieldnames = [
    "Sequence","Pair","RollerSet","Step",
    "Prev","Current","Steps_Moved","Actual_Move"
]

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows_sorted:
        writer.writerow({field: r[field] for field in fieldnames})

print("✔ CUSTOM SORT COMPLETED → saved as:", OUTPUT_CSV)
