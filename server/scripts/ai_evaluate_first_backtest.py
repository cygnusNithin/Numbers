
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "ai-training" / "results"

INPUT = RESULTS / "ai_first_backtest_per_draw.csv"
OUTPUT = RESULTS / "ai_first_backtest_robustness.csv"

BOOTSTRAP_REPEATS = 20000
SEED = 20261010


def bootstrap_ci(values, rng, repeats=BOOTSTRAP_REPEATS):
    """Percentile 95% confidence interval for the mean."""
    values = np.asarray(values, dtype=float)
    n = len(values)

    if n == 0:
        return np.nan, np.nan

    means = np.empty(repeats, dtype=float)

    # Batch the work to keep memory usage modest.
    batch_size = 500
    for start in range(0, repeats, batch_size):
        size = min(batch_size, repeats - start)
        indices = rng.integers(0, n, size=(size, n))
        means[start:start + size] = values[indices].mean(axis=1)

    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Backtest results not found: {INPUT}"
        )

    df = pd.read_csv(INPUT)
    required = {
        "event_order", "method", "top_k", "hits",
        "precision", "recall", "lift",
        "random_expected_hits",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    rng = np.random.default_rng(SEED)
    rows = []

    for top_k in sorted(df["top_k"].unique()):
        subset = df[df["top_k"] == top_k]

        model = (
            subset[subset["method"] == "ml_model"]
            .set_index("event_order")
            .sort_index()
        )

        frequency = (
            subset[subset["method"] == "historical_frequency"]
            .set_index("event_order")
            .sort_index()
        )

        common = model.index.intersection(frequency.index)

        if len(common) == 0:
            continue

        model = model.loc[common]
        frequency = frequency.loc[common]

        differences = (
            model["hits"].to_numpy(dtype=float)
            - frequency["hits"].to_numpy(dtype=float)
        )

        low, high = bootstrap_ci(differences, rng)

        mean_difference = float(differences.mean())
        wins = int((differences > 0).sum())
        ties = int((differences == 0).sum())
        losses = int((differences < 0).sum())

        # Approximate two-sided sign-test p-value, ignoring ties.
        non_ties = wins + losses
        if non_ties:
            from scipy.stats import binomtest

            p_value = float(
                binomtest(
                    wins,
                    n=non_ties,
                    p=0.5,
                    alternative="two-sided",
                ).pvalue
            )
        else:
            p_value = 1.0

        model_mean_hits = float(model["hits"].mean())
        frequency_mean_hits = float(frequency["hits"].mean())
        random_expected = float(
            model["random_expected_hits"].mean()
        )

        rows.append({
            "top_k": int(top_k),
            "test_draws": len(common),
            "ml_mean_hits": model_mean_hits,
            "frequency_mean_hits": frequency_mean_hits,
            "random_expected_hits": random_expected,
            "ml_minus_frequency_mean_hits": mean_difference,
            "difference_ci95_low": low,
            "difference_ci95_high": high,
            "ml_wins": wins,
            "ties": ties,
            "ml_losses": losses,
            "ml_win_rate_excluding_ties": (
                wins / non_ties if non_ties else np.nan
            ),
            "sign_test_p_value": p_value,
            "ml_mean_precision": float(model["precision"].mean()),
            "frequency_mean_precision": float(
                frequency["precision"].mean()
            ),
            "ml_mean_lift": float(model["lift"].mean()),
            "frequency_mean_lift": float(
                frequency["lift"].mean()
            ),
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT, index=False)

    print("\nPaired robustness evaluation")
    print("============================")
    print(result.to_string(
        index=False,
        float_format=lambda value: f"{value:.5f}",
    ))

    print("\nInterpretation:")
    print(
        "- A confidence interval crossing zero means the observed "
        "mean difference is not clearly positive at the 95% level."
    )
    print(
        "- The sign test checks whether wins outnumber losses, "
        "excluding ties; it does not measure the size of each win."
    )
    print(
        "- These are exploratory comparisons across several top-K "
        "values, so avoid treating one small p-value as proof."
    )
    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()