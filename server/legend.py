import pandas as pd

# ===============================
# CONFIGURATION
# ===============================
INPUT_FILE = "sixroller_gaps_detailed.csv"
OUTPUT_FILE = "sixroller_gap_frequency.csv"

# ===============================
# MAIN FUNCTION
# ===============================
def main():
    print(f"📂 Loading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE)

    if df.empty:
        print("⚠️ No data found in CSV.")
        return

    # Drop NaN gaps
    df = df.dropna(subset=["gap_steps"])

    # Ensure integer type
    df["gap_steps"] = df["gap_steps"].astype(int)
    df["roller_id"] = df["roller_id"].astype(int)

    # ===========================
    # Compute frequency of each gap per roller
    # ===========================
    freq_table = (
        df.groupby(["roller_id", "gap_steps"])
        .size()
        .reset_index(name="count")
        .sort_values(["roller_id", "count"], ascending=[True, False])
    )

    # Save full frequency list
    freq_table.to_csv(OUTPUT_FILE, index=False)
    print(f"✅ Saved full roller movement frequencies → {OUTPUT_FILE}")

    # ===========================
    # Print detailed summary per roller
    # ===========================
    print("\n📊 Roller Movement Frequency Summary:\n")
    for rid in sorted(freq_table["roller_id"].unique()):
        sub = freq_table[freq_table["roller_id"] == rid]
        print(f"🔹 Roller {rid}")
        for _, row in sub.iterrows():
            print(f"   Gap {row['gap_steps']:>2} → {row['count']} times")
        print("-" * 40)


if __name__ == "__main__":
    main()
