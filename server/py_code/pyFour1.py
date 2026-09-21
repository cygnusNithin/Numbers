# check_patterns_vs_new.py
import ast
import re
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
from tqdm import tqdm

# ----------------------
# Config (edit paths) //error on result(don't use)
# ----------------------
PATTERN_FILE = "5000_number_patterns18.csv"
NEW_BY_DAY_FILE = "new_5000_prize_numbers_grouped_ist.csv"  # your date,new_numbers_count,new_numbers file
WRITE_REPORTS = True  # set False if you don't want CSV outputs

# ----------------------
# Parsers
# ----------------------
def parse_dates_pipe(s: str) -> list[pd.Timestamp]:
    if pd.isna(s) or not s:
        return []
    out = []
    for part in str(s).split("|"):
        part = part.strip()
        # Try DD/MM/YYYY first, then YYYY-MM-DD
        ok = False
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                out.append(pd.to_datetime(part, format=fmt, dayfirst=True))
                ok = True
                break
            except Exception:
                pass
        if not ok:
            # last resort
            try:
                out.append(pd.to_datetime(part, dayfirst=True))
            except Exception:
                pass
    return sorted(out)

def parse_counts_dict(s: str) -> dict:
    if pd.isna(s) or not str(s).strip():
        return {}
    try:
        return ast.literal_eval(s)
    except Exception:
        # Fallback: very permissive parser for {"Key": n, ...}
        try:
            pairs = re.findall(r"'([^']+)'\s*:\s*([0-9]+)", str(s))
            return {k: int(v) for k, v in pairs}
        except Exception:
            return {}

def split_new_numbers(s: str) -> list[str]:
    if pd.isna(s) or not s: return []
    return [x.strip() for x in str(s).split("|") if x.strip()]

# ----------------------
# Load files
# ----------------------
def load_pattern_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Normalize and parse
    df["dates_list"] = df["dates"].apply(parse_dates_pipe)
    df["first_date"] = df["dates_list"].apply(lambda x: x[0] if x else pd.NaT)
    df["weekday_counts_dict"] = df["weekday_counts"].apply(parse_counts_dict)
    df["month_counts_dict"]   = df["month_counts"].apply(parse_counts_dict)
    return df

def load_new_by_day(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    df["new_list"] = df["new_numbers"].apply(split_new_numbers)
    return df

# ----------------------
# Checks
# ----------------------
def recompute_counts_from_dates(dates: list[pd.Timestamp]) -> tuple[dict, dict]:
    wd = Counter()
    mo = Counter()
    for d in dates:
        wd[d.day_name()] += 1
        mo[d.month_name()] += 1
    return dict(wd), dict(mo)

def top_k_keys(d: dict, k=2) -> list[str]:
    if not d: return []
    # Sort by count desc, then key asc for stability
    return [k_ for k_, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

def check_internal_counts(pattern_df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, r in tqdm(pattern_df.iterrows(), total=len(pattern_df), desc="Verify counts from dates"):
        wd_calc, mo_calc = recompute_counts_from_dates(r["dates_list"])
        wd_given = r["weekday_counts_dict"]
        mo_given = r["month_counts_dict"]
        if wd_calc != wd_given or mo_calc != mo_given:
            records.append({
                "number": r["number"],
                "wd_calc": wd_calc,
                "wd_given": wd_given,
                "mo_calc": mo_calc,
                "mo_given": mo_given
            })
    return pd.DataFrame(records)

def build_first_appearance_map(new_by_day: pd.DataFrame) -> dict[str, pd.Timestamp]:
    first_map = {}
    for _, row in new_by_day.iterrows():
        d = row["date"]
        for n in row["new_list"]:
            if n not in first_map:
                first_map[n] = d
    return first_map

def compare_first_dates(pattern_df: pd.DataFrame, first_map: dict[str, pd.Timestamp]) -> tuple[pd.DataFrame, pd.DataFrame]:
    in_both = pattern_df[pattern_df["number"].astype(str).isin(first_map.keys())].copy()
    in_both["first_from_new"] = in_both["number"].astype(str).map(first_map)
    in_both["first_match"] = (in_both["first_date"].dt.normalize() == in_both["first_from_new"].dt.normalize())
    mismatches = in_both[~in_both["first_match"]].copy()

    # new numbers missing in pattern file
    missing_numbers = sorted(set(first_map.keys()) - set(pattern_df["number"].astype(str)))
    missing_df = pd.DataFrame({"missing_in_pattern": missing_numbers})
    return mismatches, missing_df

def calendar_fit_check(new_by_day: pd.DataFrame, pattern_df: pd.DataFrame) -> pd.DataFrame:
    pat_map = {}
    for _, r in pattern_df.iterrows():
        pat_map[str(r["number"])] = {
            "wd": r["weekday_counts_dict"],
            "mo": r["month_counts_dict"]
        }
    rows = []
    for _, row in tqdm(new_by_day.iterrows(), total=len(new_by_day), desc="Calendar-fit on new_numbers"):
        d = row["date"]
        wd = d.day_name()
        mo = d.month_name()
        for n in row["new_list"]:
            n_str = str(n)
            if n_str not in pat_map:
                rows.append({"date": d, "number": n_str, "has_pattern": False, "wd_fit": np.nan, "mo_fit": np.nan, "both_fit": np.nan})
                continue
            wd_top2 = top_k_keys(pat_map[n_str]["wd"], k=2)
            mo_top2 = top_k_keys(pat_map[n_str]["mo"], k=2)
            wd_fit = wd in wd_top2 if wd_top2 else False
            mo_fit = mo in mo_top2 if mo_top2 else False
            rows.append({
                "date": d, "number": n_str, "has_pattern": True,
                "wd_fit": wd_fit, "mo_fit": mo_fit, "both_fit": (wd_fit and mo_fit)
            })
    return pd.DataFrame(rows)

# ----------------------
# Main
# ----------------------
def main():
    if not Path(PATTERN_FILE).exists():
        raise FileNotFoundError(f"Pattern file not found: {PATTERN_FILE}")
    if not Path(NEW_BY_DAY_FILE).exists():
        raise FileNotFoundError(f"New-numbers file not found: {NEW_BY_DAY_FILE}")

    pattern_df = load_pattern_df(PATTERN_FILE)
    new_by_day = load_new_by_day(NEW_BY_DAY_FILE)

    print(f"Loaded pattern file: {len(pattern_df):,} numbers")
    print(f"Loaded new-by-day file: {len(new_by_day):,} days")

    # 1) Internal consistency: weekday/month counts
    bad_counts = check_internal_counts(pattern_df)
    if bad_counts.empty:
        print("✓ All weekday/month counts match the dates in the pattern file.")
    else:
        print(f"⚠ Found {len(bad_counts)} numbers with mismatched weekday/month counts.")

    # 2) First date alignment with new_numbers
    first_map = build_first_appearance_map(new_by_day)
    mismatches, missing_df = compare_first_dates(pattern_df, first_map)
    print(f"\nFirst-date alignment:")
    print(f"  Numbers in pattern ∩ new: {len(pattern_df[pattern_df['number'].astype(str).isin(first_map.keys())])}")
    print(f"  First-date mismatches: {len(mismatches)}")
    print(f"  New-numbers missing from pattern: {len(missing_df)}")

    # 3) Calendar-fit of new_numbers to each number’s top-2 weekday/month
    fit_df = calendar_fit_check(new_by_day, pattern_df)
    have_pat = fit_df["has_pattern"].sum()
    rate_wd  = fit_df.loc[fit_df["has_pattern"], "wd_fit"].mean()
    rate_mo  = fit_df.loc[fit_df["has_pattern"], "mo_fit"].mean()
    rate_both = fit_df.loc[fit_df["has_pattern"], "both_fit"].mean()
    print(f"\nCalendar fit on new_numbers (only where pattern exists):")
    print(f"  Rows checked: {have_pat:,}")
    print(f"  Weekday in top-2: {rate_wd:.2%}")
    print(f"  Month   in top-2: {rate_mo:.2%}")
    print(f"  Both weekday & month in top-2: {rate_both:.2%}")

    # 4) Optional reports
    if WRITE_REPORTS:
        if not bad_counts.empty:
            bad_counts.to_csv("pattern_counts_mismatch.csv", index=False)
            print("→ Saved pattern_counts_mismatch.csv")
        if not mismatches.empty:
            mismatches[["number","first_date","first_from_new"]].to_csv("first_date_mismatches.csv", index=False)
            print("→ Saved first_date_mismatches.csv")
        if not missing_df.empty:
            missing_df.to_csv("missing_in_pattern.csv", index=False)
            print("→ Saved missing_in_pattern.csv")
        fit_df.to_csv("calendar_fit_new_numbers.csv", index=False)
        print("→ Saved calendar_fit_new_numbers.csv")

if __name__ == "__main__":
    main()