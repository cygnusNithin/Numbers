
from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
from scipy.stats import binomtest


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

RESULTS_DIR = ROOT / "data" / "ai-training" / "results"
INPUT_CSV = RESULTS_DIR / "ai_train_v1_per_draw.csv"

PAIRED_OUTPUT = RESULTS_DIR / "ai_train_v1_paired_comparison.csv"
PERIOD_OUTPUT = RESULTS_DIR / "ai_train_v1_period_comparison.csv"
DIFFERENCES_OUTPUT = RESULTS_DIR / "ai_train_v1_paired_draw_differences.csv"
METADATA_OUTPUT = RESULTS_DIR / "ai_train_v1_validation_metadata.json"

TOP_K_VALUES = [10, 25, 50, 100]

# 3 comparisons x 4 Top-K values = 12 comparisons.
MODELS_TO_COMPARE = [
    "hist_gradient_boosting",
    "logistic_regression",
    "random",
]
BASELINE_MODEL = "historical_frequency"

BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_BLOCK_LENGTH = 20
PERIOD_BLOCK_SIZE = 100
RANDOM_SEED = 42


# ============================================================
# UTILITIES
# ============================================================

def require_columns(df, required):
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(
            f"Input CSV is missing required columns: {missing}"
        )


def circular_block_bootstrap_ci(
    differences,
    replicates=BOOTSTRAP_REPLICATES,
    block_length=BOOTSTRAP_BLOCK_LENGTH,
    seed=RANDOM_SEED,
):
    """
    Circular moving-block bootstrap for the mean paired difference.

    Draws are kept in chronological order. Blocks preserve some local
    dependence between adjacent draws. This is an approximate interval,
    not a guarantee of statistical independence.
    """
    values = np.asarray(differences, dtype=float)
    values = values[np.isfinite(values)]

    n = len(values)
    if n == 0:
        return np.nan, np.nan

    if n == 1:
        return float(values[0]), float(values[0])

    block_length = max(1, min(block_length, n))
    blocks_needed = int(np.ceil(n / block_length))
    rng = np.random.default_rng(seed)

    offsets = np.arange(block_length)
    bootstrap_means = np.empty(replicates, dtype=float)

    for i in range(replicates):
        starts = rng.integers(0, n, size=blocks_needed)

        indices = (
            starts[:, None] + offsets[None, :]
        ) % n

        sampled = values[indices.ravel()[:n]]
        bootstrap_means[i] = sampled.mean()

    lower, upper = np.quantile(
        bootstrap_means, [0.025, 0.975]
    )
    return float(lower), float(upper)


def sign_test(wins, losses):
    """
    Exact two-sided binomial sign test, excluding ties.

    Its p-value does not account for serial dependence across draws.
    """
    n = int(wins + losses)

    if n == 0:
        return np.nan

    return float(
        binomtest(
            int(wins),
            n=n,
            p=0.5,
            alternative="two-sided",
        ).pvalue
    )


def safe_relative_improvement(mean_difference, baseline_mean):
    if abs(baseline_mean) < 1e-12:
        return np.nan

    return float(mean_difference / baseline_mean * 100.0)


# ============================================================
# LOAD AND VALIDATE INPUT
# ============================================================

def main():
    started = time.time()

    print("Loading per-draw evaluation results...")
    print(f"Input: {INPUT_CSV}")

    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            f"Cannot find input CSV:\n{INPUT_CSV}\n"
            "Run ai_train_v1.py first."
        )

    df = pd.read_csv(
        INPUT_CSV,
        dtype={"date": str},
    )

    required_columns = [
        "event_order",
        "date",
        "test_index",
        "model",
        "top_k",
        "hits",
        "precision",
        "recall",
        "actual_distinct_numbers",
    ]
    require_columns(df, required_columns)

    if df.empty:
        raise ValueError("The input CSV contains no rows.")

    numeric_columns = [
        "event_order",
        "test_index",
        "top_k",
        "hits",
        "precision",
        "recall",
        "actual_distinct_numbers",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column], errors="raise"
        )

    df["model"] = df["model"].astype(str)
    df["date"] = df["date"].astype(str)

    expected_models = set(MODELS_TO_COMPARE + [BASELINE_MODEL])
    found_models = set(df["model"].unique())
    missing_models = sorted(expected_models - found_models)

    if missing_models:
        raise ValueError(
            "The input CSV is missing expected models: "
            f"{missing_models}"
        )

    df = df[df["top_k"].isin(TOP_K_VALUES)].copy()

    # One row per event, model and Top-K value is expected.
    duplicate_mask = df.duplicated(
        subset=["event_order", "model", "top_k"],
        keep=False,
    )

    if duplicate_mask.any():
        examples = df.loc[
            duplicate_mask,
            ["event_order", "model", "top_k"],
        ].head(10)

        raise ValueError(
            "Duplicate event/model/Top-K rows found:\n"
            f"{examples.to_string(index=False)}"
        )

    # Check that each event has all expected model/Top-K rows.
    expected_row_count = len(expected_models) * len(TOP_K_VALUES)

    rows_per_event = df.groupby("event_order").size()
    bad_events = rows_per_event[
        rows_per_event != expected_row_count
    ]

    if not bad_events.empty:
        raise ValueError(
            "Some events do not contain all expected model/Top-K "
            f"rows. Expected {expected_row_count} rows per event. "
            f"First problematic event orders: "
            f"{bad_events.head(10).to_dict()}"
        )

    # All models for the same event must refer to the same draw.
    consistency = df.groupby("event_order").agg(
        date_count=("date", "nunique"),
        test_index_count=("test_index", "nunique"),
    )

    inconsistent = consistency[
        (consistency["date_count"] != 1)
        | (consistency["test_index_count"] != 1)
    ]

    if not inconsistent.empty:
        raise ValueError(
            "Inconsistent dates or test indices found for events: "
            f"{inconsistent.head(10).index.tolist()}"
        )

    df = df.sort_values(
        ["test_index", "event_order", "top_k", "model"]
    ).reset_index(drop=True)

    event_table = (
        df[["event_order", "date", "test_index"]]
        .drop_duplicates()
        .sort_values(["test_index", "event_order"])
        .reset_index(drop=True)
    )

    event_orders = event_table["event_order"].tolist()
    number_of_events = len(event_table)

    print(f"Unique test draws: {number_of_events}")
    print(f"Models: {', '.join(sorted(found_models))}")
    print(f"Top-K values: {TOP_K_VALUES}")
    print(
        "Bootstrap: "
        f"{BOOTSTRAP_REPLICATES:,} replicates, "
        f"block length {BOOTSTRAP_BLOCK_LENGTH}"
    )

    # Wide table for paired comparisons.
    wide = df.pivot(
        index=["event_order", "date", "test_index"],
        columns=["model", "top_k"],
        values="hits",
    ).sort_index()

    for top_k in TOP_K_VALUES:
        baseline_key = (BASELINE_MODEL, top_k)

        if baseline_key not in wide.columns:
            raise ValueError(
                f"Missing baseline results for Top-{top_k}."
            )

        for model in MODELS_TO_COMPARE:
            model_key = (model, top_k)

            if model_key not in wide.columns:
                raise ValueError(
                    f"Missing {model} results for Top-{top_k}."
                )

            if wide[[model_key, baseline_key]].isna().any().any():
                raise ValueError(
                    f"Missing paired hit values for {model}, "
                    f"Top-{top_k}."
                )

    # ========================================================
    # PAIRED COMPARISONS
    # ========================================================

    print("\nCalculating paired comparisons...")

    comparison_rows = []
    difference_rows = []

    comparison_number = 0
    total_comparisons = (
        len(MODELS_TO_COMPARE) * len(TOP_K_VALUES)
    )

    for model in MODELS_TO_COMPARE:
        for top_k in TOP_K_VALUES:
            comparison_number += 1

            model_hits = wide[(model, top_k)].to_numpy(dtype=float)
            baseline_hits = wide[
                (BASELINE_MODEL, top_k)
            ].to_numpy(dtype=float)

            differences = model_hits - baseline_hits

            wins = int(np.sum(differences > 0))
            losses = int(np.sum(differences < 0))
            ties = int(np.sum(differences == 0))

            mean_model_hits = float(model_hits.mean())
            mean_baseline_hits = float(baseline_hits.mean())
            mean_difference = float(differences.mean())

            ci_low, ci_high = circular_block_bootstrap_ci(
                differences,
                seed=RANDOM_SEED + comparison_number,
            )

            raw_p = sign_test(wins, losses)

            comparison_rows.append({
                "model": model,
                "baseline": BASELINE_MODEL,
                "top_k": top_k,
                "test_draws": len(differences),
                "model_mean_hits": mean_model_hits,
                "baseline_mean_hits": mean_baseline_hits,
                "mean_hit_difference": mean_difference,
                "relative_improvement_pct":
                    safe_relative_improvement(
                        mean_difference, mean_baseline_hits
                    ),
                "bootstrap_95ci_lower": ci_low,
                "bootstrap_95ci_upper": ci_high,
                "model_wins": wins,
                "baseline_wins": losses,
                "ties": ties,
                "win_rate_excluding_ties_pct":
                    100.0 * wins / (wins + losses)
                    if wins + losses else np.nan,
                "sign_test_p_value": raw_p,
                "bonferroni_adjusted_p_value": np.nan,
                "bootstrap_ci_excludes_zero":
                    bool(ci_low > 0 or ci_high < 0),
            })

            for i, row in event_table.iterrows():
                difference_rows.append({
                    "event_order": int(row["event_order"]),
                    "date": row["date"],
                    "test_index": int(row["test_index"]),
                    "model": model,
                    "baseline": BASELINE_MODEL,
                    "top_k": top_k,
                    "model_hits": int(model_hits[i]),
                    "baseline_hits": int(baseline_hits[i]),
                    "hit_difference": float(differences[i]),
                })

            print(
                f"  {comparison_number}/{total_comparisons}: "
                f"{model}, Top-{top_k}, "
                f"mean difference={mean_difference:+.4f}"
            )

    comparison_df = pd.DataFrame(comparison_rows)

    # Bonferroni correction across all 12 pre-specified comparisons.
    number_of_tests = len(comparison_df)

    comparison_df["bonferroni_adjusted_p_value"] = (
        comparison_df["sign_test_p_value"] * number_of_tests
    ).clip(upper=1.0)

    comparison_df["sign_test_significant_bonferroni_005"] = (
        comparison_df["bonferroni_adjusted_p_value"] < 0.05
    )

    comparison_df = comparison_df.sort_values(
        ["model", "top_k"]
    ).reset_index(drop=True)

    differences_df = pd.DataFrame(difference_rows).sort_values(
        ["test_index", "model", "top_k"]
    ).reset_index(drop=True)

    # ========================================================
    # CHRONOLOGICAL STABILITY
    # ========================================================

    print("\nCalculating chronological blocks...")

    period_rows = []

    for period_start in range(0, number_of_events, PERIOD_BLOCK_SIZE):
        period_end = min(
            period_start + PERIOD_BLOCK_SIZE,
            number_of_events,
        )

        period_events = event_table.iloc[period_start:period_end]
        period_orders = period_events["event_order"].tolist()

        period_df = df[
            df["event_order"].isin(period_orders)
        ]

        for model in MODELS_TO_COMPARE:
            for top_k in TOP_K_VALUES:
                model_rows = period_df[
                    (period_df["model"] == model)
                    & (period_df["top_k"] == top_k)
                ].sort_values("test_index")

                baseline_rows = period_df[
                    (period_df["model"] == BASELINE_MODEL)
                    & (period_df["top_k"] == top_k)
                ].sort_values("test_index")

                if len(model_rows) != len(period_events):
                    raise ValueError(
                        f"Missing {model} rows in chronological block "
                        f"starting at event index {period_start}."
                    )

                if len(baseline_rows) != len(period_events):
                    raise ValueError(
                        f"Missing baseline rows in chronological block "
                        f"starting at event index {period_start}."
                    )

                model_hits = model_rows["hits"].to_numpy(dtype=float)
                baseline_hits = baseline_rows[
                    "hits"
                ].to_numpy(dtype=float)

                if not np.array_equal(
                    model_rows["event_order"].to_numpy(),
                    baseline_rows["event_order"].to_numpy(),
                ):
                    raise ValueError(
                        "Model and baseline event order differs in "
                        f"block starting at index {period_start}."
                    )

                period_rows.append({
                    "block_number":
                        period_start // PERIOD_BLOCK_SIZE + 1,
                    "block_start_test_index":
                        int(period_events["test_index"].iloc[0]),
                    "block_end_test_index":
                        int(period_events["test_index"].iloc[-1]),
                    "first_date": period_events["date"].iloc[0],
                    "last_date": period_events["date"].iloc[-1],
                    "draws_in_block": len(period_events),
                    "model": model,
                    "baseline": BASELINE_MODEL,
                    "top_k": top_k,
                    "model_mean_hits": float(model_hits.mean()),
                    "baseline_mean_hits": float(baseline_hits.mean()),
                    "mean_hit_difference":
                        float((model_hits - baseline_hits).mean()),
                    "model_wins":
                        int(np.sum(model_hits > baseline_hits)),
                    "baseline_wins":
                        int(np.sum(model_hits < baseline_hits)),
                    "ties":
                        int(np.sum(model_hits == baseline_hits)),
                })

    period_df = pd.DataFrame(period_rows)

    # ========================================================
    # SAVE REPORTS
    # ========================================================

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    comparison_df.to_csv(PAIRED_OUTPUT, index=False)
    period_df.to_csv(PERIOD_OUTPUT, index=False)
    differences_df.to_csv(DIFFERENCES_OUTPUT, index=False)

    metadata = {
        "script": "ai_train_v1_validate.py",
        "input_file": str(INPUT_CSV),
        "test_draws": int(number_of_events),
        "first_test_date": str(event_table["date"].iloc[0]),
        "last_test_date": str(event_table["date"].iloc[-1]),
        "models_compared": MODELS_TO_COMPARE,
        "baseline": BASELINE_MODEL,
        "top_k_values": TOP_K_VALUES,
        "comparison_count": int(number_of_tests),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_block_length": BOOTSTRAP_BLOCK_LENGTH,
        "period_block_size": PERIOD_BLOCK_SIZE,
        "random_seed": RANDOM_SEED,
        "outputs": [
            str(PAIRED_OUTPUT),
            str(PERIOD_OUTPUT),
            str(DIFFERENCES_OUTPUT),
        ],
        "elapsed_seconds": round(time.time() - started, 2),
        "interpretation_notes": [
            "This script validates existing predictions; it does not train models.",
            "Positive mean_hit_difference favors the compared model.",
            "Bootstrap intervals use circular moving blocks and are approximate.",
            "The sign test does not account for serial dependence.",
            "Bonferroni adjustment covers the 12 model/top-K comparisons.",
            "Chronological blocks are descriptive, not independent experiments.",
            "A historical improvement does not guarantee future predictive value.",
        ],
    }

    with METADATA_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # ========================================================
    # CONSOLE SUMMARY
    # ========================================================

    print("\n" + "=" * 88)
    print("PAIRED VALIDATION SUMMARY")
    print("=" * 88)

    display_columns = [
        "model",
        "top_k",
        "model_mean_hits",
        "baseline_mean_hits",
        "mean_hit_difference",
        "bootstrap_95ci_lower",
        "bootstrap_95ci_upper",
        "model_wins",
        "baseline_wins",
        "ties",
        "bonferroni_adjusted_p_value",
        "sign_test_significant_bonferroni_005",
    ]

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 220,
        "display.max_colwidth", 30,
    ):
        print(
            comparison_df[display_columns].to_string(
                index=False,
                float_format=lambda x: f"{x:.5f}",
            )
        )

    print("\n" + "=" * 88)
    print("CHRONOLOGICAL STABILITY SUMMARY")
    print("=" * 88)

    stability = period_df.groupby(
        ["model", "top_k"]
    )["mean_hit_difference"].agg(
        blocks="count",
        positive_blocks=lambda x: int((x > 0).sum()),
        zero_blocks=lambda x: int((x == 0).sum()),
        negative_blocks=lambda x: int((x < 0).sum()),
        average_block_difference="mean",
    ).reset_index()

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 180,
    ):
        print(
            stability.to_string(
                index=False,
                float_format=lambda x: f"{x:.5f}",
            )
        )

    print("\nSaved validation reports:")
    print(f"  {PAIRED_OUTPUT}")
    print(f"  {PERIOD_OUTPUT}")
    print(f"  {DIFFERENCES_OUTPUT}")
    print(f"  {METADATA_OUTPUT}")

    print(f"\nElapsed time: {time.time() - started:.2f} seconds")
    print("\nValidation complete.")


if __name__ == "__main__":
    main()
