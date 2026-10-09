import json
import calendar
import numpy as np
import pandas as pd
from pymongo import MongoClient
from tqdm.auto import tqdm

# ============================================================
# CONFIG
# ============================================================

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "absolute_data"

OUTPUT_FILE = "absolute_data_number_patterns.csv"

# True = highest total_hits first
SORT_DESC = True

# We want the complete 0000-9999 universe.
ALL_NUMBERS = [f"{i:04d}" for i in range(10000)]

# Fixed calendar ordering.
WEEKDAY_NUMBERS = list(range(7))       # Monday = 0 ... Sunday = 6
MONTH_NUMBERS = list(range(1, 13))     # January = 1 ... December = 12


# ============================================================
# MONGODB
# ============================================================

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]


# ============================================================
# FETCH DATA
# ============================================================

def get_all_numbers():
    """
    Fetch every number occurrence from absolute_data.

    Each row represents one number/prize occurrence from a
    series inside a draw document.
    """

    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},

        {
            "$project": {
                "number": "$series.numbers.number",
                "prize": "$series.prize",

                # Preserve existing semantics:
                # if count is missing, treat it as 1.
                "count": {
                    "$ifNull": [
                        "$series.numbers.count",
                        1
                    ]
                },

                "drawDate": "$drawDate",
                "date": "$date",
            }
        }
    ]

    return lottery_data.aggregate(
        pipeline,
        allowDiskUse=True
    )


# ============================================================
# HELPERS
# ============================================================

def clean_number(value):
    """
    Normalize lottery number to exactly four digits.
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    # Handle values such as 123.0 that may appear after
    # dataframe conversion.
    if value.endswith(".0"):
        value = value[:-2]

    if not value.isdigit():
        return None

    return value.zfill(4)


def parse_dates(df):
    """
    Prefer native drawDate.
    Fall back to DD/MM/YYYY string stored in date.
    """

    # First try drawDate.
    parsed = pd.to_datetime(
        df["drawDate"],
        errors="coerce"
    )

    # Fall back to the existing date field.
    missing = parsed.isna()

    if missing.any():
        fallback = pd.to_datetime(
            df.loc[missing, "date"],
            errors="coerce",
            format="%d/%m/%Y"
        )

        parsed.loc[missing] = fallback

    return parsed


def json_compact(value):
    """
    Deterministic compact JSON representation.
    """

    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":")
    )


# ============================================================
# LOAD
# ============================================================

print("=" * 60)
print("ABSOLUTE DATA NUMBER PATTERN GENERATOR")
print("=" * 60)

print(f"\n🔄 Fetching records from '{COLLECTION}' collection...")

rows = list(get_all_numbers())

print(f"📊 Total records fetched: {len(rows)}")

if not rows:
    print("⚠️ No data returned. Exiting.")
    raise SystemExit


df = pd.DataFrame(rows)


# ============================================================
# NORMALIZE CORE FIELDS
# ============================================================

print("🔧 Normalizing fields...")

df["number"] = df["number"].apply(clean_number)

# Remove invalid numbers.
invalid_numbers = int(df["number"].isna().sum())

if invalid_numbers:
    print(
        f"⚠️ Removing {invalid_numbers} records "
        f"with invalid lottery numbers."
    )

df = df.dropna(subset=["number"]).copy()


# Count
df["count"] = pd.to_numeric(
    df.get("count", 1),
    errors="coerce"
).fillna(1).astype(int)

# Prize
df["prize"] = pd.to_numeric(
    df.get("prize"),
    errors="coerce"
).fillna(0).astype(int)


# ============================================================
# PARSE DATES
# ============================================================

print("📅 Parsing draw dates...")

df["date_parsed"] = parse_dates(df)

bad_dates = int(df["date_parsed"].isna().sum())

if bad_dates:
    print(
        f"⚠️ {bad_dates} records have unparseable dates."
    )

df_valid = df.dropna(
    subset=["date_parsed"]
).copy()

df_valid["date_parsed"] = pd.to_datetime(
    df_valid["date_parsed"]
)


# ============================================================
# GLOBAL METRICS
# ============================================================

latest_overall_date = df_valid["date_parsed"].max()

counts_by_number = (
    df.groupby("number")["count"]
    .sum()
)

MAX_COUNT = (
    int(counts_by_number.max())
    if not counts_by_number.empty
    else 0
)

print(
    f"🎯 MAX_COUNT (weighted by count) = {MAX_COUNT}"
)

print(
    "📅 Most recent draw date: "
    + (
        latest_overall_date.strftime("%Y-%m-%d")
        if pd.notna(latest_overall_date)
        else "N/A"
    )
)


# ============================================================
# SORT FOR DETERMINISTIC PROCESSING
# ============================================================

df_valid = df_valid.sort_values(
    ["number", "date_parsed", "prize"]
)


# ============================================================
# GROUP SUMMARY
# ============================================================

tqdm.pandas()


def summarize_group(g: pd.DataFrame) -> pd.Series:

    # --------------------------------------------------------
    # UNIQUE DRAW DAYS
    # --------------------------------------------------------

    unique_days = (
        g["date_parsed"]
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
    )

    # --------------------------------------------------------
    # GAP CALCULATIONS
    # --------------------------------------------------------

    gaps = (
        unique_days
        .diff()
        .dt.days
        .dropna()
    )

    if not gaps.empty:

        avg_gap = round(
            float(gaps.mean()),
            4
        )

        min_gap = int(
            gaps.min()
        )

        max_gap = int(
            gaps.max()
        )

    else:

        avg_gap = np.nan
        min_gap = np.nan
        max_gap = np.nan

    # --------------------------------------------------------
    # LAST / FIRST SEEN
    # --------------------------------------------------------

    first_seen_date = (
        unique_days.min()
        if not unique_days.empty
        else pd.NaT
    )

    last_seen_date = (
        unique_days.max()
        if not unique_days.empty
        else pd.NaT
    )

    if (
        pd.notna(latest_overall_date)
        and pd.notna(last_seen_date)
    ):
        days_since_last = int(
            (latest_overall_date - last_seen_date).days
        )
    else:
        days_since_last = np.nan

    # --------------------------------------------------------
    # WEEKDAY COUNTS
    #
    # ALWAYS output all 7 weekdays.
    # Missing weekdays = 0.
    # --------------------------------------------------------

    weekday_counts_series = (
        g.assign(
            weekday=g["date_parsed"].dt.weekday
        )
        .groupby("weekday")["count"]
        .sum()
        .reindex(
            WEEKDAY_NUMBERS,
            fill_value=0
        )
    )

    weekday_counts = {
        str(day): int(
            weekday_counts_series.get(day, 0)
        )
        for day in WEEKDAY_NUMBERS
    }

    # --------------------------------------------------------
    # MONTH COUNTS
    #
    # ALWAYS output all 12 months.
    # Missing months = 0.
    #
    # IMPORTANT:
    # Numeric month keys are used intentionally.
    # 1 = January
    # 2 = February
    # ...
    # 12 = December
    # --------------------------------------------------------

    month_counts_series = (
        g.assign(
            month=g["date_parsed"].dt.month
        )
        .groupby("month")["count"]
        .sum()
        .reindex(
            MONTH_NUMBERS,
            fill_value=0
        )
    )

    month_counts = {
        str(month): int(
            month_counts_series.get(month, 0)
        )
        for month in MONTH_NUMBERS
    }

    # --------------------------------------------------------
    # PRIZE BREAKDOWN
    # --------------------------------------------------------

    prize_counts_series = (
        g.groupby("prize")["count"]
        .sum()
        .sort_index()
    )

    prize_counts = {
        str(int(prize)): int(count)
        for prize, count
        in prize_counts_series.items()
    }

    # --------------------------------------------------------
    # DATES
    #
    # Keep existing pipe-separated representation.
    # --------------------------------------------------------

    dates_string = "|".join(
        unique_days.dt.strftime(
            "%d/%m/%Y"
        )
    )

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return pd.Series({

        "last_seen_date":
            (
                last_seen_date.strftime("%d/%m/%Y")
                if pd.notna(last_seen_date)
                else ""
            ),

        "days_since_last_hit":
            days_since_last,

        "avg_gap_days":
            avg_gap,

        "min_gap_days":
            min_gap,

        "max_gap_days":
            max_gap,

        "dates":
            dates_string,

        "prize_breakdown":
            json_compact(prize_counts),

        "weekday_counts":
            json_compact(weekday_counts),

        "month_counts":
            json_compact(month_counts),
    })


# ============================================================
# RUN GROUP AGGREGATION
# ============================================================

print("\n📊 Building number summaries...")

time_summary = (
    df_valid
    .groupby("number")[
        ["date_parsed", "count", "prize"]
    ]
    .progress_apply(
        summarize_group,
        include_groups=False
    )
    .reset_index()
)


# ============================================================
# MERGE TOTAL HITS
# ============================================================

out_df = (
    counts_by_number
    .rename("total_hits")
    .reset_index()
    .merge(
        time_summary,
        on="number",
        how="left"
    )
)


# ============================================================
# GUARANTEE 0000-9999
# ============================================================

print("\n🔢 Ensuring complete 0000-9999 number universe...")

all_numbers_df = pd.DataFrame({
    "number": ALL_NUMBERS
})

out_df = (
    all_numbers_df
    .merge(
        out_df,
        on="number",
        how="left"
    )
)


# ============================================================
# DEFAULT VALUES FOR NEVER-SEEN NUMBERS
# ============================================================

out_df["total_hits"] = (
    pd.to_numeric(
        out_df["total_hits"],
        errors="coerce"
    )
    .fillna(0)
    .astype(int)
)


out_df["remaining_to_max"] = (
    MAX_COUNT
    - out_df["total_hits"]
).clip(
    lower=0
).astype(int)


out_df["dates"] = (
    out_df["dates"]
    .fillna("")
)


out_df["prize_breakdown"] = (
    out_df["prize_breakdown"]
    .fillna("{}")
)


# For never-seen numbers, preserve the same
# complete calendar structure.

empty_weekday_counts = {
    str(day): 0
    for day in WEEKDAY_NUMBERS
}

empty_month_counts = {
    str(month): 0
    for month in MONTH_NUMBERS
}


out_df["weekday_counts"] = (
    out_df["weekday_counts"]
    .fillna(
        json_compact(empty_weekday_counts)
    )
)


out_df["month_counts"] = (
    out_df["month_counts"]
    .fillna(
        json_compact(empty_month_counts)
    )
)


# ============================================================
# NUMERIC CLEANUP
# ============================================================

for column in [
    "days_since_last_hit",
    "avg_gap_days",
    "min_gap_days",
    "max_gap_days",
]:

    out_df[column] = pd.to_numeric(
        out_df[column],
        errors="coerce"
    )


# avg gap is deliberately limited to 4 decimals.
out_df["avg_gap_days"] = (
    out_df["avg_gap_days"]
    .round(4)
)


# ============================================================
# DIGIT FEATURES
# ============================================================

print("🔢 Building digit features...")

out_df["d1"] = (
    out_df["number"]
    .str[0]
    .astype(int)
)

out_df["d2"] = (
    out_df["number"]
    .str[1]
    .astype(int)
)

out_df["d3"] = (
    out_df["number"]
    .str[2]
    .astype(int)
)

out_df["d4"] = (
    out_df["number"]
    .str[3]
    .astype(int)
)

out_df["digit_sum"] = (
    out_df["d1"]
    + out_df["d2"]
    + out_df["d3"]
    + out_df["d4"]
)

out_df["even_digit_count"] = (
    out_df[
        ["d1", "d2", "d3", "d4"]
    ]
    .apply(
        lambda row:
            sum(
                1
                for d in row
                if d % 2 == 0
            ),
        axis=1
    )
)


# ============================================================
# COLUMN ORDER
# ============================================================

columns = [
    "number",
    "total_hits",
    "last_seen_date",
    "days_since_last_hit",
    "avg_gap_days",
    "min_gap_days",
    "max_gap_days",
    "dates",
    "prize_breakdown",
    "weekday_counts",
    "month_counts",
    "d1",
    "d2",
    "d3",
    "d4",
    "digit_sum",
    "even_digit_count",
    "remaining_to_max",
]

out_df = out_df[columns]


# ============================================================
# SORT
# ============================================================

out_df = out_df.sort_values(
    by=[
        "total_hits",
        "days_since_last_hit",
        "number"
    ],
    ascending=[
        not SORT_DESC,
        True,
        True
    ],
    na_position="last"
)


# ============================================================
# FINAL VALIDATION
# ============================================================

print("\n🔍 Final validation...")

print(
    f"Number of output rows: {len(out_df)}"
)

print(
    f"Unique numbers: {out_df['number'].nunique()}"
)

missing_numbers = sorted(
    set(ALL_NUMBERS)
    - set(out_df["number"])
)

if missing_numbers:

    print(
        f"❌ Missing numbers: {len(missing_numbers)}"
    )

    print(
        missing_numbers[:20]
    )

    raise RuntimeError(
        "Output does not contain complete 0000-9999 universe."
    )

else:

    print(
        "✅ All 0000-9999 numbers present."
    )


# Check month structure.
bad_month_rows = 0

for value in out_df["month_counts"]:

    try:

        obj = json.loads(value)

        if set(obj.keys()) != {
            str(i)
            for i in range(1, 13)
        }:

            bad_month_rows += 1

    except Exception:

        bad_month_rows += 1


print(
    f"Month structure errors: {bad_month_rows}"
)

if bad_month_rows:
    raise RuntimeError(
        "Some month_counts rows do not contain all 12 months."
    )


# ============================================================
# EXPORT
# ============================================================

print(
    f"\n💾 Writing: {OUTPUT_FILE}"
)

out_df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8"
)


print("\n" + "=" * 60)
print("✅ SUCCESS")
print("=" * 60)

print(
    f"Rows written: {len(out_df)}"
)

print(
    f"Numbers: {out_df['number'].iloc[0]} ... "
    f"{out_df['number'].iloc[-1]}"
)

print(
    f"Output: {OUTPUT_FILE}"
)

client.close()