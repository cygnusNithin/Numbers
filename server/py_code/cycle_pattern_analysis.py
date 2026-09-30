"""
cycle_pattern_analysis.py

Numbers / AbsoluteData pattern research.

Purpose:
1. Reconstruct the historical draw matrix from absolute_data_number_patterns.csv.
2. Verify user-proposed cycle boundaries.
3. Independently discover cycles using the same rule as server/routes/utils/cycleAnalysis.js:
      start a cycle -> collect unique 4-digit numbers -> when all 10,000
      have appeared, close the cycle and start the next one.
4. Compare cycle statistics.
5. Test whether previous-cycle behavior predicts the next cycle.
6. Build a cycle-aware score for the currently incomplete cycle.
7. Run simple leakage-free temporal baselines.

This is research code, not a guarantee of future lottery outcomes.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


TOTAL_NUMBERS = 10_000


def parse_date(s: str):
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format: {s}")


def number_string(x) -> str:
    return f"{int(x):04d}"


def load_history(csv_path: str):
    df = pd.read_csv(csv_path)

    required = {"number", "dates"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    date_to_numbers = defaultdict(set)

    for number, raw_dates in zip(df["number"].values, df["dates"].values):
        n = number_string(number)

        if pd.isna(raw_dates):
            continue

        for value in str(raw_dates).split("|"):
            value = value.strip()
            if not value:
                continue
            date_to_numbers[parse_date(value)].add(n)

    dates = sorted(date_to_numbers)

    # Dense occurrence matrix:
    # rows = historical draw dates
    # cols = 0000..9999
    matrix = np.zeros((len(dates), TOTAL_NUMBERS), dtype=np.bool_)

    for r, d in enumerate(dates):
        for n in date_to_numbers[d]:
            matrix[r, int(n)] = True

    return df, dates, date_to_numbers, matrix


def discover_cycles(dates, date_to_numbers):
    """
    Same conceptual rule used by server/routes/utils/cycleAnalysis.js:
    accumulate unique numbers until all 10,000 have appeared.
    """
    cycles = []
    start = 0

    while start < len(dates):
        seen = set()
        end = None

        for i in range(start, len(dates)):
            seen.update(date_to_numbers[dates[i]])

            if len(seen) == TOTAL_NUMBERS:
                end = i
                break

        if end is None:
            cycles.append(
                {
                    "cycle": len(cycles) + 1,
                    "status": "IN_PROGRESS",
                    "start": dates[start].isoformat(),
                    "end": dates[-1].isoformat(),
                    "date_count": len(dates) - start,
                    "unique": len(seen),
                    "missing": sorted(
                        set(f"{i:04d}" for i in range(TOTAL_NUMBERS)) - seen
                    ),
                }
            )
            break

        cycles.append(
            {
                "cycle": len(cycles) + 1,
                "status": "COMPLETED",
                "start": dates[start].isoformat(),
                "end": dates[end].isoformat(),
                "date_count": end - start + 1,
                "unique": TOTAL_NUMBERS,
                "missing": [],
            }
        )

        start = end + 1

    return cycles


def parse_user_cycles():
    # Exactly as supplied by the user.
    raw = [
        ("C1", "11/07/2020", "30/01/2023"),
        ("C2", "31/01/2023", "23/01/2024"),
        ("C3", "25/01/2024", "12/03/2025"),
        ("C4", "13/03/2025", "14/12/2025"),
        ("C5", "14/12/2025", "25/09/2026"),
    ]

    return [
        {
            "cycle": name,
            "start": parse_date(start).isoformat(),
            "end": parse_date(end).isoformat(),
        }
        for name, start, end in raw
    ]


def evaluate_cycle_definitions(dates, date_to_numbers, definitions):
    all_numbers = set(f"{i:04d}" for i in range(TOTAL_NUMBERS))
    output = []

    for c in definitions:
        start = parse_date(c["start"])
        end = parse_date(c["end"])

        selected_dates = [d for d in dates if start <= d <= end]
        seen = set()

        for d in selected_dates:
            seen.update(date_to_numbers[d])

        missing = sorted(all_numbers - seen)

        output.append(
            {
                **c,
                "actual_first_date": selected_dates[0].isoformat()
                if selected_dates
                else None,
                "actual_last_date": selected_dates[-1].isoformat()
                if selected_dates
                else None,
                "date_count": len(selected_dates),
                "unique": len(seen),
                "missing_count": len(missing),
                "missing_numbers": missing,
            }
        )

    return output


def cycle_ranges_from_discovered(cycles, dates):
    ranges = []

    for c in cycles:
        start = parse_date(c["start"])
        end = parse_date(c["end"])

        if c["status"] == "COMPLETED":
            idx = [i for i, d in enumerate(dates) if start <= d <= end]
        else:
            idx = [i for i, d in enumerate(dates) if d >= start]

        if idx:
            ranges.append((c["cycle"], idx[0], idx[-1], c["status"]))

    return ranges


def cycle_number_statistics(matrix, ranges):
    """
    For every complete cycle, calculate:
      - number occurrence count
      - first occurrence draw position
      - last occurrence draw position
      - percentage of cycle elapsed at first occurrence
    """
    result = []

    for cycle_no, start, end, status in ranges:
        if status != "COMPLETED":
            continue

        block = matrix[start : end + 1]
        counts = block.sum(axis=0).astype(np.int32)

        first = np.argmax(block, axis=0).astype(np.int32)

        # argmax returns 0 for all-false columns, but completed cycles have
        # every number at least once.
        last_from_end = np.argmax(block[::-1], axis=0).astype(np.int32)
        last = block.shape[0] - 1 - last_from_end

        result.append(
            {
                "cycle": cycle_no,
                "length": block.shape[0],
                "counts": counts,
                "first": first,
                "last": last,
            }
        )

    return result


def consecutive_cycle_correlations(stats):
    rows = []

    for a, b in zip(stats, stats[1:]):
        count_corr = np.corrcoef(a["counts"], b["counts"])[0, 1]
        first_corr = np.corrcoef(a["first"], b["first"])[0, 1]
        last_corr = np.corrcoef(a["last"], b["last"])[0, 1]

        rows.append(
            {
                "cycle_a": a["cycle"],
                "cycle_b": b["cycle"],
                "count_correlation": float(count_corr),
                "first_position_correlation": float(first_corr),
                "last_position_correlation": float(last_corr),
            }
        )

    return rows


def cycle_rank_score(stats, current_counts, current_seen):
    """
    Cycle-aware heuristic.

    The historical evidence should determine whether this score is useful.
    It deliberately does NOT assume that "overdue" means "more likely".

    Components:
      A) numbers still unseen in current cycle
      B) historical count rank across previous completed cycles
      C) historical first/last position tendencies
    """
    n = TOTAL_NUMBERS

    unseen = ~current_seen

    if not stats:
        score = unseen.astype(np.float64)
        return score

    prev_counts = np.stack([x["counts"] for x in stats], axis=0)
    mean_counts = prev_counts.mean(axis=0)

    # Rank-normalized historical frequency.
    order = np.argsort(np.argsort(mean_counts))
    freq_rank = order / max(1, n - 1)

    # Prefer numbers unseen in the current cycle only as a candidate constraint,
    # not as an automatic probability claim.
    score = 0.70 * unseen.astype(np.float64) + 0.30 * freq_rank

    return score


def topk_hits(scores, actual_row, k):
    idx = np.argpartition(scores, -k)[-k:]
    return int(actual_row[idx].sum())


def random_expected_hits(k, actual_count):
    return k * actual_count / TOTAL_NUMBERS


def run_recent_baseline_backtest(matrix, min_history=300, ks=(10, 25, 50, 100)):
    """
    Simple leakage-free benchmark.

    At each test date:
      - frequency = count of prior draws
      - recent30 = count in previous 30 draws
      - recent90 = count in previous 90 draws
      - overdue = current draw index - last seen index

    Evaluates top-K hit count against the exact random expectation.
    """
    rows = []

    last_seen = np.full(TOTAL_NUMBERS, -1, dtype=np.int32)
    cumulative = np.zeros(TOTAL_NUMBERS, dtype=np.int32)

    for t in range(matrix.shape[0]):
        actual = matrix[t]

        if t >= min_history:
            recent30 = matrix[max(0, t - 30) : t].sum(axis=0)
            recent90 = matrix[max(0, t - 90) : t].sum(axis=0)

            gap = np.where(last_seen >= 0, t - last_seen, t + 1)

            scores = {
                "frequency": cumulative.astype(np.float64),
                "recent30": recent30.astype(np.float64),
                "recent90": recent90.astype(np.float64),
                "frequency_recent_blend": (
                    cumulative / max(1, t)
                    + 2.0 * recent30
                    + 1.0 * recent90
                ),
                "overdue": gap.astype(np.float64),
            }

            for name, score in scores.items():
                for k in ks:
                    hits = topk_hits(score, actual, k)
                    expected = random_expected_hits(k, int(actual.sum()))

                    rows.append(
                        {
                            "draw_index": t,
                            "method": name,
                            "k": k,
                            "actual_hits_in_draw": int(actual.sum()),
                            "hits": hits,
                            "random_expected": expected,
                            "lift": hits / expected if expected else np.nan,
                        }
                    )

        cumulative += actual.astype(np.int32)
        last_seen[actual] = t

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="absolute_data_number_patterns.csv",
        help="Path to absolute_data_number_patterns.csv",
    )
    parser.add_argument(
        "--output",
        default="cycle_pattern_report",
        help="Output directory",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df, dates, date_to_numbers, matrix = load_history(args.csv)

    print(f"Rows in CSV: {len(df):,}")
    print(f"Historical dates: {len(dates):,}")
    print(f"Date range: {dates[0]} -> {dates[-1]}")
    print(f"Total recorded number/date hits: {int(matrix.sum()):,}")

    discovered = discover_cycles(dates, date_to_numbers)
    user_cycles = parse_user_cycles()
    user_eval = evaluate_cycle_definitions(
        dates, date_to_numbers, user_cycles
    )

    stats = cycle_number_statistics(
        matrix, cycle_ranges_from_discovered(discovered, dates)
    )
    correlations = consecutive_cycle_correlations(stats)

    # Current discovered cycle.
    current = discovered[-1]
    current_start = parse_date(current["start"])
    current_dates = [d for d in dates if d >= current_start]
    current_seen = np.zeros(TOTAL_NUMBERS, dtype=bool)

    for d in current_dates:
        for n in date_to_numbers[d]:
            current_seen[int(n)] = True

    cycle_scores = cycle_rank_score(stats, None, current_seen)

    ranking = pd.DataFrame(
        {
            "number": [f"{i:04d}" for i in range(TOTAL_NUMBERS)],
            "score": cycle_scores,
            "seen_in_current_cycle": current_seen,
            "remaining_in_current_cycle": ~current_seen,
        }
    ).sort_values(
        ["remaining_in_current_cycle", "score"],
        ascending=[False, False],
    )

    baseline = run_recent_baseline_backtest(matrix)

    with open(output_dir / "cycle_report.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "csv_rows": len(df),
                "date_count": len(dates),
                "first_date": dates[0].isoformat(),
                "last_date": dates[-1].isoformat(),
                "repo_style_cycles": discovered,
                "user_proposed_cycles": user_eval,
                "consecutive_cycle_correlations": correlations,
                "current_cycle_missing_count": int((~current_seen).sum()),
            },
            f,
            indent=2,
        )

    pd.DataFrame(correlations).to_csv(
        output_dir / "cycle_correlations.csv", index=False
    )
    pd.DataFrame(user_eval).to_csv(
        output_dir / "user_cycle_verification.csv", index=False
    )
    ranking.to_csv(
        output_dir / "cycle_aware_ranking.csv", index=False
    )

    baseline.groupby("method", as_index=False).agg(
        mean_hits=("hits", "mean"),
        mean_random_expected=("random_expected", "mean"),
        mean_lift=("lift", "mean"),
    ).to_csv(output_dir / "baseline_summary.csv", index=False)

    baseline.to_csv(output_dir / "baseline_backtest.csv", index=False)

    print("\n=== REPOSITORY-STYLE CYCLES ===")
    for c in discovered:
        print(
            f"Cycle {c['cycle']}: {c['start']} -> {c['end']} | "
            f"{c['unique']:,} unique | missing {len(c['missing']):,} | "
            f"{c['status']}"
        )

    print("\n=== USER-PROPOSED CYCLES ===")
    for c in user_eval:
        print(
            f"{c['cycle']}: {c['start']} -> {c['end']} | "
            f"{c['unique']:,} unique | missing {c['missing_count']:,}"
        )
        if c["missing_numbers"]:
            print("   missing:", ", ".join(c["missing_numbers"][:20]))

    print("\n=== CONSECUTIVE CYCLE CORRELATIONS ===")
    for r in correlations:
        print(
            f"{r['cycle_a']} -> {r['cycle_b']} | "
            f"count={r['count_correlation']:.4f}, "
            f"first={r['first_position_correlation']:.4f}, "
            f"last={r['last_position_correlation']:.4f}"
        )

    print("\n=== CURRENT CYCLE ===")
    print(
        f"{current['start']} -> {current['end']} | "
        f"{current['unique']:,}/10,000 | "
        f"missing {len(current['missing']):,}"
    )
    print("Missing numbers:", ", ".join(current["missing"]))

    print(f"\nReports written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
