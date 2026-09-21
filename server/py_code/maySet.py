import pandas as pd
from tqdm import tqdm

# -----------------------
# CONFIG (filenames)
# -----------------------
FULL_ROLL_CSV = "fullRoll.csv"      # 72 roll sequences (number_id,roll_position,sequence)
FIRST_CSV = "firstSet.csv"          # columns: roller,pos1,pos2,pos3,pos4
SECOND_CSV = "secondSet.csv"
THIRD_CSV = "thirdSet.csv"
FOURTH_CSV = "fourthSet.csv"        # new: add your 4th observed set
OUT_COMPARISON = "roller_set_comparison_no_decimals.csv"
OUT_PREDICTED_5 = "predicted_set5.csv"

# -----------------------
# Helpers
# -----------------------
def load_roll_sequences(full_roll_csv=FULL_ROLL_CSV):
    """Load sequences into dict: rollers[number_id][pos] -> list of ints (sequence order)"""
    df = pd.read_csv(full_roll_csv, dtype={"number_id": int, "roll_position": int, "sequence": str})
    rollers = {}
    for _, row in df.iterrows():
        nid = int(row["number_id"])
        pos = int(row["roll_position"])
        seq = [int(x) for x in row["sequence"].split("|")]
        rollers.setdefault(nid, {})[pos] = seq
    return rollers

def read_set_csv(filename):
    """Expect columns: roller,pos1,pos2,pos3,pos4 (roller 1..18) -> returns dict roller->list of 4 ints"""
    df = pd.read_csv(filename, dtype=str)
    out = {}
    for _, r in df.iterrows():
        roller = int(r[df.columns[0]])  # first column = roller number
        # take next 4 columns as digits (allow missing leading zeros)
        digits = []
        for c in df.columns[1:5]:
            val = str(r[c]).strip()
            if val == "nan" or val == "" or pd.isna(val):
                digits.append(None)
            else:
                # keep digits as int 0-9
                digits.append(int(val) if val.isdigit() else None)
        out[roller] = digits
    return out

def find_steps(d1, d2, seq):
    """Return integer steps to move d1 -> d2 along seq (0..len-1). If missing return None."""
    if d1 is None or d2 is None: 
        return None
    if d1 not in seq or d2 not in seq:
        return None
    return (seq.index(d2) - seq.index(d1)) % len(seq)

def apply_steps(d, steps, seq):
    if d is None or steps is None: 
        return None
    if d not in seq:
        return None
    return seq[(seq.index(d) + steps) % len(seq)]

# -----------------------
# Main analysis
# -----------------------
if __name__ == "__main__":
    rollers = load_roll_sequences(FULL_ROLL_CSV)
    set1 = read_set_csv(FIRST_CSV)
    set2 = read_set_csv(SECOND_CSV)
    set3 = read_set_csv(THIRD_CSV)
    set4 = read_set_csv(FOURTH_CSV)

    rows = []
    predicted_set5_digits_by_roller = {}

    print("🔄 Comparing sets and computing integer step deltas...")
    for rid in tqdm(range(1, 19), desc="Rollers (1..18)"):
        d1s = set1.get(rid, [None, None, None, None])
        d2s = set2.get(rid, [None, None, None, None])
        d3s = set3.get(rid, [None, None, None, None])
        d4s = set4.get(rid, [None, None, None, None])

        predicted5 = []
        for pos in range(4):
            seq = rollers[rid][pos+1]  # pos indices are 1..4 in rollers dict
            d1 = d1s[pos]
            d2 = d2s[pos]
            d3 = d3s[pos]
            d4 = d4s[pos]

            steps_12 = find_steps(d1, d2, seq)
            steps_23 = find_steps(d2, d3, seq)
            steps_34 = find_steps(d3, d4, seq)

            # Predict set5 by applying steps_34 to d4
            pred5_digit = apply_steps(d4, steps_34, seq)

            rows.append({
                "roller": rid,
                "position": pos+1,
                "set1_digit": "" if d1 is None else int(d1),
                "set2_digit": "" if d2 is None else int(d2),
                "set3_digit": "" if d3 is None else int(d3),
                "set4_digit": "" if d4 is None else int(d4),
                # integer step deltas (no decimals)
                "steps_1to2": "" if steps_12 is None else int(steps_12),
                "steps_2to3": "" if steps_23 is None else int(steps_23),
                "steps_3to4": "" if steps_34 is None else int(steps_34),
                "predicted_set5_digit": "" if pred5_digit is None else int(pred5_digit),
                "stable_12_23": (steps_12 == steps_23) if (steps_12 is not None and steps_23 is not None) else "",
                "stable_23_34": (steps_23 == steps_34) if (steps_23 is not None and steps_34 is not None) else ""
            })
            predicted5.append("" if pred5_digit is None else str(pred5_digit))

        predicted_set5_digits_by_roller[rid] = predicted5

    # Save per-digit analysis CSV (no decimals, ints only)
    out_df = pd.DataFrame(rows)
    # Format per-roller number strings padded with zeros for readability:
    # Also produce per-roller summary rows
    summaries = []
    for rid in range(1,19):
        s1 = set1.get(rid, ["","","",""])
        s2 = set2.get(rid, ["","","",""])
        s3 = set3.get(rid, ["","","",""])
        s4 = set4.get(rid, ["","","",""])
        p5 = predicted_set5_digits_by_roller[rid]
        # pad digits as strings
        def join_digits(arr):
            return "".join(str(x) if x != "" else "?" for x in arr)
        summaries.append({
            "roller": rid,
            "set1_number": join_digits(s1),
            "set2_number": join_digits(s2),
            "set3_number": join_digits(s3),
            "set4_number": join_digits(s4),
            "predicted_set5_number": join_digits(p5)
        })
    sum_df = pd.DataFrame(summaries)

    # Save both files
    out_df.to_csv(OUT_COMPARISON, index=False)
    sum_df.to_csv(OUT_PREDICTED_5, index=False)

    print("✅ Saved detailed per-digit comparison to", OUT_COMPARISON)
    print("✅ Saved predicted full set5 per-roller to", OUT_PREDICTED_5)
