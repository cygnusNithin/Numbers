
from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"

EVENTS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

LEADER_NUMBER = "7396"
NUMBER_UNIVERSE = 10_000

# Forward-looking horizons, measured in draw events.
HORIZONS = (1, 5, 10, 20)

# Forward-test configuration.
FORWARD_HORIZON = 10
TOP_K = 100
MIN_PRIOR_ANCHORS = 5
RANDOM_SEED = 7396


# ============================================================
# HELPERS
# ============================================================

def normalize_number(value):
    """Return a four-digit number string, or None if invalid."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    # CSV numbers may sometimes be represented as 123.0.
    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit() or len(text) > 4:
        return None

    return text.zfill(4)


def require_columns(frame, required, filename):
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(
            f"{filename} is missing required columns: {missing}"
        )



def safe_rate(numerator, denominator):
    """Safely divide scalar or NumPy values without ambiguous conditions."""
    numerator = np.asarray(numerator, dtype=np.float64)
    denominator = np.asarray(denominator, dtype=np.float64)

    result = np.full(
        np.broadcast_shapes(numerator.shape, denominator.shape),
        np.nan,
        dtype=np.float64,
    )

    np.divide(
        numerator,
        denominator,
        out=result,
        where=denominator > 0,
    )

    if result.ndim == 0:
        return float(result)

    return result



def date_text(value):
    if pd.isna(value):
        return ""
    return str(value)


def number_text(number_id):
    return f"{int(number_id):04d}"


# ============================================================
# LOAD CANONICAL CSV EXPORTS
# ============================================================

def load_data():
    if not EVENTS_FILE.exists():
        raise FileNotFoundError(f"Missing events CSV: {EVENTS_FILE}")

    if not NUMBERS_FILE.exists():
        raise FileNotFoundError(f"Missing numbers CSV: {NUMBERS_FILE}")

    events = pd.read_csv(
        EVENTS_FILE,
        dtype={"serialNumber": str},
        low_memory=False,
    )

    rows = pd.read_csv(
        NUMBERS_FILE,
        dtype={"serialNumber": str, "number": str},
        low_memory=False,
    )

    require_columns(
        events,
        ["event_order", "serialNumber"],
        EVENTS_FILE.name,
    )

    require_columns(
        rows,
        ["event_order", "number"],
        NUMBERS_FILE.name,
    )

    events["event_order"] = pd.to_numeric(
        events["event_order"], errors="coerce"
    )
    rows["event_order"] = pd.to_numeric(
        rows["event_order"], errors="coerce"
    )

    events = events.dropna(subset=["event_order"]).copy()
    rows = rows.dropna(subset=["event_order"]).copy()

    events["event_order"] = events["event_order"].astype(np.int64)
    rows["event_order"] = rows["event_order"].astype(np.int64)

    if events["event_order"].duplicated().any():
        duplicates = events.loc[
            events["event_order"].duplicated(keep=False),
            "event_order",
        ].unique()

        raise ValueError(
            "Event CSV has duplicate event_order values. "
            f"Examples: {duplicates[:10].tolist()}"
        )

    # Keep chronological event order as exported.
    events = events.sort_values("event_order").reset_index(drop=True)

    rows["number_normalized"] = rows["number"].map(normalize_number)

    invalid_numbers = int(rows["number_normalized"].isna().sum())
    rows = rows.dropna(subset=["number_normalized"]).copy()

    # Presence means the number appeared at least once in that draw,
    # regardless of prize tier or repeated rows.
    rows["number_id"] = rows["number_normalized"].astype(np.int16)

    valid_event_orders = set(events["event_order"].tolist())
    unmatched_rows = int(
        (~rows["event_order"].isin(valid_event_orders)).sum()
    )

    rows = rows[rows["event_order"].isin(valid_event_orders)].copy()

    event_orders = events["event_order"].to_numpy(dtype=np.int64)
    order_to_index = {
        int(order): index
        for index, order in enumerate(event_orders)
    }

    rows["event_index"] = rows["event_order"].map(order_to_index)
    rows = rows.dropna(subset=["event_index"]).copy()
    rows["event_index"] = rows["event_index"].astype(np.int32)

    # Remove duplicate appearances of the same number in the same event.
    rows = rows.drop_duplicates(
        subset=["event_index", "number_id"]
    )

    n_events = len(events)

    # Boolean presence matrix: [draw event, number 0000..9999].
    presence = np.zeros(
        (n_events, NUMBER_UNIVERSE),
        dtype=np.bool_,
    )

    event_indices = rows["event_index"].to_numpy(dtype=np.int32)
    number_ids = rows["number_id"].to_numpy(dtype=np.int16)

    presence[event_indices, number_ids] = True

    # Preserve a readable event date for output.
    date_column = (
        "date" if "date" in events.columns
        else "drawDate" if "drawDate" in events.columns
        else None
    )

    if date_column:
        event_dates = events[date_column].map(date_text).to_numpy()
    else:
        event_dates = np.full(n_events, "", dtype=object)

    metadata = {
        "events": int(n_events),
        "valid_distinct_appearances": int(presence.sum()),
        "invalid_number_rows_ignored": invalid_numbers,
        "rows_with_unmatched_event_order": unmatched_rows,
        "unique_dates": (
            int(events[date_column].nunique())
            if date_column
            else None
        ),
        "first_event_order": int(event_orders[0]),
        "last_event_order": int(event_orders[-1]),
        "first_date": str(event_dates[0]),
        "last_date": str(event_dates[-1]),
        "date_column": date_column,
    }

    print(f"Draw events: {n_events:,}")
    print(f"Distinct number appearances: {int(presence.sum()):,}")
    print(f"Invalid number rows ignored: {invalid_numbers:,}")
    print(f"Unmatched event rows ignored: {unmatched_rows:,}")
    print(f"Date range: {event_dates[0]} to {event_dates[-1]}")

    return events, presence, event_orders, event_dates, metadata


# ============================================================
# FIND WHEN 7396 FIRST BECOMES THE STRICT CUMULATIVE LEADER
# ============================================================

def find_first_strict_lead(presence):
    cumulative = np.cumsum(
        presence,
        axis=0,
        dtype=np.int32,
    )

    leader_id = int(LEADER_NUMBER)
    leader_hits = cumulative[:, leader_id]

    # Maximum cumulative hits among all numbers other than 7396.
    other_max = np.max(
        np.concatenate(
            [
                cumulative[:, :leader_id],
                cumulative[:, leader_id + 1:],
            ],
            axis=1,
        ),
        axis=1,
    )

    strict_lead_indices = np.flatnonzero(leader_hits > other_max)

    if len(strict_lead_indices) == 0:
        raise RuntimeError(
            f"{LEADER_NUMBER} never becomes the strict cumulative "
            "leader in this dataset."
        )

    first_lead_index = int(strict_lead_indices[0])

    # Rank is 1 + the number of numbers with strictly more hits.
    rank = 1 + np.sum(
        cumulative > leader_hits[:, None],
        axis=1,
    )

    # Identify one top number at each event for the timeline.
    # If tied, choose the smallest numeric ID for display.
    max_hits = cumulative.max(axis=1)
    top_ids = np.argmax(cumulative, axis=1)

    return (
        cumulative,
        first_lead_index,
        rank.astype(np.int32),
        other_max,
        max_hits,
        top_ids,
    )


def write_leader_timeline(
    events,
    event_orders,
    event_dates,
    cumulative,
    first_lead_index,
    rank,
    other_max,
    max_hits,
    top_ids,
):
    leader_id = int(LEADER_NUMBER)
    records = []

    for i in range(first_lead_index, len(events)):
        records.append(
            {
                "event_index": i,
                "event_order": int(event_orders[i]),
                "date": event_dates[i],
                "leader_number": LEADER_NUMBER,
                "leader_cumulative_hits": int(cumulative[i, leader_id]),
                "leader_rank": int(rank[i]),
                "highest_other_number_hits": int(other_max[i]),
                "strict_lead_margin": int(
                    cumulative[i, leader_id] - other_max[i]
                ),
                "top_number": number_text(top_ids[i]),
                "top_number_hits": int(max_hits[i]),
                "7396_appeared_this_draw": bool(
                    cumulative[i, leader_id]
                    - (cumulative[i - 1, leader_id] if i else 0)
                ),
            }
        )

    output = RESULTS_DIR / "ai_7396_leader_timeline.csv"
    pd.DataFrame(records).to_csv(output, index=False)
    print(f"Saved: {output.name}")


# ============================================================
# EVENT-ALIGNED CO-OCCURRENCE AND FOLLOWING-DRAW ANALYSIS
# ============================================================

def calculate_event_aligned_stats(
    presence,
    cumulative,
    first_lead_index,
):
    leader_id = int(LEADER_NUMBER)

    # Only use the timeline starting when 7396 first becomes leader.
    indices = np.arange(first_lead_index, len(presence))

    anchor_indices = indices[presence[indices, leader_id]]
    control_indices = indices[~presence[indices, leader_id]]

    print(f"\nFirst strict-lead event index: {first_lead_index}")
    print(f"7396-hit anchor events after first lead: {len(anchor_indices)}")
    print(f"Control events where 7396 did not hit: {len(control_indices)}")

    # For each number, accumulate:
    # - appearance on the anchor draw
    # - appearances during the next H draws
    anchor_same = np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
    control_same = np.zeros(NUMBER_UNIVERSE, dtype=np.int64)

    anchor_future = {
        h: np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
        for h in HORIZONS
    }
    control_future = {
        h: np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
        for h in HORIZONS
    }

    anchor_valid_counts = {h: 0 for h in HORIZONS}
    control_valid_counts = {h: 0 for h in HORIZONS}

    # Gap-change statistics for the 7396-hit anchors.
    gap_change_sum = {
        h: np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
        for h in HORIZONS
    }
    gap_close_count = {
        h: np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
        for h in HORIZONS
    }
    positive_gap_count = {
        h: np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
        for h in HORIZONS
    }
    gap_observation_count = {
        h: np.zeros(NUMBER_UNIVERSE, dtype=np.int64)
        for h in HORIZONS
    }

    anchor_gap_sum = np.zeros(NUMBER_UNIVERSE, dtype=np.int64)

    # Same-draw co-occurrence.
    if len(anchor_indices):
        anchor_same = presence[anchor_indices].sum(axis=0, dtype=np.int64)

    if len(control_indices):
        control_same = presence[control_indices].sum(axis=0, dtype=np.int64)

    # Anchor-by-anchor calculations keep memory bounded.
    for anchor in anchor_indices:
        # Gap after the anchor draw, including that draw's hits.
        gap_at_anchor = (
            cumulative[anchor, leader_id] - cumulative[anchor]
        ).astype(np.int64)

        anchor_gap_sum += gap_at_anchor

        for h in HORIZONS:
            end = int(anchor) + h

            if end >= len(presence):
                continue

            future = presence[anchor + 1:end + 1].sum(
                axis=0,
                dtype=np.int64,
            )

            leader_future_hits = int(future[leader_id])
            candidate_hits = future

            gap_change = leader_future_hits - candidate_hits

            gap_change_sum[h] += gap_change
            gap_observation_count[h] += 1

            positive = gap_at_anchor > 0
            positive_gap_count[h] += positive.astype(np.int64)

            # A positive gap closes if the candidate gains more hits
            # than 7396 over the future horizon.
            gap_close_count[h] += (
                positive & (candidate_hits > leader_future_hits)
            ).astype(np.int64)

            anchor_future[h] += future
            anchor_valid_counts[h] += 1

    # Control anchors: events where 7396 did not appear.
    for anchor in control_indices:
        for h in HORIZONS:
            end = int(anchor) + h

            if end >= len(presence):
                continue

            future = presence[anchor + 1:end + 1].sum(
                axis=0,
                dtype=np.int64,
            )

            control_future[h] += future
            control_valid_counts[h] += 1

    anchor_count = len(anchor_indices)
    control_count = len(control_indices)

    records = []

    for number_id in range(NUMBER_UNIVERSE):
        if number_id == leader_id:
            continue

        record = {
            "number": number_text(number_id),
            "anchor_count": anchor_count,
            "control_count": control_count,
            "same_draw_hits_with_7396": int(anchor_same[number_id]),
            "same_draw_rate_with_7396": safe_rate(
                anchor_same[number_id], anchor_count
            ),
            "same_draw_hits_without_7396": int(control_same[number_id]),
            "same_draw_rate_without_7396": safe_rate(
                control_same[number_id], control_count
            ),
            "same_draw_rate_difference": (
                safe_rate(anchor_same[number_id], anchor_count)
                - safe_rate(control_same[number_id], control_count)
            ),
            "mean_gap_at_7396_anchor": safe_rate(
                anchor_gap_sum[number_id], anchor_count
            ),
        }

        for h in HORIZONS:
            a_count = anchor_valid_counts[h]
            c_count = control_valid_counts[h]

            a_hits = int(anchor_future[h][number_id])
            c_hits = int(control_future[h][number_id])

            a_opportunities = a_count * h
            c_opportunities = c_count * h

            anchor_rate = safe_rate(a_hits, a_opportunities)
            control_rate = safe_rate(c_hits, c_opportunities)

            record[f"future_{h}_draw_hits_after_7396"] = a_hits
            record[f"future_{h}_draw_rate_after_7396"] = anchor_rate
            record[f"future_{h}_draw_hits_after_control"] = c_hits
            record[f"future_{h}_draw_rate_after_control"] = control_rate

            record[f"future_{h}_draw_rate_difference"] = (
                anchor_rate - control_rate
                if np.isfinite(anchor_rate) and np.isfinite(control_rate)
                else np.nan
            )

            record[f"mean_gap_change_next_{h}_draws"] = safe_rate(
                gap_change_sum[h][number_id],
                gap_observation_count[h],
            )

            record[f"positive_gap_observations_{h}"] = int(
                positive_gap_count[h][number_id]
            )

            record[f"gap_closes_count_next_{h}"] = int(
                gap_close_count[h][number_id]
            )

            record[f"gap_close_rate_next_{h}"] = safe_rate(
                gap_close_count[h][number_id],
                positive_gap_count[h][number_id],
            )

        records.append(record)

    summary = pd.DataFrame(records)

    # Rank candidates by future 10-draw conditional hit-rate difference.
    summary = summary.sort_values(
        [
            "future_10_draw_rate_difference",
            "same_draw_rate_difference",
        ],
        ascending=False,
        na_position="last",
    )

    output = RESULTS_DIR / "ai_7396_event_aligned_summary.csv"
    summary.to_csv(output, index=False)
    print(f"Saved: {output.name}")

    return summary, anchor_indices, control_indices


# ============================================================
# GAP SNAPSHOTS FOR EVERY NUMBER AT EVERY 7396-HIT ANCHOR
# ============================================================

def write_gap_snapshots(
    events,
    presence,
    cumulative,
    event_orders,
    event_dates,
    first_lead_index,
    anchor_indices,
):
    leader_id = int(LEADER_NUMBER)
    records = []

    for anchor in anchor_indices:
        if anchor < first_lead_index:
            continue

        leader_hits = int(cumulative[anchor, leader_id])
        candidate_hits = cumulative[anchor].astype(np.int64)
        gaps = leader_hits - candidate_hits

        ranks = 1 + np.sum(
            cumulative[anchor] > candidate_hits[:, None],
            axis=0,
        ) if False else None

        # Rank all candidates using this event's cumulative counts.
        # Stable tie handling: equal hit counts share the same competition rank.
        counts = cumulative[anchor]
        sorted_counts = np.sort(counts)[::-1]
        unique_count_to_rank = {}
        for position, count in enumerate(sorted_counts, start=1):
            if int(count) not in unique_count_to_rank:
                unique_count_to_rank[int(count)] = position

        candidate_ranks = np.array(
            [unique_count_to_rank[int(x)] for x in counts],
            dtype=np.int32,
        )

        current_hits = presence[anchor]

        for number_id in range(NUMBER_UNIVERSE):
            if number_id == leader_id:
                continue

            records.append(
                {
                    "event_index": int(anchor),
                    "event_order": int(event_orders[anchor]),
                    "date": event_dates[anchor],
                    "leader_number": LEADER_NUMBER,
                    "candidate_number": number_text(number_id),
                    "candidate_appeared_on_anchor": bool(
                        current_hits[number_id]
                    ),
                    "leader_cumulative_hits": leader_hits,
                    "candidate_cumulative_hits": int(
                        cumulative[anchor, number_id]
                    ),
                    "gap_7396_minus_candidate": int(gaps[number_id]),
                    "candidate_cumulative_rank": int(
                        candidate_ranks[number_id]
                    ),
                }
            )

    output = RESULTS_DIR / "ai_7396_gap_snapshots.csv"
    pd.DataFrame(records).to_csv(output, index=False)
    print(f"Saved: {output.name}")


# ============================================================
# WALK-FORWARD TEST OF EVENT-ALIGNED CHASERS
# ============================================================

def run_forward_test(
    presence,
    cumulative,
    events,
    event_orders,
    event_dates,
    first_lead_index,
    anchor_indices,
):
    """
    At each eligible 7396-hit anchor:
      1. Use only earlier data.
      2. Learn which candidates appeared in the 10 draws after
         previous 7396-hit anchors.
      3. Require prior anchor windows to have ended before this cutoff.
      4. Rank candidates by smoothed conditional future hit rate
         relative to their own historical hit rate.
      5. Evaluate the selected Top K on the next 10 draw events.

    This tests a specific chaser hypothesis, not lottery predictability
    in general.
    """

    leader_id = int(LEADER_NUMBER)
    rng = np.random.default_rng(RANDOM_SEED)

    prediction_rows = []
    period_rows = []

    anchors = np.asarray(anchor_indices, dtype=np.int32)

    for anchor in anchors:
        # Need a complete unseen future horizon.
        if anchor + FORWARD_HORIZON >= len(presence):
            continue

        # Previous anchor windows must finish strictly before this cutoff.
        prior_anchors = anchors[
            anchors + FORWARD_HORIZON < anchor
        ]

        if len(prior_anchors) < MIN_PRIOR_ANCHORS:
            continue

        # All training history ends before this anchor.
        historical = presence[first_lead_index:anchor]

        if len(historical) == 0:
            continue

        historical_hits = historical.sum(axis=0, dtype=np.int64)
        historical_rate = historical_hits / float(len(historical))

        # Count appearances in the 10 events after each prior anchor.
        prior_future_counts = np.zeros(
            NUMBER_UNIVERSE,
            dtype=np.int64,
        )

        for prior_anchor in prior_anchors:
            prior_future_counts += presence[
                prior_anchor + 1:
                prior_anchor + 1 + FORWARD_HORIZON
            ].sum(axis=0, dtype=np.int64)

        prior_opportunities = (
            len(prior_anchors) * FORWARD_HORIZON
        )

        prior_future_rate = (
            prior_future_counts / float(prior_opportunities)
        )

        # Empirical-Bayes-style smoothing toward each candidate's
        # historical rate, preventing a few hits from dominating.
        smoothing_opportunities = 20.0
        smoothed_rate = (
            prior_future_counts
            + historical_rate * smoothing_opportunities
        ) / (
            prior_opportunities + smoothing_opportunities
        )

        lift = np.divide(
            smoothed_rate,
            historical_rate,
            out=np.zeros_like(smoothed_rate, dtype=np.float64),
            where=historical_rate > 0,
        )

        eligible = np.ones(NUMBER_UNIVERSE, dtype=bool)
        eligible[leader_id] = False

        # Candidates with no historical hits cannot have a stable lift.
        eligible &= historical_rate > 0

        candidate_ids = np.flatnonzero(eligible)

        if len(candidate_ids) < TOP_K:
            continue

        # Primary score: historical conditional lift after prior
        # 7396-hit anchors. Tie-break with smoothed future hit rate.
        ordering = np.lexsort(
            (
                smoothed_rate[candidate_ids],
                lift[candidate_ids],
            )
        )[::-1]

        selected = candidate_ids[ordering[:TOP_K]]

        # Historical-frequency baseline: Top K by prior cumulative hits.
        frequency_order = np.lexsort(
            (
                np.arange(NUMBER_UNIVERSE),
                historical_hits,
            )
        )[::-1]

        frequency_order = [
            int(x) for x in frequency_order
            if int(x) != leader_id
        ][:TOP_K]

        # Random baseline, chosen deterministically for reproducibility.
        random_candidates = np.array(
            [x for x in range(NUMBER_UNIVERSE) if x != leader_id],
            dtype=np.int32,
        )
        random_selected = rng.choice(
            random_candidates,
            size=TOP_K,
            replace=False,
        )

        # Evaluate only events after the current anchor.
        future_presence = presence[
            anchor + 1:
            anchor + 1 + FORWARD_HORIZON
        ]

        actual_hits_by_number = future_presence.sum(
            axis=0,
            dtype=np.int64,
        )

        model_hits = int(actual_hits_by_number[selected].sum())
        frequency_hits = int(
            actual_hits_by_number[frequency_order].sum()
        )
        random_hits = int(
            actual_hits_by_number[random_selected].sum()
        )

        period_rows.append(
            {
                "cutoff_event_index": int(anchor),
                "cutoff_event_order": int(event_orders[anchor]),
                "cutoff_date": event_dates[anchor],
                "prior_7396_anchor_count": int(len(prior_anchors)),
                "future_horizon_draws": FORWARD_HORIZON,
                "top_k": TOP_K,
                "chaser_strategy_hits": model_hits,
                "historical_frequency_hits": frequency_hits,
                "random_hits": random_hits,
                "chaser_minus_frequency": model_hits - frequency_hits,
                "chaser_minus_random": model_hits - random_hits,
            }
        )

        for rank_position, number_id in enumerate(selected, start=1):
            prediction_rows.append(
                {
                    "cutoff_event_index": int(anchor),
                    "cutoff_event_order": int(event_orders[anchor]),
                    "cutoff_date": event_dates[anchor],
                    "number": number_text(number_id),
                    "rank": rank_position,
                    "historical_hits_before_cutoff": int(
                        historical_hits[number_id]
                    ),
                    "historical_hit_rate": float(
                        historical_rate[number_id]
                    ),
                    "prior_anchor_future_hits": int(
                        prior_future_counts[number_id]
                    ),
                    "prior_anchor_future_rate": float(
                        prior_future_rate[number_id]
                    ),
                    "smoothed_future_rate": float(
                        smoothed_rate[number_id]
                    ),
                    "conditional_lift_score": float(
                        lift[number_id]
                    ),
                    "actual_hits_next_10_draws": int(
                        actual_hits_by_number[number_id]
                    ),
                }
            )

    predictions = pd.DataFrame(prediction_rows)
    periods = pd.DataFrame(period_rows)

    predictions_path = (
        RESULTS_DIR / "ai_7396_chaser_forward_predictions.csv"
    )
    periods_path = (
        RESULTS_DIR / "ai_7396_chaser_forward_test.csv"
    )

    predictions.to_csv(predictions_path, index=False)
    periods.to_csv(periods_path, index=False)

    print(f"Saved: {predictions_path.name}")
    print(f"Saved: {periods_path.name}")

    if periods.empty:
        print(
            "\nForward test has no eligible periods yet. "
            "More historical 7396-hit anchors may be needed."
        )
        return

    summary = []

    for strategy, column in [
        ("event_aligned_chasers", "chaser_strategy_hits"),
        ("historical_frequency", "historical_frequency_hits"),
        ("random", "random_hits"),
    ]:
        values = periods[column].to_numpy(dtype=float)

        summary.append(
            {
                "strategy": strategy,
                "test_periods": int(len(values)),
                "future_draws_per_period": FORWARD_HORIZON,
                "top_k": TOP_K,
                "mean_hits_per_period": float(values.mean()),
                "median_hits_per_period": float(np.median(values)),
                "total_hits": int(values.sum()),
            }
        )

    summary_df = pd.DataFrame(summary)
    summary_path = (
        RESULTS_DIR / "ai_7396_chaser_forward_summary.csv"
    )
    summary_df.to_csv(summary_path, index=False)

    print(f"Saved: {summary_path.name}")
    print("\nForward-test summary:")
    print(summary_df.to_string(index=False))

    print("\nMean per-period differences:")
    print(
        "Chasers minus historical frequency:",
        round(
            float(
                (
                    periods["chaser_strategy_hits"]
                    - periods["historical_frequency_hits"]
                ).mean()
            ),
            4,
        ),
    )
    print(
        "Chasers minus random:",
        round(
            float(
                (
                    periods["chaser_strategy_hits"]
                    - periods["random_hits"]
                ).mean()
            ),
            4,
        ),
    )


# ============================================================
# MAIN
# ============================================================

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    (
        events,
        presence,
        event_orders,
        event_dates,
        metadata,
    ) = load_data()

    (
        cumulative,
        first_lead_index,
        rank,
        other_max,
        max_hits,
        top_ids,
    ) = find_first_strict_lead(presence)

    metadata.update(
        {
            "leader_number": LEADER_NUMBER,
            "first_strict_lead_event_index": first_lead_index,
            "first_strict_lead_event_order": int(
                event_orders[first_lead_index]
            ),
            "first_strict_lead_date": event_dates[first_lead_index],
            "leader_hits_at_first_strict_lead": int(
                cumulative[first_lead_index, int(LEADER_NUMBER)]
            ),
            "highest_other_hits_at_first_strict_lead": int(
                other_max[first_lead_index]
            ),
            "horizons": list(HORIZONS),
            "forward_test_horizon": FORWARD_HORIZON,
            "forward_test_top_k": TOP_K,
        }
    )

    print("\nFirst strict cumulative lead:")
    print(f"Number: {LEADER_NUMBER}")
    print(f"Event index: {first_lead_index}")
    print(f"Event order: {event_orders[first_lead_index]}")
    print(f"Date: {event_dates[first_lead_index]}")
    print(
        "7396 cumulative hits:",
        int(cumulative[first_lead_index, int(LEADER_NUMBER)]),
    )
    print(
        "Highest other cumulative hits:",
        int(other_max[first_lead_index]),
    )

    write_leader_timeline(
        events,
        event_orders,
        event_dates,
        cumulative,
        first_lead_index,
        rank,
        other_max,
        max_hits,
        top_ids,
    )

    summary, anchor_indices, control_indices = (
        calculate_event_aligned_stats(
            presence,
            cumulative,
            first_lead_index,
        )
    )

    write_gap_snapshots(
        events,
        presence,
        cumulative,
        event_orders,
        event_dates,
        first_lead_index,
        anchor_indices,
    )

    run_forward_test(
        presence,
        cumulative,
        events,
        event_orders,
        event_dates,
        first_lead_index,
        anchor_indices,
    )

    metadata.update(
        {
            "7396_hit_anchors_after_first_lead": int(
                len(anchor_indices)
            ),
            "non_7396_control_anchors_after_first_lead": int(
                len(control_indices)
            ),
            "numbers_in_summary": int(len(summary)),
        }
    )

    metadata_path = (
        RESULTS_DIR / "ai_7396_event_aligned_metadata.json"
    )

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, ensure_ascii=False)

    print(f"\nSaved: {metadata_path.name}")

    print("\nTop 20 candidates by future 10-draw rate difference:")
    columns = [
        "number",
        "same_draw_rate_with_7396",
        "same_draw_rate_without_7396",
        "future_10_draw_rate_after_7396",
        "future_10_draw_rate_after_control",
        "future_10_draw_rate_difference",
        "mean_gap_change_next_10_draws",
        "gap_close_rate_next_10",
    ]

    print(
        summary[columns]
        .head(20)
        .to_string(index=False)
    )

    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
