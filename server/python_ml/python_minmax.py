import pandas as pd

# ======================
# CONFIG
# ======================
DATA_CSV = "lotteryData1.csv"

# ======================
# LOAD DATA
# ======================
df = pd.read_csv(DATA_CSV)
df["number"] = df["number"].astype(str).str.zfill(4)

# ======================
# COUNT REPETITIONS
# ======================
counts = df["number"].value_counts()

# Get min and max repeated numbers
min_num = counts.idxmin()
min_count = counts.min()

max_num = counts.idxmax()
max_count = counts.max()

print(f"🎯 Min repeated number: {min_num} (repeated {min_count} times)")
print(f"🏆 Max repeated number: {max_num} (repeated {max_count} times)")
