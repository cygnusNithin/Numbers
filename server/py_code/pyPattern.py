import pandas as pd
import matplotlib.pyplot as plt

# ================================
# Load data
# ================================
df = pd.read_csv("5000_analysis_since_2025-08-26.csv")

# --- 1. Numbers with low remaining count ---
hot_numbers = df[df["remaining_to_12"] <= 2]
print("🔥 Hot numbers close to cap (likely repeat soon):")
print(hot_numbers[["number", "remaining_to_12", "dates_after_2025-08-26"]])

# --- 2. Most common weekday in new hits ---
df["new_dates_list"] = df["dates_after_2025-08-26"].fillna("").apply(lambda x: x.split("|"))
all_new_dates = [d for dates in df["new_dates_list"] for d in dates if d]
dates = pd.to_datetime(all_new_dates, format="%d/%m/%Y", errors="coerce")

print("\n📅 New hit weekday counts:")
weekday_counts = dates.day_name().value_counts()
print(weekday_counts)

# Plot weekday frequency
plt.figure(figsize=(8, 5))
weekday_counts.plot(kind="bar", color="skyblue", edgecolor="black")
plt.title("Weekday Frequency of New Hits (since 26/08/2025)")
plt.ylabel("Count")
plt.xlabel("Weekday")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# --- 3. Last digit pattern among new hits ---
df["last_digit"] = df["number"].astype(str).str[-1]
last_digit_counts = df[df["increase_after_2025-08-26"] > 0]["last_digit"].value_counts()

print("\n🔢 Last digit frequency (new hits):")
print(last_digit_counts)

# Plot last digit frequency
plt.figure(figsize=(6, 4))
last_digit_counts.plot(kind="bar", color="salmon", edgecolor="black")
plt.title("Last Digit Frequency of New Hits (since 26/08/2025)")
plt.ylabel("Count")
plt.xlabel("Last Digit")
plt.xticks(rotation=0)
plt.tight_layout()
plt.show()
