import numpy as np
import pandas as pd

# =======================
# CONFIG
# =======================
COUNTS_CSV  = "filtered_prizes_5000_counts.csv"
NUMBERS_CSV = "filtered_prizes_5000_numbers.csv"
DATE_COL = "date"

# Range model params (same style as before)
TAU_DAYS   = 120      # exponential decay time constant for ranges
ALPHA      = 5.0      # Laplace smoothing
LAMBDA     = 0.90     # uniform mix
GAMMA      = 0.50     # prior strength
PRIOR_TYPE = "digit"  # "digit" or "range"

# Number mining params
TOP_RANGES_FOR_NUMBERS = 25  # how many ranges to mine
TOP_NUMBERS            = 12  # final number picks
TAU_DAYS_NUM           = 120 # decay for numbers
WEIGHT_NUM_COUNTS      = False  # if numbers CSV has NNNN:count, set True

# =======================
# LOAD COUNTS (RANGES)
# =======================
df = pd.read_csv(COUNTS_CSV, low_memory=False)
if DATE_COL not in df.columns:
    DATE_COL = df.columns[0]
range_cols = list(df.columns[1:])

df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce", dayfirst=True)
df = df.dropna(subset=[DATE_COL]).sort_values(DATE_COL).reset_index(drop=True)
df[range_cols] = df[range_cols].apply(pd.to_numeric, errors="coerce").fillna(0).astype(float)

dates = df[DATE_COL].to_numpy()
X = df[range_cols].to_numpy(dtype=np.float64)
K = X.shape[1]

# =======================
# BUILD PRIORS (digit or per-range)
# =======================
counts_by_range = X.sum(axis=0)
starts = np.array([int(c.split('-')[0]) for c in range_cols])
thousands = starts // 1000
decade    = (starts % 100) // 10

# Digit prior (thousands × decade), normalized to mean 1
th_share = pd.Series(counts_by_range).groupby(thousands).sum()
th_share = (th_share / th_share.sum()).reindex(range(10), fill_value=1/10)
th_prior = (th_share / 0.10).to_numpy()

dec_share = pd.Series(counts_by_range).groupby(decade).sum()
dec_share = (dec_share / dec_share.sum()).reindex(range(10), fill_value=1/10)
dec_prior = (dec_share / 0.10).to_numpy()

digit_prior = (th_prior[thousands] * dec_prior[decade])
digit_prior = digit_prior / digit_prior.mean()

# Per-range prior (long-run per-range share), normalized to mean 1
range_prior = counts_by_range / max(counts_by_range.sum(), 1e-12)
range_prior = (range_prior / range_prior.mean())

priors = (range_prior if PRIOR_TYPE == "range" else digit_prior).astype(float)
priors[~np.isfinite(priors)] = 1.0
priors[priors <= 0] = 1.0

# =======================
# COMPUTE p (range probabilities) — exp-decay + smoothing + prior + mix
# =======================
DECAY = np.exp(-1.0 / float(TAU_DAYS))
train = np.zeros(K, dtype=float)

# Use day numbers to handle gaps robustly
dates_day = dates.astype('datetime64[D]').astype('int64')
for t in range(len(dates)):
    dgap = 1 if t == 0 else int(max(1, dates_day[t] - dates_day[t-1]))
    train *= (DECAY ** dgap)
    train += X[t]  # add today's counts

train_total = train.sum()
if train_total > 0:
    p_base = (train + ALPHA) / (train_total + ALPHA * K)
else:
    p_base = np.full(K, 1.0 / K, dtype=float)

p_adj = p_base * (priors ** GAMMA)
p_adj_sum = p_adj.sum()
p_adj = p_adj / p_adj_sum if p_adj_sum > 0 else np.full(K, 1.0 / K)

p = (1 - LAMBDA) * (1.0 / K) + LAMBDA * p_adj

# Top ranges to mine numbers from
idx = np.argpartition(p, -TOP_RANGES_FOR_NUMBERS)[-TOP_RANGES_FOR_NUMBERS:]
top_ranges = [range_cols[i] for i in np.sort(idx)]
print("Top ranges to mine numbers from:")
print(", ".join(top_ranges))

# =======================
# LOAD NUMBERS CSV AND MINE TOP NUMBERS
# =======================
usecols = [DATE_COL] + top_ranges
dfn = pd.read_csv(NUMBERS_CSV, usecols=usecols, low_memory=False)
dfn[DATE_COL] = pd.to_datetime(dfn[DATE_COL], errors="coerce", dayfirst=True)
dfn = dfn.dropna(subset=[DATE_COL]).sort_values(DATE_COL).reset_index(drop=True)

DECAY_NUM = np.exp(-1.0 / float(TAU_DAYS_NUM))
scores = {}  # number -> score
prev_day = None

def add_numbers_from_cell(cell):
    if not isinstance(cell, str) or not cell:
        return
    for tok in cell.split("|"):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            num, cnt = tok.split(":", 1)
            try:
                cnt = float(cnt)
            except:
                cnt = 1.0
        else:
            num, cnt = tok, 1.0
        num = num.strip()
        if not num.isdigit():
            continue
        weight = cnt if WEIGHT_NUM_COUNTS else 1.0
        scores[num] = scores.get(num, 0.0) + weight

for i, row in dfn.iterrows():
    d = row[DATE_COL]
    if prev_day is None:
        prev_day = d
    else:
        # decay by exact day gap
        day_gap = max(1, int((d - prev_day) / np.timedelta64(1, "D")))
        if scores:
            factor = DECAY_NUM ** day_gap
            for k in list(scores.keys()):
                scores[k] *= factor
        prev_day = d

    # add numbers from selected ranges
    for col in top_ranges:
        add_numbers_from_cell(row[col])

# Top numbers
top_numbers = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:TOP_NUMBERS]
print(f"\nTop-{TOP_NUMBERS} candidate numbers (from top ranges, recency-weighted):")
for n, s in top_numbers:
    print(f"{n}  score={s:.3f}")

# Optional: save picks
# pd.DataFrame(top_numbers, columns=["number","score"]).to_csv("top_numbers_5000.csv", index=False)