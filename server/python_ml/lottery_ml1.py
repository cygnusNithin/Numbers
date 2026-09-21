import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import seaborn as sns
import matplotlib.pyplot as plt

# 1. Load dataset
df = pd.read_csv("lotteryData.csv")

# Convert date properly
df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")

# Extract date features
df["day"] = df["date"].dt.day
df["month"] = df["date"].dt.month
df["weekday"] = df["date"].dt.weekday  # 0=Mon, 6=Sun

# Convert numbers to int
df["number_int"] = df["number"].astype(str).str.zfill(4).astype(int)

# 2. Create frequency-based feature
freq = df.groupby("number_int")["count"].sum().to_dict()
df["frequency"] = df["number_int"].map(freq)

# 3. Turn into a classification task
# Target = "Did this number appear (1) or not (0)"
# For training, we simulate "appeared" as label=1
df["appeared"] = 1  

# Features = prize + frequency + date parts
X = df[["prize", "frequency", "day", "month", "weekday"]]
y = df["appeared"]

# 4. Train/Test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# 5. Train a classifier
model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X_train, y_train)

print("✅ Model trained as classifier")
print("📊 Accuracy on test:", model.score(X_test, y_test))

# 6. Predict probabilities for a future date
future_date = pd.to_datetime("2025-08-20")  # example date
future_sample = pd.DataFrame({
    "prize": [5000]*50,   # check top 50 candidates for prize 5000
    "frequency": range(1, 51),
    "day": [future_date.day]*50,
    "month": [future_date.month]*50,
    "weekday": [future_date.weekday()]*50
})

probs = model.predict_proba(future_sample)[:, 1]  # probability of appearing
future_sample["probability"] = probs

# Sort by highest probability
predicted_numbers = future_sample.sort_values("probability", ascending=False).head(10)
print("\n🎯 Top 10 predicted numbers:\n", predicted_numbers)

# 7. Visualization – heatmap of number frequency by weekday/month
heatmap_data = df.groupby(["month", "weekday"])["count"].sum().unstack(fill_value=0)

plt.figure(figsize=(10,6))
sns.heatmap(heatmap_data, cmap="Reds", annot=True, fmt="d")
plt.title("🔥 Number Frequencies by Month & Weekday")
plt.xlabel("Weekday (0=Mon)")
plt.ylabel("Month")
plt.show()
