
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# Configuration
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

DRAWS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

NUMBER_COUNT = 10000
MIN_HISTORY_EVENTS = 50


# ============================================================
# Load data
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
            f"Draw CSV must contain: {sorted(required)}"
        )

    draws["event_order"] = pd.to_numeric(
        draws["event_order"], errors="raise"
    ).astype(int)

    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="raise"
    ).astype(int)

    draws = draws.sort_values("event_order").reset_index(drop=True)

    expected_order = np.arange(1, len(draws) + 1)

    if not np.array_equal(draws["event_order"].to_numpy(), expected_order):
        raise ValueError("event_order must be consecutive, starting at 1.")

    if draws["serialNumber"].duplicated().any():
        raise ValueError("Duplicate serial numbers found.")

    if numbers["number"].isna().any():
        raise ValueError("Missing number values found.")

    if not numbers["number"].str.fullmatch(r"\d{4}").all():
        raise ValueError("All values must be four-digit numbers.")

    if not numbers["event_order"].between(1, len(draws)).all():
        raise ValueError("Number rows reference unknown draw events.")

    return draws, numbers


def build_presence_matrix(draws, numbers):
    """
    One row per draw event and one column per number 0000-9999.
    A number counts once per event, even if multiple prize rows
    contain the same number.
    """
    presence = np.zeros(
        (len(draws), NUMBER_COUNT),
        dtype=np.uint8,
    )

    event_indices = (
        numbers["event_order"].to_numpy(dtype=np.int32) - 1
    )

    number_indices = numbers["number"].map(int).to_numpy(
        dtype=np.int32
    )

    presence[event_indices, number_indices] = 1

    if np.any(presence.sum(axis=1) == 0):
        raise ValueError("At least one event has no valid numbers.")

    return presence


# ============================================================
# Number properties
# ============================================================

def build_static_features():
    values = np.arange(NUMBER_COUNT, dtype=np.int32)

    digits = np.column_stack([
        values // 1000,
        (values // 100) % 10,
        (values // 10) % 10,
        values % 10,
    ])

    digit_sum = digits.sum(axis=1)

    even_digit_count = (digits % 2 == 0).sum(axis=1)

    repeated_digit_count = (
        4 - np.apply_along_axis(
            lambda row: len(set(row.tolist())),
            1,
            digits,
        )
    )

    return digits, digit_sum, even_digit_count, repeated_digit_count


# ============================================================
# Historical state
# ============================================================

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


# ============================================================
# Bucketing helpers
# ============================================================

def bucket_total_hits(values):
    return np.select(
        [
            values == 0,
            values == 1,
            values == 2,
            (values >= 3) & (values <= 5),
            (values >= 6) & (values <= 10),
            values >= 11,
        ],
        [0, 1, 2, 3, 4, 5],
        default=5,
    ).astype(np.int8)


def bucket_recency(last_seen, target_index):
    never_seen = last_seen < 0

    recency = target_index - last_seen

    return np.select(
        [
            never_seen,
            (~never_seen) & (recency <= 5),
            (recency >= 6) & (recency <= 10),
            (recency >= 11) & (recency <= 25),
            (recency >= 26) & (recency <= 50),
            (recency >= 51) & (recency <= 100),
            recency >= 101,
        ],
        [0, 1, 2, 3, 4, 5, 6],
        default=0,
    ).astype(np.int8)


def bucket_recent_activity(values):
    return np.select(
        [
            values == 0,
            values == 1,
            values == 2,
            values >= 3,
        ],
        [0, 1, 2, 3],
        default=0,
    ).astype(np.int8)


def bucket_mean_gap(mean_gap, gap_count):
    return np.select(
        [
            gap_count < 1,
            (gap_count >= 1) & (mean_gap < 10),
            (mean_gap >= 10) & (mean_gap < 25),
            (mean_gap >= 25) & (mean_gap < 50),
            (mean_gap >= 50) & (mean_gap < 100),
            mean_gap >= 100,
        ],
        [0, 1, 2, 3, 4, 5],
        default=0,
    ).astype(np.int8)


def bucket_digit_sum(values):
    return np.select(
        [
            values <= 9,
            (values >= 10) & (values <= 14),
            (values >= 15) & (values <= 19),
            (values >= 20) & (values <= 24),
            (values >= 25) & (values <= 29),
            values >= 30,
        ],
        [0, 1, 2, 3, 4, 5],
        default=0,
    ).astype(np.int8)


# ============================================================
# Accumulate hit rate by feature bucket
# ============================================================

BUCKET_LABELS = {
    "prior_total_hits": [
        "0 prior hits",
        "1 prior hit",
        "2 prior hits",
        "3-5 prior hits",
        "6-10 prior hits",
        "11+ prior hits",
    ],
    "events_since_last_hit": [
        "Never appeared before",
        "1-5 events",
        "6-10 events",
        "11-25 events",
        "26-50 events",
        "51-100 events",
        "101+ events",
    ],
    "hits_last_10_events": [
        "0 hits",
        "1 hit",
        "2 hits",
        "3+ hits",
    ],
    "hits_last_25_events": [
        "0 hits",
        "1 hit",
        "2 hits",
        "3+ hits",
    ],
    "hits_last_50_events": [
        "0 hits",
        "1 hit",
        "2 hits",
        "3+ hits",
    ],
    "mean_historical_gap": [
        "Insufficient prior gaps",
        "Under 10 events",
        "10-24 events",
        "25-49 events",
        "50-99 events",
        "100+ events",
    ],
    "digit_sum": [
        "0-9",
        "10-14",
        "15-19",
        "20-24",
        "25-29",
        "30-36",
    ],
    "even_digit_count": [
        "0 even digits",
        "1 even digit",
        "2 even digits",
        "3 even digits",
        "4 even digits",
    ],
    "repeated_digit_count": [
        "No repeated digits",
        "One duplicate beyond unique digits",
        "Two duplicates beyond unique digits",
        "Three duplicates beyond unique digits",
    ],
}


def accumulate_bucket(stats, feature_name, bucket_ids, actual):
    """
    Count candidate opportunities and observed hits for each bucket.
    Each candidate-number / target-event pair is one opportunity.
    """
    bucket_count = len(BUCKET_LABELS[feature_name])

    opportunities = np.bincount(
        bucket_ids,
        minlength=bucket_count,
    )

    hits = np.bincount(
        bucket_ids,
        weights=actual.astype(np.int32),
        minlength=bucket_count,
    )

    stats[feature_name]["opportunities"] += opportunities
    stats[feature_name]["hits"] += hits.astype(np.int64)


# ============================================================
# Main analysis
# ============================================================

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading exported historical data...")
    draws, numbers = load_data()

    print("Building draw-number presence matrix...")
    presence = build_presence_matrix(draws, numbers)

    event_count = len(draws)

    if event_count <= MIN_HISTORY_EVENTS:
        raise ValueError("Not enough draw events for this analysis.")

    print("Building historical prefix counts...")
    prefix = build_prefix(presence)

    digits, digit_sum, even_digit_count, repeated_digit_count = (
        build_static_features()
    )

    feature_names = list(BUCKET_LABELS)

    stats = {
        name: {
            "opportunities": np.zeros(
                len(BUCKET_LABELS[name]),
                dtype=np.int64,
            ),
            "hits": np.zeros(
                len(BUCKET_LABELS[name]),
                dtype=np.int64,
            ),
        }
        for name in feature_names
    }

    last_seen = np.full(NUMBER_COUNT, -1, dtype=np.int32)
    gap_sum = np.zeros(NUMBER_COUNT, dtype=np.float64)
    gap_count = np.zeros(NUMBER_COUNT, dtype=np.int32)

    # Initialize history with event zero.
    update_gap_state(
        0,
        presence[0],
        last_seen,
        gap_sum,
        gap_count,
    )

    total_hits = 0
    total_opportunities = 0

    # Digit-position occurrence counts.
    digit_position_counts = np.zeros((4, 10), dtype=np.int64)

    # Number-level hit counts, used for a descriptive frequency report.
    number_total_hits = np.zeros(NUMBER_COUNT, dtype=np.int64)

    print("Analyzing each target event without using future information...")

    for target_index in range(1, event_count):
        actual = presence[target_index].astype(bool)

        number_total_hits += actual.astype(np.int64)

        # Record the actual digit distribution in this target event.
        actual_numbers = np.flatnonzero(actual)

        for position in range(4):
            digit_values = digits[actual_numbers, position]
            digit_position_counts[position] += np.bincount(
                digit_values,
                minlength=10,
            )

        # Skip early events until enough prior history exists.
        if target_index >= MIN_HISTORY_EVENTS:
            prior_hits = prefix[target_index]

            recency_buckets = bucket_recency(
                last_seen,
                target_index,
            )

            total_hit_buckets = bucket_total_hits(prior_hits)

            recent_10 = (
                prefix[target_index] -
                prefix[max(0, target_index - 10)]
            )

            recent_25 = (
                prefix[target_index] -
                prefix[max(0, target_index - 25)]
            )

            recent_50 = (
                prefix[target_index] -
                prefix[max(0, target_index - 50)]
            )

            mean_gap = np.divide(
                gap_sum,
                gap_count,
                out=np.zeros(NUMBER_COUNT, dtype=np.float64),
                where=gap_count > 0,
            )

            mean_gap_buckets = bucket_mean_gap(
                mean_gap,
                gap_count,
            )

            feature_buckets = {
                "prior_total_hits": total_hit_buckets,
                "events_since_last_hit": recency_buckets,
                "hits_last_10_events": bucket_recent_activity(recent_10),
                "hits_last_25_events": bucket_recent_activity(recent_25),
                "hits_last_50_events": bucket_recent_activity(recent_50),
                "mean_historical_gap": mean_gap_buckets,
                "digit_sum": bucket_digit_sum(digit_sum),
                "even_digit_count": even_digit_count.astype(np.int8),
                "repeated_digit_count": repeated_digit_count.astype(np.int8),
            }

            for feature_name, bucket_ids in feature_buckets.items():
                accumulate_bucket(
                    stats,
                    feature_name,
                    bucket_ids,
                    actual,
                )

            total_hits += int(actual.sum())
            total_opportunities += NUMBER_COUNT

        # Consume this event only after evaluating it.
        update_gap_state(
            target_index,
            presence[target_index],
            last_seen,
            gap_sum,
            gap_count,
        )

        if target_index % 200 == 0:
            print(
                f"Analyzed event {target_index + 1}/{event_count}"
            )

    # ========================================================
    # Conditional hit-rate reports
    # ========================================================

    baseline_rate = (
        total_hits / total_opportunities
        if total_opportunities
        else 0.0
    )

    bucket_rows = []

    for feature_name, feature_stats in stats.items():
        for bucket_id, label in enumerate(
            BUCKET_LABELS[feature_name]
        ):
            opportunities = int(
                feature_stats["opportunities"][bucket_id]
            )

            hits = int(feature_stats["hits"][bucket_id])

            hit_rate = (
                hits / opportunities
                if opportunities
                else 0.0
            )

            lift = (
                hit_rate / baseline_rate
                if baseline_rate
                else 0.0
            )

            bucket_rows.append({
                "feature": feature_name,
                "bucket": label,
                "opportunities": opportunities,
                "hits": hits,
                "hit_rate": hit_rate,
                "baseline_hit_rate": baseline_rate,
                "lift_vs_baseline": lift,
            })

    bucket_df = pd.DataFrame(bucket_rows)

    bucket_path = (
        RESULTS_DIR / "ai_pattern_conditional_hit_rates.csv"
    )

    bucket_df.to_csv(bucket_path, index=False)

    # ========================================================
    # Digit-position distribution
    # ========================================================

    digit_rows = []

    for position in range(4):
        position_total = int(digit_position_counts[position].sum())

        for digit in range(10):
            count = int(digit_position_counts[position, digit])

            digit_rows.append({
                "position": [
                    "thousands",
                    "hundreds",
                    "tens",
                    "units",
                ][position],
                "digit": digit,
                "observed_occurrences": count,
                "total_occurrences_at_position": position_total,
                "observed_share": (
                    count / position_total
                    if position_total
                    else 0.0
                ),
                "uniform_expected_share": 0.10,
                "observed_to_uniform_ratio": (
                    (count / position_total) / 0.10
                    if position_total
                    else 0.0
                ),
            })

    digit_df = pd.DataFrame(digit_rows)

    digit_path = (
        RESULTS_DIR / "ai_pattern_digit_positions.csv"
    )

    digit_df.to_csv(digit_path, index=False)

    # ========================================================
    # Overall number frequency report
    # ========================================================

    number_rows = []

    for number in range(NUMBER_COUNT):
        number_rows.append({
            "number": f"{number:04d}",
            "historical_hits": int(number_total_hits[number]),
            "total_events": event_count - 1,
            "observed_hit_rate": (
                number_total_hits[number] / max(event_count - 1, 1)
            ),
        })

    number_df = pd.DataFrame(number_rows)

    number_df = number_df.sort_values(
        ["historical_hits", "number"],
        ascending=[False, True],
    )

    number_path = (
        RESULTS_DIR / "ai_pattern_number_frequencies.csv"
    )

    number_df.to_csv(number_path, index=False)

    # ========================================================
    # Metadata
    # ========================================================

    metadata = {
        "draw_events": event_count,
        "minimum_history_events": MIN_HISTORY_EVENTS,
        "target": (
            "A number appears at least once among exported prize "
            "rows in a target draw"
        ),
        "number_universe": NUMBER_COUNT,
        "evaluated_target_events": (
            event_count - MIN_HISTORY_EVENTS
        ),
        "conditional_baseline_hit_rate": baseline_rate,
        "files": [
            bucket_path.name,
            digit_path.name,
            number_path.name,
        ],
        "interpretation_warning": [
            "These are descriptive historical associations.",
            "A higher historical hit rate does not prove future predictability.",
            "Many buckets and digits are examined, so some apparent differences "
            "can occur by chance.",
            "The digit uniformity ratio is descriptive and does not account "
            "for statistical uncertainty.",
            "The analysis uses event order from the exported CSV files.",
        ],
    }

    metadata_path = (
        RESULTS_DIR / "ai_pattern_discovery_metadata.json"
    )

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    # ========================================================
    # Console summary
    # ========================================================

    print("\n" + "=" * 70)
    print("PATTERN DISCOVERY COMPLETE")
    print("=" * 70)

    print(f"Draw events: {event_count}")
    print(f"Evaluated target events: {event_count - MIN_HISTORY_EVENTS}")
    print(f"Baseline hit rate per candidate-event: {baseline_rate:.6%}")

    print("\nConditional hit rates:")
    print(
        bucket_df[
            [
                "feature",
                "bucket",
                "opportunities",
                "hits",
                "hit_rate",
                "lift_vs_baseline",
            ]
        ].to_string(
            index=False,
            formatters={
                "hit_rate": lambda value: f"{value:.6%}",
                "lift_vs_baseline": lambda value: f"{value:.3f}",
            },
        )
    )

    print("\nMost frequent historical numbers (descriptive only):")
    print(number_df.head(20).to_string(index=False))

    print("\nFiles created:")
    print(bucket_path)
    print(digit_path)
    print(number_path)
    print(metadata_path)


if __name__ == "__main__":
    main()
