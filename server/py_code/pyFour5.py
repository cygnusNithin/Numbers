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
WDX = {w:i for i,w in enumerate(WEEKDAYS)}
MOX = {m:i for i,m in enumerate(MONTHS)}

# ----------------------
# Parsers
# ----------------------
def parse_dates_pipe(s):
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
            try:
                out.append(pd.to_datetime(part, dayfirst=True))
            except Exception:
                pass
    return sorted(out)

def parse_counts_dict(s):
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

def split_new_numbers(s):
    if pd.isna(s) or not s: return []
    return [x.strip() for x in str(s).split("|") if x.strip()]

def z4(x):
    return str(x).strip().zfill(4)

def digits4(s):
    return [int(c) for c in s]

def parse_any_date(s: str) -> pd.Timestamp:
    if not s:
        return pd.NaT
    try:
        return pd.to_datetime(s, format="%Y-%m-%d")
    except Exception:
        pass
    try:
        return pd.to_datetime(s, dayfirst=True)
    except Exception:
        return pd.NaT

# ----------------------
# Loaders (leading-zero safe)
# ----------------------
def load_pattern_df(path):
    df = pd.read_csv(path, dtype={"number": str})
    df["number"] = df["number"].apply(z4)
    df["dates_list"] = df["dates"].apply(parse_dates_pipe)
    df["first_date"] = df["dates_list"].apply(lambda x: x[0] if x else pd.NaT)
    df["weekday_counts_dict"] = df["weekday_counts"].apply(parse_counts_dict)
    df["month_counts_dict"]   = df["month_counts"].apply(parse_counts_dict)
    return df

def load_new_by_day(path):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    df["new_list"] = df["new_numbers"].apply(split_new_numbers)
    df["new_list"] = df["new_list"].apply(lambda arr: [z4(x) for x in arr])
    return df

# ----------------------
# Helpers
# ----------------------
def recompute_counts_from_dates(dates):
    wd = Counter()
    mo = Counter()
    for d in dates:
        wd[d.day_name()] += 1
        mo[d.month_name()] += 1
    return dict(wd), dict(mo)

def top_k_keys(d, k=2):
    if not d: return []
    return [k_ for k_, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

def filter_dates_before(dates, cutoff):
    return [dt for dt in dates if pd.notna(dt) and dt < cutoff]

# ----------------------
# Checks (full-history)
# ----------------------
def check_internal_counts(pattern_df):
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

def build_first_appearance_map(new_by_day):
    first_map = {}
    for _, row in new_by_day.iterrows():
        d = row["date"]
        for n in row["new_list"]:
            if n not in first_map:
                first_map[n] = d
    return first_map

def compare_first_dates(pattern_df, first_map):
    pat_nums = set(pattern_df["number"])
    new_nums = set(first_map.keys())

    in_both = pattern_df[pattern_df["number"].isin(new_nums)].copy()
    in_both["first_from_new"] = in_both["number"].map(first_map)
    in_both["first_match"] = (in_both["first_date"].dt.normalize() == in_both["first_from_new"].dt.normalize())
    mismatches = in_both[~in_both["first_match"]].copy()

    missing_in_pattern = sorted(new_nums - pat_nums)
    pattern_only = sorted(pat_nums - new_nums)
    missing_df = pd.DataFrame({"missing_in_pattern": missing_in_pattern})
    pattern_only_df = pd.DataFrame({"pattern_only": pattern_only})
    inter_size = len(in_both)
    return inter_size, mismatches, missing_df, pattern_only_df

def calendar_fit_check(new_by_day, pattern_df, topk=2):
    pat_map = {r["number"]: {"wd": r["weekday_counts_dict"], "mo": r["month_counts_dict"]}
               for _, r in pattern_df.iterrows()}
    rows = []
    for _, row in tqdm(new_by_day.iterrows(), total=len(new_by_day), desc="Calendar-fit on new_numbers"):
        d = row["date"]; wd = d.day_name(); mo = d.month_name()
        for n in row["new_list"]:
            info = pat_map.get(n)
            if info is None:
                rows.append({"date": d, "number": n, "has_pattern": False, "wd_fit": np.nan, "mo_fit": np.nan, "both_fit": np.nan})
                continue
            wd_top = top_k_keys(info["wd"], k=topk)
            mo_top = top_k_keys(info["mo"], k=topk)
            wd_fit = wd in wd_top if wd_top else False
            mo_fit = mo in mo_top if mo_top else False
            rows.append({"date": d, "number": n, "has_pattern": True, "wd_fit": wd_fit, "mo_fit": mo_fit, "both_fit": (wd_fit and mo_fit)})
    return pd.DataFrame(rows)

# ----------------------
# No-look-ahead backtest (top-k buckets pre-cutoff)
# ----------------------
def build_pre_cutoff_topk(pattern_df, cutoff, k=2):
    out = {}
    for _, r in pattern_df.iterrows():
        dates = filter_dates_before(r["dates_list"], cutoff)
        if not dates:
            out[r["number"]] = {"wd_top": [], "mo_top": [], "n": 0}
            continue
        wd, mo = recompute_counts_from_dates(dates)
        out[r["number"]] = {"wd_top": top_k_keys(wd, k), "mo_top": top_k_keys(mo, k), "n": len(dates)}
    return out

def calendar_fit_with_cutoff(new_by_day, pattern_df, cutoff, topk=2, eval_start=None):
    cutoff_ts = pd.to_datetime(cutoff)
    eval_start_ts = pd.to_datetime(eval_start) if eval_start else (cutoff_ts + pd.Timedelta(days=1))
    topk_map = build_pre_cutoff_topk(pattern_df, cutoff_ts, k=topk)
    rows = []
    for _, row in tqdm(new_by_day.iterrows(), total=len(new_by_day), desc="Backtest (cutoff)"):
        d = row["date"]
        if d < eval_start_ts:
            continue
        wd = d.day_name(); mo = d.month_name()
        for n in row["new_list"]:
            info = topk_map.get(n)
            if info is None:
                rows.append({"date": d, "number": n, "has_pattern": False, "has_history": False,
                             "wd_fit": np.nan, "mo_fit": np.nan, "both_fit": np.nan})
                continue
            has_hist = (info["n"] > 0)
            if not has_hist:
                rows.append({"date": d, "number": n, "has_pattern": True, "has_history": False,
                             "wd_fit": np.nan, "mo_fit": np.nan, "both_fit": np.nan})
                continue
            wd_fit = wd in info["wd_top"] if info["wd_top"] else False
            mo_fit = mo in info["mo_top"] if info["mo_top"] else False
            rows.append({"date": d, "number": n, "has_pattern": True, "has_history": True,
                         "wd_fit": wd_fit, "mo_fit": mo_fit, "both_fit": (wd_fit and mo_fit)})
    return pd.DataFrame(rows)

def export_topk_table(pattern_df, cutoff, k=2, path="topk_buckets.csv"):
    cutoff_ts = pd.to_datetime(cutoff) if cutoff else None
    rows = []
    for _, r in pattern_df.iterrows():
        dates = r["dates_list"]
        if cutoff_ts is not None:
            dates = filter_dates_before(dates, cutoff_ts)
        wd, mo = recompute_counts_from_dates(dates)
        wd_top = top_k_keys(wd, k); mo_top = top_k_keys(mo, k)
        rows.append({
            "number": r["number"],
            "hits_used": len(dates),
            "top_weekdays": "|".join(wd_top),
            "top_months": "|".join(mo_top),
            "weekday_counts": str(wd),
            "month_counts": str(mo)
        })
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df

# ----------------------
# Calendar–digit model for predicting future "new" numbers
# ----------------------
def build_new_training_rows(new_by_day, cutoff):
    if cutoff is not None:
        train = new_by_day[new_by_day["date"] < cutoff].copy()
    else:
        train = new_by_day.copy()
    rows = []
    for _, r in train.iterrows():
        d = r["date"]; wd = d.day_name(); mo = d.month_name()
        for n in r["new_list"]:
            rows.append({"date": d, "weekday": wd, "month": mo, "number": n})
    return pd.DataFrame(rows)

def build_digit_models(train_rows, alpha=1.0):
    counts_wk = np.full((4, len(WEEKDAYS), 10), alpha, dtype=float)
    counts_mo = np.full((4, len(MONTHS),   10), alpha, dtype=float)
    for _, r in train_rows.iterrows():
        n = r["number"]; wd = r["weekday"]; mo = r["month"]
        w = WDX.get(wd); m = MOX.get(mo)
        if w is None or m is None: continue
        ds = digits4(n)
        for p in range(4):
            counts_wk[p, w, ds[p]] += 1.0
            counts_mo[p, m, ds[p]] += 1.0
    probs_wk = counts_wk / counts_wk.sum(axis=2, keepdims=True)
    probs_mo = counts_mo / counts_mo.sum(axis=2, keepdims=True)
    return probs_wk, probs_mo

def build_expected_counts(new_by_day, cutoff):
    if cutoff is not None:
        df = new_by_day[new_by_day["date"] < cutoff].copy()
    else:
        df = new_by_day.copy()
    df["weekday"] = df["date"].dt.day_name()
    df["month"]   = df["date"].dt.month_name()
    if "new_numbers_count" in df.columns:
        combo = df.groupby(["weekday","month"])["new_numbers_count"].mean()
    else:
        combo = df.assign(cnt=df["new_list"].apply(len)).groupby(["weekday","month"])["cnt"].mean()
    return combo.to_dict()

def score_number_for_date(num, date, probs_wk, probs_mo, w_wk=0.5, w_mo=0.5):
    w = WDX[date.day_name()]
    m = MOX[date.month_name()]
    ds = digits4(num)
    s = 0.0
    for p in range(4):
        s += w_wk * np.log(probs_wk[p, w, ds[p]] + 1e-12)
        s += w_mo * np.log(probs_mo[p, m, ds[p]] + 1e-12)
    return s

def predict_new_numbers(unseen, start, days,
                        probs_wk, probs_mo,
                        expected_counts_map, topn=50, w_wk=0.5, w_mo=0.5,
                        source_label="full-history"):
    rows = []
    for d in pd.date_range(start=start, periods=days, freq="D"):
        wd = d.day_name(); mo = d.month_name()
        exp_cnt = expected_counts_map.get((wd, mo))
        if exp_cnt is None:
            wd_only = np.mean([v for (w, m), v in expected_counts_map.items() if w == wd]) if expected_counts_map else np.nan
            mo_only = np.mean([v for (w, m), v in expected_counts_map.items() if m == mo]) if expected_counts_map else np.nan
            exp_cnt = np.nanmean([wd_only, mo_only]) if not np.isnan(np.nanmean([wd_only, mo_only])) else np.nan
        scores = []
        for num in unseen:
            s = score_number_for_date(num, d, probs_wk, probs_mo, w_wk=w_wk, w_mo=w_mo)
            scores.append((num, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        take = scores[:min(topn, len(scores))]
        for rank, (num, s) in enumerate(take, start=1):
            rows.append({
                "date": d.date().isoformat(),
                "rank": rank,
                "number": num,
                "score": float(s),
                "expected_new_count": None if exp_cnt is None else float(exp_cnt),
                "source": source_label
            })
    return pd.DataFrame(rows)

# ----------------------
# CLI + Main
# ----------------------
def main():
    ap = argparse.ArgumentParser(description="Check patterns + predict future 'new' numbers by calendar–digit model.")
    ap.add_argument("--pattern-file", default="5000_number_patterns18.csv")
    ap.add_argument("--new-file", default="new_5000_prize_numbers_grouped_ist.csv")
    ap.add_argument("--topk", type=int, default=2, help="Top-K buckets for weekday/month (1 or 2) for fit checks.")
    ap.add_argument("--cutoff", type=str, default=None, help="YYYY-MM-DD; learn pattern from dates < cutoff; eval new ≥ cutoff(+1).")
    ap.add_argument("--eval-start", type=str, default=None, help="YYYY-MM-DD; override eval start (defaults to cutoff+1).")
    ap.add_argument("--show-numbers", type=str, default=None, help="Comma-separated numbers to print top-k for (respects cutoff).")
    # Prediction args
    ap.add_argument("--predict-start", type=str, default=None, help="YYYY-MM-DD or DD/MM/YYYY; start date for predictions.")
    ap.add_argument("--predict-days", type=int, default=0, help="How many days to predict.")
    ap.add_argument("--topn", type=int, default=50, help="How many candidate numbers per day to output.")
    ap.add_argument("--alpha", type=float, default=1.0, help="Laplace smoothing for digit models.")
    ap.add_argument("--w-wk", type=float, default=0.5, help="Weight for weekday log-probs.")
    ap.add_argument("--w-mo", type=float, default=0.5, help="Weight for month   log-probs.")
    ap.add_argument("--no-reports", action="store_true")
    args = ap.parse_args()

    # Load CSVs
    pattern_df = load_pattern_df(args.pattern_file)
    new_by_day = load_new_by_day(args.new_file)
    if "new_numbers_count" not in new_by_day.columns:
        new_by_day["new_numbers_count"] = new_by_day["new_list"].apply(len)

    print(f"Loaded pattern file: {len(pattern_df):,} numbers")
    print(f"Loaded new-by-day file: {len(new_by_day):,} days")
    print("pattern number len counts:", pattern_df["number"].map(len).value_counts().to_dict())

    # Default prediction window = last DB date + 1 day (7 days) if no flags
    last_db_date = new_by_day["date"].max().normalize()
    if not args.predict_start and args.predict_days == 0:
        start_dt = last_db_date + pd.Timedelta(days=1)
        args.predict_start = start_dt.date().isoformat()
        args.predict_days = 7
        print(f"(Default) Predicting next {args.predict_days} days from {args.predict_start} (last DB date = {last_db_date.date().isoformat()})")
    else:
        # Accept YYYY-MM-DD or DD/MM/YYYY
        if args.predict_start:
            parsed = parse_any_date(args.predict_start)
            if pd.isna(parsed):
                raise ValueError(f"Could not parse --predict-start: {args.predict_start}. Use YYYY-MM-DD or DD/MM/YYYY.")
            args.predict_start = parsed.date().isoformat()

    # Integrity check
    bad = check_internal_counts(pattern_df)
    print("✓ All weekday/month counts match the dates in the pattern file." if bad.empty
          else f"⚠ Found {len(bad)} mismatches (pattern_counts_mismatch.csv).")
    if not bad.empty and not args.no_reports:
        bad.to_csv("pattern_counts_mismatch.csv", index=False)

    # First-date alignment
    first_map = build_first_appearance_map(new_by_day)
    inter_size, mism, missing_df, pattern_only_df = compare_first_dates(pattern_df, first_map)
    print("\nFirst-date alignment:")
    print(f"  Numbers in pattern ∩ new: {inter_size}")
    print(f"  First-date mismatches: {len(mism)}")
    print(f"  New-numbers missing from pattern: {len(missing_df)}")
    print(f"  Numbers in pattern but never seen as 'new': {len(pattern_only_df)}")

    # Full-history calendar fit (descriptive)
    full_fit = calendar_fit_check(new_by_day, pattern_df, topk=args.topk)
    have_pat = full_fit["has_pattern"].sum()
    print("\nCalendar fit on new_numbers (only where pattern exists):")
    print(f"  Rows checked: {have_pat:,}")
    print(f"  Weekday in top-{args.topk}: {full_fit.loc[full_fit['has_pattern'],'wd_fit'].mean():.2%}")
    print(f"  Month   in top-{args.topk}: {full_fit.loc[full_fit['has_pattern'],'mo_fit'].mean():.2%}")
    print(f"  Both weekday & month in top-{args.topk}: {full_fit.loc[full_fit['has_pattern'],'both_fit'].mean():.2%}")
    if not args.no_reports:
        full_fit.to_csv("calendar_fit_new_numbers1.csv", index=False)
        print("→ Saved calendar_fit_new_numbers1.csv")

    # Show top-k buckets for requested numbers
    if args.show_numbers:
        nums = [z4(x) for x in args.show_numbers.split(",")]
        cutoff_ts = pd.to_datetime(args.cutoff) if args.cutoff else None
        print("\nTop-k buckets for requested numbers" + (f" (using dates < {args.cutoff})" if cutoff_ts is not None else " (full history)") + ":")
        for n in nums:
            row = pattern_df.loc[pattern_df["number"] == n]
            if row.empty:
                print(f"  {n}: not in pattern file")
                continue
            dates = row.iloc[0]["dates_list"]
            if cutoff_ts is not None:
                dates = filter_dates_before(dates, cutoff_ts)
            wd, mo = recompute_counts_from_dates(dates)
            wd_top = top_k_keys(wd, args.topk); mo_top = top_k_keys(mo, args.topk)
            print(f"  {n}: weekdays {wd_top} from {wd} | months {mo_top} from {mo} (hits_used={len(dates)})")

    # Optional no-look-ahead backtest
    if args.cutoff:
        back = calendar_fit_with_cutoff(new_by_day, pattern_df, cutoff=args.cutoff, topk=args.topk, eval_start=args.eval_start)
        have_hist = back["has_history"].sum()
        print(f"\nBacktest with cutoff={args.cutoff} (learn < cutoff; eval ≥ {args.eval_start or str(pd.to_datetime(args.cutoff)+pd.Timedelta(days=1))}):")
        print(f"  Rows with history: {have_hist:,}")
        if have_hist > 0:
            print(f"  Weekday in top-{args.topk}: {back.loc[back['has_history'],'wd_fit'].mean():.2%}")
            print(f"  Month   in top-{args.topk}: {back.loc[back['has_history'],'mo_fit'].mean():.2%}")
            print(f"  Both weekday & month in top-{args.topk}: {back.loc[back['has_history'],'both_fit'].mean():.2%}")
        else:
            print("  No new numbers after cutoff or no prior history for them.")
        if not args.no_reports:
            back.to_csv("calendar_fit_new_numbers_cutoff.csv", index=False)
            export_topk_table(pattern_df, cutoff=args.cutoff, k=args.topk, path="topk_buckets_pre_cutoff.csv")
            print("→ Saved calendar_fit_new_numbers_cutoff.csv")
            print("→ Saved topk_buckets_pre_cutoff.csv")

    # ----------------------
    # Predict actual numbers for future dates (from unseen pool)
    # ----------------------
    if args.predict_start and args.predict_days > 0:
        predict_start = pd.to_datetime(args.predict_start)
        cutoff_ts = pd.to_datetime(args.cutoff) if args.cutoff else None

        # Training rows for digit model (only new/first-appearances)
        train_rows = build_new_training_rows(new_by_day, cutoff=cutoff_ts)
        probs_wk, probs_mo = build_digit_models(train_rows, alpha=args.alpha)
        expected_counts_map = build_expected_counts(new_by_day, cutoff=cutoff_ts)

        # Unseen numbers = 0000..9999 minus pattern numbers
        seen = set(pattern_df["number"].tolist())
        unseen = [z4(i) for i in range(10000) if z4(i) not in seen]
        if not unseen:
            print("\nAll 10,000 numbers have already appeared; there is no unseen pool to predict.")
            return
        print(f"\nUnseen pool size: {len(unseen)} numbers")

        label = "pre-cutoff" if cutoff_ts is not None else "full-history"
        pred_df = predict_new_numbers(
            unseen=unseen,
            start=predict_start,
            days=args.predict_days,
            probs_wk=probs_wk,
            probs_mo=probs_mo,
            expected_counts_map=expected_counts_map,
            topn=args.topn,
            w_wk=args.w_wk,
            w_mo=args.w_mo,
            source_label=label
        )

        pred_path = "predicted_new_numbers1.csv" if not args.cutoff else f"predicted_new_numbers_cutoff_{args.cutoff}.csv"
        pred_df.to_csv(pred_path, index=False)
        print(f"→ Saved {pred_path}")
        # Show a quick peek
        first_date = pred_df["date"].iloc[0]
        print("\nSample predictions (first date):")
        print(pred_df[pred_df["date"]==first_date].head(15).to_string(index=False))

if __name__ == "__main__":
    main()