import pandas as pd

# ===============================
# CONFIGURATION
# ===============================
TRIES_FILE = "mainPrizes.csv"       # e.g. columns: try,number
ROLLER_FILE = "sixRoll.csv"   # e.g. number_id,sequence
OUTPUT_FILE = "try_differences.csv"

# ===============================
# LOAD ROLLER SEQUENCES
# ===============================
def load_rollers(csv_path):
    df = pd.read_csv(csv_path, dtype=str)
    rollers = {}
    for _, row in df.iterrows():
        rid = int(row["number_id"])
        seq = [int(x) for x in row["sequence"].split("|") if x.strip().isdigit()]
        rollers[rid] = seq
    return rollers

def roller_gap(seq, start_digit, end_digit):
    """Steps forward from start_digit to end_digit in roller sequence."""
    if start_digit not in seq or end_digit not in seq:
        return None
    i1, i2 = seq.index(start_digit), seq.index(end_digit)
    return (i2 - i1) % len(seq)

# ===============================
# MAIN
# ===============================
def main():
    rollers = load_rollers(ROLLER_FILE)
    print(f"✅ Loaded {len(rollers)} roller sequences")

    tries_df = pd.read_csv(TRIES_FILE, dtype=str)
    tries_df["try"] = tries_df["try"].astype(int)
    tries_df.sort_values("try", inplace=True)

    all_rows = []

    for i in range(len(tries_df) - 1):
        try_a = tries_df.iloc[i]
        try_b = tries_df.iloc[i + 1]
        num_a = try_a["number"].zfill(6)
        num_b = try_b["number"].zfill(6)

        for roller_id in range(1, 7):
            seq = rollers.get(roller_id)
            if not seq:
                continue

            d1 = int(num_a[roller_id - 1])
            d2 = int(num_b[roller_id - 1])
            gap = roller_gap(seq, d1, d2)

            all_rows.append({
                "from_try": try_a["try"],
                "to_try": try_b["try"],
                "from_number": num_a,
                "to_number": num_b,
                "roller_id": roller_id,
                "digit_from": d1,
                "digit_to": d2,
                "gap_steps": gap
            })

    # Create output CSV
    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"✅ Saved → {OUTPUT_FILE}")
    print(df.head(12))

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    main()
