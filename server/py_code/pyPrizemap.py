import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pymongo import MongoClient
from collections import Counter, defaultdict
import math

# ======================
# CONFIG
# ======================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
coll = client[DB_NAME][COLLECTION]

# ----------------------
# Collect all numbers
# ----------------------
numbers = []
for doc in coll.find({}, {"series": 1}):
    for s in doc.get("series", []):
        prize = s.get("prize")
        for n in s.get("numbers", []):
            num = str(n.get("number")).zfill(4)
            for pos, d in enumerate(num):
                numbers.append({"digit": int(d), "pos": pos, "prize": prize})

df = pd.DataFrame(numbers)

# ----------------------
# Heatmap: Digit frequencies by position
# ----------------------
pos_counts = df.groupby(["pos", "digit"]).size().unstack(fill_value=0)

plt.figure(figsize=(10,6))
sns.heatmap(pos_counts, annot=True, fmt="d", cmap="YlGnBu")
plt.title("Digit Frequency by Position (0 = Thousands, 3 = Ones)")
plt.xlabel("Digit")
plt.ylabel("Position")
plt.savefig("digit_position_heatmap.png")
plt.show()

# ----------------------
# Heatmap: Digit frequencies by prize
# ----------------------
prize_counts = df.groupby(["prize", "digit"]).size().unstack(fill_value=0)

plt.figure(figsize=(12,6))
sns.heatmap(prize_counts, annot=True, fmt="d", cmap="YlOrBr")
plt.title("Digit Frequency by Prize Category")
plt.xlabel("Digit")
plt.ylabel("Prize")
plt.savefig("digit_prize_heatmap.png")
plt.show()

# ----------------------
# Bar chart for each position
# ----------------------
for pos in sorted(df["pos"].unique()):
    plt.figure(figsize=(8,4))
    df[df["pos"] == pos]["digit"].value_counts().sort_index().plot(kind="bar")
    plt.title(f"Digit Distribution at Position {pos} (0 = Thousands)")
    plt.xlabel("Digit")
    plt.ylabel("Frequency")
    plt.savefig(f"digit_distribution_pos{pos}.png")
    plt.show()

# ----------------------
# Bar chart for each prize
# ----------------------
for prize in sorted(df["prize"].unique()):
    plt.figure(figsize=(8,4))
    df[df["prize"] == prize]["digit"].value_counts().sort_index().plot(kind="bar")
    plt.title(f"Digit Distribution for Prize {prize}")
    plt.xlabel("Digit")
    plt.ylabel("Frequency")
    plt.savefig(f"digit_distribution_prize{prize}.png")
    plt.show()

print("✅ Heatmaps and bar charts saved (digit_position_heatmap.png, digit_prize_heatmap.png, etc.)")
