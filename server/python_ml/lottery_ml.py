import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt

# 1. Load dataset
df = pd.read_csv("lotteryData.csv")

# Ensure number column is string (to keep leading zeros)
df["number"] = df["number"].astype(str).str.zfill(4)

# Convert number into integer for ML
df["number_int"] = df["number"].astype(int)

print("✅ Data loaded:", df.head())

# 2. Feature Engineering
# Frequency: how many times each number appeared
freq = df.groupby("number_int")["count"].sum().to_dict()
df["frequency"] = df["number_int"].map(freq)

# Features (X) and target (y)
X = df[["prize", "frequency"]]
y = df["number_int"]

# 3. Train/Test Split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# 4. Train Model (Linear Regression)
model = LinearRegression()
model.fit(X_train, y_train)

print("✅ Model trained")

# 5. Evaluate with R² score (how well regression explains variation)
score = model.score(X_test, y_test)
print(f"📊 R² Score: {score:.4f}")

# 6. Predict Next Likely Numbers (example: for prize = 5000)
future_prize = 5000
sample = pd.DataFrame({
    "prize": [future_prize] * 10,
    "frequency": range(1, 11)
})
predictions = model.predict(sample)

# Round predictions to nearest valid lottery number
predicted_numbers = [str(int(round(num))).zfill(4) for num in predictions]

print("🎯 Top predicted numbers for prize", future_prize, ":", predicted_numbers)

# 7. Show top hot numbers by frequency
top_numbers = df.groupby("number_int")["count"].sum().sort_values(ascending=False).head(10)
print("\n🔥 Top hot numbers:\n", top_numbers)

# Plot top 10 frequent numbers
top_numbers.plot(kind="bar", figsize=(10,5))
plt.title("Top 10 Frequent Lottery Numbers")
plt.xlabel("Number")
plt.ylabel("Count")
plt.show()
