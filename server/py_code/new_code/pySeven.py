#!/usr/bin/env python3
"""
lottery_transition_analysis.py

Connects to MongoDB (mongodb://localhost:27017/), reads number appearance documents
from numbergrid.lotterydatas, normalizes dates (Indian DD/MM/YYYY and variants),
computes per-number timelines, transitions between prize segments, statistics and
pattern interpretation, and writes multiple CSV files:

- clean_preview.csv
- number_timelines.csv
- number_transitions.csv
- 5000_prior_analysis.csv
- summary_stats.csv
- transition_summary.csv

Adjust MONGO_URI, DB_NAME, COLLECTION, and DATE WINDOW below if needed.
"""

import csv
from collections import defaultdict, Counter
from datetime import datetime
from math import isnan
import numpy as np
import pandas as pd
from pymongo import MongoClient
from tqdm import tqdm

# -----------------------
# CONFIG
# -----------------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

# Output filenames
OUT_CLEAN_PREVIEW = "clean_preview.csv"
OUT_TIMELINES = "number_timelines.csv"
OUT_TRANSITIONS = "number_transitions.csv"
OUT_5000_PRIOR = "5000_prior_analysis.csv"
OUT_SUMMARY = "summary_stats.csv"
OUT_TRANSITION_SUMMARY = "transition_summary.csv"

# Date window for sorting/filtering (Indian format day/month/year)
WINDOW_START = "11/07/2020"   # inclusive
WINDOW_END = "09/11/2025"     # inclusive

# Prize levels we expect; script will auto-detect all prizes found in DB.
DEFAULT_PRIZE_ORDER = [100, 200, 500, 1000, 2000, 5000]

# -----------------------
# HELPERS
# -----------------------
def parse_date_indian(s):
    """
    Robust date parsing for common variants.
    Returns datetime or None.
    Accepts: DD/MM/YYYY, D/M/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD.MM.YYYY, etc.
    """
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    s = str(s).strip()
    if not s:
        return None
    fmts = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%Y.%m.%d"
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    # Try swapping parts heuristically (if format looks ambiguous)
    parts = [p for p in s.replace("-", "/").replace(".", "/").split("/") if p]
    if len(parts) == 3:
        # attempt DD/MM/YYYY with zero-padding
        try:
            d, m, y = parts
            if len(y) == 2:
                y = "20" + y
            return datetime(int(y), int(m), int(d))
        except Exception:
            pass
    return None

def format_date_indian(dt):
    if pd.isna(dt) or dt is None:
        return ""
    return dt.strftime("%d/%m/%Y")

# -----------------------
# CONNECT & LOAD
# -----------------------
print("➡️ Connecting to MongoDB...")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]

print("➡️ Reading documents from collection...")
# We expect documents that contain a `date` field and series/numbers or prize and number combos.
# Try to be tolerant: documents may be shaped differently (flattened or nested).
docs = list(collection.find({}))

print(f"   Retrieved {len(docs)} documents from DB.")

# -----------------------
# EXTRACT EVENTS: rows = (number, prize, date_string, parsed_date)
# -----------------------
events = []  # list of dicts
missed_dates = 0

for doc in docs:
    # try multiple shapes:
    # shape A: document has 'date' and 'series' (array) with {prize:..., numbers:[{number, count}, ...]}
    if "series" in doc and isinstance(doc["series"], list):
        doc_date = doc.get("date") or doc.get("drawDate") or doc.get("draw_date")
        for series in doc["series"]:
            prize = series.get("prize") or series.get("prize_amount") or series.get("prizeValue")
            numbers = series.get("numbers") or series.get("numbers_list") or []
            for n in numbers:
                # number may be inside {number: '0123'} or simple string
                num = n.get("number") if isinstance(n, dict) else n
                if num is None:
                    continue
                parsed = parse_date_indian(doc_date)
                if parsed is None:
                    missed_dates += 1
                events.append({
                    "number": str(num).zfill(4),
                    "prize": int(prize) if prize is not None else None,
                    "raw_date": doc_date,
                    "date": parsed
                })
    # shape B: document is flat: {date, prize, number}
    elif "number" in doc and ("prize" in doc or "prize_amount" in doc):
        num = doc.get("number")
        prize = doc.get("prize") or doc.get("prize_amount")
        doc_date = doc.get("date") or doc.get("drawDate") or doc.get("draw_date")
        parsed = parse_date_indian(doc_date)
        if parsed is None:
            missed_dates += 1
        events.append({
            "number": str(num).zfill(4),
            "prize": int(prize) if prize is not None else None,
            "raw_date": doc_date,
            "date": parsed
        })
    # shape C: document has multiple prize keys with arrays (rare)
    else:
        # attempt to find any prize-like keys
        doc_date = doc.get("date") or doc.get("drawDate") or doc.get("draw_date")
        parsed = parse_date_indian(doc_date)
        found_any = False
        for key, val in doc.items():
            if key in ("_id", "date", "drawDate", "draw_date"):
                continue
            # if key looks like prize (numeric string) or 'prize_5000'
            key_lower = str(key).lower()
            prize_val = None
            if "prize" in key_lower:
                # skip - unclear
                continue
            # if value is list of numbers, treat key as prize if numeric
            try:
                maybe_prize = int(key)
                prize_val = maybe_prize
            except Exception:
                # not numeric key
                prize_val = None
            if prize_val and isinstance(val, list):
                for n in val:
                    events.append({
                        "number": str(n).zfill(4),
                        "prize": int(prize_val),
                        "raw_date": doc_date,
                        "date": parsed
                    })
                    found_any = True
        if not found_any:
            # can't parse this doc; skip
            continue

print(f"➡️ Extracted {len(events)} raw events (missed_dates={missed_dates})")

# Build DataFrame
df_events = pd.DataFrame(events)
# Drop events without parsed dates (we want only dated events)
df_events = df_events[df_events["date"].notnull()].copy()

# Ensure prize is int and number zero-padded 4
df_events["prize"] = df_events["prize"].astype("Int64")
df_events["number"] = df_events["number"].astype(str).str.zfill(4)

# Auto-detect observed prizes and choose the order (prefer DEFAULT_PRIZE_ORDER)
observed_prizes = sorted(df_events["prize"].dropna().unique().astype(int).tolist())
# Create a final prize order: keep DEFAULT order for known prizes, append any extras at end
prize_order = [p for p in DEFAULT_PRIZE_ORDER if p in observed_prizes] + [p for p in observed_prizes if p not in DEFAULT_PRIZE_ORDER]
print("Observed prizes:", observed_prizes)
print("Using prize order:", prize_order)

# -----------------------
# FILTER BY DATE WINDOW (inclusive)
# -----------------------
start_dt = parse_date_indian(WINDOW_START)
end_dt = parse_date_indian(WINDOW_END)
if start_dt is None or end_dt is None:
    raise ValueError("WINDOW_START or WINDOW_END could not be parsed. Use DD/MM/YYYY formats.")

df_events = df_events[(df_events["date"] >= start_dt) & (df_events["date"] <= end_dt)].copy()
df_events.sort_values(["date", "number", "prize"], inplace=True)

print(f"➡️ Events after applying date window ({WINDOW_START} → {WINDOW_END}): {len(df_events)}")

# -----------------------
# CLEAN PREVIEW
# -----------------------
clean_preview = df_events.head(100).copy()
# Normalize columns
clean_preview_out = clean_preview[["number", "prize", "raw_date", "date"]].copy()
clean_preview_out["date"] = clean_preview_out["date"].dt.strftime("%d/%m/%Y")
clean_preview_out.to_csv(OUT_CLEAN_PREVIEW, index=False, encoding="utf-8")
print(f"✅ Wrote clean preview -> {OUT_CLEAN_PREVIEW} (rows: {len(clean_preview_out)})")

# -----------------------
# BUILD PER-NUMBER TIMELINES
# -----------------------
print("➡️ Building per-number timelines...")

# group events by number, sort by date
number_groups = df_events.groupby("number")

timelines = {}  # number -> list of (date, prize)
for num, g in tqdm(number_groups, total=len(number_groups)):
    rows = g.sort_values("date")
    timeline = [(r["date"], int(r["prize"])) for _, r in rows.iterrows()]
    timelines[num] = timeline

# write number_timelines.csv (one row per number)
rows_out = []
for num, timeline in timelines.items():
    # timeline string like: 11/07/2020 (₹5000) → 30/09/2020 (₹100) ...
    timeline_str = " → ".join([f"{d.strftime('%d/%m/%Y')} (₹{p})" for d, p in timeline])
    total_hits = len(timeline)
    counts = Counter([p for _, p in timeline])
    # prepare weekday and month counts combined (per-prize)
    weekday_counts = defaultdict(lambda: defaultdict(int))
    month_counts = defaultdict(lambda: defaultdict(int))
    for d, p in timeline:
        weekday_counts[p][d.strftime("%A")] += 1
        month_counts[p][d.strftime("%B")] += 1

    rows_out.append({
        "number": num,
        "first_date": timeline[0][0].strftime("%d/%m/%Y"),
        "last_date": timeline[-1][0].strftime("%d/%m/%Y"),
        "timeline_str": timeline_str,
        "total_appearances": total_hits,
        "remaining_to_max": max(0, 0),  # placeholder (user has own max idea)
        "total_per_prize": dict(counts),
        "weekday_counts": dict(weekday_counts),
        "month_counts": dict(month_counts)
    })

df_timelines_out = pd.DataFrame(rows_out)
# Save more readable CSV: expand total_per_prize into columns
def prize_count_col(p):
    return f"count_₹{p}"

for p in prize_order:
    df_timelines_out[prize_count_col(p)] = df_timelines_out["total_per_prize"].apply(lambda d: d.get(p, 0) if isinstance(d, dict) else 0)

# Keep essential columns and timeline string
export_timelines = df_timelines_out[[
    "number", "first_date", "last_date", "total_appearances", "timeline_str"
] + [prize_count_col(p) for p in prize_order] + ["weekday_counts", "month_counts"]]

export_timelines.to_csv(OUT_TIMELINES, index=False, encoding="utf-8")
print(f"✅ Wrote number timelines -> {OUT_TIMELINES} (rows: {len(export_timelines)})")

# -----------------------
# COMPUTE TRANSITIONS (consecutive events)
# -----------------------
print("➡️ Computing transitions between consecutive prize appearances...")

transition_rows = []
for num, timeline in timelines.items():
    # timeline is sorted list of (date, prize)
    for i in range(1, len(timeline)):
        from_date, from_prize = timeline[i-1]
        to_date, to_prize = timeline[i]
        gap_days = (to_date - from_date).days
        transition_rows.append({
            "number": num,
            "from_prize": int(from_prize),
            "to_prize": int(to_prize),
            "from_date": from_date.strftime("%d/%m/%Y"),
            "to_date": to_date.strftime("%d/%m/%Y"),
            "gap_days": gap_days
        })

df_transitions = pd.DataFrame(transition_rows)
if not df_transitions.empty:
    df_transitions.to_csv(OUT_TRANSITIONS, index=False, encoding="utf-8")
    print(f"✅ Wrote transitions -> {OUT_TRANSITIONS} (rows: {len(df_transitions)})")
else:
    print("⚠️ No transitions found (insufficient timeline length).")

# -----------------------
# PER-NUMBER SUMMARY FIELDS (first_seen_in_<prize>, counts, avg gaps per prize)
# -----------------------
print("➡️ Computing per-number summary metrics...")

summary_rows = []
for num, timeline in timelines.items():
    # first seen per prize
    first_seen = {}
    last_seen = {}
    per_prize_dates = defaultdict(list)
    for d, p in timeline:
        per_prize_dates[p].append(d)
        if p not in first_seen:
            first_seen[p] = d
        last_seen[p] = d

    # compute avg gaps per prize for appearances of that prize (gaps between consecutive appearances of same prize)
    avg_gap_per_prize = {}
    total_counts = {}
    for p, dates in per_prize_dates.items():
        dates_sorted = sorted(dates)
        total_counts[p] = len(dates_sorted)
        if len(dates_sorted) >= 2:
            gaps = [(dates_sorted[i] - dates_sorted[i-1]).days for i in range(1, len(dates_sorted))]
            avg_gap_per_prize[p] = float(np.mean(gaps))
        else:
            avg_gap_per_prize[p] = float("nan")

    # total appearances across all prizes
    total_appearances = len(timeline)

    # gather first_seen_in_100, 500, 1000, 2000, 5000 (if present)
    row = {
        "number": num,
        "first_seen_in_100": format_date_indian(first_seen.get(100)) if 100 in first_seen else "",
        "first_seen_in_500": format_date_indian(first_seen.get(500)) if 500 in first_seen else "",
        "first_seen_in_1000": format_date_indian(first_seen.get(1000)) if 1000 in first_seen else "",
        "first_seen_in_2000": format_date_indian(first_seen.get(2000)) if 2000 in first_seen else "",
        "first_seen_in_5000": format_date_indian(first_seen.get(5000)) if 5000 in first_seen else "",
        "total_appearances": total_appearances,
        "remaining_to_max": 0,
        "appearances_timeline": " → ".join([f"{d.strftime('%d/%m/%Y')} (₹{p})" for d, p in timeline]),
    }

    # counts per prize
    for p in prize_order:
        row[f"total_appearances_in_{p}"] = total_counts.get(p, 0)

    # avg gaps per prize
    for p in prize_order:
        val = avg_gap_per_prize.get(p, float("nan"))
        row[f"avg_gap_days_in_{p}"] = round(val, 3) if not (val is None or (isinstance(val, float) and isnan(val))) else ""

    # weekday_counts and month_counts for combined appearances (stringified)
    weekday_counter = {}
    month_counter = {}
    for p in per_prize_dates:
        wc = Counter([d.strftime("%A") for d in per_prize_dates[p]])
        mc = Counter([d.strftime("%B") for d in per_prize_dates[p]])
        weekday_counter[p] = dict(wc)
        month_counter[p] = dict(mc)
    row["weekday_counts"] = str(weekday_counter)
    row["month_counts"] = str(month_counter)

    summary_rows.append(row)

df_summary = pd.DataFrame(summary_rows)
# sort by first_seen_in_5000 ascending (parse back to date for sort)
def parse_if_date(s):
    d = parse_date_indian(s) if (isinstance(s, str) and s.strip()) else None
    return d

df_summary["__first_5000_dt"] = df_summary["first_seen_in_5000"].apply(lambda s: parse_if_date(s))
# Put rows with no 5000 at end
df_summary.sort_values(by="__first_5000_dt", na_position="last", inplace=True)
df_summary.drop(columns=["__first_5000_dt"], inplace=True)

# Save CSV in requested sample column structure (reorder columns)
ordered_cols = [
    "number",
    "first_seen_in_100", "first_seen_in_500", "first_seen_in_1000", "first_seen_in_2000", "first_seen_in_5000",
    "total_appearances", "remaining_to_max", "appearances_timeline"
]
# add per-prize totals and avg gaps in order
for p in prize_order:
    ordered_cols.append(f"total_appearances_in_{p}")
for p in prize_order:
    ordered_cols.append(f"avg_gap_days_in_{p}")
ordered_cols += ["weekday_counts", "month_counts"]

df_summary = df_summary.reindex(columns=ordered_cols)
df_summary.to_csv(OUT_5000_PRIOR, index=False, encoding="utf-8")
print(f"✅ Wrote per-number summary -> {OUT_5000_PRIOR} (rows: {len(df_summary)})")

# -----------------------
# 5000 PRIOR ANALYSIS (numbers that appeared in 5000 and whether had prior lower prize hits)
# -----------------------
print("➡️ Performing focused analysis for numbers that appear in ₹5000...")

# collect numbers with first_seen_in_5000 present
df_with_5000 = df_summary[df_summary["first_seen_in_5000"].astype(bool)].copy()

analysis_rows = []
gaps_list = []  # min days between any prior lower prize first occurrence and first 5000
count_with_prior = 0
for _, row in df_with_5000.iterrows():
    num = row["number"]
    first_5000_dt = parse_date_indian(row["first_seen_in_5000"])
    # find earliest date among lower prizes (100,500,1000,2000) that is strictly before first_5000_dt
    lower_prizes = [p for p in prize_order if p != 5000]
    earliest_lower = None
    earliest_lower_prize = None
    for p in lower_prizes:
        col = f"first_seen_in_{p}"
        if col in row and isinstance(row[col], str) and row[col].strip():
            d = parse_date_indian(row[col])
            if d and d < first_5000_dt:
                if earliest_lower is None or d < earliest_lower:
                    earliest_lower = d
                    earliest_lower_prize = p
    had_prior = earliest_lower is not None
    if had_prior:
        gap = (first_5000_dt - earliest_lower).days
        gaps_list.append(gap)
        count_with_prior += 1
    else:
        gap = None

    analysis_rows.append({
        "number": num,
        "first_seen_in_5000": row["first_seen_in_5000"],
        "had_prior_lower": had_prior,
        "earliest_lower_prize": earliest_lower_prize if had_prior else "",
        "earliest_lower_date": format_date_indian(earliest_lower) if had_prior else "",
        "days_from_earliest_lower_to_5000": gap if gap is not None else ""
    })

df_5000_analysis = pd.DataFrame(analysis_rows)
df_5000_analysis.to_csv("5000_prior_analysis_detailed.csv", index=False, encoding="utf-8")
print(f"✅ Wrote detailed 5000 prior analysis -> 5000_prior_analysis_detailed.csv (rows: {len(df_5000_analysis)})")

# High-level gap stats
if gaps_list:
    gaps_arr = np.array(gaps_list)
    summary_gap = {
        "count": int(len(gaps_arr)),
        "mean": float(np.mean(gaps_arr)),
        "median": float(np.median(gaps_arr)),
        "25%": float(np.percentile(gaps_arr, 25)),
        "75%": float(np.percentile(gaps_arr, 75)),
        "min": int(np.min(gaps_arr)),
        "max": int(np.max(gaps_arr))
    }
else:
    summary_gap = {"count": 0, "mean": "", "median": "", "25%": "", "75%": "", "min": "", "max": ""}

# -----------------------
# TRANSITION SUMMARY: Most common transitions and average gap
# -----------------------
print("➡️ Summarizing transitions across all numbers...")

if not df_transitions.empty:
    trans_summary = df_transitions.groupby(["from_prize", "to_prize"]).agg(
        count=("gap_days", "count"),
        avg_gap_days=("gap_days", "mean"),
        median_gap_days=("gap_days", lambda s: float(np.median(s)))
    ).reset_index().sort_values("count", ascending=False)
else:
    trans_summary = pd.DataFrame(columns=["from_prize", "to_prize", "count", "avg_gap_days", "median_gap_days"])

trans_summary.to_csv(OUT_TRANSITION_SUMMARY, index=False, encoding="utf-8")
print(f"✅ Wrote transition summary -> {OUT_TRANSITION_SUMMARY} (rows: {len(trans_summary)})")

# -----------------------
# SUMMARY STATS (high-level)
# -----------------------
print("➡️ Computing final summary statistics...")

total_numbers = len(timelines)
numbers_with_5000 = df_with_5000.shape[0]
numbers_with_prior_percent = (count_with_prior / numbers_with_5000 * 100) if numbers_with_5000 > 0 else 0.0

summary_stats = {
    "total_numbers_inspected": total_numbers,
    "numbers_with_any_5000": numbers_with_5000,
    "numbers_with_prior_lower_count": count_with_prior,
    "numbers_with_prior_lower_percent": round(numbers_with_prior_percent, 4),
    "gap_count": summary_gap["count"],
    "gap_mean_days": summary_gap["mean"],
    "gap_median_days": summary_gap["median"],
    "gap_25pct_days": summary_gap["25%"],
    "gap_75pct_days": summary_gap["75%"],
    "gap_min_days": summary_gap["min"],
    "gap_max_days": summary_gap["max"]
}

# Also include a few human-friendly finds: top transitions
top_transitions = trans_summary.head(10).to_dict(orient="records")

# Save summary_stats CSV
df_summary_stats = pd.DataFrame([summary_stats])
df_summary_stats.to_csv(OUT_SUMMARY, index=False, encoding="utf-8")
print(f"✅ Wrote summary stats -> {OUT_SUMMARY}")

# Save number_timelines and number_transitions (already done) — but also export number_transitions in requested format
if not df_transitions.empty:
    df_transitions = df_transitions[[
        "number", "from_prize", "to_prize", "from_date", "to_date", "gap_days"
    ]]
    df_transitions.to_csv(OUT_TRANSITIONS, index=False, encoding="utf-8")

# -----------------------
# PRINT PATTERN INTERPRETATION SUMMARY (human-readable)
# -----------------------
print("\n\n==================== PATTERN INTERPRETATION SUMMARY ====================\n")
print(f"Date window: {WINDOW_START} → {WINDOW_END}")
print(f"Total unique numbers inspected: {total_numbers:,}")
print(f"Numbers that appeared at least once in ₹5,000: {numbers_with_5000:,}")
print(f"Of those, numbers that had at least one prior appearance in lower prizes ({[p for p in prize_order if p!=5000]}): {count_with_prior:,} ({numbers_with_prior_percent:.2f}%).")
if summary_gap["count"] > 0:
    print("\nGap (days) distribution from earliest lower-prize appearance to first ₹5,000 appearance (numbers with prior lower-prize hits):")
    print(f"  Count = {summary_gap['count']}")
    print(f"  Mean ≈ {summary_gap['mean']:.2f} days")
    print(f"  Median = {summary_gap['median']:.0f} days")
    print(f"  25% percentile = {summary_gap['25%']:.0f} days")
    print(f"  75% percentile = {summary_gap['75%']:.0f} days")
    print(f"  Min = {summary_gap['min']} days, Max = {summary_gap['max']} days")
else:
    print("No prior-lower → 5000 gaps to report.")

# Top transition patterns
if not trans_summary.empty:
    print("\nMost common immediate transitions (from_prize → to_prize):")
    for idx, rec in trans_summary.head(8).iterrows():
        print(f"  ₹{int(rec['from_prize'])} → ₹{int(rec['to_prize'])}: count={int(rec['count'])}, avg_gap_days={rec['avg_gap_days']:.1f}, median_gap_days={rec['median_gap_days']:.1f}")
else:
    print("No transitions available.")

# Quick takeaways
print("\nQuick interpretation:")
print("  • A high fraction of numbers that later show up in ₹5,000 have prior hits in lower prizes (if percent is high).")
print("  • Median gap gives a practical window (weeks/months) for signal-following from lower prizes → ₹5,000.")
print("  • Most common direct transitions and their average gaps are written to", OUT_TRANSITION_SUMMARY)
print("\nAll detailed CSV outputs:")
print("  -", OUT_CLEAN_PREVIEW)
print("  -", OUT_TIMELINES)
print("  -", OUT_TRANSITIONS)
print("  -", "5000_prior_analysis_detailed.csv")
print("  -", OUT_TRANSITION_SUMMARY)
print("  -", OUT_SUMMARY)

print("\nDone. ✅\n")
