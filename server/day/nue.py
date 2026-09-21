import pandas as pd
import numpy as np

# Config
CSV = "filtered_prizes.csv"
DATE_COL = "date"  # first column
WINDOW_DAYS = 180  # rolling training window
ALPHA = 1.0        # Laplace smoothing
TOPK = 50          # evaluate top-K hit rate

# Load and reshape to long (sparse)
df = pd.read_csv(CSV)
if DATE_COL not in df.columns:
    DATE_COL = df.columns[0]
bins = df.columns[1:]

df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce", dayfirst=True)
df = df.dropna(subset=[DATE_COL]).sort_values(DATE_COL)

long = df.melt(id_vars=[DATE_COL], var_name="bin", value_name="count")
long["count"] = pd.to_numeric(long["count"], errors="coerce").fillna(0).astype(int)
long = long[long["count"] > 0]

# Precompute per-date data
dates = np.array(sorted(long[DATE_COL].unique()))
date_to_idx = {d:i for i,d in enumerate(dates)}

# Build per-date totals and sparse rows
per_date_tot = long.groupby(DATE_COL)["count"].sum().reindex(dates, fill_value=0).to_numpy()
# Map bins to indices
bin_list = list(bins)
bin_to_idx = {b:i for i,b in enumerate(bin_list)}
K = len(bin_list)

# Sparse daily bin->count dictionaries
daily = [dict() for _ in range(len(dates))]
for d, b, c in long[[DATE_COL, "bin", "count"]].itertuples(index=False):
    i = date_to_idx[d]
    j = bin_to_idx[b]
    daily[i][j] = daily[i].get(j, 0) + c

# Rolling counts over window
train_counts = np.zeros(K, dtype=np.float64)
from collections import deque
window = deque()
train_total = 0.0

def add_day(idx):
    global train_total
    for j, c in daily[idx].items():
        train_counts[j] += c
        train_total += c
    window.append(idx)

def drop_day(idx):
    global train_total
    for j, c in daily[idx].items():
        train_counts[j] -= c
        train_total -= c

start = 0
logloss_sum = 0.0
draws_sum = 0
topk_hits = 0
topk_draws = 0

for t in range(len(dates)):
    # advance start to maintain WINDOW_DAYS window
    while start < t and (dates[t] - dates[start]).days > WINDOW_DAYS:
        drop_day(start)
        start += 1
    # ensure window populated (exclude current test day)
    # we add all days from previous loop; if empty, skip evaluation
    if not window:
        # bootstrap by adding past days strictly before t
        for i in range(start, t):
            add_day(i)

    if train_total == 0:
        # no training exposure yet; skip this test day
        add_day(t)
        continue

    # Predict with smoothing
    p = (train_counts + ALPHA) / (train_total + ALPHA * K)

    # Evaluate on test day t
    if per_date_tot[t] > 0:
        # log loss (sum over counts): -sum c_b * log p_b
        ll = 0.0
        for j, c in daily[t].items():
            ll -= c * np.log(p[j])
        logloss_sum += ll
        draws_sum += per_date_tot[t]

        # top-K hit rate
        top_idx = np.argpartition(p, -TOPK)[-TOPK:]
        hits = sum(c for j, c in daily[t].items() if j in top_idx)
        topk_hits += hits
        topk_draws += per_date_tot[t]

    # slide window: add current day at the end (becomes part of training for future days)
    add_day(t)

# Results
uniform_ll_per_draw = np.log(K)  # log loss for uniform
model_ll_per_draw = logloss_sum / max(draws_sum, 1)
rel_gain = (uniform_ll_per_draw - model_ll_per_draw) / uniform_ll_per_draw * 100

print(f"Draws evaluated: {draws_sum}")
print(f"LogLoss per draw - model: {model_ll_per_draw:.6f}, uniform: {uniform_ll_per_draw:.6f}, rel. gain: {rel_gain:.3f}%")
print(f"Top-{TOPK} hit rate: {topk_hits/topk_draws*100:.3f}%  vs uniform expectation {TOPK/K*100:.3f}%")