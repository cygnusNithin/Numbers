import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import joblib
from tqdm import tqdm
import random
import csv

# ======================
# CONFIG
# ======================
MACHINE_FILE = "machine.csv"
FILES = [
    "Result2020.csv",
    "Result2021.csv",
    "Result2022.csv",
    "Result2023.csv",
    "Result2024.csv",
    "Result2025.csv",
]

MODEL_FILE = "lottery_model.pkl"
FUTURE_COUNT = 20
TARGET = "430879"
OUTPUT_FILE = "PredictedSequences.csv"

# ======================
# LOAD MACHINE CYCLES
# ======================
machine_df = pd.read_csv(MACHINE_FILE)
machine_cycles = {}
for pos in ["0", "1", "2", "3", "4", "5"]:
    cycle = machine_df[pos].dropna().astype(int).tolist()
    machine_cycles[int(pos)] = cycle

# ======================
# LOAD HISTORICAL RESULTS
# ======================
all_results = []
for f in FILES:
    df = pd.read_csv(f)
    numbers = df.iloc[:, 0].astype(str).str.zfill(6)
    all_results.extend(numbers)

# ======================
# PREPARE DATA
# ======================
X, y = [], []
for i in range(len(all_results) - 1):
    current = all_results[i]
    next_num = all_results[i + 1]
    features = [int(d) for d in current]
    label = [int(d) for d in next_num]
    X.append(features)
    y.append(label)

X = np.array(X)
y = np.array(y)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

# ======================
# MODEL TRAINING
# ======================
models = {}
for pos in range(6):
    clf = RandomForestClassifier(n_estimators=200, random_state=42)
    clf.fit(X_train, y_train[:, pos])
    models[pos] = clf

joblib.dump(models, MODEL_FILE)

# ======================
# LOOP UNTIL TARGET FOUND
# ======================
print(f"🔄 Generating predictions until {TARGET} is found...")
last_number = [int(d) for d in all_results[-1]]

sequence_id = 0
found = False

with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    header = ["SequenceID"] + [f"Num{i+1}" for i in range(FUTURE_COUNT)]
    writer.writerow(header)

    with tqdm(total=1000000, desc="Simulations", unit="seq") as pbar:  # large cap
        while not found:
            future_numbers = []
            for step in range(FUTURE_COUNT):
                predicted_digits = []
                for pos in range(6):
                    probs = models[pos].predict_proba([last_number])[0]
                    classes = models[pos].classes_
                    cycle = machine_cycles[pos]
                    allowed = [(c, p) for c, p in zip(classes, probs) if c in cycle]

                    if allowed:
                        digits, probas = zip(*allowed)
                        probas = np.array(probas) / np.sum(probas)
                        pred = np.random.choice(digits, p=probas)
                    else:
                        if last_number[pos] in cycle:
                            idx = cycle.index(last_number[pos])
                            pred = cycle[(idx + 1) % len(cycle)]
                        else:
                            pred = cycle[0]

                    predicted_digits.append(int(pred))

                predicted_number = "".join(map(str, predicted_digits))
                future_numbers.append(predicted_number)
                last_number = predicted_digits  # feed into next

                if predicted_number == TARGET:
                    found = True

            # Save this sequence to CSV
            sequence_id += 1
            writer.writerow([sequence_id] + future_numbers)

            pbar.update(1)

print(f"\n✅ Target {TARGET} found in sequence {sequence_id}.")
print(f"📂 All sequences saved to {OUTPUT_FILE}")
