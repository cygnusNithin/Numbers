
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ai-training"
OUT = DATA / "results"
OUT.mkdir(parents=True, exist_ok=True)

DRAWS_FILE = DATA / "ai_training_draws.csv"
NUMBERS_FILE = DATA / "ai_training_draw_numbers.csv"
MIN_HISTORY = 50
PERIOD_NAMES = ["Period 1", "Period 2", "Period 3", "Period 4"]


def col(df, names, required=True):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    if required:
        raise ValueError(
            f"Missing one of {names}. Available columns: {list(df.columns)}"
        )
    return None


def normalize_key(series):
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


print("Loading exported CSVs...")
draws = pd.read_csv(DRAWS_FILE, dtype=str)
rows = pd.read_csv(NUMBERS_FILE, dtype=str)

# These are the real columns shown in your error.
order_col = col(draws, ["event_order"], required=False)
serial_col = col(draws, ["serialNumber", "serial_number"], required=False)
date_col = col(draws, ["drawDate", "date", "draw_date"], required=False)

number_order_col = col(rows, ["event_order"], required=False)
number_serial_col = col(rows, ["serialNumber", "serial_number"], required=False)

# Prefer a unique key present in BOTH CSVs.
join_pairs = []
if serial_col and number_serial_col:
    join_pairs.append((serial_col, number_serial_col, "serialNumber"))
if order_col and number_order_col:
    join_pairs.append((order_col, number_order_col, "event_order"))

join_key = None
for left, right, label in join_pairs:
    test = normalize_key(draws[left])
    valid = test.notna() & test.ne("") & test.ne("nan")
    if valid.sum() and test[valid].nunique() == valid.sum():
        join_key = (left, right, label)
        break

if join_key is None:
    raise ValueError(
        "Could not find a shared unique event key.\n"
        f"Draw CSV columns: {list(draws.columns)}\n"
        f"Number CSV columns: {list(rows.columns)}\n"
        "Do not guess a join using date alone; multiple draws may share a date."
    )

left_key, right_key, key_name = join_key
print(f"Joining CSVs using {key_name}...")

draws["_key"] = normalize_key(draws[left_key])
rows["_key"] = normalize_key(rows[right_key])

draws = draws[draws["_key"].ne("") & draws["_key"].ne("nan")].copy()
draws = draws.drop_duplicates("_key", keep="first")

if order_col:
    draws["_sort"] = pd.to_numeric(draws[order_col], errors="coerce")
elif serial_col:
    draws["_sort"] = pd.to_numeric(draws[serial_col], errors="coerce")
elif date_col:
    draws["_sort"] = pd.to_datetime(
        draws[date_col], dayfirst=True, errors="coerce"
    )
else:
    raise ValueError("No event ordering field found in draw CSV.")

draws = draws.dropna(subset=["_sort"]).sort_values(
    ["_sort", "_key"], kind="stable"
).reset_index(drop=True)

# Keep the event sequence and build a safe key-to-index mapping.
event_to_index = {
    key: i for i, key in enumerate(draws["_key"].tolist())
}
rows["_event_index"] = rows["_key"].map(event_to_index)
rows = rows.dropna(subset=["_event_index"]).copy()
rows["_event_index"] = rows["_event_index"].astype(int)

number_col = col(
    rows,
    ["number", "winning_number", "draw_number", "prize_number", "result_number"],
)

# Preserve leading zeros, e.g. 0047.
rows["_number"] = (
    rows[number_col].astype(str).str.strip()
    .str.replace(r"\.0$", "", regex=True)
    .str.zfill(4)
)
rows = rows[rows["_number"].str.fullmatch(r"\d{4}", na=False)].copy()

event_count = len(draws)
if event_count <= MIN_HISTORY:
    raise ValueError(f"Only {event_count} usable events found.")

print(f"Usable draw events: {event_count}")
print(f"Usable number rows: {len(rows)}")
print("Building presence matrix...")

presence = np.zeros((event_count, 10000), dtype=np.uint8)
presence[
    rows["_event_index"].to_numpy(),
    rows["_number"].astype(int).to_numpy()
] = 1

# Four chronological periods; event order is never shuffled.
bounds = np.linspace(0, event_count, 5, dtype=int)
period_id = np.minimum(
    np.searchsorted(bounds[1:], np.arange(event_count), side="right"), 3
)

# Buckets for each candidate number, based only on prior events.
total_hits = np.zeros(10000, dtype=np.int32)
last_seen = np.full(10000, -1, dtype=np.int32)
raw_records = []

print("Evaluating each event using history available before that event...")

for t in range(event_count):
    if t >= MIN_HISTORY:
        period = PERIOD_NAMES[int(period_id[t])]
        recent_start = max(0, t - 10)
        recent_hits = presence[recent_start:t].sum(axis=0)

        gaps = np.where(last_seen >= 0, t - last_seen, -1)

        feature_buckets = {
            "hits_last_10": np.select(
                [recent_hits == 0, recent_hits == 1, recent_hits == 2],
                ["0 hits", "1 hit", "2 hits"],
                default="3+ hits",
            ),
            "prior_total_hits": np.select(
                [
                    total_hits == 0,
                    total_hits == 1,
                    total_hits <= 5,
                    total_hits <= 10,
                ],
                ["0 prior hits", "1 prior hit", "2-5 prior hits",
                 "6-10 prior hits"],
                default="11+ prior hits",
            ),
            "events_since_last_hit": np.select(
                [
                    gaps < 0, gaps <= 5, gaps <= 10,
                    gaps <= 25, gaps <= 50, gaps <= 100,
                ],
                ["Never appeared", "1-5", "6-10", "11-25",
                 "26-50", "51-100"],
                default="101+",
            ),
        }

        target = presence[t].astype(bool)

        for feature, buckets in feature_buckets.items():
            for bucket in np.unique(buckets):
                mask = buckets == bucket
                raw_records.append({
                    "period": period,
                    "event_index": t,
                    "feature": feature,
                    "bucket": str(bucket),
                    "opportunities": int(mask.sum()),
                    "hits": int(target[mask].sum()),
                })

    # Update only after scoring this event, preventing future leakage.
    appeared = presence[t].astype(bool)
    total_hits += presence[t]
    last_seen[appeared] = t

    if (t + 1) % 200 == 0:
        print(f"Processed {t + 1}/{event_count}")

raw = pd.DataFrame(raw_records)
raw.to_csv(OUT / "ai_pattern_stability_raw.csv", index=False)

summary = (
    raw.groupby(["period", "feature", "bucket"], as_index=False)
    [["opportunities", "hits"]].sum()
)

# Calculate one correct baseline per period, not by summing feature groups.
baseline_records = []
for p, name in enumerate(PERIOD_NAMES):
    event_ids = np.where((np.arange(event_count) >= bounds[p]) &
                         (np.arange(event_count) < bounds[p + 1]))[0]
    event_ids = event_ids[event_ids >= MIN_HISTORY]

    if len(event_ids):
        hit_count = int(presence[event_ids].sum())
        opportunities = int(len(event_ids) * 10000)
        baseline_records.append({
            "period": name,
            "target_events": len(event_ids),
            "baseline_hits": hit_count,
            "baseline_opportunities": opportunities,
            "baseline": hit_count / opportunities,
        })

baselines = pd.DataFrame(baseline_records)
summary = summary.merge(baselines[["period", "baseline"]], on="period")
summary["hit_rate"] = summary["hits"] / summary["opportunities"]
summary["lift_vs_period_baseline"] = (
    summary["hit_rate"] / summary["baseline"]
)

# Approximate two-sided test. Treat as exploratory because outcomes can
# be dependent within a draw and repeated tests require careful interpretation.
def approximate_p(row):
    n = int(row["opportunities"])
    p0 = float(row["baseline"])
    observed = float(row["hit_rate"])
    if n <= 0 or p0 <= 0 or p0 >= 1:
        return np.nan
    se = np.sqrt(p0 * (1 - p0) / n)
    return float(2 * norm.sf(abs((observed - p0) / se)))

summary["p_value_approx"] = summary.apply(approximate_p, axis=1)

# Benjamini-Hochberg adjustment across all reported bucket-period tests.
valid = summary["p_value_approx"].notna()
pvals = summary.loc[valid, "p_value_approx"].to_numpy()
m = len(pvals)
if m:
    order = np.argsort(pvals)
    ranked = pvals[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty(m)
    adjusted[order] = np.minimum(ranked, 1.0)
    summary["p_value_BH"] = np.nan
    summary.loc[valid, "p_value_BH"] = adjusted
else:
    summary["p_value_BH"] = np.nan

summary.to_csv(OUT / "ai_pattern_stability_summary.csv", index=False)

wide = summary.pivot_table(
    index=["feature", "bucket"],
    columns="period",
    values="lift_vs_period_baseline",
    aggfunc="first",
).reset_index()
wide.columns.name = None

for name in PERIOD_NAMES:
    if name not in wide.columns:
        wide[name] = np.nan

wide["periods_above_baseline"] = wide[PERIOD_NAMES].gt(1.0).sum(axis=1)
wide["minimum_period_lift"] = wide[PERIOD_NAMES].min(axis=1)
wide["maximum_period_lift"] = wide[PERIOD_NAMES].max(axis=1)
wide = wide.sort_values(
    ["periods_above_baseline", "minimum_period_lift"],
    ascending=[False, False],
)
wide.to_csv(OUT / "ai_pattern_stability_comparison.csv", index=False)

metadata = {
    "events": int(event_count),
    "join_key": key_name,
    "minimum_history": MIN_HISTORY,
    "period_boundaries": bounds.tolist(),
    "baseline_by_period": baselines.to_dict(orient="records"),
    "note": (
        "Exploratory associations, not proof of predictive edge. "
        "Approximate p-values may overstate evidence because numbers and "
        "events are not necessarily independent."
    ),
}
(OUT / "ai_pattern_stability_metadata.json").write_text(
    json.dumps(metadata, indent=2, default=str),
    encoding="utf-8",
)

print("\nPATTERN STABILITY ANALYSIS COMPLETE")
print("\nLift comparison: values above 1.0 exceed that period's baseline")
print(wide.to_string(index=False))
print("\nFiles created:")
for name in [
    "ai_pattern_stability_raw.csv",
    "ai_pattern_stability_summary.csv",
    "ai_pattern_stability_comparison.csv",
    "ai_pattern_stability_metadata.json",
]:
    print(OUT / name)
