import pandas as pd
from collections import Counter

# ===============================
# CONFIGURATION
# ===============================
INPUT_FILE = "try_differences.csv"

# ===============================
# MAIN FUNCTION
# ===============================
def main():
    # Load the CSV
    df = pd.read_csv(INPUT_FILE)

    # Clean data: remove rows with NaN or invalid gap_steps
    df = df.dropna(subset=["gap_steps"])
    df = df[df["gap_steps"].astype(str).str.isdigit()]
    df["gap_steps"] = df["gap_steps"].astype(int)

    print("📊 Roller Movement Frequency Summary:\n")

    # Process each roller
    for roller_id in sorted(df["roller_id"].unique()):
        roller_data = df[df["roller_id"] == roller_id]
        counter = Counter(roller_data["gap_steps"])
        sorted_counts = sorted(counter.items(), key=lambda x: (-x[1], x[0]))

        print(f"🔹 Roller {roller_id}")
        for gap, count in sorted_counts:
            print(f"   Gap {gap:2} → {count} times")
        print("-" * 40)

    print("✅ Frequency analysis complete!")

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    main()
