import pandas as pd
import numpy as np
import statsmodels.api as sm
import statsmodels.formula.api as smf

NUMBERS_CSV = "filtered_prizes_5000_numbers.csv"
DATE_COL = "date"
WEIGHT_NUM_COUNTS = False  # True if cells like "NNNN:count" and you want to use counts

# Load and aggregate per-number totals (same as before)
df = pd.read_csv(NUMBERS_CSV, low_memory=False)
if DATE_COL not in df.columns:
    DATE_COL = df.columns[0]
range_cols = [c for c in df.columns if c != DATE_COL]

def parse_cell(cell):
    out = {}
    if not isinstance(cell, str) or not cell:
        return out
    for tok in cell.split("|"):
        tok = tok.strip()
        if not tok: continue
        if ":" in tok:
            num, cnt = tok.split(":", 1)
            try: cnt = float(cnt)
            except: cnt = 1.0
        else:
            num, cnt = tok, 1.0
        num = num.strip()
        if not num.isdigit(): continue
        out[num] = out.get(num, 0.0) + (cnt if WEIGHT_NUM_COUNTS else 1.0)
    return out

counts = {}
for _, row in df.iterrows():
    for c in range_cols:
        d = parse_cell(row[c])
        for n, v in d.items():
            n4 = n.zfill(4)
            counts[n4] = counts.get(n4, 0.0) + v

all_nums = [f"{i:04d}" for i in range(10000)]
obs = pd.DataFrame({"number": all_nums})
obs["y"] = obs["number"].map(counts).fillna(0.0)

# Digits
obs["th"] = obs["number"].str[0].astype(int)
obs["h"]  = obs["number"].str[1].astype(int)
obs["t"]  = obs["number"].str[2].astype(int)
obs["o"]  = obs["number"].str[3].astype(int)

# Fit Poisson GLMs
m_ind = smf.glm("y ~ C(th) + C(h) + C(t) + C(o)", data=obs, family=sm.families.Poisson()).fit()
m_int = smf.glm(
    "y ~ C(th) + C(h) + C(t) + C(o)"
    " + C(th):C(h) + C(th):C(t) + C(th):C(o)"
    " + C(h):C(t)  + C(h):C(o)  + C(t):C(o)",
    data=obs, family=sm.families.Poisson()
).fit()

def explain(m):
    dev_null = m.null_deviance
    dev_res  = m.deviance
    r2 = (dev_null - dev_res) / dev_null * 100 if dev_null > 0 else 0
    return r2

print(f"Digit-only deviance explained: {explain(m_ind):.2f}%")
print(f"Digit+pairwise deviance explained: {explain(m_int):.2f}%")

# Coefficients are your "equation" parameters; use m_int.params to see them.