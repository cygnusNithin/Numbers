
from __future__ import annotations

import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

NUMBER_COUNT = 10000
TOP_K_VALUES = [10, 25, 50, 100]

# Five consecutive, chronological test blocks.
# Each block tests approximately 10% of all draw events.
FIRST_TEST_FRACTION = 0.50
TEST_BLOCK_FRACTION = 0.10

NEGATIVES_PER_POSITIVE = 5
RANDOM_SEED = 20261011


# ============================================================
# Load and validate data
# ============================================================

def load_data():
    if not DRAWS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {DRAWS_FILE}")

    if not NUMBERS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {NUMBERS_FILE}")

    draws = pd.read_csv(
        DRAWS_FILE,
        dtype={
            "serialNumber": "string",
            "date": "string",
            "fileName": "string",
        },
    )

    numbers = pd.read_csv(
        NUMBERS_FILE,
        dtype={
            "serialNumber": "string",
            "number": "string",
        },
        usecols=["event_order", "serialNumber", "number"],
    )

    required = {"event_order", "serialNumber", "date", "fileName"}

    if not required.issubset(draws.columns):
        raise ValueError(
            f"Draw CSV must contain these columns: {sorted(required)}"
        )

    draws["event_order"] = pd.to_numeric(
        draws["event_order"], errors="raise"
    ).astype(int)

    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="raise"
    ).astype(int)

    draws = draws.sort_values("event_order").reset_index(drop=True)

    expected = np.arange(1, len(draws) + 1)

    if not np.array_equal(draws["event_order"].to_numpy(), expected):
        raise ValueError(
            "event_order must be consecutive, starting at 1."
        )

    if draws["serialNumber"].duplicated().any():
        raise ValueError("Duplicate serial numbers in draw CSV.")

    if numbers["number"].isna().any():
        raise ValueError("Missing number values in number CSV.")

    if not numbers["number"].str.fullmatch(r"\d{4}").all():
        raise ValueError("Every number must contain exactly four digits.")

    if not numbers["event_order"].between(1, len(draws)).all():
        raise ValueError("Number CSV references an unknown event.")

    return draws, numbers


def build_presence_matrix(draws, numbers):
    """Rows are draw events; columns represent 0000 through 9999."""
    presence = np.zeros((len(draws), NUMBER_COUNT), dtype=np.uint8)

    event_indices = (
        numbers["event_order"].to_numpy(dtype=np.int32) - 1
    )

    number_values = numbers["number"].map(int).to_numpy(dtype=np.int32)

    presence[event_indices, number_values] = 1

    if np.any(presence.sum(axis=1) == 0):
        raise ValueError("At least one draw has no valid number rows.")

    return presence


# ============================================================
# Feature engineering
# Features use only draws that occurred before the target draw.
# ============================================================

def build_static_features():
    values = np.arange(NUMBER_COUNT, dtype=np.int32)

    digits = np.column_stack([
        values // 1000,
        (values // 100) % 10,
        (values // 10) % 10,
        values % 10,
    ])

    digit_sum = digits.sum(axis=1).astype(np.float32)
    even_digit_count = (digits % 2 == 0).sum(axis=1).astype(np.float32)

    return digit_sum, even_digit_count


def build_prefix(presence):
    cumulative = np.cumsum(presence, axis=0, dtype=np.int32)

    prefix = np.zeros(
        (len(presence) + 1, NUMBER_COUNT),
        dtype=np.int32,
    )

    prefix[1:] = cumulative
    return prefix


def update_gap_state(
    event_index,
    present_numbers,
    last_seen,
    gap_sum,
    gap_count,
):
    hits = np.flatnonzero(present_numbers)
    previously_seen = hits[last_seen[hits] >= 0]

    if len(previously_seen):
        gaps = event_index - last_seen[previously_seen]
        gap_sum[previously_seen] += gaps
        gap_count[previously_seen] += 1

    last_seen[hits] = event_index


def build_features(
    target_index,
    prefix,
    last_seen,
    gap_sum,
    gap_count,
    digit_sum,
    even_digit_count,
):
    total_hits = prefix[target_index].astype(np.float32)

    recency = np.where(
        last_seen >= 0,
        target_index - last_seen,
        target_index + 1,
    ).astype(np.float32)

    mean_gap = np.divide(
        gap_sum,
        gap_count,
        out=np.zeros(NUMBER_COUNT, dtype=np.float64),
        where=gap_count > 0,
    ).astype(np.float32)

    features = np.empty((NUMBER_COUNT, 8), dtype=np.float32)

    features[:, 0] = np.log1p(total_hits)
    features[:, 1] = np.log1p(recency)

    for column, window in enumerate([10, 25, 50], start=2):
        start = max(0, target_index - window)

        window_hits = (
            prefix[target_index] - prefix[start]
        ).astype(np.float32)

        effective_window = target_index - start

        features[:, column] = (
            window_hits / max(effective_window, 1)
        )

    features[:, 5] = np.log1p(mean_gap)
    features[:, 6] = digit_sum
    features[:, 7] = even_digit_count

    return features


# ============================================================
# Ranking and evaluation
# ============================================================

def ranking_order(scores, rng):
    """
    Sort scores from highest to lowest.
    Randomly break equal-score ties, avoiding a systematic
    preference for smaller four-digit numbers.
    """
    tie_breakers = rng.random(len(scores))

    return np.lexsort((tie_breakers, -scores))


def ranking_metrics(ranked_numbers, actual_numbers, top_k):
    selected = ranked_numbers[:top_k]
    hits = int(np.isin(selected, actual_numbers).sum())

    actual_count = len(actual_numbers)
    precision = hits / top_k
    recall = hits / actual_count if actual_count else 0.0

    prevalence = actual_count / NUMBER_COUNT
    lift = precision / prevalence if prevalence else 0.0

    return {
        "hits": hits,
        "precision": precision,
        "recall": recall,
        "lift": lift,
        "random_expected_hits": top_k * prevalence,
    }


# ============================================================
# Train one model using only events before a fold's test block
# ============================================================

def train_fold_model(
    fold_number,
    train_end,
    presence,
    prefix,
    digit_sum,
    even_digit_count,
):
    rng = np.random.default_rng(RANDOM_SEED + fold_number)

    last_seen = np.full(NUMBER_COUNT, -1, dtype=np.int32)
    gap_sum = np.zeros(NUMBER_COUNT, dtype=np.float64)
    gap_count = np.zeros(NUMBER_COUNT, dtype=np.int32)

    # Event zero is known before predicting event one.
    update_gap_state(
        0,
        presence[0],
        last_seen,
        gap_sum,
        gap_count,
    )

    X_parts = []
    y_parts = []

    # Target event indices [1, train_end) are training targets.
    for target_index in range(1, train_end):
        X_all = build_features(
            target_index,
            prefix,
            last_seen,
            gap_sum,
            gap_count,
            digit_sum,
            even_digit_count,
        )

        positives = np.flatnonzero(presence[target_index])
        negatives = np.flatnonzero(presence[target_index] == 0)

        negative_count = min(
            len(negatives),
            len(positives) * NEGATIVES_PER_POSITIVE,
        )

        sampled_negatives = rng.choice(
            negatives,
            size=negative_count,
            replace=False,
        )

        selected = np.concatenate([positives, sampled_negatives])

        labels = np.concatenate([
            np.ones(len(positives), dtype=np.uint8),
            np.zeros(len(sampled_negatives), dtype=np.uint8),
        ])

        X_parts.append(X_all[selected])
        y_parts.append(labels)

        # Update history after the target event has been processed.
        update_gap_state(
            target_index,
            presence[target_index],
            last_seen,
            gap_sum,
            gap_count,
        )

        if target_index % 300 == 0:
            print(
                f"  Fold {fold_number}: prepared training history "
                f"through event {target_index + 1}"
            )

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    del X_parts, y_parts
    gc.collect()

    print(
        f"  Training samples: {len(y_train):,}; "
        f"positive: {int(y_train.sum()):,}; "
        f"negative: {len(y_train) - int(y_train.sum()):,}"
    )

    model = make_pipeline(
        StandardScaler(),
        SGDClassifier(
            loss="log_loss",
            penalty="l2",
            alpha=0.0001,
            max_iter=20,
            tol=0.001,
            random_state=RANDOM_SEED + fold_number,
            average=True,
        ),
    )

    model.fit(X_train, y_train)

    del X_train, y_train
    gc.collect()

    return model


# ============================================================
# Evaluate each chronological fold
# ============================================================

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading source CSV files...")
    draws, numbers = load_data()

    print("Building event-number matrix...")
    presence = build_presence_matrix(draws, numbers)

    event_count = len(draws)

    if event_count < 100:
        raise ValueError("Too few draw events for this experiment.")

    digit_sum, even_digit_count = build_static_features()
    prefix = build_prefix(presence)

    first_test_index = int(event_count * FIRST_TEST_FRACTION)
    block_size = max(1, int(event_count * TEST_BLOCK_FRACTION))

    if first_test_index < 2 or first_test_index >= event_count:
        raise ValueError("Invalid first test index.")

    print(f"Total draw events: {event_count}")
    print(f"First test event index: {first_test_index + 1}")
    print(f"Test block size: approximately {block_size} events")
    print(f"Top-K values: {TOP_K_VALUES}")

    all_rows = []
    fold_number = 0
    test_start = first_test_index

    while test_start < event_count:
        test_end = min(test_start + block_size, event_count)
        fold_number += 1

        print("\n" + "=" * 65)
        print(
            f"FOLD {fold_number}: "
            f"training targets before event {test_start + 1}; "
            f"testing events {test_start + 1} to {test_end}"
        )
        print("=" * 65)

        model = train_fold_model(
            fold_number,
            test_start,
            presence,
            prefix,
            digit_sum,
            even_digit_count,
        )

        # Rebuild history through the test block using only events
        # preceding each individual target. The model remains fixed
        # within this fold, but observed draw history advances.
        last_seen = np.full(NUMBER_COUNT, -1, dtype=np.int32)
        gap_sum = np.zeros(NUMBER_COUNT, dtype=np.float64)
        gap_count = np.zeros(NUMBER_COUNT, dtype=np.int32)

        update_gap_state(
            0,
            presence[0],
            last_seen,
            gap_sum,
            gap_count,
        )

        # Replay history up to the first test event.
        for event_index in range(1, test_start):
            update_gap_state(
                event_index,
                presence[event_index],
                last_seen,
                gap_sum,
                gap_count,
            )

        # Independent random generator per fold for reproducibility.
        ranking_rng = np.random.default_rng(
            RANDOM_SEED + 10000 + fold_number
        )

        for target_index in range(test_start, test_end):
            X_all = build_features(
                target_index,
                prefix,
                last_seen,
                gap_sum,
                gap_count,
                digit_sum,
                even_digit_count,
            )

            actual_numbers = np.flatnonzero(presence[target_index])

            model_scores = model.predict_proba(X_all)[:, 1]
            frequency_scores = prefix[target_index].astype(np.float64)

            # A separate randomly ranked universe for the empirical
            # random baseline on this event.
            random_scores = ranking_rng.random(NUMBER_COUNT)

            model_order = ranking_order(model_scores, ranking_rng)
            frequency_order = ranking_order(
                frequency_scores, ranking_rng
            )
            random_order = ranking_order(random_scores, ranking_rng)

            date = draws.iloc[target_index]["date"]
            serial = draws.iloc[target_index]["serialNumber"]
            event_order = int(draws.iloc[target_index]["event_order"])

            rankings = [
                ("ml_model", model_order),
                ("historical_frequency", frequency_order),
                ("empirical_random", random_order),
            ]

            for method, ranked_numbers in rankings:
                for top_k in TOP_K_VALUES:
                    metrics = ranking_metrics(
                        ranked_numbers,
                        actual_numbers,
                        top_k,
                    )

                    all_rows.append({
                        "fold": fold_number,
                        "event_order": event_order,
                        "date": date,
                        "serialNumber": serial,
                        "method": method,
                        "top_k": top_k,
                        "actual_number_count": len(actual_numbers),
                        **metrics,
                    })

            # The target event is revealed only after predictions
            # have been evaluated.
            update_gap_state(
                target_index,
                presence[target_index],
                last_seen,
                gap_sum,
                gap_count,
            )

            if (target_index - test_start + 1) % 50 == 0:
                print(
                    f"  Evaluated through event {event_order}"
                )

        print(
            f"Fold {fold_number} complete: "
            f"{test_end - test_start} test events."
        )

        del model
        gc.collect()

        test_start = test_end

    per_draw = pd.DataFrame(all_rows)

    per_draw_path = (
        RESULTS_DIR / "ai_second_backtest_per_draw.csv"
    )
    summary_path = (
        RESULTS_DIR / "ai_second_backtest_summary.csv"
    )
    fold_summary_path = (
        RESULTS_DIR / "ai_second_backtest_fold_summary.csv"
    )
    metadata_path = (
        RESULTS_DIR / "ai_second_backtest_metadata.json"
    )

    per_draw.to_csv(per_draw_path, index=False)

    summary = (
        per_draw.groupby(["method", "top_k"], as_index=False)
        .agg(
            test_draws=("event_order", "nunique"),
            mean_hits=("hits", "mean"),
            mean_precision=("precision", "mean"),
            mean_recall=("recall", "mean"),
            mean_lift=("lift", "mean"),
            mean_random_expected_hits=(
                "random_expected_hits", "mean"
            ),
        )
    )

    summary.to_csv(summary_path, index=False)

    fold_summary = (
        per_draw.groupby(["fold", "method", "top_k"], as_index=False)
        .agg(
            test_draws=("event_order", "nunique"),
            mean_hits=("hits", "mean"),
            mean_precision=("precision", "mean"),
            mean_lift=("lift", "mean"),
        )
    )

    fold_summary.to_csv(fold_summary_path, index=False)

    metadata = {
        "draw_events": event_count,
        "first_test_fraction": FIRST_TEST_FRACTION,
        "test_block_fraction": TEST_BLOCK_FRACTION,
        "fold_count": fold_number,
        "number_universe": NUMBER_COUNT,
        "top_k_values": TOP_K_VALUES,
        "negative_sampling_ratio": NEGATIVES_PER_POSITIVE,
        "random_seed": RANDOM_SEED,
        "model": "StandardScaler + SGDClassifier(log_loss)",
        "features": [
            "log_total_historical_hits",
            "log_events_since_last_hit",
            "appearance_rate_last_10_events",
            "appearance_rate_last_25_events",
            "appearance_rate_last_50_events",
            "log_mean_historical_gap",
            "digit_sum",
            "even_digit_count",
        ],
        "methods": [
            "ml_model",
            "historical_frequency",
            "empirical_random",
        ],
        "methodology": [
            "Each fold trains only on events preceding its test block.",
            "The trained model remains fixed within each test block.",
            "Observed history advances after each evaluated event.",
            "Ranking ties are broken randomly with a fixed seed.",
            "The empirical random baseline randomly ranks all 10000 numbers.",
            "Repeated prize rows for a number within one event count once.",
        ],
        "limitations": [
            "Exploratory analysis; not evidence that lottery results are predictable.",
            "The model predicts number appearance, not exact prize tier.",
            "Negative training examples are sampled.",
            "Results depend on the ordering in the source CSV.",
            "Random baseline results have simulation variance.",
        ],
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 65)
    print("SECOND BACKTEST COMPLETE")
    print("=" * 65)

    print("\nOverall summary:")
    print(
        summary.to_string(
            index=False,
            float_format=lambda value: f"{value:.5f}",
        )
    )

    print("\nFold-by-fold summary:")
    print(
        fold_summary.to_string(
            index=False,
            float_format=lambda value: f"{value:.5f}",
        )
    )

    print("\nFiles created:")
    print(per_draw_path)
    print(summary_path)
    print(fold_summary_path)
    print(metadata_path)


if __name__ == "__main__":
    main()
