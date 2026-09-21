import csv
from collections import defaultdict

INPUT = "gaps_detail.csv"
OUTPUT = "similar_gap_groups3.csv"
SIMILARITY_TOLERANCE = 3   # allowed difference between gap values


# STEP 1 — Load gap_days for each number
gaps_for_num = defaultdict(list)

with open(INPUT, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        num = row["number"]
        gap = int(row["gap_days"])
        gaps_for_num[num].append(gap)


# STEP 2 — Compare numbers for similar patterns
def are_similar(g1, g2, tol=SIMILARITY_TOLERANCE):
    if len(g1) != len(g2):
        return False
    return all(abs(a - b) <= tol for a, b in zip(g1, g2))


similar_groups = []
numbers = list(gaps_for_num.keys())
checked = set()

for i in range(len(numbers)):
    n1 = numbers[i]
    if n1 in checked:
        continue

    group = [n1]

    for j in range(i + 1, len(numbers)):
        n2 = numbers[j]

        if are_similar(gaps_for_num[n1], gaps_for_num[n2]):
            group.append(n2)

    if len(group) > 1:
        similar_groups.append(group)

    checked.update(group)


# STEP 3 — Save to CSV (horizontal gaps)
with open(OUTPUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["group_numbers", "gap_sequence"])

    for group in similar_groups:
        # Write each number in the group with its horizontal gaps
        for num in group:
            gap_list_str = ", ".join(map(str, gaps_for_num[num]))
            writer.writerow([" | ".join(group), gap_list_str])

print("CSV saved as:", OUTPUT)
