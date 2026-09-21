# analyze_prizes.py
import os
import ast
import csv
from datetime import datetime
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- CONFIG ---
INPUT_CSV = "5000_oct30.csv"   # change if different
OUT_DIR = "analysis_outputs"
DATE_FMT = "%d/%m/%Y"      # format used in your sample
# ----------------

os.makedirs(OUT_DIR, exist_ok=True)

def parse_row(row):
    """
    Expected CSV columns:
    number,total_hits,remaining_to_max,dates,avg_gap_days,weekday_counts,month_counts
    dates is pipe-separated: 01/03/2021|...
    weekday_counts and month_counts are Python dict strings like "{'Monday': 3, ...}"
    """
    number = str(row[0]).zfill(4) if len(row[0]) < 4 else str(row[0])
    total_hits = int(row[1])
    remaining_to_max = int(row[2])
    dates_raw = row[3]
    avg_gap_days = float(row[4]) if row[4] not in ("", "nan", "None") else np.nan
    # parse lists/dicts safely
    dates = []
    if dates_raw and isinstance(dates_raw, str):
        dates = [d.strip() for d in dates_raw.split("|") if d.strip()]
    try:
        weekday_counts = ast.literal_eval(row[5]) if row[5] else {}
    except Exception:
        weekday_counts = {}
    try:
        month_counts = ast.literal_eval(row[6]) if row[6] else {}
    except Exception:
        month_counts = {}

    # parse dates to datetime
    parsed_dates = []
    for d in dates:
        try:
            parsed_dates.append(datetime.strptime(d, DATE_FMT))
        except Exception:
            # try alternate formats if necessary
            try:
                parsed_dates.append(pd.to_datetime(d, dayfirst=True))
            except:
                pass

    parsed_dates.sort()
    recency_days = (datetime.now() - parsed_dates[-1]).days if parsed_dates else np.nan
    # compute gaps between hits
    gaps = []
    if len(parsed_dates) >= 2:
        for a, b in zip(parsed_dates, parsed_dates[1:]):
            gaps.append((b - a).days)

    return {
        "number": number,
        "total_hits": total_hits,
        "remaining_to_max": remaining_to_max,
        "dates_str": dates_raw,
        "dates": parsed_dates,
        "avg_gap_days": avg_gap_days,
        "weekday_counts": weekday_counts,
        "month_counts": month_counts,
        "recency_days": recency_days,
        "gaps": gaps,
        "last_hit": parsed_dates[-1] if parsed_dates else None,
        "first_hit": parsed_dates[0] if parsed_dates else None
    }

# Read CSV into list of parsed rows
parsed = []
with open(INPUT_CSV, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)  # if there's a header; if not, comment out
    for row in reader:
        if not any(row):
            continue
        parsed.append(parse_row(row))

df = pd.DataFrame(parsed)

# Basic checks
df['dates_count'] = df['dates'].apply(len)
inconsistent = df[df['dates_count'] != df['total_hits']]
print(f"Rows with inconsistent hit counts: {len(inconsistent)} (saved to {OUT_DIR}/inconsistent.csv)")
inconsistent.to_csv(os.path.join(OUT_DIR, "inconsistent.csv"), index=False)

# SUMMARY STATISTICS
summary = {
    "count_numbers": len(df),
    "total_hits_sum": df['total_hits'].sum(),
    "total_hits_mean": df['total_hits'].mean(),
    "avg_gap_mean": df['avg_gap_days'].mean(),
    "recency_mean_days": df['recency_days'].mean()
}
print("Summary:", summary)
pd.Series(summary).to_frame("value").to_csv(os.path.join(OUT_DIR, "dataset_summary.csv"))

# Top numbers
top_hits = df.sort_values(['total_hits', 'last_hit'], ascending=[False, False]).head(50)
top_hits[['number','total_hits','remaining_to_max','last_hit','recency_days']].to_csv(os.path.join(OUT_DIR, "top_by_hits.csv"), index=False)

# Numbers close to max (remaining_to_max small)
near_max = df.sort_values('remaining_to_max').head(200)
near_max[['number','total_hits','remaining_to_max','last_hit','recency_days']].to_csv(os.path.join(OUT_DIR, "near_max_candidates.csv"), index=False)

# Recent trending: numbers with last_hit within last 365 days
recent = df[df['recency_days'] <= 365].sort_values('last_hit', ascending=False)
recent[['number','total_hits','last_hit','recency_days']].to_csv(os.path.join(OUT_DIR, "recent_hits_365d.csv"), index=False)

# Aggregate weekday and month counts across all numbers
weekday_agg = Counter()
month_agg = Counter()
for d in df['weekday_counts']:
    weekday_agg.update(d)
for m in df['month_counts']:
    month_agg.update(m)

pd.DataFrame.from_records(list(weekday_agg.items()), columns=['weekday','count']).sort_values('count', ascending=False).to_csv(os.path.join(OUT_DIR, "weekday_agg.csv"), index=False)
pd.DataFrame.from_records(list(month_agg.items()), columns=['month','count']).sort_values('count', ascending=False).to_csv(os.path.join(OUT_DIR, "month_agg.csv"), index=False)

# Plot distributions
plt.figure(figsize=(8,5))
df['total_hits'].hist(bins=30)
plt.title('Distribution of total_hits')
plt.xlabel('total_hits')
plt.ylabel('count')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "dist_total_hits.png"))
plt.close()

plt.figure(figsize=(8,5))
df['recency_days'].dropna().hist(bins=50)
plt.title('Distribution of recency (days since last hit)')
plt.xlabel('days')
plt.ylabel('count')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "dist_recency_days.png"))
plt.close()

plt.figure(figsize=(8,5))
df['avg_gap_days'].dropna().hist(bins=50)
plt.title('Distribution of avg_gap_days')
plt.xlabel('days')
plt.ylabel('count')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "dist_avg_gap_days.png"))
plt.close()

# Gaps summary per number: mean gap, median gap, max gap
def summarize_gaps(gaps):
    if not gaps:
        return pd.Series({"gaps_mean": np.nan, "gaps_median": np.nan, "gaps_max": np.nan})
    return pd.Series({"gaps_mean": np.mean(gaps), "gaps_median": np.median(gaps), "gaps_max": np.max(gaps)})

gaps_df = df['gaps'].apply(summarize_gaps)
df = pd.concat([df, gaps_df], axis=1)
df[['number','total_hits','gaps_mean','gaps_median','gaps_max']].sort_values('gaps_mean').head(50).to_csv(os.path.join(OUT_DIR, "smallest_mean_gaps.csv"), index=False)

# Build month and weekday feature matrix for clustering (optional)
# Create consistent ordering for weekdays and months
weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
months = ['January','February','March','April','May','June','July','August','September','October','November','December']

def make_vector(counts, keys):
    return [counts.get(k, 0) for k in keys]

weekday_matrix = np.array([make_vector(w, weekdays) for w in df['weekday_counts']])
month_matrix = np.array([make_vector(m, months) for m in df['month_counts']])
# Normalize
weekday_norm = weekday_matrix.astype(float)
month_norm = month_matrix.astype(float)
weekday_sums = weekday_norm.sum(axis=1, keepdims=True)
month_sums = month_norm.sum(axis=1, keepdims=True)
weekday_sums[weekday_sums==0] = 1
month_sums[month_sums==0] = 1
weekday_norm /= weekday_sums
month_norm /= month_sums

# Save a combined feature CSV for external clustering or ML
feat_df = pd.DataFrame(weekday_norm, columns=[f"wd_{d}" for d in weekdays])
feat_df = pd.concat([pd.DataFrame(month_norm, columns=[f"m_{m}" for m in months]), feat_df.reset_index(drop=True)], axis=1)
feat_df['number'] = df['number'].values
feat_df.to_csv(os.path.join(OUT_DIR, "weekday_month_feature_matrix.csv"), index=False)

# Export full annotated dataframe
df.to_csv(os.path.join(OUT_DIR, "annotated_full.csv"), index=False)

print("Analysis completed. Outputs placed in:", OUT_DIR)
