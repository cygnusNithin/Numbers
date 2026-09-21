import csv
import re
from collections import defaultdict

INPUT_CSV = "sorted_output.csv"
OUTPUT_CSV = "step_wide_output.csv"

def parse_pair(pair_str):
    # pair_str example: "(3,2)"
    nums = re.findall(r'\d+', pair_str)
    return tuple(map(int, nums))  # -> (3,2)

# Dictionary: step → { pair → actual_move }
step_map = defaultdict(dict)
pair_set = set()

# Read input CSV
with open(INPUT_CSV, "r", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        step = int(row["Step"])
        pair = parse_pair(row["Pair"])
        actual_move = row["Actual_Move"].strip()

        pair_set.add(pair)
        step_map[step][pair] = actual_move

# Sort pairs in natural ascending order (1,1), (1,2) ... (X,Y)
sorted_pairs = sorted(pair_set)

# Create header labels (strings)
header_labels = ["Step"] + [f"{p}" for p in sorted_pairs]

# Determine max width for each column including header
col_widths = [len(h) for h in header_labels]

for step in sorted(step_map.keys()):
    col_widths[0] = max(col_widths[0], len(str(step)))
    for idx, p in enumerate(sorted_pairs, start=1):
        val = step_map[step].get(p, "")
        col_widths[idx] = max(col_widths[idx], len(str(val)))

# Function to pad text to fixed width (left align)
def pad(text, width):
    return str(text).ljust(width)

# Write to pipe-delimited CSV with padded fields
with open(OUTPUT_CSV, "w", newline="") as f:
    # Manually write header with padding and pipe delimiter
    header_line = " | ".join(pad(h, w) for h, w in zip(header_labels, col_widths))
    f.write(header_line + "\n")

    # Write rows
    for step in sorted(step_map.keys()):
        row_items = [pad(step, col_widths[0])]
        for idx, p in enumerate(sorted_pairs, start=1):
            val = step_map[step].get(p, "")
            row_items.append(pad(val, col_widths[idx]))
        f.write(" | ".join(row_items) + "\n")

print("Pipe-delimited CSV with padded columns created:", OUTPUT_CSV)
