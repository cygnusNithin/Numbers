import csv
import ast

movement_file = "movement_analysis.csv"
sequence_file = "similar_sequence_groups.csv"

# ========================
# Load movement data
# ========================
movements = []
with open(movement_file, newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        movements.append(row)

# ========================
# Load sequence maps
# ========================
seq_map = {}
with open(sequence_file, newline='') as f:
    reader = csv.reader(f)
    next(reader)  # skip header
    for seq, pairs in reader:
        seq_map[seq] = ast.literal_eval(pairs)

# ========================
# Build output for ALL pairs
# ========================
output = []

for seq, pairs in seq_map.items():
    for rs, col in pairs:
        rs_name = f"rollerset{rs}"
        for m in movements:
            if m["RollerSet"] == rs_name:

                # Full steps list (example: "0|4|7|3")
                full_steps = m["Steps_Moved"]

                # Selecting only the current column move
                # col is 1-based index, so use (col - 1)
                try:
                    actual = full_steps.split("|")[col-1]
                except:
                    actual = ""

                output.append({
                    "Sequence": seq,
                    "Pair": f"({rs},{col})",
                    "RollerSet": m["RollerSet"],
                    "Step": m["Step"],
                    "Prev": m["Prev"],
                    "Current": m["Current"],
                    "Steps_Moved": full_steps,
                    "Actual_Move": actual
                })

# ========================
# Save output
# ========================
out_file = "sequence_movement_full_map.csv"
with open(out_file, "w", newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output[0].keys())
    writer.writeheader()
    writer.writerows(output)

print("Done -> sequence_movement_full_map.csv created")
