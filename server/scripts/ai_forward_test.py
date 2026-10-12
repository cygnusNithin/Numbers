from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import time

import joblib
import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"
SUMMARY_FILE = RESULTS_DIR / "ai_forward_summary.csv"

DRAWS_CSV = DATA_DIR / "ai_training_draws.csv"
NUMBERS_CSV = DATA_DIR / "ai_training_draw_numbers.csv"
MODEL_FILE = RESULTS_DIR / "ai_train_v3_final.joblib"

PREDICTIONS_FILE = RESULTS_DIR / "ai_forward_predictions.csv"
EVALUATION_FILE = RESULTS_DIR / "ai_forward_evaluation.csv"
COMPARISON_FILE = RESULTS_DIR / "ai_forward_comparisons.csv"
METADATA_FILE = RESULTS_DIR / "ai_forward_metadata.json"

NUMBER_COUNT = 10_000
TOP_K_VALUES = [10, 25, 50, 100]
RANDOM_SEED = 42042

METHODS = ["model", "historical_frequency", "random"]


# ============================================================
# UTILITIES
# ============================================================

def require_columns(df, columns, label):
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


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


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


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
        [4 - len(set(f"{n:04d}")) for n in ids],
        dtype=np.float32,
    )

    return digits, digit_sum, even_count, repeated_count


# ============================================================
# LOAD CANONICAL DATA
# ============================================================

def load_data():
    print("Loading canonical CSV exports...")

    if not DRAWS_CSV.exists():
        raise FileNotFoundError(DRAWS_CSV)

    if not NUMBERS_CSV.exists():
        raise FileNotFoundError(NUMBERS_CSV)

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Trained model not found: {MODEL_FILE}\n"
            "Run ai_train_v3_final.py first."
        )

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
        raise ValueError("Draw events CSV is empty.")

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

    unknown = (
        set(numbers["event_order"].unique())
        - set(event_to_index)
    )

    if unknown:
        raise ValueError(
            f"{len(unknown)} number-data event IDs "
            "are missing from the draw events CSV."
        )

    numbers["number_id"] = numbers["number"].map(normalize_number)

    invalid = int(numbers["number_id"].isna().sum())

    if invalid:
        print(f"Ignoring invalid number rows: {invalid:,}")

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

    print(f"Draws: {len(draws):,}")
    print(f"Valid number rows: {len(numbers):,}")
    print(f"Latest draw date: {draws['date'].iloc[-1]}")
    print(f"Latest event_order: {int(event_orders[-1])}")

    return draws, presence, event_orders


# ============================================================
# BUILD FEATURES — MATCHES V3 TRAINING
# ============================================================

def build_history_arrays(presence):
    n_draws = presence.shape[0]

    prefix_hits = np.zeros(
        (n_draws + 1, NUMBER_COUNT),
        dtype=np.int32,
    )

    prefix_hits[1:] = np.cumsum(
        presence, axis=0, dtype=np.int32
    )

    last_seen_by_draw = np.full(
        (n_draws + 1, NUMBER_COUNT),
        -1,
        dtype=np.int32,
    )

    last_seen = np.full(NUMBER_COUNT, -1, dtype=np.int32)

    for i in range(n_draws):
        last_seen_by_draw[i] = last_seen
        last_seen[presence[i]] = i

    last_seen_by_draw[n_draws] = last_seen

    return prefix_hits, last_seen_by_draw


def build_next_features(
    n_draws,
    prefix_hits,
    last_seen_by_draw,
):
    digit_features = make_digit_features()
    digits, digit_sum, even_count, repeated_count = digit_features

    X = np.empty((NUMBER_COUNT, 14), dtype=np.float32)

    for column, window in enumerate([5, 10, 25, 50]):
        start = max(0, n_draws - window)
        X[:, column] = (
            prefix_hits[n_draws] - prefix_hits[start]
        )

    total_prior = prefix_hits[n_draws]

    X[:, 4] = total_prior
    X[:, 5] = total_prior / max(n_draws, 1)

    last_seen = last_seen_by_draw[n_draws]

    X[:, 6] = np.where(
        last_seen < 0,
        n_draws + 1,
        n_draws - last_seen,
    )

    X[:, 7:11] = digits
    X[:, 11] = digit_sum
    X[:, 12] = even_count
    X[:, 13] = repeated_count

    return X, last_seen


# ============================================================
# GENERATE PREDICTIONS
# ============================================================

def predict():
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    draws, presence, event_orders = load_data()

    n_draws = len(draws)
    cutoff = int(event_orders[-1])
    latest_draw = draws.iloc[-1]

    # Do not generate a second prediction for the same cutoff.
    if PREDICTIONS_FILE.exists():
        old = pd.read_csv(
            PREDICTIONS_FILE,
            dtype={
                "number": str,
                "as_of_serialNumber": str,
                "as_of_date": str,
                "model_sha256": str,
            },
        )

        if not old.empty:
            old_cutoffs = pd.to_numeric(
                old["as_of_event_order"],
                errors="coerce",
            )

            if (old_cutoffs == cutoff).any():
                print("\nPrediction already recorded for this cutoff.")
                print(f"event_order: {cutoff}")
                print(f"date: {latest_draw['date']}")
                print("Existing predictions were not changed.")
                print("\nRun the evaluation command when a new draw is added.")
                return

    print("\nLoading fixed v3 model...")
    model = joblib.load(MODEL_FILE)
    model_hash = sha256_file(MODEL_FILE)

    print("Building current-history features...")
    prefix_hits, last_seen_by_draw = build_history_arrays(presence)

    X, last_seen = build_next_features(
        n_draws,
        prefix_hits,
        last_seen_by_draw,
    )

    print("Scoring model candidates...")
    scores = model.predict_proba(X)[:, 1]

    ids = np.arange(NUMBER_COUNT, dtype=np.int32)

    # Stable sorting: ties preserve ascending number order.
    model_order = np.argsort(-scores, kind="stable")
    frequency_order = np.argsort(
        -prefix_hits[n_draws], kind="stable"
    )

    # Deterministic random baseline for this cutoff.
    rng = np.random.default_rng(RANDOM_SEED + cutoff)
    random_order = rng.permutation(ids)

    orders = {
        "model": model_order,
        "historical_frequency": frequency_order,
        "random": random_order,
    }

    output_rows = []

    for method, order in orders.items():
        for rank, number_id in enumerate(order[:100], start=1):
            output_rows.append({
                "prediction_created_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "as_of_event_order": cutoff,
                "as_of_serialNumber": str(
                    latest_draw["serialNumber"]
                ),
                "as_of_date": str(latest_draw["date"]),
                "method": method,
                "method_rank": rank,
                "number": f"{int(number_id):04d}",
                "model_score": (
                    float(scores[number_id])
                    if method == "model"
                    else ""
                ),
                "historical_total_hits": int(
                    prefix_hits[n_draws, number_id]
                ),
                "draws_since_last_hit": int(
                    n_draws + 1
                    if last_seen[number_id] < 0
                    else n_draws - last_seen[number_id]
                ),
                "model_sha256": model_hash,
            })

    new_predictions = pd.DataFrame(output_rows)

    if PREDICTIONS_FILE.exists():
        existing = pd.read_csv(
            PREDICTIONS_FILE,
            dtype={
                "number": str,
                "as_of_serialNumber": str,
                "as_of_date": str,
                "model_sha256": str,
            },
        )

        combined = pd.concat(
            [existing, new_predictions],
            ignore_index=True,
        )
    else:
        combined = new_predictions

    combined.to_csv(PREDICTIONS_FILE, index=False)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "latest_event_order": cutoff,
        "latest_serialNumber": str(latest_draw["serialNumber"]),
        "latest_date": str(latest_draw["date"]),
        "model_file": str(MODEL_FILE),
        "model_sha256": model_hash,
        "predictions_file": str(PREDICTIONS_FILE),
        "methods": METHODS,
        "top_k_values": TOP_K_VALUES,
        "important_note": (
            "Predictions are frozen per cutoff. Do not edit old rows "
            "after the target draw becomes available. Model scores are "
            "ranking scores, not calibrated probabilities."
        ),
    }

    METADATA_FILE.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print("FORWARD PREDICTION SAVED")
    print("=" * 72)
    print(f"Cutoff event_order: {cutoff}")
    print(f"Cutoff date: {latest_draw['date']}")
    print(f"Model SHA-256: {model_hash}")
    print(f"Predictions saved: {PREDICTIONS_FILE}")

    model_top = new_predictions[
        new_predictions["method"] == "model"
    ].head(25)

    print("\nModel Top 25:")
    print(
        model_top[[
            "method_rank",
            "number",
            "model_score",
            "historical_total_hits",
        ]].to_string(index=False)
    )

    print(f"\nElapsed: {time.time() - started:.2f} seconds")


# ============================================================
# EVALUATE SAVED PREDICTIONS AGAINST NEXT DRAW
# ============================================================

def evaluate():
    if not PREDICTIONS_FILE.exists():
        raise FileNotFoundError(
            f"No prediction ledger found: {PREDICTIONS_FILE}\n"
            "Run the predict command first."
        )

    draws, presence, event_orders = load_data()

    predictions = pd.read_csv(
        PREDICTIONS_FILE,
        dtype={
            "number": str,
            "as_of_serialNumber": str,
            "as_of_date": str,
            "model_sha256": str,
        },
    )

    require_columns(
        predictions,
        [
            "as_of_event_order",
            "method",
            "method_rank",
            "number",
            "model_sha256",
        ],
        "Forward predictions CSV",
    )

    event_to_index = {
        int(event_order): i
        for i, event_order in enumerate(event_orders)
    }

    predictions["as_of_event_order"] = pd.to_numeric(
        predictions["as_of_event_order"],
        errors="raise",
    ).astype(np.int64)

    predictions["method_rank"] = pd.to_numeric(
        predictions["method_rank"],
        errors="raise",
    ).astype(np.int64)

    predictions["number_id"] = predictions["number"].map(
        normalize_number
    )

    predictions = predictions.dropna(subset=["number_id"]).copy()
    predictions["number_id"] = predictions["number_id"].astype(np.int32)

    evaluation_rows = []

    # Each cutoff is evaluated against the immediately following
    # event in event_order, never against the cutoff draw itself.
    for cutoff, group in predictions.groupby(
        "as_of_event_order",
        sort=True,
    ):
        if int(cutoff) not in event_to_index:
            continue

        cutoff_index = event_to_index[int(cutoff)]
        target_index = cutoff_index + 1

        # The next draw has not yet arrived in the canonical export.
        if target_index >= len(draws):
            continue

        target_draw = draws.iloc[target_index]
        target_event_order = int(event_orders[target_index])
        actual = presence[target_index]

        for _, row in group.iterrows():
            number_id = int(row["number_id"])

            evaluation_rows.append({
                "as_of_event_order": int(cutoff),
                "as_of_date": str(row["as_of_date"]),
                "target_event_order": target_event_order,
                "target_serialNumber": str(
                    target_draw["serialNumber"]
                ),
                "target_date": str(target_draw["date"]),
                "method": str(row["method"]),
                "method_rank": int(row["method_rank"]),
                "number": f"{number_id:04d}",
                "hit": int(actual[number_id]),
                "model_sha256": str(row["model_sha256"]),
            })

    if not evaluation_rows:
        print("\nNo saved predictions have a subsequent draw yet.")
        print("Keep the ledger. Re-run evaluation after new results are imported.")
        return

    evaluation = pd.DataFrame(evaluation_rows)

    # Keep evaluation repeatable: replace evaluation outputs from
    # the frozen ledger and current canonical results.
    evaluation.to_csv(EVALUATION_FILE, index=False)

    # Summarize each strategy at each Top-K cutoff.
    summary_rows = []

    group_columns = ["model_sha256", "method"]

    for (model_hash, method), group in evaluation.groupby(
        group_columns,
        dropna=False,
    ):
        for k in TOP_K_VALUES:
            selected = group[group["method_rank"] <= k]

            by_draw = (
                selected.groupby(
                    ["as_of_event_order", "target_event_order"],
                    as_index=False,
                )
                .agg(
                    hits=("hit", "sum"),
                    selected_count=("number", "count"),
                )
            )

            if by_draw.empty:
                continue

            summary_rows.append({
                "model_sha256": model_hash,
                "method": method,
                "top_k": k,
                "evaluated_draws": len(by_draw),
                "mean_hits": by_draw["hits"].mean(),
                "median_hits": by_draw["hits"].median(),
                "total_hits": int(by_draw["hits"].sum()),
                "mean_precision": (
                    by_draw["hits"].sum()
                    / by_draw["selected_count"].sum()
                ),
                "first_target_date": selected["target_date"].min(),
                "last_target_date": selected["target_date"].max(),
            })

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(SUMMARY_FILE, index=False)

    print("\n" + "=" * 72)
    print("FORWARD TEST EVALUATION")
    print("=" * 72)
    print(f"Evaluated target draws: {evaluation['target_event_order'].nunique()}")
    print(f"Per-number evaluation rows: {len(evaluation):,}")
    print(f"Detailed results: {EVALUATION_FILE}")
    print(f"Summary: {SUMMARY_FILE}")

    if not summary.empty:
        print("\nMean hits per draw by method and Top-K:")
        display_columns = [
            "method",
            "top_k",
            "evaluated_draws",
            "mean_hits",
            "median_hits",
            "total_hits",
            "mean_precision",
        ]

        print(
            summary[display_columns].sort_values(
                ["top_k", "method"]
            ).to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )

    # Paired comparisons: same cutoff/target draws and same model
    # version only. Descriptive differences, not a significance test.
    comparisons = []

    for model_hash, hash_group in evaluation.groupby(
        "model_sha256",
        dropna=False,
    ):
        hits_by_draw_method = {}

        for method in METHODS:
            for k in TOP_K_VALUES:
                subset = hash_group[
                    (hash_group["method"] == method)
                    & (hash_group["method_rank"] <= k)
                ]

                hits_by_draw_method[(method, k)] = (
                    subset.groupby("as_of_event_order")["hit"].sum()
                )

        for k in TOP_K_VALUES:
            model_hits = hits_by_draw_method[("model", k)]

            for baseline in ["historical_frequency", "random"]:
                base_hits = hits_by_draw_method[(baseline, k)]

                paired = pd.concat(
                    [
                        model_hits.rename("model_hits"),
                        base_hits.rename("baseline_hits"),
                    ],
                    axis=1,
                    join="inner",
                ).dropna()

                if paired.empty:
                    continue

                differences = (
                    paired["model_hits"] - paired["baseline_hits"]
                )

                comparisons.append({
                    "model_sha256": model_hash,
                    "top_k": k,
                    "model_vs": baseline,
                    "paired_draws": len(paired),
                    "model_mean_hits": paired["model_hits"].mean(),
                    "baseline_mean_hits": paired["baseline_hits"].mean(),
                    "mean_hit_difference": differences.mean(),
                    "draws_model_won": int((differences > 0).sum()),
                    "draws_baseline_won": int((differences < 0).sum()),
                    "draws_tied": int((differences == 0).sum()),
                })

    comparison_df = pd.DataFrame(comparisons)
    comparison_df.to_csv(COMPARISON_FILE, index=False)

    if not comparison_df.empty:
        print("\nPaired mean-hit differences (model minus baseline):")
        print(
            comparison_df[[
                "top_k",
                "model_vs",
                "paired_draws",
                "mean_hit_difference",
                "draws_model_won",
                "draws_baseline_won",
                "draws_tied",
            ]].to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )

    print(
        "\nImportant: a small number of future draws is not enough "
        "to establish predictive advantage. Treat these as ongoing "
        "out-of-sample measurements, not proof of a winning strategy."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "predict"

    if command == "predict":
        predict()
    elif command == "evaluate":
        evaluate()
    else:
        raise SystemExit(
            "Usage:\n"
            "  python scripts/ai_forward_test.py predict\n"
            "  python scripts/ai_forward_test.py evaluate"
        )