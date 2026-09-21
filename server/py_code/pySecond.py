import pandas as pd
import numpy as np

# =====================
# CONFIG
# =====================
MACHINE_FILE = "machine.csv"
CYCLES_FILE = "machine_cycles.csv"

# =====================
# Load machine
# =====================
machine_df = pd.read_csv(MACHINE_FILE, index_col=0)
rollers = []
for col in machine_df.columns:
    digits = machine_df[col].dropna().astype(int).tolist()
    rollers.append(digits)

# =====================
# Load cycles
# =====================
cycles_df = pd.read_csv(CYCLES_FILE)

# =====================
# Compute probable cycles per roller
# =====================
probable_cycles = []
for i in range(6):
    # Option 1: average cycles
    avg = int(round(cycles_df[f"Cycles_Roller{i}"].mean()))
    probable_cycles.append(avg)

print("Probable cycles for next draw:", probable_cycles)

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
        last_positions.append(0)  # default if not in roller

# =====================
# Predict next number
# =====================
predicted_number = []
for i in range(6):
    roller_len = len(rollers[i])
    next_pos = (last_positions[i] + probable_cycles[i]) % roller_len
    predicted_number.append(rollers[i][next_pos])

predicted_number_str = "".join(map(str, predicted_number))
print("Predicted next number:", predicted_number_str)
