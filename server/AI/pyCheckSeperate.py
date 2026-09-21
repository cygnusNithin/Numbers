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

# Fetch all documents
docs = list(lottery_data.find())

# --- Step 2: Flatten nested schema ---
rows = []
for doc in docs:
    for s in doc.get("series", []):
        prize = s.get("prize")
        for num in s.get("numbers", []):
            rows.append({
                "entryNumber": doc.get("entryNumber"),
                "serialNumber": doc.get("serialNumber"),
                "date": doc.get("date"),
                "prize": prize,
                "number": num.get("number"),
                "count": num.get("count", 1)
            })

df = pd.DataFrame(rows)
print("Flattened DataFrame:")
print(df.head())

# --- Step 3: Feature engineering ---
# Split 4-digit number into digits
df["d1"] = df["number"].str[0].astype(int)
df["d2"] = df["number"].str[1].astype(int)
df["d3"] = df["number"].str[2].astype(int)
df["d4"] = df["number"].str[3].astype(int)

# Extract serial prefix (e.g., "KR" from "KR-456")
df["serial_prefix"] = df["serialNumber"].str.split("-").str[0]
df["serial_prefix_encoded"] = df["serial_prefix"].astype("category").cat.codes

# Features
X = df[["d1", "d2", "d3", "d4", "serial_prefix_encoded", "count"]]

# --- Step 4: Train separate models for each prize ---
prizes = df["prize"].unique()
models = {}

for prize in prizes:
    print(f"\n=== Training model for prize {prize} ===")
    
    # Binary target: 1 if this prize, else 0
    df_binary = df.copy()
    df_binary["target"] = (df_binary["prize"] == prize).astype(int)
    
    y = df_binary["target"]
    
    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Train Random Forest
    model = RandomForestClassifier(n_estimators=200, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Accuracy for prize {prize}: {acc:.4f}")
    
    # Save model in dictionary
    models[prize] = model

# --- Step 5: Sample prediction using all models ---
sample = pd.DataFrame([[0, 0, 4, 6,  # digits of "0046"
                        df["serial_prefix_encoded"].iloc[0],  # use first prefix encoding
                        1]],  # count
                      columns=["d1", "d2", "d3", "d4", "serial_prefix_encoded", "count"])

print("\nSample predictions:")
for prize, model in models.items():
    pred = model.predict(sample)[0]
    print(f"Prize {prize}: {'YES' if pred == 1 else 'NO'}")
