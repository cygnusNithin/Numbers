# save as roller_row_sequence_analysis.py and run with python3
import re
from collections import Counter, defaultdict
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import chi2_contingency

# Paste your roller lines here (the block you provided). Keep the same format.
ROLLER_TEXT = """
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

# -------------------------
# Parse the block into rows
lines = [ln.strip() for ln in ROLLER_TEXT.strip().splitlines() if ln.strip()]
rows = []
for ln in lines:
    try:
        num_id, roll_pos, seq = ln.split(",", 2)
        num_id = int(num_id)
        roll_pos = int(roll_pos)
        seq_norm = "|".join(x.strip() for x in seq.split("|"))
        rows.append({"number_id": num_id, "roll_pos": roll_pos, "sequence": seq_norm})
    except Exception as e:
        print("Skipping line:", ln, "err:", e)

df = pd.DataFrame(rows)

# map number_id -> row_index (1..6) and column_index (1..3)
# you told: 1-6 in first column, 7-12 in second column, 13-18 in third column
# Row index = number_id % 6 (mapped to 1..6)
def number_to_row_col(n):
    # n in 1..18
    col = ( (n-1)//6 ) + 1      # 1..3
    row = ((n-1) % 6) + 1       # 1..6
    return row, col

df["row_index"], df["col_index"] = zip(*df["number_id"].map(number_to_row_col))

# canonical sequence id (group identical strings)
seq_counter = Counter(df["sequence"])
# give each distinct sequence an id
seq_map = {s: f"seq_{i+1:02d}" for i, s in enumerate(sorted(seq_counter.keys(), key=lambda x: (-seq_counter[x], x)))}
df["seq_id"] = df["sequence"].map(seq_map)

print("Distinct sequences:", len(seq_map))
print(seq_counter.most_common())

# frequency by row_index vs seq_id
pivot = pd.crosstab(df["row_index"], df["seq_id"])
print("\nContingency table (rows=RowIndex 1..6, columns=sequence groups):")
print(pivot)

# chi-square test
chi2, p, dof, expected = chi2_contingency(pivot)
print(f"\nChi-square test: chi2={chi2:.2f}, p-value={p:.6f}, dof={dof}")

# effect size: Cramer's V
n = pivot.values.sum()
phi2 = chi2 / n
r, k = pivot.shape
cramer_v = np.sqrt(phi2 / min(r-1, k-1))
print(f"Cramer's V = {cramer_v:.4f}  (0.1 small, 0.3 medium, 0.5 large)")

# show heatmap of normalized frequencies by row
pivot_norm = pivot.div(pivot.sum(axis=1), axis=0).fillna(0)
plt.figure(figsize=(12, 6))
sns.heatmap(pivot_norm, annot=True, fmt=".2f", cmap="Blues")
plt.title("Normalized frequency of sequence groups by RowIndex (1..6)")
plt.xlabel("sequence id")
plt.ylabel("row index (1..6)")
plt.tight_layout()
plt.show()

# also check roll_pos (1..4) association similarly
pivot_pos = pd.crosstab(df["roll_pos"], df["seq_id"])
chi2p, pp, dofp, exp = chi2_contingency(pivot_pos)
n2 = pivot_pos.values.sum()
cram_v_pos = np.sqrt((chi2p / n2) / min(pivot_pos.shape[0]-1, pivot_pos.shape[1]-1))
print(f"\nroll_pos chi2={chi2p:.2f}, p={pp:.6f}, Cramer's V={cram_v_pos:.4f}")

# Print a grouped listing to inspect (which seq appears in each RowIndex)
grouped = df.groupby(["row_index", "seq_id"]).size().unstack(fill_value=0)
print("\nGrouped counts (row_index x seq_id):\n", grouped)

# Print mapping seq_id -> sample roller positions
seq_samples = defaultdict(list)
for _, r in df.iterrows():
    seq_samples[r["seq_id"]].append((r["number_id"], r["roll_pos"]))
print("\nExample mapping seq_id -> rollers (number_id,roll_pos):")
for sid, lst in seq_samples.items():
    print(sid, ":", lst)

# Save outputs for further inspection
df.to_csv("roller_sequences_normalized.csv", index=False)
pivot.to_csv("roller_sequence_contingency_by_row.csv")
pivot_pos.to_csv("roller_sequence_contingency_by_rollpos.csv")
print("\nSaved CSVs: roller_sequences_normalized.csv, roller_sequence_contingency_by_row.csv, roller_sequence_contingency_by_rollpos.csv")
