import pandas as pd

fp = "filtered_prizes.csv"
df = pd.read_csv(fp)

date_col = df.columns[0]
range_cols = df.columns[1:]

# Month totals (exposure)
df["_dt"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
df["_month"] = df["_dt"].dt.to_period("M")
month_totals = df[range_cols].sum(axis=1).groupby(df["_month"]).sum()

def normalized_month_profile(target):
    s = df[[ "_month", target ]].copy()
    m = s.groupby("_month")[target].sum()
    share = (m / month_totals).dropna() * 100  # % of all counts in that month
    share.index = share.index.astype(str)
    return share

# Example:
target = "7520-7529"
profile = normalized_month_profile(target)
print(profile.sort_index())  # % share per month for the target
print("Overall share:", df[range_cols][target].sum() / df[range_cols].sum().sum() * 100)