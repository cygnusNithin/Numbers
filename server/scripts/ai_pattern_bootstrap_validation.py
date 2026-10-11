
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "ai-training" / "results"
INPUT = RESULTS / "ai_pattern_stability_raw.csv"

BOOTSTRAPS = 2000
SEED = 42
MIN_OPPORTUNITIES = 1000

rng = np.random.default_rng(SEED)


def main():
    raw = pd.read_csv(INPUT)

    required = {
        "period", "event_index", "feature", "bucket",
        "opportunities", "hits",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    raw["opportunities"] = pd.to_numeric(
        raw["opportunities"], errors="raise"
    )
    raw["hits"] = pd.to_numeric(raw["hits"], errors="raise")

    if (raw["hits"] < 0).any() or (
        raw["hits"] > raw["opportunities"]
    ).any():
        raise ValueError("Invalid hits/opportunities values.")

    # Each event's baseline is calculated across all buckets of
    # the same feature. Resampling is performed by event, not row.
    baseline = (
        raw.groupby(
            ["period", "feature", "event_index"], as_index=False
        )
        .agg(
            baseline_hits=("hits", "sum"),
            baseline_opportunities=("opportunities", "sum"),
        )
    )

    records = []

    for (period, feature), base_group in baseline.groupby(
        ["period", "feature"], sort=False
    ):
        base_group = base_group.reset_index(drop=True)

        event_base_hits = base_group["baseline_hits"].to_numpy(
            dtype=float
        )
        event_base_opp = base_group[
            "baseline_opportunities"
        ].to_numpy(dtype=float)

        valid = event_base_opp > 0
        base_group = base_group.loc[valid].reset_index(drop=True)
        event_base_hits = event_base_hits[valid]
        event_base_opp = event_base_opp[valid]

        if len(base_group) < 10:
            continue

        baseline_rate = event_base_hits.sum() / event_base_opp.sum()

        feature_rows = raw[
            (raw["period"] == period)
            & (raw["feature"] == feature)
        ]

        for bucket, bucket_group in feature_rows.groupby(
            "bucket", sort=False
        ):
            by_event = (
                bucket_group.groupby("event_index")
                .agg(
                    hits=("hits", "sum"),
                    opportunities=("opportunities", "sum"),
                )
            )

            # Align every event, including events where this bucket
            # had zero eligible candidates.
            aligned = (
                base_group[["event_index"]]
                .merge(
                    by_event,
                    left_on="event_index",
                    right_index=True,
                    how="left",
                )
                .fillna({"hits": 0, "opportunities": 0})
            )

            h = aligned["hits"].to_numpy(dtype=float)
            o = aligned["opportunities"].to_numpy(dtype=float)

            total_hits = h.sum()
            total_opp = o.sum()

            if total_opp < MIN_OPPORTUNITIES or baseline_rate <= 0:
                continue

            observed_rate = total_hits / total_opp
            observed_lift = observed_rate / baseline_rate

            # Cluster bootstrap: sample entire draw events.
            n = len(aligned)
            lifts = []

            for _ in range(BOOTSTRAPS):
                idx = rng.integers(0, n, size=n)

                sampled_opp = o[idx].sum()
                sampled_base_opp = event_base_opp[idx].sum()

                if sampled_opp == 0 or sampled_base_opp == 0:
                    continue

                bucket_rate = h[idx].sum() / sampled_opp
                sampled_baseline = (
                    event_base_hits[idx].sum() / sampled_base_opp
                )

                if sampled_baseline > 0:
                    lifts.append(bucket_rate / sampled_baseline)

            if not lifts:
                continue

            low, high = np.percentile(lifts, [2.5, 97.5])

            records.append({
                "period": period,
                "feature": feature,
                "bucket": bucket,
                "events": n,
                "opportunities": int(total_opp),
                "hits": int(total_hits),
                "baseline_rate": baseline_rate,
                "bucket_hit_rate": observed_rate,
                "observed_lift": observed_lift,
                "bootstrap_ci_low": low,
                "bootstrap_ci_high": high,
                "ci_excludes_1": bool(low > 1 or high < 1),
            })

    result = pd.DataFrame(records)

    if result.empty:
        raise RuntimeError(
            "No results produced. Check input values and thresholds."
        )

    result["ci_excludes_1"] = result["ci_excludes_1"].astype(bool)

    result = result.sort_values(
        ["feature", "bucket", "period"]
    )

    output = RESULTS / "ai_pattern_bootstrap_validation.csv"
    result.to_csv(output, index=False)

    print("\nBOOTSTRAP VALIDATION COMPLETE")
    print(f"Output: {output}")

    print("\nRows whose 95% bootstrap interval excludes lift = 1:")
    print(
        result[result["ci_excludes_1"]][
            [
                "period", "feature", "bucket", "events",
                "observed_lift", "bootstrap_ci_low",
                "bootstrap_ci_high",
            ]
        ].to_string(index=False)
    )

    print("\nFull results:")
    print(
        result[
            [
                "period", "feature", "bucket", "events",
                "opportunities", "observed_lift",
                "bootstrap_ci_low", "bootstrap_ci_high",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
