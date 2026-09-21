import pandas as pd
import json

# ======================
# CONFIG
# ======================
DATA_CSV = "lotteryData.csv"
PRIZE_LIST = [5000, 2000, 1000, 500, 200, 100]

# ======================
# LOAD DATA
# ======================
df = pd.read_csv(DATA_CSV)
df["number"] = df["number"].astype(str).str.zfill(4)
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
df = df.dropna(subset=["date"])

print("✅ Data loaded:", df.head())

# ======================
# BUILD PRIZE → NUMBERS MAP
# ======================
prize_map = {}
for prize in PRIZE_LIST:
    sub = df[df["prize"] == prize]
    grouped = sub.groupby("number")["date"].apply(
        lambda x: sorted(x.dt.strftime("%Y-%m-%d").unique())
    ).to_dict()
    prize_map[prize] = grouped

# ======================
# CROSS-CHECK MAPPINGS
# ======================
results = {}

for prize in PRIZE_LIST:
    results[prize] = {}
    for number, dates in prize_map[prize].items():
        results[prize][number] = {
            "dates": dates,
            "also_in": {}
        }
        # check in other prizes
        for other_prize in PRIZE_LIST:
            if other_prize == prize:
                continue
            if number in prize_map[other_prize]:
                results[prize][number]["also_in"][other_prize] = prize_map[other_prize][number]
            else:
                results[prize][number]["also_in"][other_prize] = []

# ======================
# SAVE TO JSON
# ======================
with open("lottery_cross_prize.json", "w") as f:
    json.dump(results, f, indent=2)

print("✅ Cross-prize analysis saved to lottery_cross_prize.json")
