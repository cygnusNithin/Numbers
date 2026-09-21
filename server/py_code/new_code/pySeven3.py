import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm
import numpy as np

# ============================================
# CONFIG
# ============================================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

DATE_WINDOW_START = datetime(2020, 7, 11)
DATE_WINDOW_END   = datetime(2025, 11, 14)

OUTPUT_HYBRID = "hybrid_predictions_5000.csv"
OUTPUT_TRANSITIONS = "hybrid_transition_summary.csv"
OUTPUT_HISTORY = "hybrid_historical_metrics.csv"

PRIZE_ORDER = [100, 200, 500, 1000, 2000, 5000]

# ============================================
# PARSE DATE FUNCTION
# ============================================
def parse_date(d):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except:
            pass
    return None


# ============================================
# FETCH DB EVENTS
# ============================================
client = MongoClient(MONGO_URI)
col = client[DB_NAME][COLLECTION]

print("Fetching all prize events from MongoDB...")

events = []

for doc in col.find():
    dt = parse_date(doc.get("date", ""))
    if dt is None: 
        continue

    if not (DATE_WINDOW_START <= dt <= DATE_WINDOW_END):
        continue

    for s in doc.get("series", []):
        prize = s.get("prize")
        if prize not in PRIZE_ORDER:
            continue

        for n in s.get("numbers", []):
            number = str(n["number"]).zfill(4)
            events.append({
                "number": number,
                "date": dt,
                "prize": prize
            })

df = pd.DataFrame(events)
df.sort_values("date", inplace=True)
df.reset_index(drop=True, inplace=True)

print(f"Total events after filtering: {len(df)}")

# ============================================
# BUILD TIMELINE FOR EACH NUMBER
# ============================================
print("Building per-number timelines...")

number_groups = {n: g.sort_values("date") for n, g in df.groupby("number")}

# Flatten transitions
transition_rows = []

for num, g in tqdm(number_groups.items(), total=10000):
    g = g.sort_values("date")
    dates = list(g["date"])
    prizes = list(g["prize"])

    for i in range(1, len(prizes)):
        from_p = prizes[i - 1]
        to_p = prizes[i]
        delta = (dates[i] - dates[i - 1]).days

        transition_rows.append({
            "number": num,
            "from_prize": from_p,
            "to_prize": to_p,
            "gap_days": delta
        })

transitions = pd.DataFrame(transition_rows)
transitions.to_csv(OUTPUT_TRANSITIONS, index=False)

# ============================================
# TRANSITION PROBABILITY MODEL
# ============================================
print("Computing transition stats...")

transition_summary = transitions.groupby(
    ["from_prize", "to_prize"]
)["gap_days"].agg(["count", "mean", "median"]).reset_index()

transition_summary.to_csv("transition_probability_summary.csv", index=False)

# Normalize transition probabilities
transition_prob = (
    transition_summary
    .groupby("from_prize")["count"]
    .transform(lambda x: x / x.sum())
)
transition_summary["prob"] = transition_prob


# Helper: get transition probability
def get_transition_prob(frm, to):
    row = transition_summary[
        (transition_summary["from_prize"] == frm) &
        (transition_summary["to_prize"] == to)
    ]
    if row.empty:
        return 0
    return row["prob"].iloc[0]


# ============================================
# HISTORICAL PATTERN MODEL
# ============================================
print("Computing historical metrics...")

historical_metrics = []

for num, g in number_groups.items():
    first_5000 = g[g["prize"] == 5000]["date"]
    if len(first_5000) == 0:
        continue

    first_5000_date = first_5000.iloc[0]

    lower_hits = g[g["prize"] < 5000]
    maturity_gap = None
    if len(lower_hits) > 0:
        first_low = lower_hits["date"].min()
        maturity_gap = (first_5000_date - first_low).days

    # path detection
    prize_seq = list(g["prize"])
    path_tokens = set(prize_seq)

    follows_full_path = (
        100 in path_tokens and
        500 in path_tokens and
        1000 in path_tokens
    )

    fast_500_jump = (
        500 in path_tokens and
        (prize_seq[-1] != 5000)  # before hitting 5000
    )

    historical_metrics.append({
        "number": num,
        "maturity_gap": maturity_gap,
        "follows_path": follows_full_path,
        "fast_jump": fast_500_jump,
    })

hist_df = pd.DataFrame(historical_metrics)
hist_df.to_csv(OUTPUT_HISTORY, index=False)


# ============================================
# HYBRID PREDICTOR
# ============================================
print("Computing hybrid predictor scores...")

pred_rows = []

for num, g in number_groups.items():
    g = g.sort_values("date")
    last_date = g["date"].iloc[-1]
    days_since = (DATE_WINDOW_END - last_date).days

    prize_counts = g["prize"].value_counts().to_dict()

    # Transition score
    trans_score = 0
    for i in range(1, len(g)):
        frm = g.iloc[i-1]["prize"]
        to = g.iloc[i]["prize"]
        trans_score += get_transition_prob(frm, to) * 50

    # Historical metrics
    hist = hist_df[hist_df["number"] == num]
    maturity_score = 0
    path_bonus = 0

    if not hist.empty:
        mg = hist["maturity_gap"].iloc[0]
        if mg is not None:
            if 28 <= mg <= 60: maturity_score += 20
            elif 10 <= mg < 28: maturity_score += 10
            elif mg > 120: maturity_score -= 20

        if hist["follows_path"].iloc[0]:
            path_bonus += 25
        if hist["fast_jump"].iloc[0]:
            path_bonus += 15

    # Low-prize signal
    low_hits = sum(prize_counts.get(p, 0) for p in [100, 200, 500, 1000, 2000])
    low_signal = low_hits * 0.5

    # Recency penalty
    recency_penalty = days_since * 0.3

    # Final score
    final_score = trans_score + maturity_score + path_bonus + low_signal - recency_penalty

    pred_rows.append({
        "number": num,
        "last_seen": last_date.strftime("%d/%m/%Y"),
        "days_since_seen": days_since,
        "score": final_score,
        "counts": prize_counts
    })

pred_df = pd.DataFrame(pred_rows)
pred_df.sort_values("score", ascending=False, inplace=True)
pred_df.to_csv(OUTPUT_HYBRID, index=False)

print(f"\n========================================")
print(f"Top 15 HYBRID predicted ₹5000 candidates:")
print(pred_df.head(15))
print(f"\nSaved -> {OUTPUT_HYBRID}")
print(f"========================================")
