"""
NumberGrid: Rank Movement, Leadership, Followers and Forward Backtesting

Tracks all 10,000 four-digit numbers (0000-9999), using Day 1 as the
baseline and reporting changes from Day 2 onward.

Inputs:
  data/ai-training/ai_training_draws.csv
      Required columns: event_order, date
  data/ai-training/ai_training_draw_numbers.csv
      Required columns: event_order, number

Run from the server directory:
  python scripts/ai_rank_movement_followers.py

Optional:
  python scripts/ai_rank_movement_followers.py --top-k 100
  python scripts/ai_rank_movement_followers.py --min-train-draws 100

Progress bars:
  pip install tqdm

Important:
  This is exploratory historical analysis, not a guaranteed prediction system.
  Rank movement is based on cumulative-hit rank, with ties broken by number.
  The full rank matrix is saved in compressed NPZ format. The CSV movement
  file is intentionally sparse to avoid producing tens of millions of rows:
  it includes appearances, large rank jumps, and Top-100 entries/exits.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from tqdm.auto import tqdm
except ImportError:
    # If tqdm is not installed, run without progress bars.
    def tqdm(iterable=None, **kwargs):
        return iterable


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
    """Convert a valid 0-9999 value to a four-character string."""
    if pd.isna(value):
        return None

    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit() or len(text) > 4:
        return None

    return text.zfill(4)


def load_data(draws_path: Path, numbers_path: Path):
    if not draws_path.exists():
        raise FileNotFoundError(f"Missing draw file: {draws_path}")
    if not numbers_path.exists():
        raise FileNotFoundError(f"Missing draw-number file: {numbers_path}")

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

    draws["event_order"] = pd.to_numeric(draws["event_order"], errors="coerce")
    numbers["event_order"] = pd.to_numeric(numbers["event_order"], errors="coerce")
    draws = draws.dropna(subset=["event_order"]).copy()
    numbers = numbers.dropna(subset=["event_order"]).copy()
    draws["event_order"] = draws["event_order"].astype(int)
    numbers["event_order"] = numbers["event_order"].astype(int)

    # Project dates commonly use DD/MM/YYYY.
    draws["date"] = pd.to_datetime(draws["date"], dayfirst=True, errors="coerce")
    draws = draws.dropna(subset=["date"]).copy()

    numbers["number"] = numbers["number"].map(normalise_number)
    numbers = numbers.dropna(subset=["number"]).copy()
    numbers = numbers[numbers["event_order"].isin(draws["event_order"])].copy()

    numbers_by_event = (
        numbers.groupby("event_order")["number"]
        .apply(lambda values: sorted(set(values)))
        .to_dict()
    )

    draws = draws[draws["event_order"].isin(numbers_by_event)].copy()
    draws = (
        draws.sort_values(["date", "event_order"])
        .drop_duplicates("event_order")
        .reset_index(drop=True)
    )

    events = [numbers_by_event[int(event_order)] for event_order in draws["event_order"]]

    if len(events) < 3:
        raise ValueError(f"At least 3 valid draw events are required; found {len(events)}.")
    if any(not event for event in events):
        raise ValueError("An event has no valid numbers.")

    return draws, events


def number_text(value: int) -> str:
    return f"{int(value):04d}"


def make_ranks(counts: np.ndarray) -> np.ndarray:
    """Ordinal ranks: highest hit count first, then smaller number first."""
    ids = np.arange(NUMBER_COUNT)
    order = np.lexsort((ids, -counts))
    ranks = np.empty(NUMBER_COUNT, dtype=np.int16)
    ranks[order] = np.arange(1, NUMBER_COUNT + 1, dtype=np.int16)
    return ranks


def ranked_ids(ranks: np.ndarray, limit: int) -> np.ndarray:
    return np.argsort(ranks, kind="stable")[:limit]


def percentile_score(values: np.ndarray) -> np.ndarray:
    """Percentile score with average ranks for ties (avoids tie-score bias)."""
    values = np.asarray(values)
    return pd.Series(values).rank(method="average", pct=True).to_numpy(dtype=float)


def make_candidate_score(
    cumulative_counts: np.ndarray,
    recent10: np.ndarray,
    recent25: np.ndarray,
    recent50: np.ndarray,
    rank_momentum10: np.ndarray,
    rank_momentum25: np.ndarray,
) -> np.ndarray:
    # Exploratory weights only; the walk-forward test evaluates this formula.
    return (
        0.30 * percentile_score(cumulative_counts)
        + 0.30 * percentile_score(recent10)
        + 0.15 * percentile_score(recent25)
        + 0.10 * percentile_score(recent50)
        + 0.10 * percentile_score(rank_momentum10)
        + 0.05 * percentile_score(rank_momentum25)
    )


def update_recent_counts(
    recent_counts: dict[int, np.ndarray],
    events: list[np.ndarray],
    event_index: int,
) -> None:
    """Update rolling windows in O(number of numbers in the event)."""
    current = events[event_index]
    for window in RECENT_WINDOWS:
        recent_counts[window][current] += 1
        expired_index = event_index - window
        if expired_index >= 0:
            recent_counts[window][events[expired_index]] -= 1


def main():
    args = parse_args()

    if not 1 <= args.top_k <= NUMBER_COUNT:
        raise ValueError("--top-k must be between 1 and 10000.")
    if args.min_train_draws < 2:
        raise ValueError("--min-train-draws must be at least 2.")
    if args.backtest_step < 1:
        raise ValueError("--backtest-step must be at least 1.")

    rng = np.random.default_rng(args.seed)
    draws, raw_events = load_data(args.draws, args.draw_numbers)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    event_orders = draws["event_order"].astype(int).tolist()
    event_dates = draws["date"].dt.strftime("%Y-%m-%d").tolist()
    events = [np.asarray([int(n) for n in event], dtype=np.int32) for event in raw_events]

    event_count = len(events)
    top_limit = max(100, args.top_k)

    counts = np.zeros(NUMBER_COUNT, dtype=np.int32)
    rolling = {window: np.zeros(NUMBER_COUNT, dtype=np.int32) for window in RECENT_WINDOWS}

    count_snapshots: list[np.ndarray] = []
    rank_snapshots: list[np.ndarray] = []
    recent_snapshots: dict[int, list[np.ndarray]] = {window: [] for window in RECENT_WINDOWS}

    rank_history_rows = []
    movement_rows = []
    leadership_rows = []
    top10_entry_rows = []
    top100_entry_rows = []

    previous_rank = None
    previous_top1 = None
    previous_top10: set[int] = set()
    previous_top100: set[int] = set()

    # 1. Build snapshots. Day 1 is the baseline; reporting starts on Day 2.
    for i, event in tqdm(
        enumerate(events),
        total=event_count,
        desc="Building rank snapshots",
        unit="draw",
    ):
        counts[event] += 1
        update_recent_counts(rolling, events, i)

        current_rank = make_ranks(counts)
        count_snapshots.append(counts.copy())
        rank_snapshots.append(current_rank.copy())
        for window in RECENT_WINDOWS:
            recent_snapshots[window].append(rolling[window].copy())

        top_ids = ranked_ids(current_rank, top_limit)
        current_top1 = int(top_ids[0])
        current_top10 = set(ranked_ids(current_rank, 10).tolist())
        current_top100 = set(ranked_ids(current_rank, 100).tolist())

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

        for value in top_ids:
            rank_history_rows.append(
                {
                    "day_index": day_index,
                    "event_order": order,
                    "date": date,
                    "number": number_text(value),
                    "rank": int(current_rank[value]),
                    "cumulative_hits": int(counts[value]),
                    "recent_hits_10": int(rolling[10][value]),
                    "recent_hits_25": int(rolling[25][value]),
                    "recent_hits_50": int(rolling[50][value]),
                    "rank_change": int(previous_rank[value] - current_rank[value]),
                    "appeared_today": value in appeared_today,
                }
            )

        rank_delta = previous_rank.astype(np.int32) - current_rank.astype(np.int32)
        entered_top10 = current_top10 - previous_top10
        left_top10 = previous_top10 - current_top10
        entered_top100 = current_top100 - previous_top100
        left_top100 = previous_top100 - current_top100

        # Sparse CSV: keep useful movement rows rather than millions of tiny
        # tie-break displacement rows. Complete rank history is in the NPZ.
        relevant_ids = set(np.flatnonzero(np.abs(rank_delta) >= 100).tolist())
        relevant_ids.update(appeared_today)
        relevant_ids.update(entered_top100)
        relevant_ids.update(left_top100)

        for value in sorted(relevant_ids):
            delta = int(rank_delta[value])
            if (
                delta == 0
                and value not in appeared_today
                and value not in entered_top100
                and value not in left_top100
            ):
                continue
            movement_rows.append(
                {
                    "day_index": day_index,
                    "event_order": order,
                    "date": date,
                    "number": number_text(value),
                    "previous_rank": int(previous_rank[value]),
                    "current_rank": int(current_rank[value]),
                    "rank_change": delta,
                    "movement": "UP" if delta > 0 else ("DOWN" if delta < 0 else "NO_CHANGE"),
                    "appeared_today": value in appeared_today,
                    "entered_top10": value in entered_top10,
                    "left_top10": value in left_top10,
                    "entered_top100": value in entered_top100,
                    "left_top100": value in left_top100,
                    "cumulative_hits": int(counts[value]),
                }
            )

        if current_top1 != previous_top1:
            leadership_rows.append(
                {
                    "day_index": day_index,
                    "event_order": order,
                    "date": date,
                    "previous_top1": number_text(previous_top1),
                    "new_top1": number_text(current_top1),
                    "new_top1_hits": int(counts[current_top1]),
                    "new_top1_previous_rank": int(previous_rank[current_top1]),
                    "new_top1_appeared_today": current_top1 in appeared_today,
                }
            )

        for value in sorted(entered_top10):
            top10_entry_rows.append(
                {
                    "day_index": day_index,
                    "event_order": order,
                    "date": date,
                    "number": number_text(value),
                    "rank": int(current_rank[value]),
                    "cumulative_hits": int(counts[value]),
                    "appeared_today": value in appeared_today,
                }
            )
        for value in sorted(entered_top100):
            top100_entry_rows.append(
                {
                    "day_index": day_index,
                    "event_order": order,
                    "date": date,
                    "number": number_text(value),
                    "rank": int(current_rank[value]),
                    "cumulative_hits": int(counts[value]),
                    "appeared_today": value in appeared_today,
                }
            )

        previous_rank = current_rank
        previous_top1 = current_top1
        previous_top10 = current_top10
        previous_top100 = current_top100

    # Save complete rank snapshots for all numbers and all events. Ranks fit
    # safely in int16 (1..10000); compressed NPZ avoids a massive CSV.
    np.savez_compressed(
        args.output_dir / "all_number_rank_snapshots.npz",
        ranks=np.stack(rank_snapshots).astype(np.int16),
        event_orders=np.asarray(event_orders, dtype=np.int64),
        dates=np.asarray(event_dates, dtype="U10"),
        number_ids=np.arange(NUMBER_COUNT, dtype=np.int16),
    )

    # 2. Follower analysis. Correct denominator: every eligible trigger window,
    # including windows where a particular follower did NOT appear.
    follower_stats = defaultdict(lambda: {"appeared_windows": 0, "hits": 0})
    eligible_windows = defaultdict(int)
    trigger_event_counts = defaultdict(int)

    for i in tqdm(
        range(1, max(1, event_count - 1)),
        total=max(0, event_count - 2),
        desc="Follower analysis",
        unit="draw",
    ):
        old_rank = rank_snapshots[i - 1]
        new_rank = rank_snapshots[i]
        old_top1 = int(ranked_ids(old_rank, 1)[0])
        new_top1 = int(ranked_ids(new_rank, 1)[0])

        old_top10 = set(ranked_ids(old_rank, 10).tolist())
        new_top10 = set(ranked_ids(new_rank, 10).tolist())
        old_top100 = set(ranked_ids(old_rank, 100).tolist())
        new_top100 = set(ranked_ids(new_rank, 100).tolist())

        delta = old_rank.astype(np.int32) - new_rank.astype(np.int32)
        triggers = set()

        if old_top1 != new_top1:
            triggers.add(("top1_leader_change", new_top1))
        for value in new_top10 - old_top10:
            triggers.add(("top10_entry", int(value)))
        for value in new_top100 - old_top100:
            triggers.add(("top100_entry", int(value)))
        for value in np.flatnonzero(delta >= 100):
            triggers.add(("rank_jump_100_plus", int(value)))

        for trigger_type, trigger_id in triggers:
            trigger_event_counts[trigger_type] += 1
            trigger_text = number_text(trigger_id)

            for horizon in HORIZONS:
                future_events = events[i + 1 : i + 1 + horizon]
                # Use only full windows so horizon rates are comparable.
                if len(future_events) != horizon:
                    continue

                denominator_key = (trigger_type, trigger_text, horizon)
                eligible_windows[denominator_key] += 1

                future_counts = np.zeros(NUMBER_COUNT, dtype=np.int32)
                for future_event in future_events:
                    future_counts[future_event] += 1

                for follower_id in np.flatnonzero(future_counts > 0):
                    if follower_id == trigger_id:
                        continue
                    key = (
                        trigger_type,
                        trigger_text,
                        number_text(follower_id),
                        horizon,
                    )
                    follower_stats[key]["appeared_windows"] += 1
                    follower_stats[key]["hits"] += int(future_counts[follower_id])

    follower_rows = []
    for (trigger_type, trigger, follower, horizon), stat in follower_stats.items():
        trials = eligible_windows[(trigger_type, trigger, horizon)]
        if trials <= 0:
            continue
        follower_rows.append(
            {
                "trigger_type": trigger_type,
                "trigger_number": trigger,
                "follower_number": follower,
                "horizon_draws": horizon,
                "eligible_trigger_windows": trials,
                "follower_appeared_windows": stat["appeared_windows"],
                "follower_appearance_rate": stat["appeared_windows"] / trials,
                "total_follower_hits": stat["hits"],
                "mean_follower_hits_per_trigger_window": stat["hits"] / trials,
            }
        )

    follower_rows.sort(
        key=lambda row: (
            row["trigger_type"],
            row["horizon_draws"],
            -row["follower_appearance_rate"],
            -row["mean_follower_hits_per_trigger_window"],
            row["trigger_number"],
            row["follower_number"],
        )
    )

    # 3. Current ranking based on all available historical events.
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
        latest_counts, latest_r10, latest_r25, latest_r50, momentum10, momentum25
    )

    current_rows = []
    for value in np.argsort(-latest_score, kind="stable")[:top_limit]:
        current_rows.append(
            {
                "number": number_text(value),
                "score": round(float(latest_score[value]), 8),
                "cumulative_rank": int(latest_rank[value]),
                "cumulative_hits": int(latest_counts[value]),
                "recent_hits_10": int(latest_r10[value]),
                "recent_hits_25": int(latest_r25[value]),
                "recent_hits_50": int(latest_r50[value]),
                "rank_change_last_10_draws": int(momentum10[value]),
                "rank_change_last_25_draws": int(momentum25[value]),
            }
        )

    # 4. Chronological walk-forward backtest. Every checkpoint only uses
    # history up to that point; outcomes are in subsequent complete windows.
    backtest_rows = []
    checkpoints = list(
        range(
            args.min_train_draws,
            event_count - max(HORIZONS) + 1,
            args.backtest_step,
        )
    )

    for checkpoint in tqdm(
        checkpoints,
        total=len(checkpoints),
        desc="Walk-forward backtest",
        unit="checkpoint",
    ):
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
            train_counts, train_r10, train_r25, train_r50, momentum10, momentum25
        )

        strategies = {
            "rank_movement_combo": np.argsort(-score, kind="stable")[: args.top_k],
            "cumulative_frequency": np.argsort(-train_counts, kind="stable")[: args.top_k],
            "recent_frequency_10": np.argsort(-train_r10, kind="stable")[: args.top_k],
            "recent_frequency_25": np.argsort(-train_r25, kind="stable")[: args.top_k],
            "random_baseline": rng.choice(NUMBER_COUNT, size=args.top_k, replace=False),
        }

        for horizon in HORIZONS:
            future_events = events[checkpoint : checkpoint + horizon]
            if len(future_events) != horizon:
                continue

            future_counts = np.zeros(NUMBER_COUNT, dtype=np.int32)
            for future_event in future_events:
                future_counts[future_event] += 1
            future_present = future_counts > 0

            for strategy, chosen in strategies.items():
                unique_appearing = int(future_present[chosen].sum())
                total_hits = int(future_counts[chosen].sum())
                backtest_rows.append(
                    {
                        "checkpoint_event_order": event_orders[idx],
                        "checkpoint_date": event_dates[idx],
                        "training_draws": checkpoint,
                        "horizon_requested": horizon,
                        "horizon_actual": len(future_events),
                        "strategy": strategy,
                        "top_k": args.top_k,
                        "unique_candidates_appearing": unique_appearing,
                        "total_hits_by_candidates": total_hits,
                        "candidate_appearance_rate": unique_appearing / args.top_k,
                        "hits_per_candidate": total_hits / args.top_k,
                    }
                )

    # 5. Save reports.
    def save(rows, filename):
        pd.DataFrame(rows).to_csv(args.output_dir / filename, index=False, encoding="utf-8-sig")

    save(rank_history_rows, "rank_history_top100.csv")
    save(movement_rows, "rank_movement_events.csv")
    save(leadership_rows, "top1_leadership_timeline.csv")
    save(top10_entry_rows, "top10_entries.csv")
    save(top100_entry_rows, "top100_entries.csv")
    save(follower_rows, "follower_relationships.csv")
    save(current_rows, "current_number_ranking.csv")
    save(backtest_rows, "forward_backtest.csv")

    backtest_df = pd.DataFrame(backtest_rows)
    if not backtest_df.empty:
        summary = (
            backtest_df.groupby(["horizon_requested", "strategy"], as_index=False)
            .agg(
                checkpoints=("checkpoint_date", "nunique"),
                mean_unique_candidates_appearing=("unique_candidates_appearing", "mean"),
                mean_total_hits=("total_hits_by_candidates", "mean"),
                mean_candidate_appearance_rate=("candidate_appearance_rate", "mean"),
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
                    pivot[f"lift_vs_{baseline}"] = pivot["rank_movement_combo"] - pivot[baseline]
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
            "Ranks are ordinal; ties are broken by ascending number.",
            "A rank change does not necessarily mean that number appeared.",
            "rank_movement_events.csv is a sparse report; full rank history is in all_number_rank_snapshots.npz.",
            "Follower appearance rates use all eligible complete trigger windows as the denominator, including non-appearances.",
            "Follower relationships are descriptive associations, not proof of prediction.",
            "Backtesting is chronological; future outcomes are excluded from checkpoint features.",
            "Backtest horizons overlap and are not independent observations.",
            "Score weights are exploratory and not proven optimal.",
            "Past patterns may not persist; results are not guaranteed predictions.",
        ],
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("\nRank-movement analysis completed.")
    print(f"Draw events: {event_count}")
    print(f"Date range: {event_dates[0]} -> {event_dates[-1]}")
    print("Tracking begins on Day 2.")
    print(f"Output directory (where files are saved): {args.output_dir}")
    print(f"Top-rank history rows: {len(rank_history_rows):,}")
    print(f"Sparse movement rows: {len(movement_rows):,}")
    print(f"Top 1 changes: {len(leadership_rows):,}")
    print(f"Follower relationships: {len(follower_rows):,}")
    print(f"Backtest rows: {len(backtest_rows):,}")
    print("\nGenerated files:")
    for path in sorted(args.output_dir.glob("*")):
        if path.is_file():
            print(f"  {path.name} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()