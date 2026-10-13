from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------
# 7396 event-aligned chaser analysis — v2
# Inputs: data/ai-training/ai_training_draws.csv
#         data/ai-training/ai_training_draw_numbers.csv
# Run: python .\scripts\ai_7396_event_aligned_chasers_v2.py
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "ai-training"
RESULTS_DIR = DATA_DIR / "results"
DRAWS_FILE = DATA_DIR / "ai_training_draws.csv"
NUMBERS_FILE = DATA_DIR / "ai_training_draw_numbers.csv"

FOCUS = "7396"
HORIZONS = [1, 5, 10, 20]
TOP_K = 100
MIN_TRAIN_ANCHORS = 3
MIN_TRAIN_CONTROLS = 20


def safe_rate(numerator: float, denominator: float) -> float:
    """A zero denominator produces 0.0 instead of a crash or NaN."""
    return float(numerator) / float(denominator) if denominator and denominator > 0 else 0.0


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    for path in (DRAWS_FILE, NUMBERS_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Missing input file: {path}")

    draws = pd.read_csv(
        DRAWS_FILE,
        dtype={"serialNumber": "string", "date": "string", "fileName": "string"},
    )
    numbers = pd.read_csv(
        NUMBERS_FILE,
        dtype={"serialNumber": "string", "number": "string"},
        usecols=["event_order", "serialNumber", "number"],
    )

    required = {"event_order", "serialNumber", "date"}
    missing = required - set(draws.columns)
    if missing:
        raise ValueError(f"Draw CSV missing columns: {sorted(missing)}")

    draws["event_order"] = pd.to_numeric(draws["event_order"], errors="raise").astype(np.int32)
    numbers["event_order"] = pd.to_numeric(numbers["event_order"], errors="raise").astype(np.int32)
    if draws["event_order"].duplicated().any():
        raise ValueError("Duplicate event_order in draw CSV.")
    draws = draws.sort_values("event_order").reset_index(drop=True)

    expected = np.arange(1, len(draws) + 1, dtype=np.int32)
    if not np.array_equal(draws["event_order"].to_numpy(), expected):
        raise ValueError("event_order must be consecutive, starting at 1.")

    numbers["number"] = numbers["number"].astype("string").str.strip().str.zfill(4)
    valid = numbers["number"].str.fullmatch(r"\d{4}", na=False)
    invalid_count = int((~valid).sum())
    numbers = numbers.loc[valid].copy()
    numbers["number_int"] = numbers["number"].astype(np.int32)
    if not numbers["number_int"].between(0, 9999).all():
        raise ValueError("Found a number outside 0000–9999.")

    known = set(draws["event_order"].astype(int))
    unknown = set(numbers["event_order"].astype(int)) - known
    if unknown:
        raise ValueError(f"Number CSV references {len(unknown)} unknown events.")
    if numbers.empty:
        raise ValueError("No valid number rows remain.")

    print(f"Draw events: {len(draws):,}")
    print(f"Valid number rows: {len(numbers):,}")
    print(f"Invalid number rows ignored: {invalid_count:,}")
    print(f"Date range: {draws.iloc[0]['date']} to {draws.iloc[-1]['date']}")
    return draws, numbers


def build_presence(draws: pd.DataFrame, numbers: pd.DataFrame) -> np.ndarray:
    """Binary event-by-number matrix; duplicate prize rows count only once."""
    presence = np.zeros((len(draws), 10000), dtype=np.uint8)
    rows = numbers["event_order"].to_numpy(dtype=np.int32) - 1
    cols = numbers["number_int"].to_numpy(dtype=np.int32)
    presence[rows, cols] = 1
    empty = np.flatnonzero(presence.sum(axis=1) == 0)
    if len(empty):
        raise ValueError(f"{len(empty)} events have no valid numbers; first indices: {empty[:10].tolist()}")
    return presence


def find_first_strict_lead(presence: np.ndarray, focus_idx: int) -> tuple[int | None, pd.DataFrame]:
    cumulative = np.zeros(10000, dtype=np.int32)
    rows = []
    first_lead = None
    for i, event in enumerate(presence):
        cumulative += event
        focus_hits = int(cumulative[focus_idx])
        highest_other = int(np.max(np.delete(cumulative, focus_idx)))
        is_leader = focus_hits > highest_other
        rows.append({
            "event_index_zero_based": i,
            "event_order": i + 1,
            "focus_cumulative_hits": focus_hits,
            "highest_other_cumulative_hits": highest_other,
            "strict_lead": is_leader,
        })
        if first_lead is None and is_leader:
            first_lead = i
    return first_lead, pd.DataFrame(rows)


def next_window_counts(presence: np.ndarray, event_indices: list[int], horizon: int) -> tuple[np.ndarray, int]:
    """Count hits in the next H draws; return counts and number of draw opportunities."""
    counts = np.zeros(10000, dtype=np.int64)
    opportunities = 0
    for i in event_indices:
        start, end = i + 1, min(i + 1 + horizon, len(presence))
        if start < end:
            counts += presence[start:end].sum(axis=0, dtype=np.int64)
            opportunities += end - start
    return counts, opportunities


def make_rate_table(presence: np.ndarray, anchors: list[int], controls: list[int], horizon: int) -> pd.DataFrame:
    anchor_counts, anchor_opps = next_window_counts(presence, anchors, horizon)
    control_counts, control_opps = next_window_counts(presence, controls, horizon)

    anchor_same = presence[anchors].sum(axis=0) if anchors else np.zeros(10000, dtype=np.int64)
    control_same = presence[controls].sum(axis=0) if controls else np.zeros(10000, dtype=np.int64)
    anchor_rate = anchor_counts / max(anchor_opps, 1)
    control_rate = control_counts / max(control_opps, 1)

    df = pd.DataFrame({
        "number": [f"{n:04d}" for n in range(10000)],
        "same_draw_rate_with_7396": anchor_same / max(len(anchors), 1),
        "same_draw_rate_without_7396": control_same / max(len(controls), 1),
        "same_draw_rate_difference": anchor_same / max(len(anchors), 1) - control_same / max(len(controls), 1),
        "future_hits_after_7396": anchor_counts,
        "future_hits_after_control": control_counts,
        "future_draw_opportunities_after_7396": anchor_opps,
        "future_draw_opportunities_after_control": control_opps,
        "future_rate_after_7396": anchor_rate,
        "future_rate_after_control": control_rate,
        "future_rate_difference": anchor_rate - control_rate,
        "future_rate_ratio": np.divide(anchor_rate, control_rate, out=np.zeros(10000), where=control_rate > 0),
        "anchor_events": len(anchors),
        "control_events": len(controls),
        "horizon": horizon,
    })
    df = df[df["number"] != FOCUS].copy()
    df = df.sort_values(
        ["future_rate_difference", "same_draw_rate_difference", "number"],
        ascending=[False, False, True], kind="stable",
    ).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def forward_test(presence: np.ndarray, post_lead: list[int], horizon: int) -> pd.DataFrame:
    """Expanding-origin test. Training windows end before test anchor; test windows don't overlap."""
    focus_idx = int(FOCUS)
    anchors = [i for i in post_lead if presence[i, focus_idx]]
    controls = [i for i in post_lead if not presence[i, focus_idx]]
    rows = []
    last_test_end = -1

    for test_i in anchors:
        future_start, future_end = test_i + 1, test_i + horizon
        if future_end >= len(presence) or test_i <= last_test_end:
            continue

        train_anchors = [i for i in anchors if i + horizon < test_i]
        train_controls = [i for i in controls if i + horizon < test_i]
        if len(train_anchors) < MIN_TRAIN_ANCHORS or len(train_controls) < MIN_TRAIN_CONTROLS:
            continue

        a_counts, a_opps = next_window_counts(presence, train_anchors, horizon)
        c_counts, c_opps = next_window_counts(presence, train_controls, horizon)
        score = a_counts / max(a_opps, 1) - c_counts / max(c_opps, 1)
        score[focus_idx] = -np.inf
        chaser_ids = np.argsort(-score, kind="stable")[:TOP_K]

        historical = presence[:test_i].sum(axis=0, dtype=np.int64)
        historical[focus_idx] = -1
        frequency_ids = np.argsort(-historical, kind="stable")[:TOP_K]

        future = presence[future_start:future_end + 1]
        actual_slots = int(future.sum())
        chaser_hits = int(future[:, chaser_ids].sum())
        frequency_hits = int(future[:, frequency_ids].sum())
        random_expected = safe_rate(TOP_K, 10000) * actual_slots

        rows.append({
            "horizon": horizon,
            "test_anchor_event_order": test_i + 1,
            "training_anchor_count": len(train_anchors),
            "training_control_count": len(train_controls),
            "top_k": TOP_K,
            "future_draws_tested": len(future),
            "actual_number_draw_hits": actual_slots,
            "event_aligned_chaser_hits": chaser_hits,
            "historical_frequency_hits": frequency_hits,
            "random_expected_hits": random_expected,
            "chasers_minus_frequency": chaser_hits - frequency_hits,
            "chasers_minus_random_expected": chaser_hits - random_expected,
        })
        last_test_end = future_end
    return pd.DataFrame(rows)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    draws, numbers = load_data()
    presence = build_presence(draws, numbers)
    focus_idx = int(FOCUS)

    lead_i, timeline = find_first_strict_lead(presence, focus_idx)
    timeline["date"] = draws["date"].astype(str).to_numpy()
    timeline.to_csv(RESULTS_DIR / "ai_7396_leader_timeline_v2.csv", index=False)
    if lead_i is None:
        raise RuntimeError(f"{FOCUS} never strictly led all other numbers cumulatively.")

    post_lead = list(range(lead_i + 1, len(presence)))
    anchors = [i for i in post_lead if presence[i, focus_idx] == 1]
    controls = [i for i in post_lead if presence[i, focus_idx] == 0]
    lead_date = str(draws.iloc[lead_i]["date"])
    lead_hits = int(timeline.iloc[lead_i]["focus_cumulative_hits"])
    competitor_hits = int(timeline.iloc[lead_i]["highest_other_cumulative_hits"])

    print("\nFIRST STRICT CUMULATIVE LEAD")
    print(f"Number: {FOCUS} | Event order: {lead_i + 1} | Date: {lead_date}")
    print(f"Cumulative hits: {lead_hits} | Highest competitor: {competitor_hits}")
    print(f"Post-lead anchor events: {len(anchors)} | control events: {len(controls)}")

    horizon_summary = []
    for horizon in HORIZONS:
        # Use only anchors/controls with a complete H-draw future window.
        usable_anchors = [i for i in anchors if i + horizon < len(presence)]
        usable_controls = [i for i in controls if i + horizon < len(presence)]
        table = make_rate_table(presence, usable_anchors, usable_controls, horizon)
        out_path = RESULTS_DIR / f"ai_7396_chaser_candidates_next_{horizon}_v2.csv"
        table.to_csv(out_path, index=False)

        top = table.iloc[0] if len(table) else None
        horizon_summary.append({
            "horizon": horizon,
            "usable_anchor_events": len(usable_anchors),
            "usable_control_events": len(usable_controls),
            "top_candidate": str(top["number"]) if top is not None else "",
            "top_candidate_rate_difference": float(top["future_rate_difference"]) if top is not None else 0.0,
            "top_candidate_anchor_rate": float(top["future_rate_after_7396"]) if top is not None else 0.0,
            "top_candidate_control_rate": float(top["future_rate_after_control"]) if top is not None else 0.0,
            "caution": "Descriptive windows may overlap; use chronological forward-test results for validation.",
        })
        print(f"\nTop 10 candidates: next {horizon} draw(s)")
        cols = ["rank", "number", "same_draw_rate_with_7396", "same_draw_rate_without_7396",
                "future_rate_after_7396", "future_rate_after_control", "future_rate_difference"]
        print(table[cols].head(10).to_string(index=False))
        print(f"Saved: {out_path}")

    pd.DataFrame(horizon_summary).to_csv(RESULTS_DIR / "ai_7396_chaser_horizon_summary_v2.csv", index=False)

    tests = []
    for horizon in HORIZONS:
        part = forward_test(presence, post_lead, horizon)
        if not part.empty:
            part["test_anchor_date"] = part["test_anchor_event_order"].map(
                lambda order: str(draws.iloc[int(order) - 1]["date"])
            )
            tests.append(part)
    forward = pd.concat(tests, ignore_index=True) if tests else pd.DataFrame()
    forward.to_csv(RESULTS_DIR / "ai_7396_chaser_forward_test_v2.csv", index=False)

    if not forward.empty:
        forward_summary = forward.groupby("horizon", as_index=False).agg(
            test_periods=("test_anchor_event_order", "count"),
            mean_chaser_hits=("event_aligned_chaser_hits", "mean"),
            mean_frequency_hits=("historical_frequency_hits", "mean"),
            mean_random_expected_hits=("random_expected_hits", "mean"),
            mean_chaser_minus_frequency=("chasers_minus_frequency", "mean"),
            mean_chaser_minus_random=("chasers_minus_random_expected", "mean"),
        )
    else:
        forward_summary = pd.DataFrame(columns=[
            "horizon", "test_periods", "mean_chaser_hits", "mean_frequency_hits",
            "mean_random_expected_hits", "mean_chaser_minus_frequency", "mean_chaser_minus_random",
        ])
    forward_summary.to_csv(RESULTS_DIR / "ai_7396_chaser_forward_summary_v2.csv", index=False)

    metadata = {
        "focus_number": FOCUS,
        "first_strict_lead_event_order": lead_i + 1,
        "first_strict_lead_date": lead_date,
        "focus_cumulative_hits_at_lead": lead_hits,
        "highest_other_cumulative_hits_at_lead": competitor_hits,
        "draw_events": len(draws),
        "post_lead_events": len(post_lead),
        "post_lead_anchor_events": len(anchors),
        "post_lead_control_events": len(controls),
        "horizons": HORIZONS,
        "top_k": TOP_K,
        "minimum_training_anchors": MIN_TRAIN_ANCHORS,
        "minimum_training_controls": MIN_TRAIN_CONTROLS,
        "method_note": "Descriptive anchor/control windows can overlap. Forward-test periods do not overlap, and training windows must end before the test anchor.",
        "warning": "Exploratory association only; this cannot establish causation or guarantee future lottery results.",
    }
    (RESULTS_DIR / "ai_7396_chaser_metadata_v2.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    print("\nCHRONOLOGICAL FORWARD-TEST SUMMARY")
    if forward_summary.empty:
        print("No eligible periods. There may not be enough prior anchors and controls under the strict rules.")
    else:
        print(forward_summary.to_string(index=False))
    print(f"\nAnalysis complete. Results: {RESULTS_DIR}")
    print("Source CSVs and database records were not modified.")


if __name__ == "__main__":
    main()
