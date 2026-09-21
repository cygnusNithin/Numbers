#!/usr/bin/env python3
import pandas as pd
import numpy as np
from io import StringIO

# ===========================
# LOAD 4-DIGIT RAW DATA CSV
# ===========================
raw_csv = r"fourDigit.csv"  # CHANGE IF NEEDED
df = pd.read_csv(raw_csv, header=0)

df = df.replace("nan", np.nan)
df = df.dropna(how="all")

def clean_val(x):
    try:
        return f"{int(x):04d}"
    except:
        return np.nan

df = df.map(clean_val)

# Convert column names (rollerset1 → 1)
df.columns = df.columns.map(lambda x: ''.join(filter(str.isdigit, x)))

# ===========================
# ROLLER SEQUENCE TABLE
# ===========================
ROLLER_TABLE = """
number_id,roll_position,sequence
1,1,7|6|8|5|9|0|3|1|2|4
1,2,7|9|2|5|1|6|3|8|0|4
1,3,7|8|9|0|1|2|3|4|5|6
1,4,7|4|1|8|6|3|5|0|2|9
2,1,7|2|4|6|9|0|1|3|5|8
2,2,7|3|8|2|0|1|9|5|6|4
2,3,7|4|1|8|6|3|5|0|2|9
2,4,7|8|9|0|1|2|3|4|5|6
3,1,7|5|3|1|0|8|6|4|2|9
3,2,7|2|4|6|9|0|1|3|5|8
3,3,7|3|8|2|0|1|9|5|6|4
3,4,7|4|1|8|6|3|5|0|2|9
4,1,7|2|4|6|9|0|1|3|5|8
4,2,7|3|8|2|0|1|9|5|6|4
4,3,7|4|1|8|6|3|5|0|2|9
4,4,7|9|2|5|1|6|3|8|0|4
5,1,7|2|4|6|9|0|1|3|5|8
5,2,7|3|8|2|0|1|9|5|6|4
5,3,7|6|8|5|9|0|3|1|2|4
5,4,7|8|9|0|1|2|3|4|5|6
6,1,7|2|4|6|9|0|1|3|5|8
6,2,7|3|8|2|0|1|9|5|6|4
6,3,7|9|2|5|1|6|3|8|0|4
6,4,7|4|1|8|6|3|5|0|2|9
7,1,7|3|8|2|0|1|9|6|5|4
7,2,7|8|9|0|1|2|3|4|5|6
7,3,7|5|3|1|0|8|6|4|2|9
7,4,7|5|3|1|0|8|6|4|2|9
8,1,7|5|1|9|6|4|2|8|3|0
8,2,7|5|9|1|3|6|8|4|0|2
8,3,7|9|2|5|1|6|3|8|0|4
8,4,7|6|8|5|9|0|3|1|2|4
9,1,7|9|2|5|1|6|3|8|0|4
9,2,7|5|1|9|6|4|2|8|3|0
9,3,7|5|9|1|3|6|8|4|0|2
9,4,7|8|9|0|1|2|3|4|5|6
10,1,7|5|1|9|6|4|2|8|3|0
10,2,7|6|5|4|3|2|1|0|9|8
10,3,7|8|9|0|1|2|3|4|5|6
10,4,7|6|8|5|9|0|3|1|2|4
11,1,7|5|1|9|6|4|2|8|3|0
11,2,7|5|9|1|3|6|8|4|0|2
11,3,7|9|2|5|1|6|3|8|0|4
11,4,7|4|1|8|6|3|5|0|2|9
12,1,7|5|1|9|6|4|2|8|3|0
12,2,7|5|9|1|3|6|8|4|0|2
12,3,7|6|5|4|3|2|1|0|9|8
12,4,7|8|9|0|1|2|3|4|5|6
13,1,7|5|9|1|3|6|8|4|0|2
13,2,7|6|5|4|3|2|1|0|9|8
13,3,7|5|1|9|6|4|2|8|3|0
13,4,7|5|3|1|0|8|6|4|2|9
14,1,7|6|5|4|3|2|1|0|9|8
14,2,7|5|3|1|0|8|6|4|2|9
14,3,7|5|1|9|6|4|2|8|3|0
14,4,7|4|1|8|6|3|5|0|2|9
15,1,7|6|8|5|9|0|3|1|2|4
15,2,7|6|5|4|3|2|1|0|9|8
15,3,7|4|1|3|6|0|8|9|5|2
15,4,7|5|9|1|3|6|8|4|0|2
16,1,7|5|9|1|3|6|8|4|0|2
16,2,7|5|3|1|0|8|6|4|2|9
16,3,7|2|4|6|9|0|1|3|5|8
16,4,7|3|8|2|0|1|9|5|6|4
17,1,7|8|9|0|1|2|3|4|5|6
17,2,7|6|8|5|9|0|3|1|2|4
17,3,7|6|5|4|3|2|1|0|9|8
17,4,7|5|3|1|0|8|6|4|2|9
18,1,7|6|8|5|9|0|3|1|2|4
18,2,7|5|3|1|0|8|6|4|2|9
18,3,7|2|4|6|9|0|1|3|5|8
18,4,7|3|8|2|0|1|9|5|6|4
"""
roller_df = pd.read_csv(StringIO(ROLLER_TABLE))
roller_df["sequence"] = roller_df["sequence"].apply(lambda x: list(map(int, x.split("|"))))

# ===========================
# MOVEMENT CALCULATION (4 DIGITS)
# ===========================
rows = []

for set_id in df.columns:
    values = df[set_id].values

    for i in range(len(values) - 1):
        prev = values[i]
        curr = values[i + 1]

        if pd.isna(prev) or pd.isna(curr):
            continue

        prev = str(prev)
        curr = str(curr)

        step_digits = []  # store 4 movements

        for pos in range(4):  # pos 0,1,2,3
            d_prev = int(prev[pos])
            d_curr = int(curr[pos])

            seq_row = roller_df[(roller_df.number_id == int(set_id)) &
                                (roller_df.roll_position == pos + 1)]

            if seq_row.empty:
                step_digits.append("X")  # missing data
                continue

            seq = seq_row.sequence.values[0]
            p_idx = seq.index(d_prev)
            c_idx = seq.index(d_curr)
            diff = (c_idx - p_idx) % len(seq)

            step_digits.append(str(diff))

        rows.append([f"rollerset{set_id}", i + 1, prev, curr, "|".join(step_digits)])

# ===========================
# SAVE OUTPUT
# ===========================
out = pd.DataFrame(rows, columns=["RollerSet", "Step", "Prev", "Current", "Steps_Moved"])
out.to_csv("movement_analysis.csv", index=False)

print("\n🎉 DONE! File saved → movement_analysis.csv\n")
