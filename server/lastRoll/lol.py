import numpy as np
import pandas as pd

# Canonical prize order
prizes = [100, 200, 500, 1000, 2000, 5000]

# Load counts with the first column as index
T = pd.read_csv("prize_transition_counts.csv", index_col=0)

# Normalize index/columns to integers (strip whitespace, handle strings)
def normalize_labels(idx):
    out = []
    for x in idx:
        s = str(x).strip()
        # allow '100', ' 500 ', etc.
        if s.isdigit():
            out.append(int(s))
        else:
            # keep as-is (will get dropped on reindex)
            out.append(s)
    return out

T.index = normalize_labels(T.index)
T.columns = normalize_labels(T.columns)

# Convert all cells to numeric
T = T.apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)

# Ensure exact order and presence of all prizes; fill missing with 0
T = T.reindex(index=prizes, columns=prizes, fill_value=0)

# Sanity: show what we have now
print("Index:", T.index.tolist())
print("Columns:", T.columns.tolist())

# Row-normalized transition probabilities
row_tot = T.sum(axis=1).replace(0, np.nan)
P = T.div(row_tot, axis=0)

print("\nP(next=5000 | prev):")
print((P[5000] * 100).round(2))

# Unconditional next-state distribution
col_tot = T.sum(axis=0)
uncond_next = (col_tot / col_tot.sum() * 100).round(2)
print("\nUnconditional next-state %:")
print(uncond_next)

# k-step probability of being at 5000 after k transitions (Markov)
def k_step_prob_to_5000(P_df, k, states=prizes):
    M = P_df.values
    Mk = np.linalg.matrix_power(M, k)
    return pd.Series(Mk[:, states.index(5000)], index=states)

for k in [1, 3, 5, 10]:
    print(f"\nP(at 5000 in {k} step(s)) by prev prize (%):")
    print((k_step_prob_to_5000(P, k) * 100).round(2))