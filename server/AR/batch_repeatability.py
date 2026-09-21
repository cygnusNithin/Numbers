#!/usr/bin/env python3
"""
batch_repeatability.py

Usage:
    python batch_repeatability.py --csv all_prizes_number_patters26.csv --outdir outputs --top 100 --workers 4

Input CSV columns (expected):
    number,total_hits,dates,avg_gap_days,weekday_counts,month_counts,remaining_to_max

Key behavior:
- Parses dates field like: 17/08/2020(100)|10/09/2020(500)|...
- Builds daily binary series per number (presence of hit on a day)
- Computes inter-hit gap metrics, ACF peak (7..180 days), spectral dominant period (7..365 days)
- Produces repeatability_score combining ACF peak and spectral power fraction
- Saves repeatability_summary.csv and diagnostics for top N numbers
"""
import argparse
import os
import re
from datetime import datetime
import numpy as np
import pandas as pd
from scipy.signal import periodogram
from statsmodels.tsa.stattools import acf
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

# Regex to parse date(category) tokens
DATE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\((\d+)\)")

def parse_dates_field(dates_field):
    """Return list of (pd.Timestamp, int category) from the dates string."""
    if pd.isna(dates_field) or str(dates_field).strip() == "":
        return []
    parts = str(dates_field).split("|")
    out = []
    for p in parts:
        m = DATE_RE.search(p.strip())
        if m:
            dstr, cat = m.groups()
            try:
                dt = pd.to_datetime(dstr, dayfirst=True, format="%d/%m/%Y")
            except Exception:
                dt = pd.to_datetime(dstr, dayfirst=True, errors="coerce")
            if pd.notna(dt):
                out.append((dt.normalize(), int(cat)))
    return out

def build_daily_binary_series(dates_list, start=None, end=None):
    """Return daily binary Series indexed by date from start to end inclusive."""
    if len(dates_list) == 0:
        return pd.Series(dtype=int)
    dates = [d for d, c in dates_list if pd.notna(d)]
    s = pd.Series(1, index=pd.to_datetime(dates))
    s = s.groupby(s.index).sum().sort_index()
    if start is None:
        start = s.index.min()
    if end is None:
        end = s.index.max()
    idx = pd.date_range(start=start, end=end, freq="D")
    s = s.reindex(idx, fill_value=0)
    s = (s > 0).astype(int)
    return s

def inter_hit_metrics(series):
    """Compute inter-hit gap metrics from a daily binary series."""
    hit_dates = series[series > 0].index
    num_hits = len(hit_dates)
    if num_hits < 2:
        return {
            "num_hits": int(num_hits),
            "mean_gap_days": None,
            "std_gap_days": None,
            "cv_gap": None,
            "last_gap_days": None
        }
    gaps = hit_dates.to_series().diff().dt.days.dropna().values
    mean_gap = float(np.mean(gaps))
    std_gap = float(np.std(gaps, ddof=0))
    cv = float(std_gap / (mean_gap + 1e-9))
    last_gap = int(gaps[-1])
    return {
        "num_hits": int(num_hits),
        "mean_gap_days": mean_gap,
        "std_gap_days": std_gap,
        "cv_gap": cv,
        "last_gap_days": last_gap
    }

def acf_peak(series, nlags=365, min_lag=7, max_lag=180):
    """Compute ACF and return peak lag and value within min_lag..max_lag."""
    x = series.values.astype(float)
    if x.sum() < 2:
        return {"acf_peak_lag": None, "acf_peak_value": None, "acf_values": None}
    try:
        acf_vals = acf(x, nlags=nlags, fft=True, missing='conservative')
    except Exception:
        acf_vals = acf(x, nlags=min(len(x)-1, nlags), fft=True, missing='conservative')
    lags = np.arange(len(acf_vals))
    mask = (lags >= min_lag) & (lags <= max_lag)
    if not mask.any():
        return {"acf_peak_lag": None, "acf_peak_value": None, "acf_values": acf_vals}
    masked = acf_vals[mask]
    peak_idx = np.argmax(masked)
    peak_lag = int(lags[mask][peak_idx])
    peak_val = float(masked[peak_idx])
    return {"acf_peak_lag": peak_lag, "acf_peak_value": peak_val, "acf_values": acf_vals}

def spectral_dominant_period(series, fs=1.0, min_period=7, max_period=365):
    """Compute periodogram and return dominant period in days and its power."""
    x = series.values.astype(float)
    if x.sum() < 2:
        return {"dominant_period_days": None, "dominant_power": None, "freq": None, "power": None}
    f, Pxx = periodogram(x, fs=fs)
    with np.errstate(divide='ignore', invalid='ignore'):
        periods = np.zeros_like(f)
        nonzero = f > 0
        periods[nonzero] = 1.0 / f[nonzero]
    mask = (periods >= min_period) & (periods <= max_period)
    if not mask.any():
        return {"dominant_period_days": None, "dominant_power": None, "freq": f, "power": Pxx}
    idx = np.argmax(Pxx[mask])
    dom_period = float(periods[mask][idx])
    dom_power = float(Pxx[mask][idx])
    return {"dominant_period_days": dom_period, "dominant_power": dom_power, "freq": f, "power": Pxx}

def repeatability_score(acf_peak_val, dom_power, total_power):
    """Combine ACF peak and spectral power fraction into a simple score."""
    score = 0.0
    if acf_peak_val is not None:
        score += 0.5 * max(0.0, acf_peak_val)
    if dom_power is not None and total_power is not None and total_power > 0:
        score += 0.5 * (dom_power / (total_power + 1e-9))
    return float(score)

def analyze_row(row):
    """Process a single CSV row (dict-like) and return metrics dict."""
    number = str(row["number"])
    dates_field = row.get("dates", "")
    parsed = parse_dates_field(dates_field)
    if len(parsed) == 0:
        return {
            "number": number,
            "num_hits": 0,
            "mean_gap_days": None,
            "std_gap_days": None,
            "cv_gap": None,
            "last_gap_days": None,
            "acf_peak_lag": None,
            "acf_peak_value": None,
            "dominant_period_days": None,
            "dominant_power": None,
            "repeatability_score": 0.0,
            "start_date": None,
            "end_date": None
        }
    start = min(d for d, c in parsed)
    end = max(d for d, c in parsed)
    daily = build_daily_binary_series(parsed, start=start, end=end)
    ih = inter_hit_metrics(daily)
    acf_res = acf_peak(daily, nlags=365, min_lag=7, max_lag=180)
    spec_res = spectral_dominant_period(daily, fs=1.0, min_period=7, max_period=365)
    total_power = None
    if spec_res.get("power") is not None:
        total_power = float(np.sum(spec_res["power"]))
    score = repeatability_score(acf_res["acf_peak_value"], spec_res.get("dominant_power"), total_power)
    return {
        "number": number,
        "num_hits": ih["num_hits"],
        "mean_gap_days": ih["mean_gap_days"],
        "std_gap_days": ih["std_gap_days"],
        "cv_gap": ih["cv_gap"],
        "last_gap_days": ih["last_gap_days"],
        "acf_peak_lag": acf_res["acf_peak_lag"],
        "acf_peak_value": acf_res["acf_peak_value"],
        "dominant_period_days": spec_res["dominant_period_days"],
        "dominant_power": spec_res["dominant_power"],
        "repeatability_score": score,
        "start_date": str(start.date()),
        "end_date": str(end.date())
    }

def save_diagnostics(number, dates_field, outdir):
    """Save parsed hits CSV and diagnostic plots for a single number."""
    parsed = parse_dates_field(dates_field)
    if len(parsed) == 0:
        return
    start = min(d for d, c in parsed)
    end = max(d for d, c in parsed)
    daily = build_daily_binary_series(parsed, start=start, end=end)
    hits_df = pd.DataFrame(parsed, columns=["date", "category"])
    hits_df.to_csv(os.path.join(outdir, f"number_{number}_hits_parsed.csv"), index=False)
    daily_df = daily.rename("hits").reset_index().rename(columns={"index": "date"})
    daily_df.to_csv(os.path.join(outdir, f"number_{number}_daily_series.csv"), index=False)

    # daily plot
    plt.figure(figsize=(12,3))
    plt.plot(daily.index, daily.values, drawstyle='steps-mid')
    plt.title(f"Daily hits for {number}")
    plt.ylabel("hits (0/1)")
    plt.xlabel("date")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"number_{number}_daily_plot.png"))
    plt.close()

    # weekly heatmap
    df_week = daily.reset_index().rename(columns={"index":"date", 0:"hits"})
    df_week["week"] = df_week["date"].dt.isocalendar().week
    df_week["year"] = df_week["date"].dt.year
    pivot = df_week.pivot_table(index="year", columns="week", values="hits", aggfunc='sum', fill_value=0)
    plt.figure(figsize=(14, max(2, pivot.shape[0]*0.3)))
    sns.heatmap(pivot, cmap="Greys", cbar=True)
    plt.title(f"Weekly heatmap (year x week) for {number}")
    plt.xlabel("ISO week")
    plt.ylabel("year")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"number_{number}_weekly_heatmap.png"))
    plt.close()

def main():
    parser = argparse.ArgumentParser(description="Batch repeatability analysis for 4-digit numbers CSV.")
    parser.add_argument("--csv", required=True, help="Input CSV path")
    parser.add_argument("--outdir", default="outputs", help="Output directory")
    parser.add_argument("--top", type=int, default=100, help="Top N repeaters to save diagnostics for")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (use >1 for speed)")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    df = pd.read_csv(args.csv, dtype=str)
    if "number" not in df.columns or "dates" not in df.columns:
        raise ValueError("CSV must contain 'number' and 'dates' columns")

    rows = df.to_dict(orient="records")
    results = []

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as exe:
            futures = {exe.submit(analyze_row, r): r for r in rows}
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Processing rows"):
                try:
                    res = fut.result()
                    results.append(res)
                except Exception as e:
                    r = futures[fut]
                    print(f"Error processing number {r.get('number')}: {e}")
    else:
        for r in tqdm(rows, desc="Processing rows"):
            try:
                res = analyze_row(r)
                results.append(res)
            except Exception as e:
                print(f"Error processing number {r.get('number')}: {e}")

    summary_df = pd.DataFrame(results)
    numeric_cols = ["num_hits","mean_gap_days","std_gap_days","cv_gap","last_gap_days","acf_peak_lag","acf_peak_value","dominant_period_days","dominant_power","repeatability_score"]
    for c in numeric_cols:
        if c in summary_df.columns:
            summary_df[c] = pd.to_numeric(summary_df[c], errors="coerce")

    summary_df = summary_df.sort_values("repeatability_score", ascending=False).reset_index(drop=True)
    summary_csv = os.path.join(args.outdir, "repeatability_summary.csv")
    summary_df.to_csv(summary_csv, index=False)
    print(f"Saved summary to {summary_csv}")

    top_n = summary_df.head(args.top)["number"].tolist()
    print(f"Saving diagnostics for top {len(top_n)} numbers")
    for num in tqdm(top_n, desc="Saving diagnostics"):
        row = df[df["number"].astype(str) == str(num)]
        if row.empty:
            continue
        dates_field = row.iloc[0]["dates"]
        try:
            save_diagnostics(num, dates_field, args.outdir)
        except Exception as e:
            print(f"Failed diagnostics for {num}: {e}")

if __name__ == "__main__":
    main()
