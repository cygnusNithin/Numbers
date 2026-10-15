"""NumberGrid: Three-hit leader and second-to-21st hit tracker.

Rule implemented:
1. Day 1 establishes the baseline; processing begins on Day 2.
2. A number becomes a leader when its cumulative hit count first reaches 3.
3. The active leader stays active until another number reaches 3 for the first time.
4. When a leader activates, and whenever that active leader gets another hit,
   take a fresh snapshot of the 20 other most-hit numbers with at least 2 hits.
   These are ranked as positions 2-21 (leader is position 1 conceptually).
5. While that snapshot is active, record later appearances of those watched
   numbers. A new snapshot replaces the previous watchlist for that leader.

Inputs (defaults, relative to server root):
  data/ai-training/ai_training_draws.csv
  data/ai-training/ai_training_draw_numbers.csv

Outputs:
  leader_activations.csv       each number's first arrival at 3 hits
  leader_watchlist_snapshots.csv  the 20 watched numbers for each snapshot
  leader_watchlist_hits.csv    watched-number appearances after a snapshot
  leader_cycles.csv            summary of each active-leader period
  current_leader_state.csv     current leader and latest watchlist
  metadata.json

Progress bar: uses tqdm if installed; otherwise displays a lightweight
terminal progress bar without requiring another package.

Run from the server directory:
  python scripts/ai_three_hit_leader_tracker.py

Optional:
  python scripts/ai_three_hit_leader_tracker.py --threshold 3 --watch-count 20
  python scripts/ai_three_hit_leader_tracker.py --output-dir data/ai-training/results/three-hit-leaders
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
DEFAULT_DRAWS = DATA_DIR / "ai_training_draws.csv"
DEFAULT_NUMBERS = DATA_DIR / "ai_training_draw_numbers.csv"
DEFAULT_OUTPUT = DATA_DIR / "results" / "three-hit-leaders"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=Path, default=DEFAULT_DRAWS)
    parser.add_argument("--draw-numbers", type=Path, default=DEFAULT_NUMBERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=int, default=3,
                        help="Cumulative hit count that first activates a leader (default: 3).")
    parser.add_argument("--watch-count", type=int, default=20,
                        help="How many other numbers to watch (default: 20).")
    parser.add_argument("--minimum-watch-hits", type=int, default=2,
                        help="Only put numbers with at least this many cumulative hits on watchlists (default: 2).")
    return parser.parse_args()


def normalise_number(value: object) -> str | None:
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
    required_draws = {"event_order", "date"}
    required_numbers = {"event_order", "number"}
    if not required_draws.issubset(draws.columns):
        raise ValueError(f"{draws_path.name} requires {sorted(required_draws)}; found {list(draws.columns)}")
    if not required_numbers.issubset(numbers.columns):
        raise ValueError(f"{numbers_path.name} requires {sorted(required_numbers)}; found {list(numbers.columns)}")

    draws["event_order"] = pd.to_numeric(draws["event_order"], errors="coerce")
    numbers["event_order"] = pd.to_numeric(numbers["event_order"], errors="coerce")
    draws = draws.dropna(subset=["event_order"]).copy()
    numbers = numbers.dropna(subset=["event_order"]).copy()
    draws["event_order"] = draws["event_order"].astype(int)
    numbers["event_order"] = numbers["event_order"].astype(int)
    draws["date"] = pd.to_datetime(draws["date"], dayfirst=True, errors="coerce")
    draws = draws.dropna(subset=["date"]).copy()
    numbers["number"] = numbers["number"].map(normalise_number)
    numbers = numbers.dropna(subset=["number"]).copy()
    valid_orders = set(draws["event_order"].tolist())
    numbers = numbers[numbers["event_order"].isin(valid_orders)].copy()

    by_event = numbers.groupby("event_order")["number"].apply(lambda s: sorted(set(s))).to_dict()
    draws = draws[draws["event_order"].isin(by_event)].copy()
    draws = draws.sort_values(["date", "event_order"]).drop_duplicates("event_order").reset_index(drop=True)
    events = [by_event[int(order)] for order in draws["event_order"]]
    if len(events) < 3:
        raise ValueError(f"At least 3 valid draw events are required; found {len(events)}.")
    if any(not e for e in events):
        raise ValueError("An event has no valid four-digit numbers.")
    return draws, events


def progress_iter(items: Iterable, total: int, label: str = "Processing"):
    """Use tqdm when available; otherwise yield items with a simple progress bar."""
    try:
        from tqdm import tqdm  # type: ignore
        return tqdm(items, total=total, desc=label, unit="draw", dynamic_ncols=True)
    except ImportError:
        def generator():
            width = 28
            for index, item in enumerate(items, start=1):
                filled = int(width * index / max(total, 1))
                bar = "#" * filled + "-" * (width - filled)
                pct = 100.0 * index / max(total, 1)
                print(f"\r{label}: [{bar}] {pct:6.2f}% ({index:,}/{total:,})", end="", file=sys.stderr, flush=True)
                yield item
            print(file=sys.stderr)
        return generator()


def fmt_num(number: int) -> str:
    return f"{number:04d}"


def build_watchlist(counts: dict[int, int], last_seen: dict[int, int], leader: int,
                    watch_count: int, minimum_hits: int) -> list[int]:
    candidates = [n for n, hit_count in counts.items() if n != leader and hit_count >= minimum_hits]
    # Most cumulative hits first; ties: most recently seen first; then smaller number.
    candidates.sort(key=lambda n: (-counts[n], -last_seen.get(n, -1), n))
    return candidates[:watch_count]


def main() -> None:
    args = parse_args()
    if args.threshold < 2:
        raise ValueError("--threshold must be at least 2; Day 1 is only the baseline.")
    if args.watch_count < 1:
        raise ValueError("--watch-count must be at least 1.")
    if args.minimum_watch_hits < 1:
        raise ValueError("--minimum-watch-hits must be at least 1.")

    draws, events = load_data(args.draws, args.draw_numbers)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    event_orders = draws["event_order"].astype(int).tolist()
    dates = draws["date"].dt.strftime("%Y-%m-%d").tolist()

    counts: dict[int, int] = defaultdict(int)
    last_seen: dict[int, int] = {}
    threshold_reached: set[int] = set()
    activations: list[dict] = []
    snapshots: list[dict] = []
    watch_hits: list[dict] = []
    cycles: list[dict] = []

    active_leader: int | None = None
    active_cycle_id: int | None = None
    active_start_index: int | None = None
    active_start_date: str | None = None
    active_start_order: int | None = None
    active_watchlist: list[int] = []
    active_snapshot_id: int | None = None
    active_snapshot_start_index: int | None = None
    snapshot_counter = 0
    cycle_counter = 0
    previous_leader_hits = 0

    def close_cycle(end_index: int, replacement: int | None, reason: str) -> None:
        nonlocal active_leader, active_cycle_id, active_start_index
        if active_leader is None or active_cycle_id is None or active_start_index is None:
            return
        cycles.append({
            "cycle_id": active_cycle_id,
            "leader_number": fmt_num(active_leader),
            "leader_start_day": active_start_index + 1,
            "leader_start_date": active_start_date,
            "leader_start_event_order": active_start_order,
            "leader_end_day": end_index + 1,
            "leader_end_date": dates[end_index],
            "leader_end_event_order": event_orders[end_index],
            "days_active": end_index - active_start_index + 1,
            "leader_hits_at_end": counts[active_leader],
            "replaced_by": fmt_num(replacement) if replacement is not None else "",
            "end_reason": reason,
        })

    for i, event in enumerate(progress_iter(events, len(events), "Three-hit leader analysis")):
        appeared = [int(x) for x in event]
        before = {n: counts[n] for n in appeared}
        for n in appeared:
            counts[n] += 1
            last_seen[n] = i

        # First, record appearances against the watchlist that was active
        # BEFORE this draw. Do this before refreshing/replacing it below, or a
        # leader that hits frequently could refresh the list before its hits
        # have a chance to be recorded.
        if active_leader is not None and active_snapshot_id is not None and active_snapshot_start_index is not None:
            if i > active_snapshot_start_index:
                watch_rank = {n: pos for pos, n in enumerate(active_watchlist, start=2)}
                snapshot_hit_counts = {
                    int(row["watched_number"]): int(row["watched_cumulative_hits"])
                    for row in snapshots if row["snapshot_id"] == active_snapshot_id
                }
                for n in appeared:
                    if n in watch_rank:
                        watch_hits.append({
                            "cycle_id": active_cycle_id,
                            "snapshot_id": active_snapshot_id,
                            "leader_number": fmt_num(active_leader),
                            "leader_hits_at_snapshot": next((int(row["leader_hits"]) for row in reversed(snapshots) if row["snapshot_id"] == active_snapshot_id), counts[active_leader]),
                            "snapshot_day": active_snapshot_start_index + 1,
                            "snapshot_date": dates[active_snapshot_start_index],
                            "hit_day": i + 1,
                            "hit_date": dates[i],
                            "hit_event_order": event_orders[i],
                            "watch_position_at_snapshot": watch_rank[n],
                            "watched_number": fmt_num(n),
                            "watched_hits_at_snapshot": snapshot_hit_counts.get(n, max(0, counts[n] - 1)),
                            "watched_hits_after_hit": counts[n],
                            "draws_after_snapshot": i - active_snapshot_start_index,
                        })

        # Day 1 is baseline only: do not activate leaders on the first draw.
        newly_qualified = []
        if i > 0:
            for n in appeared:
                if before[n] < args.threshold <= counts[n] and n not in threshold_reached:
                    newly_qualified.append(n)
                    threshold_reached.add(n)

        # If multiple numbers reach the threshold in the same draw, pick the
        # one with the greatest cumulative count; break ties by most recent
        # appearance (same event), then lower number. Other qualified numbers
        # remain recorded as threshold arrivals but don't become active leader
        # until/unless another qualifying rule is introduced in a later turn.
        if newly_qualified:
            newly_qualified.sort(key=lambda n: (-counts[n], -last_seen[n], n))
            next_leader = newly_qualified[0]
            for n in newly_qualified:
                activations.append({
                    "day_index": i + 1,
                    "event_order": event_orders[i],
                    "date": dates[i],
                    "number": fmt_num(n),
                    "hits_after_draw": counts[n],
                    "became_active_leader": n == next_leader,
                    "activation_note": "Reached threshold this draw" if n == next_leader else "Reached threshold same draw; not selected as active leader",
                })

            if active_leader is not None:
                close_cycle(i - 1, next_leader, "replaced_when_new_number_reached_threshold")
            cycle_counter += 1
            active_leader = next_leader
            active_cycle_id = cycle_counter
            active_start_index = i
            active_start_date = dates[i]
            active_start_order = event_orders[i]
            active_watchlist = []
            active_snapshot_id = None
            active_snapshot_start_index = None
            previous_leader_hits = counts[active_leader]
            # Snapshot the 20 other numbers at leader activation.
            snapshot_counter += 1
            active_snapshot_id = snapshot_counter
            active_snapshot_start_index = i
            active_watchlist = build_watchlist(counts, last_seen, active_leader,
                                               args.watch_count, args.minimum_watch_hits)
            for rank_pos, n in enumerate(active_watchlist, start=2):
                snapshots.append({
                    "cycle_id": active_cycle_id,
                    "snapshot_id": active_snapshot_id,
                    "snapshot_reason": "leader_activated",
                    "snapshot_day": i + 1,
                    "snapshot_date": dates[i],
                    "snapshot_event_order": event_orders[i],
                    "leader_number": fmt_num(active_leader),
                    "leader_hits": counts[active_leader],
                    "watch_position": rank_pos,
                    "watched_number": fmt_num(n),
                    "watched_cumulative_hits": counts[n],
                    "watched_last_seen_day": last_seen[n] + 1,
                })

        elif active_leader is not None and active_leader in appeared and counts[active_leader] > previous_leader_hits:
            # Refresh the 2nd-21st list whenever the current leader gets another hit.
            previous_leader_hits = counts[active_leader]
            snapshot_counter += 1
            active_snapshot_id = snapshot_counter
            active_snapshot_start_index = i
            active_watchlist = build_watchlist(counts, last_seen, active_leader,
                                               args.watch_count, args.minimum_watch_hits)
            for rank_pos, n in enumerate(active_watchlist, start=2):
                snapshots.append({
                    "cycle_id": active_cycle_id,
                    "snapshot_id": active_snapshot_id,
                    "snapshot_reason": "active_leader_got_extra_hit",
                    "snapshot_day": i + 1,
                    "snapshot_date": dates[i],
                    "snapshot_event_order": event_orders[i],
                    "leader_number": fmt_num(active_leader),
                    "leader_hits": counts[active_leader],
                    "watch_position": rank_pos,
                    "watched_number": fmt_num(n),
                    "watched_cumulative_hits": counts[n],
                    "watched_last_seen_day": last_seen[n] + 1,
                })

    if active_leader is not None and active_cycle_id is not None:
        close_cycle(len(events) - 1, None, "end_of_available_data")

    # Current state includes the latest leader's current ranked watchlist.
    current_rows = []
    if active_leader is not None:
        current_watchlist = build_watchlist(counts, last_seen, active_leader,
                                            args.watch_count, args.minimum_watch_hits)
        for rank_pos, n in enumerate(current_watchlist, start=2):
            current_rows.append({
                "active_cycle_id": active_cycle_id,
                "active_leader": fmt_num(active_leader),
                "leader_hits": counts[active_leader],
                "leader_start_date": active_start_date,
                "watch_position": rank_pos,
                "watched_number": fmt_num(n),
                "watched_cumulative_hits": counts[n],
                "watched_last_seen_date": dates[last_seen[n]] if n in last_seen else "",
            })

    def save(rows: list[dict], filename: str, columns: list[str] | None = None) -> None:
        frame = pd.DataFrame(rows, columns=columns)
        frame.to_csv(args.output_dir / filename, index=False, encoding="utf-8-sig")

    save(activations, "leader_activations.csv", [
        "day_index", "event_order", "date", "number", "hits_after_draw",
        "became_active_leader", "activation_note",
    ])
    save(snapshots, "leader_watchlist_snapshots.csv", [
        "cycle_id", "snapshot_id", "snapshot_reason", "snapshot_day", "snapshot_date",
        "snapshot_event_order", "leader_number", "leader_hits", "watch_position",
        "watched_number", "watched_cumulative_hits", "watched_last_seen_day",
    ])
    save(watch_hits, "leader_watchlist_hits.csv", [
        "cycle_id", "snapshot_id", "leader_number", "leader_hits_at_snapshot",
        "snapshot_day", "snapshot_date", "hit_day", "hit_date", "hit_event_order",
        "watch_position_at_snapshot", "watched_number", "watched_hits_at_snapshot",
        "watched_hits_after_hit", "draws_after_snapshot",
    ])
    save(cycles, "leader_cycles.csv", [
        "cycle_id", "leader_number", "leader_start_day", "leader_start_date",
        "leader_start_event_order", "leader_end_day", "leader_end_date",
        "leader_end_event_order", "days_active", "leader_hits_at_end", "replaced_by", "end_reason",
    ])
    save(current_rows, "current_leader_state.csv", [
        "active_cycle_id", "active_leader", "leader_hits", "leader_start_date",
        "watch_position", "watched_number", "watched_cumulative_hits", "watched_last_seen_date",
    ])

    metadata = {
        "script": Path(__file__).name,
        "draw_events": len(events),
        "first_date": dates[0],
        "last_date": dates[-1],
        "tracking_starts": "Day 2; Day 1 is baseline only",
        "leader_rule": f"A number activates when its cumulative hits first reach {args.threshold} on Day 2 or later.",
        "replacement_rule": "The active leader is replaced when another number first reaches the threshold; if several qualify in the same draw, highest cumulative hits then lowest number wins.",
        "watchlist_rule": f"At activation and each extra hit by the active leader, snapshot up to {args.watch_count} other numbers with at least {args.minimum_watch_hits} cumulative hits, ordered by hits descending, last-seen recency descending, then number ascending.",
        "outputs": [
            "leader_activations.csv", "leader_watchlist_snapshots.csv",
            "leader_watchlist_hits.csv", "leader_cycles.csv", "current_leader_state.csv",
        ],
        "caveats": [
            "This is a descriptive tracking rule, not a proven lottery prediction method.",
            "The watchlist is a snapshot; it refreshes when the active leader gets an extra hit.",
            "A watched number's later appearance is recorded, but does not establish that the leader caused or predicted it.",
            "If fewer than 20 other numbers have the minimum hit count, the watchlist contains fewer than 20.",
        ],
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("\nThree-hit leader analysis completed.")
    print(f"Draw events: {len(events):,} ({dates[0]} to {dates[-1]})")
    print(f"Threshold arrivals: {len(activations):,}")
    print(f"Active leader cycles: {len(cycles):,}")
    print(f"Watchlist snapshots: {snapshot_counter:,}")
    print(f"Recorded watchlist hits: {len(watch_hits):,}")
    print(f"Output directory: {args.output_dir.resolve()}")
    print("Files:")
    for path in sorted(args.output_dir.glob("*")):
        if path.is_file():
            print(f"  {path.name} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
