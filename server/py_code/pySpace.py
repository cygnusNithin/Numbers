input_file = "Results2024.csv"
output_file = "Result2024.csv"

with open(input_file, "r") as infile, open(output_file, "w") as outfile:
    for line in infile:
        # Remove spaces after commas
        cleaned = line.replace(", ", ",").strip()
        outfile.write(cleaned + "\n")

print(f"✅ Cleaned CSV saved as {output_file}")
