from pathlib import Path
from datetime import datetime, timezone
import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_CSV = DATA_DIR / "ai_training_draws.csv"
NUMBERS_CSV = DATA_DIR / "ai_training_draw_numbers.csv"

MODEL_FILE = RESULTS_DIR / "ai_train_v3_final.joblib"
RANKING_FILE = RESULTS_DIR / "ai_train_v3_next_draw_ranking.csv"
TOP100_FILE = RESULTS_DIR / "ai_train_v3_top100.csv"
METADATA_FILE = RESULTS_DIR / "ai_train_v3_metadata.json"

NUMBER_COUNT = 10_000
MIN_HISTORY_DRAWS = 50
NEGATIVE_SAMPLES_PER_DRAW = 300
RANDOM_SEED = 42

TOP_K_VALUES = [10, 25, 50, 100]

MODEL_PARAMETERS = {
    "learning_rate": 0.08,
    "max_iter": 100,
    "max_leaf_nodes": 15,
    "l2_regularization": 1.0,
    "random_state": RANDOM_SEED,
}

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


# ============================================================
# VALIDATION AND NUMBER FEATURES
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

    number = int(text)

    if not 0 <= number <= 9999:
        return None

    return number


def make_digit_features():
    ids = np.arange(NUMBER_COUNT, dtype=np.int32)

    digits = np.column_stack([
        (ids // 1000) % 10,
        (ids // 100) % 10,
        (ids // 10) % 10,
        ids % 10,
    ]).astype(np.float32)

    digit_sum = digits.sum(axis=1).astype(np.float32)

    even_count = (
        (digits % 2 == 0).sum(axis=1)
    ).astype(np.float32)

    repeated_count = np.array(
        [
            4 - len(set(f"{number:04d}"))
            for number in ids
        ],
        dtype=np.float32,
    )

    return digits, digit_sum, even_count, repeated_count


# ============================================================
# LOAD CANONICAL CSV EXPORTS
# ============================================================

def load_presence_matrix():
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

    if draws.empty:
        raise ValueError("The draw events CSV is empty.")

    draws["event_order"] = pd.to_numeric(
        draws["event_order"],
        errors="raise",
    ).astype(np.int64)

    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"],
        errors="raise",
    ).astype(np.int64)

    draws = (
        draws.sort_values("event_order")
        .reset_index(drop=True)
    )

    if draws["event_order"].duplicated().any():
        raise ValueError(
            "Duplicate event_order values in draw events CSV."
        )

    # Preserve the exported event sequence. Do not sort by date:
    # event_order is the established chronology for this dataset.
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
            f"Number CSV contains {len(unknown_events)} "
            "event_order values missing from the draw CSV."
        )

    numbers["number_id"] = numbers["number"].map(
        normalize_number
    )

    invalid_rows = int(numbers["number_id"].isna().sum())

    if invalid_rows:
        print(
            f"Warning: ignoring {invalid_rows:,} invalid "
            "number rows."
        )

    numbers = numbers.dropna(
        subset=["number_id"]
    ).copy()

    numbers["number_id"] = numbers["number_id"].astype(
        np.int32
    )

    numbers["draw_index"] = numbers["event_order"].map(
        event_to_index
    ).astype(np.int32)

    n_draws = len(draws)

    print(f"Draw events: {n_draws:,}")
    print(f"Valid number rows: {len(numbers):,}")
    print(f"Unique dates: {draws['date'].nunique():,}")
    print(
        f"Date range: {draws['date'].iloc[0]} "
        f"to {draws['date'].iloc[-1]}"
    )

    print("\nBuilding presence matrix...")

    presence = np.zeros(
        (n_draws, NUMBER_COUNT),
        dtype=np.bool_,
    )

    presence[
        numbers["draw_index"].to_numpy(),
        numbers["number_id"].to_numpy(),
    ] = True

    distinct_counts = presence.sum(axis=1)

    print(f"Presence matrix: {presence.shape}")
    print(
        "Average distinct numbers per draw: "
        f"{distinct_counts.mean():.2f}"
    )

    if n_draws <= MIN_HISTORY_DRAWS:
        raise ValueError(
            f"Need more than {MIN_HISTORY_DRAWS} draws."
        )

    return draws, presence, event_orders


# ============================================================
# HISTORY ARRAYS
# ============================================================

def build_history_arrays(presence):
    """
    prefix_hits[i, n] counts appearances in draws [0, i).

    last_seen_by_draw[i, n] is the latest draw index strictly
    before i, or -1 if the number has never appeared.

    The extra final row permits scoring the next draw at index
    n_draws without accessing outside the array.
    """
    n_draws = presence.shape[0]

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
        (n_draws + 1, NUMBER_COUNT),
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

    # Final historical state: includes every known draw.
    last_seen_by_draw[n_draws] = last_seen

    return prefix_hits, last_seen_by_draw


# ============================================================
# FEATURE MATRIX
# ============================================================

def build_feature_matrix(
    draw_index,
    prefix_hits,
    last_seen_by_draw,
    digit_features,
):
    """
    Generate features for all 10,000 candidates.

    For a historical training example at index i, only draws
    before i are used. For the next-draw ranking, draw_index
    equals n_draws and all existing history is available.
    """
    if not 0 <= draw_index < len(prefix_hits):
        raise ValueError(
            f"Invalid draw index: {draw_index}"
        )

    digits, digit_sum, even_count, repeated_count = (
        digit_features
    )

    total_prior = prefix_hits[draw_index]

    X = np.empty(
        (NUMBER_COUNT, len(FEATURE_NAMES)),
        dtype=np.float32,
    )

    for column, window in enumerate([5, 10, 25, 50]):
        start = max(0, draw_index - window)

        X[:, column] = (
            prefix_hits[draw_index]
            - prefix_hits[start]
        )

    X[:, 4] = total_prior
    X[:, 5] = total_prior / max(draw_index, 1)

    last_seen = last_seen_by_draw[draw_index]

    age = np.where(
        last_seen < 0,
        draw_index + 1,
        draw_index - last_seen,
    )

    X[:, 6] = age
    X[:, 7:11] = digits
    X[:, 11] = digit_sum
    X[:, 12] = even_count
    X[:, 13] = repeated_count

    return X


# ============================================================
# TRAINING EXAMPLES
# ============================================================

def build_training_examples(
    presence,
    prefix_hits,
    last_seen_by_draw,
    digit_features,
):
    """
    Build historical training rows.

    Positive examples: every number that appeared in a draw.
    Negative examples: a reproducible random sample of absent
    numbers from the same draw.

    Each feature row only uses history preceding its target draw.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    all_ids = np.arange(NUMBER_COUNT, dtype=np.int32)

    X_parts = []
    y_parts = []

    n_draws = presence.shape[0]

    print("\nBuilding training examples...")

    for i in range(MIN_HISTORY_DRAWS, n_draws):
        positive_ids = np.flatnonzero(
            presence[i]
        ).astype(np.int32)

        if positive_ids.size == 0:
            continue

        negative_pool = all_ids[
            ~presence[i]
        ]

        sample_count = min(
            NEGATIVE_SAMPLES_PER_DRAW,
            len(negative_pool),
        )

        negative_ids = rng.choice(
            negative_pool,
            size=sample_count,
            replace=False,
        ).astype(np.int32)

        X_all = build_feature_matrix(
            i,
            prefix_hits,
            last_seen_by_draw,
            digit_features,
        )

        selected_ids = np.concatenate([
            positive_ids,
            negative_ids,
        ])

        X_parts.append(X_all[selected_ids])

        y_parts.append(
            np.concatenate([
                np.ones(
                    len(positive_ids),
                    dtype=np.uint8,
                ),
                np.zeros(
                    len(negative_ids),
                    dtype=np.uint8,
                ),
            ])
        )

        if (i + 1) % 200 == 0:
            print(
                f"  Prepared through draw "
                f"{i + 1:,}/{n_draws:,}"
            )

    if not X_parts:
        raise RuntimeError(
            "No training examples were generated."
        )

    X_train = np.concatenate(X_parts, axis=0)
    y_train = np.concatenate(y_parts, axis=0)

    del X_parts, y_parts

    if len(np.unique(y_train)) < 2:
        raise RuntimeError(
            "Training data has fewer than two classes."
        )

    print(f"\nTraining examples: {len(y_train):,}")
    print(f"Positive examples: {int(y_train.sum()):,}")
    print(
        "Negative examples: "
        f"{int((y_train == 0).sum()):,}"
    )
    print(f"Feature count: {X_train.shape[1]}")

    return X_train, y_train


# ============================================================
# DETERMINISTIC RANKING
# ============================================================

def stable_rank(scores):
    """
    Sort by descending score. If scores tie, preserve numeric
    order, so 0000 comes before 0001, and so on.
    """
    scores = np.asarray(scores, dtype=np.float64)

    return np.argsort(
        -scores,
        kind="stable",
    )


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    draws, presence, event_orders = load_presence_matrix()

    n_draws = len(draws)

    print("\nBuilding historical features...")

    prefix_hits, last_seen_by_draw = (
        build_history_arrays(presence)
    )

    digit_features = make_digit_features()

    # --------------------------------------------------------
    # Train final experimental model on all available history
    # --------------------------------------------------------

    X_train, y_train = build_training_examples(
        presence,
        prefix_hits,
        last_seen_by_draw,
        digit_features,
    )

    print("\nTraining final HistGradientBoostingClassifier...")

    model = HistGradientBoostingClassifier(
        **MODEL_PARAMETERS
    )

    model.fit(X_train, y_train)

    del X_train, y_train

    # --------------------------------------------------------
    # Save model
    # --------------------------------------------------------

    print("\nSaving fitted model...")

    joblib.dump(model, MODEL_FILE)

    # --------------------------------------------------------
    # Score every candidate for the next draw
    # --------------------------------------------------------

    print("\nScoring all 10,000 candidates for the next draw...")

    X_next = build_feature_matrix(
        n_draws,
        prefix_hits,
        last_seen_by_draw,
        digit_features,
    )

    model_scores = model.predict_proba(X_next)[:, 1]

    # These are ranking scores from a sampled-negative training
    # setup. They must not be interpreted as calibrated real-world
    # probabilities of winning.
    model_order = stable_rank(model_scores)

    frequency_scores = prefix_hits[n_draws].astype(
        np.int32
    )

    frequency_order = stable_rank(frequency_scores)

    model_ranks = np.empty(
        NUMBER_COUNT,
        dtype=np.int32,
    )
    model_ranks[model_order] = np.arange(
        1,
        NUMBER_COUNT + 1,
        dtype=np.int32,
    )

    frequency_ranks = np.empty(
        NUMBER_COUNT,
        dtype=np.int32,
    )
    frequency_ranks[frequency_order] = np.arange(
        1,
        NUMBER_COUNT + 1,
        dtype=np.int32,
    )

    ids = np.arange(NUMBER_COUNT, dtype=np.int32)

    last_seen = last_seen_by_draw[n_draws]

    draws_since_last_hit = np.where(
        last_seen < 0,
        n_draws + 1,
        n_draws - last_seen,
    )

    digits, digit_sum, even_count, repeated_count = (
        digit_features
    )

    ranking = pd.DataFrame({
        "number": [f"{n:04d}" for n in ids],
        "model_rank": model_ranks,
        "model_score": model_scores,
        "historical_frequency_rank": frequency_ranks,
        "historical_total_hits": frequency_scores,
        "hits_last_5": X_next[:, 0].astype(np.int32),
        "hits_last_10": X_next[:, 1].astype(np.int32),
        "hits_last_25": X_next[:, 2].astype(np.int32),
        "hits_last_50": X_next[:, 3].astype(np.int32),
        "draws_since_last_hit": draws_since_last_hit,
        "digit_sum": digit_sum,
        "even_digit_count": even_count,
        "repeated_digit_count": repeated_count,
    })

    ranking = ranking.sort_values(
        ["model_rank"],
        ascending=True,
    ).reset_index(drop=True)

    ranking.to_csv(
        RANKING_FILE,
        index=False,
        float_format="%.10f",
    )

    ranking.head(100).to_csv(
        TOP100_FILE,
        index=False,
        float_format="%.10f",
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {
        "model_version": 3,
        "model_type": "HistGradientBoostingClassifier",
        "training_mode": "final fit using all available historical draws",
        "trained_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_draws_csv": str(DRAWS_CSV),
        "source_numbers_csv": str(NUMBERS_CSV),
        "draw_count": int(n_draws),
        "first_event_order": int(event_orders[0]),
        "last_event_order": int(event_orders[-1]),
        "first_draw_date": str(draws["date"].iloc[0]),
        "last_draw_date": str(draws["date"].iloc[-1]),
        "number_universe": NUMBER_COUNT,
        "minimum_history_draws": MIN_HISTORY_DRAWS,
        "negative_samples_per_draw": NEGATIVE_SAMPLES_PER_DRAW,
        "random_seed": RANDOM_SEED,
        "model_parameters": MODEL_PARAMETERS,
        "feature_names": FEATURE_NAMES,
        "target": (
            "Whether a number appeared at least once in the "
            "exported prize rows for a draw."
        ),
        "artifacts": {
            "model": str(MODEL_FILE),
            "all_number_ranking": str(RANKING_FILE),
            "top_100_ranking": str(TOP100_FILE),
        },
        "interpretation": [
            "Model scores are rankings, not calibrated probabilities.",
            "Training negatives are sampled, so score calibration "
            "does not represent the full 10,000-number universe.",
            "The model has not established reliable superiority "
            "over historical frequency in prior validation.",
            "Historical ranking is included as a comparison baseline.",
            "No guarantee of future lottery accuracy.",
        ],
        "elapsed_seconds": round(
            time.time() - started,
            2,
        ),
    }

    with METADATA_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(metadata, f, indent=2)

    # --------------------------------------------------------
    # Print summary
    # --------------------------------------------------------

    print("\n" + "=" * 80)
    print("FINAL MODEL TRAINING COMPLETE")
    print("=" * 80)

    print(f"Historical draws used: {n_draws:,}")
    print(
        f"Training date range: {draws['date'].iloc[0]} "
        f"to {draws['date'].iloc[-1]}"
    )

    print("\nTop 25 model-ranked numbers:")
    print(
        ranking.head(25)[[
            "number",
            "model_rank",
            "model_score",
            "historical_total_hits",
            "historical_frequency_rank",
            "draws_since_last_hit",
        ]].to_string(
            index=False,
            float_format=lambda x: f"{x:.8f}",
        )
    )

    print("\nSaved files:")
    print(f"  Model:       {MODEL_FILE}")
    print(f"  All numbers: {RANKING_FILE}")
    print(f"  Top 100:     {TOP100_FILE}")
    print(f"  Metadata:    {METADATA_FILE}")

    print(f"\nElapsed: {time.time() - started:.2f} seconds")


if __name__ == "__main__":
    main()