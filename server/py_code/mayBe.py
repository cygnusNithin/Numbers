import pandas as pd

# Load your CSV with 72 rolls
df = pd.read_csv("fullRoll.csv")

# Group by number_id (each has 4 rollers)
groups = df.groupby("number_id")["sequence"].apply(list).to_dict()
ids = list(groups.keys())

matches_exact = []
matches_rotation = []
matches_partial = []

def is_rotation(a, b):
    """Check if b is a rotation of a"""
    if len(a) != len(b):
        return False
    return any(a == b[i:] + b[:i] for i in range(len(b)))

for i in range(len(ids)):
    for j in range(i+1, len(ids)):
        set1, set2 = groups[ids[i]], groups[ids[j]]

        # 1. Exact match
        if set1 == set2:
            matches_exact.append((ids[i], ids[j]))

        # 2. Rotation match
        elif is_rotation(set1, set2):
            matches_rotation.append((ids[i], ids[j]))

        # 3. Partial overlap (at least 2 rollers same)
        else:
            overlap = len(set(set1) & set(set2))
            if overlap >= 2:
                matches_partial.append((ids[i], ids[j], overlap))

# ==== REPORT ====
if matches_exact:
    print("✅ Exact identical sets found:")
    for m in matches_exact:
        print(f"  number_id {m[0]} and {m[1]}")

if matches_rotation:
    print("\n🔄 Rotation matches found:")
    for m in matches_rotation:
        print(f"  number_id {m[0]} and {m[1]} (rotated)")

if matches_partial:
    print("\n⚠️ Partial overlaps (≥2 rollers same):")
    for m in matches_partial:
        print(f"  number_id {m[0]} and {m[1]} share {m[2]} rollers")

if not (matches_exact or matches_rotation or matches_partial):
    print("❌ No suspicious similarities found")
