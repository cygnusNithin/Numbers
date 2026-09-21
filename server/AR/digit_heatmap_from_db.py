from pymongo import MongoClient
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# -----------------------------
# CONNECT TO MONGODB
# -----------------------------
client = MongoClient("mongodb://localhost:27017/")
db = client["numbergrid"]
collection = db["lotterydatas"]

# -----------------------------
# LOAD DATA FROM DB
# -----------------------------
records = []

for doc in collection.find({}, {"date": 1, "series": 1}):
    date_str = doc.get("date")
    if not date_str:
        continue

    try:
        date_obj = datetime.strptime(date_str, "%d/%m/%Y")
    except:
        continue

    for series in doc.get("series", []):
        for num_obj in series.get("numbers", []):
            number = num_obj.get("number")
            if number:
                records.append({
                    "date": date_obj,
                    "number": str(number).zfill(4)  # ✅ 4 digits only
                })

df = pd.DataFrame(records)

print("Total numbers loaded:", len(df))

# -----------------------------
# SPLIT BEFORE / AFTER MAY 2025
# -----------------------------
cutoff = pd.Timestamp("2025-05-01")

before_df = df[df["date"] < cutoff].copy()
after_df  = df[df["date"] >= cutoff].copy()

print("Before May 2025 numbers:", len(before_df))
print("After May 2025 numbers: ", len(after_df))

# -----------------------------
# FUNCTION TO EXTRACT DIGIT MATRIX
# -----------------------------
def digit_matrix(data):
    digits = data['number'].apply(lambda x: [int(d) for d in x])
    return np.array(digits.tolist())

before_digits = digit_matrix(before_df)
after_digits  = digit_matrix(after_df)

# -----------------------------
# CALCULATE AVERAGE DIGIT PER POSITION
# -----------------------------
before_avg = before_digits.mean(axis=0)
after_avg  = after_digits.mean(axis=0)
shift = after_avg - before_avg

positions = [f"Pos {i+1}" for i in range(4)]

heatmap_data = pd.DataFrame({
    "Before May 2025": before_avg,
    "After May 2025": after_avg,
    "Shift": shift
}, index=positions)

print("\nDigit Position Shift Table:\n")
print(heatmap_data)

# -----------------------------
# HEATMAP
# -----------------------------
plt.figure(figsize=(8,5))
sns.heatmap(heatmap_data, annot=True, cmap="coolwarm", center=0)
plt.title("Digit Position Drift (Before vs After May 2025)")
plt.show()
