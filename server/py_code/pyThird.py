import pandas as pd
import itertools
from tqdm import tqdm

# =====================
# CONFIG
# =====================
MACHINE_FILE = "machine.csv"
CYCLES_FILE = "machine_cycles.csv"
TOP_N = 10  # Number of predicted numbers

# =====================
# Load machine
# =====================
machine_df = pd.read_csv(MACHINE_FILE, index_col=0)
rollers = []
for col in machine_df.columns:
    digits = machine_df[col].dropna().astype(int).tolist()
    rollers.append(digits)

# =====================
# Load cycles data
# =====================
cycles_df = pd.read_csv(CYCLES_FILE)

# =====================
# Analyze frequency of cycles per roller
# =====================
freq_cycles = []
for i in range(6):
    counts = cycles_df[f"Cycles_Roller{i}"].value_counts().sort_values(ascending=False)
    # Keep top 3 most frequent cycles for variety
    top_cycles = counts.head(3).index.tolist()
    freq_cycles.append(top_cycles)

print("Top probable cycles per roller:", freq_cycles)

# =====================
# Get last known positions
# =====================
last_row = cycles_df.iloc[-1]
last_number_str = f"{last_row['WinningNumber']:06d}"
last_positions = []
for i, d in enumerate(last_number_str):
    digit = int(d)
    if digit in rollers[i]:
        last_positions.append(rollers[i].index(digit))
    else:
        last_positions.append(0)  # default if digit not in roller

# =====================
# Generate all combinations of probable cycles with progress bar
# =====================
all_combinations = list(itertools.product(*freq_cycles))
predicted_numbers = []

print("\nCalculating predicted numbers with progress bar...")
for combo in tqdm(all_combinations):
    predicted_number = []
    for i in range(6):
        roller_len = len(rollers[i])
        next_pos = (last_positions[i] + combo[i]) % roller_len
        predicted_number.append(rollers[i][next_pos])
    predicted_numbers.append("".join(map(str, predicted_number)))

# Keep only TOP_N unique predictions
predicted_numbers = list(dict.fromkeys(predicted_numbers))[:TOP_N]

print("\nTop predicted next numbers:")
for num in predicted_numbers:
    print(num)
