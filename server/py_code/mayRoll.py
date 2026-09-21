import pandas as pd

# ============================
# Load full roller sequences
# ============================
def load_sequences(csv_file="fullRoll.csv"):
    df = pd.read_csv(csv_file)
    rollers = {}
    for _, row in df.iterrows():
        nid, pos, seq = int(row["number_id"]), int(row["roll_position"]), row["sequence"]
        nums = [int(x) for x in seq.split("|")]
        rollers.setdefault(nid, {})[pos] = nums
    return rollers

# ============================
# Find step movement
# ============================
def find_steps(d1, d2, seq):
    """Steps needed to move d1 → d2 along the sequence"""
    if d1 not in seq or d2 not in seq:
        return None
    i1, i2 = seq.index(d1), seq.index(d2)
    return (i2 - i1) % len(seq)

# ============================
# Apply steps to predict next digit
# ============================
def apply_steps(d, steps, seq):
    if d not in seq or steps is None:
        return None
    i = seq.index(d)
    return seq[(i + steps) % len(seq)]

# ============================
# Compare 18-number sets
# ============================
def predict_third_set(first_set, second_set, rollers):
    """
    first_set, second_set = lists of 18 numbers (each number is 4-digit)
    rollers = roller mapping from CSV
    """
    third_set = []
    moves_record = []

    for rid in range(1, 19):  # 18 rollers
        num1 = str(first_set[rid-1]).zfill(4)
        num2 = str(second_set[rid-1]).zfill(4)

        predicted_digits = []
        roller_moves = []

        for pos in range(1, 5):  # 4 positions
            seq = rollers[rid][pos]
            d1, d2 = int(num1[pos-1]), int(num2[pos-1])

            steps = find_steps(d1, d2, seq)
            d3 = apply_steps(d2, steps, seq)  # apply same steps again

            roller_moves.append((pos, d1, d2, steps, d3))
            predicted_digits.append(str(d3) if d3 is not None else "?")

        third_set.append(int("".join(predicted_digits)))
        moves_record.append((rid, roller_moves))

    return third_set, moves_record

# ============================
# Example Usage
# ============================
if __name__ == "__main__":
    rollers = load_sequences("fullRoll.csv")

    # Example sets of 18 numbers
    first_set = [1243, 1578, 8196, 8521, 6215, 1244, 7609, 7956, 5746,
                 3342, 3938, 9198, 6665, 7684, 1703, 1207, 9670, 1532]
    second_set = [8787, 9912, 5548, 0672, 9856, 7620, 2501, 9170, 9370,
                 8899, 6449, 2368, 2508, 5315, 8913, 1178, 3792, 1610]

    third_set, moves = predict_third_set(first_set, second_set, rollers)

    print("🔹 Predicted 3rd set of numbers:")
    print(third_set)

    print("\n🔍 Movement details (sample for roller 4):")
    for move in moves[3][1]:  # Roller 4
        pos, d1, d2, steps, d3 = move
        print(f"Pos {pos}: {d1} → {d2} (steps={steps}) → {d3}")
