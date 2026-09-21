import re, math
import pandas as pd
import numpy as np

fp = "filtered_prizes.csv"
df = pd.read_csv(fp)

date_col = df.columns[0]
range_cols = df.columns[1:]

# Total counts per range and overall
counts = df[range_cols].sum(numeric_only=True)
N = counts.sum()
K = len(range_cols)
p0 = 1.0 / K
mu = N * p0
sigma = math.sqrt(N * p0 * (1 - p0))

summary = (
    counts.rename("Total")
          .to_frame()
          .assign(Prob=lambda s: s["Total"] / N * 100.0,
                  Z=lambda s: (s["Total"] - mu) / sigma)
          .sort_values("Total", ascending=False)
)

print("Top 10 ranges by total:")
print(summary.head(10))

# Parse helpers
def parse_start(r):
    # r like '7520-7529'
    m = re.match(r"^(\d{4})-\d{4}$", r)
    return int(m.group(1)) if m else np.nan

meta = pd.DataFrame({"Range": range_cols})
meta["start"] = meta["Range"].apply(parse_start)
meta["thousands"] = (meta["start"] // 1000).astype("Int64")
meta["last2_decade"] = ((meta["start"] % 100) // 10).astype("Int64")  # 0..9 for 00-09,10-19,...,90-99

# Join counts/z back to meta
meta = meta.merge(summary.reset_index().rename(columns={"index":"Range"}), on="Range", how="left")

# 1) Overrepresentation by thousands block
by_thousands = (meta.groupby("thousands")["Total"].sum() / N * 100).sort_values(ascending=False)
print("\nShare by thousands block (% of total):")
print(by_thousands)

# 2) Bias by last-two-digit decade (00–09,..,90–99)
by_decade = (meta.groupby("last2_decade")["Total"].sum() / N * 100)
by_decade = by_decade.reindex(range(10), fill_value=0).rename(index=lambda d: f"{d*10:02d}-{d*10+9:02d}")
print("\nShare by last-two-digit decade (% of total):")
print(by_decade)

# 3) How unusual are the leaders? (Z-scores under uniform multinomial)
print("\nTop 10 Z-scores:")
print(summary.sort_values("Z", ascending=False).head(10)[["Prob","Total","Z"]])

# Optional: month-of-year profile for a specific range (weighted by counts)
# Example for '7520-7529'
target = "7520-7529"
s = df[[date_col, target]].copy()
s[date_col] = pd.to_datetime(s[date_col], errors="coerce", dayfirst=True)
mo = (s.dropna(subset=[date_col])
       .assign(month=s[date_col].dt.month_name())
       .groupby("month")[target].sum()
       .reindex(["January","February","March","April","May","June","July","August","September","October","November","December"], fill_value=0))
print(f"\nMonthly distribution for {target}:")
print((mo / mo.sum() * 100).round(2))