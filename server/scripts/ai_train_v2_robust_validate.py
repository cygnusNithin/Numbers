from pathlib import Path
import json
import time

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "data" / "ai-training" / "results"

INPUT_CSV = RESULTS_DIR / "ai_train_v2_per_draw.csv"
FOLD_CSV = RESULTS_DIR / "ai_train_v2_fold_summary.csv"

OUTPUT_CSV = RESULTS_DIR / "ai_train_v2_robust_validation.csv"
FOLD_OUTPUT_CSV = RESULTS_DIR / "ai_train_v2_robust_fold_check.csv"
METADATA_JSON = RESULTS_DIR / "ai_train_v2_robust_validation_metadata.json"

ML_MODEL = "hist_gradient_boosting"
BASELINES = ["historical_frequency", "random"]
TOP_K_VALUES = [10, 25, 50, 100]

BOOTSTRAP_REPLICATES = 5000
BLOCK_LENGTH = 20
RANDOM_SEED = 20261012
ALPHA = 0.05

# Eight primary comparisons:
# 2 baselines x 4 Top-K cutoffs.
COMPARISON_COUNT = len(BASELINES) * len(TOP_K_VALUES)


# ============================================================
# HELPERS
# ============================================================

def require_columns(df, required, label):
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {missing}"
        )


def circular_block_bootstrap_means(
    values,
    replicates,
    block_length,
    rng,
):
    """
    Circular moving-block bootstrap.

    Each replicate samples contiguous blocks of draws, wrapping
    around the end when necessary. This preserves short-range
    dependence better than independently resampling each draw.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)

    if n == 0:
        raise ValueError("Cannot bootstrap an empty array.")

    if block_length < 1:
        raise ValueError("BLOCK_LENGTH must be at least 1.")

    block_length = min(block_length, n)
    blocks_needed = int(np.ceil(n / block_length))

    offsets = np.arange(block_length)
    result = np.empty(replicates, dtype=float)

    for i in range(replicates):
        starts = rng.integers(0, n, size=blocks_needed)

        indices = (
            starts[:, None] + offsets[None, :]
        ) % n

        sample = values[indices.ravel()[:n]]
        result[i] = sample.mean()

    return result


def bootstrap_comparison(
    differences,
    rng,
):
    """
    Evaluate the paired difference:
        ML hits per draw - baseline hits per draw

    The confidence interval is percentile-based. The two-sided
    bootstrap p-value is calculated from a null-centered series.
    """
    differences = np.asarray(differences, dtype=float)
    observed = float(differences.mean())

    bootstrap_means = circular_block_bootstrap_means(
        differences,
        BOOTSTRAP_REPLICATES,
        BLOCK_LENGTH,
        rng,
    )

    ci_low, ci_high = np.quantile(
        bootstrap_means,
        [ALPHA / 2, 1 - ALPHA / 2],
    )

    # Center the observed differences to simulate the null
    # hypothesis of zero average improvement.
    centered = differences - observed

    null_bootstrap_means = circular_block_bootstrap_means(
        centered,
        BOOTSTRAP_REPLICATES,
        BLOCK_LENGTH,
        rng,
    )

    p_value = (
        1 + np.count_nonzero(
            np.abs(null_bootstrap_means) >= abs(observed)
        )
    ) / (BOOTSTRAP_REPLICATES + 1)

    return {
        "mean_difference": observed,
        "ci_95_lower": float(ci_low),
        "ci_95_upper": float(ci_high),
        "bootstrap_p_value": float(p_value),
    }


def fold_consistency(per_draw, top_k, baseline):
    """
    Return the per-fold mean difference and whether ML has
    positive improvement in each fold.
    """
    subset = per_draw[per_draw["top_k"] == top_k]

    wide = subset.pivot(
        index=["fold", "event_order", "test_index"],
        columns="model",
        values="hits",
    ).reset_index()

    rows = []

    for fold, group in wide.groupby("fold", sort=True):
        difference = (
            group[ML_MODEL] - group[baseline]
        ).to_numpy(dtype=float)

        rows.append({
            "fold": int(fold),
            "top_k": int(top_k),
            "baseline": baseline,
            "draws": int(len(difference)),
            "ml_mean_hits": float(group[ML_MODEL].mean()),
            "baseline_mean_hits": float(group[baseline].mean()),
            "ml_minus_baseline": float(difference.mean()),
            "ml_positive": bool(difference.mean() > 0),
        })

    return rows


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            f"Missing backtest output: {INPUT_CSV}\n"
            "Run ai_train_v2_backtest.py first."
        )

    print("Loading V2 out-of-sample predictions...")

    per_draw = pd.read_csv(INPUT_CSV)

    require_columns(
        per_draw,
        [
            "fold",
            "event_order",
            "date",
            "test_index",
            "model",
            "top_k",
            "hits",
        ],
        "V2 per-draw CSV",
    )

    per_draw["top_k"] = pd.to_numeric(
        per_draw["top_k"], errors="raise"
    ).astype(int)

    per_draw["hits"] = pd.to_numeric(
        per_draw["hits"], errors="raise"
    )

    per_draw["fold"] = pd.to_numeric(
        per_draw["fold"], errors="raise"
    ).astype(int)

    required_models = {ML_MODEL, *BASELINES}
    found_models = set(per_draw["model"].unique())

    if not required_models.issubset(found_models):
        raise ValueError(
            "Missing model results. "
            f"Required={sorted(required_models)}, "
            f"found={sorted(found_models)}"
        )

    rng = np.random.default_rng(RANDOM_SEED)

    result_rows = []
    fold_rows = []

    print(f"Prediction rows: {len(per_draw):,}")
    print(
        "Unique test draws:",
        per_draw["test_index"].nunique(),
    )
    print(f"Bootstrap replicates: {BOOTSTRAP_REPLICATES:,}")
    print(f"Block length: {BLOCK_LENGTH} draws")

    # --------------------------------------------------------
    # Paired bootstrap comparisons
    # --------------------------------------------------------

    for top_k in TOP_K_VALUES:
        subset = per_draw[per_draw["top_k"] == top_k]

        wide = subset.pivot(
            index=["event_order", "date", "test_index"],
            columns="model",
            values="hits",
        ).sort_index()

        if wide.index.duplicated().any():
            raise ValueError(
                f"Duplicate draw rows found for Top-K={top_k}."
            )

        if wide[[ML_MODEL, *BASELINES]].isna().any().any():
            raise ValueError(
                f"Missing paired predictions for Top-K={top_k}."
            )

        for baseline in BASELINES:
            differences = (
                wide[ML_MODEL] - wide[baseline]
            ).to_numpy(dtype=float)

            stats = bootstrap_comparison(differences, rng)

            relative_improvement = np.nan
            baseline_mean = float(wide[baseline].mean())

            if baseline_mean != 0:
                relative_improvement = (
                    stats["mean_difference"] / baseline_mean * 100
                )

            result_rows.append({
                "model": ML_MODEL,
                "baseline": baseline,
                "top_k": top_k,
                "test_draws": len(differences),
                "model_mean_hits": float(wide[ML_MODEL].mean()),
                "baseline_mean_hits": baseline_mean,
                "mean_hit_difference": stats["mean_difference"],
                "relative_improvement_pct": relative_improvement,
                "ci_95_lower": stats["ci_95_lower"],
                "ci_95_upper": stats["ci_95_upper"],
                "bootstrap_p_value": stats["bootstrap_p_value"],
            })

            fold_rows.extend(
                fold_consistency(per_draw, top_k, baseline)
            )

            print(
                f"Top-{top_k:3d} vs {baseline:22s} "
                f"difference={stats['mean_difference']:+.4f} "
                f"CI=[{stats['ci_95_lower']:+.4f}, "
                f"{stats['ci_95_upper']:+.4f}] "
                f"p={stats['bootstrap_p_value']:.5f}"
            )

    results = pd.DataFrame(result_rows)

    # Bonferroni correction across all eight planned comparisons.
    results["bonferroni_adjusted_p_value"] = (
        results["bootstrap_p_value"] * COMPARISON_COUNT
    ).clip(upper=1.0)

    results["significant_after_bonferroni_005"] = (
        results["bonferroni_adjusted_p_value"] < ALPHA
    )

    results["ci_excludes_zero"] = (
        (results["ci_95_lower"] > 0)
        | (results["ci_95_upper"] < 0)
    )

    results["positive_mean_difference"] = (
        results["mean_hit_difference"] > 0
    )

    # --------------------------------------------------------
    # Fold stability report
    # --------------------------------------------------------

    fold_check = pd.DataFrame(fold_rows)

    fold_summary = (
        fold_check.groupby(
            ["baseline", "top_k"],
            as_index=False,
        )
        .agg(
            folds=("fold", "nunique"),
            positive_folds=("ml_positive", "sum"),
            mean_fold_difference=("ml_minus_baseline", "mean"),
            minimum_fold_difference=("ml_minus_baseline", "min"),
            maximum_fold_difference=("ml_minus_baseline", "max"),
        )
    )

    fold_summary["positive_fold_rate"] = (
        fold_summary["positive_folds"] / fold_summary["folds"]
    )

    # Attach the fold stability summary to the primary results.
    results = results.merge(
        fold_summary,
        on=["baseline", "top_k"],
        how="left",
        validate="one_to_one",
    )

    results.to_csv(OUTPUT_CSV, index=False)
    fold_check.to_csv(FOLD_OUTPUT_CSV, index=False)

    metadata = {
        "validation": "paired circular moving-block bootstrap",
        "input": str(INPUT_CSV),
        "unique_test_draws": int(
            per_draw["test_index"].nunique()
        ),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "block_length": BLOCK_LENGTH,
        "random_seed": RANDOM_SEED,
        "planned_comparisons": COMPARISON_COUNT,
        "multiple_testing_correction": "Bonferroni",
        "alpha": ALPHA,
        "caveats": [
            "Bootstrap intervals rely on approximate stationarity "
            "within the tested sequence.",
            "Block bootstrap accounts for short-range dependence "
            "only approximately.",
            "The model and features were selected using prior work; "
            "this is not a completely untouched final test.",
            "A positive result does not guarantee future lottery "
            "prediction accuracy.",
            "This script validates existing predictions; it does "
            "not train or save a new model.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }

    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 100)
    print("ROBUST VALIDATION RESULTS")
    print("=" * 100)

    columns = [
        "baseline",
        "top_k",
        "test_draws",
        "mean_hit_difference",
        "ci_95_lower",
        "ci_95_upper",
        "bootstrap_p_value",
        "bonferroni_adjusted_p_value",
        "significant_after_bonferroni_005",
        "positive_folds",
        "folds",
        "positive_fold_rate",
    ]

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 240,
    ):
        print(
            results[columns].to_string(
                index=False,
                float_format=lambda x: f"{x:.5f}",
            )
        )

    print("\nSaved:")
    print(f"  {OUTPUT_CSV}")
    print(f"  {FOLD_OUTPUT_CSV}")
    print(f"  {METADATA_JSON}")
    print(f"\nElapsed: {time.time() - started:.2f} seconds")


if __name__ == "__main__":
    main()