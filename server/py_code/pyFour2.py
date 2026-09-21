# check_patterns_vs_new.py
import ast
import re
import argparse
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from tqdm import tqdm

WEEKDAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
MONTHS   = ["January","February","March","April","May","June","July","August","September","October","November","December"]

# ----------------------
# Parsers
# ----------------------
def parse_dates_pipe(s: str) -> list[pd.Timestamp]:
    if pd.isna(s) or not s:
        return []
    out = []
    for part in str(s).split("|"):
        part = part.strip()
        ok = False
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                out.append(pd.to_datetime(part, format=fmt, dayfirst=True))
                ok = True
                break
            except Exception:
                continue
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
        try:
            pairs = re.findall(r"'([^']+)'\s*:\s*([0-9]+)", str(s))
            return {k: int(v) for k, v in pairs}
        except Exception:
            return {}

def split_new_numbers(s: str) -> list[str]:
    if pd.isna(s) or not s: return []
    return [x.strip() for x in str(s).split("|") if x.strip()]

def z4(x) -> str:
    return str(x).strip().zfill(4)

# ----------------------
# Loaders (with leading-zero handling)
# ----------------------
def load_pattern_df(path: str) -> pd.DataFrame:
    # Force number to string, keep leading zeros
    df = pd.read_csv(path, dtype={"number": str})
    df["number"] = df["number"].apply(z4)

    df["dates_list"] = df["dates"].apply(parse_dates_pipe)
    df["first_date"] = df["dates_list"].apply(lambda x: x[0] if x else pd.NaT)
    df["weekday_counts_dict"] = df["weekday_counts"].apply(parse_counts_dict)
    df["month_counts_dict"]   = df["month_counts"].apply(parse_counts_dict)
    return df

def load_new_by_day(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Date is DD/MM/YYYY in your samples
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    df["new_list"] = df["new_numbers"].apply(split_new_numbers)
    # Canonicalize numbers to 4-char strings
    df["new_list"] = df["new_list"].apply(lambda arr: [z4(x) for x in arr])
    return df

# ----------------------
# Helpers
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
    return [k_ for k_, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

# ----------------------
# Checks
# ----------------------
def check_internal_counts(pattern_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in tqdm(pattern_df.iterrows(), total=len(pattern_df), desc="Verify counts from dates"):
        wd_calc, mo_calc = recompute_counts_from_dates(r["dates_list"])
        if wd_calc != r["weekday_counts_dict"] or mo_calc != r["month_counts_dict"]:
            rows.append({
                "number": r["number"],
                "wd_calc": wd_calc,
                "wd_given": r["weekday_counts_dict"],
                "mo_calc": mo_calc,
                "mo_given": r["month_counts_dict"],
            })
    return pd.DataFrame(rows)

def build_first_appearance_map(new_by_day: pd.DataFrame) -> dict[str, pd.Timestamp]:
    first_map = {}
    for _, row in new_by_day.iterrows():
        d = row["date"]
        for n in row["new_list"]:
            if n not in first_map:
                first_map[n] = d
    return first_map

def compare_first_dates(pattern_df: pd.DataFrame, first_map: dict[str, pd.Timestamp]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pat_nums = set(pattern_df["number"])
    new_nums = set(first_map.keys())

    in_both = pattern_df[pattern_df["number"].isin(new_nums)].copy()
    in_both["first_from_new"] = in_both["number"].map(first_map)
    in_both["first_match"] = (in_both["first_date"].dt.normalize() == in_both["first_from_new"].dt.normalize())
    mismatches = in_both[~in_both["first_match"]].copy()

    missing_in_pattern = sorted(new_nums - pat_nums)
    missing_df = pd.DataFrame({"missing_in_pattern": missing_in_pattern})

    pattern_only = sorted(pat_nums - new_nums)
    pattern_only_df = pd.DataFrame({"pattern_only": pattern_only})

    return mismatches, missing_df, pattern_only_df

def calendar_fit_check(new_by_day: pd.DataFrame, pattern_df: pd.DataFrame, topk=2) -> pd.DataFrame:
    pat_map = {}
    for _, r in pattern_df.iterrows():
        pat_map[r["number"]] = {
            "wd": r["weekday_counts_dict"],
            "mo": r["month_counts_dict"]
        }

    rows = []
    for _, row in tqdm(new_by_day.iterrows(), total=len(new_by_day), desc="Calendar-fit on new_numbers"):
        d = row["date"]
        wd = d.day_name()
        mo = d.month_name()
        for n in row["new_list"]:
            info = pat_map.get(n)
            if info is None:
                rows.append({"date": d, "number": n, "has_pattern": False, "wd_fit": np.nan, "mo_fit": np.nan, "both_fit": np.nan})
                continue
            wd_top = top_k_keys(info["wd"], k=topk)
            mo_top = top_k_keys(info["mo"], k=topk)
            wd_fit = wd in wd_top if wd_top else False
            mo_fit = mo in mo_top if mo_top else False
            rows.append({
                "date": d, "number": n, "has_pattern": True,
                "wd_fit": wd_fit, "mo_fit": mo_fit, "both_fit": (wd_fit and mo_fit)
            })
    return pd.DataFrame(rows)

# ----------------------
# CLI + Main
# ----------------------
def main():
    ap = argparse.ArgumentParser(description="Cross-check 5000_number_patterns18.csv against daily new_numbers file.")
    ap.add_argument("--pattern-file", default="5000_number_patterns18.csv", help="Path to 5000_number_patterns18.csv")
    ap.add_argument("--new-file", default="new_5000_prize_numbers_grouped_ist.csv", help="Path to new_5000_prize_numbers_grouped_ist.csv (date,new_numbers_count,new_numbers)")
    ap.add_argument("--topk", type=int, default=2, help="Use top-K weekday/month buckets for calendar-fit (default: 2)")
    ap.add_argument("--no-reports", action="store_true", help="Do not write CSV reports")
    args = ap.parse_args()

    pattern_path = Path(args.pattern_file)
    new_path = Path(args.new_file)
    if not pattern_path.exists():
        raise FileNotFoundError(f"Pattern file not found: {pattern_path}")
    if not new_path.exists():
        raise FileNotFoundError(f"New file not found: {new_path}")

    # Load
    pattern_df = load_pattern_df(str(pattern_path))
    new_by_day = load_new_by_day(str(new_path))

    # Quick sanity
    print(f"Loaded pattern file: {len(pattern_df):,} numbers")
    print(f"Loaded new-by-day file: {len(new_by_day):,} days")
    print("pattern number len counts:", pattern_df["number"].map(len).value_counts().to_dict())

    # 1) Internal consistency
    bad_counts = check_internal_counts(pattern_df)
    if bad_counts.empty:
        print("✓ All weekday/month counts match the dates in the pattern file.")
    else:
        print(f"⚠ Found {len(bad_counts)} numbers with mismatched weekday/month counts (see pattern_counts_mismatch.csv).")

    # 2) First-date alignment
    first_map = build_first_appearance_map(new_by_day)
    mismatches, missing_df, pattern_only_df = compare_first_dates(pattern_df, first_map)
    inter_size = len(pattern_df[pattern_df["number"].isin(first_map.keys())])
    print("\nFirst-date alignment:")
    print(f"  Numbers in pattern ∩ new: {inter_size}")
    print(f"  First-date mismatches: {len(mismatches)}")
    print(f"  New-numbers missing from pattern: {len(missing_df)}")
    print(f"  Numbers in pattern but never seen as 'new': {len(pattern_only_df)}")

    # 3) Calendar fit
    fit_df = calendar_fit_check(new_by_day, pattern_df, topk=args.topk)
    have_pat = fit_df["has_pattern"].sum()
    rate_wd  = fit_df.loc[fit_df["has_pattern"], "wd_fit"].mean()
    rate_mo  = fit_df.loc[fit_df["has_pattern"], "mo_fit"].mean()
    rate_both = fit_df.loc[fit_df["has_pattern"], "both_fit"].mean()
    print("\nCalendar fit on new_numbers (only where pattern exists):")
    print(f"  Rows checked: {have_pat:,}")
    print(f"  Weekday in top-{args.topk}: {rate_wd:.2%}")
    print(f"  Month   in top-{args.topk}: {rate_mo:.2%}")
    print(f"  Both weekday & month in top-{args.topk}: {rate_both:.2%}")

    # 4) Write reports
    if not args.no_reports:
        if not bad_counts.empty:
            bad_counts.to_csv("pattern_counts_mismatch.csv", index=False)
            print("→ Saved pattern_counts_mismatch.csv")
        if not mismatches.empty:
            mismatches[["number","first_date","first_from_new"]].to_csv("first_date_mismatches.csv", index=False)
            print("→ Saved first_date_mismatches.csv")
        if not missing_df.empty:
            missing_df.to_csv("missing_in_pattern.csv", index=False)
            print("→ Saved missing_in_pattern.csv")
        if not pattern_only_df.empty:
            pattern_only_df.to_csv("pattern_only_numbers.csv", index=False)
            print("→ Saved pattern_only_numbers.csv")
        fit_df.to_csv("calendar_fit_new_numbers.csv", index=False)
        print("→ Saved calendar_fit_new_numbers.csv")

if __name__ == "__main__":
    main()