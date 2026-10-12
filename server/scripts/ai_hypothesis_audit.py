from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
from scipy.stats import chisquare, pearsonr


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_CSV = DATA_DIR / "ai_training_draws.csv"
NUMBERS_CSV = DATA_DIR / "ai_training_draw_numbers.csv"

NUMBER_COUNT = 10_000
BLOCK_COUNT = 8

OUT_FREQUENCY = RESULTS_DIR / "ai_audit_number_frequency.csv"
OUT_DIGITS = RESULTS_DIR / "ai_audit_digit_positions.csv"
OUT_BLOCKS = RESULTS_DIR / "ai_audit_period_stability.csv"
OUT_SUMMARY = RESULTS_DIR / "ai_audit_summary.json"


# ============================================================
# HELPERS
# ============================================================

def require_columns(df, columns, label):
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label} missing columns: {missing}")


def normalize_number(value):
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit() or len(text) > 4:
        return None

    value = int(text)

    return value if 0 <= value <= 9999 else None


def chi_square_uniform(observed):
    observed = np.asarray(observed, dtype=np.float64)
    expected = np.full(
        len(observed),
        observed.sum() / len(observed),
        dtype=np.float64,
    )

    result = chisquare(observed, f_exp=expected)

    return {
        "chi_square": float(result.statistic),
        "degrees_of_freedom": int(len(observed) - 1),
        "p_value": float(result.pvalue),
        "expected_per_category": float(expected[0]),
    }


def main():
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading canonical CSV exports...")

    draws = pd.read_csv(
        DRAWS_CSV,
        dtype={"serialNumber": str},
    )

    numbers = pd.read_csv(
        NUMBERS_CSV,
        dtype={"serialNumber": str},
    )

    require_columns(
        draws,
        ["event_order", "serialNumber", "date"],
        "Draw events CSV",
    )

    require_columns(
        numbers,
        ["event_order", "number"],
        "Draw numbers CSV",
    )

    draws["event_order"] = pd.to_numeric(
        draws["event_order"], errors="raise"
    ).astype(np.int64)

    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="raise"
    ).astype(np.int64)

    draws = draws.sort_values("event_order").reset_index(drop=True)

    if draws["event_order"].duplicated().any():
        raise ValueError("Duplicate event_order values found.")

    event_orders = draws["event_order"].to_numpy()

    event_to_index = {
        int(event_order): i
        for i, event_order in enumerate(event_orders)
    }

    unknown_events = (
        set(numbers["event_order"].unique())
        - set(event_to_index)
    )

    if unknown_events:
        raise ValueError(
            f"{len(unknown_events)} unknown event_order values "
            "were found in the number CSV."
        )

    numbers["number_id"] = numbers["number"].map(normalize_number)

    invalid_rows = int(numbers["number_id"].isna().sum())
    numbers = numbers.dropna(subset=["number_id"]).copy()
    numbers["number_id"] = numbers["number_id"].astype(np.int32)

    numbers["draw_index"] = numbers["event_order"].map(
        event_to_index
    ).astype(np.int32)

    presence = np.zeros(
        (len(draws), NUMBER_COUNT),
        dtype=np.bool_,
    )

    presence[
        numbers["draw_index"].to_numpy(),
        numbers["number_id"].to_numpy(),
    ] = True

    draw_sizes = presence.sum(axis=1).astype(np.int32)
    number_hits = presence.sum(axis=0).astype(np.int32)

    total_appearances = int(number_hits.sum())
    overall_hit_rate = float(presence.mean())

    print(f"Draws: {len(draws):,}")
    print(f"Invalid rows ignored: {invalid_rows:,}")
    print(f"Unique dates: {draws['date'].nunique():,}")
    print(f"Valid distinct number appearances: {total_appearances:,}")
    print(f"Overall number-draw hit rate: {overall_hit_rate:.6%}")

    # --------------------------------------------------------
    # TEST 1: Number frequencies versus uniform distribution
    # --------------------------------------------------------

    print("\nTesting number-frequency distribution...")

    frequency_test = chi_square_uniform(number_hits)

    mean_hits = float(number_hits.mean())
    variance_hits = float(number_hits.var(ddof=1))
    dispersion_ratio = variance_hits / mean_hits if mean_hits else 0.0

    ids = np.arange(NUMBER_COUNT, dtype=np.int32)

    frequency_df = pd.DataFrame({
        "number": [f"{n:04d}" for n in ids],
        "total_hits": number_hits,
        "hit_rate": number_hits / len(draws),
        "rank": pd.Series(number_hits).rank(
            method="min",
            ascending=False,
        ).astype(int),
    }).sort_values(
        ["total_hits", "number"],
        ascending=[False, True],
    )

    frequency_df.to_csv(OUT_FREQUENCY, index=False)

    # --------------------------------------------------------
    # TEST 2: Digit position frequencies
    # --------------------------------------------------------

    print("Testing digit positions...")

    present_ids = np.flatnonzero(presence)
    appearance_numbers = (
        np.tile(np.arange(NUMBER_COUNT, dtype=np.int32), len(draws))
    )

    # Avoid constructing a flattened 20-million-entry array.
    position_counts = np.zeros((4, 10), dtype=np.int64)

    for position in range(4):
        divisor = 10 ** (3 - position)
        digits = (present_ids // divisor) % 10
        position_counts[position] = np.bincount(
            digits, minlength=10
        )

    digit_rows = []

    digit_tests = []

    for position in range(4):
        test = chi_square_uniform(position_counts[position])
        digit_tests.append(test)

        for digit in range(10):
            digit_rows.append({
                "position": position + 1,
                "digit": digit,
                "observed_count": int(
                    position_counts[position, digit]
                ),
                "expected_count": (
                    total_appearances / 10
                ),
                "observed_expected_ratio": (
                    position_counts[position, digit]
                    / (total_appearances / 10)
                    if total_appearances else 0
                ),
                "position_chi_square": test["chi_square"],
                "position_p_value": test["p_value"],
            })

    pd.DataFrame(digit_rows).to_csv(OUT_DIGITS, index=False)

    # --------------------------------------------------------
    # TEST 3: Repeated-digit structure
    # --------------------------------------------------------

    print("Testing repeated-digit structure...")

    universe_digits = np.array([
        list(f"{n:04d}") for n in range(NUMBER_COUNT)
    ], dtype="U1")

    repeated_categories = np.array([
        4 - len(set(row.tolist()))
        for row in universe_digits
    ])

    observed_repeated = np.bincount(
        repeated_categories[present_ids % NUMBER_COUNT],
        minlength=4,
    )

    # Expected category shares from all 10,000 possible numbers.
    universe_category_counts = np.bincount(
        repeated_categories,
        minlength=4,
    )

    expected_repeated = (
        universe_category_counts
        * total_appearances
        / NUMBER_COUNT
    )

    repeated_test = chisquare(
        observed_repeated,
        f_exp=expected_repeated,
    )

    repeated_summary = {
        "chi_square": float(repeated_test.statistic),
        "degrees_of_freedom": 3,
        "p_value": float(repeated_test.pvalue),
        "categories": {},
    }

    for category in range(4):
        repeated_summary["categories"][str(category)] = {
            "observed": int(observed_repeated[category]),
            "expected": float(expected_repeated[category]),
        }

    # --------------------------------------------------------
    # TEST 4: Frequency stability across chronological blocks
    # --------------------------------------------------------

    print("Testing frequency stability across time...")

    blocks = np.array_split(np.arange(len(draws)), BLOCK_COUNT)
    block_hit_matrix = np.vstack([
        presence[block].sum(axis=0)
        for block in blocks
    ])

    block_rows = []

    for block_index, block in enumerate(blocks):
        start_date = str(draws.iloc[block[0]]["date"])
        end_date = str(draws.iloc[block[-1]]["date"])

        hits = block_hit_matrix[block_index]

        block_rows.append({
            "block": block_index + 1,
            "draws": len(block),
            "start_date": start_date,
            "end_date": end_date,
            "total_number_hits": int(hits.sum()),
            "mean_hits_per_number": float(hits.mean()),
            "std_hits_per_number": float(hits.std(ddof=1)),
            "max_hits_for_one_number": int(hits.max()),
            "min_hits_for_one_number": int(hits.min()),
            "distinct_numbers_seen": int(np.count_nonzero(hits)),
            "mean_distinct_numbers_per_draw": float(
                draw_sizes[block].mean()
            ),
        })

    block_df = pd.DataFrame(block_rows)
    block_df.to_csv(OUT_BLOCKS, index=False)

    # Compare frequency rankings in the first and second halves.
    midpoint = len(draws) // 2

    first_half_hits = presence[:midpoint].sum(axis=0)
    second_half_hits = presence[midpoint:].sum(axis=0)

    rank_correlation, rank_correlation_p = pearsonr(
        first_half_hits,
        second_half_hits,
    )

    # --------------------------------------------------------
    # TEST 5: Draw-size stability
    # --------------------------------------------------------

    print("Testing distinct-number counts per draw...")

    first_sizes = draw_sizes[:midpoint]
    second_sizes = draw_sizes[midpoint:]

    # Descriptive difference only. Draws may differ in format or
    # prize-row structure; a difference is not automatically bias.
    draw_size_summary = {
        "first_half_mean": float(first_sizes.mean()),
        "second_half_mean": float(second_sizes.mean()),
        "first_half_std": float(first_sizes.std(ddof=1)),
        "second_half_std": float(second_sizes.std(ddof=1)),
        "mean_difference_second_minus_first": float(
            second_sizes.mean() - first_sizes.mean()
        ),
        "minimum": int(draw_sizes.min()),
        "maximum": int(draw_sizes.max()),
    }

    # --------------------------------------------------------
    # Multiple-testing adjustment
    # --------------------------------------------------------

    # The five primary tests are:
    # number-frequency uniformity, four digit positions, and
    # repeated-digit structure. Apply Bonferroni to these six tests.
    primary_p_values = [
        frequency_test["p_value"],
        *[test["p_value"] for test in digit_tests],
        float(repeated_test.pvalue),
    ]

    primary_names = [
        "number_frequency_uniformity",
        "digit_position_1",
        "digit_position_2",
        "digit_position_3",
        "digit_position_4",
        "repeated_digit_structure",
    ]

    adjusted_tests = {}

    for name, p_value in zip(primary_names, primary_p_values):
        adjusted_tests[name] = {
            "raw_p_value": float(p_value),
            "bonferroni_adjusted_p_value": float(
                min(1.0, p_value * len(primary_p_values))
            ),
            "significant_at_adjusted_0_05": bool(
                p_value * len(primary_p_values) < 0.05
            ),
        }

    summary = {
        "dataset": {
            "draw_count": int(len(draws)),
            "unique_dates": int(draws["date"].nunique()),
            "first_date": str(draws.iloc[0]["date"]),
            "last_date": str(draws.iloc[-1]["date"]),
            "invalid_number_rows_ignored": invalid_rows,
            "total_distinct_number_draw_appearances": total_appearances,
            "mean_distinct_numbers_per_draw": float(draw_sizes.mean()),
            "overall_number_draw_hit_rate": overall_hit_rate,
        },
        "number_frequency": {
            **frequency_test,
            "mean_hits_per_number": mean_hits,
            "variance_hits_per_number": variance_hits,
            "variance_to_mean_ratio": float(dispersion_ratio),
            "most_frequent_numbers": frequency_df.head(20)[
                ["number", "total_hits", "hit_rate"]
            ].to_dict(orient="records"),
            "least_frequent_numbers": frequency_df.tail(20)[
                ["number", "total_hits", "hit_rate"]
            ].to_dict(orient="records"),
        },
        "digit_positions": {
            f"position_{i + 1}": digit_tests[i]
            for i in range(4)
        },
        "repeated_digit_structure": repeated_summary,
        "frequency_stability": {
            "first_half_draws": int(midpoint),
            "second_half_draws": int(len(draws) - midpoint),
            "first_half_second_half_frequency_correlation": float(
                rank_correlation
            ),
            "correlation_p_value": float(rank_correlation_p),
            "interpretation_note": (
                "Correlation describes historical stability; it does "
                "not establish future predictive power."
            ),
        },
        "draw_size_stability": draw_size_summary,
        "multiple_testing": {
            "method": "Bonferroni",
            "primary_test_count": len(primary_p_values),
            "tests": adjusted_tests,
        },
        "outputs": {
            "number_frequency": str(OUT_FREQUENCY),
            "digit_positions": str(OUT_DIGITS),
            "period_stability": str(OUT_BLOCKS),
        },
        "elapsed_seconds": round(time.time() - started, 2),
        "caution": (
            "These are exploratory diagnostics. Significant results can "
            "reflect data collection, prize structure, dependence, or "
            "chance. Confirm any candidate finding on untouched data "
            "before building a prediction model."
        ),
    }

    OUT_SUMMARY.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print("HYPOTHESIS AUDIT COMPLETE")
    print("=" * 72)

    print("\nNumber frequency:")
    print(f"  Mean hits per number: {mean_hits:.3f}")
    print(f"  Variance/mean ratio: {dispersion_ratio:.4f}")
    print(f"  Chi-square p-value: {frequency_test['p_value']:.6g}")

    print("\nDigit-position uniformity tests:")
    for i, test in enumerate(digit_tests, start=1):
        print(
            f"  Position {i}: p={test['p_value']:.6g}, "
            f"Bonferroni p="
            f"{adjusted_tests[f'digit_position_{i}']['bonferroni_adjusted_p_value']:.6g}"
        )

    print("\nRepeated-digit structure:")
    print(f"  p-value: {repeated_test.pvalue:.6g}")

    print("\nFrequency stability:")
    print(f"  First-half/second-half correlation: {rank_correlation:.4f}")
    print(f"  Correlation p-value: {rank_correlation_p:.6g}")

    print("\nMean distinct numbers per draw:")
    print(f"  First half: {first_sizes.mean():.2f}")
    print(f"  Second half: {second_sizes.mean():.2f}")

    print("\nTop 20 historical frequencies:")
    print(frequency_df.head(20).to_string(index=False))

    print("\nSaved:")
    print(f"  {OUT_FREQUENCY}")
    print(f"  {OUT_DIGITS}")
    print(f"  {OUT_BLOCKS}")
    print(f"  {OUT_SUMMARY}")
    print(f"\nElapsed: {time.time() - started:.2f} seconds")


if __name__ == "__main__":
    main()