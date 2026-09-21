import pandas as pd
from tqdm import tqdm
import matplotlib.pyplot as plt

# =====================
# CONFIG
# =====================
MACHINE_FILE = "machine.csv"
RESULT_FILES = [
    "Result2020.csv",
    "Result2021.csv",
    "Result2022.csv",
    "Result2023.csv",
    "Result2024.csv",
    "Result2025.csv",
]
OUTPUT_FILE = "machine_cycles.csv"

# =====================
# STEP 1: Load machine
# =====================
machine_df = pd.read_csv(MACHINE_FILE, index_col=0)

rollers = []
for col in machine_df.columns:  # '0'..'5'
    digits = machine_df[col].dropna().astype(int).tolist()
    rollers.append(digits)

# =====================
# STEP 2: Load all results in chronological order
# =====================
results = []
for file in RESULT_FILES:
    df = pd.read_csv(file)
    year = file[-8:-4]
    for _, row in df.iterrows():
        day = int(row['Date'])
        for month in df.columns[1:]:
            val = row[month]
            if pd.notna(val):
                results.append((pd.to_datetime(f"{day}-{month}-{year}", dayfirst=True), int(val)))

# Sort ascending
results.sort(key=lambda x: x[0])

# =====================
# STEP 3: Helper function
# =====================
def find_cycles(prev_digit, roller_digits, target_digit):
    n = len(roller_digits)
    start_idx = roller_digits.index(prev_digit)
    for cycles in range(1, n+1):
        if roller_digits[(start_idx + cycles) % n] == target_digit:
            return cycles
    return None

# =====================
# STEP 4: Compute cycles for each result
# =====================
prev_digits = [r[0] for r in rollers]
cycles_per_result = []

print("\nCalculating cycles for results...")
for date, number in tqdm(results):
    num_str = f"{number:06d}"  # pad to 6 digits
    cycles = []
    for j, d in enumerate(num_str):
        digit = int(d)
        cycle_count = find_cycles(prev_digits[j], rollers[j], digit)
        cycles.append(cycle_count)
        prev_digits[j] = digit
    cycles_per_result.append([date.strftime("%d-%B-%Y"), number] + cycles)

# =====================
# STEP 5: Save to CSV
# =====================
columns = ["Date", "WinningNumber"] + [f"Cycles_Roller{i}" for i in range(6)]
cycles_df = pd.DataFrame(cycles_per_result, columns=columns)
cycles_df.to_csv(OUTPUT_FILE, index=False)
print(f"\nMachine cycles saved to {OUTPUT_FILE}")

# =====================
# STEP 6: Last 2025 number positions
# =====================
last_2025 = [r for r in results if r[0].year == 2025][-1]
last_number_str = f"{last_2025[1]:06d}"
positions_in_machine = [rollers[i].index(int(d)) for i, d in enumerate(last_number_str)]
print(f"\nLast 2025 number: {last_2025[1]}")
print(f"Positions in machine cycles: {positions_in_machine}")

# =====================
# STEP 7: Visualization
# =====================
plt.figure(figsize=(18,6))
for i in range(6):
    plt.plot(range(len(cycles_df)), cycles_df[f"Cycles_Roller{i}"], label=f"Roller {i}")

plt.xlabel("Draw Index (chronological)")
plt.ylabel("Cycles per draw")
plt.title("Roller Cycles Over Time (2020-2025)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
