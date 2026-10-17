"""Track the first 3-hit milestone and the changing top-21 number ranking.

Run from the server directory:
    python scripts/ai_three_hit_tracker_simple.py

Inputs:
    data/ai-training/ai_training_draws.csv
    data/ai-training/ai_training_draw_numbers.csv

Outputs in data/ai-training/results/three-hit-tracker/:
    current_top21.csv   Latest ranking, highest cumulative hits first.
    ranking_history.csv Top 21 after each draw from cycle start onward.
    watched_hits.csv   Every draw-hit for a number ranked 1-21 before or after that draw.
    cycle_summary.csv  When tracking began and final ranking summary.

The cycle starts on the first draw where any number reaches the threshold (3 by default).
There is no separate active leader. After each draw, all numbers are ranked by cumulative
hits, then most recent appearance, then number ascending. Position 1 is the current top
number; positions 2-21 are the other 20 numbers being studied.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ai-training"
DEFAULT_DRAWS = DATA_DIR / "ai_training_draws.csv"
DEFAULT_NUMBERS = DATA_DIR / "ai_training_draw_numbers.csv"
DEFAULT_OUTPUT = DATA_DIR / "results" / "three-hit-tracker"


def normalise_number(value: object) -> str | None:
    if pd.isna(value):
        return None
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    if not value.isdigit() or len(value) > 4:
        return None
    return value.zfill(4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=Path, default=DEFAULT_DRAWS)
    parser.add_argument("--draw-numbers", type=Path, default=DEFAULT_NUMBERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--watch-count", type=int, default=21,
                        help="Number of ranked numbers to show, including position 1 (default: 21).")
    return parser.parse_args()


def load_events(draws_path: Path, numbers_path: Path):
    if not draws_path.exists():
        raise FileNotFoundError(f"Draw file not found: {draws_path}")
    if not numbers_path.exists():
        raise FileNotFoundError(f"Draw-number file not found: {numbers_path}")

    draws = pd.read_csv(draws_path, dtype=str)
    numbers = pd.read_csv(numbers_path, dtype=str)
    if not {"event_order", "date"}.issubset(draws.columns):
        raise ValueError(f"{draws_path.name} must contain event_order,date")
    if not {"event_order", "number"}.issubset(numbers.columns):
        raise ValueError(f"{numbers_path.name} must contain event_order,number")

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

    valid_orders = set(draws["event_order"])
    numbers = numbers[numbers["event_order"].isin(valid_orders)]
    numbers_by_event = numbers.groupby("event_order")["number"].apply(lambda s: sorted(set(s))).to_dict()
    draws = draws[draws["event_order"].isin(numbers_by_event)].copy()
    draws = draws.sort_values(["date", "event_order"]).drop_duplicates("event_order").reset_index(drop=True)
    events = []
    for i, row in draws.iterrows():
        order = int(row["event_order"])
        events.append({
            "draw_index": i + 1,
            "event_order": order,
            "date": row["date"].strftime("%Y-%m-%d"),
            "numbers": numbers_by_event.get(order, []),
        })
    if not events:
        raise ValueError("No valid draw events found.")
    return events


def rank_numbers(counts: Counter, last_seen: dict[str, int]):
    # Most cumulative hits first; ties: most recently seen, then numeric order.
    return sorted(counts, key=lambda n: (-counts[n], -last_seen.get(n, 0), int(n)))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.threshold < 1:
        raise ValueError("--threshold must be at least 1")
    if args.watch_count < 1:
        raise ValueError("--watch-count must be at least 1")

    events = load_events(args.draws, args.draw_numbers)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    last_seen: dict[str, int] = {}
    cycle_start_index = None
    cycle_start_date = ""
    cycle_start_order = ""
    cycle_start_numbers: list[str] = []
    ranking_history: list[dict] = []
    watched_hits: list[dict] = []
    current_top: list[str] = []
    previous_rank: dict[str, int] = {}
    hit_rows_count = 0

    for event in events:
        idx = event["draw_index"]
        draw_numbers = event["numbers"]
        ranks_before = {n: rank for rank, n in enumerate(rank_numbers(counts, last_seen), start=1)} if counts else {}
        hits_before = {n: counts[n] for n in draw_numbers}

        for number in draw_numbers:
            counts[number] += 1
            last_seen[number] = idx

        # Cycle begins once, at the first draw where at least one number reaches threshold.
        if cycle_start_index is None:
            newly_thresholded = sorted(
                n for n in draw_numbers
                if counts[n] >= args.threshold and hits_before.get(n, 0) < args.threshold
            )
            if newly_thresholded:
                cycle_start_index = idx
                cycle_start_date = event["date"]
                cycle_start_order = event["event_order"]
                cycle_start_numbers = newly_thresholded

        if cycle_start_index is None:
            continue

        ranked = rank_numbers(counts, last_seen)
        current_top = ranked[:args.watch_count]
        ranks_after = {n: rank for rank, n in enumerate(ranked, start=1)}
        draws_since_start = idx - cycle_start_index
        trigger_text = ";".join(cycle_start_numbers)

        # Simple history: current top N after every draw, once tracking has started.
        for rank, number in enumerate(current_top, start=1):
            ranking_history.append({
                "draw_index": idx,
                "event_order": event["event_order"],
                "date": event["date"],
                "draws_since_cycle_start": draws_since_start,
                "cycle_start_date": cycle_start_date,
                "cycle_start_numbers": trigger_text,
                "rank": rank,
                "number": number,
                "cumulative_hits": counts[number],
                "hit_this_draw": int(number in draw_numbers),
                "last_seen_date": events[last_seen[number] - 1]["date"] if last_seen[number] <= len(events) else event["date"],
            })

        # Log a number's hit if it was in the top N before the draw or is in the top N after it.
        # This catches watched numbers that move into the top N on the very draw they hit.
        for number in draw_numbers:
            before_rank = ranks_before.get(number, "")
            after_rank = ranks_after.get(number, "")
            if (before_rank != "" and before_rank <= args.watch_count) or (after_rank != "" and after_rank <= args.watch_count):
                watched_hits.append({
                    "draw_index": idx,
                    "event_order": event["event_order"],
                    "date": event["date"],
                    "draws_since_cycle_start": draws_since_start,
                    "cycle_start_date": cycle_start_date,
                    "cycle_start_numbers": trigger_text,
                    "number": number,
                    "rank_before_draw": before_rank,
                    "rank_after_draw": after_rank,
                    "hits_before_draw": hits_before.get(number, 0),
                    "cumulative_hits_after_draw": counts[number],
                    "hit_number": counts[number],
                })
                hit_rows_count += 1
        previous_rank = ranks_after

    # Current top list from the final historical draw.
    final_event = events[-1]
    current_rows = []
    final_ranked = rank_numbers(counts, last_seen)[:args.watch_count]
    for rank, number in enumerate(final_ranked, start=1):
        current_rows.append({
            "rank": rank,
            "number": number,
            "cumulative_hits": counts[number],
            "last_seen_date": events[last_seen[number] - 1]["date"],
            "last_seen_draw_index": last_seen[number],
        })

    summary = [{
        "cycle_started": bool(cycle_start_index is not None),
        "threshold": args.threshold,
        "cycle_start_draw_index": cycle_start_index or "",
        "cycle_start_event_order": cycle_start_order,
        "cycle_start_date": cycle_start_date,
        "number_or_numbers_reaching_threshold_first": ";".join(cycle_start_numbers),
        "draws_in_input": len(events),
        "draws_tracked_from_cycle_start": (len(events) - cycle_start_index + 1) if cycle_start_index else 0,
        "watch_count_including_top": args.watch_count,
        "final_top_number": final_ranked[0] if final_ranked else "",
        "final_top_hits": counts[final_ranked[0]] if final_ranked else 0,
        "final_dataset_date": final_event["date"],
        "ranking_history_rows": len(ranking_history),
        "watched_hit_rows": hit_rows_count,
    }]

    write_csv(args.output_dir / "current_top21.csv", current_rows,
              ["rank", "number", "cumulative_hits", "last_seen_date", "last_seen_draw_index"])
    write_csv(args.output_dir / "ranking_history.csv", ranking_history,
              ["draw_index", "event_order", "date", "draws_since_cycle_start", "cycle_start_date", "cycle_start_numbers", "rank", "number", "cumulative_hits", "hit_this_draw", "last_seen_date"])
    write_csv(args.output_dir / "watched_hits.csv", watched_hits,
              ["draw_index", "event_order", "date", "draws_since_cycle_start", "cycle_start_date", "cycle_start_numbers", "number", "rank_before_draw", "rank_after_draw", "hits_before_draw", "cumulative_hits_after_draw", "hit_number"])
    write_csv(args.output_dir / "cycle_summary.csv", summary,
              ["cycle_started", "threshold", "cycle_start_draw_index", "cycle_start_event_order", "cycle_start_date", "number_or_numbers_reaching_threshold_first", "draws_in_input", "draws_tracked_from_cycle_start", "watch_count_including_top", "final_top_number", "final_top_hits", "final_dataset_date", "ranking_history_rows", "watched_hit_rows"])

    print("\nThree-hit tracking complete")
    print(f"Draws processed: {len(events):,}")
    print(f"Cycle starts: {cycle_start_date or 'not reached'}")
    print(f"First threshold number(s): {', '.join(cycle_start_numbers) if cycle_start_numbers else 'none'}")
    print(f"Final top number: {final_ranked[0] if final_ranked else 'none'} ({counts[final_ranked[0]] if final_ranked else 0} hits)")
    print(f"Ranking history rows: {len(ranking_history):,}")
    print(f"Watched hit rows: {hit_rows_count:,}")
    print(f"Output folder: {args.output_dir.resolve()}")
    print("Files: current_top21.csv, ranking_history.csv, watched_hits.csv, cycle_summary.csv")
    print("\nOpen current_top21.csv first. It is sorted by cumulative hits, with rank 1 at the top.")


if __name__ == "__main__":
    main()
