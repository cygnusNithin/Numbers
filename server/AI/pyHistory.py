from pymongo import MongoClient
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# --- Step 1: Connect to MongoDB ---
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
lottery_data = db[COLLECTION]

docs = list(lottery_data.find())

# --- Step 2: Flatten nested schema ---
rows = []
for doc in docs:
    for s in doc.get("series", []):
        prize = s.get("prize")
        roller_id = s.get("roller_id", None)
        for idx, num in enumerate(s.get("numbers", [])):
            rows.append({
                "entryNumber": doc.get("entryNumber"),
                "serialNumber": doc.get("serialNumber"),
                "date": doc.get("date"),
                "prize": prize,
                "number": num.get("number"),
                "count": num.get("count", 1),
                "roller_id": roller_id,
                "position_in_roll": idx
            })

df = pd.DataFrame(rows)

# --- Step 3: Feature engineering ---
df["d1"] = df["number"].str[0].astype(int)
df["d2"] = df["number"].str[1].astype(int)
df["d3"] = df["number"].str[2].astype(int)
df["d4"] = df["number"].str[3].astype(int)

df["serial_prefix"] = df["serialNumber"].str.split("-").str[0]
df["serial_prefix_encoded"] = df["serial_prefix"].astype("category").cat.codes

df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y")

df["hit_count"] = df.groupby("number").cumcount() + 1
df["days_since_last_hit"] = df.groupby("number")["date"].diff().dt.days.fillna(9999)

X = df[[
    "d1", "d2", "d3", "d4",
    "serial_prefix_encoded",
    "count",
    "hit_count",
    "days_since_last_hit",
    "position_in_roll"
]]

# --- Step 4: Train separate models per prize ---
prizes = df["prize"].unique()
models = {}

for prize in prizes:
    df_binary = df.copy()
    df_binary["target"] = (df_binary["prize"] == prize).astype(int)
    y = df_binary["target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestClassifier(n_estimators=200, random_state=42)
    model.fit(X_train, y_train)

    models[prize] = model

# --- Step 5: Batch predictions ---
log_rows = []

# Demo: run predictions for numbers 0000–0099
for num in range(100):
    num_str = f"{num:04d}"
    d1, d2, d3, d4 = [int(d) for d in num_str]

    sample_df = pd.DataFrame([[d1, d2, d3, d4,
                               df["serial_prefix_encoded"].iloc[0],
                               1,   # count
                               1,   # hit_count (default for demo)
                               9999, # days_since_last_hit (default for demo)
                               0]], # position_in_roll (default for demo)
                             columns=["d1","d2","d3","d4","serial_prefix_encoded","count","hit_count","days_since_last_hit","position_in_roll"])

    best_prize = None
    best_prob = -1
    prob_dict = {}

    for prize, model in models.items():
        prob = model.predict_proba(sample_df)[0][1]
        prob_dict[prize] = prob
        if prob > best_prob:
            best_prob = prob
            best_prize = prize

    log_entry = {"number": num_str, "final_prize": best_prize, "final_prob": best_prob}
    log_entry.update({f"prob_{p}": prob_dict[p] for p in prizes})
    log_rows.append(log_entry)

# Save log to CSV
log_df = pd.DataFrame(log_rows)
log_df.to_csv("prediction_log.csv", index=False)

print("\nBatch prediction log saved to prediction_log.csv")
print(log_df.head(10))  # show first 10 rows
