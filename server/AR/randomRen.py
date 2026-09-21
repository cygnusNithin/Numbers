import random
import csv

DAYS = 1734
NUMBERS_PER_DAY = 274  # rounded from 273.56

output_file = "simulated_lottery_horizontal.csv"

with open(output_file, "w", newline="") as f:
    writer = csv.writer(f)
    
    # Header row
    header = ["day"] + [f"n{i+1}" for i in range(NUMBERS_PER_DAY)]
    writer.writerow(header)

    for day in range(1, DAYS + 1):
        # Generate 4-digit formatted numbers
        numbers = [f"{random.randint(0, 9999):04d}" for _ in range(NUMBERS_PER_DAY)]
        
        # Write one full row per day
        writer.writerow([day] + numbers)

print("Horizontal simulation completed.")
