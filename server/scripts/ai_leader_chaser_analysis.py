
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

NUMBER_COUNT = 10_000

# Historical chaser analysis
LOOKBACK_DRAWS = 200
BLOCK_SIZE = 10
LEADERS_TO_ANALYZE = 10
MIN_VALID_BLOCKS = 8

# Forward test
FIRST_TEST_INDEX = 500
FORWARD_HORIZON = 10
FORWARD_STEP = 10
TOP_K = 25
RANDOM_SEED = 7396


# ============================================================
# DATA LOADING
# ============================================================

def normalize_number(value):
    """Normalize a valid number to four digits."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit() or len(text) > 4:
        return None

    number = int(text)

    if not 0 <= number < NUMBER_COUNT:
        return None

    return f"{number:04d}"


def number_text(number_id):
    return f"{int(number_id):04d}"


def save_csv(frame, filename):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False)
    print(f"Saved: {path}")
    return path


def load_data():
    print("Loading canonical CSV exports...")

    if not DRAWS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {DRAWS_FILE}")

    if not NUMBERS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {NUMBERS_FILE}")

    draws = pd.read_csv(DRAWS_FILE)
    rows = pd.read_csv(NUMBERS_FILE, dtype={"number": "string"})

    required_draw_columns = {
        "event_order", "serialNumber", "date"
    }
    required_number_columns = {
        "event_order", "serialNumber", "number"
    }

    if not required_draw_columns.issubset(draws.columns):
        raise ValueError(
            f"Draw CSV requires columns: {required_draw_columns}"
        )

    if not required_number_columns.issubset(rows.columns):
        raise ValueError(
            f"Number CSV requires columns: {required_number_columns}"
        )

    draws["event_order"] = pd.to_numeric(
        draws["event_order"], errors="coerce"
    )
    rows["event_order"] = pd.to_numeric(
        rows["event_order"], errors="coerce"
    )

    draws = draws.dropna(subset=["event_order"]).copy()
    rows = rows.dropna(subset=["event_order"]).copy()

    draws["event_order"] = draws["event_order"].astype(np.int64)
    rows["event_order"] = rows["event_order"].astype(np.int64)

    draws = draws.sort_values("event_order").reset_index(drop=True)

    if draws["event_order"].duplicated().any():
        raise ValueError("Duplicate event_order values in draw CSV.")

    # Confirm the event-order/serial-number mapping.
    draw_keys = draws[["event_order", "serialNumber"]].copy()
    row_keys = rows[["event_order", "serialNumber"]].drop_duplicates()

    check = row_keys.merge(
        draw_keys,
        on=["event_order", "serialNumber"],
        how="left",
        indicator=True,
    )

    if (check["_merge"] != "both").any():
        raise ValueError(
            "The CSV files contain mismatched event keys."
        )

    valid_orders = set(draws["event_order"].tolist())
    rows = rows[rows["event_order"].isin(valid_orders)].copy()

    rows["number4"] = rows["number"].map(normalize_number)
    invalid_count = int(rows["number4"].isna().sum())

    rows = rows.dropna(subset=["number4"]).copy()
    rows["number_id"] = rows["number4"].astype(np.int32)

    order_to_index = {
        int(order): i
        for i, order in enumerate(draws["event_order"].to_numpy())
    }

    rows["event_index"] = rows["event_order"].map(order_to_index)
    rows = rows.dropna(subset=["event_index"]).copy()
    rows["event_index"] = rows["event_index"].astype(np.int32)

    # One number counts at most once per event, regardless of prize rows.
    presence = np.zeros(
        (len(draws), NUMBER_COUNT),
        dtype=np.bool_,
    )

    flat_indices = (
        rows["event_index"].to_numpy(dtype=np.int64) * NUMBER_COUNT
        + rows["number_id"].to_numpy(dtype=np.int64)
    )

    presence.ravel()[flat_indices] = True

    draws["parsed_date"] = pd.to_datetime(
        draws["date"],
        dayfirst=True,
        errors="coerce",
    )

    print(f"Draw events: {len(draws):,}")
    print(f"Valid distinct number appearances: {int(presence.sum()):,}")
    print(f"Invalid number rows ignored: {invalid_count:,}")
    print(f"Unique dates: {draws['parsed_date'].nunique():,}")
    print(
        f"Date range: {draws['parsed_date'].min()} "
        f"to {draws['parsed_date'].max()}"
    )

    return draws, presence


# ============================================================
# UTILITIES
# ============================================================

def block_counts(binary_window, block_size):
    """
    Return hit counts for non-overlapping blocks.

    Input:
        draws x numbers boolean matrix

    Output:
        blocks x numbers integer matrix
    """
    usable_length = (
        binary_window.shape[0] // block_size
    ) * block_size

    if usable_length == 0:
        return np.empty(
            (0, binary_window.shape[1]),
            dtype=np.int32,
        )

    trimmed = binary_window[-usable_length:]

    return trimmed.reshape(
        -1, block_size, binary_window.shape[1]
    ).sum(axis=1, dtype=np.int32)


def pearson_correlations(block_matrix, reference):
    """
    Pearson correlation between the reference series and every column.

    Constant columns or insufficient blocks produce NaN.
    """
    x = np.asarray(block_matrix, dtype=np.float64)
    y = np.asarray(reference, dtype=np.float64)

    if x.ndim != 2 or x.shape[0] < MIN_VALID_BLOCKS:
        return np.full(x.shape[1], np.nan, dtype=np.float64)

    x_centered = x - x.mean(axis=0, keepdims=True)
    y_centered = y - y.mean()

    x_ss = np.sum(x_centered * x_centered, axis=0)
    y_ss = float(np.sum(y_centered * y_centered))

    denominator = np.sqrt(x_ss * y_ss)
    numerator = y_centered @ x_centered

    correlations = np.full(x.shape[1], np.nan, dtype=np.float64)
    valid = denominator > 0

    correlations[valid] = numerator[valid] / denominator[valid]

    return correlations


# ============================================================
# 1. HISTORICAL LEADERBOARD
# ============================================================

def build_leader_history(draws, presence):
    print("\nReconstructing historical leaderboard...")

    # Use signed integer counts throughout this analysis.
    cumulative = np.cumsum(
        presence.astype(np.int32),
        axis=0,
        dtype=np.int32,
    )

    leaderboard_records = []
    change_records = []

    previous_leader = None

    for i, (_, draw) in enumerate(draws.iterrows()):
        counts = cumulative[i]
        order = np.argsort(-counts, kind="stable")

        leader = int(order[0])
        leader_hits = int(counts[leader])

        for rank_index, number_id in enumerate(order[:20], start=1):
            number_id = int(number_id)
            hits = int(counts[number_id])

            leaderboard_records.append({
                "event_index": i,
                "event_order": int(draw["event_order"]),
                "date": draw["date"],
                "number": number_text(number_id),
                "cumulative_hits": hits,
                "rank": rank_index,
                "gap_to_leader": leader_hits - hits,
            })

        if previous_leader is None:
            change_type = "initial_leader"
        elif leader != previous_leader:
            change_type = "leader_changed"
        else:
            change_type = "leader_unchanged"

        if change_type != "leader_unchanged":
            change_records.append({
                "event_index": i,
                "event_order": int(draw["event_order"]),
                "date": draw["date"],
                "previous_leader": (
                    number_text(previous_leader)
                    if previous_leader is not None else None
                ),
                "new_leader": number_text(leader),
                "new_leader_hits": leader_hits,
                "change_type": change_type,
            })

        previous_leader = leader

    leaderboard_df = pd.DataFrame(leaderboard_records)
    changes_df = pd.DataFrame(change_records)

    save_csv(leaderboard_df, "ai_leader_history.csv")
    save_csv(changes_df, "ai_leader_changes.csv")

    latest_counts = cumulative[-1]
    latest_order = np.argsort(-latest_counts, kind="stable")[:20]

    print("\nMost recent cumulative leaders:")
    print("Rank  Number  Hits")

    for rank, number_id in enumerate(latest_order, start=1):
        print(
            f"{rank:>4}  {number_text(number_id)}  "
            f"{int(latest_counts[number_id]):>4}"
        )

    print(f"\nLeader changes recorded: {len(changes_df):,}")

    return cumulative, leaderboard_df, changes_df


# ============================================================
# 2. CHASER GAP MOVEMENTS
# ============================================================

def build_chaser_movements(draws, cumulative):
    print("\nTracking chasers and lead-gap changes...")

    records = []

    previous_gaps = None
    previous_leader = None

    for i, (_, draw) in enumerate(draws.iterrows()):
        counts = cumulative[i]

        order = np.argsort(-counts, kind="stable")
        leader = int(order[0])
        leader_hits = int(counts[leader])

        # Convert to signed integers BEFORE subtraction.
        # This prevents uint32 underflow/overflow.
        signed_counts = counts.astype(np.int64, copy=False)
        gaps = leader_hits - signed_counts

        for rank_index, number_id in enumerate(order[1:101], start=2):
            number_id = int(number_id)
            gap = int(gaps[number_id])

            if previous_gaps is None:
                previous_gap = np.nan
                gap_change = np.nan
                closing_gap = np.nan
            else:
                # Explicit Python integers: negative changes are valid.
                previous_gap = int(previous_gaps[number_id])
                gap_change = int(gap - previous_gap)
                closing_gap = bool(gap_change < 0)

            records.append({
                "event_index": i,
                "event_order": int(draw["event_order"]),
                "date": draw["date"],
                "leader": number_text(leader),
                "leader_changed": (
                    previous_leader is not None
                    and leader != previous_leader
                ),
                "leader_hits": leader_hits,
                "chaser": number_text(number_id),
                "chaser_hits": int(signed_counts[number_id]),
                "chaser_rank": rank_index,
                "gap_to_leader": gap,
                "previous_gap": previous_gap,
                "gap_change": gap_change,
                "closing_gap": closing_gap,
            })

        # Save an independent signed snapshot for the next event.
        previous_gaps = gaps.astype(np.int64, copy=True)
        previous_leader = leader

    movements = pd.DataFrame(records)
    save_csv(movements, "ai_chaser_movements.csv")

    # Only count events where a previous gap was available.
    observed = movements.dropna(subset=["gap_change"]).copy()
    observed["closing_gap"] = observed["closing_gap"].astype(bool)

    if not observed.empty:
        summary = (
            observed.groupby("chaser", as_index=False)
            .agg(
                observed_transitions=("gap_change", "count"),
                gap_closing_events=("closing_gap", "sum"),
                mean_gap_change=("gap_change", "mean"),
                latest_rank=("chaser_rank", "last"),
                latest_gap=("gap_to_leader", "last"),
            )
        )

        summary["gap_closing_rate"] = (
            summary["gap_closing_events"]
            / summary["observed_transitions"].clip(lower=1)
        )

        summary = summary.sort_values(
            ["gap_closing_rate", "gap_closing_events"],
            ascending=False,
        )

        save_csv(
            summary,
            "ai_chaser_gap_closing_summary.csv",
        )

    return movements


# ============================================================
# 3. CO-MOVEMENT ANALYSIS
# ============================================================

def analyze_comovement(draws, presence):
    print("\nAnalyzing numbers that move together...")

    blocks = block_counts(presence, BLOCK_SIZE)
    total_hits = presence.sum(axis=0, dtype=np.int64)

    top_leaders = np.argsort(-total_hits, kind="stable")[
        :LEADERS_TO_ANALYZE
    ]

    records = []

    for leader_id in top_leaders:
        leader_id = int(leader_id)

        correlations = pearson_correlations(
            blocks,
            blocks[:, leader_id],
        )

        correlations[leader_id] = np.nan

        valid_ids = np.flatnonzero(np.isfinite(correlations))
        valid_ids = valid_ids[valid_ids != leader_id]

        candidate_order = valid_ids[
            np.argsort(correlations[valid_ids])[::-1]
        ]

        for rank, candidate_id in enumerate(candidate_order[:100], start=1):
            candidate_id = int(candidate_id)

            records.append({
                "leader": number_text(leader_id),
                "leader_total_hits": int(total_hits[leader_id]),
                "candidate": number_text(candidate_id),
                "candidate_total_hits": int(total_hits[candidate_id]),
                "block_size_draws": BLOCK_SIZE,
                "number_of_blocks": int(blocks.shape[0]),
                "pearson_correlation": float(
                    correlations[candidate_id]
                ),
                "correlation_rank": rank,
            })

    result = pd.DataFrame(records)

    if not result.empty:
        result = result.sort_values(
            ["leader", "pearson_correlation"],
            ascending=[True, False],
        )

    save_csv(result, "ai_co_movement.csv")

    # Dedicated co-movement report for 7396.
    target_id = 7396

    target_correlations = pearson_correlations(
        blocks,
        blocks[:, target_id],
    )
    target_correlations[target_id] = np.nan

    valid_ids = np.flatnonzero(np.isfinite(target_correlations))
    valid_ids = valid_ids[valid_ids != target_id]

    target_order = valid_ids[
        np.argsort(target_correlations[valid_ids])[::-1]
    ]

    target_records = []

    for rank, candidate_id in enumerate(target_order[:100], start=1):
        candidate_id = int(candidate_id)

        target_records.append({
            "reference_number": "7396",
            "candidate": number_text(candidate_id),
            "candidate_total_hits": int(total_hits[candidate_id]),
            "pearson_correlation": float(
                target_correlations[candidate_id]
            ),
            "correlation_rank": rank,
        })

    target_df = pd.DataFrame(target_records)
    save_csv(target_df, "ai_comovement_with_7396.csv")

    print("\nTop positive co-movement candidates for 7396:")

    for row in target_records[:15]:
        print(
            f"{row['candidate']}  "
            f"correlation={row['pearson_correlation']:+.4f}  "
            f"total_hits={row['candidate_total_hits']}"
        )

    print(
        "\nCorrelations are descriptive. They do not prove that "
        "one number predicts or influences another."
    )

    return result, target_df


# ============================================================
# 4. FORWARD TEST
# ============================================================

def forward_test(draws, presence):
    print("\nRunning chronological forward test...")

    n_draws = len(draws)

    if FIRST_TEST_INDEX + FORWARD_HORIZON > n_draws:
        raise ValueError(
            "Not enough draws for the configured forward test."
        )

    if LOOKBACK_DRAWS % BLOCK_SIZE != 0:
        raise ValueError(
            "LOOKBACK_DRAWS must be divisible by BLOCK_SIZE."
        )

    rng = np.random.default_rng(RANDOM_SEED)

    test_records = []
    prediction_records = []

    for cutoff in range(
        FIRST_TEST_INDEX,
        n_draws - FORWARD_HORIZON + 1,
        FORWARD_STEP,
    ):
        # Only past data is used to choose the candidates.
        train = presence[:cutoff]
        future = presence[cutoff:cutoff + FORWARD_HORIZON]

        cumulative_counts = train.sum(axis=0, dtype=np.int64)
        leader_id = int(np.argmax(cumulative_counts))

        window = train[-LOOKBACK_DRAWS:]
        blocks = block_counts(window, BLOCK_SIZE)

        correlations = pearson_correlations(
            blocks,
            blocks[:, leader_id],
        )
        correlations[leader_id] = np.nan

        valid_ids = np.flatnonzero(np.isfinite(correlations))
        valid_ids = valid_ids[valid_ids != leader_id]

        chaser_order = valid_ids[
            np.argsort(correlations[valid_ids])[::-1]
        ]
        chaser_candidates = chaser_order[:TOP_K]

        # Historical-frequency baseline.
        frequency_candidates = np.argsort(
            -cumulative_counts,
            kind="stable",
        )[:TOP_K]

        # Random baseline.
        random_candidates = rng.choice(
            NUMBER_COUNT,
            size=TOP_K,
            replace=False,
        )

        # Evaluate only after selections are finalized.
        chaser_hits = int(future[:, chaser_candidates].sum())
        frequency_hits = int(future[:, frequency_candidates].sum())
        random_hits = int(future[:, random_candidates].sum())

        cutoff_date = str(draws.iloc[cutoff - 1]["date"])
        first_test_date = str(draws.iloc[cutoff]["date"])

        test_records.append({
            "cutoff_index": cutoff,
            "cutoff_event_order": int(
                draws.iloc[cutoff - 1]["event_order"]
            ),
            "cutoff_date": cutoff_date,
            "first_test_event_order": int(
                draws.iloc[cutoff]["event_order"]
            ),
            "first_test_date": first_test_date,
            "leader_at_cutoff": number_text(leader_id),
            "leader_hits_at_cutoff": int(
                cumulative_counts[leader_id]
            ),
            "horizon_draws": FORWARD_HORIZON,
            "top_k": TOP_K,
            "chaser_hits": chaser_hits,
            "frequency_hits": frequency_hits,
            "random_hits": random_hits,
            "chaser_hits_per_draw": chaser_hits / FORWARD_HORIZON,
            "frequency_hits_per_draw": (
                frequency_hits / FORWARD_HORIZON
            ),
            "random_hits_per_draw": random_hits / FORWARD_HORIZON,
        })

        strategies = (
            ("leader_comovement", chaser_candidates),
            ("historical_frequency", frequency_candidates),
            ("random", random_candidates),
        )

        for strategy, candidates in strategies:
            for rank, number_id in enumerate(candidates, start=1):
                number_id = int(number_id)

                prediction_records.append({
                    "cutoff_index": cutoff,
                    "cutoff_date": cutoff_date,
                    "first_test_date": first_test_date,
                    "strategy": strategy,
                    "rank": rank,
                    "number": number_text(number_id),
                    "leader_at_cutoff": number_text(leader_id),
                    "historical_hits_at_cutoff": int(
                        cumulative_counts[number_id]
                    ),
                    "historical_leader_correlation": (
                        float(correlations[number_id])
                        if np.isfinite(correlations[number_id])
                        else np.nan
                    ),
                })

    test_df = pd.DataFrame(test_records)
    prediction_df = pd.DataFrame(prediction_records)

    save_csv(test_df, "ai_chaser_forward_test.csv")
    save_csv(prediction_df, "ai_chaser_forward_predictions.csv")

    if test_df.empty:
        print("No forward-test periods were available.")
        return test_df

    summary_rows = []

    for strategy, column in (
        ("leader_comovement", "chaser_hits"),
        ("historical_frequency", "frequency_hits"),
        ("random", "random_hits"),
    ):
        summary_rows.append({
            "strategy": strategy,
            "test_periods": len(test_df),
            "total_future_draws": int(
                len(test_df) * FORWARD_HORIZON
            ),
            "mean_hits_per_period": float(test_df[column].mean()),
            "median_hits_per_period": float(test_df[column].median()),
            "total_hits": int(test_df[column].sum()),
        })

    summary_df = pd.DataFrame(summary_rows)
    save_csv(summary_df, "ai_chaser_forward_summary.csv")

    print("\nForward-test summary:")
    print(summary_df.to_string(index=False))

    print(
        "\nCompare leader_comovement with historical_frequency first. "
        "Beating random alone does not establish a predictive advantage."
    )

    return test_df


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    draws, presence = load_data()

    cumulative, _, _ = build_leader_history(draws, presence)

    build_chaser_movements(draws, cumulative)

    analyze_comovement(draws, presence)

    forward_test(draws, presence)

    summary = {
        "draw_count": int(len(draws)),
        "number_universe": NUMBER_COUNT,
        "total_distinct_number_appearances": int(presence.sum()),
        "overall_hit_rate": float(presence.mean()),
        "lookback_draws": LOOKBACK_DRAWS,
        "block_size": BLOCK_SIZE,
        "forward_horizon": FORWARD_HORIZON,
        "forward_step": FORWARD_STEP,
        "top_k": TOP_K,
        "first_test_index": FIRST_TEST_INDEX,
        "random_seed": RANDOM_SEED,
        "elapsed_seconds": round(time.time() - started, 2),
        "warning": (
            "Historical correlations are descriptive. Forward "
            "performance is exploratory and does not establish "
            "future predictability."
        ),
    }

    summary_path = RESULTS_DIR / "ai_leader_chaser_metadata.json"
    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved: {summary_path}")
    print(f"\nCompleted in {summary['elapsed_seconds']} seconds.")


if __name__ == "__main__":
    main()
