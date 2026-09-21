import pandas as pd
from tqdm import tqdm
from datetime import datetime
import matplotlib.pyplot as plt

# ======================
# CONFIG
# ======================
INPUT_CSV = "5000_number_patterns13.csv"
NUM_GROUPS = 20
MAX_HIT = 12
OUTPUT_CSV = "5000_number_group_daily_progress.csv"

# ======================
# LOAD DATA
# ======================
df = pd.read_csv(INPUT_CSV)
df["number"] = df["number"].astype(str).str.zfill(4)
df["dates_list"] = df["dates"].str.split("|")

# Assign each number to one of 20 groups
def assign_group(num_str):
    num_int = int(num_str)
    group_size = 10000 // NUM_GROUPS
    group_id = num_int // group_size + 1
    return group_id

df["group"] = df["number"].apply(assign_group)

# ======================
# FLATTEN DATA
# ======================
all_entries = []
for idx, row in tqdm(df.iterrows(), total=len(df), desc="Flattening numbers"):
    for d in row["dates_list"]:
        if d:  # skip empty dates
            all_entries.append({
                "date": datetime.strptime(d, "%d/%m/%Y"),
                "number": row["number"],
                "group": row["group"]
            })

all_df = pd.DataFrame(all_entries)
all_df.sort_values("date", inplace=True)

# ======================
# DAILY GROUP PROGRESS
# ======================
start_date = all_df["date"].min()
end_date = all_df["date"].max()
date_range = pd.date_range(start=start_date, end=end_date)

daily_group_progress = []

for current_date in tqdm(date_range, total=len(date_range), desc="Calculating daily progress"):
    up_to_date = all_df[all_df["date"] <= current_date]
    
    # Count hits per number
    number_hits = up_to_date.groupby("number").size().to_dict()
    
    # Compute progress per group
    group_progress = {}
    for g in range(1, NUM_GROUPS + 1):
        nums_in_group = df[df["group"] == g]["number"]
        total_progress = sum(min(number_hits.get(n,0)/MAX_HIT,1.0) for n in nums_in_group)
        group_progress[g] = total_progress
    
    daily_group_progress.append({"date": current_date, **group_progress})

daily_progress_df = pd.DataFrame(daily_group_progress)
daily_progress_df.to_csv(OUTPUT_CSV, index=False)
print(f"✅ Saved daily group progress → {OUTPUT_CSV}")

# ======================
# VISUALIZATION
# ======================
plt.figure(figsize=(14,7))
for g in range(1, NUM_GROUPS+1):
    plt.plot(daily_progress_df["date"], daily_progress_df[g], label=f"Group {g}")

plt.xlabel("Date")
plt.ylabel("Cumulative Progress toward MAX_HIT")
plt.title("Daily Progress of 5000 Prize Numbers by Group (2020–2025)")
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()
