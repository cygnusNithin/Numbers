import pandas as pd
from ast import literal_eval
from tqdm import tqdm

# Load CSV
df = pd.read_csv("5000_number_patterns7.csv")

# Function to check if Friday has max hits
def is_friday_max(weekday_counts):
    counts = literal_eval(weekday_counts)
    if "Friday" not in counts:
        return False
    max_count = max(counts.values())
    return counts["Friday"] == max_count

# Filter numbers: Friday is max, total_hits <= 11
MAX_TOTAL_HIT = 11

filtered_numbers = []

for _, row in tqdm(df.iterrows(), total=len(df), desc="Filtering Friday max numbers"):
    total_hits = row['total_hits']
    weekday_counts = row['weekday_counts']
    
    if total_hits <= MAX_TOTAL_HIT and is_friday_max(weekday_counts):
        filtered_numbers.append({
            "number": row['number'],
            "total_hits": total_hits,
            "remaining_to_max": row['remaining_to_max'],
            "weekday_counts": weekday_counts,
            "month_counts": row['month_counts']
        })

# Save filtered results
filtered_df = pd.DataFrame(filtered_numbers)
filtered_df.to_csv("friday_maxhit_numbers.csv", index=False)

print(f"✅ Found {len(filtered_numbers)} numbers where Friday has max hits and total_hits ≤ {MAX_TOTAL_HIT}.")
