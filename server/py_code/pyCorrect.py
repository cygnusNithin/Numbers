input_file = "Results2020.csv"
output_file = "Result2020.csv"

with open(input_file, "r") as infile, open(output_file, "w") as outfile:
    for line in infile:
        # Replace multiple spaces/tabs with a single comma
        cleaned = ",".join(line.strip().split())
        outfile.write(cleaned + "\n")

print(f"✅ Saved cleaned CSV → {output_file}")
