import pandas as pd
import os

# Configuration
INPUT_FILE = "all_prizes_number_patterns18.csv"
OUTPUT_FILE = "all_permutations_with_dates.csv"

def generate_master_list():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Could not find {INPUT_FILE} in the current directory.")
        return

    print("Loading source data...")
    # Load your existing data
    df_source = pd.read_csv(INPUT_FILE)
    
    # Ensure numbers are 4-digit strings (0001, 0010, etc.)
    df_source['number'] = df_source['number'].astype(str).str.zfill(4)
    
    # Create a mapping dictionary for O(1) lookup speed
    date_map = dict(zip(df_source['number'], df_source['dates']))

    print("Generating all 10,000 combinations...")
    master_data = []

    # Iterate from 0 to 9999
    for i in range(10000):
        num_str = str(i).zfill(4)
        
        # Pull dates if they exist, otherwise leave blank
        dates = date_map.get(num_str, "")
        
        master_data.append({
            "number": num_str,
            "dates": dates
        })

    # Convert to DataFrame and save
    df_master = pd.DataFrame(master_data)
    df_master.to_csv(OUTPUT_FILE, index=False)
    
    print(f"--- SUCCESS ---")
    print(f"File saved: {OUTPUT_FILE}")
    print(f"Total Rows: {len(df_master)}")

if __name__ == "__main__":
    generate_master_list()