from pathlib import Path
import json
import time

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

EVENTS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

TRAIN_FRACTION = 0.70
MIN_HISTORY_DRAWS = 50
NEGATIVE_SAMPLES_PER_DRAW = 300

TOP_K_VALUES = [10, 25, 50, 100]
RANDOM_SEED = 42

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(RANDOM_SEED)


# ============================================================
# LOAD AND VALIDATE DATA
# ============================================================

def load_draw_matrix():
    print("Loading historical CSV files...")

    if not EVENTS_FILE.exists():
        raise FileNotFoundError(f"Events CSV not found: {EVENTS_FILE}")
    if not NUMBERS_FILE.exists():
        raise FileNotFoundError(f"Numbers CSV not found: {NUMBERS_FILE}")

    events = pd.read_csv(
        EVENTS_FILE,
        dtype={"serialNumber": str, "fileName": str},
    )

    numbers = pd.read_csv(
        NUMBERS_FILE,
        dtype={"serialNumber": str, "number": str, "prize": str},
    )

    required_events = {"event_order", "serialNumber", "date"}
    required_numbers = {"event_order", "number"}

    if not required_events.issubset(events.columns):
        raise ValueError(
            f"Missing event columns: {required_events - set(events.columns)}"
        )
    if not required_numbers.issubset(numbers.columns):
        raise ValueError(
            f"Missing number columns: {required_numbers - set(numbers.columns)}"
        )
    if events.empty:
        raise ValueError("The events CSV is empty.")

    events["event_order"] = pd.to_numeric(
        events["event_order"], errors="raise"
    ).astype(int)
    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="raise"
    ).astype(int)

    events = events.sort_values("event_order").reset_index(drop=True)

    if events["event_order"].duplicated().any():
        raise ValueError("Duplicate event_order values in events CSV.")

    # Parse dates as day-first (e.g. 11/07/2020); ISO dates are also supported.
    parsed_dates = pd.to_datetime(
        events["date"].astype(str).str.strip(),
        dayfirst=True,
        errors="coerce",
    )
    if parsed_dates.isna().any():
        bad_rows = events.loc[parsed_dates.isna(), ["event_order", "date"]].head(10)
        raise ValueError(
            "Some event dates could not be parsed. Example rows:\n"
            + bad_rows.to_string(index=False)
        )

    events["parsed_date"] = parsed_dates
    if not events["parsed_date"].is_monotonic_increasing:
        raise ValueError(
            "event_order does not follow chronological date order. "
            "Sort or correct the event data before training."
        )

    # Normalize number strings while preserving leading zeroes.
    numbers["number"] = numbers["number"].astype("string").str.strip()
    numbers["number"] = numbers["number"].str.zfill(4)

    valid_number = numbers["number"].str.fullmatch(r"\d{4}", na=False)
    invalid_count = int((~valid_number).sum())
    if invalid_count:
        print(f"Warning: dropping {invalid_count:,} invalid number rows.")

    numbers = numbers.loc[valid_number].copy()
    numbers["number_int"] = numbers["number"].astype(np.int32)
    numbers = numbers[numbers["number_int"].between(0, 9999)]

    event_orders = events["event_order"].to_numpy()
    event_to_index = {
        int(event_order): i for i, event_order in enumerate(event_orders)
    }

    unknown_events = set(numbers["event_order"].unique()) - set(event_to_index)
    if unknown_events:
        raise ValueError(
            f"Number rows refer to {len(unknown_events)} unknown event IDs."
        )

    # Binary target: number appeared at least once in exported prize rows.
    presence = np.zeros((len(events), 10000), dtype=np.uint8)

    for event_order, number_values in numbers.groupby("event_order")["number_int"]:
        row = event_to_index[int(event_order)]
        presence[row, number_values.unique()] = 1

    dates = events["date"].astype(str).to_numpy()
    empty_draws = int((presence.sum(axis=1) == 0).sum())

    print(f"Draw events: {len(events):,}")
    print(f"Number rows: {len(numbers):,}")
    print(f"Unique dates: {events['parsed_date'].nunique():,}")
    print(f"Empty draws with no valid numbers: {empty_draws:,}")
    print(f"Number matrix: {presence.shape}")

    return events, presence, dates


# ============================================================
# DIGIT FEATURES
# ============================================================

def make_digit_features():
    values = np.arange(10000, dtype=np.int32)

    digits = np.column_stack([
        (values // 1000) % 10,
        (values // 100) % 10,
        (values // 10) % 10,
        values % 10,
    ])

    digit_sum = digits.sum(axis=1)
    even_count = ((digits % 2) == 0).sum(axis=1)

    repeated_digit_count = np.array(
        [4 - len(set(row.tolist())) for row in digits],
        dtype=np.int8,
    )

    return digits, digit_sum, even_count, repeated_digit_count


FEATURE_NAMES = [
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
]


def make_features(
    draw_index,
    candidate_ids,
    prefix_hits,
    last_seen_by_draw,
    digits,
    digit_sum,
    even_count,
    repeated_count,
):
    """Build features for draw_index using only information before that draw."""
    candidate_ids = np.asarray(candidate_ids, dtype=np.int32)

    features = np.empty(
        (len(candidate_ids), len(FEATURE_NAMES)),
        dtype=np.float32,
    )

    for column, window in enumerate([5, 10, 25, 50]):
        start = max(0, draw_index - window)
        counts = (
            prefix_hits[draw_index, candidate_ids]
            - prefix_hits[start, candidate_ids]
        )
        features[:, column] = counts

    total = prefix_hits[draw_index, candidate_ids]
    features[:, 4] = total
    features[:, 5] = total / max(draw_index, 1)

    # Critical fix: index the last-seen matrix by draw first, then number.
    seen_at = last_seen_by_draw[draw_index, candidate_ids]
    age = np.where(
        seen_at >= 0,
        draw_index - seen_at,
        draw_index + 1,
    )
    features[:, 6] = age

    features[:, 7:11] = digits[candidate_ids]
    features[:, 11] = digit_sum[candidate_ids]
    features[:, 12] = even_count[candidate_ids]
    features[:, 13] = repeated_count[candidate_ids]

    return features


# ============================================================
# HISTORICAL STATE
# ============================================================

def build_historical_state(presence):
    n_events = len(presence)

    # Row i contains cumulative hits through events strictly before i.
    prefix_hits = np.zeros((n_events + 1, 10000), dtype=np.uint16)
    for i in range(n_events):
        prefix_hits[i + 1] = prefix_hits[i] + presence[i]

    # State before each target draw. Each row is stored exactly once.
    last_seen_by_draw = np.full((n_events, 10000), -1, dtype=np.int32)
    last_seen = np.full(10000, -1, dtype=np.int32)

    for i in range(n_events):
        last_seen_by_draw[i] = last_seen
        appeared = np.flatnonzero(presence[i])
        last_seen[appeared] = i

    return prefix_hits, last_seen_by_draw


# ============================================================
# TRAINING SAMPLE CREATION
# ============================================================

def build_training_data(
    train_end,
    presence,
    prefix_hits,
    last_seen_by_draw,
    digit_features,
):
    digits, digit_sum, even_count, repeated_count = digit_features
    all_candidates = np.arange(10000, dtype=np.int32)

    feature_chunks = []
    label_chunks = []

    print("\nBuilding training examples...")

    for i in range(MIN_HISTORY_DRAWS, train_end):
        actual = np.flatnonzero(presence[i]).astype(np.int32)
        if len(actual) == 0:
            continue

        # Since actual is unique and sorted, setdiff1d is safe here.
        negative_pool = np.setdiff1d(
            all_candidates, actual, assume_unique=True
        )
        sample_size = min(NEGATIVE_SAMPLES_PER_DRAW, len(negative_pool))
        negatives = rng.choice(
            negative_pool, size=sample_size, replace=False
        ).astype(np.int32)

        selected = np.concatenate([actual, negatives])
        X = make_features(
            i,
            selected,
            prefix_hits,
            last_seen_by_draw,
            digits,
            digit_sum,
            even_count,
            repeated_count,
        )
        y = np.concatenate([
            np.ones(len(actual), dtype=np.uint8),
            np.zeros(len(negatives), dtype=np.uint8),
        ])

        feature_chunks.append(X)
        label_chunks.append(y)

        if (i + 1) % 200 == 0:
            print(f"  Prepared through draw {i + 1:,}/{train_end:,}")

    if not feature_chunks:
        raise ValueError(
            "No training examples were created. Check the draw data and "
            "MIN_HISTORY_DRAWS setting."
        )

    X_train = np.concatenate(feature_chunks, axis=0)
    y_train = np.concatenate(label_chunks, axis=0)

    if np.unique(y_train).size < 2:
        raise ValueError("Training data contains only one target class.")

    print(f"Training examples: {len(y_train):,}")
    print(f"Positive examples: {int(y_train.sum()):,}")
    print(f"Negative examples: {int((y_train == 0).sum()):,}")
    print(f"Feature count: {X_train.shape[1]}")

    return X_train, y_train


# ============================================================
# EVALUATION
# ============================================================

def evaluate_models(
    models,
    events,
    presence,
    train_end,
    prefix_hits,
    last_seen_by_draw,
    digit_features,
):
    digits, digit_sum, even_count, repeated_count = digit_features
    all_candidates = np.arange(10000, dtype=np.int32)

    summary_records = []
    detail_records = []
    skipped_empty_draws = 0

    test_indices = range(train_end, len(events))

    print(f"\nTesting on draws {train_end:,} to {len(events) - 1:,}")
    print(f"Test draws: {len(events) - train_end:,}")

    for i in test_indices:
        actual = presence[i].astype(bool)
        actual_count = int(actual.sum())

        if actual_count == 0:
            skipped_empty_draws += 1
            continue

        X_all = make_features(
            i,
            all_candidates,
            prefix_hits,
            last_seen_by_draw,
            digits,
            digit_sum,
            even_count,
            repeated_count,
        )

        scores_by_model = {
            "random": rng.random(10000),
            "historical_frequency": X_all[:, 4].astype(np.float64),
            "recent_frequency_5": X_all[:, 0].astype(np.float64),
            "recent_frequency_10": X_all[:, 1].astype(np.float64),
            "recent_frequency_25": X_all[:, 2].astype(np.float64),
            "recent_frequency_50": X_all[:, 3].astype(np.float64),
        }

        for model_name, model in models.items():
            scores_by_model[model_name] = model.predict_proba(X_all)[:, 1]

        for model_name, scores in scores_by_model.items():
            # Tiny seeded jitter prevents ties from being resolved by number order.
            scores = scores + rng.random(10000) * 1e-10
            ranked = np.argsort(scores)[::-1]

            for k in TOP_K_VALUES:
                top_numbers = ranked[:k]
                hits = int(actual[top_numbers].sum())

                detail_records.append({
                    "event_order": int(events.iloc[i]["event_order"]),
                    "date": str(events.iloc[i]["date"]),
                    "test_index": i,
                    "model": model_name,
                    "top_k": k,
                    "hits": hits,
                    "precision": hits / k,
                    "recall": hits / actual_count,
                    "actual_distinct_numbers": actual_count,
                })

        if (i - train_end + 1) % 50 == 0:
            print(
                f"  Evaluated {i - train_end + 1:,}/"
                f"{len(events) - train_end:,} test draws"
            )

    if not detail_records:
        raise ValueError("No test draws with valid numbers were available.")

    detail = pd.DataFrame(detail_records)

    summary = (
        detail.groupby(["model", "top_k"], as_index=False)
        .agg(
            test_draws=("test_index", "nunique"),
            mean_hits=("hits", "mean"),
            median_hits=("hits", "median"),
            mean_precision=("precision", "mean"),
            mean_recall=("recall", "mean"),
        )
    )

    for column in ["mean_hits", "median_hits"]:
        summary[column] = summary[column].round(5)
    for column in ["mean_precision", "mean_recall"]:
        summary[column] = summary[column].round(6)

    summary_path = RESULTS_DIR / "ai_train_v1_summary.csv"
    detail_path = RESULTS_DIR / "ai_train_v1_per_draw.csv"

    summary.to_csv(summary_path, index=False)
    detail.to_csv(detail_path, index=False)

    print(f"\nSkipped empty test draws: {skipped_empty_draws:,}")
    print("\nMODEL EVALUATION SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nSaved summary: {summary_path}")
    print(f"Saved per-draw results: {detail_path}")

    return summary, detail, skipped_empty_draws


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    events, presence, dates = load_draw_matrix()
    n_events = len(events)

    if n_events <= MIN_HISTORY_DRAWS + 20:
        raise ValueError("Not enough draw events for training and testing.")

    train_end = int(n_events * TRAIN_FRACTION)
    if train_end <= MIN_HISTORY_DRAWS:
        raise ValueError("Training split is too small.")

    print(f"\nChronological training boundary: {train_end:,}")
    print(f"Train period: {dates[0]} to {dates[train_end - 1]}")
    print(f"Test period: {dates[train_end]} to {dates[-1]}")

    prefix_hits, last_seen_by_draw = build_historical_state(presence)
    digit_features = make_digit_features()

    X_train, y_train = build_training_data(
        train_end,
        presence,
        prefix_hits,
        last_seen_by_draw,
        digit_features,
    )

    print("\nTraining logistic regression...")
    logistic = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=300,
            solver="lbfgs",
            random_state=RANDOM_SEED,
        ),
    )
    logistic.fit(X_train, y_train)

    print("\nTraining histogram gradient boosting...")
    gradient_boosting = HistGradientBoostingClassifier(
        max_iter=80,
        learning_rate=0.08,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        l2_regularization=1.0,
        random_state=RANDOM_SEED,
    )
    gradient_boosting.fit(X_train, y_train)

    models = {
        "logistic_regression": logistic,
        "hist_gradient_boosting": gradient_boosting,
    }

    logistic_path = RESULTS_DIR / "ai_train_v1_logistic.joblib"
    boosting_path = RESULTS_DIR / "ai_train_v1_gradient_boosting.joblib"

    joblib.dump(logistic, logistic_path)
    joblib.dump(gradient_boosting, boosting_path)

    del X_train, y_train

    summary, detail, skipped_empty_draws = evaluate_models(
        models,
        events,
        presence,
        train_end,
        prefix_hits,
        last_seen_by_draw,
        digit_features,
    )

    metadata = {
        "version": 1,
        "seed": RANDOM_SEED,
        "events": n_events,
        "numbers": 10000,
        "train_fraction": TRAIN_FRACTION,
        "train_end_index_exclusive": train_end,
        "train_first_date": str(dates[0]),
        "train_last_date": str(dates[train_end - 1]),
        "test_first_date": str(dates[train_end]),
        "test_last_date": str(dates[-1]),
        "minimum_history_draws": MIN_HISTORY_DRAWS,
        "negative_samples_per_training_draw": NEGATIVE_SAMPLES_PER_DRAW,
        "features": FEATURE_NAMES,
        "skipped_empty_test_draws": skipped_empty_draws,
        "baselines": [
            "random",
            "historical_frequency",
            "recent_frequency_5",
            "recent_frequency_10",
            "recent_frequency_25",
            "recent_frequency_50",
        ],
        "target": (
            "Whether the number appeared at least once in the exported "
            "prize rows for a draw"
        ),
        "warning": (
            "First model experiment. Sampled negatives change class "
            "prevalence, and predicted probabilities are not calibrated to "
            "the full candidate population. Historical ranking performance "
            "does not guarantee future predictive value."
        ),
        "elapsed_seconds": round(time.time() - start_time, 2),
    }

    metadata_path = RESULTS_DIR / "ai_train_v1_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\nTRAINING COMPLETE")
    print(f"Results folder: {RESULTS_DIR}")
    print(f"Elapsed seconds: {metadata['elapsed_seconds']}")
    print("Created:")
    print(f"  {summary_path if 'summary_path' in locals() else RESULTS_DIR / 'ai_train_v1_summary.csv'}")
    print(f"  {RESULTS_DIR / 'ai_train_v1_per_draw.csv'}")
    print(f"  {metadata_path}")
    print(f"  {logistic_path}")
    print(f"  {boosting_path}")


if __name__ == "__main__":
    main()
