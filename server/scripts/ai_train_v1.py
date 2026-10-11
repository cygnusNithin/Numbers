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

# ---------------------------- Configuration ----------------------------

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

FEATURE_NAMES = [
    "hits_last_5", "hits_last_10", "hits_last_25", "hits_last_50",
    "total_prior_hits", "prior_hit_rate", "draws_since_last_hit",
    "digit_1", "digit_2", "digit_3", "digit_4", "digit_sum",
    "even_digit_count", "repeated_digit_count",
]


# ---------------------------- Load data ----------------------------

def load_draw_matrix():
    print("Loading historical CSV files...")
    if not EVENTS_FILE.exists():
        raise FileNotFoundError(f"Events CSV not found: {EVENTS_FILE}")
    if not NUMBERS_FILE.exists():
        raise FileNotFoundError(f"Numbers CSV not found: {NUMBERS_FILE}")

    events = pd.read_csv(
        EVENTS_FILE, dtype={"serialNumber": str, "fileName": str}
    )
    numbers = pd.read_csv(
        NUMBERS_FILE,
        dtype={"serialNumber": str, "number": str, "prize": str},
    )

    required_events = {"event_order", "serialNumber", "date"}
    required_numbers = {"event_order", "number"}
    if not required_events.issubset(events.columns):
        raise ValueError(f"Missing event columns: {required_events - set(events.columns)}")
    if not required_numbers.issubset(numbers.columns):
        raise ValueError(f"Missing number columns: {required_numbers - set(numbers.columns)}")
    if events.empty:
        raise ValueError("The events CSV is empty.")

    events["event_order"] = pd.to_numeric(events["event_order"], errors="raise").astype(np.int64)
    numbers["event_order"] = pd.to_numeric(numbers["event_order"], errors="raise").astype(np.int64)
    events = events.sort_values("event_order").reset_index(drop=True)

    if events["event_order"].duplicated().any():
        raise ValueError("Duplicate event_order values in events CSV.")

    number_text = numbers["number"].astype("string").str.strip()
    number_text = number_text.str.replace(r"\.0$", "", regex=True).str.zfill(4)
    valid = number_text.str.fullmatch(r"\d{4}", na=False)
    numbers = numbers.loc[valid].copy()
    numbers["number_int"] = number_text.loc[valid].astype(np.int32)
    numbers = numbers[numbers["number_int"].between(0, 9999)]

    event_to_index = {
        int(event_order): i
        for i, event_order in enumerate(events["event_order"].to_numpy())
    }
    unknown = set(numbers["event_order"].unique()) - set(event_to_index)
    if unknown:
        raise ValueError(f"Number rows refer to {len(unknown)} unknown event IDs.")

    # Target: whether a number appeared at least once in an event's prize rows.
    presence = np.zeros((len(events), 10000), dtype=np.uint8)
    for event_order, group in numbers.groupby("event_order", sort=False):
        presence[event_to_index[int(event_order)], group["number_int"].unique()] = 1

    dates = events["date"].astype(str).to_numpy()
    print(f"Draw events: {len(events):,}")
    print(f"Number rows: {len(numbers):,}")
    print(f"Unique dates: {events['date'].nunique():,}")
    print(f"Number matrix: {presence.shape}")
    return events, presence, dates


# ---------------------------- Feature arrays ----------------------------

def make_digit_features():
    values = np.arange(10000, dtype=np.int32)
    digits = np.column_stack([
        (values // 1000) % 10,
        (values // 100) % 10,
        (values // 10) % 10,
        values % 10,
    ]).astype(np.float32)

    digit_sum = digits.sum(axis=1).astype(np.float32)
    even_count = ((digits % 2) == 0).sum(axis=1).astype(np.float32)
    repeated_count = np.array(
        [4 - len(set(row.tolist())) for row in digits],
        dtype=np.float32,
    )
    return digits, digit_sum, even_count, repeated_count


def build_history_arrays(presence):
    """
    prefix_hits[i, n] counts appearances in draws strictly before i.
    last_seen_by_draw[i, n] is the last index strictly before i, or -1.
    """
    n_draws = presence.shape[0]
    prefix_hits = np.zeros((n_draws + 1, 10000), dtype=np.uint16)
    np.cumsum(presence, axis=0, dtype=np.uint16, out=prefix_hits[1:])

    last_seen_by_draw = np.full((n_draws, 10000), -1, dtype=np.int32)
    last_seen = np.full(10000, -1, dtype=np.int32)
    for i in range(n_draws):
        last_seen_by_draw[i] = last_seen
        last_seen[np.flatnonzero(presence[i])] = i
    return prefix_hits, last_seen_by_draw


def make_features(draw_index, candidate_ids, prefix_hits,
                  last_seen_by_draw, digit_features):
    """
    All historical features stop before draw_index.
    Indexing is done inside this function to prevent the previous
    2D-array/1D-array IndexError.
    """
    digits, digit_sum, even_count, repeated_count = digit_features
    candidate_ids = np.asarray(candidate_ids, dtype=np.int32)
    if candidate_ids.ndim != 1:
        raise ValueError("candidate_ids must be one-dimensional.")
    if np.any((candidate_ids < 0) | (candidate_ids > 9999)):
        raise ValueError("Candidate IDs must be between 0 and 9999.")

    X = np.empty((len(candidate_ids), len(FEATURE_NAMES)), dtype=np.float32)

    for col, window in enumerate((5, 10, 25, 50)):
        start = max(0, draw_index - window)
        X[:, col] = (
            prefix_hits[draw_index, candidate_ids]
            - prefix_hits[start, candidate_ids]
        )

    total = prefix_hits[draw_index, candidate_ids].astype(np.float32)
    X[:, 4] = total
    X[:, 5] = total / max(draw_index, 1)

    # Critical fix: select current draw's 10,000-number row first.
    seen_at = last_seen_by_draw[draw_index, candidate_ids]
    X[:, 6] = np.where(seen_at >= 0, draw_index - seen_at, draw_index + 1)

    X[:, 7:11] = digits[candidate_ids]
    X[:, 11] = digit_sum[candidate_ids]
    X[:, 12] = even_count[candidate_ids]
    X[:, 13] = repeated_count[candidate_ids]
    return X


# ---------------------------- Training data ----------------------------

def build_training_data(train_end, presence, prefix_hits,
                        last_seen_by_draw, digit_features, rng):
    all_candidates = np.arange(10000, dtype=np.int32)
    X_chunks, y_chunks = [], []
    print("\nBuilding training examples...")

    for i in range(MIN_HISTORY_DRAWS, train_end):
        actual = np.flatnonzero(presence[i]).astype(np.int32)
        if actual.size == 0:
            continue

        negative_pool = np.setdiff1d(all_candidates, actual, assume_unique=True)
        n_negative = min(NEGATIVE_SAMPLES_PER_DRAW, negative_pool.size)
        negatives = rng.choice(negative_pool, size=n_negative, replace=False).astype(np.int32)
        selected = np.concatenate((actual, negatives))

        X_chunks.append(make_features(
            i, selected, prefix_hits, last_seen_by_draw, digit_features
        ))
        y_chunks.append(np.concatenate((
            np.ones(actual.size, dtype=np.uint8),
            np.zeros(negatives.size, dtype=np.uint8),
        )))

        if (i + 1) % 200 == 0:
            print(f"  Prepared through draw {i + 1:,}/{train_end:,}")

    if not X_chunks:
        raise RuntimeError("No training examples were generated.")

    X_train = np.concatenate(X_chunks, axis=0)
    y_train = np.concatenate(y_chunks, axis=0)
    if np.unique(y_train).size < 2:
        raise RuntimeError("Training data contains only one target class.")

    print(f"Training examples: {len(y_train):,}")
    print(f"Positive examples: {int(y_train.sum()):,}")
    print(f"Negative examples: {int((y_train == 0).sum()):,}")
    print(f"Feature count: {X_train.shape[1]}")
    return X_train, y_train


# ---------------------------- Evaluation ----------------------------

def evaluate_models(models, events, presence, train_end, prefix_hits,
                    last_seen_by_draw, digit_features, rng):
    all_candidates = np.arange(10000, dtype=np.int32)
    records = []
    n_test = len(events) - train_end
    print(f"\nTesting on draws {train_end:,} to {len(events) - 1:,}")
    print(f"Test draws: {n_test:,}")

    for i in range(train_end, len(events)):
        actual = presence[i].astype(bool)
        actual_count = int(actual.sum())
        if actual_count == 0:
            continue

        X_all = make_features(
            i, all_candidates, prefix_hits, last_seen_by_draw, digit_features
        )
        scores_by_model = {
            "random": rng.random(10000),
            "historical_frequency": (
                X_all[:, 4].astype(np.float64) + rng.random(10000) * 1e-8
            ),
        }
        for name, model in models.items():
            scores_by_model[name] = model.predict_proba(X_all)[:, 1]

        for name, scores in scores_by_model.items():
            scores = scores + rng.random(10000) * 1e-10
            ranked = np.argsort(scores)[::-1]
            for k in TOP_K_VALUES:
                hits = int(actual[ranked[:k]].sum())
                records.append({
                    "event_order": int(events.iloc[i]["event_order"]),
                    "date": str(events.iloc[i]["date"]),
                    "test_index": i,
                    "model": name,
                    "top_k": k,
                    "hits": hits,
                    "precision": hits / k,
                    "recall": hits / actual_count,
                    "actual_distinct_numbers": actual_count,
                })

        completed = i - train_end + 1
        if completed % 50 == 0:
            print(f"  Evaluated {completed:,}/{n_test:,} test draws")

    detail = pd.DataFrame(records)
    if detail.empty:
        raise RuntimeError("Evaluation produced no test results.")

    summary = detail.groupby(["model", "top_k"], as_index=False).agg(
        test_draws=("test_index", "nunique"),
        mean_hits=("hits", "mean"),
        median_hits=("hits", "median"),
        mean_precision=("precision", "mean"),
        mean_recall=("recall", "mean"),
    )
    summary["mean_hits"] = summary["mean_hits"].round(5)
    summary["median_hits"] = summary["median_hits"].round(5)
    summary["mean_precision"] = summary["mean_precision"].round(6)
    summary["mean_recall"] = summary["mean_recall"].round(6)

    summary_path = RESULTS_DIR / "ai_train_v1_summary.csv"
    detail_path = RESULTS_DIR / "ai_train_v1_per_draw.csv"
    summary.to_csv(summary_path, index=False)
    detail.to_csv(detail_path, index=False)

    print("\nMODEL EVALUATION SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nSummary saved: {summary_path}")
    print(f"Per-draw results saved: {detail_path}")
    return summary


# ---------------------------- Main ----------------------------

def main():
    started = time.time()
    rng = np.random.default_rng(RANDOM_SEED)

    events, presence, dates = load_draw_matrix()
    n_events = len(events)
    if n_events <= MIN_HISTORY_DRAWS + 20:
        raise ValueError("Not enough draw events for training and testing.")

    train_end = int(n_events * TRAIN_FRACTION)
    if not MIN_HISTORY_DRAWS < train_end < n_events:
        raise ValueError("Invalid chronological training split.")

    print(f"\nChronological training boundary: {train_end:,}")
    print(f"Train period: {dates[0]} to {dates[train_end - 1]}")
    print(f"Test period: {dates[train_end]} to {dates[-1]}")

    print("\nBuilding historical feature arrays...")
    prefix_hits, last_seen_by_draw = build_history_arrays(presence)
    digit_features = make_digit_features()

    X_train, y_train = build_training_data(
        train_end, presence, prefix_hits, last_seen_by_draw, digit_features, rng
    )

    print("\nTraining logistic regression...")
    logistic = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=300, solver="lbfgs", random_state=RANDOM_SEED
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

    joblib.dump(logistic, RESULTS_DIR / "ai_train_v1_logistic.joblib")
    joblib.dump(
        gradient_boosting,
        RESULTS_DIR / "ai_train_v1_gradient_boosting.joblib",
    )
    del X_train, y_train

    evaluate_models(
        models, events, presence, train_end, prefix_hits,
        last_seen_by_draw, digit_features, rng
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
        "target": "Number appeared at least once in exported prize rows for a draw.",
        "caveats": [
            "Sampled negatives alter training class prevalence.",
            "Model scores are used for ranking, not calibrated probabilities.",
            "This is a first chronological holdout experiment, not proof of a durable edge.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }
    with open(RESULTS_DIR / "ai_train_v1_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\nTRAINING COMPLETE")
    print(f"Results folder: {RESULTS_DIR}")
    print(f"Elapsed seconds: {metadata['elapsed_seconds']}")
    print("Created:")
    print("  ai_train_v1_summary.csv")
    print("  ai_train_v1_per_draw.csv")
    print("  ai_train_v1_metadata.json")
    print("  ai_train_v1_logistic.joblib")
    print("  ai_train_v1_gradient_boosting.joblib")


if __name__ == "__main__":
    main()
