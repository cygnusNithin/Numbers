import pandas as pd

# ===============================
# CONFIGURATION
# ===============================
INPUT_FILE = "mainPrize.csv"   # file that has just "number" column
OUTPUT_FILE = "mainPrizes.csv"         # file with "try,number"

# ===============================
# MAIN
# ===============================
def main():
    # Read input numbers (one per line or column)
    df = pd.read_csv(INPUT_FILE, header=None, names=["number"], dtype=str)
    
    # Add try number (starting from 1)
    df.insert(0, "try", range(1, len(df) + 1))
    
    # Save output
    df.to_csv(OUTPUT_FILE, index=False)
    
    print(f"✅ Added try numbers and saved → {OUTPUT_FILE}")
    print(df.head(10))

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    main()
