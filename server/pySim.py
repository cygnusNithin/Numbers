import csv
import math
from pathlib import Path

# =======================
# CONFIGURATION
# =======================
ROLL_DURATION_SEC = 2.4          # time for one roll/press
DIGIT_HEIGHT_CM = 7              # height of one digit
GAP_CM = 1                       # gap between digits
DIGITS_PER_ROLLER = 10
FORWARD = True                   # True = clockwise

# File paths
ROLLERS_FILE = "sixRoll.csv"     # contains roller_id,sequence (or number_id,sequence)
MAIN_FILE = "mainPrizes.csv"     # contains try,number

# =======================
# CALCULATED CONSTANTS
# =======================
segment_cm = DIGIT_HEIGHT_CM + GAP_CM
circumference_cm = DIGITS_PER_ROLLER * segment_cm
diameter_cm = circumference_cm / math.pi
radius_cm = diameter_cm / 2
DEG_PER_DIGIT = 360 / DIGITS_PER_ROLLER

print(f"[INFO] Roller circumference: {circumference_cm:.2f} cm | Diameter: {diameter_cm:.2f} cm")

# =======================
# LOAD ROLLER PATTERNS
# =======================
def parse_sequence(seq_str):
    return [int(x) for x in seq_str.strip().split("|")]

roller_patterns = {}
with open(ROLLERS_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rid = int(row.get("roller_id") or row.get("number_id"))
        seq = parse_sequence(row["sequence"])
        roller_patterns[rid] = seq

# =======================
# LOAD MAIN PRIZE NUMBERS
# =======================
main_prizes = []
with open(MAIN_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        main_prizes.append((int(row["try"]), row["number"].strip()))

# =======================
# SIMULATION FUNCTIONS
# =======================
def get_digit_index(roller_id, digit):
    seq = roller_patterns[roller_id]
    return seq.index(int(digit))

def rotation_distance(a, b, total_positions):
    """Return forward rotation distance (0–total_positions-1)."""
    diff = (b - a) % total_positions
    return diff if FORWARD else (-diff) % total_positions

def rotation_angle(a, b, total_positions):
    return rotation_distance(a, b, total_positions) * (360 / total_positions)

# =======================
# SIMULATION LOOP
# =======================
results = []
prev_number = None
for try_num, number_str in main_prizes:
    if prev_number:
        prev_digits = list(prev_number)
        curr_digits = list(number_str)

        for rid in range(1, 7):
            if rid <= len(curr_digits):
                a_digit = prev_digits[rid - 1]
                b_digit = curr_digits[rid - 1]

                total_pos = len(roller_patterns[rid])
                a_idx = get_digit_index(rid, a_digit)
                b_idx = get_digit_index(rid, b_digit)
                dist = rotation_distance(a_idx, b_idx, total_pos)
                angle = rotation_angle(a_idx, b_idx, total_pos)
                time_per_try = ROLL_DURATION_SEC
                rpm = (60 / time_per_try) * (dist / total_pos)

                results.append({
                    "try": try_num,
                    "roller_id": rid,
                    "from": a_digit,
                    "to": b_digit,
                    "distance_steps": dist,
                    "angle_deg": angle,
                    "rpm": round(rpm, 2)
                })
    prev_number = number_str

# =======================
# SAVE RESULTS
# =======================
detail_path = Path("roller_sim_results.csv")
with open(detail_path, "w", newline="", encoding="utf-8") as f:
    fieldnames = ["try", "roller_id", "from", "to", "distance_steps", "angle_deg", "rpm"]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

# Summary per roller
summary = {}
for r in results:
    rid = r["roller_id"]
    summary.setdefault(rid, []).append(r["rpm"])

summary_path = Path("roller_summary.csv")
with open(summary_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["roller_id", "avg_rpm", "max_rpm", "min_rpm"])
    for rid, rpms in summary.items():
        writer.writerow([rid, round(sum(rpms)/len(rpms), 2), max(rpms), min(rpms)])

print(f"\n✅ Simulation complete!")
print(f"→ Detailed output: {detail_path.resolve()}")
print(f"→ Summary output:  {summary_path.resolve()}")
