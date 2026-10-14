"""
NumberGrid: Rank Movement, Leadership, Followers and Forward Backtesting

Starts tracking from Day 2:
- Day 1 is the initial baseline.
- Tracks all numbers from 0000 through 9999.
- Records cumulative-frequency ranks and rank movement.
- Tracks Top 1 leadership changes, Top 10 entries and Top 100 entries.
- Investigates which numbers appear after leadership/movement events.
- Evaluates candidate rankings against frequency and random baselines.

Expected input files:
    data/ai-training/ai_training_draws.csv
    data/ai-training/ai_training_draw_numbers.csv

Run from the server directory:
    python scripts/ai_rank_movement_followers.py

Optional:
    python scripts/ai_rank_movement_followers.py --top-k 100
    python scripts/ai_rank_movement_followers.py --min-train-draws 100
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"

DEFAULT_DRAWS = DATA_DIR / "ai_training_draws.csv"
DEFAULT_NUMBERS = DATA_DIR / "ai_training_draw_numbers.csv"
DEFAULT_OUTPUT = DATA_DIR / "results" / "rank-movement"

HORIZONS = (1, 5, 10, 20)
RECENT_WINDOWS = (10, 25, 50)
NUMBER_COUNT = 10_000


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--draws", type=Path, default=DEFAULT_DRAWS)
    parser.add_argument("--draw-numbers", type=Path, default=DEFAULT_NUMBERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)

    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--min-train-draws", type=int, default=100)
    parser.add_argument("--backtest-step", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)

    return parser.parse_args()


def normalise_number(value):
    """Convert a valid number into a four-character string."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit():
        return None

    if len(text) > 4:
        return None

    return text.zfill(4)


def load_data(draws_path, numbers_path):
    if not draws_path.exists():
        raise FileNotFoundError(f"Missing draw file: {draws_path}")

    if not numbers_path.exists():
        raise FileNotFoundError(f"Missing number file: {numbers_path}")

    draws = pd.read_csv(draws_path, dtype=str)
    numbers = pd.read_csv(numbers_path, dtype=str)

    required_draw_columns = {"event_order", "date"}
    required_number_columns = {"event_order", "number"}

    if not required_draw_columns.issubset(draws.columns):
        raise ValueError(
            f"{draws_path.name} requires columns "
            f"{sorted(required_draw_columns)}. Found: {list(draws.columns)}"
        )

    if not required_number_columns.issubset(numbers.columns):
        raise ValueError(
            f"{numbers_path.name} requires columns "
            f"{sorted(required_number_columns)}. Found: {list(numbers.columns)}"
        )

    draws["event_order"] = pd.to_numeric(
        draws["event_order"], errors="coerce"
    )
    numbers["event_order"] = pd.to_numeric(
        numbers["event_order"], errors="coerce"
    )

    draws = draws.dropna(subset=["event_order"]).copy()
    numbers = numbers.dropna(subset=["event_order"]).copy()

    draws["event_order"] = draws["event_order"].astype(int)
    numbers["event_order"] = numbers["event_order"].astype(int)

    # The project has used day-first date strings such as 26/09/2026.
    draws["date"] = pd.to_datetime(
        draws["date"], dayfirst=True, errors="coerce"
    )
    draws = draws.dropna(subset=["date"]).copy()

    numbers["number"] = numbers["number"].map(normalise_number)
    numbers = numbers.dropna(subset=["number"]).copy()

    numbers = numbers[
        numbers["event_order"].isin(draws["event_order"])
    ].copy()

    # One event contains a set of distinct numbers.
    numbers_by_event = (
        numbers.groupby("event_order")["number"]
        .apply(lambda values: sorted(set(values)))
        .to_dict()
    )

    draws = draws[
        draws["event_order"].isin(numbers_by_event)
    ].copy()

    draws = (
        draws.sort_values(["date", "event_order"])
        .drop_duplicates("event_order")
        .reset_index(drop=True)
    )

    events = [
        numbers_by_event[int(event_order)]
        for event_order in draws["event_order"]
    ]

    if len(events) < 3:
        raise ValueError(
            f"At least 3 valid draw events are required; found {len(events)}."
        )

    if any(not event for event in events):
        raise ValueError("An event has no valid numbers.")

    return draws, events


def number_id(number):
    return int(number)


def number_text(value):
    return f"{int(value):04d}"


def make_ranks(counts):
    """
    Rank all 10,000 numbers:
    - Most cumulative hits gets rank 1.
    - Ties are broken by ascending number.
    - Ranks are ordinal, so each number has a unique rank.
    """
    ids = np.arange(NUMBER_COUNT)

    order = np.lexsort((ids, -counts))

    ranks = np.empty(NUMBER_COUNT, dtype=np.int32)
    ranks[order] = np.arange(1, NUMBER_COUNT + 1)

    return ranks


def ranked_ids(ranks, limit):
    return np.argsort(ranks, kind="stable")[:limit]


def percentile_score(values):
    """Return scores from 0 to 1, with larger values scoring higher."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="stable")

    result = np.empty(len(values), dtype=float)
    result[order] = np.linspace(0.0, 1.0, len(values))

    return result


def make_recent_counts(history, window):
    counts = np.zeros(NUMBER_COUNT, dtype=np.int32)

    for event in history[-window:]:
        counts[event] += 1

    return counts


def make_candidate_score(
    cumulative_counts,
    recent10,
    recent25,
    recent50,
    rank_momentum10,
    rank_momentum25,
):
    """
    Exploratory ranking score.

    These weights are hypotheses, not trained or proven optimal weights.
    """
    return (
        0.30 * percentile_score(cumulative_counts)
        + 0.30 * percentile_score(recent10)
        + 0.15 * percentile_score(recent25)
        + 0.10 * percentile_score(recent50)
        + 0.10 * percentile_score(rank_momentum10)
        + 0.05 * percentile_score(rank_momentum25)
    )


def main():
    args = parse_args()

    if not 1 <= args.top_k <= NUMBER_COUNT:
        raise ValueError("--top-k must be between 1 and 10000.")

    if args.min_train_draws < 2:
        raise ValueError("--min-train-draws must be at least 2.")

    if args.backtest_step < 1:
        raise ValueError("--backtest-step must be at least 1.")

    rng = np.random.default_rng(args.seed)

    draws, raw_events = load_data(
        args.draws,
        args.draw_numbers,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    event_orders = draws["event_order"].astype(int).tolist()
    event_dates = draws["date"].dt.strftime("%Y-%m-%d").tolist()

    events = [
        np.array([number_id(n) for n in event], dtype=np.int32)
        for event in raw_events
    ]

    event_count = len(events)
    top_limit = max(100, args.top_k)

    # Snapshots are captured after each historical draw.
    # A backtest checkpoint uses only its own historical snapshot.
    counts = np.zeros(NUMBER_COUNT, dtype=np.int32)

    count_snapshots = []
    rank_snapshots = []
    recent_snapshots = {w: [] for w in RECENT_WINDOWS}

    rank_history_rows = []
    movement_rows = []
    leadership_rows = []

    previous_rank = None
    previous_top1 = None
    previous_top10 = set()
    previous_top100 = set()

    # ------------------------------------------------------------
    # 1. Build historical snapshots, starting with Day 1 baseline.
    # ------------------------------------------------------------
    for i, event in enumerate(events):
        counts[event] += 1

        current_rank = make_ranks(counts)

        count_snapshots.append(counts.copy())
        rank_snapshots.append(current_rank.copy())

        for window in RECENT_WINDOWS:
            recent_snapshots[window].append(
                make_recent_counts(events[: i + 1], window)
            )

        top_ids = ranked_ids(current_rank, top_limit)
        current_top1 = int(top_ids[0])
        current_top10 = set(ranked_ids(current_rank, 10).tolist())
        current_top100 = set(ranked_ids(current_rank, 100).tolist())

        # Day 1 is only a baseline. Start event reporting on Day 2.
        if i == 0:
            previous_rank = current_rank
            previous_top1 = current_top1
            previous_top10 = current_top10
            previous_top100 = current_top100
            continue

        day_index = i + 1
        date = event_dates[i]
        order = event_orders[i]
        appeared_today = set(event.tolist())

        # Store current leaders.
        for position, value in enumerate(top_ids, start=1):
            rank_history_rows.append({
                "day_index": day_index,
                "event_order": order,
                "date": date,
                "number": number_text(value),
                "rank": int(current_rank[value]),
                "cumulative_hits": int(counts[value]),
                "recent_hits_10": int(recent_snapshots[10][i][value]),
                "recent_hits_25": int(recent_snapshots[25][i][value]),
                "recent_hits_50": int(recent_snapshots[50][i][value]),
                "rank_change": int(
                    previous_rank[value] - current_rank[value]
                ),
                "appeared_today": value in appeared_today,
            })

        # Rank movement for all numbers. A positive value means rank improved.
        rank_delta = previous_rank.astype(np.int32) - current_rank.astype(
            np.int32
        )

        changed_ids = np.flatnonzero(rank_delta != 0)

        for value in changed_ids:
            movement_rows.append({
                "day_index": day_index,
                "event_order": order,
                "date": date,
                "number": number_text(value),
                "previous_rank": int(previous_rank[value]),
                "current_rank": int(current_rank[value]),
                "rank_change": int(rank_delta[value]),
                "movement": "UP" if rank_delta[value] > 0 else "DOWN",
                "appeared_today": value in appeared_today,
                "cumulative_hits": int(counts[value]),
            })

        # Record Top 1 changes.
        if current_top1 != previous_top1:
            leadership_rows.append({
                "day_index": day_index,
                "event_order": order,
                "date": date,
                "previous_top1": number_text(previous_top1),
                "new_top1": number_text(current_top1),
                "new_top1_hits": int(counts[current_top1]),
                "new_top1_previous_rank": int(
                    previous_rank[current_top1]
                ),
                "new_top1_appeared_today": (
                    current_top1 in appeared_today
                ),
            })

        previous_rank = current_rank
        previous_top1 = current_top1
        previous_top10 = current_top10
        previous_top100 = current_top100

    # ------------------------------------------------------------
    # 2. Examine followers after historical trigger events.
    #
    # For each trigger, count actual future appearances over 1/5/10/20
    # subsequent draws. Store only followers that actually appear.
    # This keeps the output sparse instead of generating billions of rows.
    # ------------------------------------------------------------
    follower_stats = defaultdict(lambda: {
        "trigger_events": 0,
        "follower_appeared": 0,
        "follower_hits": 0,
        "complete_horizons": 0,
    })

    trigger_event_counts = defaultdict(int)

    for i in range(1, event_count):
        old_rank = rank_snapshots[i - 1]
        new_rank = rank_snapshots[i]
        old_top1 = int(ranked_ids(old_rank, 1)[0])
        new_top1 = int(ranked_ids(new_rank, 1)[0])

        triggers = []

        if old_top1 != new_top1:
            triggers.append(("top1_leader_change", new_top1))

        old_top10 = set(ranked_ids(old_rank, 10).tolist())
        new_top10 = set(ranked_ids(new_rank, 10).tolist())

        for value in sorted(new_top10 - old_top10):
            triggers.append(("top10_entry", int(value)))

        old_top100 = set(ranked_ids(old_rank, 100).tolist())
        new_top100 = set(ranked_ids(new_rank, 100).tolist())

        for value in sorted(new_top100 - old_top100):
            triggers.append(("top100_entry", int(value)))

        delta = old_rank.astype(np.int32) - new_rank.astype(np.int32)

        for value in np.flatnonzero(delta >= 100):
            triggers.append(("rank_jump_100_plus", int(value)))

        # The trigger is known after draw i. Outcomes begin at draw i + 1.
        for trigger_type, trigger_id in triggers:
            trigger = number_text(trigger_id)
            trigger_event_counts[trigger_type] += 1

            for horizon in HORIZONS:
                future_events = events[i + 1 : i + 1 + horizon]

                if not future_events:
                    continue

                future_counts = np.zeros(NUMBER_COUNT, dtype=np.int32)

                for future_event in future_events:
                    future_counts[future_event] += 1

                appearing_ids = np.flatnonzero(future_counts > 0)

                for follower_id in appearing_ids:
                    if follower_id == trigger_id:
                        continue

                    key = (
                        trigger_type,
                        trigger,
                        number_text(follower_id),
                        horizon,
                    )

                    stat = follower_stats[key]
                    stat["trigger_events"] += 1
                    stat["follower_appeared"] += 1
                    stat["follower_hits"] += int(
                        future_counts[follower_id]
                    )

                    if len(future_events) == horizon:
                        stat["complete_horizons"] += 1

    follower_rows = []

    for key, stat in follower_stats.items():
        trigger_type, trigger, follower, horizon = key

        trials = stat["trigger_events"]

        follower_rows.append({
            "trigger_type": trigger_type,
            "trigger_number": trigger,
            "follower_number": follower,
            "horizon_draws": horizon,
            "observed_trigger_windows": trials,
            "follower_appearance_rate": (
                stat["follower_appeared"] / trials if trials else 0.0
            ),
            "mean_follower_hits_per_observed_window": (
                stat["follower_hits"] / trials if trials else 0.0
            ),
            "complete_horizon_windows": stat["complete_horizons"],
        })

    follower_rows.sort(
        key=lambda row: (
            row["trigger_type"],
            row["horizon_draws"],
            -row["follower_appearance_rate"],
            -row["mean_follower_hits_per_observed_window"],
            row["trigger_number"],
            row["follower_number"],
        )
    )

    # ------------------------------------------------------------
    # 3. Current ranking from the full historical dataset.
    # ------------------------------------------------------------
    latest_counts = count_snapshots[-1].astype(float)
    latest_rank = rank_snapshots[-1].astype(float)

    latest_r10 = recent_snapshots[10][-1].astype(float)
    latest_r25 = recent_snapshots[25][-1].astype(float)
    latest_r50 = recent_snapshots[50][-1].astype(float)

    rank_10_ago = rank_snapshots[max(0, event_count - 11)].astype(float)
    rank_25_ago = rank_snapshots[max(0, event_count - 26)].astype(float)

    momentum10 = rank_10_ago - latest_rank
    momentum25 = rank_25_ago - latest_rank

    latest_score = make_candidate_score(
        latest_counts,
        latest_r10,
        latest_r25,
        latest_r50,
        momentum10,
        momentum25,
    )

    current_rows = []

    for value in np.argsort(-latest_score)[:top_limit]:
        current_rows.append({
            "number": number_text(value),
            "score": round(float(latest_score[value]), 8),
            "cumulative_rank": int(latest_rank[value]),
            "cumulative_hits": int(latest_counts[value]),
            "recent_hits_10": int(latest_r10[value]),
            "recent_hits_25": int(latest_r25[value]),
            "recent_hits_50": int(latest_r50[value]),
            "rank_change_last_10_draws": int(momentum10[value]),
            "rank_change_last_25_draws": int(momentum25[value]),
        })

    # ------------------------------------------------------------
    # 4. Walk-forward backtest.
    #
    # At each checkpoint, candidates use only data available by that
    # checkpoint. Future outcomes are measured separately.
    # ------------------------------------------------------------
    backtest_rows = []

    checkpoints = range(
        args.min_train_draws,
        event_count - max(HORIZONS),
        args.backtest_step,
    )

    for checkpoint in checkpoints:
        idx = checkpoint - 1

        train_counts = count_snapshots[idx].astype(float)
        train_rank = rank_snapshots[idx].astype(float)

        train_r10 = recent_snapshots[10][idx].astype(float)
        train_r25 = recent_snapshots[25][idx].astype(float)
        train_r50 = recent_snapshots[50][idx].astype(float)

        old_rank10 = rank_snapshots[max(0, idx - 10)].astype(float)
        old_rank25 = rank_snapshots[max(0, idx - 25)].astype(float)

        momentum10 = old_rank10 - train_rank
        momentum25 = old_rank25 - train_rank

        score = make_candidate_score(
            train_counts,
            train_r10,
            train_r25,
            train_r50,
            momentum10,
            momentum25,
        )

        strategies = {
            "rank_movement_combo": np.argsort(-score)[:args.top_k],
            "cumulative_frequency": np.argsort(-train_counts)[:args.top_k],
            "recent_frequency_10": np.argsort(-train_r10)[:args.top_k],
            "recent_frequency_25": np.argsort(-train_r25)[:args.top_k],
            "random_baseline": rng.choice(
                NUMBER_COUNT, size=args.top_k, replace=False
            ),
        }

        for horizon in HORIZONS:
            future_events = events[checkpoint : checkpoint + horizon]

            if not future_events:
                continue

            future_counts = np.zeros(NUMBER_COUNT, dtype=np.int32)

            for future_event in future_events:
                future_counts[future_event] += 1

            future_present = future_counts > 0

            for strategy, chosen in strategies.items():
                unique_appearing = int(future_present[chosen].sum())
                total_hits = int(future_counts[chosen].sum())

                backtest_rows.append({
                    "checkpoint_event_order": event_orders[idx],
                    "checkpoint_date": event_dates[idx],
                    "training_draws": checkpoint,
                    "horizon_requested": horizon,
                    "horizon_actual": len(future_events),
                    "strategy": strategy,
                    "top_k": args.top_k,
                    "unique_candidates_appearing": unique_appearing,
                    "total_hits_by_candidates": total_hits,
                    "candidate_appearance_rate": (
                        unique_appearing / args.top_k
                    ),
                    "hits_per_candidate": total_hits / args.top_k,
                })

    # ------------------------------------------------------------
    # 5. Save outputs.
    # ------------------------------------------------------------
    def save(rows, filename):
        pd.DataFrame(rows).to_csv(
            args.output_dir / filename,
            index=False,
            encoding="utf-8-sig",
        )

    save(rank_history_rows, "rank_history_top100.csv")
    save(movement_rows, "rank_movement_events.csv")
    save(leadership_rows, "top1_leadership_timeline.csv")
    save(follower_rows, "follower_relationships.csv")
    save(current_rows, "current_number_ranking.csv")
    save(backtest_rows, "forward_backtest.csv")

    backtest_df = pd.DataFrame(backtest_rows)

    if not backtest_df.empty:
        summary = (
            backtest_df.groupby(
                ["horizon_requested", "strategy"],
                as_index=False,
            )
            .agg(
                checkpoints=("checkpoint_date", "nunique"),
                mean_unique_candidates_appearing=(
                    "unique_candidates_appearing", "mean"
                ),
                mean_total_hits=("total_hits_by_candidates", "mean"),
                mean_candidate_appearance_rate=(
                    "candidate_appearance_rate", "mean"
                ),
                mean_hits_per_candidate=("hits_per_candidate", "mean"),
            )
        )

        summary.to_csv(
            args.output_dir / "forward_backtest_summary.csv",
            index=False,
            encoding="utf-8-sig",
        )

        pivot = summary.pivot(
            index="horizon_requested",
            columns="strategy",
            values="mean_candidate_appearance_rate",
        )

        if "rank_movement_combo" in pivot.columns:
            for baseline in (
                "cumulative_frequency",
                "recent_frequency_10",
                "recent_frequency_25",
                "random_baseline",
            ):
                if baseline in pivot.columns:
                    pivot[f"lift_vs_{baseline}"] = (
                        pivot["rank_movement_combo"] - pivot[baseline]
                    )

        pivot.reset_index().to_csv(
            args.output_dir / "forward_backtest_lift.csv",
            index=False,
            encoding="utf-8-sig",
        )

    metadata = {
        "script": Path(__file__).name,
        "draw_events": event_count,
        "first_date": event_dates[0],
        "last_date": event_dates[-1],
        "first_event_order": event_orders[0],
        "last_event_order": event_orders[-1],
        "tracking_starts": "Day 2; Day 1 is baseline only",
        "number_universe": "0000-9999",
        "top_k": args.top_k,
        "min_train_draws": args.min_train_draws,
        "backtest_step": args.backtest_step,
        "horizons": list(HORIZONS),
        "trigger_event_counts": dict(trigger_event_counts),
        "score_weights": {
            "cumulative_frequency": 0.30,
            "recent_frequency_10": 0.30,
            "recent_frequency_25": 0.15,
            "recent_frequency_50": 0.10,
            "rank_momentum_10": 0.10,
            "rank_momentum_25": 0.05,
        },
        "important_notes": [
            "Rank is cumulative-hit rank with ties broken by ascending number.",
            "A rank improvement does not necessarily mean that number appeared.",
            "Follower relationships are descriptive associations, not proof of prediction.",
            "Backtesting is chronological and evaluates future draws after each checkpoint.",
            "Past patterns may not persist; results are not guaranteed predictions.",
        ],
    }

    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("\nRank-movement analysis completed.")
    print(f"Draw events: {event_count}")
    print(f"Date range: {event_dates[0]} -> {event_dates[-1]}")
    print("Tracking begins on Day 2.")
    print(f"Output directory: {args.output_dir}")
    print(f"Rank movement rows: {len(movement_rows):,}")
    print(f"Top 1 changes: {len(leadership_rows):,}")
    print(f"Follower relationships: {len(follower_rows):,}")
    print(f"Backtest rows: {len(backtest_rows):,}")

    print("\nGenerated files:")
    for path in sorted(args.output_dir.glob("*")):
        if path.is_file():
            print(f"  {path.name} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()