
from __future__ import annotations

import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

TRAIN_FRACTION = 0.70
NEGATIVES_PER_POSITIVE = 5
TOP_K_VALUES = [10, 25, 50, 100]
RANDOM_SEED = 20261010


# ------------------------------------------------------------
# Load and validate source files
# ------------------------------------------------------------

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
            "date": "string",
            "number": "string",
        },
        usecols=["event_order", "serialNumber", "number"],
    )

    required_draw_columns = {
        "event_order", "serialNumber", "date", "fileName"
    }

    if not required_draw_columns.issubset(draws.columns):
        raise ValueError(
            f"Draw CSV must contain: {required_draw_columns}"
        )

    draws["event_order"] = pd.to_numeric(
        draws["event_order"], errors="raise"
    ).astype(int)

    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="raise"
    ).astype(int)

    if draws["event_order"].duplicated().any():
        raise ValueError("Duplicate event_order values in draw CSV.")

    draws = draws.sort_values("event_order").reset_index(drop=True)

    expected_order = np.arange(1, len(draws) + 1)

    if not np.array_equal(
        draws["event_order"].to_numpy(), expected_order
    ):
        raise ValueError(
            "event_order must be consecutive, starting at 1."
        )

    if draws["serialNumber"].duplicated().any():
        raise ValueError("Duplicate serial numbers in draw CSV.")

    if numbers["number"].isna().any():
        raise ValueError("Missing number values in number CSV.")

    if not numbers["number"].str.fullmatch(r"\d{4}").all():
        raise ValueError("Found a number that is not four digits.")

    if not numbers["event_order"].between(1, len(draws)).all():
        raise ValueError("Number CSV references an unknown event.")

    return draws, numbers


def build_presence_matrix(draws, numbers):
    """
    Rows = draw events in chronological order.
    Columns = numbers 0000 through 9999.
    Value = 1 if the number appeared in any exported prize row.
    """
    event_count = len(draws)

    presence = np.zeros((event_count, 10000), dtype=np.uint8)

    event_indices = (
        numbers["event_order"].to_numpy(dtype=np.int32) - 1
    )

    number_values = numbers["number"].map(
        lambda value: int(value)
    ).to_numpy(dtype=np.int32)

    # Repeated number/prize rows within an event become one presence.
    presence[event_indices, number_values] = 1

    if np.any(presence.sum(axis=1) == 0):
        raise ValueError("At least one draw has no valid numbers.")

    return presence


# ------------------------------------------------------------
# Features available BEFORE the target draw
# ------------------------------------------------------------

def build_static_features():
    values = np.arange(10000, dtype=np.int32)

    thousands = values // 1000
    hundreds = (values // 100) % 10
    tens = (values // 10) % 10
    units = values % 10

    digit_sum = (
        thousands + hundreds + tens + units
    ).astype(np.float32)

    even_digit_count = (
        (thousands % 2 == 0).astype(np.int8)
        + (hundreds % 2 == 0).astype(np.int8)
        + (tens % 2 == 0).astype(np.int8)
        + (units % 2 == 0).astype(np.int8)
    ).astype(np.float32)

    return digit_sum, even_digit_count


def build_prefix(presence):
    """
    prefix[t] counts appearances in events 0 through t-1.
    This permits efficient rolling-window calculations.
    """
    cumulative = np.cumsum(presence, axis=0, dtype=np.int32)

    prefix = np.zeros(
        (len(presence) + 1, 10000),
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
    """
    Update appearance history after an event has been observed.
    """
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
    """
    Construct features using only events before target_index.

    Features:
      1. log total historical appearances
      2. log events since last appearance
      3. appearance rate in last 10 events
      4. appearance rate in last 25 events
      5. appearance rate in last 50 events
      6. log average gap between prior appearances
      7. digit sum
      8. count of even digits
    """
    total_hits = prefix[target_index].astype(np.float32)

    last = last_seen.astype(np.int32)

    recency = np.where(
        last >= 0,
        target_index - last,
        target_index + 1,
    ).astype(np.float32)

    mean_gap = np.divide(
        gap_sum,
        gap_count,
        out=np.zeros(10000, dtype=np.float64),
        where=gap_count > 0,
    ).astype(np.float32)

    features = np.empty((10000, 8), dtype=np.float32)

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


# ------------------------------------------------------------
# Metrics
# ------------------------------------------------------------

def evaluate_ranking(scores, actual_numbers, top_k):
    # Stable sorting makes ties reproducible.
    ranked = np.argsort(-scores, kind="stable")
    selected = ranked[:top_k]

    hits = int(np.isin(selected, actual_numbers).sum())
    actual_count = len(actual_numbers)

    precision = hits / top_k
    recall = hits / actual_count if actual_count else 0.0

    prevalence = actual_count / 10000
    lift = precision / prevalence if prevalence else 0.0

    random_expected_hits = top_k * prevalence

    return {
        "hits": hits,
        "precision": precision,
        "recall": recall,
        "lift": lift,
        "random_expected_hits": random_expected_hits,
    }


# ------------------------------------------------------------
# Main experiment
# ------------------------------------------------------------

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading CSV files...")
    draws, numbers = load_data()

    print("Building event-number matrix...")
    presence = build_presence_matrix(draws, numbers)

    event_count = len(draws)

    if event_count < 100:
        raise ValueError("Too few events for this experiment.")

    split_index = int(event_count * TRAIN_FRACTION)

    if split_index >= event_count - 1:
        raise ValueError("Not enough test events.")

    print(f"Draw events: {event_count}")
    print(f"Training target events: {split_index - 1}")
    print(f"Test target events: {event_count - split_index}")
    print(f"Chronological split index: {split_index + 1}")

    digit_sum, even_digit_count = build_static_features()
    prefix = build_prefix(presence)

    last_seen = np.full(10000, -1, dtype=np.int32)
    gap_sum = np.zeros(10000, dtype=np.float64)
    gap_count = np.zeros(10000, dtype=np.int32)

    # Event 0 is known before we predict event 1.
    update_gap_state(
        0,
        presence[0],
        last_seen,
        gap_sum,
        gap_count,
    )

    rng = np.random.default_rng(RANDOM_SEED)

    X_parts = []
    y_parts = []

    print("\nPreparing training samples...")

    for target_index in range(1, split_index):
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
        negative_mask = presence[target_index] == 0
        negatives = np.flatnonzero(negative_mask)

        negative_count = min(
            len(negatives),
            len(positives) * NEGATIVES_PER_POSITIVE,
        )

        sampled_negatives = rng.choice(
            negatives,
            size=negative_count,
            replace=False,
        )

        selected = np.concatenate(
            [positives, sampled_negatives]
        )

        labels = np.concatenate(
            [
                np.ones(len(positives), dtype=np.uint8),
                np.zeros(len(sampled_negatives), dtype=np.uint8),
            ]
        )

        X_parts.append(X_all[selected])
        y_parts.append(labels)

        # Only after creating the sample do we consume this draw.
        update_gap_state(
            target_index,
            presence[target_index],
            last_seen,
            gap_sum,
            gap_count,
        )

        if target_index % 200 == 0:
            print(f"Prepared through event {target_index + 1}")

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    del X_parts, y_parts
    gc.collect()

    positive_samples = int(y_train.sum())
    negative_samples = len(y_train) - positive_samples

    print("\nTraining model...")
    print("Training rows:", len(y_train))
    print("Positive rows:", positive_samples)
    print("Sampled negative rows:", negative_samples)

    model = make_pipeline(
        StandardScaler(),
        SGDClassifier(
            loss="log_loss",
            penalty="l2",
            alpha=0.0001,
            max_iter=20,
            tol=0.001,
            random_state=RANDOM_SEED,
            average=True,
        ),
    )

    model.fit(X_train, y_train)

    del X_train, y_train
    gc.collect()

    print("\nEvaluating on later unseen draws...")

    per_draw_rows = []

    for target_index in range(split_index, event_count):
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

        # Model ranks all 10,000 candidates.
        model_scores = model.predict_proba(X_all)[:, 1]

        # Baseline: rank only by appearances before this draw.
        frequency_scores = prefix[target_index].astype(np.float64)

        date = draws.iloc[target_index]["date"]
        serial = draws.iloc[target_index]["serialNumber"]
        event_order = int(
            draws.iloc[target_index]["event_order"]
        )

        for method, scores in [
            ("ml_model", model_scores),
            ("historical_frequency", frequency_scores),
        ]:
            for top_k in TOP_K_VALUES:
                metrics = evaluate_ranking(
                    scores,
                    actual_numbers,
                    top_k,
                )

                per_draw_rows.append({
                    "event_order": event_order,
                    "date": date,
                    "serialNumber": serial,
                    "method": method,
                    "top_k": top_k,
                    "actual_number_count": len(actual_numbers),
                    **metrics,
                })

        # Update history only after scoring the target event.
        update_gap_state(
            target_index,
            presence[target_index],
            last_seen,
            gap_sum,
            gap_count,
        )

        if (target_index - split_index + 1) % 100 == 0:
            print(f"Evaluated through event {event_order}")

    per_draw = pd.DataFrame(per_draw_rows)

    per_draw_path = RESULTS_DIR / "ai_first_backtest_per_draw.csv"
    summary_path = RESULTS_DIR / "ai_first_backtest_summary.csv"
    metadata_path = RESULTS_DIR / "ai_first_backtest_metadata.json"

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

    metadata = {
        "draw_events": event_count,
        "training_fraction": TRAIN_FRACTION,
        "split_event_order": int(
            draws.iloc[split_index]["event_order"]
        ),
        "first_test_serial": str(
            draws.iloc[split_index]["serialNumber"]
        ),
        "last_test_serial": str(draws.iloc[-1]["serialNumber"]),
        "number_universe": 10000,
        "target": (
            "Number appears at least once among exported prize rows "
            "in the next draw"
        ),
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
        "limitations": [
            "This is an exploratory experiment, not evidence of predictability.",
            "The model is trained once and is not updated during the test period.",
            "Negative examples are sampled during training.",
            "Predictions cover number appearance, not exact prize tier.",
            "Results depend on the event ordering in the source CSV.",
        ],
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("\nBacktest complete.")
    print("\nSummary:")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print("\nFiles created:")
    print(per_draw_path)
    print(summary_path)
    print(metadata_path)


if __name__ == "__main__":
    main()