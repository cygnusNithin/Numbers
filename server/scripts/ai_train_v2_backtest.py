
from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import HistGradientBoostingClassifier


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_CSV = DATA_DIR / "ai_training_draws.csv"
NUMBERS_CSV = DATA_DIR / "ai_training_draw_numbers.csv"

SUMMARY_CSV = RESULTS_DIR / "ai_train_v2_summary.csv"
PER_DRAW_CSV = RESULTS_DIR / "ai_train_v2_per_draw.csv"
FOLD_CSV = RESULTS_DIR / "ai_train_v2_fold_summary.csv"
COMPARISON_CSV = RESULTS_DIR / "ai_train_v2_comparisons.csv"
METADATA_JSON = RESULTS_DIR / "ai_train_v2_metadata.json"

NUMBER_COUNT = 10_000
MIN_HISTORY_DRAWS = 50

FIRST_TEST_INDEX = 997
TEST_BLOCK_SIZE = 200
FOLD_COUNT = 5

NEGATIVE_SAMPLES_PER_DRAW = 300
TOP_K_VALUES = [10, 25, 50, 100]

RANDOM_SEED = 42

MODEL_PARAMETERS = {
    "learning_rate": 0.08,
    "max_iter": 100,
    "max_leaf_nodes": 15,
    "l2_regularization": 1.0,
    "random_state": RANDOM_SEED,
}


# ============================================================
# HELPERS
# ============================================================

def require_columns(df, columns, label):
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {missing}"
        )


def normalize_number(value):
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit() or len(text) > 4:
        return None

    return text.zfill(4)


def top_k_ids(scores, k):
    """
    Deterministic Top-K selection.

    When scores tie at the cutoff, prefer lower numeric IDs.
    This avoids arbitrary selection among many equally frequent
    historical candidates.
    """
    scores = np.asarray(scores)
    threshold = np.partition(scores, len(scores) - k)[len(scores) - k]

    above = np.flatnonzero(scores > threshold)
    tied = np.flatnonzero(scores == threshold)

    needed = k - len(above)
    selected = np.concatenate([above, tied[:needed]])

    # Stable descending order within the selected candidates.
    order = np.argsort(-scores[selected], kind="stable")
    return selected[order]


def make_digit_features():
    ids = np.arange(NUMBER_COUNT)

    digits = np.array(
        [[int(ch) for ch in f"{n:04d}"] for n in ids],
        dtype=np.float32,
    )

    digit_sum = digits.sum(axis=1)
    even_count = (digits % 2 == 0).sum(axis=1)

    repeated_count = np.empty(NUMBER_COUNT, dtype=np.float32)

    for i in range(NUMBER_COUNT):
        repeated_count[i] = 4 - len(set(f"{i:04d}"))

    return digits, digit_sum, even_count, repeated_count


def build_feature_matrix(
    draw_index,
    prefix_hits,
    last_seen_by_draw,
    digit_features,
    digit_sum,
    even_count,
    repeated_count,
):
    """
    Build features using only draws before draw_index.

    prefix_hits[i] contains the cumulative history of draws [0, i).
    """
    total_prior = prefix_hits[draw_index]

    features = np.empty(
        (NUMBER_COUNT, 14),
        dtype=np.float32,
    )

    for column, window in enumerate([5, 10, 25, 50]):
        start = max(0, draw_index - window)

        features[:, column] = (
            prefix_hits[draw_index] - prefix_hits[start]
        )

    features[:, 4] = total_prior
    features[:, 5] = total_prior / max(draw_index, 1)

    last_seen = last_seen_by_draw[draw_index]

    age = np.where(
        last_seen < 0,
        draw_index + 1,
        draw_index - last_seen,
    )

    features[:, 6] = age
    features[:, 7:11] = digit_features
    features[:, 11] = digit_sum
    features[:, 12] = even_count
    features[:, 13] = repeated_count

    return features


def build_training_examples(
    cutoff,
    presence,
    prefix_hits,
    last_seen_by_draw,
    digit_features,
    digit_sum,
    even_count,
    repeated_count,
    rng,
):
    """
    Generate training rows for historical draws before cutoff.

    Each training feature vector uses information available before
    its target draw. Negatives are sampled from numbers absent in
    that target draw.
    """
    all_ids = np.arange(NUMBER_COUNT)

    feature_parts = []
    label_parts = []

    for draw_index in range(MIN_HISTORY_DRAWS, cutoff):
        positive_ids = np.flatnonzero(presence[draw_index])
        negative_pool = all_ids[~presence[draw_index]]

        sample_count = min(
            NEGATIVE_SAMPLES_PER_DRAW,
            len(negative_pool),
        )

        negative_ids = (
            rng.choice(
                negative_pool,
                size=sample_count,
                replace=False,
            )
            if sample_count
            else np.empty(0, dtype=np.int32)
        )

        selected_ids = np.concatenate(
            [positive_ids, negative_ids]
        )

        if len(selected_ids) == 0:
            continue

        X_draw = build_feature_matrix(
            draw_index,
            prefix_hits,
            last_seen_by_draw,
            digit_features,
            digit_sum,
            even_count,
            repeated_count,
        )

        feature_parts.append(X_draw[selected_ids])

        labels = np.concatenate([
            np.ones(len(positive_ids), dtype=np.uint8),
            np.zeros(len(negative_ids), dtype=np.uint8),
        ])

        label_parts.append(labels)

        if (draw_index + 1) % 400 == 0:
            print(
                f"    Prepared training history through "
                f"draw {draw_index + 1}/{cutoff}"
            )

    if not feature_parts:
        raise ValueError(
            f"No training examples generated for cutoff {cutoff}."
        )

    X = np.concatenate(feature_parts, axis=0)
    y = np.concatenate(label_parts, axis=0)

    if len(np.unique(y)) < 2:
        raise ValueError(
            f"Training labels contain fewer than two classes "
            f"at cutoff {cutoff}."
        )

    return X, y


def exact_sign_test(differences):
    differences = np.asarray(differences)

    wins = int(np.sum(differences > 0))
    losses = int(np.sum(differences < 0))
    ties = int(np.sum(differences == 0))

    if wins + losses == 0:
        p_value = np.nan
    else:
        p_value = float(
            binomtest(
                wins,
                n=wins + losses,
                p=0.5,
                alternative="two-sided",
            ).pvalue
        )

    return wins, losses, ties, p_value


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading canonical CSV exports...")

    if not DRAWS_CSV.exists():
        raise FileNotFoundError(DRAWS_CSV)

    if not NUMBERS_CSV.exists():
        raise FileNotFoundError(NUMBERS_CSV)

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
    ).astype(int)

    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="raise"
    ).astype(int)

    draws = draws.sort_values("event_order").reset_index(drop=True)

    if draws["event_order"].duplicated().any():
        raise ValueError(
            "Duplicate event_order values in draw events CSV."
        )

    numbers["normalized_number"] = numbers["number"].map(
        normalize_number
    )

    invalid_count = int(
        numbers["normalized_number"].isna().sum()
    )

    if invalid_count:
        print(
            f"Warning: ignoring {invalid_count} invalid number rows."
        )

    numbers = numbers.dropna(
        subset=["normalized_number"]
    ).copy()

    valid_events = set(draws["event_order"])
    numbers = numbers[
        numbers["event_order"].isin(valid_events)
    ].copy()

    event_orders = draws["event_order"].to_numpy()
    event_to_index = {
        event_order: i
        for i, event_order in enumerate(event_orders)
    }

    n_draws = len(draws)

    required_draws = (
        FIRST_TEST_INDEX + FOLD_COUNT * TEST_BLOCK_SIZE
    )

    if n_draws < required_draws:
        raise ValueError(
            f"Need at least {required_draws} draws for this setup; "
            f"found {n_draws}."
        )

    numbers["draw_index"] = numbers["event_order"].map(
        event_to_index
    )

    numbers["number_id"] = numbers[
        "normalized_number"
    ].astype(int)

    print(f"Draw events: {n_draws:,}")
    print(f"Number rows: {len(numbers):,}")
    print(f"Unique dates: {draws['date'].nunique():,}")
    print(
        f"Date range: {draws['date'].iloc[0]} to "
        f"{draws['date'].iloc[-1]}"
    )

    # --------------------------------------------------------
    # Presence matrix
    # --------------------------------------------------------

    print("\nBuilding number-presence matrix...")

    presence = np.zeros(
        (n_draws, NUMBER_COUNT),
        dtype=np.bool_,
    )

    presence[
        numbers["draw_index"].to_numpy(dtype=np.int32),
        numbers["number_id"].to_numpy(dtype=np.int32),
    ] = True

    distinct_per_draw = presence.sum(axis=1)

    print(f"Presence matrix: {presence.shape}")
    print(
        f"Average distinct numbers per draw: "
        f"{distinct_per_draw.mean():.2f}"
    )

    # prefix_hits[i] counts appearances in draws [0, i).
    print("Building historical feature arrays...")

    prefix_hits = np.zeros(
        (n_draws + 1, NUMBER_COUNT),
        dtype=np.int32,
    )

    prefix_hits[1:] = np.cumsum(
        presence,
        axis=0,
        dtype=np.int32,
    )

    last_seen_by_draw = np.full(
        (n_draws, NUMBER_COUNT),
        -1,
        dtype=np.int32,
    )

    last_seen = np.full(
        NUMBER_COUNT,
        -1,
        dtype=np.int32,
    )

    for i in range(n_draws):
        last_seen_by_draw[i] = last_seen
        last_seen[presence[i]] = i

    (
        digit_features,
        digit_sum,
        even_count,
        repeated_count,
    ) = make_digit_features()

    # --------------------------------------------------------
    # Walk-forward folds
    # --------------------------------------------------------

    per_draw_rows = []
    fold_rows = []

    for fold_number in range(FOLD_COUNT):
        cutoff = (
            FIRST_TEST_INDEX
            + fold_number * TEST_BLOCK_SIZE
        )

        test_end = cutoff + TEST_BLOCK_SIZE

        train_first_date = str(
            draws["date"].iloc[MIN_HISTORY_DRAWS]
        )
        train_last_date = str(draws["date"].iloc[cutoff - 1])
        test_first_date = str(draws["date"].iloc[cutoff])
        test_last_date = str(draws["date"].iloc[test_end - 1])

        print("\n" + "=" * 76)
        print(
            f"FOLD {fold_number + 1}/{FOLD_COUNT}: "
            f"training [50, {cutoff}), testing "
            f"[{cutoff}, {test_end})"
        )
        print(f"Training through: {train_last_date}")
        print(f"Testing: {test_first_date} to {test_last_date}")

        # Use a reproducible fold-specific seed.
        rng = np.random.default_rng(RANDOM_SEED + fold_number)

        X_train, y_train = build_training_examples(
            cutoff,
            presence,
            prefix_hits,
            last_seen_by_draw,
            digit_features,
            digit_sum,
            even_count,
            repeated_count,
            rng,
        )

        print(
            f"Training rows: {len(y_train):,} "
            f"(positive={int(y_train.sum()):,}, "
            f"negative={int(len(y_train) - y_train.sum()):,})"
        )

        print("Training HistGradientBoostingClassifier...")

        model = HistGradientBoostingClassifier(
            **MODEL_PARAMETERS
        )
        model.fit(X_train, y_train)

        print("Model trained. Scoring test draws...")

        fold_values = {
            k: {
                "hist_gradient_boosting": [],
                "historical_frequency": [],
                "random": [],
            }
            for k in TOP_K_VALUES
        }

        for test_index in range(cutoff, test_end):
            X_all = build_feature_matrix(
                test_index,
                prefix_hits,
                last_seen_by_draw,
                digit_features,
                digit_sum,
                even_count,
                repeated_count,
            )

            model_scores = model.predict_proba(X_all)[:, 1]
            frequency_scores = prefix_hits[test_index].astype(
                np.float32
            )

            # Independent, reproducible random ranking per test draw.
            random_scores = rng.random(NUMBER_COUNT)

            actual = presence[test_index]
            actual_count = int(actual.sum())

            score_sets = {
                "hist_gradient_boosting": model_scores,
                "historical_frequency": frequency_scores,
                "random": random_scores,
            }

            rankings = {
                model_name: {
                    k: top_k_ids(scores, k)
                    for k in TOP_K_VALUES
                }
                for model_name, scores in score_sets.items()
            }

            hits_by_model = {}

            for model_name, k_map in rankings.items():
                hits_by_model[model_name] = {}

                for k, selected_ids in k_map.items():
                    hits = int(actual[selected_ids].sum())
                    hits_by_model[model_name][k] = hits

                    per_draw_rows.append({
                        "fold": fold_number + 1,
                        "event_order": int(event_orders[test_index]),
                        "date": str(draws["date"].iloc[test_index]),
                        "test_index": test_index,
                        "model": model_name,
                        "top_k": k,
                        "hits": hits,
                        "precision": hits / k,
                        "recall": (
                            hits / actual_count
                            if actual_count else 0.0
                        ),
                        "actual_distinct_numbers": actual_count,
                    })

            for k in TOP_K_VALUES:
                for model_name in score_sets:
                    fold_values[k][model_name].append(
                        hits_by_model[model_name][k]
                    )

            tested = test_index - cutoff + 1

            if tested % 50 == 0:
                print(
                    f"  Tested {tested}/{TEST_BLOCK_SIZE} draws"
                )

        # Fold-level performance and stability.
        for k in TOP_K_VALUES:
            ml_hits = np.asarray(
                fold_values[k]["hist_gradient_boosting"],
                dtype=float,
            )
            frequency_hits = np.asarray(
                fold_values[k]["historical_frequency"],
                dtype=float,
            )
            random_hits = np.asarray(
                fold_values[k]["random"],
                dtype=float,
            )

            fold_rows.append({
                "fold": fold_number + 1,
                "train_first_date": train_first_date,
                "train_last_date": train_last_date,
                "test_first_date": test_first_date,
                "test_last_date": test_last_date,
                "train_draws": cutoff - MIN_HISTORY_DRAWS,
                "test_draws": TEST_BLOCK_SIZE,
                "top_k": k,
                "ml_mean_hits": float(ml_hits.mean()),
                "frequency_mean_hits": float(frequency_hits.mean()),
                "random_mean_hits": float(random_hits.mean()),
                "ml_minus_frequency":
                    float((ml_hits - frequency_hits).mean()),
                "ml_minus_random":
                    float((ml_hits - random_hits).mean()),
                "ml_wins_vs_frequency":
                    int(np.sum(ml_hits > frequency_hits)),
                "frequency_wins_vs_ml":
                    int(np.sum(ml_hits < frequency_hits)),
                "ties_vs_frequency":
                    int(np.sum(ml_hits == frequency_hits)),
            })

        del X_train, y_train, model

    # --------------------------------------------------------
    # Aggregate metrics
    # --------------------------------------------------------

    print("\nAggregating out-of-sample predictions...")

    per_draw = pd.DataFrame(per_draw_rows)
    fold_df = pd.DataFrame(fold_rows)

    summary_rows = []

    for model_name in [
        "hist_gradient_boosting",
        "historical_frequency",
        "random",
    ]:
        for k in TOP_K_VALUES:
            subset = per_draw[
                (per_draw["model"] == model_name)
                & (per_draw["top_k"] == k)
            ]

            summary_rows.append({
                "model": model_name,
                "top_k": k,
                "test_draws": len(subset),
                "mean_hits": float(subset["hits"].mean()),
                "median_hits": float(subset["hits"].median()),
                "mean_precision": float(subset["precision"].mean()),
                "mean_recall": float(subset["recall"].mean()),
            })

    summary = pd.DataFrame(summary_rows)

    # --------------------------------------------------------
    # Paired comparisons
    # --------------------------------------------------------

    comparison_rows = []

    for k in TOP_K_VALUES:
        subset = per_draw[per_draw["top_k"] == k]

        wide = subset.pivot(
            index=["event_order", "date", "test_index"],
            columns="model",
            values="hits",
        ).sort_index()

        for baseline in [
            "historical_frequency",
            "random",
        ]:
            differences = (
                wide["hist_gradient_boosting"]
                - wide[baseline]
            ).to_numpy(dtype=float)

            wins, losses, ties, p_value = exact_sign_test(
                differences
            )

            comparison_rows.append({
                "model": "hist_gradient_boosting",
                "baseline": baseline,
                "top_k": k,
                "test_draws": len(differences),
                "model_mean_hits":
                    float(wide["hist_gradient_boosting"].mean()),
                "baseline_mean_hits": float(wide[baseline].mean()),
                "mean_hit_difference": float(differences.mean()),
                "relative_improvement_pct": (
                    float(
                        differences.mean()
                        / wide[baseline].mean()
                        * 100
                    )
                    if wide[baseline].mean() != 0
                    else np.nan
                ),
                "model_wins": wins,
                "baseline_wins": losses,
                "ties": ties,
                "sign_test_p_value": p_value,
            })

    comparisons = pd.DataFrame(comparison_rows)

    # Correct for eight comparisons:
    # 2 baselines x 4 Top-K values.
    comparisons["bonferroni_adjusted_p_value"] = (
        comparisons["sign_test_p_value"] * len(comparisons)
    ).clip(upper=1.0)

    comparisons["significant_after_bonferroni_005"] = (
        comparisons["bonferroni_adjusted_p_value"] < 0.05
    )

    # Add historical-frequency comparisons to ML summary rows only.
    # Construct object-typed columns explicitly so missing values do
    # not cause pandas Boolean/NaN assignment errors.
    frequency_comparisons = (
        comparisons[
            comparisons["baseline"] == "historical_frequency"
        ].set_index("top_k")
    )

    comparison_columns = [
        "mean_hit_difference",
        "relative_improvement_pct",
        "model_wins",
        "baseline_wins",
        "ties",
        "sign_test_p_value",
        "bonferroni_adjusted_p_value",
        "significant_after_bonferroni_005",
    ]

    for column in comparison_columns:
        values = []

        for _, row in summary.iterrows():
            if row["model"] == "hist_gradient_boosting":
                values.append(
                    frequency_comparisons.loc[row["top_k"], column]
                )
            else:
                values.append(np.nan)

        summary[column] = pd.Series(
            values,
            index=summary.index,
            dtype=object,
        )

    # --------------------------------------------------------
    # Save reports
    # --------------------------------------------------------

    summary.to_csv(SUMMARY_CSV, index=False)
    per_draw.to_csv(PER_DRAW_CSV, index=False)
    fold_df.to_csv(FOLD_CSV, index=False)
    comparisons.to_csv(COMPARISON_CSV, index=False)

    metadata = {
        "version": 2,
        "method": "expanding-window walk-forward backtest",
        "events": int(n_draws),
        "number_universe": NUMBER_COUNT,
        "first_test_index": FIRST_TEST_INDEX,
        "test_block_size": TEST_BLOCK_SIZE,
        "fold_count": FOLD_COUNT,
        "total_test_draws": FOLD_COUNT * TEST_BLOCK_SIZE,
        "test_first_date": str(
            draws["date"].iloc[FIRST_TEST_INDEX]
        ),
        "test_last_date": str(
            draws["date"].iloc[
                FIRST_TEST_INDEX + FOLD_COUNT * TEST_BLOCK_SIZE - 1
            ]
        ),
        "minimum_history_draws": MIN_HISTORY_DRAWS,
        "negative_samples_per_training_draw":
            NEGATIVE_SAMPLES_PER_DRAW,
        "top_k_values": TOP_K_VALUES,
        "model_parameters": MODEL_PARAMETERS,
        "features": [
            "hits_last_5",
            "hits_last_10",
            "hits_last_25",
            "hits_last_50",
            "total_prior_hits",
            "prior_hit_rate",
            "draws_since_last_hit",
            "digit_1",
            "digit_2",
            "digit_3",
            "digit_4",
            "digit_sum",
            "even_digit_count",
            "repeated_digit_count",
        ],
        "target": (
            "Number appeared at least once in exported prize rows "
            "for a draw."
        ),
        "caveats": [
            "Negative sampling changes training class prevalence.",
            "Model scores are rankings, not calibrated probabilities.",
            "Each fold trains only on draws before its test block.",
            "The sign test does not account for serial dependence.",
            "Bonferroni adjustment covers eight ML/baseline/Top-K tests.",
            "This historical backtest does not guarantee future accuracy.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }

    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # --------------------------------------------------------
    # Print summaries
    # --------------------------------------------------------

    print("\n" + "=" * 100)
    print("WALK-FORWARD BACKTEST SUMMARY")
    print("=" * 100)

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 240,
    ):
        print(
            summary.to_string(
                index=False,
                float_format=lambda x: f"{x:.5f}",
            )
        )

    print("\n" + "=" * 100)
    print("ML PAIRED COMPARISONS")
    print("=" * 100)

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 240,
    ):
        print(
            comparisons.to_string(
                index=False,
                float_format=lambda x: f"{x:.5f}",
            )
        )

    print("\n" + "=" * 100)
    print("FOLD STABILITY")
    print("=" * 100)

    print(
        fold_df[[
            "fold",
            "test_first_date",
            "test_last_date",
            "top_k",
            "ml_minus_frequency",
            "ml_minus_random",
        ]].to_string(
            index=False,
            float_format=lambda x: f"{x:.5f}",
        )
    )

    print("\nReports saved:")
    print(f"  {SUMMARY_CSV}")
    print(f"  {PER_DRAW_CSV}")
    print(f"  {FOLD_CSV}")
    print(f"  {COMPARISON_CSV}")
    print(f"  {METADATA_JSON}")

    print(f"\nElapsed: {time.time() - started:.2f} seconds")
    print("Walk-forward backtest complete.")


if __name__ == "__main__":
    main()
