import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from tqdm import tqdm

# ==========================
# CONFIGURATION
# ==========================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"
OUTPUT_FILE = "pattern_comparison_short_vs_long.csv"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

# ==========================
# HELPERS
# ==========================
def parse_date(d):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None

def get_data():
    pipeline = [
        {"$unwind": "$series"},
        {"$unwind": "$series.numbers"},
        {"$project": {
            "number": "$series.numbers.number",
            "prize": "$series.prize",
            "date": "$date"
        }}
    ]
    data = list(lottery_data.aggregate(pipeline))
    df = pd.DataFrame(data)
    df["parsed_date"] = df["date"].apply(parse_date)
    df = df[df["parsed_date"].notnull()]
    return df

# ==========================
# MAIN
# ==========================
print("🔄 Fetching all prize data from MongoDB...")
df = get_data()
df = df.sort_values("parsed_date")

# Define windows
early_mask = df["parsed_date"] < datetime(2023, 1, 1)
recent_mask = df["parsed_date"] >= datetime(2023, 1, 1)
df_early = df[early_mask]
df_recent = df[recent_mask]

def transition_stats(subdf):
    subdf = subdf.sort_values(["number", "parsed_date"])
    transitions = []
    for num, grp in tqdm(subdf.groupby("number"), total=subdf["number"].nunique()):
        prizes = grp["prize"].tolist()
        dates = grp["parsed_date"].tolist()
        for i in range(len(prizes)-1):
            gap = (dates[i+1] - dates[i]).days
            transitions.append({
                "from_prize": prizes[i],
                "to_prize": prizes[i+1],
                "gap_days": gap
            })
    tdf = pd.DataFrame(transitions)
    summary = tdf.groupby(["from_prize", "to_prize"])["gap_days"].agg(
        ["count", "mean", "median"]
    ).reset_index()
    return summary

print("📆 Computing early (2020–2022) transition stats...")
early_summary = transition_stats(df_early)
early_summary["period"] = "2020–2022"

print("📆 Computing recent (2023–2025) transition stats...")
recent_summary = transition_stats(df_recent)
recent_summary["period"] = "2023–2025"

combined = pd.concat([early_summary, recent_summary])
combined.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

# ==========================
# INTERPRETATION
# ==========================
print(f"✅ Saved short vs long pattern comparison -> {OUTPUT_FILE}")
print("\n🧩 Quick Glance:")
for period, grp in combined.groupby("period"):
    print(f"\nPeriod: {period}")
    print(grp.sort_values("count", ascending=False).head(10))
